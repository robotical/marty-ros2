# Onboard Pi and ROS workstation

The Pi runs the Marty driver in a ROS 2 Jazzy container and captures camera video
with the native Raspberry Pi OS camera stack. The workstation receives Marty
telemetry through ROS 2, decodes H.264 video and publishes `/marty/camera/image_raw`.
RViz runs on the workstation. Closing RViz leaves both drivers running.

## Pi

Use 64-bit Raspberry Pi OS, the Robotical expansion cable and a supported Pi
camera. Configure the UART using the [Robotical Pi guide](https://userguides.robotical.io/martyv2/userguides/raspberry_pi/start).
For a Pi 3, the configuration provides `/dev/ttyAMA0`, disables the serial console
and frees the UART from Bluetooth. Check the camera with `rpicam-hello --list-cameras`.

From the repository root:

```bash
sudo apt update
sudo apt install docker.io
sudo docker build -f examples/onboard-pi/Dockerfile -t marty-driver:jazzy .
```

The image includes only the driver, interfaces and bringup packages. Its build
uses one compiler job to fit the Pi 3's memory.

Set `config/robots.yaml`:

```yaml
martys:
  marty:
    method: exp
    locator: /dev/ttyAMA0
    serial_baud: 921600
    auto_connect: false
    auto_reconnect: false
    subscribe_rate_hz: 10.0
```

Set `config/machine.env` on the Pi:

```bash
ROS_DOMAIN_ID=0
MARTY_SERIAL_PORT=/dev/ttyAMA0
MARTY_ROS_ROBOTS_FILE="$MARTY_ROS_ROOT/config/robots.yaml"
```

Start the driver, connect explicitly, and start the camera stream:

```bash
bash examples/onboard-pi/run-driver.sh
bash examples/onboard-pi/ros2.sh service call /marty/connect std_srvs/srv/Trigger '{}'
bash examples/onboard-pi/run-camera.sh
sudo docker logs -f marty-driver
```

The container uses host networking and exposes only the UART device. The native
camera stream uses TCP port 5000, H.264 at 640×480 and 10 fps. It accepts one video
receiver; ROS consumers subscribe to the workstation's image topic.
Optional camera settings in `machine.env` are `CAMERA_WIDTH`, `CAMERA_HEIGHT`,
`CAMERA_FPS`, `CAMERA_BITRATE`, `CAMERA_BIND` and `CAMERA_PORT`.

Both processes are started manually. The camera runs as a transient systemd
service so it survives the terminal closing, and restarts when its client
disconnects. Neither process is configured to start after reboot.

## Workstation

Use Linux with ROS 2 Jazzy and the same ROS domain as the Pi. From a checkout of
this repository:

```bash
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths src/marty_interfaces src/marty_camera --ignore-src -r -y
colcon build --base-paths src --packages-select marty_interfaces marty_camera --symlink-install
```

Set `config/machine.env`, replacing `PI_ADDRESS` with the Pi's address:

```bash
ROS_SETUP_FILE=/opt/ros/jazzy/setup.bash
ROS_DOMAIN_ID=0
RMW_IMPLEMENTATION=rmw_fastrtps_cpp
MARTY_CAMERA_SOURCE=tcp://PI_ADDRESS:5000
```

Start the camera receiver in one terminal:

```bash
bash examples/onboard-pi/receive-camera.sh
```

In another terminal, open RViz:

```bash
bash examples/onboard-pi/view-camera.sh
```

Inspect the Pi's ROS node and telemetry from another prepared terminal:

```bash
source scripts/setup_env.sh
ros2 node list
ros2 topic echo /marty/imu/data_raw --field linear_acceleration --qos-reliability best_effort
ros2 topic echo /marty/status --once --qos-durability transient_local
```

The camera receiver reconnects after stream loss and publishes each decoded image
once. Images use reliable QoS with depth 1 to avoid dropping large images locally.
Timestamps record receipt on the workstation, not exposure on the Pi. This is an
RViz **Image** display: calibration and a TF tree are not required. The RViz global
TF warning does not indicate an image error. No calibration or camera mounting
transform is supplied by this example.

## Stop

Ctrl+C stops the receiver or RViz in its terminal. On the Pi:

```bash
bash examples/onboard-pi/ros2.sh service call /marty/disconnect std_srvs/srv/Trigger '{}'
sudo docker stop marty-driver
sudo systemctl stop marty-camera
```
