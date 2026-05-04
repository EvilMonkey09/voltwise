"""NetworkManager helpers via nmcli (Linux / Raspberry Pi OS)."""
from __future__ import annotations

import os
import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path


SETUP_CON_NAME = "voltwise-setup-ap"

# Written when setup AP is up; NetworkManager's shared dnsmasq includes this directory.
CAPTIVE_DNSMASQ_PATH = Path("/etc/NetworkManager/dnsmasq-shared.d/voltwise-captive.conf")

# Resolve these hostnames to the AP gateway so phones' captive-portal checks hit our HTTP server.
CPD_DNS_NAMES = (
    "connectivitycheck.gstatic.com",
    "connectivitycheck.android.com",
    "android.clients.google.com",
    "clients1.google.com",
    "clients3.google.com",
    "clients.l.google.com",
    "captive.apple.com",
    "www.apple.com",
    "www.msftncsi.com",
    "msftncsi.com",
    "dns.msftncsi.com",
    "ipv6.msftncsi.com",
    "msftconnecttest.com",
    "www.msftconnecttest.com",
    "connectivitycheck.platform.hicloud.com",
    "connectivitycheck.platform.hihonorcloud.com",
)


def nmcli_available() -> bool:
    return shutil.which("nmcli") is not None


def run_nmcli(args: list, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["nmcli", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def device_active_connection(dev: str) -> str | None:
    """Active NetworkManager connection name for a device, or None."""
    r = run_nmcli(["-g", "GENERAL.CONNECTION", "device", "show", dev], timeout=10)
    if r.returncode != 0:
        return None
    name = (r.stdout or "").strip()
    if not name or name == "--":
        return None
    return name


def connection_wifi_mode(name: str | None) -> str | None:
    if not name:
        return None
    r = run_nmcli(["-g", "802-11-wireless.mode", "connection", "show", name], timeout=10)
    if r.returncode != 0:
        return None
    v = (r.stdout or "").strip()
    return v or None


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
        has_ipv4 = pr.returncode == 0 and pr.stdout.strip() and " inet " in pr.stdout
        if not has_ipv4:
            continue
        # Treat LAN as usable only when it also carries default route.
        # This avoids false "uplink_ok" when eth0 keeps a stale/local address.
        rt = subprocess.run(
            ["ip", "route", "show", "default", "dev", iface],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if rt.returncode == 0 and "default" in (rt.stdout or ""):
            return True
    return False


def wifi_station_connected(wlan: str | None) -> bool:
    """True if wlan is a Wi-Fi *client* connected to an external network — not our setup AP."""
    if not wlan:
        return False
    r = run_nmcli(["-t", "-f", "DEVICE,STATE", "device", "status"], timeout=10)
    if r.returncode != 0:
        return False
    for line in r.stdout.strip().split("\n"):
        parts = line.split(":")
        if len(parts) >= 2 and parts[0] == wlan:
            if parts[1] != "connected":
                return False
            # In AP mode NM still reports STATE=connected — do not treat as uplink.
            conn = device_active_connection(wlan)
            if conn == SETUP_CON_NAME:
                return False
            if connection_wifi_mode(conn) == "ap":
                return False
            return True
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


def prefer_ethernet_wifi_policy_enabled() -> bool:
    """When True (default), disable Wi-Fi radio while LAN has default route — one path only."""
    v = (os.environ.get("VOLTWISE_PREFER_ETHERNET") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def apply_ethernet_preferred_wifi_policy() -> None:
    """
    If Ethernet carries IPv4 + default route, turn Wi-Fi radio off so the node has a single
    client address (Central / scans see one IP). When LAN is not usable, turn Wi-Fi back on.
    No-op when VOLTWISE_PREFER_ETHERNET=0 (or false).
    """
    if not prefer_ethernet_wifi_policy_enabled():
        return
    if ethernet_ready():
        run_nmcli(["radio", "wifi", "off"], timeout=15)
    else:
        run_nmcli(["radio", "wifi", "on"], timeout=15)


def has_real_connectivity() -> bool:
    """True if LAN up or Wi-Fi client connected (not the VoltWise setup AP)."""
    wlan = wifi_iface()
    return connectivity_good(wlan)


def connectivity_uplink_detail() -> str:
    """Why has_real_connectivity() is True — for journal diagnostics."""
    if ethernet_ready():
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
            has_ipv4 = pr.returncode == 0 and pr.stdout.strip() and " inet " in pr.stdout
            if has_ipv4:
                rt = subprocess.run(
                    ["ip", "route", "show", "default", "dev", iface],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if rt.returncode == 0 and "default" in (rt.stdout or ""):
                    return f"LAN {iface} has IPv4 + default route"
    wlan = wifi_iface()
    if wlan and wifi_station_connected(wlan):
        rt = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if rt.returncode == 0 and wlan in (rt.stdout or "") and "default" in (rt.stdout or ""):
            return f"Wi-Fi station on {wlan} has default route"
        return f"Wi-Fi station on {wlan} connected"
    return "unknown (internal mismatch)"


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
    remove_captive_dnsmasq()


def ipv4_on_device(dev: str, retries: int = 10, delay: float = 0.35) -> str | None:
    """First IPv4 address on device (e.g. AP gateway on shared link)."""
    for _ in range(retries):
        r = run_nmcli(["-g", "IP4.ADDRESS", "device", "show", dev], timeout=10)
        if r.returncode == 0 and (r.stdout or "").strip():
            first = (r.stdout or "").strip().split("\n")[0].strip()
            if first and "/" in first:
                return first.split("/")[0].strip()
        time.sleep(delay)
    return None


def write_captive_dnsmasq(gateway_ip: str) -> None:
    """Point captive-portal probe hostnames at the AP so clients open the sign-in page."""
    try:
        CAPTIVE_DNSMASQ_PATH.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"voltwise-net: cannot create {CAPTIVE_DNSMASQ_PATH.parent}: {e}")
        return
    lines = ["# Managed by VoltWise (voltwise-network) — do not edit by hand", ""]
    for name in CPD_DNS_NAMES:
        lines.append(f"address=/{name}/{gateway_ip}")
    try:
        CAPTIVE_DNSMASQ_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as e:
        print(f"voltwise-net: cannot write captive DNS: {e}")
        return
    _signal_dnsmasq_reload()


def remove_captive_dnsmasq() -> None:
    try:
        if CAPTIVE_DNSMASQ_PATH.is_file():
            CAPTIVE_DNSMASQ_PATH.unlink()
    except OSError as e:
        print(f"voltwise-net: cannot remove captive DNS file: {e}")
    _signal_dnsmasq_reload()


def _signal_dnsmasq_reload() -> None:
    subprocess.run(
        ["killall", "-HUP", "dnsmasq"],
        capture_output=True,
        timeout=5,
    )
    time.sleep(0.35)
    subprocess.run(
        ["killall", "-HUP", "dnsmasq"],
        capture_output=True,
        timeout=5,
    )


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
        ],
        timeout=60,
    )
    if r.returncode != 0:
        print("voltwise-net: failed to add AP connection:", r.stderr)
        return False
    # Ensure the setup AP stays fully open (no passphrase/secret prompts).
    run_nmcli(
        ["connection", "modify", SETUP_CON_NAME, "remove", "802-11-wireless-security"],
        timeout=30,
    )
    up = run_nmcli(["connection", "up", SETUP_CON_NAME], timeout=60)
    if up.returncode != 0:
        print("voltwise-net: failed to bring up AP:", up.stderr)
        return False
    gw = ipv4_on_device(wlan)
    if gw:
        write_captive_dnsmasq(gw)
    else:
        print("voltwise-net: warning: could not read AP IPv4 — captive portal DNS hints skipped")
    return True


def scan_wifi_networks() -> tuple[list[dict], str | None]:
    """
    Return (networks, hint). Networks are {ssid, signal, security}.
    While wlan is in AP mode, scanning may be empty — hint explains that.
    """
    wlan = wifi_iface()
    if not wlan:
        return [], "No Wi-Fi device"

    run_nmcli(["device", "wifi", "rescan"], timeout=20)
    time.sleep(1.2)

    rows: list[dict] = []
    r = run_nmcli(["--json", "device", "wifi", "list"], timeout=35)
    if r.returncode == 0 and (r.stdout or "").strip():
        try:
            data = json.loads(r.stdout)
            if isinstance(data, list):
                iter_aps = data
            elif isinstance(data, dict):
                iter_aps = (
                    data.get("wifi")
                    or data.get("wifi-networks")
                    or data.get("devices")
                    or []
                )
                if not isinstance(iter_aps, list):
                    iter_aps = []
            else:
                iter_aps = []
            data = iter_aps
            if not isinstance(data, list):
                data = []
            best: dict[str, dict] = {}
            for ap in data:
                if not isinstance(ap, dict):
                    continue
                ssid = (ap.get("ssid") or ap.get("SSID") or "").strip()
                if not ssid:
                    continue
                try:
                    sig = int(ap.get("signal", ap.get("SIGNAL", 0)) or 0)
                except (TypeError, ValueError):
                    sig = 0
                sec = (ap.get("security", ap.get("SECURITY") or "") or "").strip()
                prev = best.get(ssid)
                if prev is None or sig > int(prev.get("signal") or 0):
                    best[ssid] = {
                        "ssid": ssid,
                        "signal": sig,
                        "security": sec,
                        "bars": signal_to_bars(sig),
                    }
            rows = sorted(best.values(), key=lambda x: -x["signal"])
        except (json.JSONDecodeError, TypeError, ValueError):
            rows = []

    if not rows:
        r2 = run_nmcli(
            ["-t", "-e", "yes", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"],
            timeout=35,
        )
        if r2.returncode == 0 and (r2.stdout or "").strip():
            best2: dict[str, dict] = {}
            for line in (r2.stdout or "").strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    ssid_raw, sig_s, sec = line.rsplit(":", 2)
                except ValueError:
                    continue
                ssid = ssid_raw.replace("\\:", ":").strip()
                try:
                    sig = int(sig_s)
                except ValueError:
                    sig = 0
                sec = sec.strip()
                if not ssid:
                    continue
                prev = best2.get(ssid)
                if prev is None or sig > int(prev.get("signal") or 0):
                    best2[ssid] = {
                        "ssid": ssid,
                        "signal": sig,
                        "security": sec,
                        "bars": signal_to_bars(sig),
                    }
            rows = sorted(best2.values(), key=lambda x: -x["signal"])

    hint = None
    if not rows:
        hint = (
            "No networks found (scan while hosting an AP is limited on some hardware). "
            "Enter the SSID manually below."
        )
    return rows, hint


def stop_ap():
    ensure_setup_ap_down()


def _collect_wifi_connection_rows() -> list[dict]:
    """All Wi-Fi profiles except setup AP — raw rows for deduplication."""
    r = run_nmcli(["-t", "-f", "NAME,UUID,TYPE", "connection", "show"], timeout=30)
    rows: list[dict] = []
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
    return rows


def find_wifi_connection_uuid_for_ssid(target_ssid: str) -> str | None:
    """Return UUID of an existing Wi-Fi connection with this SSID, or None."""
    want = (target_ssid or "").strip()
    if not want:
        return None
    for row in _collect_wifi_connection_rows():
        s = (connection_ssid(row["uuid"]) or row.get("ssid") or "").strip()
        if s == want:
            return row["uuid"]
    return None


def list_saved_wifi():
    """
    Return list of {uuid,name,ssid,priority} excluding setup AP.
    Deduplicates by SSID: NetworkManager often creates multiple profiles for the same
    network (e.g. repeated \"Save\" in the captive portal). We keep the best profile
    and delete the rest.
    """
    rows = _collect_wifi_connection_rows()
    by_key: dict[str, list[dict]] = {}
    for row in rows:
        ssid = (row.get("ssid") or "").strip()
        key = ssid if ssid else f"__uuid__{row['uuid']}"
        by_key.setdefault(key, []).append(row)

    merged: list[dict] = []
    for key, group in by_key.items():
        if len(group) == 1:
            merged.append(group[0])
            continue
        group.sort(
            key=lambda x: (
                -int(x.get("priority") or 0),
                1 if str(x.get("name", "")).startswith("voltwise-w-") else 0,
                str(x.get("name", "")),
            )
        )
        winner = group[0]
        for loser in group[1:]:
            run_nmcli(["connection", "delete", loser["uuid"]], timeout=30)
        merged.append(winner)

    return sorted(merged, key=lambda x: -x["priority"])


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


def signal_to_bars(signal: int | None) -> int:
    """Map dBm-like percentage (0–100 from nmcli) to 0–3 bars for UI."""
    try:
        s = int(signal or 0)
    except (TypeError, ValueError):
        s = 0
    if s >= 55:
        return 3
    if s >= 30:
        return 2
    if s > 0:
        return 1
    return 0


def _wifi_profile_con_name(ssid: str) -> str:
    h = hashlib.sha256(ssid.encode("utf-8")).hexdigest()[:10]
    safe = re.sub(r"[^a-zA-Z0-9]+", "-", ssid)[:20].strip("-") or "net"
    return f"voltwise-w-{safe}-{h}"


def save_wifi_profile_only(ssid: str, password: str | None) -> tuple[bool, str]:
    """
    Add or update an inactive Wi-Fi connection profile (used while wlan is in AP mode).
    If a profile for the same SSID already exists, update it instead of creating another.
    """
    existing = find_wifi_connection_uuid_for_ssid(ssid)
    if existing:
        args = [
            "connection",
            "modify",
            existing,
            "connection.autoconnect",
            "yes",
            "connection.autoconnect-priority",
            "80",
        ]
        if password:
            args.extend(
                [
                    "wifi-sec.key-mgmt",
                    "wpa-psk",
                    "wifi-sec.psk",
                    password,
                ]
            )
        else:
            args.extend(["wifi-sec.key-mgmt", "none"])
        r = run_nmcli(args, timeout=90)
        if r.returncode != 0:
            return False, (r.stderr or r.stdout or "connection modify failed").strip()
        return True, ""

    name = _wifi_profile_con_name(ssid)
    args = [
        "connection",
        "add",
        "type",
        "wifi",
        "con-name",
        name,
        "ssid",
        ssid,
        "connection.autoconnect",
        "yes",
        "connection.autoconnect-priority",
        "80",
    ]
    if password:
        args.extend(["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", password])
    else:
        args.extend(["wifi-sec.key-mgmt", "none"])
    r = run_nmcli(args, timeout=90)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        if "already exists" in err.lower() or "gehort zu ' bereits" in err.lower():
            return True, ""
        return False, err or "nmcli connection add failed"
    return True, ""


def switch_from_ap_to_saved_wifi(ssid: str) -> tuple[bool, str]:
    """
    Tear down the VoltWise setup AP, then bring up the saved profile for ``ssid``.
    Used after saving credentials from the captive portal (same radio cannot be AP+client).
    """
    ensure_setup_ap_down()
    time.sleep(1.2)
    uuid = find_wifi_connection_uuid_for_ssid(ssid)
    if uuid:
        r = run_nmcli(["connection", "up", uuid], timeout=120)
    else:
        name = _wifi_profile_con_name(ssid)
        r = run_nmcli(["connection", "up", name], timeout=120)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "connection up failed").strip()
    return True, ""


def add_wifi_network_result(ssid: str, password: str | None) -> dict:
    """
    Result dict: ok, optional mode ('connected'|'saved'), handoff, message (German), error.
    On the setup AP, the profile is saved and a background handoff tears down the AP
    and runs ``connection up`` for that profile (same radio cannot be AP+client at once).
    """
    wlan = wifi_iface()
    if not wlan:
        return {"ok": False, "error": "Kein WLAN-Adapter gefunden."}

    on_setup_ap = device_active_connection(wlan) == SETUP_CON_NAME

    if on_setup_ap:
        ok, err = save_wifi_profile_only(ssid, password)
        if not ok:
            return {"ok": False, "error": err}
        return {
            "ok": True,
            "mode": "saved",
            "handoff": True,
            "message": (
                "Netzwerk gespeichert. Der Einrichtungs-Hotspot wird jetzt beendet und der Pi "
                "verbindet sich mit diesem WLAN (einige Sekunden). Das Handy verliert dabei "
                "kurz die Verbindung zum Pi — danach den Pi im Heim-WLAN unter seiner neuen IP erreichen."
            ),
        }

    args = ["device", "wifi", "connect", ssid, "ifname", wlan]
    if password:
        args.extend(["password", password])
    r = run_nmcli(args, timeout=120)
    if r.returncode != 0:
        err_t = (r.stderr or r.stdout or "").strip() or "Verbindung fehlgeschlagen."
        return {"ok": False, "error": err_t}
    return {
        "ok": True,
        "mode": "connected",
        "message": "Mit WLAN verbunden. Das Einrichtungsfenster kann sich schließen.",
    }


def add_wifi_network(ssid: str, password: str | None) -> tuple[bool, str]:
    """Backward-compatible wrapper for sensor-node app routes."""
    out = add_wifi_network_result(ssid, password)
    if out.get("ok"):
        return True, out.get("message") or "OK"
    return False, out.get("error") or "Failed"


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
