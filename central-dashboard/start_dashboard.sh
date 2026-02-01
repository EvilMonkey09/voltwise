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
(sleep 2 && open http://127.0.0.1:5000) &

./venv/bin/python3 app.py
