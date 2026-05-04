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
    data_url = f"http://{ip}:{PORT}/api/data"
    try:
        resp = requests.get(data_url, timeout=0.5)
        if resp.status_code != 200:
            return
        label = None
        node_id = ""
        try:
            info = requests.get(f"http://{ip}:{PORT}/api/node/info", timeout=0.35)
            if info.status_code == 200:
                j = info.json()
                label = (j.get("display_name") or j.get("node_name") or "").strip()
                node_id = (j.get("node_id") or "").strip()
        except Exception:
            pass
        if not label:
            label = f"Node {str(ip).split('.')[-1]}"
        results.append({"ip": str(ip), "hostname": label, "node_id": node_id})
    except Exception:
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
