#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/load-config.sh"
# The native Raspberry Pi camera stack owns the camera and hardware encoder.
exec rpicam-vid --timeout 0 --nopreview \
    --width "${CAMERA_WIDTH:-640}" --height "${CAMERA_HEIGHT:-480}" \
    --framerate "${CAMERA_FPS:-10}" --bitrate "${CAMERA_BITRATE:-1000000}" \
    --codec libav --libav-format mpegts --intra "${CAMERA_FPS:-10}" \
    --output "tcp://${CAMERA_BIND:-0.0.0.0}:${CAMERA_PORT:-5000}?listen=1"
