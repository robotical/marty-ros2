"""Launch one Marty with package defaults, local robot settings and CLI overrides."""

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import EnvironmentVariable, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from marty_driver.config import DEFAULT_PARAMETERS

from marty_bringup.config import load_robots


def runtime_node(context):
    parameters = [LaunchConfiguration('params_file')]
    robots_file = LaunchConfiguration('robots_file').perform(context)
    if robots_file:
        namespace = '/' + LaunchConfiguration('namespace').perform(context).strip('/')
        robots = load_robots(robots_file)
        if namespace not in robots:
            raise ValueError(f'{namespace} is not configured in {robots_file}')
        parameters.append({
            key: ParameterValue(value, value_type=type(DEFAULT_PARAMETERS[key]))
            for key, value in robots[namespace].items()
        })
    overrides = {}
    for name, default in DEFAULT_PARAMETERS.items():
        value = LaunchConfiguration(name).perform(context)
        if value == '':
            continue
        if isinstance(default, bool):
            if value.lower() not in ('true', 'false'):
                raise ValueError(f'{name} must be true or false')
            value = value.lower() == 'true'
        else:
            value = type(default)(value)
        overrides[name] = ParameterValue(value, value_type=type(default))
    return [Node(
        package='marty_driver', executable='marty_driver_node',
        namespace=LaunchConfiguration('namespace'), output='screen',
        parameters=parameters + [overrides],
    )]


def generate_launch_description():
    default_file = get_package_share_directory('marty_bringup') + '/config/marty.yaml'
    arguments = [
        DeclareLaunchArgument('namespace', default_value='marty', description='Robot namespace'),
        DeclareLaunchArgument('robots_file', default_value=EnvironmentVariable(
            'MARTY_ROS_ROBOTS_FILE', default_value=''), description='Local robot YAML file'),
        DeclareLaunchArgument('params_file', default_value=default_file,
                             description='ROS parameter YAML file'),
        *[DeclareLaunchArgument(name, default_value='',
                               description='Override the configured driver parameter')
          for name in DEFAULT_PARAMETERS],
    ]
    return LaunchDescription(arguments + [OpaqueFunction(function=runtime_node)])
