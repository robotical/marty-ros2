#!/usr/bin/env bash
# Small eyebrow movements only; the robot is not asked to walk.
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
serial_port=${1:?Usage: validate_usb.sh /dev/cu.usbserial-210 [baud]}
baud=${2:-115200}
image=${MARTY_ROS_IMAGE:-marty-ros2:jazzy}
python=${MARTY_HOST_PYTHON:-$repo_root/.venv/bin/python}
mkdir -p "$repo_root/.validation"
"$python" "$repo_root/scripts/usb_relay.py" "$serial_port" --baud "$baud" \
  > "$repo_root/.validation/usb-relay.log" 2>&1 &
relay_pid=$!
trap 'kill "$relay_pid" 2>/dev/null || true; wait "$relay_pid" 2>/dev/null || true' EXIT
for attempt in {1..30}; do
  if rg -q 'USB relay ready' "$repo_root/.validation/usb-relay.log"; then break; fi
  if ! kill -0 "$relay_pid" 2>/dev/null; then cat "$repo_root/.validation/usb-relay.log"; exit 1; fi
  sleep 0.1
done
docker run --rm -e MARTY_SERIAL_BAUD="$baud" \
  -v "$repo_root:/work:ro" -v "$repo_root/.validation:/results" \
  "$image" bash -lc '
    set -eo pipefail
    source /opt/ros/jazzy/setup.bash
    colcon build --base-paths /work/src
    source /ws/install/setup.bash
    python3 /work/scripts/check_usb.py
  ' 2>&1 | tee "$repo_root/.validation/hardware.log"
