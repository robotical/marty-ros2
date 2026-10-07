"""Hardware ROS smoke check: telemetry, eyebrow motion, cancel, stop and reconnect."""

import json
import os
import threading
import time
from pathlib import Path

import rclpy
from action_msgs.msg import GoalStatus
from marty_driver.node import MartyDriver
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import BatteryState, Imu, JointState
from std_srvs.srv import Trigger
from usb_pty import USBPTY

from marty_interfaces.action import Motion
from marty_interfaces.msg import DriverStatus


def wait_for(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    assert predicate(), 'Hardware check timed out'


def main():
    link = USBPTY()
    baud = os.environ.get('MARTY_SERIAL_BAUD', '115200')
    rclpy.init(args=['--ros-args', '-p', f'locator:={link.path}', '-p', f'serial_baud:={baud}',
                     '-p', 'auto_connect:=true'])
    driver = MartyDriver(namespace='marty')
    probe = Node('marty_hardware_probe', use_global_arguments=False)
    executor = MultiThreadedExecutor(num_threads=6)
    executor.add_node(driver)
    executor.add_node(probe)
    thread = threading.Thread(target=executor.spin, daemon=True)
    thread.start()
    joints, imus, statuses, batteries = [], [], [], []
    subscriptions = [probe.create_subscription(kind, topic, target.append, qos_profile_sensor_data)
                     for kind, topic, target in (
                         (JointState, '/marty/joint_states', joints),
                         (Imu, '/marty/imu/data_raw', imus),
                         (DriverStatus, '/marty/status', statuses),
                         (BatteryState, '/marty/battery', batteries))]
    client = ActionClient(probe, Motion, '/marty/motion')
    report = {'checks': []}

    def check(name):
        report['checks'].append(name)
        print(f'PASS: {name}', flush=True)

    def motion(position, duration):
        future = client.send_goal_async(Motion.Goal(
            command=Motion.Goal.MOVE_JOINT, joint_id=8,
            position_degrees=position, move_time_ms=duration,
        ))
        wait_for(future.done)
        goal = future.result()
        assert goal.accepted
        return goal, goal.get_result_async()

    def service(name):
        service_client = probe.create_client(Trigger, f'/marty/{name}')
        assert service_client.wait_for_service(timeout_sec=3)
        future = service_client.call_async(Trigger.Request())
        wait_for(future.done, 35)
        response = future.result()
        probe.destroy_client(service_client)
        assert response.success, response.message

    original_eye = None
    try:
        wait_for(lambda: joints and imus and statuses and statuses[-1].motion_status_valid, 35)
        assert len(joints[-1].name) == 9
        original_eye = round(
            joints[-1].position[joints[-1].name.index('eyes')] * 180 / 3.1415926536
        )
        report['firmware'] = driver.session.sdk.get_system_info()
        report['initial_eye_degrees'] = original_eye
        report['initial_acceleration_m_s2'] = [getattr(imus[-1].linear_acceleration, a)
                                              for a in ('x', 'y', 'z')]
        check('Actual MartyPy USB handshake, nine joint states and IMU delivered through ROS DDS')
        assert imus[-1].orientation_covariance[0] == -1
        assert imus[-1].angular_velocity_covariance[0] == -1
        assert not joints[-1].effort
        check('Unavailable orientation/gyro/torque correctly represented')
        assert client.wait_for_server(timeout_sec=3)

        target = max(-20, min(20, original_eye + 8))
        goal, result = motion(target, 800)
        wait_for(result.done)
        assert result.result().status == GoalStatus.STATUS_SUCCEEDED
        wait_for(lambda: abs(joints[-1].position[joints[-1].name.index('eyes')] *
                             180 / 3.1415926536 - target) <= 3)
        check('Eyebrow action completes with fresh idle status and measured position change')

        goal, result = motion(original_eye, 4000)
        wait_for(lambda: driver.session.active.acknowledged_at is not None)
        time.sleep(0.3)
        cancel = goal.cancel_goal_async()
        wait_for(cancel.done)
        assert cancel.result().goals_canceling
        wait_for(result.done)
        assert result.result().status == GoalStatus.STATUS_CANCELED
        check('Action cancellation clears firmware movement and confirms idle status')

        goal, result = motion(target, 4000)
        wait_for(lambda: driver.session.active.acknowledged_at is not None)
        time.sleep(0.3)
        service('stop')
        wait_for(result.done)
        assert result.result().status == GoalStatus.STATUS_ABORTED
        check('Stop service interrupts an active action')

        before = driver.session.generation
        service('disconnect')
        wait_for(lambda: statuses and not statuses[-1].connected)
        service('connect')
        wait_for(lambda: driver.session.generation > before and
                 driver.session.status()['motion_status_valid'], 35)
        check('Explicit USB disconnect/reconnect restores telemetry')

        goal, result = motion(original_eye, 800)
        wait_for(result.done)
        assert result.result().result.success
        check('Original eyebrow position restored')
        report['battery_samples'] = len(batteries)
        report['joint_samples'] = len(joints)
        report['imu_samples'] = len(imus)
        report['relay_error'] = str(link.error) if link.error else None
        assert link.error is None
        Path('/results/hardware.json').write_text(json.dumps(report, indent=2) + '\n')
    finally:
        # On any failed assertion, stop outstanding work before disconnecting.
        if driver.session.sdk is not None:
            driver.session.stop().result(5)
        client.destroy()
        for subscription in subscriptions:
            probe.destroy_subscription(subscription)
        driver.session.close()
        executor.shutdown(timeout_sec=3)
        thread.join(3)
        driver.destroy_node()
        probe.destroy_node()
        rclpy.shutdown()
        link.close()


if __name__ == '__main__':
    main()
