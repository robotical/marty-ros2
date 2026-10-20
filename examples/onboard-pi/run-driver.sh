#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/load-config.sh"
repo=$MARTY_ROS_ROOT
robots_file=${MARTY_ROS_ROBOTS_FILE:-$repo/config/robots.yaml}
serial_port=${MARTY_SERIAL_PORT:-/dev/ttyAMA0}
[[ -r "$robots_file" ]] || { echo "Robot configuration missing: $robots_file" >&2; exit 1; }
[[ -c "$serial_port" ]] || { echo "UART missing: $serial_port" >&2; exit 1; }
exec sudo docker run --rm -d --init --name marty-driver \
    --network host --ipc host --device "$serial_port:$serial_port" \
    -e ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}" -e RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
    -v "$robots_file:/config/robots.yaml:ro" \
    marty-driver:jazzy
