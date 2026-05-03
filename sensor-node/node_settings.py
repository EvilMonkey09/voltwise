"""Persistent VoltWise Node settings (JSON alongside the app)."""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path

SETTINGS_FILE = Path(__file__).resolve().parent / "node_settings.json"

DEFAULTS = {
    "node_name": "",
    "timezone": "Europe/Berlin",
}


def _path() -> Path:
    return SETTINGS_FILE


def load() -> dict:
    p = _path()
    if not p.exists():
        return dict(DEFAULTS)
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        out = dict(DEFAULTS)
        out.update({k: data[k] for k in DEFAULTS if k in data})
        for k, v in data.items():
            if k not in out:
                out[k] = v
        return out
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)


def save(updates: dict) -> dict:
    current = load()
    for key in ("node_name", "timezone"):
        if key in updates and isinstance(updates[key], str):
            current[key] = updates[key].strip()
    p = _path()
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, p)
    return current


def display_name() -> str:
    s = load().get("node_name") or ""
    if s:
        return s
    try:
        return socket.gethostname() or "VoltWise Node"
    except OSError:
        return "VoltWise Node"


def version_string() -> str:
    return os.environ.get("VOLTWISE_VERSION", "1.1.0")
