"""Lightweight EN/DE for VoltWise Central (cookie: voltwise_lang)."""
from __future__ import annotations

from flask import Request

COOKIE_NAME = "voltwise_lang"
LOCALES = frozenset({"en", "de"})

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "browser_title": "VoltWise Central",
        "nav.scan": "Scan network",
        "nav.record_start": "Start recording all",
        "nav.record_stop": "Stop recording all",
        "nav.lang_en": "EN",
        "nav.lang_de": "DE",
        "loading.scanning": "Scanning…",
        "discover.found": "Found {count} VoltWise Node(s).",
        "modal.recording_title": "Recording name",
        "modal.recording_hint": "This event name is sent to every VoltWise Node.",
        "modal.placeholder": "Event name",
        "modal.event_default": "Central event",
        "modal.cancel": "Cancel",
        "modal.start": "Start",
        "upd.title": "Update available",
        "upd.lead": "Installed:",
        "upd.latest": "Latest:",
        "upd.later": "Later",
        "upd.open_release": "Open release page",
        "upd.download": "Download installer",
        "live.sim_banner": "Demo / simulation — synthetic readings, not live PZEM hardware.",
        "live.no_data": "No data",
        "live.sensor_heading": "Sensor / Phase · Addr",
        "live.voltage": "Voltage",
        "live.current": "Current",
        "live.power": "Power",
        "live.energy": "Energy",
        "live.frequency": "Frequency",
        "live.pf": "Power factor",
        "live.neutral": "Neutral current (calc.)",
        "live.offline": "Node offline — no live data.",
        "live.error": "Could not load readings (network or node).",
        "live.loading": "Loading readings…",
        "seen.just_now": "just now",
        "seen.min_ago": "min ago",
        "seen.h_ago": "h ago",
        "grid.ip": "IP",
        "grid.last_seen": "Last seen:",
        "grid.display_placeholder": "Display name",
        "grid.save": "Save",
        "grid.full_ui": "Full node UI",
    },
    "de": {
        "browser_title": "VoltWise Central",
        "nav.scan": "Netzwerk scannen",
        "nav.record_start": "Alle aufnehmen",
        "nav.record_stop": "Aufnahme auf allen stoppen",
        "nav.lang_en": "EN",
        "nav.lang_de": "DE",
        "loading.scanning": "Suche…",
        "discover.found": "{count} VoltWise Node(s) gefunden.",
        "modal.recording_title": "Name der Aufnahme",
        "modal.recording_hint": "Dieser Ereignisname wird an jeden VoltWise Node gesendet.",
        "modal.placeholder": "Ereignisname",
        "modal.event_default": "Central-Aufnahme",
        "modal.cancel": "Abbrechen",
        "modal.start": "Start",
        "upd.title": "Update verfügbar",
        "upd.lead": "Installiert:",
        "upd.latest": "Neueste:",
        "upd.later": "Später",
        "upd.open_release": "Release-Seite öffnen",
        "upd.download": "Installer herunterladen",
        "live.sim_banner": "Demo / Simulation — keine Live-PZEM-Hardware.",
        "live.no_data": "Keine Daten",
        "live.sensor_heading": "Sensor / Phase · Addr",
        "live.voltage": "Spannung",
        "live.current": "Strom",
        "live.power": "Leistung",
        "live.energy": "Energie",
        "live.frequency": "Frequenz",
        "live.pf": "Leistungsfaktor",
        "live.neutral": "Neutralleiterstrom (berechnet)",
        "live.offline": "Node offline — keine Live-Daten.",
        "live.error": "Messwerte konnten nicht geladen werden (Netzwerk oder Node).",
        "live.loading": "Lade Messwerte…",
        "seen.just_now": "gerade eben",
        "seen.min_ago": "Min.",
        "seen.h_ago": "Std.",
        "grid.ip": "IP",
        "grid.last_seen": "Zuletzt gesehen:",
        "grid.display_placeholder": "Anzeigename",
        "grid.save": "Speichern",
        "grid.full_ui": "Volle Node-Oberfläche",
    },
}


def translate(locale: str, key: str) -> str:
    loc = locale if locale in LOCALES else "en"
    if key in STRINGS.get(loc, {}):
        return STRINGS[loc][key]
    return STRINGS["en"].get(key, key)


def resolve_locale(req: Request) -> str:
    c = req.cookies.get(COOKIE_NAME)
    if c in LOCALES:
        return c
    al = (req.headers.get("Accept-Language") or "").lower()
    if al.startswith("de"):
        return "de"
    return "en"


def central_js_strings(locale: str) -> dict[str, str]:
    """Flat dict for window.VW_CENTRAL in dashboard.html."""
    loc = locale if locale in LOCALES else "en"
    keys = [
        "loading.scanning",
        "discover.found",
        "modal.recording_title",
        "modal.placeholder",
        "modal.event_default",
        "modal.recording_hint",
        "live.sim_banner",
        "live.no_data",
        "live.sensor_heading",
        "live.voltage",
        "live.current",
        "live.power",
        "live.energy",
        "live.frequency",
        "live.pf",
        "live.neutral",
        "live.offline",
        "live.error",
        "live.loading",
        "seen.just_now",
        "seen.min_ago",
        "seen.h_ago",
        "grid.ip",
        "grid.last_seen",
        "grid.display_placeholder",
        "grid.save",
        "grid.full_ui",
        "nav.record_start",
        "nav.record_stop",
    ]
    out: dict[str, str] = {}
    for k in keys:
        flat = k.replace(".", "_")
        out[flat] = translate(loc, k)
    return out
