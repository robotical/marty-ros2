"""Verify the installed ROS launch carries actual motion all the way to TF."""

import os
import signal
import subprocess
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from tf2_msgs.msg import TFMessage


def test_installed_simulation_command_feedback_and_tf(tmp_path, monkeypatch):
    # colcon runs other packages' hardware-driver tests concurrently. Keep this
    # graph isolated so their deliberate driver launches are not mistaken for ours.
    monkeypatch.setenv('ROS_DOMAIN_ID', '85')
    log = (tmp_path / 'simulation.log').open('w+')
    process = subprocess.Popen([
        'ros2', 'launch', 'marty_simulation', 'simulation.launch.py',
        'gui:=false', 'rviz:=false',
    ], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    rclpy.init()
    probe = Node('simulation_probe', use_global_arguments=False)
    feedback, transforms = [], []
    probe.create_subscription(JointState, '/marty_sim/joint_states', feedback.append, 10)
    probe.create_subscription(TFMessage, '/tf', lambda msg: transforms.extend(msg.transforms), 10)
    command = probe.create_publisher(JointState, '/marty_sim/joint_commands', 10)

    def wait_for(predicate, timeout=15):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            rclpy.spin_once(probe, timeout_sec=0.05)
        log.flush()
        assert predicate(), (tmp_path / 'simulation.log').read_text()

    try:
        wait_for(lambda: feedback and command.get_subscription_count() > 0)
        wait_for(lambda: ('marty_simulation', '/marty_sim')
                 in probe.get_node_names_and_namespaces())
        nodes = probe.get_node_names_and_namespaces()
        assert ('marty_simulation', '/marty_sim') in nodes
        assert ('robot_state_publisher', '/marty_sim') in nodes
        assert not any(name == 'marty_driver' for name, _ in nodes)
        assert not probe.get_service_names_and_types() or not any(
            name == '/marty/connect' for name, _ in probe.get_service_names_and_types())
        target = JointState(name=['eye_left_joint'], position=[-0.5])
        command.publish(target)
        wait_for(lambda: any(
            abs(dict(zip(msg.name, msg.position)).get('eye_left_joint', 0) + 0.5) < 0.02
            for msg in feedback))
        wait_for(lambda: any(t.child_frame_id == 'marty_sim/eye_right'
                            and t.transform.rotation.x > 0.2 for t in transforms))
        wait_for(lambda: any(t.header.frame_id == 'world'
                            and t.child_frame_id == 'marty_sim/base_link'
                            and t.transform.translation.z > 0.1 for t in transforms))
    finally:
        probe.destroy_node()
        rclpy.shutdown()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        log.close()
