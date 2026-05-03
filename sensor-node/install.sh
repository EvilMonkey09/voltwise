#!/bin/bash

# VoltWise Node — installation script (Raspberry Pi OS).

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Effective user for systemd (avoid root when using sudo ./install.sh)
# OEM SD image first-boot may run as root with VOLTWISE_INSTALL_AS=username (UID 1000).
if [[ "$(id -u)" -eq 0 ]] && [[ -n "${VOLTWISE_INSTALL_AS:-}" ]]; then
  INSTALL_USER="$VOLTWISE_INSTALL_AS"
  if ! id "$INSTALL_USER" &>/dev/null; then
    echo -e "${RED}User ${INSTALL_USER} does not exist.${NC}"
    exit 1
  fi
  INSTALL_GROUP="$(id -gn "$INSTALL_USER")"
elif [[ -n "${SUDO_USER}" ]]; then
  INSTALL_USER="$SUDO_USER"
elif [[ "$(id -u)" -eq 0 ]]; then
  echo -e "${RED}Do not run as root without sudo (use: sudo -u pi ./install.sh or a normal user with sudo).${NC}"
  echo -e "${RED}OEM image: set VOLTWISE_INSTALL_AS=<login user>.${NC}"
  exit 1
else
  INSTALL_USER="$USER"
fi

INSTALL_GROUP="$(id -gn "$INSTALL_USER")"

echo -e "${GREEN}Starting VoltWise Node installation...${NC}"
echo -e "Installing as user: ${YELLOW}${INSTALL_USER}${NC}"

NONINTERACTIVE="${NONINTERACTIVE:-0}"

echo -e "${YELLOW}Installing system dependencies...${NC}"
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip libopenblas-dev network-manager

echo -e "${YELLOW}Adding ${INSTALL_USER} to dialout and netdev...${NC}"
sudo usermod -a -G dialout "$INSTALL_USER"
sudo usermod -a -G netdev "$INSTALL_USER" 2>/dev/null || true

if [[ ! -d "venv" ]]; then
    echo -e "${YELLOW}Creating Python virtual environment...${NC}"
    sudo -u "$INSTALL_USER" python3 -m venv venv
fi

echo -e "${YELLOW}Installing Python dependencies...${NC}"
sudo -u "$INSTALL_USER" "$SCRIPT_DIR/venv/bin/pip" install --upgrade pip
sudo -u "$INSTALL_USER" "$SCRIPT_DIR/venv/bin/pip" install -r requirements.txt

PYTHON_BIN="$SCRIPT_DIR/venv/bin/python3"

if [[ "$NONINTERACTIVE" == "1" ]]; then
  SERIAL_PORT="${SERIAL_PORT:-$("$PYTHON_BIN" "$SCRIPT_DIR/scripts/detect_serial.py")}"
  SENSOR_ADDRESSES="${SENSOR_ADDRESSES:-1,2,3}"
  NODE_NAME="${NODE_NAME:-}"
  echo -e "${GREEN}NONINTERACTIVE: SERIAL_PORT=${SERIAL_PORT} SENSOR_ADDRESSES=${SENSOR_ADDRESSES}${NC}"
else
  echo "Available serial ports:"
  ls /dev/ttyUSB* /dev/ttyACM* /dev/ttyAMA* 2>/dev/null || echo "(none listed)"
  DEFAULT_PORT="$("$PYTHON_BIN" "$SCRIPT_DIR/scripts/detect_serial.py")"
  read -r -p "Enter serial port [${DEFAULT_PORT}]: " SERIAL_PORT
  SERIAL_PORT="${SERIAL_PORT:-$DEFAULT_PORT}"
  read -r -p "Sensor Modbus addresses (comma-separated) [1,2,3]: " ADDR_INPUT
  SENSOR_ADDRESSES="${ADDR_INPUT:-1,2,3}"
  read -r -p "Node display name (optional, shown in dashboard & Central): " NODE_NAME
fi

