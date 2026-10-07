#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
serial_port=${1:?Usage: run_usb.sh /dev/cu.usbserial-210 [baud]}
baud=${2:-115200}
image=${MARTY_ROS_IMAGE:-marty-ros2:jazzy}
python=${MARTY_HOST_PYTHON:-$repo_root/.venv/bin/python}
mkdir -p "$repo_root/.runtime"
docker build -t "$image" -f "$repo_root/scripts/Dockerfile.ros" "$repo_root/scripts"
"$python" "$repo_root/scripts/usb_relay.py" "$serial_port" --baud "$baud" \
  > "$repo_root/.runtime/usb-relay.log" 2>&1 &
relay_pid=$!
trap 'kill "$relay_pid" 2>/dev/null || true; wait "$relay_pid" 2>/dev/null || true' EXIT
for attempt in {1..30}; do
  if rg -q 'USB relay ready' "$repo_root/.runtime/usb-relay.log"; then break; fi
  if ! kill -0 "$relay_pid" 2>/dev/null; then cat "$repo_root/.runtime/usb-relay.log"; exit 1; fi
  sleep 0.1
done
docker run --rm -it --name marty-ros2-usb -e MARTY_SERIAL_BAUD="$baud" \
  -v "$repo_root:/work:ro" "$image" bash -lc '
    set -eo pipefail
    source /opt/ros/jazzy/setup.bash
    colcon build --base-paths /work/src
    source /ws/install/setup.bash
    exec python3 /work/scripts/run_driver.py
  '
