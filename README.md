# Marty V2 ROS 2 driver

A standalone Python driver using one MartyPy connection to a physical Marty V2.
ROS Jazzy, Ubuntu 24.04 and Python 3.12 are the initial target. The driver is
independent of Axiom; a future combined demonstration can use its ROS interfaces.

The firmware generates walks and other movements. This package provides a bounded
movement action, stop/connect/disconnect services, fresh telemetry and diagnostics.
It does not implement a `ros2_control` hardware system, arbitrary joint trajectories,
velocity control or odometry.

## Quick start on this Mac

Docker Desktop supplies Linux ROS. A loopback-only byte relay forwards the Mac USB
port to a Linux pseudo-terminal; the ROS driver still uses MartyPy's USB protocol.
Only one process should own the serial port.

```bash
cd /Users/ntheodoropoulos/Robotical/marty-ros2
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
./scripts/run_usb.sh /dev/cu.usbserial-210
```

The script builds the ROS image/workspace and runs the driver in `/marty`. It sends
no movement on startup. In another terminal, enter its ROS environment:

```bash
docker exec -it marty-ros2-usb bash
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
ros2 topic echo /marty/status
```

Ctrl-C in the first terminal stops/disconnects the driver and removes the relay.
Use the actual Mac serial port, which can change after reconnection. The relay's
physical baud is fixed for its lifetime: its default is 115200, validated with the
connected RIC 1.3.21. Pass a second argument for firmware that needs another baud.
MartyPy's baud changes on the virtual terminal cannot change the Mac relay's baud.

## Native Linux installation

Install ROS Jazzy and its normal development tools, then from this repository:

```bash
sudo apt-get install python3-venv python3-pip
source /opt/ros/jazzy/setup.bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt colcon-common-extensions
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
ros2 launch marty_bringup bringup.launch.py locator:=/dev/ttyUSB0
```

For Wi-Fi, use Marty's IP address rather than a URL:

```bash
ros2 launch marty_bringup bringup.launch.py method:=wifi locator:=192.168.1.50
```

MartyPy is a separately installed Python dependency, pinned to 3.7.2. It is not a
rosdep package. Python 3.12 is required by this tested setup; MartyPy's pydub import
depends on `audioop`, removed in Python 3.13. Use the virtual environment's Python
for `colcon` so the generated executable can import the SDK; installing
`colcon-common-extensions` inside the active virtual environment supplies that entry point.

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

Launch accepts `namespace`, `method`, `locator`, `serial_baud`, `wifi_port`,
`auto_connect` and `params_file`. Startup parameters are read-only; connection
services reuse the configured endpoint. Direct node execution defaults to
disconnected, while launch defaults to connecting.

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

## Validation

Run a clean Linux ROS build and the automated suite without hardware:

```bash
./scripts/validate_ros.sh
```

The suite exercises the real SDK against a socket RIC peer, actual ROS DDS fan-out,
services and actions, plus worker-level failure cases. Results are retained in
`.validation/ros.log` and `.validation/pytest.xml`.

With an available USB-connected Marty, this hardware check performs only small
eyebrow movements, tests action completion/cancellation/stop, reconnects and restores
the initial eyebrow position:

```bash
./scripts/validate_usb.sh /dev/cu.usbserial-210
```

Results are saved in `.validation/hardware.log` and, on success,
`.validation/hardware.json`. See `docs/validation.md` for the actual validation
record and remaining physical checks.
