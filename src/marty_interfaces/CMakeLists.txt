cmake_minimum_required(VERSION 3.16)
project(marty_interfaces)
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(action_msgs REQUIRED)
rosidl_generate_interfaces(${PROJECT_NAME}
  "action/Motion.action"
  "msg/DriverStatus.msg"
  "msg/ServoState.msg"
  "msg/ServoStates.msg"
  "msg/Telemetry.msg"
  DEPENDENCIES std_msgs action_msgs
)
ament_export_dependencies(rosidl_default_runtime)
ament_package()
