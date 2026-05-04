"""Captive portal HTTP server for VoltWise Node setup (port 80)."""
from __future__ import annotations

import html
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import Flask, Response, jsonify, redirect, render_template_string, request

from . import nm_helpers

NODE_ROOT = Path(__file__).resolve().parent.parent


def schedule_wifi_handoff(ssid: str) -> None:
    """Run AP teardown + Wi-Fi connect in a detached process (survives portal/service restart)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(NODE_ROOT)
    inner = [sys.executable, "-m", "voltwise_network.handoff", ssid]
    unit = f"voltwise-wifi-handoff-{int(time.time())}"
    cmd = (
        ["systemd-run", f"--unit={unit}", "--collect", "--no-block", *inner]
        if shutil.which("systemd-run")
        else inner
    )
    try:
        subprocess.Popen(
            cmd,
            cwd=str(NODE_ROOT),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        pass


def portal_base_url() -> str:
    """Absolute URL of the sign-in page (required for captive-portal redirects)."""
    gw = os.environ.get("VOLTWISE_CAPTIVE_GATEWAY_IP", "").strip()
    if not gw:
        w = nm_helpers.wifi_iface()
        if w:
            gw = nm_helpers.ipv4_on_device(w) or ""
    if gw:
        return f"http://{gw}/"
    return "http://127.0.0.1/"


def cp_html_portal() -> Response:
    """
    HTTP 200 + HTML redirect — many phones treat 204 on /generate_204 as 'online'
    and ignore 302 for captive detection; a small HTML page triggers the sign-in UI.
    """
    url = html.escape(portal_base_url())
    body = f"""<!DOCTYPE html><html lang="de"><head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0;url={url}">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VoltWise</title></head>
