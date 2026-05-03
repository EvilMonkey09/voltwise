from flask import Flask, render_template, jsonify, request, Response
import logging
import os
import platform
import re
import requests
import socket
import sqlite3
import sys
import threading
import time

from scanner import scan_network

_IPV4 = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")

def get_data_dir():
    """Resolve OS-specific user data directory."""
    app_name = "VoltWise"
    system = platform.system()
    
    if system == "Windows":
        base_path = os.environ.get("APPDATA", os.path.expanduser("~\\AppData\\Roaming"))
    elif system == "Darwin":
        base_path = os.path.expanduser("~/Library/Application Support")
    else: # Linux/Unices
        base_path = os.path.expanduser("~/.local/share")
        
    data_dir = os.path.join(base_path, app_name)
    try:
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
    except Exception:
        # Fallback to /tmp if we can't create the directory
        data_dir = "/tmp"
        
    return data_dir

# --- Setup Data Directory & Logging ---
DATA_DIR = get_data_dir()
DB_PATH = os.path.join(DATA_DIR, 'dashboard.db')
LOG_PATH = os.path.join(DATA_DIR, 'debug.log')

try:
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
except Exception:
    # Fallback logging to stderr
    logging.basicConfig(level=logging.DEBUG)

logging.info(f"Starting VoltWise. Data Directory: {DATA_DIR}")

app = Flask(__name__)

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

