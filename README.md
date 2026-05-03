# VoltWise

An Open Source Energy Monitoring System using Raspberry Pis and PZEM-004T sensors.

This repository is divided into two parts:

## 1. [Sensor Node](./sensor-node)

The software that runs on the Raspberry Pi.

- Connects to PZEM-004T sensors.
- Provides a local web dashboard at `http://<pi-ip>:25500` with **Settings** (device name, timezone, Wi‑Fi profiles).

**[>> Go to Sensor Node Documentation](./sensor-node/SETUP_GUIDE.md)**

**Fertiges SD-Image (nur flashen):** Vorgebautes Raspberry-Pi-OS-Image mit automatischer Erstinstallation und **GPIO-UART / `/dev/serial0`** für PZEM per Jumperkabel — siehe [docs/IMAGE_BUILD.md](docs/IMAGE_BUILD.md). Lokal: `tools/image-build/build-image.sh` (Docker). Auf GitHub: Workflow **„Build SD image“** baut dieselbe `.img.xz` und legt sie als Artifact / bei Tag `v*` am Release ab.

## 2. [Central Dashboard](./central-dashboard)

(Optional) A central server to monitor multiple sensor nodes.

- runs on PC/Mac/Linux.
- Aggregates data from multiple Pis.
- **[Download Central](https://github.com/EvilMonkey09/voltwise/releases/latest)** (Windows / Linux / macOS — siehe Release-Assets)

Versionierte **Komplett-Releases** (Node SD-Image + Central): Tag **`v*`** pushen → Workflow **„Release (Node SD + Central)“**.
- _Note for Mac Users: If you see a security warning, please Right-Click -> Open._

---

## Quick Start (Raspberry Pi)

### A) Fertig-Image (empfohlen für Einsatz vor Ort)

1. Image bauen (Docker): `./tools/image-build/build-image.sh` → Datei unter `dist/`.
2. Mit **Raspberry Pi Imager** auf die SD schreiben; im Imager **WLAN/SSH/Benutzer** setzen (Erstinstallation braucht Internet).
3. Pi starten; nach ein paar Minuten Dashboard: `http://<pi-ip>:25500`.

Details: [docs/IMAGE_BUILD.md](docs/IMAGE_BUILD.md).

### B) Manuell (Repository auf dem Pi)

1.  Clone this repository:
    ```bash
    git clone https://github.com/EvilMonkey09/voltwise.git
    ```
2.  Enter the sensor directory:
    ```bash
    cd voltwise/sensor-node
    ```
3.  Run the installer:
    ```bash
    sudo ./install.sh
    ```
