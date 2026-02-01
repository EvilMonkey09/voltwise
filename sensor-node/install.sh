#!/bin/bash

# VoltWise Installation Script
# This script sets up the environment, dependencies, and systemd service.

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting VoltWise Installation...${NC}"

# 1. System Dependencies
echo -e "${YELLOW}Installing system dependencies...${NC}"
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip libatlas-base-dev

# 2. Add user to dialout group (needed for Serial/Modbus)
echo -e "${YELLOW}Adding user $USER to 'dialout' group...${NC}"
sudo usermod -a -G dialout $USER

# 3. Virtual Environment
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating Python virtual environment...${NC}"
    python3 -m venv venv
else
    echo -e "${GREEN}Virtual environment already exists.${NC}"
fi

# 4. Install Python Dependencies
echo -e "${YELLOW}Installing Python dependencies...${NC}"
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 5. Interactive Configuration
echo -e "${YELLOW}Configuring VoltWise...${NC}"

# Detect USB/Serial ports
echo "Available Serial Ports:"
ls /dev/ttyUSB* /dev/ttyACM* /dev/ttyAMA* 2>/dev/null || echo "No common serial ports found."

read -p "Enter Serial Port (default: /dev/ttyAMA0): " SERIAL_PORT
SERIAL_PORT=${SERIAL_PORT:-/dev/ttyAMA0}

read -p "Enter Sensor Addresses (comma separated, e.g., 1,2,3) (default: 1,2,3): " SENSOR_ADDRESSES
SENSOR_ADDRESSES=${SENSOR_ADDRESSES:-1,2,3}

# Update config.py using a temporary python script
echo -e "${YELLOW}Updating config.py...${NC}"
cat <<EOF > update_config_tmptool.py
import re

config_path = 'config.py'
new_port = '$SERIAL_PORT'
new_addresses = [$SENSOR_ADDRESSES]

with open(config_path, 'r') as f:
    content = f.read()

# Replace SERIAL_PORT
content = re.sub(r"SERIAL_PORT\s*=\s*['\"].*['\"]", f"SERIAL_PORT = '{new_port}'", content)

# Replace SENSOR_ADDRESSES
content = re.sub(r"SENSOR_ADDRESSES\s*=\s*\[.*\]", f"SENSOR_ADDRESSES = {new_addresses}", content)

with open(config_path, 'w') as f:
    f.write(content)
EOF

./venv/bin/python3 update_config_tmptool.py
rm update_config_tmptool.py
echo -e "${GREEN}Configuration updated.${NC}"
# 5.1 Advanced Sensor Configuration
if [[ -f "configure_sensors.py" ]]; then
    echo -e "${YELLOW}Do you want to run the Advanced Sensor Configuration Wizard?${NC}"
    echo -e "This tool helps you scan for sensors and set their addresses (1, 2, 3...) interactively."
    read -p "Run wizard now? (y/N): " RUN_WIZARD
    if [[ "$RUN_WIZARD" =~ ^[Yy]$ ]]; then
        # Use simple python execution, assuming system python or venv python
        # We need root, which we have (sudo ./install.sh)
        chmod +x configure_sensors.py
        ./venv/bin/python3 configure_sensors.py
        
        # Reload config after wizard might have changed it
        # Actually, configure_sensors.py edits config.py directly.
        echo -e "${GREEN}Continuing installation...${NC}"
    fi
fi

# 6. Service Setup
SERVICE_NAME="voltwise.service"
WORKING_DIR=$(pwd)
USER_NAME=$USER
GROUP_NAME=$(id -gn)

echo -e "${YELLOW}Creating systemd service...${NC}"

cat <<EOF > $SERVICE_NAME
[Unit]
Description=VoltWise Service
After=network.target

[Service]
User=$USER_NAME
Group=$GROUP_NAME
WorkingDirectory=$WORKING_DIR
Environment="PATH=$WORKING_DIR/venv/bin"
ExecStart=$WORKING_DIR/venv/bin/python3 app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo -e "${YELLOW}Installing service to /etc/systemd/system/...${NC}"
sudo cp $SERVICE_NAME /etc/systemd/system/$SERVICE_NAME
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME

echo -e "${GREEN}Installation Complete!${NC}"
echo -e "You can start the service manually with: ${YELLOW}sudo systemctl start $SERVICE_NAME${NC}"
echo -e "Check status with: ${YELLOW}sudo systemctl status $SERVICE_NAME${NC}"
echo -e "Please reboot or log out/in to ensure group permissions apply."
