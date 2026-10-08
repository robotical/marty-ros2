# Validation record

The software target is ROS Jazzy on Ubuntu 24.04, Python 3.12 and MartyPy 3.7.2.
Automated checks were repeated on 8 October 2026 in disposable Linux containers.
Physical USB checks below were completed on 1 October 2026.

## Automated checks

The automated suite passed **38 ROS tests and four setup-script tests**, with
zero errors, failures or skips.
`./scripts/validate_ros.sh` builds all three packages, generates the actual ROS
interfaces, runs driver and bringup tests through `colcon`, checks the setup script
and verifies installed launch arguments. Validation runs locally; there is no
GitHub Actions workflow. Logs and JUnit XML are saved under `.validation/`.

The tests cover:

- Real MartyPy handshake, subscriptions, framed firmware messages and SDK commands
  against a TCP/WebSocket RIC peer, rather than replacing the SDK with a ROS mock.
- Actual DDS telemetry delivery to independent subscribers, unit conversion,
  validity and unavailable sensor fields.
- Action completion after firmware idle telemetry, rejection of busy/invalid
  goals, cancellation, stop-service interruption and all five movement commands.
- Transport loss, abort, reconnection and prevention of command replay.
- Disappearance of telemetry without publication of stale cached measurements.
- Worker boundary cases: stop before dispatch, a delayed acknowledgement, rejected
  acknowledgements, status-only loss, movement timeout and failed stop handling.
- Local robot configuration types, namespaces and duplicate connections.
- Installed launch precedence: parameter YAML, selected robot entry, then CLI.
  Launch stays disconnected until an explicit connect service call, after which
  accelerometer measurements reach a real ROS subscriber.
- Machine setup from outside the checkout, paths containing spaces, relative paths,
  Python environment activation and missing-file errors.

The build was checked with a fresh Python 3.12 virtual environment and MartyPy
available only inside that environment. Bare `colcon build` reproduced the import
failure: system colcon generated a driver executable using `/usr/bin/python3`.
Running `python "$(command -v colcon)" build` regenerated it with the venv's Python.
The installed launch test then passed explicit connection and accelerometer delivery
through ROS, with no global MartyPy installation. No physical robot was connected
or moved during this configuration validation.

The RIC peer intentionally accepts the historical MartyPy WebSocket upgrade without
`Sec-WebSocket-Key`, as the firmware does. A standards-strict WebSocket server cannot
stand in for this firmware interface without adapting that handshake. Its motion
timing is synthetic; it is not a walking-physics simulator.

## Physical Marty V2

The USB device was identified and tested at `/dev/cu.usbserial-210`:

| Property | Observed |
|---|---|
| Controller | RIC, hardware revision 6 |
| Firmware | 1.3.21 |
| USB physical baud | 115200 |
| Initial telemetry | Nine communicating servos; empty, idle movement queue |
| ROS telemetry during smoke test | 99 joint samples, 68 acceleration samples, 12 valid battery samples |

`./scripts/validate_usb.sh /dev/cu.usbserial-210` passed all seven checks:

1. The real SDK USB handshake and joint/accelerometer delivery through ROS DDS.
2. Explicit unavailable orientation and gyro, with no invented joint torque.
3. A small eyebrow action, fresh idle completion and measured target position.
4. Cancellation of an active eyebrow action, including fresh idle confirmation.
5. Stop-service interruption of an active action, with its ROS result aborted.
6. Explicit disconnect/reconnect and resumed fresh telemetry.
7. Restoration of the initial eyebrow position, approximately -8 degrees.

The commands moved only servo 8. The script saves `.validation/hardware.json` only
when all assertions pass, and stops outstanding work during cleanup. The relay was
closed afterwards. An initial relay attempt at 2,000,000 baud failed its handshake;
direct SDK inspection established 115200 as the working physical rate. The repeat
at that rate passed without command-acknowledgement errors.

The normal `run_usb.sh` launcher was also exercised. ROS CLI discovery found the
`/marty/motion` action and all three services. Its status showed a ready connection,
fresh robot telemetry, an idle empty queue, no dropped samples and no last error.

## Remaining physical checks

- Walking, turning, dance, kick and stand: command routing is tested through the
  real SDK and emulator, but these gait movements have not been exercised on the
  physical robot in this milestone.
- Unexpected physical USB removal/reinsertion and Wi-Fi outage: loss handling is
  tested with a socket peer; physical validation covered explicit connection cycles.
- Joint-to-URDF naming, signs and zero offsets: configurable, awaiting calibration.
- Sustained telemetry delivery rates and low-battery/disconnected-servo conditions:
  not physically benchmarked here.

Action success means the firmware reports an idle movement queue. The physical
eyebrow check additionally verifies position, but generic actions do not implement
a per-joint tracking tolerance. A transport outage can prevent delivery of a stop.
