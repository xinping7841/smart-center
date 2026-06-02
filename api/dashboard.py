# AI_MODULE: dashboard_api
# AI_PURPOSE: 为首页提供轻量总览摘要，聚合各模块在线数、告警数和快速状态。
# AI_BOUNDARY: 不直接轮询硬件；只读取 CONFIG 和 runtime/cache 中已有状态。
# AI_DATA_FLOW: runtime.state/CONFIG -> /api/dashboard/summary -> static/js/views/dashboard-summary.js。
# AI_RUNTIME: 首页加载和定时刷新调用，必须保持快速返回。
# AI_RISK: 中，接口慢会拖慢主页；字段变化会影响首页统计和底部状态栏。
# AI_COMPAT: /api/dashboard/summary 的 ok/counts/modules 字段需保持兼容。
# AI_SEARCH_KEYWORDS: dashboard, summary, counts, modules, home overview.

from datetime import datetime
from copy import deepcopy
import threading
import time

from flask import Blueprint, jsonify

from auth.decorators import require_permission
from config import CONFIG, DEVICE_STATUS, ENV_STATUS, LIGHT_ONLINE, LIGHT_STATUS
from data_logger import load_logs
from runtime.state import PROJECTOR_STATUS, PROXY_STATUS, SCREEN_STATUS, SNMP_STATUS, UPS_STATUS


bp = Blueprint("dashboard", __name__)
_DASHBOARD_SUMMARY_CACHE = {"payload": None, "ts": 0.0}
_DASHBOARD_SUMMARY_CACHE_LOCK = threading.Lock()
_DASHBOARD_SUMMARY_CACHE_TTL_SEC = 2.0


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


def _compact_operation_log(item):
    payload = item if isinstance(item, dict) else {}
    return {
        "time": payload.get("time"),
        "cab_idx": payload.get("cab_idx"),
        "operation": payload.get("operation") or payload.get("msg") or "",
        "category": payload.get("category"),
        "status": payload.get("status"),
    }


def _recent_logs_snapshot(limit=36):
    try:
        rows = load_logs(None)
    except Exception:
        rows = []
    if not isinstance(rows, list):
        rows = []
    rows.sort(key=lambda item: str((item or {}).get("time") or ""), reverse=True)
    return [_compact_operation_log(item) for item in rows[: max(1, min(int(limit or 36), 80))]]


def _door_snapshot():
    try:
        from api.door import DOOR_STATUS_TEXT, camera_states, door_status_info, status_lock

        with status_lock:
            state = dict(door_status_info)
        cameras = [dict(item) for item in (camera_states or {}).values()]
        status_value = str(state.get("transition_status") or state.get("current_status") or "unknown")
        text = DOOR_STATUS_TEXT.get(status_value, status_value or "状态未知")
        return {
            "online": bool(state.get("updated_at")),
            "status_level": "online" if state.get("updated_at") else "stale",
            "status": status_value,
            "text": text,
            "confidence": state.get("confidence"),
            "engine": state.get("engine"),
            "detection_camera": state.get("detection_camera"),
            "people_count": state.get("people_count"),
            "updated_at": state.get("updated_at"),
            "camera_total": len(cameras),
            "camera_online": sum(1 for item in cameras if item.get("online")),
        }
    except Exception as exc:
        return {
            "online": False,
            "status_level": "error",
            "status": "unknown",
            "text": "门禁状态读取失败",
            "camera_total": 0,
            "camera_online": 0,
            "last_error": str(exc),
        }


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


def _projector_snapshot():
    devices = []
    for cfg in _safe_config_items("projectors"):
        dev_id = str(cfg.get("id"))
        state = dict(PROJECTOR_STATUS.get(dev_id, {}) or {})
        online = bool(state.get("online"))
        devices.append({
            "id": dev_id,
            "name": cfg.get("name") or dev_id,
            "online": online,
            "status_level": state.get("status_level") or _status_level(state),
            "power": state.get("power") or "unknown",
            "source": state.get("source_name") or state.get("source"),
            "ip": cfg.get("ip"),
            "last_success_at": state.get("last_success_at") or state.get("updated_at"),
            "last_error": state.get("last_error") or state.get("error"),
        })
    return devices


