#!/usr/bin/env bash
set -e
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
source "$repo/scripts/setup_env.sh"
source_uri=${1:-${MARTY_CAMERA_SOURCE:-}}
[[ -n "$source_uri" ]] || { echo 'Set MARTY_CAMERA_SOURCE or pass tcp://PI_ADDRESS:5000' >&2; exit 1; }
export OPENCV_FFMPEG_CAPTURE_OPTIONS='fflags;nobuffer|flags;low_delay|probesize;32768|analyzeduration;1000000'
exec ros2 launch marty_camera view.launch.py source:="$source_uri" rviz:=false
