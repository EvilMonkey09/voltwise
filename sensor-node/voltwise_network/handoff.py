"""Background job: leave setup AP and connect saved Wi-Fi (started by captive portal)."""
from __future__ import annotations

import subprocess
import sys
import time


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python -m voltwise_network.handoff SSID", flush=True)
        sys.exit(2)
    ssid = sys.argv[1]
    time.sleep(2)
    from voltwise_network import nm_helpers

    ok, err = nm_helpers.switch_from_ap_to_saved_wifi(ssid)
    print(f"voltwise-handoff: ok={ok} err={err!r}", flush=True)
    subprocess.run(
        ["systemctl", "restart", "voltwise-network.service"],
        timeout=90,
    )


if __name__ == "__main__":
    main()
