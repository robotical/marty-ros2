"""Publish simulated joint feedback and the floating base transform for RViz."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import TransformStamped
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from tf2_ros import TransformBroadcaster

from marty_simulation.physics import MartyPhysics


class MartySimulation(Node):
    def __init__(self):
        super().__init__('marty_simulation')
        self.declare_parameter('mode', 'stabilized')
        self.declare_parameter('frame_prefix', 'marty_sim/')
        self.prefix = self.get_parameter('frame_prefix').value
        share = Path(get_package_share_directory('marty_simulation'))
        self.physics = MartyPhysics(share / 'physics/marty2_full.xml',
                                    self.get_parameter('mode').value)
        self.publisher = self.create_publisher(JointState, 'joint_states', 10)
        self.transforms = TransformBroadcaster(self)
        self.create_subscription(JointState, 'joint_commands', self.command,
                                 qos_profile_sensor_data)
        self.create_timer(float(self.physics.model.opt.timestep) * 40, self.tick)
        self.get_logger().info(
            f'Simulated Marty ready ({self.physics.mode}); commands use radians')

    def command(self, message):
        try:
            self.physics.set_targets(message.name, message.position)
        except ValueError as error:
            self.get_logger().warning(f'Rejected joint command: {error}')

    def tick(self):
        self.physics.step()
        stamp = self.get_clock().now().to_msg()
        state = JointState()
        state.header.stamp = stamp
        state.name, state.position, state.velocity = self.physics.joint_state()
        self.publisher.publish(state)
        transform = TransformStamped()
        transform.header.stamp = stamp
        transform.header.frame_id = 'world'
        transform.child_frame_id = self.prefix + 'base_link'
        pos = self.physics.data.qpos
        transform.transform.translation.x = float(pos[0])
        transform.transform.translation.y = float(pos[1])
        transform.transform.translation.z = float(pos[2])
        # MuJoCo uses w,x,y,z; ROS uses x,y,z,w.
        transform.transform.rotation.w = float(pos[3])
        transform.transform.rotation.x = float(pos[4])
        transform.transform.rotation.y = float(pos[5])
        transform.transform.rotation.z = float(pos[6])
        self.transforms.sendTransform(transform)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = MartySimulation()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
