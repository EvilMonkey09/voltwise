# Ultimate VoltWise Setup Guide

Welcome! This guide will walk you through building your own Energy Monitor using a Raspberry Pi and PZEM-004T sensors. This guide assumes you have just unboxed your components.

---

## 1. Hardware Requirements

Before we start, ensure you have:

- **1x Raspberry Pi** (3, 4, or Zero W) with SD Card (8GB+).
- **1x Power Supply** for the Raspberry Pi.
- **1-3x PZEM-004T v3.0 Sensors** (includes the main board and a CT coil).
- **1x USB to RS485/TTL Adapter** OR **Jumper Wires** (if connecting directly to GPIO).
  - _Recommended: USB to TTL/UART Adapter for easier setup._
- **Wires** to connect sensors to the adapter.

---

## 2. Hardware Assembly

### Step A: Wiring the Sensors (High Voltage Warning ⚠️)

> **DANGER:** You will be working with mains voltage (110V/230V). **Turn off your main breaker** before installing CT coils or voltage lines if you are not comfortable working with live electricity. Consult an electrician!

1.  **The CT Coil (Blue current transformer)**:
    - Clip the coil around **ONE** of the main power wires (Live or Neutral, but not both at once!).
    - Connect the two small wires from the coil to the pins marked **CT** on the PZEM board.
2.  **Voltage Measurement**:
    - Connect two wires from the PZEM screw terminals to a standard power outlet or breaker. This powers the measurement side and reads voltage.

### Step B: Connect Sensors to Raspberry Pi (Data)

You need to connect the Low Voltage data side (5V, RX, TX, GND) to your Raspberry Pi.

**Option 1: Using a USB Adapter (Easiest)**

- Connect all PZEM sensors in parallel (daisy-chain):
  - **5V** on all sensors -> **5V** on USB Adapter.
  - **GND** on all sensors -> **GND** on USB Adapter.
  - **RX** on all sensors -> **TX** on USB Adapter.
  - **TX** on all sensors -> **RX** on USB Adapter.
- Plug the USB Adapter into the Raspberry Pi.

**Option 2: Direct GPIO (typisch / OEM-Image)**

- **5V** -> Pin 4 (5V).
- **GND** -> Pin 6 (GND).
- **RX** (Sensor) -> Pin 8 (GPIO 14 TX).
- **TX** (Sensor) -> Pin 10 (GPIO 15 RX).

Das **vorgefertigte SD-Image** aus [docs/IMAGE_BUILD.md](../docs/IMAGE_BUILD.md) aktiviert die UART (`enable_uart=1`) und nutzt **`/dev/serial0`** für die PZEM — ohne USB-Adapter.

Manuelle OS-Installation: Seriell unter `sudo raspi-config` (Interface Options → Serial) freigeben und ggf. Konsole von der seriellen Schnittstelle nehmen.

---

## 3. Raspberry Pi Software Setup

1.  **Install OS**: Flash **Raspberry Pi OS (Legacy/Lite is fine)** onto your SD card using "Raspberry Pi Imager".
2.  **Network**: Setup Wi-Fi in the Imager settings or plug in Ethernet.
3.  **Boot**: Insert SD card and power on.
4.  **Connect**: Open a terminal on your computer and SSH into the Pi (or attach monitor/keyboard).
    ```bash
    ssh pi@raspberrypi.local
    # Default password is usually 'raspberry' or what you set in the Imager.
    ```

---

## 4. Install VoltWise Software

### 0. OEM: Nur SD flashen (ohne `git` auf dem Pi)

Wenn du das Image aus **IMAGE_BUILD** verwendest, entfällt dieser Abschnitt: Beim **ersten Boot** wird `install.sh` automatisch ausgeführt (Netzwerk im Imager eintragen). Anschließung der PZEM wie unter „Direct GPIO“.

### 1. Manuell: Download the Software

Running in the terminal on your Raspberry Pi:

```bash
# Clone the repository
git clone https://github.com/EvilMonkey09/voltwise.git

# Enter the SENSOR NODE directory
cd voltwise/sensor-node
```

### 2. Run the Installer

We have a magic script that does everything for you.

```bash
# Make it executable
chmod +x install.sh

# Run it
sudo ./install.sh
```

### 3. The Setup Wizard

During installation, the script will ask:

1.  **Serial Port**: Press Enter to accept the default (usually correct if using GPIO/HAT), or select your USB adapter (e.g., `/dev/ttyUSB0`).
2.  **Sensor Configuration**: The script will ask:

    > _"Do you want to run the Advanced Sensor Configuration Wizard?"_

    **Type `y` (Yes).**
    - The Wizard will ask you to **connect only Sensor 1**. (Unplug the data wires of others, or better yet, just wire one at a time as instructed).
    - It will find the sensor and name it **Address 1**.
    - It will ask for **Sensor 2**. Connect it (disconnect #1 if needed, or if robust, just add it). The wizard handles the addressing.
    - Repeat for all sensors.

3.  **Finish**: Once done, the installer will finish setting up the automatic background service.

---

## 5. Verify & Enjoy

1.  **Reboot**:
    ```bash
    sudo reboot
    ```
2.  **Open Dashboard**:
    On your computer/phone connected to the same Wi-Fi, open:
    `http://raspberrypi.local:25500` (or your Pi's IP address: `http://192.168.1.X:25500`)

You should now see the Real-Time Dashboard showing Voltage, Current, and Power!

---

## Wi-Fi setup (no LAN cable)

The **`voltwise-network`** service runs continuously: whenever the Pi has **no usable Ethernet and no active Wi‑Fi client connection**, it starts an **open** access point so staff on site can configure Wi‑Fi:

- **SSID:** `VoltWise-Setup-` followed by a short id (e.g. last digits of the Wi‑Fi MAC).
- **No password.** Connect with a phone or laptop; the **captive portal** (port 80) lets you add one or more Wi-Fi networks. When the node gets back online, the AP stops until the next time there is no uplink.

You can also manage saved Wi‑Fi profiles and set the **node display name** and timezone under **Settings** in the dashboard (`http://<ip>:25500/settings`) when you are already on the network.

Environment tuning (optional): `VOLTWISE_NET_WAIT` (boot grace before counting “offline”, default 90), `VOLTWISE_OFFLINE_BEFORE_AP` (seconds without uplink before opening the AP, default 45).

Service: `sudo systemctl status voltwise-network`

---

## Troubleshooting

- **Dashboard not loading?**
  Check if service is running: `sudo systemctl status voltwise`
- **Readings are 0?**
  Check your soldering/wiring. Ensure RX goes to TX and TX goes to RX.
- **Can't find sensors?**
  Run the wizard manually: `sudo ./venv/bin/python3 configure_sensors.py`

## 6. Updating VoltWise

To update to the latest version, simply run the update script:

1.  **Connect via SSH**: `ssh pi@raspberrypi.local`
2.  **Go to the directory**: `cd voltwise/sensor-node`
3.  **Run the update**:
    ```bash
    sudo ./update.sh
    ```

This will automatically pull the latest changes, update dependencies, and restart the service.

Happy Monitoring! ⚡
