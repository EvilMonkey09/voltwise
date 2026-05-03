"""
Keep VoltWise setup AP available whenever there is no usable LAN or Wi-Fi client:
- After boot grace, if connectivity is missing for debounce period → open AP + captive portal (port 80).
- When connectivity returns → stop AP and portal; repeat monitoring forever.

Linux + NetworkManager only; exits immediately on other platforms.

Run from sensor-node: python3 -m voltwise_network.daemon
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

BOOT_GRACE_SEC = int(os.environ.get("VOLTWISE_NET_WAIT", "90"))
OFFLINE_DEBOUNCE_SEC = int(os.environ.get("VOLTWISE_OFFLINE_BEFORE_AP", "45"))
POLL_SEC = int(os.environ.get("VOLTWISE_NET_POLL", "5"))


def main():
    if sys.platform != "linux":
        print("voltwise-net: skipping (not Linux)")
        sys.exit(0)

    from . import nm_helpers

    if not nm_helpers.nmcli_available():
        print("voltwise-net: nmcli not found, skipping")
        sys.exit(0)

    wlan = nm_helpers.wifi_iface()
    if not wlan:
        print("voltwise-net: no Wi-Fi interface, skipping setup AP")
        sys.exit(0)

    node_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    portal_proc: subprocess.Popen | None = None

    def stop_portal():
        nonlocal portal_proc
        if portal_proc is None:
            return
        try:
            portal_proc.terminate()
            portal_proc.wait(timeout=8)
        except Exception:
            try:
                portal_proc.kill()
            except Exception:
                pass
        portal_proc = None

    def start_portal():
        nonlocal portal_proc
        stop_portal()
        exe = sys.executable
        portal_proc = subprocess.Popen(
            [exe, "-m", "voltwise_network.portal_main"],
            cwd=node_root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    boot_until = time.time() + BOOT_GRACE_SEC
    offline_since: float | None = None
    setup_active = False
    last_log_kind = ""

    print(
        f"voltwise-net: monitoring (boot_grace={BOOT_GRACE_SEC}s, "
        f"offline_before_ap={OFFLINE_DEBOUNCE_SEC}s)"
    )

    try:
        while True:
            now = time.time()
            connected = nm_helpers.has_real_connectivity()

            # One line when *state kind* changes — no ERROR, but explains missing AP (e.g. false uplink).
            if connected:
                log_state = "uplink_ok"
                extra = nm_helpers.connectivity_uplink_detail()
            elif now < boot_until:
                log_state = "boot_grace"
                extra = f"{int(max(0, boot_until - now))}s left before offline detection"
            elif setup_active:
                log_state = "ap_running"
                extra = "open SSID VoltWise-Setup-… + captive portal"
            elif offline_since is None:
                log_state = "offline_debounce"
                extra = "starting timer (no LAN / no Wi-Fi client)"
            elif now - offline_since < OFFLINE_DEBOUNCE_SEC:
                log_state = "offline_debounce"
                extra = (
                    f"{int(OFFLINE_DEBOUNCE_SEC - (now - offline_since))}s until AP may start"
                )
            else:
                log_state = "will_start_ap"
                extra = "bringing up AP next"

            if log_state != last_log_kind:
                line = f"voltwise-net: state={log_state}"
                if extra:
                    line += f" — {extra}"
                print(line, flush=True)
                last_log_kind = log_state

            if connected:
                offline_since = None
                if setup_active:
                    print("voltwise-net: connectivity restored — stopping setup AP")
                    nm_helpers.stop_ap()
                    stop_portal()
                    setup_active = False
                time.sleep(POLL_SEC)
                continue

            # No Ethernet / no Wi-Fi client profile active
            if now < boot_until:
                time.sleep(POLL_SEC)
                continue

            if offline_since is None:
                offline_since = now
            if now - offline_since < OFFLINE_DEBOUNCE_SEC:
                time.sleep(POLL_SEC)
                continue

            if not setup_active:
                suffix = nm_helpers.setup_ssid_suffix()
                ssid = f"VoltWise-Setup-{suffix}"
                print(f"voltwise-net: starting open setup AP {ssid}")
                if not nm_helpers.start_open_ap(wlan, ssid):
                    print("voltwise-net: failed to start AP, retry later")
                    time.sleep(30)
                    continue
                start_portal()
                setup_active = True

            time.sleep(POLL_SEC)
    except KeyboardInterrupt:
        nm_helpers.stop_ap()
        stop_portal()
        sys.exit(0)


if __name__ == "__main__":
    main()
