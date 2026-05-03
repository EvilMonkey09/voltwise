#!/bin/bash
# First-boot on Raspberry Pi: extract bundled sensor-node and run install.sh once.
# Intended GPIO UART default: /dev/serial0 (PZEM via jumper wires). Requires network for apt.

set -euo pipefail

MARK=/var/lib/voltwise/firstboot.done
mkdir -p "$(dirname "$MARK")"

log() { echo "[voltwise-firstboot] $*"; }

if [[ -f "$MARK" ]]; then
  exit 0
fi

MAIN_USER=$(getent passwd 1000 | cut -d: -f1 || true)
MAIN_HOME=$(getent passwd 1000 | cut -d: -f6 || true)
if [[ -z "${MAIN_USER:-}" || -z "${MAIN_HOME:-}" ]]; then
  log "ERROR: No login user with UID 1000. Create your user in Raspberry Pi Imager (Advanced options), re-flash, and reboot."
  exit 1
fi

TAR=""
for p in /boot/firmware/voltwise-sensor-node.tar.gz /boot/voltwise-sensor-node.tar.gz; do
  if [[ -f "$p" ]]; then TAR="$p"; break; fi
done

if [[ -z "$TAR" ]]; then
  log "ERROR: voltwise-sensor-node.tar.gz missing on the boot partition — rebuild the SD image."
  exit 1
fi

log "Extracting bundle from $TAR"
mkdir -p "$MAIN_HOME/voltwise"
tar xzf "$TAR" -C "$MAIN_HOME/voltwise"
chown -R "$MAIN_USER:$(id -gn "$MAIN_USER" 2>/dev/null || echo "$MAIN_USER")" "$MAIN_HOME/voltwise"

INSTALL_DIR="$MAIN_HOME/voltwise/sensor-node"
if [[ ! -f "$INSTALL_DIR/install.sh" ]]; then
  log "ERROR: install.sh missing — archive layout must be sensor-node/ at repo root."
  exit 1
fi

chmod +x "$INSTALL_DIR/install.sh"

log "Installing VoltWise Node (GPIO UART → SERIAL_PORT=${VOLTWISE_SERIAL_PORT:-/dev/serial0}) …"

export NONINTERACTIVE=1
export SERIAL_PORT="${VOLTWISE_SERIAL_PORT:-/dev/serial0}"
export SENSOR_ADDRESSES="${VOLTWISE_SENSOR_ADDRESSES:-1,2,3}"
export NODE_NAME="${VOLTWISE_NODE_NAME:-}"
export VOLTWISE_INSTALL_AS="$MAIN_USER"

cd "$INSTALL_DIR"
./install.sh

touch "$MARK"
log "First boot complete."

systemctl disable voltwise-firstboot.service 2>/dev/null || true
rm -f /etc/systemd/system/multi-user.target.wants/voltwise-firstboot.service 2>/dev/null || true

log "You may reboot once if serial/UART changes require it: sudo reboot"

exit 0
