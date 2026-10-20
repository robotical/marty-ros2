#!/usr/bin/env bash
set -euo pipefail
exec sudo docker exec marty-driver bash /marty-entrypoint.sh ros2 "$@"
