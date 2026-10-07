"""Real ROS DDS/services/actions through the actual SDK and a socket RIC peer."""

import math
import threading
import time

import pytest

rclpy = pytest.importorskip('rclpy')
from action_msgs.msg import GoalStatus  # noqa: E402
from firmware_peer import FirmwarePeer  # noqa: E402
from marty_driver.node import MartyDriver  # noqa: E402
from rclpy.action import ActionClient  # noqa: E402
from rclpy.executors import MultiThreadedExecutor  # noqa: E402
from rclpy.node import Node  # noqa: E402
from rclpy.qos import qos_profile_sensor_data  # noqa: E402
from sensor_msgs.msg import BatteryState, Imu, JointState  # noqa: E402
from std_srvs.srv import Trigger  # noqa: E402
from test_session import wait_for  # noqa: E402

from marty_interfaces.action import Motion  # noqa: E402
from marty_interfaces.msg import DriverStatus, ServoStates, Telemetry  # noqa: E402


@pytest.fixture
def ros_fixture():
    peer = FirmwarePeer()
    rclpy.init(args=['--ros-args', '-p', 'method:=wifi', '-p', 'locator:=127.0.0.1',
                     '-p', f'wifi_port:={peer.port}', '-p', 'auto_connect:=true',
                     '-p', 'stale_after_seconds:=0.6', '-p', 'reconnect_interval_seconds:=0.1'])
    driver = MartyDriver(namespace='marty')
    probe = Node('marty_probe', use_global_arguments=False)
    executor = MultiThreadedExecutor(num_threads=6)
    executor.add_node(driver)
    executor.add_node(probe)
    thread = threading.Thread(target=executor.spin, daemon=True)
    thread.start()
    try:
        wait_for(lambda: driver.session.status()['motion_status_valid'], 8)
        yield peer, driver, probe
    finally:
        driver.session.close()
        executor.shutdown(timeout_sec=3)
        thread.join(3)
        driver.destroy_node()
        probe.destroy_node()
        rclpy.shutdown()
        peer.close()


def send(probe, goal):
    client = ActionClient(probe, Motion, '/marty/motion')
    assert client.wait_for_server(timeout_sec=3)
    future = client.send_goal_async(goal)
    wait_for(future.done)
    return client, future.result()


def service(probe, name):
    client = probe.create_client(Trigger, f'/marty/{name}')
    assert client.wait_for_service(timeout_sec=2)
    future = client.call_async(Trigger.Request())
    wait_for(future.done, 10)
    response = future.result()
    probe.destroy_client(client)
    return response


def joint_goal(duration=500):
    return Motion.Goal(command=Motion.Goal.MOVE_JOINT, joint_id=8,
                       position_degrees=5, move_time_ms=duration)


def test_real_sdk_telemetry_units_and_dds_fanout(ros_fixture):
    peer, driver, probe = ros_fixture
    joints, second, imus, batteries, servos, raw, statuses = [], [], [], [], [], [], []
    subscriptions = [probe.create_subscription(kind, topic, target.append, qos_profile_sensor_data)
                     for kind, topic, target in (
                         (JointState, '/marty/joint_states', joints),
                         (JointState, '/marty/joint_states', second),
                         (Imu, '/marty/imu/data_raw', imus),
                         (BatteryState, '/marty/battery', batteries),
                         (ServoStates, '/marty/servo_states', servos),
                         (Telemetry, '/marty/telemetry', raw),
                         (DriverStatus, '/marty/status', statuses))]
    wait_for(lambda: all((joints, second, imus, batteries, servos, raw, statuses)))
    assert joints[-1].position[0] == pytest.approx(math.pi / 6)
    assert joints[-1].name[0] == 'left_hip'
    assert not joints[-1].velocity and not joints[-1].effort
    assert joints[-1].position == second[-1].position
    assert servos[-1].servos[0].current_amperes == pytest.approx(0.12)
    assert imus[-1].linear_acceleration.z == pytest.approx(9.80665)
    assert imus[-1].orientation_covariance[0] == -1
    assert imus[-1].angular_velocity_covariance[0] == -1
    assert batteries[-1].percentage == pytest.approx(0.75)
    assert batteries[-1].charge == pytest.approx(0.6)
    assert batteries[-1].current == pytest.approx(-0.2)
    assert math.isnan(batteries[-1].voltage)
    assert statuses[-1].connected
    assert driver.describe_parameter('locator').read_only
    assert len(peer.connections) == 1
    for subscription in subscriptions:
        probe.destroy_subscription(subscription)


