#!/bin/bash
# Builds a flashable Raspberry Pi OS image with VoltWise Node embedded (Docker or CI — Linux + root).
set -euo pipefail

SRC="${SOURCE_DIR:-/src}"
OUT="${OUTPUT_DIR:-/out}"
CACHE="${CACHE_DIR:-/cache}"
mkdir -p "$OUT" "$CACHE"

IMG_URL="${RPI_OS_IMG_URL:-https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2024-11-19/2024-11-19-raspios-bookworm-arm64-lite.img.xz}"
# Stable path after decompress (upstream filename varies with the release date in IMG_URL)
RAW_IMG="$CACHE/raspios-unpacked.img"

ROOT_MOUNT=/mnt/rpi-img
BOOT_MNT="$ROOT_MOUNT/boot"
ROOT_MNT="$ROOT_MOUNT/root"

echo "==> Source repo: $SRC"
echo "==> Output dir:  $OUT"

if [[ ! -d "$SRC/sensor-node" ]]; then
  echo "ERROR: $SRC/sensor-node not found. Mount the VoltWise repository at $SRC."
  exit 1
fi

echo "==> Creating sensor-node bundle tarball (excluding venv, DB, local settings) …"
tar czf "$CACHE/voltwise-sensor-node.tar.gz" \
  --exclude='venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='energy_data.db' \
  --exclude='node_settings.json' \
  --exclude='.git' \
  -C "$SRC" sensor-node

XZ_PATH="$CACHE/$(basename "$IMG_URL")"
LOOP=""

cleanup() {
  set +e
  [[ -n "$LOOP" ]] && umount -l "$BOOT_MNT" 2>/dev/null
  [[ -n "$LOOP" ]] && umount -l "$ROOT_MNT" 2>/dev/null
  [[ -n "$LOOP" ]] && losetup -d "$LOOP" 2>/dev/null
  LOOP=""
}
trap cleanup EXIT

if [[ ! -f "$RAW_IMG" ]]; then
  if [[ ! -f "$XZ_PATH" ]]; then
    echo "==> Downloading Raspberry Pi OS Lite …"
    echo "    URL: $IMG_URL"
    if command -v curl >/dev/null 2>&1; then
      curl -fSL --retry 3 --connect-timeout 30 -o "$XZ_PATH" "$IMG_URL"
    else
      wget -nv -O "$XZ_PATH" "$IMG_URL"
    fi
  fi
  echo "==> Decompressing image …"
  xz -dkf "$XZ_PATH"
  DECOMP="${XZ_PATH%.xz}"
  if [[ ! -f "$DECOMP" ]]; then
    echo "ERROR: Expected decompressed file: $DECOMP"
    exit 1
  fi
  mv -f "$DECOMP" "$RAW_IMG"
fi

echo "==> Loop-mounting image …"
LOOP=$(losetup -fP --show "$RAW_IMG")
BOOT_PART="${LOOP}p1"
ROOT_PART="${LOOP}p2"
mkdir -p "$BOOT_MNT" "$ROOT_MNT"

mount "$BOOT_PART" "$BOOT_MNT"
mount "$ROOT_PART" "$ROOT_MNT"

echo "==> Copy VoltWise bundle to boot partition (FAT) …"
cp -f "$CACHE/voltwise-sensor-node.tar.gz" "$BOOT_MNT/voltwise-sensor-node.tar.gz"

# Bookworm also exposes firmware under rootfs /boot/firmware — duplicate so first-boot finds it either way.
if [[ -d "$ROOT_MNT/boot/firmware" ]]; then
  cp -f "$CACHE/voltwise-sensor-node.tar.gz" "$ROOT_MNT/boot/firmware/voltwise-sensor-node.tar.gz"
fi

echo "==> UART for GPIO jumper-wire PZEM (/dev/serial0) …"
if [[ -f "$BOOT_MNT/config.txt" ]] && ! grep -q '^enable_uart=1' "$BOOT_MNT/config.txt"; then
  printf '\n# VoltWise Node — UART for PZEM Modbus (GPIO 14/15)\nenable_uart=1\n' >> "$BOOT_MNT/config.txt"
fi

if [[ -f "$BOOT_MNT/cmdline.txt" ]]; then
  sed -i 's/ console=serial0,115200//g; s/console=serial0,115200 //g' "$BOOT_MNT/cmdline.txt" || true
fi

echo "==> Install first-boot scripts …"
install -m 755 "$SRC/tools/image-build/firstboot.sh" "$ROOT_MNT/usr/local/sbin/voltwise-firstboot.sh"
install -m 644 "$SRC/tools/image-build/voltwise-firstboot.service" "$ROOT_MNT/etc/systemd/system/voltwise-firstboot.service"
mkdir -p "$ROOT_MNT/etc/systemd/system/multi-user.target.wants"
ln -sf ../voltwise-firstboot.service "$ROOT_MNT/etc/systemd/system/multi-user.target.wants/voltwise-firstboot.service"
mkdir -p "$ROOT_MNT/var/lib/voltwise"

sync
umount "$BOOT_MNT"
umount "$ROOT_MNT"
losetup -d "$LOOP"
LOOP=""
trap - EXIT

OUT_IMG="$OUT/voltwise-node-bookworm-arm64-lite.img"
cp -f "$RAW_IMG" "$OUT_IMG"
echo "==> Done: $OUT_IMG ($(du -h "$OUT_IMG" | cut -f1))"

if [[ "${COMPRESS:-1}" == "1" ]]; then
  echo "==> Compressing with xz …"
  xz -9 -T0 -f -k "$OUT_IMG"
  echo "==> Released: ${OUT_IMG}.xz"
fi

echo "Flash with Raspberry Pi Imager or: dd if=${OUT_IMG} of=/dev/sdX bs=4M status=progress conv=fsync"
