from flask import Flask, render_template, jsonify, request, g, redirect, url_for
import math
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import i18n
import config
import node_settings
import voltwise_release_info
from database_handler import DatabaseHandler
from modbus_handler import PZEMHandler

_UPDATE_CACHE = Path(__file__).resolve().parent / ".update_check_cache.json"
_OTA_SCRIPT = "/usr/local/sbin/voltwise-apply-update.sh"
_OTA_DIR_FILE = "/etc/voltwise/sensor_node_dir"

app = Flask(__name__)


@app.before_request
def _set_locale():
    g.locale = i18n.resolve_locale(request)


@app.context_processor
def _i18n_context():
    loc = getattr(g, "locale", "en")

    def _t(key: str) -> str:
        return i18n.translate(loc, key)

    return dict(
        t=_t,
        lang=loc,
        vw_js=i18n.client_strings(loc),
        vw_settings=i18n.settings_js_strings(loc),
        vw_event=i18n.event_client_strings(loc),
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


# Global State
latest_data = {}
current_event_id = None
db = DatabaseHandler()
pzem = PZEMHandler(config.SERIAL_PORT, config.SENSOR_ADDRESSES)

def calculate_neutral(i1, i2, i3):
    """
    Calculates Neutral Current for 3-phase system assuming 120 degree shift.
    Formula: sqrt(i1^2 + i2^2 + i3^2 - (i1*i2 + i2*i3 + i3*i1))
    """
    try:
        val = (i1**2 + i2**2 + i3**2) - (i1*i2 + i2*i3 + i3*i1)
        # Floating point precision might make val slightly negative in balanced zero case
        return round(math.sqrt(max(0, val)), 3)
    except Exception:
        return 0.0

def background_poller():
    global latest_data, current_event_id
    while True:
        try:
            timestamp = time.time()
            data = pzem.read_all()
            
            # Calculate Neutral if 3 phases
            neutral_i = 0.0
            if len(config.SENSOR_ADDRESSES) == 3:
                # Helper to get currentsafely
                def get_i(addr):
                    d = data.get(addr)
                    if not d:
                        return 0.0
                    return d.get("current", 0.0)
                
                i1 = get_i(config.SENSOR_ADDRESSES[0])
                i2 = get_i(config.SENSOR_ADDRESSES[1])
                i3 = get_i(config.SENSOR_ADDRESSES[2])
                neutral_i = calculate_neutral(i1, i2, i3)

            # Update global state for API
            latest_data = {
                "timestamp": timestamp,
                "sensors": data,
                "neutral_current": neutral_i,
                "event_id": current_event_id,
                "simulation": pzem.simulation_mode,
            }
            
            # Log to DB
            db.log_data(data, timestamp, current_event_id, neutral_i)
            
        except Exception as e:
            print(f"Error in poller: {e}")
        
        time.sleep(1)

# Start background thread - MOVED to __main__ to avoid reloader duplication
# poller_thread = threading.Thread(target=background_poller, daemon=True)
# poller_thread.start()

def _nm_helpers():
    if sys.platform != "linux":
        return None
    try:
        from voltwise_network import nm_helpers

        if not nm_helpers.nmcli_available():
            return None
        return nm_helpers
    except Exception:
        return None


@app.route("/")
def index():
    return render_template(
        "index.html",
        sensors=config.SENSOR_ADDRESSES,
        node_display_name=node_settings.display_name(),
    )


@app.route("/settings")
def settings_page():
    return render_template(
        "settings.html",
        settings=node_settings.load(),
        display_name=node_settings.display_name(),
    )


@app.route("/api/node/info")
def api_node_info():
    s = node_settings.load()
    return jsonify(
        {
            "node_name": s.get("node_name") or "",
            "display_name": node_settings.display_name(),
            "hostname": socket.gethostname(),
            "timezone": s.get("timezone") or "Europe/Berlin",
            "version": node_settings.version_string(),
            "serial_port": config.SERIAL_PORT,
            "sensor_addresses": config.SENSOR_ADDRESSES,
            "simulation": getattr(pzem, "simulation_mode", False),
        }
    )


@app.route("/api/settings", methods=["GET", "PUT"])
def api_settings():
    if request.method == "GET":
        return jsonify(node_settings.load())
    data = request.get_json(silent=True) or {}
    saved = node_settings.save(data)
    return jsonify(saved)


@app.route("/api/network/status")
def api_network_status():
    nm = _nm_helpers()
    if not nm:
        return jsonify(
            {
                "available": False,
                "online": None,
                "message": "Network management is only available on the Raspberry Pi with NetworkManager.",
            }
        )
    try:
        online = nm.has_real_connectivity()
        profiles = nm.list_saved_wifi()
        return jsonify({"available": True, "online": online, "profiles": profiles})
    except Exception as e:
        return jsonify({"available": True, "error": str(e)}), 500


@app.route("/api/network/connect", methods=["POST"])
def api_network_connect():
    nm = _nm_helpers()
    if not nm:
        return jsonify({"ok": False, "error": "Not available on this platform"}), 400
    data = request.get_json(silent=True) or {}
    ssid = (data.get("ssid") or "").strip()
    password = data.get("password") or ""
    if not ssid:
        return jsonify({"ok": False, "error": "SSID required"}), 400
    ok, err = nm.add_wifi_network(ssid, password if password else None)
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True})


