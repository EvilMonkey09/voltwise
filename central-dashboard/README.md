# Central Dashboard

This directory will contain the Central Dashboard application, designed to aggregate data from multiple VoltWise sensor nodes.

**Status**: Active / Production Ready

## Installation

### Option 1: Download App (Recommended)

You don't need to install Python or use the terminal.

1.  **[Download the Latest Release Here](https://github.com/EvilMonkey09/voltwise/releases/latest)**
2.  Choose `VoltWise-Windows.exe` or `VoltWise-macOS`.
3.  Run the app!

### Option 2: Run from Source

If you are a developer:

1.  Install Python 3.
2.  Run `install_deps.sh` (or `pip install -r requirements.txt`).
3.  Run `start_dashboard.sh`.

## Features

- **Auto-Discovery**: Scans local network (Port 25500) for sensors.
- **Central Recording**: Start/Stop recording on all nodes at once.
- **Live View**: Click to expand any node and see its real-time stats.
