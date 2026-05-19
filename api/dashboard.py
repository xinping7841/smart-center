from datetime import datetime
import time

from flask import Blueprint, jsonify

from auth.decorators import require_permission
from config import CONFIG, DEVICE_STATUS, ENV_STATUS, LIGHT_ONLINE, LIGHT_STATUS
from runtime.state import NVR_STATUS, PROXY_STATUS, SNMP_STATUS, UPS_STATUS


bp = Blueprint("dashboard", __name__)


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _status_level(item):
    payload = item if isinstance(item, dict) else {}
    if payload.get("online") and payload.get("stale"):
        return "stale"
    if payload.get("online"):
        return "online"
    if payload.get("last_error") or payload.get("error"):
        return "error"
    return "offline"


def _counts_from_items(items):
    rows = list(items or [])
    total = len(rows)
    online = 0
    stale = 0
    error = 0
    for item in rows:
        level = _status_level(item)
        if level == "online":
            online += 1
        elif level == "stale":
            online += 1
            stale += 1
        elif level == "error":
            error += 1
    return {
        "total": total,
        "online": online,
        "offline": max(0, total - online),
        "stale": stale,
        "error": error,
    }


def _safe_config_items(key):
    rows = CONFIG.get(key, [])
    return rows if isinstance(rows, list) else []


def _cabinet_snapshot():
    devices = []
    for idx, cfg in enumerate(_safe_config_items("cabinets")):
        status = dict(DEVICE_STATUS.get(idx, {}) or {})
        channels = list(status.get("channels_1_4", []) or [])
        online = bool(status.get("comm_status", False))
        devices.append({
            "id": str(idx),
            "name": cfg.get("cabinet_name") or cfg.get("name") or f"强电柜 {idx + 1}",
            "online": online,
            "status_level": "online" if online else "offline",
            "channel_count": int(cfg.get("channel_count") or len(channels) or 0),
            "channel_on_count": sum(1 for item in channels if bool(item)),
            "realtime_power": status.get("realtime_power"),
            "daily_energy": status.get("daily_energy"),
            "monthly_energy": status.get("monthly_energy"),
            "updated_at": status.get("updated_at"),
        })
    return devices


def _light_snapshot():
    devices = []
    for cfg in _safe_config_items("light_devices"):
        dev_id = str(cfg.get("id"))
        channels = list(LIGHT_STATUS.get(cfg.get("id"), LIGHT_STATUS.get(dev_id, [])) or [])
        online = bool(LIGHT_ONLINE.get(cfg.get("id"), LIGHT_ONLINE.get(dev_id, False)))
        devices.append({
            "id": dev_id,
            "name": cfg.get("name") or dev_id,
            "online": online,
            "status_level": "online" if online else "offline",
            "channel_count": len(channels),
            "channel_on_count": sum(1 for item in channels if bool(item)),
        })
    return devices


def _env_snapshot():
    devices = []
    for cfg in _safe_config_items("env_sensors"):
        dev_id = str(cfg.get("id"))
        state = dict(ENV_STATUS.get(dev_id, {}) or {})
        online = bool(state.get("online"))
        devices.append({
            "id": dev_id,
            "name": cfg.get("name") or dev_id,
            "online": online,
            "status_level": "online" if online else "offline",
            "temp": state.get("temp"),
            "hum": state.get("hum"),
            "lux": state.get("lux"),
            "contact": state.get("contact"),
            "updated_at": state.get("updated_at"),
        })
    return devices


def _ups_snapshot():
    devices = []
    for cfg in _safe_config_items("ups_devices"):
        dev_id = str(cfg.get("id"))
        state = dict(UPS_STATUS.get(dev_id, {}) or {})
        devices.append({
            "id": dev_id,
            "name": cfg.get("name") or dev_id,
            "online": bool(state.get("online")),
            "status_level": _status_level(state),
            "input_voltage": state.get("input_voltage"),
            "output_voltage": state.get("output_voltage"),
            "load_percent": state.get("load_percent"),
            "battery_percent": state.get("battery_percent"),
            "last_success_at": state.get("last_success_at"),
            "last_error": state.get("last_error") or state.get("error"),
        })
    return devices