@app.route("/api/network/profile/<uuid>", methods=["DELETE"])
def api_network_delete(uuid):
    nm = _nm_helpers()
    if not nm:
        return jsonify({"ok": False}), 400
    ok, err = nm.delete_connection(uuid)
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True})


@app.route("/api/network/profile/<uuid>/priority", methods=["POST"])
def api_network_priority(uuid):
    nm = _nm_helpers()
    if not nm:
        return jsonify({"ok": False}), 400
    data = request.get_json(silent=True) or {}
    delta = int(data.get("delta") or 0)
    nets = nm.list_saved_wifi()
    cur = next((n for n in nets if n["uuid"] == uuid), None)
    if not cur:
        return jsonify({"ok": False, "error": "Unknown"}), 404
    new_prio = max(0, cur["priority"] + delta)
    ok, err = nm.set_priority(uuid, new_prio)
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True})


@app.route('/api/data')
def get_data():
    return jsonify(latest_data)

@app.route('/api/reset', methods=['POST'])
def reset_energy():
    # Only allow reset if monitoring inactive? Or just do it.
    # PZEM reset clears the internal counter.
    try:
        data = request.json
        address = data.get('address')
        if address:
            success = pzem.reset_energy(int(address))
            return jsonify({"success": success})
        return jsonify({"error": "No address provided"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Event Management Routes ---

@app.route('/api/events', methods=['GET', 'POST'])
def handle_events():
    if request.method == 'GET':
        events = db.get_events()
        # Add "active" flag if it matches current_event_id
        for e in events:
            e['is_active'] = (e['id'] == current_event_id)
        return jsonify(events)
        
    if request.method == 'POST':
        # Create new event without starting recording automatically
        data = request.json
        name = data.get('name', 'Untitled Event')
        event_id = db.create_event(name)
        return jsonify({"success": True, "event_id": event_id})

@app.route('/api/recording/start', methods=['POST'])
def start_recording():
    global current_event_id
    data = request.json
    event_id = data.get('event_id')
    
    if not event_id:
        return jsonify({"error": "Event ID required"}), 400
        
    # Verify event exists
    event = db.get_event_details(event_id)
    if not event:
        return jsonify({"error": "Event not found"}), 404
        
    current_event_id = int(event_id)
    return jsonify({"success": True})

@app.route('/api/recording/stop', methods=['POST'])
def stop_recording():
    global current_event_id
    current_event_id = None
    return jsonify({"success": True})
    
@app.route('/api/recording/status')
def recording_status():
    return jsonify({"recording": current_event_id is not None, "event_id": current_event_id})

@app.route('/api/events/stop', methods=['POST'])
def stop_event():
    global current_event_id
    if not current_event_id:
        return jsonify({"error": "No event in progress"}), 400
        
    db.stop_event(current_event_id)
    current_event_id = None
    return jsonify({"success": True})

@app.route('/api/events')
def list_events():
    events = db.get_events()
    return jsonify(events)

@app.route('/events/<int:event_id>')
def view_event(event_id):
    return render_template('event_detail.html', event_id=event_id)

@app.route('/api/history')
def get_history():
    # Get last N records (e.g. 500) for live charts
    # We can reuse get_logs with a limit
    limit = request.args.get('limit', 500)
    try:
        limit = int(limit)
    except:
        limit = 500
    logs = db.get_logs(limit=limit)
    # Sort by timestamp ascending for charts
    logs.reverse()
    return jsonify(logs)

@app.route('/api/events/<int:event_id>', methods=['GET', 'PUT', 'DELETE'])
def manage_event(event_id):
    if request.method == 'GET':
        details = db.get_event_details(event_id)
        logs = db.get_logs(event_id)
        return jsonify({"details": details, "logs": logs})
        
    if request.method == 'PUT':
        data = request.json
        name = data.get('name')
        if not name:
            return jsonify({"error": "Name required"}), 400
        db.update_event(event_id, name)
        return jsonify({"success": True})
        
    if request.method == 'DELETE':
        db.delete_event(event_id)
        return jsonify({"success": True})

@app.route('/api/events/<int:event_id>/export')
def export_event_csv(event_id):
    import csv
    import io
    from flask import Response
    
    event = db.get_event_details(event_id)
    logs = db.get_logs(event_id)
    
    if not event:
        return "Event not found", 404
        
    # Generate CSV
    si = io.StringIO()
    cw = csv.writer(si)
    
    cw.writerow([
        'Timestamp',
        'P1_V', 'P1_A', 'P1_W', 'P1_Wh', 'P1_Hz', 'P1_PF',
        'P2_V', 'P2_A', 'P2_W', 'P2_Wh', 'P2_Hz', 'P2_PF',
        'P3_V', 'P3_A', 'P3_W', 'P3_Wh', 'P3_Hz', 'P3_PF',
        'Neutral_I_A',
    ])

    for log in logs:
        cw.writerow([
            log['timestamp'],
            log.get('p1_v'), log.get('p1_i'), log.get('p1_p'), log.get('p1_e'),
            log.get('p1_hz'), log.get('p1_pf'),
            log.get('p2_v'), log.get('p2_i'), log.get('p2_p'), log.get('p2_e'),
            log.get('p2_hz'), log.get('p2_pf'),
            log.get('p3_v'), log.get('p3_i'), log.get('p3_p'), log.get('p3_e'),
            log.get('p3_hz'), log.get('p3_pf'),
            log.get('neutral_i'),
        ])
        
    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={event['name']}.csv"}
    )


@app.route("/api/update/status")
def api_update_status():
    info = voltwise_release_info.check_cached_or_fetch(
        node_settings.version_string(), _UPDATE_CACHE
    )
    info["can_apply_zip"] = os.path.isfile(_OTA_SCRIPT) and os.path.isfile(_OTA_DIR_FILE)
    return jsonify(info)


@app.route("/api/update/apply", methods=["POST"])
def api_update_apply():
    data = request.get_json(silent=True) or {}
    if not data.get("confirm"):
        return jsonify({"ok": False, "error": "confirm required"}), 400
    st = voltwise_release_info.check_cached_or_fetch(
        node_settings.version_string(),
        _UPDATE_CACHE,
        max_age_seconds=120,
    )
    if not st.get("ok") or not st.get("update_available"):
        return jsonify({"ok": False, "error": "No update available"}), 400
    if not os.path.isfile(_OTA_SCRIPT):
        return jsonify(
            {
                "ok": False,
                "error": "OTA script missing — run install.sh once or see SETUP_GUIDE.",
            }
        ), 503
    try:
        r = subprocess.run(
            ["sudo", "-n", _OTA_SCRIPT, "latest"],
            capture_output=True,
            text=True,
            timeout=900,
        )
        return jsonify(
            {
                "ok": r.returncode == 0,
                "stdout": r.stdout[-8000:],
                "stderr": r.stderr[-8000:],
                "code": r.returncode,
            }
        )
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Update timed out"}), 500
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "sudo not available"}), 500


if __name__ == '__main__':
    # Initialize DB (create tables)
    db.init_db()
    
    # Configure debug mode here so we can check it reliably
    app.debug = True
    
    # ONLY start the background poller if we are in the reloader child process
    # or if the reloader is not being used.
    # When debug=True, the reloader is used. The parent process (WERKZEUG_RUN_MAIN not set)
    # just manages the child. The child process (WERKZEUG_RUN_MAIN='true') runs the app code.
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        print("Starting background poller thread...")
        poller_thread = threading.Thread(target=background_poller, daemon=True)
        poller_thread.start()
        
    app.run(host='0.0.0.0', port=25500, debug=app.debug)
