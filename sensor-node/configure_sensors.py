#!/usr/bin/env python3
import sys
import time
import glob
import serial
import minimalmodbus
import os
import subprocess
import re

# ANSI Colors
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
RED = '\033[0;31m'
NC = '\033[0m'

def print_header():
    print(f"\n{YELLOW}=== VoltWise Sensor Configuration ==={NC}")

def check_superuser():
    if os.geteuid() != 0:
        print(f"{RED}Error: This script must be run as root/sudo to access serial ports and services.{NC}")
        sys.exit(1)

def stop_service():
    """Checks if service is running and attempts to stop it."""
    service_name = "voltwise.service"
    try:
        # Check status
        result = subprocess.run(["systemctl", "is-active", service_name], capture_output=True, text=True)
        if result.stdout.strip() == "active":
            print(f"{YELLOW}The {service_name} is currently running.{NC}")
            choice = input(f"Stop it to free up the serial port? (Y/n): ").strip().lower()
            if choice == '' or choice == 'y':
                print("Stopping service...")
                subprocess.run(["systemctl", "stop", service_name])
                time.sleep(1)
            else:
                print(f"{RED}Cannot proceed while service is using the port.{NC}")
                sys.exit(1)
    except FileNotFoundError:
        # Systemctl might not exist on non-systemd systems (like Mac dev env)
        pass

def list_serial_ports():
    if sys.platform.startswith('linux'):
        return glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyAMA*') + glob.glob('/dev/ttyACM*')
    elif sys.platform.startswith('darwin'):
        return glob.glob('/dev/tty.*')
    return []

def select_port():
    ports = list_serial_ports()
    if not ports:
        print(f"{RED}No serial ports found!{NC}")
        sys.exit(1)
    
    print("\nAvailable Serial Ports:")
    for i, p in enumerate(ports):
        print(f"[{i+1}] {p}")
        
    choice = input(f"\nSelect port (1-{len(ports)}) [Default: 1]: ").strip()
    if not choice:
        return ports[0]
    
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(ports):
            return ports[idx]
    except ValueError:
        pass
        
    print(f"{RED}Invalid selection.{NC}")
    sys.exit(1)

def get_instrument(port, address):
    try:
        inst = minimalmodbus.Instrument(port, address)
        inst.serial.baudrate = 9600
        inst.serial.timeout = 0.5
        inst.clear_buffers_before_each_transaction = True
        return inst
    except Exception as e:
        print(f"{RED}Error opening port: {e}{NC}")
        sys.exit(1)

def scan_sensors(port):
    print(f"\n{YELLOW}Scanning for sensors on {port}...{NC}")
    found = []
    
    # Try broadcast first (only works if 1 sensor)
    # Actually, broadcast read is not standard Modbus, usually only write.
    # We will scan common addresses 1-10 and factory default 0xF8 (248)
    scan_list = list(range(1, 11)) + [0xF8]
    
    instrument = get_instrument(port, 1)
    
    for addr in scan_list:
        sys.stdout.write(f"\rchecking address {addr}...")
        sys.stdout.flush()
        instrument.address = addr
        try:
            # Try to read voltage (register 0)
            _ = instrument.read_register(0, 1, 4)
            print(f" {GREEN}FOUND!{NC}")
            found.append(addr)
        except Exception:
            pass
            
    print("\n")
    if found:
        print(f"{GREEN}Found sensors at addresses: {found}{NC}")
    else:
        print(f"{RED}No sensors found in range 1-10 or 248.{NC}")
    return found

