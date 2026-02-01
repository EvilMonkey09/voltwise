# Central Dashboard

This directory will contain the Central Dashboard application, designed to aggregate data from multiple VoltWise sensor nodes.

**Status**: Active / Production Ready

## Installation

### Option 1: Download App (Recommended)

You don't need to install Python or use the terminal.

1.  Go to the [GitHub Actions Page](https://github.com/EvilMonkey09/voltwise/actions).
2.  Click the latest workflow run.
3.  Download the **Artifact** for your OS (`VoltWise-Windows` or `VoltWise-macOS`).
4.  Run the app!

### Option 2: Run from Source

If you are a developer:

1.  Install Python 3.
2.  Run `install_deps.sh` (or `pip install -r requirements.txt`).
3.  Run `start_dashboard.sh`.

## Features

- **Auto-Discovery**: Scans local network (Port 25500) for sensors.
- **Central Recording**: Start/Stop recording on all nodes at once.
- **Live View**: Click to expand any node and see its real-time stats.
