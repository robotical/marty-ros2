# Marty simulation in RViz

This is a separate ROS setup with no physical robot connection. It reuses the
URDF, meshes and generated MuJoCo model from `marty-urdf-simulator`. RViz displays
the resulting joint positions and floating base pose; MuJoCo runs the simulation.
The browser simulator is not needed at runtime.

## Build

After the machine environment and ROS workspace from the main README are set up,
run from the repository root:

```bash
source scripts/setup_env.sh
python -m pip install -r requirements-simulation.txt
rosdep install --from-paths src --ignore-src -r -y
python "$(command -v colcon)" build --base-paths src --symlink-install
source scripts/setup_env.sh
```

The simulation adds `marty2_description` and `marty_simulation`. An existing
workspace must not also contain a second package named `marty2_description`.

## Open RViz and joint controls

```bash
ros2 launch marty_simulation simulation.launch.py
```

RViz opens with Marty and a ground grid. Move the joint-control sliders to change
the simulated pose. The eleven mimic joints are derived from the nine independent
joints, including the opposite eyebrow and the arm gears.

To control the simulation from the console, disable the sliders so they do not
keep replacing console commands:

```bash
ros2 launch marty_simulation simulation.launch.py gui:=false
```

In another terminal, from the repository root:

```bash
source scripts/setup_env.sh
ros2 topic pub --once /marty_sim/joint_commands sensor_msgs/msg/JointState \
  '{name: [eye_left_joint, arm_servo_gear_left_joint, arm_servo_gear_right_joint], position: [-0.5, 0.7, 0.7]}'
ros2 topic echo /marty_sim/joint_states --once
```

Positions are radians. Partial commands retain the other actuator targets.
Unknown joints, duplicate names, non-finite values and targets outside the
MuJoCo actuator limits are rejected. The GUI also sends mimic joints, which are
ignored as command inputs because the simulation computes them.

```text
joint controls / console -> /marty_sim/joint_commands -> MuJoCo
MuJoCo -> /marty_sim/joint_states -> robot_state_publisher -> /tf -> RViz
MuJoCo -> world-to-marty_sim/base_link transform -> /tf -> RViz
```

The launch starts no Marty driver, hardware connection or Axiom node. Ctrl+C in
the launch terminal closes the simulation, sliders and RViz. For a headless run,
add `gui:=false rviz:=false`.

## Model limits

The default `mode:=stabilized` uses the browser simulator's height/tilt assistance
forces. It also adds estimated passive joint damping and uses a 0.5 ms integration
step to prevent numerical instability in the small eye joint. Feedback is computed
from the MuJoCo state, rather than copying commanded positions. The simulation
advances 20 ms per ROS timer tick and publishes at approximately 50 Hz with host
timestamps; it does not publish a global `/clock`.

`mode:=free` removes the damping and balance assistance. The source model's
contact, actuator and mass calibration remains incomplete; free walking and
physical motion accuracy are not validated. This setup accepts joint targets,
not the physical driver's firmware `Motion` action.

The asset snapshot and SHA-256 hashes are in
`src/marty_simulation/physics/sources.json`. The source URDF, meshes and MJCF are
unchanged. Simulation assistance is confined to `marty_simulation/physics.py`.
