import minimalmodbus
import serial
import random
import time
import config

class PZEMHandler:
    def __init__(self, port, addresses):
        self.port = port
        self.addresses = addresses
        self.instrument = None
        self.simulation_mode = False

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

    def read_all(self):
        """
        Reads data from all configured sensors.
        Returns a dictionary keyed by address.
        """
        data = {}
        for address in self.addresses:
            if self.simulation_mode:
                data[address] = self._simulate_data(address)
            else:
                try:
                    self.instrument.address = address
                    # Read Input Registers (Function Code 0x04)
                    # Register 0x0000: Voltage (0.1V)
                    # Register 0x0001: Current Low (0.001A)
                    # Register 0x0002: Current High 
                    # ... and so on.
                    # minimalmodbus read_registers reads N registers starting from addr
                    
                    # Reading 10 registers starting from 0x0000
                    # 0: Voltage
                    # 1-2: Current (32bit)
                    # 3-4: Power (32bit)
                    # 5-6: Energy (32bit)
                    # 7: Frequency
                    # 8: Power Factor
                    # 9: Alarm Status
                    
                    # Note: read_registers returns list of integers
                    # We can also use read_float/long but bulk read is more efficient
                    
                    # Using read_registers to get raw values then parse
                    
                    # Read 10 registers starting from 0x0000
                    # 0: Voltage (0.1V)
                    # 1: Current Low (0.001A)
                    # 2: Current High
                    # 3: Power Low (0.1W)
                    # 4: Power High
                    # 5: Energy Low (1Wh)
                    # 6: Energy High
                    # 7: Frequency (0.1Hz)
                    # 8: PF (0.01)
                    # 9: Alarm
                    
                    values = self.instrument.read_registers(0x0000, 10, functioncode=4)
                    
                    # Parse values (Little Endian Word Order for 32-bit values per manual)
                    voltage = values[0] * 0.1
                    
                    # Current: High<<16 | Low
                    current_low = values[1]
                    current_high = values[2]
                    current = ((current_high << 16) | current_low) * 0.001
                    
                    # Power: High<<16 | Low
                    power_low = values[3]
                    power_high = values[4]
                    power = ((power_high << 16) | power_low) * 0.1
                    
                    # Energy: High<<16 | Low
                    energy_low = values[5]
                    energy_high = values[6]
                    energy = ((energy_high << 16) | energy_low)
                    
                    frequency = values[7] * 0.1
                    pf = values[8] * 0.01
                    
                    data[address] = {
                        "voltage": round(voltage, 1),
                        "current": round(current, 3),
                        "power": round(power, 1),
                        "energy": energy, # Wh
                        "frequency": round(frequency, 1),
                        "pf": round(pf, 2)
                    }
                    
                except Exception as e:
                    print(f"Error reading sensor {address}: {e}")
                    # Return None or error state?
                    data[address] = None
        return data

    def reset_energy(self, address):
        """
        Resets energy counter for a specific address.
        Function code 0x42 (Spectial for PZEM).
        """
        if self.simulation_mode:
            print(f"[SIM] Energy reset for address {address}")
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

    def _simulate_data(self, address):
        """Generates random data for testing."""
        # Make values slightly different based on address to distinguish phases
        base_v = 230
        base_i = 2 * address # Phase 1=2A, Phase 2=4A...
        
        return {
            "voltage": round(base_v + random.uniform(-5, 5), 1),
            "current": round(base_i + random.uniform(-0.5, 0.5), 3),
            "power": round((base_v * base_i) + random.uniform(-10, 10), 1),
            "energy": int(time.time() // 60), # Just some increasing number
            "frequency": round(50 + random.uniform(-0.1, 0.1), 1),
            "pf": round(0.95 + random.uniform(-0.05, 0.0), 2)
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
