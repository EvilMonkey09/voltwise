from flask import Flask, render_template, jsonify, request
import requests
import sqlite3
import threading
import time
from scanner import scan_network

import sys
import os

app = Flask(__name__)
DB_PATH = 'dashboard.db'

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
    # Nodes table: ip, hostname, last_seen
    c.execute('''CREATE TABLE IF NOT EXISTS nodes 
                 (ip TEXT PRIMARY KEY, hostname TEXT, last_seen REAL, status TEXT)''')
    conn.commit()
    conn.close()

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
        # Upsert
        c.execute("INSERT OR REPLACE INTO nodes (ip, hostname, last_seen, status) VALUES (?, ?, ?, ?)",
                  (node['ip'], node.get('hostname', 'Unknown'), timestamp, 'online'))
        count += 1
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "count": count, "nodes": found_nodes})

@app.route('/api/proxy/<path:ip>/<path:endpoint>')
def proxy_request(ip, endpoint):
    """
    Proxy requests to sensor nodes to avoid mixed content/CORS.
    Example: /api/proxy/192.168.1.50/api/data
    """
    try:
        url = f"http://{ip}:25500/{endpoint}"
        if request.query_string:
            url += f"?{request.query_string.decode('utf-8')}"
            
        resp = requests.get(url, timeout=3)
        return (resp.content, resp.status_code, resp.headers.items())
    except Exception as e:
        return jsonify({"error": str(e)}), 502

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
        
        # --- System Tray & GUI Setup ---
        logging.info("Importing System Tray Libraries...")
        from pystray import Icon as TrayIcon, Menu as TrayMenu, MenuItem as TrayMenuItem
        from PIL import Image
        import webbrowser

        def open_dashboard(icon, item):
            logging.info("Opening Dashboard in Browser...")
            webbrowser.open('http://127.0.0.1:5000')

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
            TrayMenuItem("VoltWise Dashboard", None, enabled=False),
            TrayMenuItem("Open Dashboard", open_dashboard, default=True),
            TrayMenuItem("Quit", quit_app)
        )

        # Create Icon
        logging.info("Creating Tray Icon...")
        icon = TrayIcon("VoltWise", image, "VoltWise Central", menu)

        # Run Flask in Background Thread
        def run_server():
            logging.info("Starting Flask Server on Port 5000...")
            # Disable reloader because it doesn't work well with threads/PyInstaller
            app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

        # Open Browser on Launch
        logging.info("Launching Browser...")
        webbrowser.open('http://127.0.0.1:5000')

        # Run Tray Icon (Block Main Thread)
        logging.info("Running System Tray Loop...")
        icon.run()
        logging.info("System Tray Loop Ended. Exiting.")
        
    except Exception as e:
        logging.error(f"CRITICAL ERROR MAIN: {e}", exc_info=True)


