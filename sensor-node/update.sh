#!/bin/bash

# VoltWise Update Script
# Updates the repository and restarts the service.

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SERVICE_NAME="voltwise.service"
NET_SERVICE_NAME="voltwise-network.service"

echo -e "${YELLOW}Starting VoltWise Update...${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Please run as root (sudo ./update.sh)${NC}"
  exit 1
fi

# 1. Stop the services
echo -e "${YELLOW}Stopping services...${NC}"
systemctl stop $SERVICE_NAME || echo -e "${RED}Warning: Could not stop voltwise (maybe not running?)${NC}"
systemctl stop $NET_SERVICE_NAME || true

# 2. Git Pull
echo -e "${YELLOW}Pulling latest changes from GitHub...${NC}"
# stash local changes just in case user edited config without committing (though config is ignored usually)
# actually, let's just pull. If there are conflicts, git will complain.
git pull || { echo -e "${RED}Git pull failed! Please resolve conflicts manually.${NC}"; exit 1; }

# 3. Update Dependencies
if [ -d "venv" ]; then
    echo -e "${YELLOW}Updating Python dependencies...${NC}"
    ./venv/bin/pip install -r requirements.txt
else
    echo -e "${RED}Virtual environment not found! Run install.sh first.${NC}"
fi

# 4. Restart services
echo -e "${YELLOW}Restarting services...${NC}"
systemctl daemon-reload # In case service file changed
systemctl start $SERVICE_NAME
systemctl start $NET_SERVICE_NAME || true

# 5. Check Status
echo -e "${YELLOW}Checking service status...${NC}"
sleep 2
systemctl is-active --quiet $SERVICE_NAME
if [ $? -eq 0 ]; then
    echo -e "${GREEN}Update Successful! Service is running.${NC}"
else
    echo -e "${RED}Service failed to start. Check logs with 'journalctl -u $SERVICE_NAME -f'${NC}"
fi