def _compact_snmp_summary(summary):
    payload = summary if isinstance(summary, dict) else {}
    alert_counts = payload.get("alert_counts")
    if not isinstance(alert_counts, dict):
        alert_counts = {}
    return {
        "device_type": payload.get("device_type"),
        "risk_level": payload.get("risk_level"),
        "health_score": payload.get("health_score"),
        "alert_counts": alert_counts,
        "poll_elapsed_sec": payload.get("poll_elapsed_sec"),
    }


def _snmp_snapshot():
    devices = []
    for cfg in _safe_config_items("snmp_devices"):
        dev_id = str(cfg.get("id"))
        state = dict(SNMP_STATUS.get(dev_id, {}) or {})
        devices.append({
            "id": dev_id,
            "name": cfg.get("name") or dev_id,
            "device_type": cfg.get("device_type"),
            "online": bool(state.get("online")),
            "status_level": _status_level(state),
            "summary": _compact_snmp_summary(state.get("summary", {})),
            "last_success_at": state.get("last_success_at"),
            "last_error": state.get("last_error") or state.get("error"),
        })
    return devices


def _nvr_snapshot():
    devices = []
    for cfg in _safe_config_items("nvr_devices"):
        dev_id = str(cfg.get("id"))
        state = dict(NVR_STATUS.get(dev_id, {}) or {})
        channels = list(state.get("channels", []) or cfg.get("channels", []) or [])
        online_channels = sum(1 for item in channels if bool((item or {}).get("online", True)))
        devices.append({
            "id": dev_id,
            "name": cfg.get("name") or dev_id,
            "online": bool(state.get("online")),
            "status_level": _status_level(state),
            "channel_count": len(channels),
            "online_channel_count": online_channels,
            "last_success_at": state.get("last_success_at"),
            "last_error": state.get("last_error") or state.get("error"),
        })
    return devices


def _sequencer_snapshot():
    try:
        from api.sequencer import SEQUENCER_STATUS, ensure_config_devices

        devices = []
        for seq in ensure_config_devices():
            dev_id = str(seq.get("id"))
            state = dict(SEQUENCER_STATUS.get(dev_id, {}) or {})
            channels = list(state.get("channels", []) or [])
            devices.append({
                "id": dev_id,
                "name": seq.get("name") or dev_id,
                "online": bool(state.get("online")),
                "status_level": _status_level(state),
                "channel_count": int(seq.get("channel_count") or len(channels) or 0),
                "channel_on_count": sum(1 for item in channels if bool(item)),
                "last_success_at": state.get("last_success_at"),
                "last_error": state.get("last_error") or state.get("error"),
            })
        return devices
    except Exception as exc:
        return [{"id": "sequencer_error", "name": "时序电源", "online": False, "status_level": "error", "last_error": str(exc)}]


def _server_snapshot():
    try:
        from api.server import get_cached_machine_payload

        machines = list(get_cached_machine_payload() or [])
    except Exception:
        machines = []
    visible = [item for item in machines if str(item.get("asset_group") or "").strip()]
    visible.sort(key=lambda item: (_server_sort_order(item), str(item.get("mac") or "")))
    return {
        "total": len(visible),
        "online": sum(1 for item in visible if item.get("is_online")),
        "all_total": len(machines),
        "groups": sorted({str(item.get("asset_group") or "").strip() for item in visible if str(item.get("asset_group") or "").strip()}),
        "machines": [_compact_server_machine(item) for item in visible],
    }


def _server_sort_order(item):
    try:
        return int(item.get("sort_order") or 0)
    except (TypeError, ValueError):
        return 0


def _compact_server_gpu_list(raw_list):
    rows = raw_list if isinstance(raw_list, list) else []
    compact = []
    for item in rows[:6]:
        if not isinstance(item, dict):
            continue
        compact.append({
            "index": item.get("index"),
            "name": item.get("name"),
            "temp": item.get("temp"),
            "util_percent": item.get("util_percent"),
            "source": item.get("source"),
        })
    return compact


