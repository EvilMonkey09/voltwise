#!/bin/bash

# VoltWise Update Script
# - Git clone: git pull + pip + restart
# - OEM / no .git: release tarball via /usr/local/sbin/voltwise-apply-update.sh

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SERVICE_NAME="voltwise.service"
NET_SERVICE_NAME="voltwise-network.service"

echo -e "${YELLOW}Starting VoltWise Update...${NC}"

if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Please run as root (sudo ./update.sh)${NC}"
  exit 1
fi

cd "$(dirname "$0")"

if [ -d .git ]; then
  echo -e "${YELLOW}Stopping services...${NC}"
  systemctl stop $SERVICE_NAME || echo -e "${RED}Warning: Could not stop voltwise${NC}"
  systemctl stop $NET_SERVICE_NAME || true

  echo -e "${YELLOW}Pulling latest changes from GitHub...${NC}"
  git pull || { echo -e "${RED}Git pull failed!${NC}"; exit 1; }

  if [ -d "venv" ]; then
    echo -e "${YELLOW}Updating Python dependencies...${NC}"
    ./venv/bin/pip install -r requirements.txt
  else
    echo -e "${RED}Virtual environment not found! Run install.sh first.${NC}"
    exit 1
  fi

  echo -e "${YELLOW}Restarting services...${NC}"
  systemctl daemon-reload || true
  systemctl start $SERVICE_NAME
  systemctl start $NET_SERVICE_NAME || true

  sleep 2
  systemctl is-active --quiet $SERVICE_NAME
  if [ $? -eq 0 ]; then
    echo -e "${GREEN}Update Successful! Service is running.${NC}"
  else
    echo -e "${RED}Service failed to start. Check journalctl -u $SERVICE_NAME -f${NC}"
  fi
elif [ -x /usr/local/sbin/voltwise-apply-update.sh ]; then
  echo -e "${YELLOW}No git repo — applying latest release tarball...${NC}"
  exec /usr/local/sbin/voltwise-apply-update.sh latest
else
  echo -e "${RED}Cannot update: no .git and OTA helper missing.${NC}"
  echo -e "${YELLOW}Run install.sh once, or clone the repo and use git pull.${NC}"
  exit 1
fi
