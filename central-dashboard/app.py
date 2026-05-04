from flask import Flask, render_template, jsonify, request, Response, g, redirect, url_for
from urllib.parse import unquote

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
from pathlib import Path

import i18n
from scanner import scan_network
import voltwise_release_info

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

NODE_PORT = 25500


def fetch_node_info(ip: str) -> dict | None:
    """GET /api/node/info from a VoltWise Node."""
    if not _IPV4.match(ip or ""):
        return None
    try:
        r = requests.get(f"http://{ip}:{NODE_PORT}/api/node/info", timeout=4)
        if r.status_code == 200:
            return r.json()
    except requests.RequestException:
        pass
    return None


def _nodes_columns(conn) -> set[str]:
    c = conn.cursor()
    c.execute("PRAGMA table_info(nodes)")
    return {row[1] for row in c.fetchall()}


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cols = _nodes_columns(conn)
    if not cols:
        conn.cursor().execute(
            """CREATE TABLE nodes (
                node_id TEXT PRIMARY KEY,
                ip TEXT NOT NULL UNIQUE,
                hostname TEXT,
                last_seen REAL,
                status TEXT,
                node_label TEXT,
                remote_name TEXT
            )"""
        )
        conn.commit()
        conn.close()
        return

    if "node_id" not in cols:
        c = conn.cursor()
        c.execute(
            "SELECT ip, hostname, last_seen, status, node_label FROM nodes",
        )
        old_rows = c.fetchall()
        c.execute("DROP TABLE nodes")
        c.execute(
            """CREATE TABLE nodes (
                node_id TEXT PRIMARY KEY,
                ip TEXT NOT NULL UNIQUE,
                hostname TEXT,
                last_seen REAL,
                status TEXT,
                node_label TEXT,
                remote_name TEXT
            )"""
        )
        for row in old_rows:
            ip, hostname, last_seen, status, node_label = (
                row[0],
                row[1] or "",
                row[2],
                row[3] or "offline",
                row[4] if len(row) > 4 else None,
            )
            nid = f"legacy-{ip}"
            c.execute(
                """INSERT INTO nodes (node_id, ip, hostname, last_seen, status, node_label, remote_name)
                   VALUES (?,?,?,?,?,?,?)""",
                (nid, ip, hostname, last_seen, status, node_label, None),
            )
        conn.commit()
    else:
        for col in ("remote_name",):
            try:
                conn.cursor().execute(f"ALTER TABLE nodes ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass
        conn.commit()
    conn.close()


def upsert_node_from_network(
    ip: str,
    hostname_guess: str | None,
    info: dict | None,
    status: str = "online",
) -> None:
    """Insert or update a node; stable key is node_id from the Node."""
    if not _IPV4.match(ip or ""):
        return
    info = info or {}
    nid = (info.get("node_id") or "").strip()
    if not nid:
        nid = f"legacy-{ip}"
    remote = (info.get("display_name") or info.get("node_name") or "").strip()
    host = (hostname_guess or "").strip() or remote or ""

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = time.time()

    c.execute("DELETE FROM nodes WHERE ip = ? AND node_id != ?", (ip, nid))

    legacy = f"legacy-{ip}"
    if nid != legacy:
        c.execute("SELECT node_id FROM nodes WHERE node_id = ?", (legacy,))
        if c.fetchone():
            c.execute("SELECT 1 FROM nodes WHERE node_id = ?", (nid,))
            if c.fetchone():
                c.execute("DELETE FROM nodes WHERE node_id = ?", (nid,))
            row = c.execute(
                "SELECT node_label, hostname FROM nodes WHERE node_id = ?",
                (legacy,),
            ).fetchone()
            preserved_label = row[0] if row else None
            preserved_host = (row[1] if row else "") or host
            c.execute("DELETE FROM nodes WHERE node_id = ?", (legacy,))
            c.execute(
                """INSERT INTO nodes (node_id, ip, hostname, last_seen, status, node_label, remote_name)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(node_id) DO UPDATE SET
                     ip = excluded.ip,
                     hostname = excluded.hostname,
                     last_seen = excluded.last_seen,
                     status = excluded.status,
                     remote_name = excluded.remote_name""",
                (
                    nid,
                    ip,
                    preserved_host or host,
                    now,
                    status,
                    preserved_label,
                    remote or None,
                ),
            )
            conn.commit()
            conn.close()
            return

    c.execute(
        """INSERT INTO nodes (node_id, ip, hostname, last_seen, status, node_label, remote_name)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(node_id) DO UPDATE SET
             ip = excluded.ip,
             hostname = excluded.hostname,
             last_seen = excluded.last_seen,
             status = excluded.status,
             remote_name = excluded.remote_name""",
        (nid, ip, host, now, status, None, remote or None),
    )
    conn.commit()
    conn.close()


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


@app.before_request
def _central_set_locale():
    g.locale = i18n.resolve_locale(request)


@app.context_processor
def _central_i18n_context():
    loc = getattr(g, "locale", "en")

    def _t(key: str) -> str:
        return i18n.translate(loc, key)

    return dict(
        t=_t,
        lang=loc,
        vw_central=i18n.central_js_strings(loc),
    )


@app.route("/set-language/<code>")
def set_language(code):
    code = (code or "").lower()
    if code not in i18n.LOCALES:
        code = "en"
    dest = request.referrer or url_for("index")
    resp = redirect(dest)
    resp.set_cookie(
        i18n.COOKIE_NAME,
        code,
        max_age=365 * 24 * 3600,
        samesite="Lax",
        path="/",
    )
    return resp


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def app_version_string():
    try:
        vf = resource_path("VERSION")
        if os.path.isfile(vf):
            with open(vf, encoding="utf-8") as f:
                v = f.read().strip()
                if v:
                    return v
    except OSError:
        pass
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    return os.environ.get("VOLTWISE_VERSION", "0.0.0")


def central_asset_hint():
    system = platform.system()
    if system == "Windows":
        return {"filename": "VoltWise-Central-Windows-x86_64.exe", "label": "Windows"}
    if system == "Darwin":
        return {"filename": "VoltWise-Central-macOS.dmg", "label": "macOS"}
    return {"filename": "VoltWise-Central-Linux-x86_64", "label": "Linux"}

if getattr(sys, 'frozen', False):
    # If running as compiled exe, look for templates/static in the temp folder
    app.template_folder = resource_path('templates')
    app.static_folder = resource_path('static')


def node_health_loop():
    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT node_id, ip FROM nodes")
            rows = c.fetchall()
            now = time.time()
            for row in rows:
                nid = row["node_id"]
                ip = row["ip"]
                ok = False
                inf = None
                try:
                    r = requests.get(f"http://{ip}:{NODE_PORT}/api/data", timeout=2)
                    ok = r.status_code == 200
                except requests.RequestException:
                    ok = False
                if ok:
                    inf = fetch_node_info(ip)
                    ni = (inf or {}).get("node_id") or ""
                    ni = ni.strip() if isinstance(ni, str) else ""
                    if ni and ni != nid:
                        upsert_node_from_network(ip, None, inf, "online")
                        continue
                remote = None
                new_host = None
                if inf:
                    remote = (
                        (inf.get("display_name") or inf.get("node_name") or "").strip()
                        or None
                    )
                    new_host = remote
                c.execute(
                    """UPDATE nodes SET last_seen = ?, status = ?,
                       remote_name = COALESCE(?, remote_name),
                       hostname = COALESCE(?, hostname)
                       WHERE node_id = ?""",
                    (
                        now,
                        "online" if ok else "offline",
                        remote,
                        new_host,
                        nid,
                    ),
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


@app.route("/api/app/update-status")
def api_app_update_status():
    cache = Path(DATA_DIR) / "update_check_cache.json"
    info = voltwise_release_info.check_cached_or_fetch(app_version_string(), cache)
    hint = central_asset_hint()
    dl_url = None
    if info.get("ok") and info.get("assets"):
        for a in info["assets"]:
            if a.get("name") == hint["filename"]:
                dl_url = a.get("browser_download_url")
                break
    out = dict(info)
    out["recommended_asset"] = hint
    out["recommended_download_url"] = dl_url
    return jsonify(out)


@app.route("/api/nodes", methods=["GET", "POST"])
def api_nodes_list():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        ip = (data.get("ip") or "").strip()
        if not _IPV4.match(ip):
            return jsonify({"ok": False, "error": "invalid_ip"}), 400
        inf = fetch_node_info(ip)
        if not inf:
            return jsonify({"ok": False, "error": "unreachable"}), 502
        upsert_node_from_network(ip, None, inf, "online")
        return jsonify({"ok": True})
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
    found_nodes = scan_network()
    count = 0
    for node in found_nodes:
        ip = node["ip"]
        inf = fetch_node_info(ip) or {}
        if not inf.get("node_id") and node.get("node_id"):
            inf["node_id"] = node["node_id"]
        upsert_node_from_network(ip, node.get("hostname"), inf, "online")
        count += 1
    return jsonify({"success": True, "count": count, "nodes": found_nodes})


@app.route("/api/nodes/<path:nid>", methods=["DELETE"])
def delete_node(nid):
    nid = unquote(nid)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM nodes WHERE node_id = ?", (nid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

def _proxy_to_node(ip: str, subpath: str):
    if not _IPV4.match(ip or ""):
        return jsonify({"error": "invalid ip"}), 400
    url = f"http://{ip}:25500/{subpath}"
    if request.query_string:
        url += f"?{request.query_string.decode('utf-8')}"
    try:
        resp = requests.get(url, timeout=6, stream=False)
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


@app.route("/api/nodes/<path:nid>/label", methods=["PUT"])
def set_node_label(nid):
    nid = unquote(nid)
    data = request.get_json(silent=True) or {}
    label = (data.get("label") or "").strip() or None
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE nodes SET node_label = ? WHERE node_id = ?", (label, nid))
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
            create_url = f"http://{ip}:{NODE_PORT}/api/events"
            r1 = requests.post(create_url, json={"name": event_name}, timeout=3)
            if r1.status_code == 200:
                event_id = r1.json().get('event_id')
                # 2. Start Recording
                start_url = f"http://{ip}:{NODE_PORT}/api/recording/start"
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
            requests.post(f"http://{ip}:{NODE_PORT}/api/recording/stop", timeout=2)
            requests.post(f"http://{ip}:{NODE_PORT}/api/events/stop", timeout=2)
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