<body style="font-family:system-ui,sans-serif;padding:16px;">
<p>VoltWise WLAN-Einrichtung …</p>
<p><a href="{url}">Weiter</a></p>
</body></html>"""
    return Response(body, mimetype="text/html; charset=utf-8", status=200)


def ms_fake_captive() -> Response:
    """Not the real Microsoft NCSI text → Windows shows captive / sign-in."""
    return Response("VoltWise captive\n", mimetype="text/plain; charset=utf-8", status=200)


SETUP_PAGE = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VoltWise — WLAN</title>
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
      --sig-on: #22c55e;
      --sig-off: #d1d5db;
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
    .sub { color: var(--muted); font-size: 0.9rem; margin-bottom: 16px; }
    .banner {
      background: #fefce8;
      border: 1px solid #fde047;
      border-radius: var(--radius);
      padding: 12px 14px;
      margin-bottom: 16px;
      font-size: 0.9rem;
    }
    .banner code { font-size: 0.85rem; word-break: break-all; background: #fff; padding: 2px 6px; border-radius: 4px; }
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
    button:disabled { opacity: 0.6; cursor: not-allowed; }
    button.secondary { background: #fff; color: var(--text); border: 1px solid var(--border); width: auto; }
    button.secondary:hover { background: var(--bg); }
    .msg { font-size: 0.9rem; margin-top: 12px; white-space: pre-wrap; }
    .msg.err { color: var(--danger); }
    .msg.ok { color: #15803d; }
    .hint { font-size: 0.85rem; color: var(--muted); margin-top: 8px; }
    ul { list-style: none; padding: 0; margin: 0; }
    li.net-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      margin-bottom: 8px;
      cursor: pointer;
      gap: 10px;
    }
    li.net-row:hover { background: var(--bg); }
    li.saved-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 0;
      border-bottom: 1px solid var(--border);
      gap: 12px;
    }
    li.saved-row:last-child { border-bottom: none; }
    .ssid { font-weight: 500; }
    .meta { font-size: 0.75rem; color: var(--muted); }
    .row-btns { display: flex; gap: 8px; flex-shrink: 0; }
    .row-btns button { width: auto; padding: 6px 12px; font-size: 0.85rem; }
    .scan-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
    .scan-head h2 { font-size: 1rem; margin: 0; }
    .sig-bars {
      display: inline-flex;
      align-items: flex-end;
      gap: 3px;
      height: 14px;
      vertical-align: middle;
    }
    .sig-bars span {
      width: 4px;
      border-radius: 1px;
      background: var(--sig-off);
    }
    .sig-bars span:nth-child(1) { height: 5px; }
    .sig-bars span:nth-child(2) { height: 9px; }
    .sig-bars span:nth-child(3) { height: 14px; }
    .sig-bars.on1 span:nth-child(1),
    .sig-bars.on2 span:nth-child(1), .sig-bars.on2 span:nth-child(2),
    .sig-bars.on3 span { background: var(--sig-on); }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>VoltWise Node</h1>
    <p class="sub">Mit dem Heim-WLAN verbinden — Netz wählen oder SSID unten eintragen.</p>

    <div id="banner" class="banner" style="display:none;"></div>

    <div class="card">
      <div class="scan-head">
        <h2>Netze in der Nähe</h2>
        <button type="button" class="secondary" id="btn-scan">Aktualisieren</button>
      </div>
      <p id="scan-hint" class="hint"></p>
      <ul id="scan-list"></ul>
    </div>

    <div class="card">
      <h2 style="font-size:1rem;margin:0 0 16px;">Gespeicherte Netze</h2>
      <ul id="list"></ul>
      <p id="empty" class="sub" style="display:none;">Noch keine Netze gespeichert.</p>
    </div>

    <div class="card">
      <label for="ssid">Netzname (SSID)</label>
      <input id="ssid" autocomplete="off" placeholder="WLAN-Name">
      <label for="pw">Passwort (leer lassen bei offenem WLAN)</label>
      <input id="pw" type="password" autocomplete="off" placeholder="Passwort">
      <button type="button" id="btn-add">Speichern &amp; verbinden</button>
      <div id="msg" class="msg"></div>
    </div>
  </div>
  <script>
    function barsEl(bars) {
      const b = Math.min(3, Math.max(0, parseInt(bars, 10) || 0));
      const cls = b <= 0 ? 'sig-bars' : ('sig-bars on' + b);
      return '<span class="' + cls + '" title="Empfang"><span></span><span></span><span></span></span>';
    }
    async function loadBanner() {
      try {
        const r = await fetch('/api/portal-info');
        const d = await r.json();
        const el = document.getElementById('banner');
        if (d.portal_url) {
          el.style.display = 'block';
          el.innerHTML =
            '<strong>Öffnet sich nicht automatisch?</strong> Browser öffnen und eingeben: <code>' +
            d.portal_url.replace(/</g,'') +
            '</code>';
        }
      } catch (e) {}
    }
    async function loadScan() {
      const hint = document.getElementById('scan-hint');
      const ul = document.getElementById('scan-list');
      hint.textContent = 'Suche …';
      ul.innerHTML = '';
      try {
        const r = await fetch('/api/scan');
        const data = await r.json();
        hint.textContent = data.hint || '';
        (data.networks || []).forEach((n) => {
          const li = document.createElement('li');
          li.className = 'net-row';
          const left = document.createElement('div');
          left.innerHTML = '<div class="ssid"></div><div class="meta"></div>';
          left.querySelector('.ssid').textContent = n.ssid;
          left.querySelector('.meta').textContent = n.security || '—';
          const right = document.createElement('div');
          right.style.display = 'flex';
          right.style.alignItems = 'center';
          right.style.gap = '10px';
          right.innerHTML = barsEl(n.bars != null ? n.bars : (n.signal >= 55 ? 3 : n.signal >= 30 ? 2 : n.signal > 0 ? 1 : 0));
          li.appendChild(left);
          li.appendChild(right);
          li.onclick = () => {
            document.getElementById('ssid').value = n.ssid;
            document.getElementById('pw').value = '';
            document.getElementById('ssid').focus();
          };
          ul.appendChild(li);
        });
      } catch (e) {
        hint.textContent = 'Scan fehlgeschlagen — SSID manuell eintragen.';
      }
    }
    async function loadList() {
      const r = await fetch('/api/networks');
      const data = await r.json();
      const ul = document.getElementById('list');
      ul.innerHTML = '';
      document.getElementById('empty').style.display = data.networks.length ? 'none' : 'block';
      data.networks.forEach((n) => {
        const li = document.createElement('li');
        li.className = 'saved-row';
        li.innerHTML = `<div><div class="ssid"></div><div class="meta"></div></div><div class="row-btns">
          <button type="button" class="secondary up">↑</button>
          <button type="button" class="secondary down">↓</button>
          <button type="button" class="secondary del">Entfernen</button></div>`;
        li.querySelector('.ssid').textContent = n.ssid || n.name;
        li.querySelector('.meta').textContent = 'Priorität ' + n.priority;
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
      if (!confirm('Dieses Netz entfernen?')) return;
      await fetch('/api/networks/' + uuid, { method: 'DELETE' });
      loadList();
    }
    document.getElementById('btn-scan').onclick = () => loadScan();
    document.getElementById('btn-add').onclick = async () => {
      const msg = document.getElementById('msg');
      const btn = document.getElementById('btn-add');
      msg.textContent = '';
      msg.className = 'msg';
      const ssid = document.getElementById('ssid').value.trim();
      const password = document.getElementById('pw').value;
      if (!ssid) {
        msg.textContent = 'Bitte einen Netznamen eingeben.';
        msg.className = 'msg err';
        return;
      }
      btn.disabled = true;
      btn.textContent = 'Bitte warten, verbinde …';
      try {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 130000);
        const r = await fetch('/api/add-network', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ ssid, password }),
          signal: ctrl.signal
        });
        clearTimeout(timer);
        const j = await r.json();
        if (!j.ok) {
          msg.textContent = j.error || 'Fehlgeschlagen.';
          msg.className = 'msg err';
        } else {
          msg.textContent = j.message || 'OK.';
          msg.className = 'msg ok';
          document.getElementById('ssid').value = '';
          document.getElementById('pw').value = '';
          loadList();
        }
      } catch (e) {
        if (e.name === 'AbortError') {
          msg.textContent = 'Zeitüberschreitung — evtl. ist der Pi noch am Verbinden. Kurz warten und Liste prüfen.';
          msg.className = 'msg err';
        } else {
          msg.textContent = 'Anfrage fehlgeschlagen: ' + e;
          msg.className = 'msg err';
        }
      } finally {
        btn.disabled = false;
        btn.textContent = 'Speichern & verbinden';
      }
    };
    loadBanner();
    loadScan();
    loadList();
  </script>
</body>
</html>
"""