echo -e "${YELLOW}Writing node_settings.json...${NC}"
sudo -u "$INSTALL_USER" env INSTALL_NODE_NAME="${NODE_NAME:-}" "$PYTHON_BIN" -c "
import json, os, pathlib
p = pathlib.Path('node_settings.json')
name = os.environ.get('INSTALL_NODE_NAME', '').strip()
cfg = {'timezone': 'Europe/Berlin', 'node_name': name}
if p.exists():
    try:
        old = json.loads(p.read_text(encoding='utf-8'))
        merged = {**old, **cfg}
        if not name:
            merged['node_name'] = old.get('node_name', '')
        p.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    except Exception:
        p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
else:
    p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
"

echo -e "${YELLOW}Updating config.py...${NC}"
cat <<EOF > update_config_tmptool.py
import re

config_path = 'config.py'
new_port = '${SERIAL_PORT}'
new_addresses = [${SENSOR_ADDRESSES}]

with open(config_path, 'r') as f:
    content = f.read()

content = re.sub(r"SERIAL_PORT\s*=\s*['\"].*['\"]", f"SERIAL_PORT = '{new_port}'", content)
content = re.sub(r"SENSOR_ADDRESSES\s*=\s*\[.*\]", f"SENSOR_ADDRESSES = {new_addresses}", content)

with open(config_path, 'w') as f:
    f.write(content)
EOF
sudo -u "$INSTALL_USER" "$PYTHON_BIN" update_config_tmptool.py
rm -f update_config_tmptool.py

if [[ "$NONINTERACTIVE" != "1" ]] && [[ -f "configure_sensors.py" ]]; then
    echo -e "${YELLOW}Run Advanced Sensor Configuration Wizard now?${NC}"
    read -r -p "Run wizard? (y/N): " RUN_WIZARD
    if [[ "$RUN_WIZARD" =~ ^[Yy]$ ]]; then
        chmod +x configure_sensors.py
        sudo -u "$INSTALL_USER" ./venv/bin/python3 configure_sensors.py
    fi
fi

SERVICE_NAME="voltwise.service"
NET_SERVICE_NAME="voltwise-network.service"

echo -e "${YELLOW}Creating systemd unit ${SERVICE_NAME}...${NC}"

case "${VOLTWISE_SIMULATION:-}" in
  1|true|TRUE|yes|YES) VOLTWISE_SIM_EXPORT='Environment=VOLTWISE_SIMULATION=1' ;;
  *) VOLTWISE_SIM_EXPORT="" ;;
esac

cat <<EOF > "$SERVICE_NAME"
[Unit]
Description=VoltWise Node
After=network.target

[Service]
User=${INSTALL_USER}
Group=${INSTALL_GROUP}
WorkingDirectory=${SCRIPT_DIR}
Environment="PATH=${SCRIPT_DIR}/venv/bin"
${VOLTWISE_SIM_EXPORT}
ExecStart=${SCRIPT_DIR}/venv/bin/python3 app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo -e "${YELLOW}Creating systemd unit ${NET_SERVICE_NAME}...${NC}"

cat <<EOF > "$NET_SERVICE_NAME"
[Unit]
Description=VoltWise Node setup Wi-Fi (open AP + captive portal when offline)
After=NetworkManager.service network-online.target
Wants=NetworkManager.service

[Service]
Type=simple
User=root
WorkingDirectory=${SCRIPT_DIR}
Environment=PATH=${SCRIPT_DIR}/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin
ExecStart=${SCRIPT_DIR}/venv/bin/python3 -m voltwise_network.daemon
Restart=on-failure
RestartSec=15

[Install]
WantedBy=multi-user.target
EOF

sudo cp "$SERVICE_NAME" "/etc/systemd/system/$SERVICE_NAME"
sudo cp "$NET_SERVICE_NAME" "/etc/systemd/system/$NET_SERVICE_NAME"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl enable "$NET_SERVICE_NAME"

echo -e "${GREEN}Installation complete.${NC}"
echo -e "Start node:     ${YELLOW}sudo systemctl start ${SERVICE_NAME}${NC}"
echo -e "Start setup AP service: ${YELLOW}sudo systemctl start ${NET_SERVICE_NAME}${NC}"
echo -e "Dashboard (when connected): ${YELLOW}http://<node-ip>:25500${NC}"
echo -e "${YELLOW}Log out and back in (or reboot) so group dialout applies.${NC}"
