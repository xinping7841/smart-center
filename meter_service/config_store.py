import json
import os
import threading
from copy import deepcopy

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_PATH = os.path.join(DATA_DIR, "meter_service_config.json")

DEFAULT_CONFIG = {
    "cabinets": [],
    "meters": [],
    "meter_statistics": {
        "summary_mode": "include_flag",
        "display_reset_enabled": False,
        "display_reset_from": "",
        "energy_display_mode": "display",
        "report_dir": "/data/reports/energy",
        "auto_export_enabled": True,
        "history_keep_days": 90,
        "default_trend_mode": "total",
        "cabinet_gateway_enabled": False,
        "cabinet_gateway_url": "",
        "cabinet_gateway_timeout_sec": 5,
    }
}

_LOCK = threading.Lock()
_CONFIG = None


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_config():
    global _CONFIG
    with _LOCK:
        _ensure_data_dir()
        if _CONFIG is None:
            if os.path.exists(CONFIG_PATH):
                try:
                    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                except Exception:
                    loaded = {}
            else:
                loaded = {}
            merged = deepcopy(DEFAULT_CONFIG)
            merged.update(loaded if isinstance(loaded, dict) else {})
            ms = deepcopy(DEFAULT_CONFIG["meter_statistics"])
            ms.update(merged.get("meter_statistics", {}) or {})
            merged["meter_statistics"] = ms
            _CONFIG = merged
        return deepcopy(_CONFIG)


def save_config(new_config):
    global _CONFIG
    with _LOCK:
        _ensure_data_dir()
        merged = deepcopy(DEFAULT_CONFIG)
        if isinstance(new_config, dict):
            merged.update(new_config)
        ms = deepcopy(DEFAULT_CONFIG["meter_statistics"])
        ms.update(merged.get("meter_statistics", {}) or {})
        merged["meter_statistics"] = ms
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        _CONFIG = merged
        return deepcopy(_CONFIG)
