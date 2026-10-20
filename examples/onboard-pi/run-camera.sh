#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# A manual, transient service: survive a terminal closing, but do not start at boot.
exec sudo systemd-run --unit=marty-camera --collect \
    --property="User=$(id -un)" --property=Restart=on-failure --property=RestartSec=2 \
    /bin/bash "$script_dir/stream-camera.sh"
