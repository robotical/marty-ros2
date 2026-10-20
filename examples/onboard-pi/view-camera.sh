#!/usr/bin/env bash
set -e
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
source "$repo/scripts/setup_env.sh"
exec rviz2 -d "$(ros2 pkg prefix --share marty_camera)/config/camera.rviz"
