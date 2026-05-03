import math
import minimalmodbus
import serial
import time
import config


class PZEMHandler:
    def __init__(self, port, addresses):
        self.port = port
        self.addresses = addresses
        self.instrument = None
        self.simulation_mode = bool(getattr(config, "SIMULATION_MODE", False))
        self._sim_energy_wh = {}
        self._sim_last_tick = time.time()
        self._sim_t0 = time.time()

        if self.simulation_mode:
            print("VoltWise: SIMULATION MODE — synthetic measurements (no PZEM hardware).")
            for a in addresses:
                self._sim_energy_wh[a] = 0.0
            return

        try:
            # Setup minimalmodbus instrument
            # We use a dummy address initially, will be changed per request
            self.instrument = minimalmodbus.Instrument(self.port, 1)
            self.instrument.serial.baudrate = 9600
            self.instrument.serial.bytesize = 8
            self.instrument.serial.parity = serial.PARITY_NONE
            self.instrument.serial.stopbits = 1
            self.instrument.serial.timeout = 0.5
            self.instrument.mode = minimalmodbus.MODE_RTU
            self.instrument.clear_buffers_before_each_transaction = True
            
            # Enable debug mode if configured
            if hasattr(config, 'DEBUG_MODE') and config.DEBUG_MODE:
                self.instrument.debug = True
                print(f"MinimalModbus debug mode enabled for port {self.port}")
        except Exception as e:
            print(f"Error opening serial port {self.port}: {e}")
            print("Switching to SIMULATION MODE")
            self.simulation_mode = True
            self._sim_energy_wh = {a: 0.0 for a in self.addresses}
            self._sim_last_tick = time.time()
            self._sim_t0 = time.time()

    def read_all(self):
        """
        Reads data from all configured sensors.
        Returns a dictionary keyed by address.
        """
        data = {}
        if self.simulation_mode:
            now = time.time()
            dt = max(0.0, min(5.0, now - self._sim_last_tick))
            self._sim_last_tick = now
            for address in self.addresses:
                data[address] = self._simulate_data(address, dt)
            return data

        for address in self.addresses:
            try:
                self.instrument.address = address
                values = self.instrument.read_registers(0x0000, 10, functioncode=4)

                voltage = values[0] * 0.1
                current_low = values[1]
                current_high = values[2]
                current = ((current_high << 16) | current_low) * 0.001
                power_low = values[3]
                power_high = values[4]
                power = ((power_high << 16) | power_low) * 0.1
                energy_low = values[5]
                energy_high = values[6]
                energy = ((energy_high << 16) | energy_low)
                frequency = values[7] * 0.1
                pf = values[8] * 0.01

                data[address] = {
                    "voltage": round(voltage, 1),
                    "current": round(current, 3),
                    "power": round(power, 1),
                    "energy": energy,
                    "frequency": round(frequency, 1),
                    "pf": round(pf, 2),
                }

            except Exception as e:
                print(f"Error reading sensor {address}: {e}")
                data[address] = None
        return data

    def reset_energy(self, address):
        """
        Resets energy counter for a specific address.
        Function code 0x42 (Spectial for PZEM).
        """
        if self.simulation_mode:
            print(f"[SIM] Energy reset for address {address}")
            self._sim_energy_wh[address] = 0.0
            return True
            
        try:
            self.instrument.address = address
            # minimalmodbus doesn't have a generic "send raw" easily for specific non-std codes
            # But the PZEM reset command is: Address, 0x42, CRC-Low, CRC-High
            # minimalmodbus `_perform_command` might be needed OR `write_register` if mapped
            # Actually PZEM reset is just a 4-byte frame: Addr, 0x42, CRC
            
            # Implementing raw serial write for reset
            payload = bytearray([address, 0x42])
            # Calculate CRC
            crc = self._calculate_crc(payload)
            payload.extend(crc)
            
            self.instrument.serial.write(payload)
            time.sleep(0.5)
            # Response is same as sent (4 bytes)
            # We MUST read it to clear the buffer for the next transaction
            _ = self.instrument.serial.read(4) 
            return True
        except Exception as e:
            print(f"Error resetting energy for {address}: {e}")
            return False

    def _simulate_data(self, address, dt):
        """Smooth synthetic values + cumulative energy (Wh) for UI / DB testing."""
        now = time.time()
        t = now - self._sim_t0
        phase = (address - 1) * (2 * math.pi / max(len(self.addresses), 1))

        voltage = 230.0 + 4.0 * math.sin(t / 42.0 + phase) + 1.5 * math.sin(t / 17.3)
        current = (1.2 + 0.6 * address) * (0.85 + 0.15 * math.sin(t / 55.0 + phase * 1.1))
        current = max(0.05, current)
        pf = min(0.99, max(0.82, 0.93 + 0.04 * math.sin(t / 31.0)))
        power = voltage * current * pf
        hz = 50.0 + 0.06 * math.sin(t / 88.0)

        wh = self._sim_energy_wh.get(address, 0.0) + (power * dt / 3600.0)
        self._sim_energy_wh[address] = wh

        return {
            "voltage": round(voltage, 1),
            "current": round(current, 3),
            "power": round(power, 1),
            "energy": round(wh, 2),
            "frequency": round(hz, 1),
            "pf": round(pf, 2),
        }

    def _calculate_crc(self, data):
        """Calculates CRC16 for Modbus."""
        crc = 0xFFFF
        for pos in data:
            crc ^= pos
            for i in range(8):
                if (crc & 1) != 0:
                    crc >>= 1
                    crc ^= 0xA001
                else:
                    crc >>= 1
        return bytearray([crc & 0xFF, (crc >> 8) & 0xFF])
