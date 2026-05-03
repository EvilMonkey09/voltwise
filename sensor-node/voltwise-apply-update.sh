#!/bin/bash
# Root: apply VoltWise Node update from GitHub release tarball (no .git required).
# Usage: voltwise-apply-update.sh [latest|v1.2.3]

set -euo pipefail

TAG_ARG="${1:-latest}"
REPO="${VOLTWISE_GITHUB_REPO:-EvilMonkey09/voltwise}"
NODE_DIR_FILE="${VOLTWISE_SENSOR_NODE_DIR_FILE:-/etc/voltwise/sensor_node_dir}"
SERVICE_MAIN="${VOLTWISE_SERVICE:-voltwise.service}"
SERVICE_NET="${VOLTWISE_NETWORK_SERVICE:-voltwise-network.service}"

log() { echo "[voltwise-apply-update] $*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root (this script is invoked via sudo)." >&2
  exit 1
fi

if [[ ! -f "$NODE_DIR_FILE" ]]; then
  log "Missing $NODE_DIR_FILE — run install.sh first."
  exit 1
fi

NODE_DIR="$(tr -d '\n\r' < "$NODE_DIR_FILE")"
if [[ ! -d "$NODE_DIR" ]]; then
  log "sensor_node_dir is not a directory: $NODE_DIR"
  exit 1
fi

export VOLTWISE_GITHUB_REPO="$REPO"

resolve_tag() {
  if [[ "$TAG_ARG" == "latest" ]]; then
    python3 - <<'PY'
import json
import os
import urllib.request

repo = os.environ.get("VOLTWISE_GITHUB_REPO", "EvilMonkey09/voltwise")
url = f"https://api.github.com/repos/{repo}/releases/latest"
req = urllib.request.Request(
    url,
    headers={"Accept": "application/vnd.github+json", "User-Agent": "VoltWise-OTA"},
)
with urllib.request.urlopen(req, timeout=25) as r:
    data = json.loads(r.read().decode())
print(data["tag_name"])
PY
  else
    echo "$TAG_ARG"
  fi
}

TAG="$(resolve_tag)"
if [[ "$TAG" != v* ]]; then
  TAG="v${TAG}"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

ARCHIVE_URL="https://github.com/${REPO}/archive/refs/tags/${TAG}.tar.gz"
log "Downloading ${ARCHIVE_URL}"
curl -fsSL "$ARCHIVE_URL" -o "$TMP/src.tar.gz"

FIRST="$(tar tzf "$TMP/src.tar.gz" | head -1)"
TOPDIR="${FIRST%%/*}"
tar xzf "$TMP/src.tar.gz" -C "$TMP"

SRC_SN="$TMP/$TOPDIR/sensor-node"
if [[ ! -d "$SRC_SN" ]]; then
  log "sensor-node/ missing in release archive."
  exit 1
fi

BACKUP="${NODE_DIR}.bak-$(date +%s)"
log "Backup -> $BACKUP"
cp -a "$NODE_DIR" "$BACKUP"

log "Merging into $NODE_DIR"
rsync -a \
  --exclude=venv \
  --exclude=node_settings.json \
  --exclude=energy_data.db \
  --exclude=__pycache__ \
  --exclude='*.pyc' \
  "$SRC_SN/" "$NODE_DIR/"

OWNER="$(stat -c '%U' "$NODE_DIR" 2>/dev/null || stat -f '%Su' "$NODE_DIR")"
GROUP="$(stat -c '%G' "$NODE_DIR" 2>/dev/null || stat -f '%Sg' "$NODE_DIR")"
chown -R "$OWNER:$GROUP" "$NODE_DIR"

if [[ ! -x "$NODE_DIR/venv/bin/pip" ]]; then
  log "venv not found at $NODE_DIR/venv — run install.sh first."
  exit 1
fi

log "pip install -r requirements.txt"
sudo -u "$OWNER" "$NODE_DIR/venv/bin/pip" install -r "$NODE_DIR/requirements.txt"

systemctl daemon-reload || true
systemctl restart "$SERVICE_MAIN"
systemctl restart "$SERVICE_NET" || true
log "Update applied ($TAG). Services restarted."
