"""Run a simulated Marty, its joint controls and RViz; no physical driver."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    model = Path(get_package_share_directory('marty2_description'))
    simulation = Path(get_package_share_directory('marty_simulation'))
    description = {'robot_description': (model / 'urdf/marty2.urdf').read_text()}
    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='true', description='Open joint sliders'),
        DeclareLaunchArgument('rviz', default_value='true', description='Open RViz'),
        DeclareLaunchArgument('mode', default_value='stabilized',
                              choices=['stabilized', 'free'],
                              description='Assisted visualization or unassisted source model'),
        Node(package='marty_simulation', executable='marty_simulation_node',
             namespace='marty_sim', output='screen',
             parameters=[{'mode': LaunchConfiguration('mode'), 'frame_prefix': 'marty_sim/'}]),
        Node(package='robot_state_publisher', executable='robot_state_publisher',
             namespace='marty_sim', output='screen',
             parameters=[description, {'frame_prefix': 'marty_sim/'}]),
        Node(package='joint_state_publisher_gui', executable='joint_state_publisher_gui',
             namespace='marty_sim', name='joint_controls', output='screen',
             parameters=[description], remappings=[('joint_states', 'joint_commands')],
             condition=IfCondition(LaunchConfiguration('gui'))),
        Node(package='rviz2', executable='rviz2', name='marty_rviz', output='screen',
             arguments=['-d', str(simulation / 'config/marty.rviz')],
             condition=IfCondition(LaunchConfiguration('rviz'))),
    ])
