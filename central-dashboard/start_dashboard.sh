#!/bin/bash
# VoltWise Central Dashboard Launcher

cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    ./venv/bin/pip install flask requests
fi

echo "Starting Dashboard..."
# Open browser after a slight delay
# Browser launch handled by app.py

./venv/bin/python3 app.py