def _compact_server_machine(item):
    machine = item if isinstance(item, dict) else {}
    status = dict(machine.get("status", {}) or {})
    agent = dict(machine.get("agent_status", {}) or status.get("agent", {}) or {})
    diagnostic = dict(machine.get("diagnostic", {}) or {})
    return {
        "mac": machine.get("mac"),
        "hostname": machine.get("hostname"),
        "custom_name": machine.get("custom_name"),
        "remark": machine.get("remark"),
        "ip": machine.get("ip"),
        "is_online": bool(machine.get("is_online")),
        "asset_group": machine.get("asset_group"),
        "sort_order": machine.get("sort_order"),
        "card_size": machine.get("card_size"),
        "last_online": machine.get("last_online"),
        "diagnostic": {
            "level": diagnostic.get("level"),
            "summary": diagnostic.get("summary"),
            "detail": diagnostic.get("detail"),
            "suggestion": diagnostic.get("suggestion"),
            "has_runtime_metrics": diagnostic.get("has_runtime_metrics"),
            "needs_redeploy": diagnostic.get("needs_redeploy"),
        },
        "agent_status": {
            "task_exists": agent.get("task_exists"),
            "task_state": agent.get("task_state"),
            "version": agent.get("version"),
        },
        "status": {
            "cpu_percent": status.get("cpu_percent"),
            "mem_percent": status.get("mem_percent"),
            "disk_percent": status.get("disk_percent"),
            "hardware_refreshed_at": status.get("hardware_refreshed_at"),
            "gpu_list": _compact_server_gpu_list(status.get("gpu_list")),
        },
    }


def _proxy_snapshot():
    status = dict(PROXY_STATUS.get("default", {}) or {})
    config = dict(status.get("config", {}) or {})
    checks = list(status.get("checks", []) or [])
    required_check = status.get("required_check")
    if not isinstance(required_check, dict):
        required_check = next((item for item in checks if isinstance(item, dict) and item.get("required")), None)
        if required_check is None:
            required_check = next((item for item in checks if isinstance(item, dict) and "google" in str(item.get("name") or item.get("url") or "").lower()), None)
    return {
        "online": bool(status.get("online")),
        "status_level": _status_level(status),
        "host": status.get("host") or config.get("host"),
        "port": status.get("port") or config.get("port"),
        "google_ok": bool(status.get("google_ok") or status.get("checks_ok")),
        "google_latency_ms": status.get("google_latency_ms"),
        "google_status_code": status.get("google_status_code"),
        "healthy_target_count": status.get("healthy_target_count", 0),
        "check_count": status.get("check_count", 0),
        "checks": checks,
        "required_check": required_check or {},
        "traffic": dict(status.get("traffic", {}) or {}),
        "clients": dict(status.get("clients", {}) or {}),
        "updated_at": status.get("updated_at"),
        "last_checked_at": status.get("last_checked_at") or status.get("updated_at"),
        "last_error": status.get("last_error") or status.get("error"),
    }


@bp.route("/api/dashboard/summary")
@require_permission("dashboard.view")
def api_dashboard_summary():
    started = time.monotonic()
    cabinets = _cabinet_snapshot()
    lights = _light_snapshot()
    env = _env_snapshot()
    ups = _ups_snapshot()
    snmp = _snmp_snapshot()
    nvr = _nvr_snapshot()
    sequencers = _sequencer_snapshot()
    servers = _server_snapshot()
    proxy = _proxy_snapshot()
    payload = {
        "ok": True,
        "read_only": True,
        "generated_at": _now_iso(),
        "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
        "counts": {
            "power": _counts_from_items(cabinets),
            "light": _counts_from_items(lights),
            "env": _counts_from_items(env),
            "ups": _counts_from_items(ups),
            "snmp": _counts_from_items(snmp),
            "nvr": _counts_from_items(nvr),
            "sequencer": _counts_from_items(sequencers),
            "server": {key: value for key, value in servers.items() if key != "machines"},
            "proxy": {
                "total": 1,
                "online": 1 if proxy.get("online") else 0,
                "offline": 0 if proxy.get("online") else 1,
                "error": 1 if proxy.get("status_level") == "error" else 0,
                "stale": 1 if proxy.get("status_level") == "stale" else 0,
            },
        },
        "modules": {
            "power": {"devices": cabinets},
            "light": {"devices": lights},
            "env": {"devices": env},
            "ups": {"devices": ups},
            "snmp": {"devices": snmp},
            "nvr": {"devices": nvr},
            "sequencer": {"devices": sequencers},
            "server": servers,
            "proxy": proxy,
        },
    }
    return jsonify(payload)
