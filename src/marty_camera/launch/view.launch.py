from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('source', description='Pi camera stream URL, tcp://PI_ADDRESS:5000'),
        DeclareLaunchArgument('rviz', default_value='true'),
        DeclareLaunchArgument('publish_rate_hz', default_value='10.0'),
        Node(
            package='marty_camera', executable='camera_receiver', namespace='marty/camera',
            parameters=[{
                'source': LaunchConfiguration('source'),
                'publish_rate_hz': ParameterValue(LaunchConfiguration('publish_rate_hz'), value_type=float),
            }], output='screen',
        ),
        Node(
            package='rviz2', executable='rviz2',
            arguments=['-d', get_package_share_directory('marty_camera') + '/config/camera.rviz'],
            condition=IfCondition(LaunchConfiguration('rviz')), output='screen',
        ),
    ])