if getattr(sys, 'frozen', False):
    # If running as compiled exe, look for templates/static in the temp folder
    app.template_folder = resource_path('templates')
    app.static_folder = resource_path('static')


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS nodes 
                 (ip TEXT PRIMARY KEY, hostname TEXT, last_seen REAL, status TEXT, node_label TEXT)"""
    )
    for col in ("node_label",):
        try:
            c.execute(f"ALTER TABLE nodes ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


def node_health_loop():
    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT ip FROM nodes")
            ips = [row[0] for row in c.fetchall()]
            now = time.time()
            for ip in ips:
                try:
                    r = requests.get(f"http://{ip}:25500/api/data", timeout=2)
                    ok = r.status_code == 200
                except requests.RequestException:
                    ok = False
                c.execute(
                    "UPDATE nodes SET last_seen = ?, status = ? WHERE ip = ?",
                    (now, "online" if ok else "offline", ip),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            logging.exception("node_health_loop: %s", e)
        time.sleep(30)


def start_node_health_monitor():
    t = threading.Thread(target=node_health_loop, daemon=True)
    t.start()

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/api/nodes', methods=['GET'])
def get_nodes():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM nodes")
    rows = c.fetchall()
    nodes = [dict(row) for row in rows]
    conn.close()
    return jsonify(nodes)

@app.route('/api/discover', methods=['POST'])
def discover():
    # Run scan in background or wait? 
    # For better UX, we'll run it synchronously for now (up to few seconds) or return "started"
    # Let's do a quick scan.
    found_nodes = scan_network() 
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    count = 0
    timestamp = time.time()
    for node in found_nodes:
        c.execute(
            """INSERT INTO nodes (ip, hostname, last_seen, status)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(ip) DO UPDATE SET
                 hostname = excluded.hostname,
                 last_seen = excluded.last_seen,
                 status = excluded.status""",
            (node["ip"], node.get("hostname", "Unknown"), timestamp, "online"),
        )
        count += 1
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "count": count, "nodes": found_nodes})

def _proxy_to_node(ip: str, subpath: str):
    if not _IPV4.match(ip or ""):
        return jsonify({"error": "invalid ip"}), 400
    url = f"http://{ip}:25500/{subpath}"
    if request.query_string:
        url += f"?{request.query_string.decode('utf-8')}"
    try:
        resp = requests.get(url, timeout=15, stream=False)
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502
    excluded = {"content-encoding", "content-length", "transfer-encoding", "connection"}
    headers = [(k, v) for k, v in resp.headers.items() if k.lower() not in excluded]
    return Response(resp.content, resp.status_code, headers)


@app.route("/embed/<ip>/", defaults={"subpath": ""})
@app.route("/embed/<ip>/<path:subpath>")
def embed_node(ip, subpath):
    """Proxy VoltWise Node web UI for same-origin iframe embedding."""
    return _proxy_to_node(ip, subpath)


@app.route("/api/proxy/<path:ip>/<path:endpoint>")
def proxy_request(ip, endpoint):
    """Legacy JSON proxy; prefer /embed/ for browser content."""
    return _proxy_to_node(ip, endpoint)


@app.route("/api/nodes/<ip>/label", methods=["PUT"])
def set_node_label(ip):
    data = request.get_json(silent=True) or {}
    label = (data.get("label") or "").strip() or None
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE nodes SET node_label = ? WHERE ip = ?", (label, ip))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/recording/start_all', methods=['POST'])
def start_recording_all():
    data = request.json
    event_name = data.get('name', 'Central Recording')
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT ip FROM nodes WHERE status='online'")
    nodes = c.fetchall()
    conn.close()
    
    results = []
    
    for row in nodes:
        ip = row[0]
        try:
            # 1. Create Event on Node
            create_url = f"http://{ip}:25500/api/events"
            r1 = requests.post(create_url, json={"name": event_name}, timeout=3)
            if r1.status_code == 200:
                event_id = r1.json().get('event_id')
                # 2. Start Recording
                start_url = f"http://{ip}:25500/api/recording/start"
                requests.post(start_url, json={"event_id": event_id}, timeout=3)
                results.append({"ip": ip, "status": "started"})
            else:
                results.append({"ip": ip, "status": "failed_create"})
        except:
            results.append({"ip": ip, "status": "unreachable"})
            
    return jsonify(results)

@app.route('/api/recording/stop_all', methods=['POST'])
def stop_recording_all():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT ip FROM nodes") # Try stopping on all known nodes
    nodes = c.fetchall()
    conn.close()
    
    for row in nodes:
        ip = row[0]
        try:
            requests.post(f"http://{ip}:25500/api/recording/stop", timeout=2)
            requests.post(f"http://{ip}:25500/api/events/stop", timeout=2)
        except:
            pass
    return jsonify({"success": True})

if __name__ == '__main__':
    try:
        logging.info("Initializing Database...")
        init_db()
        start_node_health_monitor()
        
        # --- System Tray & GUI Setup ---
        logging.info("Importing System Tray Libraries...")
        from pystray import Icon as TrayIcon, Menu as TrayMenu, MenuItem as TrayMenuItem
        from PIL import Image
        import webbrowser

        def open_dashboard(icon, item):
            logging.info("Opening Dashboard in Browser...")
            webbrowser.open('http://127.0.0.1:25555')

        def quit_app(icon, item):
            logging.info("Quitting Application...")
            icon.stop()
            os._exit(0)

        # Load Logo
        logo_path = resource_path('logo.png')
        logging.info(f"Loading Logo from: {logo_path}")
        if not os.path.exists(logo_path):
            logging.warning("Logo file NOT found. Using fallback red box.")
            image = Image.new('RGB', (64, 64), color = (255, 0, 0))
        else:
            logging.info("Logo file found.")
            image = Image.open(logo_path)

        # Define Menu
        menu = TrayMenu(
            TrayMenuItem("VoltWise Central", None, enabled=False),
            TrayMenuItem("Open Dashboard", open_dashboard, default=True),
            TrayMenuItem("Quit", quit_app)
        )

        # Create Icon
        logging.info("Creating Tray Icon...")
        icon = TrayIcon("VoltWise", image, "VoltWise Central", menu)

        # Run Flask in Background Thread
        def run_server():
            # Find local IP for display
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(('10.255.255.255', 1))
                local_ip = s.getsockname()[0]
                s.close()
            except Exception:
                local_ip = "127.0.0.1"
                
            logging.info("Starting Flask Server on Port 25555...")
            print(f"\n * VoltWise Central available at: http://{local_ip}:25555\n")

            # Disable reloader because it doesn't work well with threads/PyInstaller
            app.run(host='0.0.0.0', port=25555, debug=False, use_reloader=False)

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

        # Open Browser on Launch
        logging.info("Launching Browser...")
        webbrowser.open('http://127.0.0.1:25555')

        # Run Tray Icon (Block Main Thread)
        logging.info("Running System Tray Loop...")
        icon.run()
        logging.info("System Tray Loop Ended. Exiting.")
        
    except Exception as e:
        logging.error(f"CRITICAL ERROR MAIN: {e}", exc_info=True)


