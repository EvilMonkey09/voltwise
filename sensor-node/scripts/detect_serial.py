#!/usr/bin/env python3
"""Pick default serial port for PZEM (USB adapters preferred)."""
import sys

try:
    from serial.tools import list_ports
except ImportError:
    list_ports = None


def detect_default():
    if list_ports:
        ports = list(list_ports.comports())
        for p in ports:
            desc = (p.description or "").lower()
            if any(x in desc for x in ("usb", "uart", "serial", "cp210", "ch340", "ft232", "pl2303")):
                return p.device
        if ports:
            return ports[0].device
    # Fallback heuristics without pyserial
    import glob
    for pattern in ("/dev/ttyUSB*", "/dev/ttyACM*"):
        found = sorted(glob.glob(pattern))
        if found:
            return found[0]
    return "/dev/ttyAMA0"


if __name__ == "__main__":
    print(detect_default())
    sys.exit(0)
