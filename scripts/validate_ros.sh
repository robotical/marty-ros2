#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
image=${MARTY_ROS_IMAGE:-marty-ros2:jazzy}
docker build -t "$image" -f "$repo_root/scripts/Dockerfile.ros" "$repo_root/scripts"
mkdir -p "$repo_root/.validation"
docker run --rm -v "$repo_root:/work:ro" -v "$repo_root/.validation:/results" \
  -w /ws "$image" bash -lc '
    set -eo pipefail
    source /opt/ros/jazzy/setup.bash
    export PYTHONDONTWRITEBYTECODE=1
    colcon build --base-paths /work/src
    source /ws/install/setup.bash
    test_status=0
    colcon test --base-paths /work/src --packages-select marty_driver marty_bringup marty_simulation \
      --event-handlers console_direct+ --return-code-on-test-failure || test_status=$?
    cp /ws/build/marty_driver/pytest.xml /results/
    cp /ws/build/marty_bringup/pytest.xml /results/bringup-pytest.xml
    cp /ws/build/marty_simulation/pytest.xml /results/simulation-pytest.xml
    python3 -m pytest /work/scripts/test -q || test_status=$?
    colcon test-result --verbose || test_status=$?
    test "$test_status" -eq 0
    ros2 launch marty_bringup bringup.launch.py --show-args
  ' 2>&1 | tee "$repo_root/.validation/ros.log"
