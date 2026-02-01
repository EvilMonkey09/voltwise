# VoltWise

An Open Source Energy Monitoring System using Raspberry Pis and PZEM-004T sensors.

This repository is divided into two parts:

## 1. [Sensor Node](./sensor-node)

The software that runs on the Raspberry Pi.

- Connects to PZEM-004T sensors.
- Provides a localThe web dashboard will be available at `http://<pi-ip>:25500`.

**[>> Go to Sensor Node Documentation](./sensor-node/SETUP_GUIDE.md)**

## 2. [Central Dashboard](./central-dashboard)

(Optional) A central server to monitor multiple sensor nodes.

- runs on PC/Mac/Linux.
- Aggregates data from multiple Pis.

---

## Quick Start (Raspberry Pi)

If you are setting up a sensor:

1.  Clone this repository:
    ```bash
    git clone https://github.com/yourusername/voltwise.git
    ```
2.  Enter the sensor directory:
    ```bash
    cd voltwise/sensor-node
    ```
3.  Run the installer:
    ```bash
    sudo ./install.sh
    ```
