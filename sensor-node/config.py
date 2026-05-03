# Configuration for VoltWise
import os


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


# When True (or env VOLTWISE_SIMULATION=1), no Modbus reads — synthetic data for demos / bench testing.
SIMULATION_MODE = _env_truthy("VOLTWISE_SIMULATION")

# List of Modbus addresses for the PZEM-004T modules.
# Example: [1] for single phase, [1, 2, 3] for three-phase.
SENSOR_ADDRESSES = [1, 2, 3]

# Serial port configuration
# On Raspberry Pi with USB adapter: '/dev/ttyUSB0'
# On Raspberry Pi with direct GPIO (UART): '/dev/ttyS0' or '/dev/serial0'
SERIAL_PORT = '/dev/ttyAMA0'

# Modbus Configuration
BAUDRATE = 9600
BYTESIZE = 8
PARITY = 'N'
STOPBITS = 1
TIMEOUT = 0.5

# Debug Configuration
DEBUG_MODE = False
