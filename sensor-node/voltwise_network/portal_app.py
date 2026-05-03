"""Captive portal HTTP server for VoltWise Node setup (port 80)."""
from __future__ import annotations

import threading

from flask import Flask, jsonify, render_template_string, request

from . import nm_helpers

SETUP_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VoltWise — Wi-Fi setup</title>
  <style>
    :root {
      --bg: #f6f7f9;
      --card: #fff;
      --border: #e2e5eb;
      --text: #1a1d24;
      --muted: #5c6370;
      --accent: #2563eb;
      --accent-h: #1d4ed8;
      --danger: #dc2626;
      --radius: 12px;
    }
    * { box-sizing: border-box; }
    body {
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      margin: 0;
      padding: 24px;
      line-height: 1.45;
    }
    .wrap { max-width: 520px; margin: 0 auto; }
    h1 { font-size: 1.35rem; font-weight: 600; margin: 0 0 8px; }
    .sub { color: var(--muted); font-size: 0.9rem; margin-bottom: 24px; }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 20px;
      margin-bottom: 16px;
    }
    label { display: block; font-size: 0.8rem; color: var(--muted); margin-bottom: 6px; }
    input {
      width: 100%;
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 1rem;
      margin-bottom: 14px;
    }
    button {
      background: var(--accent);
      color: #fff;
      border: none;
      padding: 10px 18px;
      border-radius: 8px;
      font-weight: 500;
      cursor: pointer;
      width: 100%;
    }
    button:hover { background: var(--accent-h); }
    button.secondary { background: #fff; color: var(--text); border: 1px solid var(--border); }
    button.secondary:hover { background: var(--bg); }
    .msg { font-size: 0.9rem; margin-top: 12px; }
    .msg.err { color: var(--danger); }
    ul { list-style: none; padding: 0; margin: 0; }
    li {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 0;
      border-bottom: 1px solid var(--border);
      gap: 12px;
    }
    li:last-child { border-bottom: none; }
    .ssid { font-weight: 500; }
    .prio { font-size: 0.75rem; color: var(--muted); }
    .row-btns { display: flex; gap: 8px; flex-shrink: 0; }
    .row-btns button { width: auto; padding: 6px 12px; font-size: 0.85rem; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>VoltWise Node</h1>
    <p class="sub">Connect this device to your Wi-Fi. You can save several networks; they are tried by priority when you move between venues.</p>

    <div class="card">
      <h2 style="font-size:1rem;margin:0 0 16px;">Saved networks</h2>
      <ul id="list"></ul>
      <p id="empty" class="sub" style="display:none;">No networks saved yet.</p>
    </div>

    <div class="card">
      <label for="ssid">Network name (SSID)</label>
      <input id="ssid" autocomplete="off" placeholder="Venue Wi-Fi">
      <label for="pw">Password (leave empty if open)</label>
      <input id="pw" type="password" autocomplete="off" placeholder="Password">
      <button type="button" id="btn-add">Save &amp; connect</button>
      <div id="msg" class="msg"></div>
    </div>
  </div>
  <script>
    async function loadList() {
      const r = await fetch('/api/networks');
      const data = await r.json();
      const ul = document.getElementById('list');
      ul.innerHTML = '';
      document.getElementById('empty').style.display = data.networks.length ? 'none' : 'block';
      data.networks.forEach((n) => {
        const li = document.createElement('li');
        li.innerHTML = `<div><div class="ssid"></div><div class="prio">Priority </div></div><div class="row-btns">
          <button class="secondary up" data-uuid="">↑</button>
          <button class="secondary down" data-uuid="">↓</button>
          <button class="secondary del" data-uuid="">Remove</button></div>`;
        li.querySelector('.ssid').textContent = n.ssid || n.name;
        li.querySelector('.prio').textContent = 'Priority ' + n.priority;
        li.querySelectorAll('button').forEach((b) => b.dataset.uuid = n.uuid);
        li.querySelector('.up').onclick = () => bump(n.uuid, 1);
        li.querySelector('.down').onclick = () => bump(n.uuid, -1);
        li.querySelector('.del').onclick = () => removeNet(n.uuid);
        ul.appendChild(li);
      });
    }
    async function bump(uuid, delta) {
      await fetch('/api/networks/' + uuid + '/priority', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ delta })
      });
      loadList();
    }
    async function removeNet(uuid) {
      if (!confirm('Remove this network?')) return;
      await fetch('/api/networks/' + uuid, { method: 'DELETE' });
      loadList();
    }
    document.getElementById('btn-add').onclick = async () => {
      const msg = document.getElementById('msg');
      msg.textContent = '';
      const ssid = document.getElementById('ssid').value.trim();
      const password = document.getElementById('pw').value;
      if (!ssid) { msg.textContent = 'Enter a network name.'; msg.className = 'msg err'; return; }
      const r = await fetch('/api/add-network', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ ssid, password })
      });
      const j = await r.json();
      if (!j.ok) { msg.textContent = j.error || 'Failed'; msg.className = 'msg err'; return; }
      msg.textContent = 'Saved. This device will reconnect — you may need to rejoin your normal Wi-Fi.';
      msg.className = 'msg';
      document.getElementById('ssid').value = '';
      document.getElementById('pw').value = '';
      loadList();
    };
    loadList();
  </script>
</body>
</html>
"""


def create_app():
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(SETUP_PAGE)

    @app.route("/generate_204")
    def android_captive():
        return ("", 204)

    @app.route("/hotspot-detect.html")
    def apple_captive():
        return ("<!DOCTYPE html><html><head><title>Success</title></head><body>Success</body></html>", 200)

    @app.route("/ncsi.txt")
    def ncsi():
        return "Microsoft NCSI", 200

    @app.route("/connecttest.txt")
    def ms_connecttest():
        return "Microsoft Connect Test", 200

    @app.route("/api/networks", methods=["GET"])
    def api_networks():
        return jsonify({"networks": nm_helpers.list_saved_wifi()})

    @app.route("/api/add-network", methods=["POST"])
    def api_add():
        data = request.get_json(silent=True) or {}
        ssid = (data.get("ssid") or "").strip()
        password = data.get("password") or ""
        if not ssid:
            return jsonify({"ok": False, "error": "SSID required"}), 400
        ok, err = nm_helpers.add_wifi_network(ssid, password if password else None)
        if not ok:
            return jsonify({"ok": False, "error": err}), 400
        return jsonify({"ok": True})

    @app.route("/api/networks/<uuid>", methods=["DELETE"])
    def api_del(uuid):
        ok, err = nm_helpers.delete_connection(uuid)
        if not ok:
            return jsonify({"ok": False, "error": err}), 400
        return jsonify({"ok": True})

    @app.route("/api/networks/<uuid>/priority", methods=["POST"])
    def api_prio(uuid):
        data = request.get_json(silent=True) or {}
        delta = int(data.get("delta") or 0)
        nets = nm_helpers.list_saved_wifi()
        cur = next((n for n in nets if n["uuid"] == uuid), None)
        if not cur:
            return jsonify({"ok": False, "error": "Unknown"}), 404
        new_prio = max(0, cur["priority"] + delta)
        ok, err = nm_helpers.set_priority(uuid, new_prio)
        if not ok:
            return jsonify({"ok": False, "error": err}), 400
        return jsonify({"ok": True})

    return app


def run_portal(host: str = "0.0.0.0", port: int = 80):
    app = create_app()
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


def run_portal_thread(host: str = "0.0.0.0", port: int = 80) -> threading.Thread:
    t = threading.Thread(target=lambda: run_portal(host, port), daemon=True)
    t.start()
    return t