def test_action_completion_busy_validation_cancel_and_stop(ros_fixture):
    peer, driver, probe = ros_fixture
    client, goal = send(probe, joint_goal())
    assert goal.accepted
    result = goal.get_result_async()
    time.sleep(0.1)
    assert not result.done(), 'A command acknowledgement is not movement completion'
    other_client, rejected = send(probe, joint_goal())
    assert not rejected.accepted
    other_client.destroy()
    wait_for(result.done)
    assert result.result().status == GoalStatus.STATUS_SUCCEEDED
    assert result.result().result.success
    client.destroy()

    client, invalid = send(probe, joint_goal(0))
    assert not invalid.accepted
    client.destroy()

    client, goal = send(probe, joint_goal(3000))
    wait_for(lambda: driver.session.active.acknowledged_at is not None)
    result = goal.get_result_async()
    canceled = goal.cancel_goal_async()
    wait_for(canceled.done)
    assert canceled.result().goals_canceling
    wait_for(result.done)
    assert result.result().status == GoalStatus.STATUS_CANCELED
    assert not result.result().result.success
    assert peer.commands[-1] == 'robot/stop'
    client.destroy()

    client, goal = send(probe, joint_goal(3000))
    wait_for(lambda: driver.session.active.acknowledged_at is not None)
    result = goal.get_result_async()
    assert service(probe, 'stop').success
    wait_for(result.done)
    assert result.result().status == GoalStatus.STATUS_ABORTED
    client.destroy()


def test_stale_samples_stop_publishing_and_disconnect_disables_reconnect(ros_fixture):
    peer, driver, probe = ros_fixture
    imus = []
    subscription = probe.create_subscription(Imu, '/marty/imu/data_raw', imus.append,
                                             qos_profile_sensor_data)
    wait_for(lambda: len(imus) > 2)
    peer.silent = True
    time.sleep(0.25)
    count = len(imus)
    time.sleep(0.2)
    assert len(imus) == count
    assert service(probe, 'disconnect').success
    generation = driver.session.generation
    time.sleep(0.3)
    assert driver.session.generation == generation
    assert not driver.session.status()['connected']
    peer.silent = False
    assert service(probe, 'connect').success
    wait_for(lambda: driver.session.status()['motion_status_valid'], 8)
    probe.destroy_subscription(subscription)


def test_transport_loss_aborts_and_reconnect_never_replays_motion(ros_fixture):
    peer, driver, probe = ros_fixture
    client, goal = send(probe, joint_goal(3000))
    wait_for(lambda: driver.session.active.acknowledged_at is not None)
    result = goal.get_result_async()
    generation = driver.session.generation
    peer.drop_connections()
    peer.silent = True
    wait_for(result.done, 8)
    assert result.result().status == GoalStatus.STATUS_ABORTED
    peer.silent = False
    wait_for(lambda: driver.session.generation > generation and
             driver.session.status()['motion_status_valid'], 10)
    assert sum(c.startswith('traj/') for c in peer.commands) == 1
    client.destroy()


@pytest.mark.parametrize('command,fragment', [
    (Motion.Goal.WALK, 'traj/step/1?stepLength=10&turn=5'),
    (Motion.Goal.DANCE, 'traj/dance?'),
    (Motion.Goal.KICK, 'traj/kick?'),
    (Motion.Goal.STAND, 'traj/standStraight?'),
])
def test_all_high_level_movements_reach_the_sdk_firmware_interface(
    ros_fixture, command, fragment,
):
    peer, driver, probe = ros_fixture
    client, goal = send(probe, Motion.Goal(
        command=command, num_steps=1, side='right', turn_degrees=5,
        step_length_mm=10, move_time_ms=200,
    ))
    assert goal.accepted
    result = goal.get_result_async()
    wait_for(result.done)
    assert result.result().result.success
    assert any(c.startswith(fragment) for c in peer.commands)
    client.destroy()
