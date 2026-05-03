"""NetworkManager helpers via nmcli (Linux / Raspberry Pi OS)."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


SETUP_CON_NAME = "voltwise-setup-ap"


def nmcli_available() -> bool:
    return shutil.which("nmcli") is not None


def run_nmcli(args: list, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["nmcli", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def wifi_iface() -> str | None:
    r = run_nmcli(["-t", "-f", "DEVICE,TYPE", "device", "status"], timeout=10)
    if r.returncode != 0:
        return None
    for line in r.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split(":")
        if len(parts) >= 2 and parts[1] == "wifi":
            dev = parts[0]
            if dev and dev != "p2p-dev-wlan0":
                return dev
    return None


def ethernet_ready() -> bool:
    for iface in ("eth0", "end0"):
        cpath = Path(f"/sys/class/net/{iface}/carrier")
        if not cpath.exists():
            continue
        try:
            if cpath.read_text().strip() != "1":
                continue
        except OSError:
            continue
        pr = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "dev", iface],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if pr.returncode == 0 and pr.stdout.strip() and " inet " in pr.stdout:
            return True
    return False


def wifi_station_connected(wlan: str | None) -> bool:
    if not wlan:
        return False
    r = run_nmcli(["-t", "-f", "DEVICE,STATE", "device", "status"], timeout=10)
    if r.returncode != 0:
        return False
    for line in r.stdout.strip().split("\n"):
        parts = line.split(":")
        if len(parts) >= 2 and parts[0] == wlan:
            return parts[1] == "connected"
    return False


def connectivity_good(wlan: str | None) -> bool:
    if ethernet_ready():
        return True
    if wifi_station_connected(wlan):
        r = run_nmcli(["networking", "connectivity", "check"], timeout=15)
        if r.returncode == 0:
            out = (r.stdout or "").strip().lower()
            if "full" in out or "limited" in out or "portal" in out:
                return True
        rt = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, timeout=5)
        return wlan and wlan in (rt.stdout or "") and "default" in (rt.stdout or "")
    return False


def has_real_connectivity() -> bool:
    """True if LAN up or Wi-Fi client connected (not the VoltWise setup AP)."""
    if ethernet_ready():
        return True
    r = run_nmcli(["-t", "-f", "NAME", "connection", "show", "--active"], timeout=15)
    if r.returncode != 0:
        return False
    for line in r.stdout.strip().split("\n"):
        name = line.strip()
        if not name or name == SETUP_CON_NAME:
            continue
        ty = run_nmcli(["-g", "connection.type", "connection", "show", name], timeout=10)
        if ty.returncode != 0:
            continue
        ctype = (ty.stdout or "").strip()
        if ctype == "802-11-wireless":
            return True
    return False


def setup_ssid_suffix() -> str:
    wlan = wifi_iface()
    if wlan:
        mac_path = Path(f"/sys/class/net/{wlan}/address")
        if mac_path.exists():
            mac = mac_path.read_text().strip().replace(":", "")
            if len(mac) >= 4:
                return mac[-4:].upper()
    return "SETUP"


def ensure_setup_ap_down():
    run_nmcli(["connection", "down", SETUP_CON_NAME], timeout=30)
    run_nmcli(["connection", "delete", SETUP_CON_NAME], timeout=30)


def start_open_ap(wlan: str, ssid: str) -> bool:
    ensure_setup_ap_down()
    subprocess.run(
        ["nmcli", "device", "disconnect", wlan],
        capture_output=True,
        timeout=30,
    )
    r = run_nmcli(
        [
            "connection",
            "add",
            "type",
            "wifi",
            "ifname",
            wlan,
            "con-name",
            SETUP_CON_NAME,
            "autoconnect",
            "no",
            "ssid",
            ssid,
            "802-11-wireless.mode",
            "ap",
            "802-11-wireless.band",
            "bg",
            "ipv4.method",
            "shared",
            "ipv6.method",
            "ignore",
            "802-11-wireless-security.key-mgmt",
            "none",
        ],
        timeout=60,
    )
    if r.returncode != 0:
        print("voltwise-net: failed to add AP connection:", r.stderr)
        return False
    up = run_nmcli(["connection", "up", SETUP_CON_NAME], timeout=60)
    if up.returncode != 0:
        print("voltwise-net: failed to bring up AP:", up.stderr)
        return False
    return True


def stop_ap():
    ensure_setup_ap_down()


def list_saved_wifi():
    """Return list of {uuid,name,ssid,priority} excluding setup AP."""
    r = run_nmcli(["-t", "-f", "NAME,UUID,TYPE", "connection", "show"], timeout=30)
    rows = []
    if r.returncode != 0:
        return rows
    for line in r.stdout.strip().split("\n"):
        parts = line.split(":")
        if len(parts) < 3:
            continue
        name, uuid, ctype = parts[0], parts[1], parts[2]
        if ctype != "802-11-wireless":
            continue
        if name == SETUP_CON_NAME:
            continue
        ssid = connection_ssid(uuid)
        prio = connection_priority(uuid)
        rows.append(
            {"uuid": uuid, "name": name, "ssid": ssid or name, "priority": prio}
        )
    return sorted(rows, key=lambda x: -x["priority"])


def connection_ssid(uuid: str) -> str | None:
    r = run_nmcli(["-g", "802-11-wireless.ssid", "connection", "show", uuid], timeout=10)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    return None


def connection_priority(uuid: str) -> int:
    r = run_nmcli(["-g", "connection.autoconnect-priority", "connection", "show", uuid], timeout=10)
    if r.returncode == 0 and r.stdout.strip().isdigit():
        return int(r.stdout.strip())
    return 0


def add_wifi_network(ssid: str, password: str | None) -> tuple[bool, str]:
    wlan = wifi_iface()
    if not wlan:
        return False, "No Wi-Fi device found"
    args = ["device", "wifi", "connect", ssid, "ifname", wlan]
    if password:
        args.extend(["password", password])
    r = run_nmcli(args, timeout=120)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "connection failed").strip()
    return True, "Connected"


def delete_connection(uuid: str) -> tuple[bool, str]:
    r = run_nmcli(["connection", "delete", uuid], timeout=30)
    if r.returncode != 0:
        return False, (r.stderr or "delete failed").strip()
    return True, "Deleted"


def set_priority(uuid: str, priority: int) -> tuple[bool, str]:
    r = run_nmcli(
        ["connection", "modify", uuid, "connection.autoconnect-priority", str(priority)],
        timeout=15,
    )
    if r.returncode != 0:
        return False, (r.stderr or "").strip()
    return True, "OK"


def activate_wifi(uuid: str) -> tuple[bool, str]:
    r = run_nmcli(["connection", "up", uuid], timeout=120)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "").strip()
    return True, "OK"