def create_app():
    app = Flask(__name__)

    def cp_redirect():
        return redirect(portal_base_url(), code=302)

    @app.route("/")
    def index():
        return render_template_string(SETUP_PAGE)

    @app.route("/api/portal-info", methods=["GET"])
    def api_portal_info():
        gw = os.environ.get("VOLTWISE_CAPTIVE_GATEWAY_IP", "").strip()
        if not gw:
            w = nm_helpers.wifi_iface()
            if w:
                gw = nm_helpers.ipv4_on_device(w) or ""
        url = portal_base_url()
        return jsonify(
            {
                "gateway": gw,
                "portal_url": url,
            }
        )

    @app.route("/generate_204")
    @app.route("/gen_204")
    def android_captive():
        return cp_html_portal()

    @app.route("/hotspot-detect.html")
    def apple_captive():
        return cp_html_portal()

    @app.route("/library/test/success.html")
    def apple_alt():
        return cp_html_portal()

    @app.route("/ncsi.txt")
    def ms_ncsi():
        return ms_fake_captive()

    @app.route("/connecttest.txt")
    def ms_connecttest():
        return ms_fake_captive()

    @app.route("/redirect")
    def samsung_redirect():
        return cp_redirect()

    @app.route("/success.txt")
    def success_txt():
        return cp_html_portal()

    @app.route("/api/networks", methods=["GET"])
    def api_networks():
        return jsonify({"networks": nm_helpers.list_saved_wifi()})

    @app.route("/api/scan", methods=["GET"])
    def api_scan():
        nets, hint = nm_helpers.scan_wifi_networks()
        return jsonify({"networks": nets, "hint": hint})

    @app.route("/api/add-network", methods=["POST"])
    def api_add():
        data = request.get_json(silent=True) or {}
        ssid = (data.get("ssid") or "").strip()
        password = data.get("password") or ""
        if not ssid:
            return jsonify({"ok": False, "error": "SSID fehlt."}), 400
        result = nm_helpers.add_wifi_network_result(ssid, password if password else None)
        if not result.get("ok"):
            return jsonify(result), 400
        if result.get("handoff"):
            schedule_wifi_handoff(ssid)
        return jsonify(result)

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