def wizard_setup(port):
    print_header()
    print("This wizard will help you set up addresses (1, 2, 3...) one by one.")
    print(f"{YELLOW}IMPORTANT: connect only ONE sensor at a time when prompted.{NC}")
    
    count_str = input("\nHow many sensors do you have? (1-3) [3]: ").strip()
    count = int(count_str) if count_str else 3
    
    final_addresses = []
    
    for i in range(1, count + 1):
        target_addr = i
        print(f"\n{YELLOW}--- Step {i}/{count} ---{NC}")
        input(f"Please CONNECT 'Sensor {i}' and DISCONNECT all others.\nPress Enter when ready...")
        
        # Try to find it
        print("Looking for sensor...")
        instrument = get_instrument(port, 1)
        
        # Use simple change technique: Write new address to 0xF8 (Universal) if supported,
        # OR scan and change.
        # PZEM usually responds to 0xF8 for write operations regardless of set address.
        
        found_addr = None
        # Try finding it first to confirm connection
        # We try 0xF8 first as "universal"
        try:
            instrument.address = 0xF8
            # Just read something to check connection, though not all support read on broadcast
            # PZEM V3 might not support read on F8.
            # Let's try to just WRITE the new address to 0xF8 directly.
            print(f"Setting address to {target_addr}...")
            instrument.write_register(0x0002, target_addr, functioncode=6)
            time.sleep(1)
            found_addr = target_addr
            print(f"{GREEN}Address successfully set to {target_addr}.{NC}")
        except Exception:
            print(f"{YELLOW}Broadcast set failed, scanning...{NC}")
            # Scan to find current
            scan_res = scan_sensors(port)
            if not scan_res:
                print(f"{RED}Could not find any connected sensor. Check wiring.{NC}")
                if input("Try again? (y/N) ").lower() == 'y':
                    i -= 1 # Retry
                    continue
                else:
                    return None
            
            # Assuming only 1 connected
            current = scan_res[0]
            print(f"Found sensor at {current}. Changing to {target_addr}...")
            try:
                instrument.address = current
                instrument.write_register(0x0002, target_addr, functioncode=6)
                time.sleep(1)
                print(f"{GREEN}Address changed.{NC}")
            except Exception as e:
                print(f"{RED}Failed to change address: {e}{NC}")
                return None
        
        # Verify
        try:
            instrument.address = target_addr
            v = instrument.read_register(0, 1, 4) * 0.1
            print(f"{GREEN}Verification successful! Voltage reading: {v:.1f}V{NC}")
            final_addresses.append(target_addr)
        except Exception as e:
            print(f"{RED}Verification failed. Sensor might not have updated.{NC}")
            
    print(f"\n{GREEN}All sensors configured! Addresses: {final_addresses}{NC}")
    print("You can now connect all sensors together.")
    return final_addresses

def update_config(port, addresses):
    config_path = 'config.py'
    if not os.path.exists(config_path):
        print(f"{RED}config.py not found.{NC}")
        return

    print(f"\nUpdating {config_path}...")
    try:
        with open(config_path, 'r') as f:
            content = f.read()
            
        # Replace port
        content = re.sub(r"SERIAL_PORT\s*=\s*['\"].*['\"]", f"SERIAL_PORT = '{port}'", content)
        # Replace addresses
        content = re.sub(r"SENSOR_ADDRESSES\s*=\s*\[.*\]", f"SENSOR_ADDRESSES = {addresses}", content)
        
        with open(config_path, 'w') as f:
            f.write(content)
        print(f"{GREEN}Configuration updated.{NC}")
    except Exception as e:
        print(f"{RED}Error updating config: {e}{NC}")

def main():
    print_header()
    check_superuser()
    stop_service()
    
    port = select_port()
    
    print("\nOptions:")
    print("1. Scan for devices")
    print("2. Setup Wizard (Configure addresses 1, 2, 3... one by one)")
    
    choice = input("\nChoose option (1/2): ").strip()
    
    if choice == '1':
        scan_sensors(port)
    elif choice == '2':
        addrs = wizard_setup(port)
        if addrs:
            save = input("\nUpdate config.py with these settings? (Y/n): ").strip().lower()
            if save == '' or save == 'y':
                update_config(port, addrs)
                print(f"{YELLOW}Don't forget to restart the service: sudo systemctl start voltwise{NC}")
    
if __name__ == "__main__":
    main()
