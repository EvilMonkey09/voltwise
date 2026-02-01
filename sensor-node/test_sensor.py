
import minimalmodbus
import serial
import time
import glob
import sys

def list_serial_ports():
    """Lists serial port names."""
    if sys.platform.startswith('win'):
        ports = ['COM%s' % (i + 1) for i in range(256)]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        # this excludes your current terminal "/dev/tty"
        ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/tty.*')
    else:
        raise EnvironmentError('Unsupported platform')

    result = []
    for port in ports:
        try:
            s = serial.Serial(port)
            s.close()
            result.append(port)
        except (OSError, serial.SerialException):
            pass
    return result

def test_sensor(port, address):
    print(f"Testing port {port} with address {address}...")
    try:
        instrument = minimalmodbus.Instrument(port, address)
        instrument.serial.baudrate = 9600
        instrument.serial.bytesize = 8
        instrument.serial.parity = serial.PARITY_NONE
        instrument.serial.stopbits = 1
        instrument.serial.timeout = 1.0
        instrument.mode = minimalmodbus.MODE_RTU
        instrument.clear_buffers_before_each_transaction = True
        
        # Try to read voltage (register 0x0000)
        print("Attempting to read voltage...")
        voltage = instrument.read_register(0x0000, 1, 4) * 0.1
        print(f"SUCCESS! Voltage: {voltage}V")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False

if __name__ == "__main__":
    print("--- PZEM-004T Diagnostic Tool ---")
    
    print("\nScanning for available serial ports...")
    ports = list_serial_ports()
    print(f"Found ports: {ports}")
    
    # Try the configured port first
    configured_port = '/dev/ttyS0' # Default from config
    addresses = [1]
    
    print(f"\nYour config uses: {configured_port}")
    if configured_port in ports:
        test_sensor(configured_port, addresses[0])
    else:
        print(f"Warning: Configured port {configured_port} not found in available ports list (or is busy).")
        
    print("\nDo you want to try all available ports? (Ctrl+C to stop)")
    time.sleep(2)
    
    for p in ports:
        if "Bluetooth" in p: continue
        print(f"\nChecking {p}...")
        if test_sensor(p, addresses[0]):
            print(f"FOUND SENSOR ON {p}!")
            break
