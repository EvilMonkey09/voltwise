from flask import Flask, render_template, jsonify, request
import time
import threading
import math
import config
from modbus_handler import PZEMHandler
from database_handler import DatabaseHandler

app = Flask(__name__)

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
                    return data.get(addr, {}).get('current', 0.0)
                
                i1 = get_i(config.SENSOR_ADDRESSES[0])
                i2 = get_i(config.SENSOR_ADDRESSES[1])
                i3 = get_i(config.SENSOR_ADDRESSES[2])
                neutral_i = calculate_neutral(i1, i2, i3)

            # Update global state for API
            latest_data = {
                "timestamp": timestamp,
                "sensors": data,
                "neutral_current": neutral_i,
                "event_id": current_event_id
            }
            
            # Log to DB
            db.log_data(data, timestamp, current_event_id, neutral_i)
            
        except Exception as e:
            print(f"Error in poller: {e}")
        
        time.sleep(1)

# Start background thread - MOVED to __main__ to avoid reloader duplication
# poller_thread = threading.Thread(target=background_poller, daemon=True)
# poller_thread.start()

@app.route('/')
def index():
    return render_template('index.html', sensors=config.SENSOR_ADDRESSES)

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
    
    # Headers
    cw.writerow(['Timestamp', 'Voltage (V)', 'Current (A)', 'Power (W)', 'Energy (Wh)', 'Frequency (Hz)', 'PF'])
    
    for log in logs:
        # Assuming sensor 1 for now, but could expand for multiple
        cw.writerow([
            log['timestamp'], 
            log['p1_v'], log['p1_i'], log['p1_p'], log['p1_e'], 
            # Freq/PF might not be logged in DB correctly if schema didn't include them?
            # Checked schema: logs has pX_v, pX_i, pX_p, pX_e. No freq/pf in logs schema.
            # We will just export what we have.
        ])
        
    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={event['name']}.csv"}
    )

if __name__ == '__main__':
    import os
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
        
    app.run(host='0.0.0.0', port=5001, debug=app.debug)
