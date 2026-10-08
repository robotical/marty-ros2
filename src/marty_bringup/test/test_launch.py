"""Exercise an installed launch, explicit connection and config precedence through DDS."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

rclpy = pytest.importorskip('rclpy')
from rcl_interfaces.srv import GetParameters  # noqa: E402
from rclpy.node import Node  # noqa: E402
from rclpy.qos import qos_profile_sensor_data  # noqa: E402
from sensor_msgs.msg import Imu  # noqa: E402
from std_srvs.srv import Trigger  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'marty_driver/test'))
from firmware_peer import FirmwarePeer  # noqa: E402


def request(probe, service_type, name, message):
    client = probe.create_client(service_type, name)
    try:
        assert client.wait_for_service(timeout_sec=15), f'{name} did not appear'
        future = client.call_async(message)
        rclpy.spin_until_future_complete(probe, future, timeout_sec=15)
        assert future.done(), f'{name} timed out'
        return future.result()
    finally:
        probe.destroy_client(client)


def test_installed_launch_manual_connection_and_overrides(tmp_path):
    peer = FirmwarePeer()
    robots = tmp_path / 'robot settings.yaml'
    robots.write_text(yaml.safe_dump({'martys': {
        'configured': {'method': 'wifi', 'locator': '127.0.0.1', 'wifi_port': peer.port,
                       'auto_connect': False, 'auto_reconnect': False, 'subscribe_rate_hz': 12},
        'other': {'method': 'usb', 'locator': '/dev/not-selected'},
    }}))
    params = tmp_path / 'defaults.yaml'
    params.write_text(yaml.safe_dump({'/**': {'ros__parameters': {
        'auto_connect': True, 'subscribe_rate_hz': 7.0, 'imu_frame': 'configured_frame',
    }}}))
    env = dict(os.environ, MARTY_ROS_ROBOTS_FILE=str(robots))
    log = (tmp_path / 'launch.log').open('w+')
    process = subprocess.Popen([
        'ros2', 'launch', 'marty_bringup', 'bringup.launch.py', 'namespace:=configured',
        f'params_file:={params}', 'subscribe_rate_hz:=15.0',
    ], env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    rclpy.init()
    probe = Node('config_probe', use_global_arguments=False)
    try:
        response = request(probe, GetParameters, '/configured/marty_driver/get_parameters',
                           GetParameters.Request(names=[
                               'auto_connect', 'subscribe_rate_hz', 'imu_frame', 'wifi_port']))
        assert not response.values[0].bool_value  # Robot config overrides parameter YAML.
        assert response.values[1].double_value == 15.0  # Explicit CLI overrides robot config.
        assert response.values[2].string_value == 'configured_frame'  # YAML fallback survives.
        assert response.values[3].integer_value == peer.port
        time.sleep(0.3)
        assert not peer.connections, 'Launch must not connect when auto_connect is false'
        measurements = []
        probe.create_subscription(Imu, '/configured/imu/data_raw', measurements.append,
                                  qos_profile_sensor_data)
        connected = request(probe, Trigger, '/configured/connect', Trigger.Request())
        assert connected.success, connected.message
        deadline = time.monotonic() + 10
        while not measurements and time.monotonic() < deadline:
            rclpy.spin_once(probe, timeout_sec=0.1)
        assert measurements, 'Accelerometer telemetry must arrive after explicit connect'
        assert measurements[-1].linear_acceleration.z == pytest.approx(9.80665)
        assert measurements[-1].header.frame_id == 'configured_frame'
        assert request(probe, Trigger, '/configured/disconnect', Trigger.Request()).success
    finally:
        probe.destroy_node()
        rclpy.shutdown()
        os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        peer.close()
        log.close()
