import serial
import time
import sys
import minimalmodbus

# Configuration
SERIAL_PORT = '/dev/ttyAMA0' # Same as your working config

def change_address(new_addr):
    try:
        # Use a broad timeout and the broadcast address (0xF8) or try 1
        # Factory default is usually 1. 0xF8 is the "universal" address but only works if 1 device is connected.
        
        print(f"Connecting to {SERIAL_PORT}...")
        instrument = minimalmodbus.Instrument(SERIAL_PORT, 1) # Default address 1
        instrument.serial.baudrate = 9600
        instrument.serial.timeout = 2
        
        print(f"Attempting to change address to {new_addr}...")
        
        # Register 0x0002 is the Modbus-RTU address
        # We try to write to the generic address 0xF8 so it works regardless of current address
        # BUT minimalmodbus requires us to set the address of the instrument object
        
        # detailed approach:
        # 1. Try generic address connection
        instrument.address = 0xF8 
        
        # Write new address to register 0x0002
        instrument.write_register(0x0002, new_addr, functioncode=6)
        
        print(f"Success! Address changed to {new_addr}.")
        print("Please disconnect this sensor and connect the next one.")
        
    except Exception as e:
        print(f"Error: {e}")
        print("Make sure only ONE sensor is connected.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 set_address.py <new_address>")
        print("Example: python3 set_address.py 2")
        sys.exit(1)
        
    new_addr = int(sys.argv[1])
    if 1 <= new_addr <= 247:
        change_address(new_addr)
    else:
        print("Address must be between 1 and 247")
