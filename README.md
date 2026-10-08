# Marty V2 ROS 2

Connect a Marty V2 over USB or Wi-Fi and read its accelerometer in ROS 2.
Use Ubuntu 24.04, ROS 2 Jazzy, Python 3.12 and a Bash terminal.

## 1. Set up and build

Install ROS using the [Ubuntu installation instructions](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html),
then install the build tools:

```bash
sudo apt install ros-dev-tools python3-venv python3-pip
sudo rosdep init  # Once per machine; skip if already initialized.
rosdep update
```

Clone the repository into any directory, then run from its root:

```bash
git clone https://github.com/robotical/marty-ros2.git
cd marty-ros2
source /opt/ros/jazzy/setup.bash
/usr/bin/python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements.txt colcon-common-extensions
rosdep install --from-paths src --ignore-src -r -y
python "$(command -v colcon)" build --base-paths src --symlink-install
```

The virtual environment includes the ROS installation's Python packages and
MartyPy. Run `colcon` explicitly through the active Python as shown above: a system
`colcon` executable otherwise builds the driver with system Python, even while the
venv is active. The generated driver executable keeps that build-time interpreter.

## 2. Configure the machine and Marty

Create these local files once; both are ignored by Git:

```bash
cp -n config/machine.env.example config/machine.env
cp -n config/robots.yaml.example config/robots.yaml
```

`config/machine.env` sets the ROS installation, DDS domain, Python environment and
robot file:

```bash
ROS_SETUP_FILE=/opt/ros/jazzy/setup.bash
ROS_DOMAIN_ID=0
MARTY_PYTHON_VENV="$MARTY_ROS_ROOT/.venv"
MARTY_ROS_ROBOTS_FILE="$MARTY_ROS_ROOT/config/robots.yaml"
```

The setup script determines `MARTY_ROS_ROOT` from its own location. The workspace
defaults to that checkout; set `ROS_WORKSPACE` for a separate build workspace.
Relative configuration paths are resolved from the checkout. Use the same
`ROS_DOMAIN_ID` in every ROS terminal.

For **USB**, edit `config/robots.yaml`:

```yaml
martys:
  marty:
    method: usb
    locator: /dev/serial/by-id/REPLACE_WITH_MARTY_DEVICE
    auto_connect: false
    auto_reconnect: false
    subscribe_rate_hz: 10.0
```

Find the USB path with `ls -l /dev/serial/by-id/`. If access is denied, run
`sudo usermod -aG dialout "$USER"`, then log out and back in.

For **Wi-Fi**, replace `method` and `locator` inside the same entry:

```yaml
    method: wifi
    locator: 192.168.1.8
```

Use Marty's actual IP address or hostname, without `http://` or `ws://`.
Marty must already be connected to the Wi-Fi network.

Defaults are in [src/marty_bringup/config/marty.yaml](src/marty_bringup/config/marty.yaml).
Values in `robots.yaml` override those defaults; explicit launch arguments override both.
Additional entries need unique namespaces and connections. Launch each separately
with its entry name, for example `namespace:=marty2`.

## 3. Connect and read acceleration

Run from the repository root. In **Terminal 1**:

```bash
source scripts/setup_env.sh
ros2 launch marty_bringup bringup.launch.py namespace:=marty
```

The script loads `machine.env`, activates the Python environment and sources the
built workspace. Launch selects `marty` from the robot file. Keep this terminal
running; Marty stays disconnected until the next command.

In **Terminal 2**, prepare the environment, connect and display acceleration:

```bash
source scripts/setup_env.sh
ros2 service call /marty/connect std_srvs/srv/Trigger '{}'
ros2 topic echo /marty/imu/data_raw --field linear_acceleration --qos-reliability best_effort
```

The service should return `success: true`. MartyPy starts telemetry on connection;
there is no separate acquisition command. The echo prints x, y and z in m/s²,
including gravity. Move Marty gently to see the readings change.

Ctrl+C stops the echo. Inspect connection state or the ROS graph with:

```bash
ros2 topic echo /marty/status --once --qos-durability transient_local
ros2 node info /marty/marty_driver
ros2 topic list -t
```

## 4. Stop

Disconnect in Terminal 2, then Ctrl+C in Terminal 1 stops the driver:

```bash
ros2 service call /marty/disconnect std_srvs/srv/Trigger '{}'
```

Connection starts no movement. Movement commands, topic types, configuration and
model integration are described in [ROS interfaces](docs/interfaces.md).
The accelerometer provides acceleration only; gyro and orientation are unavailable.
Standalone RViz robot-model integration is not included yet.

The [Marty ROS 2 userguide](https://userguides.robotical.io/martyv2/ros2/start)
covers setup, telemetry and movement commands.
See [validation](docs/validation.md) for automated and physical checks.
