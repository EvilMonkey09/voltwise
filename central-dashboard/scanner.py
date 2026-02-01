import socket
import threading
import requests
import ipaddress
import time

PORT = 25500

def get_local_ip():
    try:
        # Dummy connection to determine interface
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def check_ip(ip, results):
    url = f"http://{ip}:{PORT}/api/data"
    try:
        resp = requests.get(url, timeout=0.5)
        if resp.status_code == 200:
            # It's a VoltWise node!
            # Try to get hostname/config if possible, or just use IP
            results.append({"ip": str(ip), "hostname": f"Node {str(ip).split('.')[-1]}"})
    except:
        pass

def scan_network():
    local_ip = get_local_ip()
    if local_ip == "127.0.0.1":
        return []

    # Assume /24 subnet
    network_prefix = ".".join(local_ip.split('.')[:-1])
    
    threads = []
    results = []
    
    # Scan 1-254
    for i in range(1, 255):
        ip = f"{network_prefix}.{i}"
        if ip == local_ip: continue
        
        t = threading.Thread(target=check_ip, args=(ip, results))
        t.start()
        threads.append(t)
        
    # Wait for all
    for t in threads:
        t.join()
        
    return results

if __name__ == "__main__":
    print("Scanning...")
    print(scan_network())
