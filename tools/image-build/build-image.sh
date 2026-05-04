#!/bin/bash
# Build a flash-ready Raspberry Pi OS image with VoltWise Node (first-boot install).
# Usage (from repository root):
#   ./tools/image-build/build-image.sh
#
# Requirements: Docker with privileged loop mounts (works on macOS with Docker Desktop).
# Output: ./dist/voltwise-node-bookworm-arm64-lite.img and .img.xz
#
# Flash the .img (or .img.xz after unxz) with Raspberry Pi Imager.
# First boot needs Ethernet or Wi‑Fi (configure in Imager) so apt can run.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

mkdir -p "$ROOT/dist"

CACHE_VOL="${VOLTWISE_IMAGE_CACHE:-$HOME/.cache/voltwise-image-cache}"
mkdir -p "$CACHE_VOL"

echo "Building Docker image voltwise-sd-builder …"
docker build -t voltwise-sd-builder -f tools/image-build/Dockerfile tools/image-build

echo "Building SD image (privileged Docker) …"
echo "Cache volume: $CACHE_VOL"
docker run --rm --privileged \
  -e "COMPRESS=${COMPRESS:-1}" \
  -e "RPI_OS_IMG_URL=${RPI_OS_IMG_URL:-}" \
  -e "VOLTWISE_DEMO_IMAGE=${VOLTWISE_DEMO_IMAGE:-}" \
  -e "VOLTWISE_PI_USER=${VOLTWISE_PI_USER:-}" \
  -e "VOLTWISE_PI_PASSWORD=${VOLTWISE_PI_PASSWORD:-}" \
  -e "VOLTWISE_PI_PASSWORD_HASH=${VOLTWISE_PI_PASSWORD_HASH:-}" \
  -e "VOLTWISE_PI_ENABLE_SSH=${VOLTWISE_PI_ENABLE_SSH:-0}" \
  -v "$ROOT:/src:ro" \
  -v "$ROOT/dist:/out" \
  -v "$CACHE_VOL:/cache" \
  voltwise-sd-builder

echo ""
echo "Output files in $ROOT/dist/"
ls -la "$ROOT/dist/" || true
