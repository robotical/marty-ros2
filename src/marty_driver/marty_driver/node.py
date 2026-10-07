"""ROS actions, acknowledged services and receipt-stamped Marty V2 telemetry."""

import math
import threading
import time

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import BatteryState, Imu, JointState
from std_msgs.msg import Header
from std_srvs.srv import Trigger

from marty_interfaces.action import Motion as MotionAction
from marty_interfaces.msg import DriverStatus, ServoState, ServoStates, Telemetry

from .motion import Motion
from .session import Session
from .telemetry import battery_values, joint_mapping, json_values, servo_values


class MartyDriver(Node):
    """Each driver owns one robot; all names are relative to its namespace."""

    def __init__(self, **kwargs):
        super().__init__('marty_driver', **kwargs)
        defaults = {
            'method': 'usb', 'locator': '', 'serial_baud': 115200, 'wifi_port': 80,
            'subscribe_rate_hz': 10.0, 'auto_connect': False, 'auto_reconnect': True,
            'stale_after_seconds': 2.0, 'reconnect_interval_seconds': 2.0,
            'completion_margin_seconds': 5.0, 'joint_map': '{}',
            'acceleration_scale': 9.80665, 'imu_frame': 'marty_accelerometer',
            'battery_frame': 'marty_battery',
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value, ParameterDescriptor(read_only=True))
        p = {name: self.get_parameter(name).value for name in defaults}
        self.mapping = joint_mapping(p['joint_map'])
        self.accel_scale = p['acceleration_scale']
        if not math.isfinite(self.accel_scale) or self.accel_scale <= 0:
            raise ValueError('acceleration_scale must be positive and finite')
        self.imu_frame, self.battery_frame = p['imu_frame'], p['battery_frame']
        self.session = Session(
            method=p['method'], locator=p['locator'], rate_hz=p['subscribe_rate_hz'],
            baud=p['serial_baud'], port=p['wifi_port'], stale_after=p['stale_after_seconds'],
            reconnect_interval=p['reconnect_interval_seconds'], auto_reconnect=p['auto_reconnect'],
            completion_margin=p['completion_margin_seconds'],
            stamp=lambda: self.get_clock().now().nanoseconds,
        )
        self.control_group = ReentrantCallbackGroup()
        self._rpc_slots = threading.BoundedSemaphore(2)
        self._goals_lock = threading.Lock()
        self._reservations = {}
        self._goals = {}
        self._closing = threading.Event()
        retained = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.status_pub = self.create_publisher(DriverStatus, 'status', retained)
        self.diag_pub = self.create_publisher(DiagnosticArray, 'diagnostics', 10)
        self.raw_pub = self.create_publisher(Telemetry, 'telemetry', qos_profile_sensor_data)
        self.joint_pub = self.create_publisher(JointState, 'joint_states', qos_profile_sensor_data)
        self.servo_pub = self.create_publisher(ServoStates, 'servo_states', qos_profile_sensor_data)
        self.imu_pub = self.create_publisher(Imu, 'imu/data_raw', qos_profile_sensor_data)
        self.battery_pub = self.create_publisher(BatteryState, 'battery', qos_profile_sensor_data)
        self.control_services = [self.create_service(
            Trigger, name, self._service(operation), callback_group=self.control_group
        ) for name, operation in (
            ('connect', self.session.connect), ('disconnect', self.session.disconnect),
            ('stop', self.session.stop),
        )]
        self.action = ActionServer(
            self, MotionAction, 'motion', execute_callback=self._execute,
            goal_callback=self._goal, cancel_callback=self._cancel,
            handle_accepted_callback=self._accepted, callback_group=self.control_group,
        )
        self.timer = self.create_timer(0.05, self._publish)
        self._last_status = 0.0
        if p['auto_connect']:
            self.session.connect()

    def _service(self, operation):
        def call(request, response):
            if not self._rpc_slots.acquire(blocking=False):
                response.message = 'Two connection/control requests are already running'
                return response
            try:
                response.success = bool(operation().result(timeout=40))
                response.message = 'Acknowledged' if response.success else (
                    self.session.status()['last_error'] or 'Request was not acknowledged'
                )
            except Exception as exc:
                response.message = str(exc)
            finally:
                self._rpc_slots.release()
            return response
        return call

    @staticmethod
    def _request(request):
        return Motion(**{name: getattr(request, name) for name in Motion.__dataclass_fields__})

    def _goal(self, request):
        try:
            ticket = self.session.reserve(self._request(request))
            with self._goals_lock:
                self._reservations[id(request)] = ticket
            return GoalResponse.ACCEPT
        except (ValueError, RuntimeError) as exc:
            self.get_logger().warning(f'Movement rejected: {exc}')
            return GoalResponse.REJECT

    def _accepted(self, handle):
        with self._goals_lock:
            ticket = self._reservations.pop(id(handle.request))
            self._goals[bytes(handle.goal_id.uuid)] = ticket
        handle.execute()

    def _cancel(self, handle):
        with self._goals_lock:
            ticket = self._goals.get(bytes(handle.goal_id.uuid))
        if ticket is None or ticket.result.done():
            return CancelResponse.REJECT
        self.session.stop(ticket, reason='canceled')
        return CancelResponse.ACCEPT

    def _execute(self, handle):
        key = bytes(handle.goal_id.uuid)
        with self._goals_lock:
            ticket = self._goals[key]
        self.session.start(ticket)
        started, last_feedback = time.monotonic(), 0.0
        try:
            while not ticket.result.done() and not self._closing.is_set():
                now = time.monotonic()
                if now - last_feedback >= 0.1:
                    status = self.session.status()
                    handle.publish_feedback(MotionAction.Feedback(
                        phase='stopping' if ticket.stop_reason else (
                            'moving' if ticket.acknowledged_at else 'sending'
                        ), elapsed_seconds=now - started, moving=status['moving'],
                        queued_movements=max(0, status['queued_movements']),
                    ))
                    last_feedback = now
                time.sleep(0.02)
            if not ticket.result.done():
                handle.abort()
                return MotionAction.Result(success=False, message='Driver shutting down')
            success, outcome, message = ticket.result.result()
            if outcome == 'canceled':
                # The cancel response changes the ROS goal state after our callback returns.
                deadline = time.monotonic() + 1.0
                while not handle.is_cancel_requested and time.monotonic() < deadline:
                    time.sleep(0.01)
            if outcome == 'canceled' and handle.is_cancel_requested:
                handle.canceled()
            elif success:
                handle.succeed()
            else:
                handle.abort()
            return MotionAction.Result(success=success, message=message)
        finally:
            with self._goals_lock:
                self._goals.pop(key, None)

    @staticmethod
    def _header(sample, frame=''):
        header = Header(frame_id=frame)
        header.stamp.sec, header.stamp.nanosec = divmod(sample.stamp_ns, 1_000_000_000)
        return header

    def _publish(self):
        for sample in self.session.drain():
            # Ignore any sample invalidated by a disconnect before this timer drained it.
            if sample.generation != self.session.generation:
                continue
            header = self._header(sample)
            self.raw_pub.publish(Telemetry(
                header=header, generation=sample.generation, topic_id=sample.topic,
                values_json=json_values(sample.data),
            ))
            if sample.topic == 120:
                servos = [ServoState(**v) for v in servo_values(sample.data, self.mapping)]
                self.servo_pub.publish(ServoStates(header=header, servos=servos))
                valid = [s for s in servos if math.isfinite(s.position_radians)]
                self.joint_pub.publish(JointState(
                    header=header, name=[s.name for s in valid],
                    position=[s.position_radians for s in valid],
                ))
            elif sample.topic == 121:
                values = sample.data
                if len(values) == 3 and all(math.isfinite(float(v)) for v in values):
                    imu = Imu(header=self._header(sample, self.imu_frame))
                    imu.orientation_covariance[0] = -1.0
                    imu.angular_velocity_covariance[0] = -1.0
                    imu.linear_acceleration.x, imu.linear_acceleration.y, (
                        imu.linear_acceleration.z
                    ) = [float(v) * self.accel_scale for v in values]
                    self.imu_pub.publish(imu)
            elif sample.topic == 122:
                values = battery_values(sample.data)
                if values is not None:
                    self.battery_pub.publish(BatteryState(
                        header=self._header(sample, self.battery_frame), **values,
                    ))
        now = time.monotonic()
        if now - self._last_status >= 0.2:
            status = self.session.status()
            header = Header(stamp=self.get_clock().now().to_msg())
            self.status_pub.publish(DriverStatus(header=header, **status))
            healthy = status['connected'] and status['motion_status_valid']
            diagnostic = DiagnosticStatus(
                name=f'{self.get_namespace()}/marty_connection', hardware_id=self.session.config[1],
                level=DiagnosticStatus.OK if healthy else DiagnosticStatus.WARN,
                message='Ready' if healthy else status['last_error'] or status['connection_state'],
                values=[KeyValue(key=k, value=str(v)) for k, v in status.items()],
            )
            self.diag_pub.publish(DiagnosticArray(header=header, status=[diagnostic]))
            self._last_status = now

    def destroy_node(self):
        self.timer.cancel()
        self._closing.set()
        self.session.close()
        self.action.destroy()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    executor = MultiThreadedExecutor(num_threads=6)
    try:
        node = MartyDriver()
        executor.add_node(node)
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node:
            node.destroy_node()
        executor.shutdown(timeout_sec=3)
        if rclpy.ok():
            rclpy.shutdown()
