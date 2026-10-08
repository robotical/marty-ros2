# Marty ROS 2 interfaces

## ROS interface

All names are relative to the launch namespace (default `/marty`).

| Name | Type | Contract |
|---|---|---|
| `motion` | `marty_interfaces/action/Motion` | Walk, dance, kick, stand or move one joint; one admitted goal |
| `stop` | `std_srvs/srv/Trigger` | Request `clear and stop`; success means firmware acknowledged it |
| `connect`, `disconnect` | `std_srvs/srv/Trigger` | Explicit connection lifecycle; disconnect disables automatic reconnect |
| `status` | `marty_interfaces/msg/DriverStatus` | Retained state, freshness, moving/paused/queue validity, generation and errors |
| `joint_states` | `sensor_msgs/msg/JointState` | Valid measured positions in radians; velocity/effort left empty |
| `servo_states` | `marty_interfaces/msg/ServoStates` | Measured angles, motor current in amperes, flags and communication validity |
| `imu/data_raw` | `sensor_msgs/msg/Imu` | Acceleration in m/s²; orientation and angular velocity unavailable |
| `battery` | `sensor_msgs/msg/BatteryState` | Valid battery information only; unknown voltage/design capacity are NaN |
| `telemetry` | `marty_interfaces/msg/Telemetry` | Decoded SDK data with original names, units and validity flags |
| `diagnostics` | `diagnostic_msgs/msg/DiagnosticArray` | Connection health and telemetry freshness |

Measurement topics use best-effort sensor QoS. Match that QoS when subscribing;
`status` is reliable and transient-local. Measurements are published only when a
new SDK publication arrives, and carry **host receipt timestamps**. The SDK does
not supply acquisition timestamps. A stopped stream is not republished with fresh
timestamps. A bounded 256-sample receive queue counts overwritten samples.

The accelerometer conversion multiplies SDK g values by 9.80665 and preserves its
axes. Supply a measured mounting transform before using it in another frame. Battery
current is positive when charging, negative when discharging; capacities are Ah and
percentage is 0..1. Invalid battery information remains visible on `telemetry` and
does not produce a misleading `BatteryState`.

## Try a small movement

The following commands run inside a sourced ROS environment. Servo ID 8 is the
eyebrow servo. Angles in action requests use the SDK's degrees; published joint
positions use ROS radians.

```bash
ros2 action send_goal /marty/motion marty_interfaces/action/Motion \
  '{command: 4, joint_id: 8, position_degrees: 5, move_time_ms: 800}' --feedback

ros2 service call /marty/stop std_srvs/srv/Trigger '{}'
```

Walking and turning use firmware steps:

```bash
ros2 action send_goal /marty/motion marty_interfaces/action/Motion \
  '{command: 0, num_steps: 1, side: auto, step_length_mm: 20, turn_degrees: 0, move_time_ms: 1500}' \
  --feedback
```

Command constants are WALK=0, DANCE=1, KICK=2, STAND=3, MOVE_JOINT=4. Walk requests
accept 1..10 steps, step length -50..50 mm, turn -100..100 degrees, and side
`auto`/`left`/`right`. Explicit starting feet require exactly one step. Dance/kick
require `left` or `right`. Joint commands accept IDs 0..8 and -90..90 degrees. All
commands require 100..10000 ms; for walking, duration is per step. Set step length
to zero for a turning step.

A new goal requires fresh, idle, unpaused robot status and an empty firmware queue.
Busy or invalid goals are rejected. Firmware acknowledgement alone does not finish
an action: the driver waits for fresh post-command idle status across at least
150 ms, after observing movement or waiting the expected duration. Success confirms
the firmware queue is idle; it does not certify every servo reached its target.

Cancellation sends a priority stop and reports CANCELED only after fresh idle status.
The stop service interrupts the active goal, which reports ABORTED. Lost/failed
movement acknowledgements also cause a stop because delivery may be ambiguous.
Stale robot status, timeout or a connection loss aborts the goal. A failed stop or
unconfirmed idle state blocks further goals until reconnect. Commands are never
replayed after reconnect. A broken transport can prevent delivery of the stop.

One worker serializes commands with `blocking=False`. It never waits for physical
movement through MartyPy's blocking helper, leaving ROS telemetry and cancellation
responsive. A synchronous SDK command acknowledgement may still delay a priority
stop until that request returns (normally a 1.5-second SDK timeout). Avoid other
clients commanding the same robot concurrently.

## Configuration and the existing model

Launch reads the packaged parameter YAML, then the selected entry in
`config/robots.yaml`, then explicit launch arguments. Run
`ros2 launch marty_bringup bringup.launch.py --show-args` for the argument list.
Startup parameters are read-only; restart the driver after editing configuration.
Connection services reuse the configured endpoint. Startup is disconnected unless
`auto_connect` is set to true.

Copy `src/marty_bringup/config/marty.yaml` to customize subscription rate, timeouts,
sensor frames or `joint_map`. The default joint names describe firmware servos:
`left_hip`, `left_twist`, `left_knee`, `right_hip`, `right_twist`, `right_knee`,
`left_arm`, `right_arm`, `eyes`. They are deliberately not an unverified URDF mapping.

After physically checking the model's name, sign and zero angle for a servo, a
mapping can be configured using its ID:

```yaml
joint_map: '{"8":{"name":"eye_left_joint","sign":1,"offset_rad":0.0}}'
```

The conversion is `sign × radians(SDK angle) + offset_rad`; this mapping affects
telemetry only, not firmware action coordinates. To use `marty2_description` later,
calibrate all independent joints, remap its `robot_state_publisher` joint-state input
to `/marty/joint_states`, and avoid running its mock joint-state broadcaster on the
same input. This milestone does not declare that model mapping validated.
