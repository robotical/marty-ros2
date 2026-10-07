"""Launch an independently namespaced Marty V2 driver."""

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    default_file = get_package_share_directory('marty_bringup') + '/config/marty.yaml'
    args = {
        'namespace': ('marty', 'ROS namespace for this robot'),
        'method': ('usb', 'usb, wifi or exp'),
        'locator': ('', 'Explicit serial port or Wi-Fi hostname/IP'),
        'serial_baud': ('115200', 'Initial serial baud; MartyPy can switch baud automatically'),
        'wifi_port': ('80', 'Firmware WebSocket port'),
        'auto_connect': ('true', 'Connect on launch'),
        'params_file': (default_file, 'ROS parameter YAML file'),
    }
    parameters = [LaunchConfiguration('params_file'), {
        key: ParameterValue(LaunchConfiguration(key), value_type=kind)
        for key, kind in (('method', str), ('locator', str), ('serial_baud', int),
                          ('wifi_port', int), ('auto_connect', bool))
    }]
    return LaunchDescription([
        *[DeclareLaunchArgument(key, default_value=value, description=description)
          for key, (value, description) in args.items()],
        Node(package='marty_driver', executable='marty_driver_node',
             namespace=LaunchConfiguration('namespace'), output='screen', parameters=parameters),
    ])