def _screen_snapshot():
    devices = []
    for cfg in _safe_config_items("screens"):
        dev_id = str(cfg.get("id"))
        state = dict(SCREEN_STATUS.get(dev_id, {}) or {})
        online = bool(state.get("online"))
        devices.append({
            "id": dev_id,
            "name": cfg.get("name") or dev_id,
            "online": online,
            "status_level": state.get("status_level") or _status_level(state),
            "position": state.get("position"),
            "height": state.get("height"),
            "action": state.get("action"),
            "is_moving": bool(state.get("is_moving")),
            "remaining_time": state.get("remaining_time"),
            "last_success_at": state.get("last_success_at") or state.get("last_checked_at"),
            "last_error": state.get("last_error") or state.get("error"),
        })
    return devices


def _automation_snapshot():
    try:
        from runtime.automation import get_automation_runtime_snapshot

        snapshot = get_automation_runtime_snapshot()
    except Exception as exc:
        return {
            "total": 0,
            "enabled": 0,
            "error": 1,
            "rules": [],
            "last_error": str(exc),
        }
    rules = list(snapshot.get("rules", []) if isinstance(snapshot, dict) else [])
    compact_rules = []
    for rule in rules[:16]:
        if not isinstance(rule, dict):
            continue
        compact_rules.append({
            "id": rule.get("id"),
            "name": rule.get("name"),
            "enabled": bool(rule.get("enabled")),
            "last_result": rule.get("last_result"),
            "last_evaluated_at": rule.get("last_evaluated_at"),
            "error": rule.get("error") or rule.get("last_error"),
        })
    return {
        "total": len(rules),
        "enabled": sum(1 for item in rules if item.get("enabled")),
        "error": sum(1 for item in rules if item.get("error") or item.get("last_error")),
        "server_time": snapshot.get("server_time") if isinstance(snapshot, dict) else None,
        "rules": compact_rules,
    }


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
    runtime_fresh = machine.get("runtime_fresh")
    if runtime_fresh is None:
        runtime_fresh = diagnostic.get("runtime_fresh")
    report_online = machine.get("report_online")
    if report_online is None:
        report_online = diagnostic.get("report_online")
    return {
        "mac": machine.get("mac"),
        "hostname": machine.get("hostname"),
        "custom_name": machine.get("custom_name"),
        "remark": machine.get("remark"),
        "ip": machine.get("ip"),
        "is_online": bool(machine.get("is_online")),
        "report_online": bool(report_online),
        "runtime_fresh": bool(runtime_fresh),
        "agent_heartbeat_online": bool(machine.get("agent_heartbeat_online") or diagnostic.get("agent_heartbeat_online")),
        "ping_online": machine.get("ping_online"),
        "asset_group": machine.get("asset_group"),
        "sort_order": machine.get("sort_order"),
        "card_size": machine.get("card_size"),
        "last_online": machine.get("last_online"),
        "server_received_at": machine.get("server_received_at"),
        "client_reported_at": machine.get("client_reported_at"),
        "clock_offset_sec": machine.get("clock_offset_sec"),
        "last_report_kind": machine.get("last_report_kind") or diagnostic.get("last_report_kind") or status.get("last_report_kind"),
        "diagnostic": {
            "level": diagnostic.get("level"),
            "code": diagnostic.get("code"),
            "summary": diagnostic.get("summary"),
            "detail": diagnostic.get("detail"),
            "root_cause": diagnostic.get("root_cause"),
            "suggestion": diagnostic.get("suggestion"),
            "log_excerpt": diagnostic.get("log_excerpt"),
            "has_runtime_metrics": diagnostic.get("has_runtime_metrics"),
            "report_online": bool(report_online),
            "runtime_fresh": bool(runtime_fresh),
            "agent_heartbeat_online": bool(machine.get("agent_heartbeat_online") or diagnostic.get("agent_heartbeat_online")),
            "last_report_kind": diagnostic.get("last_report_kind") or machine.get("last_report_kind") or status.get("last_report_kind"),
            "needs_redeploy": diagnostic.get("needs_redeploy"),
        },
        "agent_status": {
            "task_exists": agent.get("task_exists"),
            "task_state": agent.get("task_state"),
            "version": agent.get("version"),
            "updated_at": agent.get("updated_at"),
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


def _local_model_snapshot():
    try:
        from api.local_model import normalize_local_model_config

        cfg = normalize_local_model_config(CONFIG.get("local_model"), keep_secret=False)
    except Exception:
        cfg = {}
    cloud = cfg.get("cloud_model") if isinstance(cfg.get("cloud_model"), dict) else {}
    nl = cfg.get("natural_language") if isinstance(cfg.get("natural_language"), dict) else {}
    training = cfg.get("training_export") if isinstance(cfg.get("training_export"), dict) else {}
    priority = str(cloud.get("priority") or "local_first").strip() or "local_first"
    return {
        "enabled": bool(cfg.get("enabled")),
        "name": cfg.get("name"),
        "provider": cfg.get("provider"),
        "model": cfg.get("model"),
        "base_url": cfg.get("base_url"),
        "max_model_len": cfg.get("max_model_len"),
        "training_export_enabled": bool(training.get("enabled")),
        "cloud_enabled": bool(cloud.get("enabled")),
        "cloud_provider": cloud.get("provider"),
        "cloud_model": cloud.get("model"),
        "cloud_priority": priority,
        "compare_with_local": bool(cloud.get("compare_with_local")),
        "feishu_control_enabled": bool(nl.get("feishu_control_enabled")),
        "feishu_require_confirmation": bool(nl.get("feishu_control_require_confirmation")),
        "record_process_enabled": bool(nl.get("record_process_enabled", True)),
    }


@bp.route("/api/dashboard/summary")
@require_permission("dashboard.view")
def api_dashboard_summary():
    now = time.monotonic()
    with _DASHBOARD_SUMMARY_CACHE_LOCK:
        cached_payload = _DASHBOARD_SUMMARY_CACHE.get("payload")
        cached_ts = float(_DASHBOARD_SUMMARY_CACHE.get("ts") or 0.0)
        cache_age = now - cached_ts if cached_ts else 0.0
        if isinstance(cached_payload, dict) and cache_age <= _DASHBOARD_SUMMARY_CACHE_TTL_SEC:
            payload = deepcopy(cached_payload)
            payload["cache_hit"] = True
            payload["cache_age_sec"] = round(max(0.0, cache_age), 2)
            return jsonify(payload)

    started = time.monotonic()
    cabinets = _cabinet_snapshot()
    lights = _light_snapshot()
    env = _env_snapshot()
    ups = _ups_snapshot()
    snmp = _snmp_snapshot()
    sequencers = _sequencer_snapshot()
    projectors = _projector_snapshot()
    screens = _screen_snapshot()
    automation = _automation_snapshot()
    servers = _server_snapshot()
    proxy = _proxy_snapshot()
    local_model = _local_model_snapshot()
    door = _door_snapshot()
    logs = _recent_logs_snapshot()
    payload = {
        "ok": True,
        "read_only": True,
        "cache_hit": False,
        "cache_age_sec": 0.0,
        "generated_at": _now_iso(),
        "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
        "counts": {
            "power": _counts_from_items(cabinets),
            "light": _counts_from_items(lights),
            "env": _counts_from_items(env),
            "ups": _counts_from_items(ups),
            "snmp": _counts_from_items(snmp),
            "sequencer": _counts_from_items(sequencers),
            "projector": _counts_from_items(projectors),
            "screen": _counts_from_items(screens),
            "server": {key: value for key, value in servers.items() if key != "machines"},
            "automation": {
                "total": automation.get("total", 0),
                "online": automation.get("enabled", 0),
                "offline": max(0, int(automation.get("total", 0) or 0) - int(automation.get("enabled", 0) or 0)),
                "error": automation.get("error", 0),
                "stale": 0,
                "enabled": automation.get("enabled", 0),
            },
            "proxy": {
                "total": 1,
                "online": 1 if proxy.get("online") else 0,
                "offline": 0 if proxy.get("online") else 1,
                "error": 1 if proxy.get("status_level") == "error" else 0,
                "stale": 1 if proxy.get("status_level") == "stale" else 0,
            },
            "door": {
                "total": 1,
                "online": 1 if door.get("online") else 0,
                "offline": 0 if door.get("online") else 1,
                "error": 1 if door.get("status_level") == "error" else 0,
                "stale": 1 if door.get("status_level") == "stale" else 0,
            },
        },
        "modules": {
            "power": {"devices": cabinets},
            "light": {"devices": lights},
            "env": {"devices": env},
            "ups": {"devices": ups},
            "snmp": {"devices": snmp},
            "sequencer": {"devices": sequencers},
            "projector": {"devices": projectors},
            "screen": {"devices": screens},
            "automation": automation,
            "server": servers,
            "proxy": proxy,
            "local_model": local_model,
            "door": door,
            "logs": {"items": logs, "total": len(logs)},
        },
    }
    with _DASHBOARD_SUMMARY_CACHE_LOCK:
        _DASHBOARD_SUMMARY_CACHE["payload"] = deepcopy(payload)
        _DASHBOARD_SUMMARY_CACHE["ts"] = time.monotonic()
    return jsonify(payload)
