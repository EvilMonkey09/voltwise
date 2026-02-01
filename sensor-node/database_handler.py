import sqlite3
import time
import os

DB_NAME = "energy_data.db"

class DatabaseHandler:
    def __init__(self):
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(DB_NAME)

    def init_db(self):
        """Initialize database with tables."""
        conn = self.get_connection()
        c = conn.cursor()
        
        # Events table
        # Stores named time periods (e.g. "Test Run 1")
        c.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            start_time REAL NOT NULL,
            end_time REAL
        )
        ''')
        
        # Logs table
        # Stores raw sensor data. 
        # Structure: timestamp | p1_v | p1_i | p1_p | p1_e | p2_... | p3_... | neutral_i
        # To make it flexible for 1-3 phases, we'll just have columns for 3 phases.
        # Unused phases will be NULL.
        c.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            
            p1_v REAL, p1_i REAL, p1_p REAL, p1_e REAL,
            p2_v REAL, p2_i REAL, p2_p REAL, p2_e REAL,
            p3_v REAL, p3_i REAL, p3_p REAL, p3_e REAL,
            
            neutral_i REAL,
            
            event_id INTEGER,
            FOREIGN KEY(event_id) REFERENCES events(id)
        )
        ''')
        
        conn.commit()
        conn.close()

    def create_event(self, name):
        """Creates a new event and returns its ID."""
        conn = self.get_connection()
        c = conn.cursor()
        start_time = time.time()
        c.execute("INSERT INTO events (name, start_time) VALUES (?, ?)", (name, start_time))
        event_id = c.lastrowid
        conn.commit()
        conn.close()
        return event_id

    def stop_event(self, event_id):
        """Stops an event."""
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("UPDATE events SET end_time = ? WHERE id = ?", (time.time(), event_id))
        conn.commit()
        conn.close()

    def log_data(self, data_dict, timestamp, current_event_id=None, neutral_i=None):
        """
        Logs data to DB.
        data_dict: {1: {...}, 2: {...}, 3: {...}}
        """
        conn = self.get_connection()
        c = conn.cursor()
        
        # Helper to safely get value
        def g(addr, key):
            if addr in data_dict and data_dict[addr]:
                return data_dict[addr].get(key)
            return None

        c.execute('''
        INSERT INTO logs (
            timestamp, event_id,
            p1_v, p1_i, p1_p, p1_e,
            p2_v, p2_i, p2_p, p2_e,
            p3_v, p3_i, p3_p, p3_e,
            neutral_i
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            timestamp, current_event_id,
            g(1, 'voltage'), g(1, 'current'), g(1, 'power'), g(1, 'energy'),
            g(2, 'voltage'), g(2, 'current'), g(2, 'power'), g(2, 'energy'),
            g(3, 'voltage'), g(3, 'current'), g(3, 'power'), g(3, 'energy'),
            neutral_i
        ))
        
        conn.commit()
        conn.close()

    def get_events(self):
        """Returns list of all events."""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM events ORDER BY start_time DESC")
        rows = c.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_event_details(self, event_id):
        """Returns details for a specific event."""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM events WHERE id = ?", (event_id,))
        event = c.fetchone()
        
        # Get duration
        if event:
            event = dict(event)
            end = event['end_time'] if event['end_time'] else time.time()
            event['duration'] = round(end - event['start_time'], 1)
            
            # Get summary stats from logs (e.g. total energy consumed during event)
            # This requires calculating delta between first and last log entry for Energy
            # Or just sum of Powers? Energy meter is cumulative, so Last - First.
            
            # Simple aggregation for now: Count logs
            c.execute("SELECT COUNT(*) as count FROM logs WHERE event_id = ?", (event_id,))
            count = c.fetchone()['count']
            event['log_count'] = count
            
        conn.close()
        return event

    def get_logs(self, event_id=None, limit=100):
        """Get logs, optionally filtered by event."""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        if event_id:
            c.execute("SELECT * FROM logs WHERE event_id = ? ORDER BY timestamp ASC", (event_id,))
        else:
            c.execute("SELECT * FROM logs ORDER BY timestamp DESC LIMIT ?", (limit,))
            # Reverse to get chronological order for charts if needed, but DESC is good for "latest"
            
        rows = c.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def update_event(self, event_id, name):
        """Updates event name."""
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("UPDATE events SET name = ? WHERE id = ?", (name, event_id))
        conn.commit()
        conn.close()

    def delete_event(self, event_id):
        """Deletes an event and its logs."""
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM logs WHERE event_id = ?", (event_id,))
        c.execute("DELETE FROM events WHERE id = ?", (event_id,))
        conn.commit()
        conn.close()

