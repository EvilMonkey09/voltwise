# VoltWise Node — fertiges SD-Image (nur flashen)

Ziel: **eine `.img` / `.img.xz`**, die du mit dem **Raspberry Pi Imager** auf die SD schreibst. Beim **ersten Boot** installiert sich der **Sensor-Node** automatisch — **PZEM per Jumperkabel am GPIO-UART** ist vorkonfiguriert (`SERIAL_PORT=/dev/serial0`).

## Was im Image steckt

- **Raspberry Pi OS Lite (64-bit, Bookworm)** — passt u. a. zum **Raspberry Pi 3 B** und neueren Modellen.
- **`voltwise-sensor-node.tar.gz`** auf der Boot-Partition (Software aus diesem Repo).
- **`enable_uart=1`** und Entfernen von `console=serial0` aus `cmdline.txt`, damit **GPIO 14/15** für den **PZEM** frei sind (typisch: `/dev/serial0`).
- **systemd**-Unit **`voltwise-firstboot.service`**: einmalig Netz → `apt` → `install.sh` im Modus **NONINTERACTIVE**.

## Voraussetzungen beim ersten Boot

- **Netzwerk**: Ethernet oder WLAN **muss erreichbar sein**, damit `apt` und `pip` laufen. Am einfachsten **WLAN/Ethernet in Raspberry Pi Imager (Erweiterte Optionen)** eintragen, **bevor** du das Image schreibst.
- **Benutzer**: Es muss ein Login mit **UID 1000** existieren (Standard, wenn du einen Benutzer im Imager anlegst). Das Firstboot-Skript installiert für diesen User nach `/home/<user>/voltwise/sensor-node`.

## Image selbst bauen (Docker)

Vom **Repository-Root**:

```bash
chmod +x tools/image-build/build-image.sh
./tools/image-build/build-image.sh
```

- Nutzt **Docker** (auf macOS: Docker Desktop, **privileged** für Loop-Devices).
- Legt Ergebnisse unter **`dist/`** ab:
  - `voltwise-node-bookworm-arm64-lite.img`
  - optional `…img.xz` (langsam, kleiner für Upload).

Cache für das Raspberry-OS-Download: `~/.cache/voltwise-image-cache/` (vermeidet erneuten Download).

### Raspberry Pi OS URL / Dateiname

Wenn der Download-Link veraltet ist, setze eine aktuelle URL und ggf. den **Dateinamen der entpackten `.img`**:

```bash
export RPI_OS_IMG_URL='https://downloads.raspberrypi.org/raspios_lite_arm64/images/…/….img.xz'
export RPI_OS_IMG_NAME='….img'   # Name der Datei *nach* xz -d
./tools/image-build/build-image.sh
```

Ohne Kompression (schneller):

```bash
COMPRESS=0 ./tools/image-build/build-image.sh
```

## SD-Karte schreiben

1. **Raspberry Pi Imager** → „OS auswählen“ → **Benutzerdefiniert** / eigene Image-Datei → `dist/voltwise-node-bookworm-arm64-lite.img` (oder `.img.xz` nach lokalem Entpacken).
2. Imager: **SSH**, **Benutzer/Passwort**, **WLAN** wie gewünscht setzen.
3. Schreiben, SD in den **Pi 3 B**, Strom an.

Erster Boot: **einige Minuten** (Download/Installation). Danach Dashboard: **`http://<pi-ip>:25500`**.

### GPIO / Jumperkabel (Standard)

- **Seriell**: **`/dev/serial0`** (nach `enable_uart` typisch der Mini-UART auf TX/RX — siehe `SETUP_GUIDE.md`).
- Modbus/Baud wie in `config.py` / PZEM-Datenblatt.

### Manuelle Installation weiter möglich

Weiterhin möglich: Repo klonen und `sudo ./install.sh` auf einem normalen Raspberry Pi OS — wie in der Haupt-**README**.

## Raspberry Pi 3 B

- **64-bit Lite** wird unterstützt; bei sehr alter Firmware ggf. Imager aktualisieren.
- Falls du **32-bit** (`armhf`) bevorzugst: eigenes OS-Image einbinden (`RPI_OS_IMG_URL` auf die **armhf**-Lite-Variante setzen) und gleichen Build-Prozess nutzen.

## GitHub Actions (CI)

- **Nur SD-Image:** Workflow **„Build SD image“** (`.github/workflows/build-sd-image.yml`) — manuell unter **Actions** → **Run workflow**. Ergebnis: **Artifact** mit der **`.xz`**.
- **Komplett-Release (empfohlen):** Workflow **„Release (Node SD + Central)“** (`.github/workflows/release.yml`) läuft beim Push eines Tags **`v*`** (z. B. `v1.0.2`). Das **GitHub Release** enthält dann:
  - **Node:** `VoltWise-Node-RaspberryPi-arm64-bookworm-lite.img.xz` (Raspberry Pi Imager)
  - **Central:** Windows-EXE, Linux-Binary, macOS-DMG

Der SD-Build läuft **ohne Docker** auf dem **Ubuntu-Runner** (`sudo losetup` / `mount`). Lokal weiterhin **`tools/image-build/build-image.sh`** (Docker) oder **`docker-build-inner.sh`** mit `SOURCE_DIR` / `OUTPUT_DIR` / `CACHE_DIR`.

**Hinweis:** Variable **`RPI_OS_IMG_URL`** (Actions → Variables) setzen, falls der Standard-Download zu Raspberry Pi OS veraltet ist.
