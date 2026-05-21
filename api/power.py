import csv
import io
import json
import os
import sqlite3
from pathlib import Path
import threading
import urllib.request
import time
from copy import deepcopy
from datetime import datetime

from flask import Blueprint, Response, jsonify, redirect, render_template, request

from audit import log_audit_event
from auth.decorators import require_permission
from auth.operation_lock import acquire_operation_lock, release_operation_lock
from auth.permissions import has_permission
from auth.session import get_current_user
from background import init_light_drivers, onekey_start, onekey_stop
from config import CONFIG, DEFAULT_UI_TEXT, DEVICE_STATUS, get_default_status, save_config
from event_logger import record_event
from data_logger import (
    add_log,
    export_energy_history_rows,
    export_meter_snapshot_csv,
    get_30days_energy_data,
    get_7days_energy_data,
    load_logs,
)
from modbus_core import reload_modbus_client, set_channel
from services.meter_center import build_meter_center_payload, get_all_meter_rows
from services.meter_payloads import apply_reference_comparison
from services.meter_remote import (
    fetch_remote_meter_payload,
    fetch_remote_meter_health,
    get_remote_meter_service_base,
    get_remote_meter_service_mode,
    get_remote_meter_timeout,
    push_remote_meter_config,
    safe_float,
    stabilize_remote_meter_rows,
)
from services.cabinet_gateway import (
    fetch_gateway_health,
    fetch_remote_cabinet_energy_history,
    fetch_remote_cabinet_logs,
    fetch_remote_cabinet_status,
    get_cabinet_gateway_base,
    push_remote_cabinet_config,
    send_remote_cabinet_channel,
    send_remote_cabinet_onekey,
)
from paths import DB_FILE as DB_FILE_PATH, RUNTIME_DIR, ensure_parent_dir, resolve_report_dir
from api.server import get_cached_machine_payload

# Module role: power and meter-facing HTTP API.
# Boundaries: routes should stay compatible while statistics, remote meter
# payload shaping, and cabinet-gateway control move toward services/modules.
# Safety: /api/set and one-key actions control physical strong-current circuits.

bp = Blueprint("power", __name__)
DB_FILE = str(DB_FILE_PATH)
LOG_RESPONSE_CACHE = {}
LOG_RESPONSE_TTL_SEC = 2.0
REMOTE_METER_PAYLOAD_CACHE = {}
REMOTE_METER_PAYLOAD_CACHE_TTL_SEC = 8.0
REMOTE_METER_DISK_CACHE_MAX_AGE_SEC = 12 * 60 * 60
REMOTE_METER_PAYLOAD_CACHE_FILE = RUNTIME_DIR / "remote_meter_payload_cache.json"
METER_ALERT_LOG_CACHE = {}
METER_ALERT_LOG_TTL_SEC = 12 * 60 * 60
GARBLED_TOKENS = ("锛", "馃", "寮€", "闂", "鎿", "鍚", "鏂", "鐏", "绯荤粺", "涓€", "閫氶亾")
POWER_CONTROL_TRACE_FILE = RUNTIME_DIR / "power_control_trace.log"
CONFIG_SAVE_SYNC_TRACE_FILE = RUNTIME_DIR / "config_save_sync_trace.log"
CONFIG_SAVE_SYNC_LOCK = threading.Lock()
CONFIG_SAVE_SYNC_STATE = {
    "running": False,
    "last_started_at": "",
    "last_finished_at": "",
    "last_result": None,
}


def _append_power_control_trace(stage, payload):
    try:
        ensure_parent_dir(POWER_CONTROL_TRACE_FILE)
        row = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "stage": str(stage or ""),
        }
        if isinstance(payload, dict):
            row.update(payload)
        with open(POWER_CONTROL_TRACE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _append_config_sync_trace(stage, payload):
    try:
        ensure_parent_dir(CONFIG_SAVE_SYNC_TRACE_FILE)
        row = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "stage": str(stage or ""),
        }
        if isinstance(payload, dict):
            row.update(payload)
        with open(CONFIG_SAVE_SYNC_TRACE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _run_config_sync_background(sync_payload, *, sync_remote_meter=False, sync_cabinet_gateway=False):
    def worker():
        result = {"remote_sync": None, "cabinet_gateway_sync": None}
        started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with CONFIG_SAVE_SYNC_LOCK:
            CONFIG_SAVE_SYNC_STATE.update({
                "running": True,
                "last_started_at": started_at,
                "last_finished_at": "",
                "last_result": None,
            })
        _append_config_sync_trace("start", {
            "remote_meter": bool(sync_remote_meter),
            "cabinet_gateway": bool(sync_cabinet_gateway),
        })
        try:
            if sync_remote_meter:
                try:
                    result["remote_sync"] = push_remote_meter_config(sync_payload)
                except Exception as sync_error:
                    result["remote_sync"] = {"ok": 0, "msg": str(sync_error)}
            if sync_cabinet_gateway:
                cabinet_payload = {
                    "cabinets": sync_payload.get("cabinets", []),
                    "meter_statistics": sync_payload.get("meter_statistics", {}),
                    "synced_at": sync_payload.get("synced_at"),
                }
                try:
                    result["cabinet_gateway_sync"] = push_remote_cabinet_config(cabinet_payload)
                except Exception as sync_error:
                    result["cabinet_gateway_sync"] = {"ok": 0, "msg": str(sync_error)}
            _append_config_sync_trace("finish", result)
        finally:
            with CONFIG_SAVE_SYNC_LOCK:
                CONFIG_SAVE_SYNC_STATE.update({
                    "running": False,
                    "last_finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "last_result": result,
                })

    with CONFIG_SAVE_SYNC_LOCK:
        if CONFIG_SAVE_SYNC_STATE.get("running"):
            return {"ok": 1, "pending": True, "already_running": True, "msg": "已有配置同步任务正在后台执行"}
    thread = threading.Thread(target=worker, name="config-save-sync", daemon=True)
    thread.start()
    return {"ok": 1, "pending": True, "msg": "远程配置同步已转入后台执行"}


def _looks_garbled_text(value):
    text = str(value or "").strip()
    if not text:
        return True
    return any(token in text for token in GARBLED_TOKENS)


def _normalize_display_reset_for_save(next_meter_statistics, previous_meter_statistics=None):
    meter_statistics = dict(next_meter_statistics or {})
    previous = dict(previous_meter_statistics or {})
    enabled = bool(meter_statistics.get("display_reset_enabled", False))
    from_text = str(meter_statistics.get("display_reset_from") or "").strip()
    current_reset = meter_statistics.get("display_reset", {})
    if not isinstance(current_reset, dict):
        current_reset = {}
    previous_reset = previous.get("display_reset", {})
    if not isinstance(previous_reset, dict):
        previous_reset = {}

    previous_enabled = bool(previous.get("display_reset_enabled", False))
    previous_from = str(previous.get("display_reset_from") or "").strip()
    reset_changed = enabled != previous_enabled or from_text != previous_from
    previous_value = safe_float(previous_reset.get("value", 0.0), 0.0)
    previous_captured_at = str(previous_reset.get("captured_at") or "").strip()
    previous_meter_values = previous_reset.get("meter_values", {})
    if not isinstance(previous_meter_values, dict):
        previous_meter_values = {}
    incoming_value = safe_float(current_reset.get("value", 0.0), 0.0)
    incoming_captured_at = str(current_reset.get("captured_at") or "").strip()
    incoming_meter_values = current_reset.get("meter_values", {})
    incoming_has_baseline = incoming_value > 0 or bool(incoming_captured_at) or isinstance(incoming_meter_values, dict) and bool(incoming_meter_values)
    should_keep_previous_baseline = (
        enabled
        and from_text
        and not reset_changed
        and previous_value > 0
        and previous_captured_at
        and not incoming_has_baseline
    )

    if not enabled or not from_text:
        meter_statistics["display_reset_enabled"] = enabled
        meter_statistics["display_reset_from"] = from_text
        meter_statistics["display_reset"] = {
            "enabled": enabled,
            "from": from_text,
            "value": 0.0,
            "pending": False,
            "captured_at": "",
            "meter_values": {},
        }
        return meter_statistics

    if reset_changed:
        meter_statistics["display_reset_enabled"] = True
        meter_statistics["display_reset_from"] = from_text
        meter_statistics["display_reset"] = {
            "enabled": True,
            "from": from_text,
            "value": 0.0,
            "pending": True,
            "captured_at": "",
            "meter_values": {},
        }
        return meter_statistics

    if should_keep_previous_baseline:
        value = previous_value
        captured_at = previous_captured_at
        pending = False
        meter_values = previous_meter_values
    else:
        value = safe_float(current_reset.get("value", previous_reset.get("value", 0.0)), 0.0)
        captured_at = str(current_reset.get("captured_at") or previous_reset.get("captured_at") or "").strip()
        pending = bool(current_reset.get("pending", previous_reset.get("pending", False)))
        meter_values = current_reset.get("meter_values", previous_reset.get("meter_values", {}))
    if not isinstance(meter_values, dict):
        meter_values = {}
    if enabled and from_text and not captured_at and value <= 0:
        pending = True

    meter_statistics["display_reset_enabled"] = True
    meter_statistics["display_reset_from"] = from_text
    meter_statistics["display_reset"] = {
        "enabled": True,
        "from": from_text,
        "value": round(value, 4),
        "pending": pending,
        "captured_at": captured_at,
        "meter_values": meter_values,
    }
    return meter_statistics


def _config_item_ids(items):
    if not isinstance(items, list):
        return set()
    ids = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or item.get("key") or "").strip()
        if item_id:
            ids.add(item_id)
    return ids


def _preserve_critical_config_for_save(new_config, previous_config):
    """Keep known-good runtime sections when a stale config page submits partial data."""
    if not isinstance(new_config, dict):
        return ["request payload is not an object"]
    previous_config = previous_config if isinstance(previous_config, dict) else {}
    events = []

    guarded_lists = {
        "cabinets": {"label": "强电柜"},
        "meters": {"label": "电表"},
        "hvac_devices": {"label": "空调设备", "protected_prefixes": ("hvac_ha_",)},
        "env_sensors": {
            "label": "环境传感器",
            "protected_ids": ("env_xiaomi_ha_temp_hum_01", "env_xiaomi_ha_contact_01"),
        },
        "automations": {"label": "自动化规则", "protected_prefixes": ("auto_",)},
        "sequencers": {"label": "时序电源"},
        "snmp_devices": {"label": "SNMP设备"},
    }
    for key, rule in guarded_lists.items():
        previous_items = previous_config.get(key)
        if not isinstance(previous_items, list) or not previous_items:
            continue
        incoming_items = new_config.get(key)
        preserve_reason = ""
        if not isinstance(incoming_items, list):
            preserve_reason = "missing_or_not_list"
        elif len(incoming_items) < len(previous_items):
            preserve_reason = f"shrunk_{len(previous_items)}_to_{len(incoming_items)}"
        else:
            previous_ids = _config_item_ids(previous_items)
            incoming_ids = _config_item_ids(incoming_items)
            protected_ids = set(rule.get("protected_ids") or ())
            for item_id in previous_ids:
                if any(item_id.startswith(prefix) for prefix in (rule.get("protected_prefixes") or ())):
                    protected_ids.add(item_id)
            missing_ids = sorted(protected_ids - incoming_ids)
            if missing_ids:
                preserve_reason = "missing_protected_ids:" + ",".join(missing_ids[:8])
        if preserve_reason:
            new_config[key] = deepcopy(previous_items)
            events.append(f"{rule.get('label', key)}({key}) {preserve_reason}")

    previous_meter_statistics = previous_config.get("meter_statistics")
    incoming_meter_statistics = new_config.get("meter_statistics")
    if isinstance(previous_meter_statistics, dict) and previous_meter_statistics:
        if not isinstance(incoming_meter_statistics, dict) or not incoming_meter_statistics:
            new_config["meter_statistics"] = deepcopy(previous_meter_statistics)
            events.append("电表统计(meter_statistics) missing_or_empty")
        else:
            merged_meter_statistics = deepcopy(previous_meter_statistics)
            merged_meter_statistics.update(incoming_meter_statistics)
            new_config["meter_statistics"] = merged_meter_statistics
    return events


def _safe_cab_ui_text(cab, key, fallback):
    ui_text = cab.get("ui_text", {}) if isinstance(cab, dict) else {}
    value = str(ui_text.get(key) or "").strip()
    if not value or _looks_garbled_text(value):
        return str(DEFAULT_UI_TEXT.get(key) or fallback)
    return value


def _cabinet_gateway_enabled():
    meter_statistics = CONFIG.get("meter_statistics", {}) or {}
    return bool(get_cabinet_gateway_base()) and (
        bool(meter_statistics.get("cabinet_gateway_enabled", False))
        or bool(meter_statistics.get("remote_service_enabled", False))
    )


def _cabinet_gateway_required_response(message, *, status_code=503, cab_idx=None, error_code="cabinet_gateway_required"):
    gateway_base = get_cabinet_gateway_base()
    payload = {
        "ok": 0,
        "msg": str(message or "cabinet gateway unavailable"),
        "error": error_code,
        "gateway_enabled": bool(gateway_base),
        "gateway_base": gateway_base,
        "data_source": "cabinet_gateway_required",
        "source_label": "电表服务不可用",
    }
    if cab_idx is not None:
        payload.update(_cabinet_meta(cab_idx))
        payload["cab_idx"] = int(cab_idx or 0)
    return jsonify(payload), int(status_code)


def _cabinet_meta(cab_idx):
    cabinets = CONFIG.get("cabinets", []) or []
    cab_idx = int(cab_idx or 0)
    if 0 <= cab_idx < len(cabinets):
        cab = cabinets[cab_idx]
        return {
            "cab_idx": cab_idx,
            "cabinet_name": cab.get("cabinet_name") or cab.get("meter_display_name") or f"电柜{cab_idx + 1}",
            "plc_type": cab.get("plc_type", ""),
            "station_id": cab.get("station_id"),
            "device_ip": cab.get("ip", ""),
            "device_port": cab.get("port", 502),
            "channel_count": int(cab.get("channel_count", 8) or 8),
        }
    return {
        "cab_idx": cab_idx,
        "cabinet_name": f"电柜{cab_idx + 1}",
        "plc_type": "",
        "station_id": 0,
        "device_ip": "",
        "device_port": 502,
        "channel_count": 8,
    }


def _decorate_cabinet_status(payload, cab_idx, source, error=""):
    data = dict(payload or {})
    meta = _cabinet_meta(cab_idx)
    for key, value in meta.items():
        data.setdefault(key, value)
    gateway_base = get_cabinet_gateway_base()
    data["ok"] = 1 if data.get("ok", 1) not in (0, False) else 0
    data["cab_idx"] = int(cab_idx or 0)
    data["gateway_enabled"] = _cabinet_gateway_enabled()
    data["gateway_base"] = gateway_base
    data["data_source"] = str(source or "remote")
    if str(source).startswith("remote"):
        data["source_label"] = "电表服务"
    elif str(source) == "cabinet_gateway_required":
        data["source_label"] = "电表服务不可用"
    else:
        data["source_label"] = "电表服务"
    data["device_address"] = f"{meta.get('device_ip', '')}:{meta.get('device_port', 502)}".strip(":")
    data["display_address"] = gateway_base if str(source).startswith("remote") and gateway_base else data["device_address"]
    if error:
        data["error"] = str(error)
    return data


def _decorate_logs(items, cab_idx, source):
    logs = []
    if isinstance(items, dict):
        candidate = items.get("logs")
        if isinstance(candidate, list):
            logs = list(candidate)
    elif isinstance(items, list):
        logs = list(items)
    gateway_base = get_cabinet_gateway_base()
    decorated = []
    for item in logs:
        row = dict(item or {})
        row.setdefault("cab_idx", int(cab_idx if cab_idx is not None else row.get("cab_idx", -1) or -1))
        row.setdefault("data_source", source)
        row.setdefault("gateway_base", gateway_base)
        decorated.append(row)
    return decorated


def _parse_log_time_iso(value):
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _merge_log_payloads(primary_logs, secondary_logs, limit=240):
    merged = []
    seen = set()
    for row in list(primary_logs or []) + list(secondary_logs or []):
        item = dict(row or {})
        operation = str(item.get("operation") or "").strip()
        if not operation:
            continue
        dedupe_key = (
            str(item.get("time") or "").strip(),
            str(item.get("cab_idx") or ""),
            operation,
            str(item.get("category") or ""),
            str(item.get("status") or ""),
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        merged.append(item)
    merged.sort(
        key=lambda row: (
            _parse_log_time_iso(row.get("time")) is not None,
            _parse_log_time_iso(row.get("time")) or datetime.min,
            str(row.get("time") or ""),
        ),
        reverse=True,
    )
    return merged[: max(int(limit or 0), 1)]


def _sort_log_payloads(log_rows, limit=None):
    rows = [dict(row or {}) for row in list(log_rows or [])]
    rows.sort(
        key=lambda row: (
            _parse_log_time_iso(row.get("time")) is not None,
            _parse_log_time_iso(row.get("time")) or datetime.min,
            str(row.get("time") or ""),
        ),
        reverse=True,
    )
    if limit is None:
        return rows
    return rows[: max(int(limit or 0), 1)]


def _filter_logs_by_cab(log_rows, cab_idx):
    if cab_idx is None:
        return list(log_rows or [])
    target = int(cab_idx)
    filtered = []
    for row in list(log_rows or []):
        try:
            row_idx = int((row or {}).get("cab_idx"))
        except Exception:
            continue
        if row_idx == target:
            filtered.append(row)
    return filtered


def _safe_float4(value, default=0.0):
    try:
        return round(float(value), 4)
    except Exception:
        return round(float(default), 4)


def _log_remote_meter_alerts_once(remote_payload):
    payload = remote_payload if isinstance(remote_payload, dict) else {}
    alerts = ((payload.get("meter_alerts") or {}).get("daily_jump_resets") or [])
    if not isinstance(alerts, list) or not alerts:
        return

    now_ts = time.time()
    stale_keys = [key for key, ts in METER_ALERT_LOG_CACHE.items() if now_ts - float(ts or 0.0) > METER_ALERT_LOG_TTL_SEC]
    for key in stale_keys:
        METER_ALERT_LOG_CACHE.pop(key, None)

    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        event_id = str(alert.get("event_id") or "").strip()
        if not event_id or event_id in METER_ALERT_LOG_CACHE:
            continue
        meter_name = str(alert.get("display_name") or alert.get("meter_id") or alert.get("source_key") or "unknown").strip()
        date_text = str(alert.get("date") or "").strip()
        implied_daily = _safe_float4(alert.get("implied_daily_before"), 0.0)
        start_before = _safe_float4(alert.get("start_before"), 0.0)
        energy_value = _safe_float4(alert.get("energy_value"), 0.0)
        threshold = _safe_float4(alert.get("threshold"), 0.0)
        detected_at = str(alert.get("detected_at") or "").strip()
        add_log(
            -1,
            f"[meter_guard] 触发日计量防跳纠偏: {meter_name} | 日期 {date_text} | 原推算日量 {implied_daily}kWh (> {threshold}kWh) | 基线 {start_before} -> {energy_value} | 时间 {detected_at}",
        )
        METER_ALERT_LOG_CACHE[event_id] = now_ts


def _remote_meter_cache_key(target, period, days):
    return f"{str(target or 'total').strip()}|{str(period or 'day').strip()}|{int(days or 7)}"


def _ensure_meter_payload_status(payload, *, default_ok=True):
    if not isinstance(payload, dict):
        return payload
    current_ok = payload.get("ok", None)
    if current_ok is None:
        payload["ok"] = 1 if default_ok else 0
    else:
        payload["ok"] = 0 if current_ok in (0, False) else 1
    current_success = payload.get("success", None)
    if current_success is None:
        payload["success"] = bool(payload.get("ok", 0))
    else:
        payload["success"] = bool(current_success)
    return payload


def _read_remote_meter_disk_cache():
    try:
        with open(REMOTE_METER_PAYLOAD_CACHE_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_remote_meter_disk_cache(cache_map):
    if not isinstance(cache_map, dict):
        return
    try:
        ensure_parent_dir(REMOTE_METER_PAYLOAD_CACHE_FILE)
        with open(REMOTE_METER_PAYLOAD_CACHE_FILE, "w", encoding="utf-8") as handle:
            json.dump(cache_map, handle, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return


def _get_cached_remote_meter_payload(target, period, days):
    cache_key = _remote_meter_cache_key(target, period, days)
    cached = REMOTE_METER_PAYLOAD_CACHE.get(cache_key)
    if not isinstance(cached, dict):
        disk_cache = _read_remote_meter_disk_cache()
        cached = disk_cache.get(cache_key)
        if isinstance(cached, dict):
            REMOTE_METER_PAYLOAD_CACHE[cache_key] = deepcopy(cached)
    if not isinstance(cached, dict):
        return None

    now_ts = time.time()
    expires_at = float(cached.get("expires_at", 0.0) or 0.0)
    cached_at = float(cached.get("cached_at", 0.0) or 0.0)
    if cached_at <= 0 and expires_at > 0:
        cached_at = max(0.0, expires_at - REMOTE_METER_PAYLOAD_CACHE_TTL_SEC)

    is_memory_hit = expires_at > now_ts
    is_disk_hit = cached_at > 0 and (now_ts - cached_at) <= REMOTE_METER_DISK_CACHE_MAX_AGE_SEC
    if not is_memory_hit and not is_disk_hit:
        REMOTE_METER_PAYLOAD_CACHE.pop(cache_key, None)
        disk_cache = _read_remote_meter_disk_cache()
        if cache_key in disk_cache:
            disk_cache.pop(cache_key, None)
            _write_remote_meter_disk_cache(disk_cache)
        return None

    payload = cached.get("payload")
    return deepcopy(payload) if isinstance(payload, dict) else None


def _store_cached_remote_meter_payload(target, period, days, payload):
    if not isinstance(payload, dict):
        return
    cache_key = _remote_meter_cache_key(target, period, days)
    now_ts = time.time()
    cache_entry = {
        "expires_at": now_ts + REMOTE_METER_PAYLOAD_CACHE_TTL_SEC,
        "cached_at": now_ts,
        "payload": deepcopy(payload),
    }
    REMOTE_METER_PAYLOAD_CACHE[cache_key] = cache_entry
    disk_cache = _read_remote_meter_disk_cache()
    disk_cache[cache_key] = deepcopy(cache_entry)
    _write_remote_meter_disk_cache(disk_cache)


def _mark_remote_payload_as_cache(payload, remote_base, mode, remote_error=""):
    cached_payload = deepcopy(payload) if isinstance(payload, dict) else {}
    _ensure_meter_payload_status(cached_payload, default_ok=True)
    cached_payload["data_source"] = "remote_meter_service_cache"
    cached_payload["remote_service_url"] = remote_base
    cached_payload["remote_service_mode"] = mode
    cached_payload["remote_error"] = str(remote_error or "")
    cached_payload["stale"] = True
    cached_payload["cache_hit"] = True
    cached_payload["msg"] = "Remote meter service timeout, showing latest cached payload"
    return cached_payload


@bp.route("/")
@require_permission("dashboard.view")
def index():
    return render_template("index.html", config=CONFIG)


@bp.route("/config")
@require_permission("config.view")
def config_page():
    current_user = get_current_user()
    role = str(current_user.role or "").lower()
    account_category = str(getattr(current_user, "account_category", "") or "").lower()
    permissions = getattr(current_user, "permissions", []) or []
    can_manage_config = (
        role == "admin"
        or account_category == "admin"
        or has_permission(role, "system.config", permissions)
        or has_permission(role, "auth.manage", permissions)
        or has_permission(role, "meter.config", permissions)
        or has_permission(role, "control_center.config", permissions)
    )
    if not can_manage_config:
        return redirect("/")
    machines = get_cached_machine_payload(force=True)
    return render_template("config.html", config=CONFIG, default_ui=DEFAULT_UI_TEXT, machines=machines)


@bp.route("/api/config/save", methods=["POST"])
@require_permission("meter.config")
def api_config_save():
    try:
        new_config = request.json
        if not isinstance(new_config, dict):
            return jsonify(ok=0, msg="配置保存数据格式错误"), 400
        guard_events = _preserve_critical_config_for_save(new_config, CONFIG)
        previous_meter_statistics = dict(CONFIG.get("meter_statistics", {}) or {})
        previous_cabinets = CONFIG.get("cabinets", []) or []
        for cab_idx, cab in enumerate(new_config.get("cabinets", [])):
            if "ui_text" not in cab:
                cab["ui_text"] = DEFAULT_UI_TEXT.copy()
            if "channel_count" not in cab:
                cab["channel_count"] = 8
            if cab.get("meter_visible_in_center", True) is False:
                cab["meter_include_in_totals"] = False
            if "meter_include_in_reports" not in cab:
                cab["meter_include_in_reports"] = True
            previous_channels = {}
            if 0 <= cab_idx < len(previous_cabinets):
                previous_channels = {
                    int(item.get("channel") or 0): item
                    for item in (previous_cabinets[cab_idx].get("channels_config", []) or [])
                    if isinstance(item, dict)
                }
            for channel_cfg in cab.get("channels_config", []) or []:
                channel_num = int(channel_cfg.get("channel") or 0)
                previous_remark = str((previous_channels.get(channel_num) or {}).get("remark") or "")
                if "remark" not in channel_cfg and previous_remark:
                    channel_cfg["remark"] = previous_remark
                elif channel_cfg.get("remark") is None:
                    channel_cfg["remark"] = ""

        for meter in new_config.get("meters", []):
            if meter.get("visible_in_meter_center", meter.get("visible", True)) is False:
                meter["include_in_totals"] = False
            if "include_in_reports" not in meter:
                meter["include_in_reports"] = True

        new_config["meter_statistics"] = _normalize_display_reset_for_save(
            new_config.get("meter_statistics", {}),
            previous_meter_statistics,
        )

        save_config(new_config)

        for i in range(len(new_config.get("cabinets", []))):
            if i not in DEVICE_STATUS:
                DEVICE_STATUS[i] = get_default_status()

        reload_modbus_client()
        init_light_drivers()

        remote_sync_result = None
        cabinet_gateway_sync = None
        meter_statistics = CONFIG.get("meter_statistics", {}) or {}
        sync_remote_meter = bool(meter_statistics.get("remote_service_enabled", False)) and bool(
            meter_statistics.get("remote_sync_on_save", False)
        )
        sync_cabinet_gateway = bool(meter_statistics.get("cabinet_gateway_sync_on_save", False)) and bool(get_cabinet_gateway_base())
        if sync_remote_meter or sync_cabinet_gateway:
            sync_payload = {
                "cabinets": deepcopy(new_config.get("cabinets", [])),
                "meters": deepcopy(new_config.get("meters", [])),
                "meter_statistics": deepcopy(new_config.get("meter_statistics", {})),
                "synced_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            sync_task = _run_config_sync_background(
                sync_payload,
                sync_remote_meter=sync_remote_meter,
                sync_cabinet_gateway=sync_cabinet_gateway,
            )
            if sync_remote_meter:
                remote_sync_result = sync_task
            if sync_cabinet_gateway:
                cabinet_gateway_sync = sync_task

        if guard_events:
            add_log(-1, "[system] config save guard preserved: " + "; ".join(guard_events))
            log_audit_event(
                "config.save.guard",
                target="system_config",
                detail={"preserved": guard_events},
            )
        add_log(-1, "[system] config saved and hot reloaded")
        log_audit_event(
            "config.save",
            target="system_config",
            detail={
                "cabinet_count": len(new_config.get("cabinets", [])),
                "meter_count": len(new_config.get("meters", [])),
                "remote_sync": bool(remote_sync_result and remote_sync_result.get("ok")),
                "remote_sync_pending": bool(remote_sync_result and remote_sync_result.get("pending")),
                "cabinet_gateway_sync": bool(cabinet_gateway_sync and cabinet_gateway_sync.get("ok")),
                "cabinet_gateway_sync_pending": bool(cabinet_gateway_sync and cabinet_gateway_sync.get("pending")),
            },
        )
        return jsonify(ok=1, remote_sync=remote_sync_result, cabinet_gateway_sync=cabinet_gateway_sync)
    except Exception as exc:
        log_audit_event("config.save", target="system_config", detail={"error": str(exc)}, status="error")
        return jsonify(ok=0, msg=str(exc))


@bp.route("/api/config/sync_status")
@require_permission("meter.config")
def api_config_sync_status():
    with CONFIG_SAVE_SYNC_LOCK:
        return jsonify(ok=1, **deepcopy(CONFIG_SAVE_SYNC_STATE))


@bp.route("/api/status")
@require_permission("power.view")
def api_status():
    cab_idx = request.args.get("cab", 0, type=int)
    if not _cabinet_gateway_enabled():
        return _cabinet_gateway_required_response("电表服务未配置或未启用", cab_idx=cab_idx)
    try:
        payload = fetch_remote_cabinet_status(cab_idx)
        return jsonify(_decorate_cabinet_status(payload, cab_idx, "remote_cabinet_gateway"))
    except Exception as exc:
        return _cabinet_gateway_required_response(str(exc), cab_idx=cab_idx, error_code="cabinet_gateway_read_failed")


@bp.route("/api/meters")
@require_permission("meter.view")
def api_meters():
    # Keep this route stable for dashboard, meter page, and exports. Expensive
    # remote reads are cached so UI refreshes do not overload the NAS service.
    target = request.args.get("target", "total")
    period = request.args.get("period", "day")
    days = request.args.get("days", 7, type=int)
    remote_base = get_remote_meter_service_base()
    mode = get_remote_meter_service_mode()

    if mode == "local_only":
        local_payload = build_meter_center_payload(target_source_key=target, period=period, days=days)
        _ensure_meter_payload_status(local_payload, default_ok=True)
        local_payload["data_source"] = "local_meter_center"
        local_payload["remote_service_mode"] = mode
        return jsonify(local_payload)

    if not remote_base:
        return jsonify({
            "ok": 0,
            "msg": "NAS meter service is not configured or not enabled",
            "data_source": "remote_meter_service_required",
            "remote_service_mode": mode,
        }), 503

    try:
        remote_payload = fetch_remote_meter_payload(target_source_key=target, period=period, days=days)
        if isinstance(remote_payload, dict):
            _ensure_meter_payload_status(remote_payload, default_ok=True)
            remote_payload["meters"] = stabilize_remote_meter_rows(remote_payload.get("meters", []) or [])
            remote_payload["remote_service_url"] = remote_base
            remote_payload["remote_service_mode"] = mode
            if not isinstance(remote_payload.get("summary"), dict):
                remote_payload = apply_reference_comparison(remote_payload)
            _log_remote_meter_alerts_once(remote_payload)
            remote_payload["data_source"] = "remote_meter_service"
            remote_payload["stale"] = False
            remote_payload["cache_hit"] = False
            _store_cached_remote_meter_payload(target, period, days, remote_payload)
            return jsonify(remote_payload)
    except Exception as remote_error:
        cached_payload = _get_cached_remote_meter_payload(target, period, days)
        if cached_payload:
            return jsonify(_mark_remote_payload_as_cache(cached_payload, remote_base, mode, remote_error=str(remote_error)))
        return jsonify({
            "ok": 0,
            "success": False,
            "msg": f"NAS meter service read failed: {str(remote_error)}",
            "data_source": "remote_meter_service_error",
            "remote_service_url": remote_base,
            "remote_error": str(remote_error),
            "remote_service_mode": mode,
        }), 503

    cached_payload = _get_cached_remote_meter_payload(target, period, days)
    if cached_payload:
        return jsonify(_mark_remote_payload_as_cache(cached_payload, remote_base, mode, remote_error="empty payload"))

    return jsonify({
        "ok": 0,
        "success": False,
        "msg": "NAS meter service returned empty payload",
        "data_source": "remote_meter_service_error",
        "remote_service_url": remote_base,
        "remote_service_mode": mode,
    }), 503


@bp.route("/api/meter_service/test")
@require_permission("meter.view")
def api_meter_service_test():
    base = get_remote_meter_service_base()
    if not base:
        return jsonify(ok=0, msg="未配置远程电表服务地址")
    try:
        req = urllib.request.Request(f"{base}/api/health", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=max(get_remote_meter_timeout(), 3)) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return jsonify(ok=1, base=base, health=payload)
    except Exception as exc:
        return jsonify(ok=0, base=base, msg=str(exc))


@bp.route("/api/cabinet_gateway/test")
@require_permission("power.view")
def api_cabinet_gateway_test():
    result = fetch_gateway_health()
    status_code = 200 if bool(result.get("ok")) else 503
    return jsonify(result), status_code


@bp.route("/api/meter_service/diagnostics")
@require_permission("meter.view")
def api_meter_service_diagnostics():
    target = request.args.get("target", "total")
    period = request.args.get("period", "day")
    days = request.args.get("days", 7, type=int)
    local_payload = build_meter_center_payload(target_source_key=target, period=period, days=days)
    local_rows = list(local_payload.get("meters", []) or [])
    local_index = {}
    for row in local_rows:
        source_key = str(row.get("source_key") or row.get("meter_id") or row.get("id") or "").strip()
        if source_key:
            local_index[source_key] = row
        meter_id = str(row.get("meter_id") or row.get("id") or "").strip()
        if meter_id:
            local_index[meter_id] = row

    health = fetch_remote_meter_health()
    remote_payload = None
    remote_rows = []
    remote_error = ""
    if health.get("ok"):
        try:
            remote_payload = fetch_remote_meter_payload(target_source_key=target, period=period, days=days)
            remote_rows = stabilize_remote_meter_rows((remote_payload or {}).get("meters", []) or [])
        except Exception as exc:
            remote_error = str(exc)
    else:
        remote_error = str(health.get("msg") or "")

    remote_index = {}
    for row in remote_rows:
        source_key = str(row.get("source_key") or row.get("meter_id") or row.get("id") or "").strip()
        if source_key:
            remote_index[source_key] = row
        meter_id = str(row.get("meter_id") or row.get("id") or "").strip()
        if meter_id:
            remote_index[meter_id] = row

    keys = sorted(set(local_index.keys()) | set(remote_index.keys()))
    diffs = []
    for key in keys:
        local_row = local_index.get(key)
        remote_row = remote_index.get(key)
        if not local_row and not remote_row:
            continue
        local_power = safe_float((local_row or {}).get("realtime_power"), 0.0)
        remote_power = safe_float((remote_row or {}).get("realtime_power"), 0.0)
        local_energy = safe_float((local_row or {}).get("electric_energy"), 0.0)
        remote_energy = safe_float((remote_row or {}).get("electric_energy"), 0.0)
        local_daily = safe_float((local_row or {}).get("daily_energy"), 0.0)
        remote_daily = safe_float((remote_row or {}).get("daily_energy"), 0.0)
        power_delta = round(local_power - remote_power, 4)
        energy_delta = round(local_energy - remote_energy, 4)
        daily_delta = round(local_daily - remote_daily, 4)
        label = (
            (local_row or {}).get("display_name")
            or (remote_row or {}).get("display_name")
            or (local_row or {}).get("cabinet_name")
            or (remote_row or {}).get("cabinet_name")
            or key
        )
        diffs.append(
            {
                "key": key,
                "label": label,
                "local_online": bool((local_row or {}).get("online", False)),
                "remote_online": bool((remote_row or {}).get("online", False)),
                "local_power": local_power,
                "remote_power": remote_power,
                "power_delta": power_delta,
                "local_energy": local_energy,
                "remote_energy": remote_energy,
                "energy_delta": energy_delta,
                "local_daily": local_daily,
                "remote_daily": remote_daily,
                "daily_delta": daily_delta,
                "has_difference": bool(abs(power_delta) > 0.2 or abs(energy_delta) > 0.5 or abs(daily_delta) > 0.5 or bool((local_row or {}).get("online", False)) != bool((remote_row or {}).get("online", False))),
            }
        )

    return jsonify(
        {
            "ok": True,
            "mode": get_remote_meter_service_mode(),
            "remote_service_url": get_remote_meter_service_base(),
            "remote_timeout_sec": get_remote_meter_timeout(),
            "health": health,
            "remote_error": remote_error,
            "local_summary": (local_payload or {}).get("summary", {}),
            "remote_summary": (remote_payload or {}).get("summary", {}) if isinstance(remote_payload, dict) else {},
            "local_meter_count": len(local_rows),
            "remote_meter_count": len(remote_rows),
            "differences": diffs,
        }
    )


@bp.route("/api/7days_energy")
@require_permission("power.view")
def api_7days_energy():
    cab_idx = request.args.get("cab", 0, type=int)
    if not _cabinet_gateway_enabled():
        return _cabinet_gateway_required_response("电表服务未配置或未启用", cab_idx=cab_idx)
    try:
        return jsonify(fetch_remote_cabinet_energy_history(cab_idx, days=7))
    except Exception as exc:
        return _cabinet_gateway_required_response(str(exc), cab_idx=cab_idx, error_code="cabinet_energy_history_failed")


@bp.route("/api/30days_energy")
@require_permission("power.view")
def api_30days_energy():
    cab_idx = request.args.get("cab", 0, type=int)
    if not _cabinet_gateway_enabled():
        return _cabinet_gateway_required_response("电表服务未配置或未启用", cab_idx=cab_idx)
    try:
        return jsonify(fetch_remote_cabinet_energy_history(cab_idx, days=30))
    except Exception as exc:
        return _cabinet_gateway_required_response(str(exc), cab_idx=cab_idx, error_code="cabinet_energy_history_failed")


@bp.route("/api/export/energy_30days")
@require_permission("power.view")
def api_export_energy_30days():
    rows = export_energy_history_rows(30)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["cab_idx", "cabinet_name", "date", "consume_kwh", "is_today"])
    for row in rows:
        writer.writerow(
            [
                row["cab_idx"],
                row["cabinet_name"],
                row["date"],
                row["consume_kwh"],
                1 if row["is_today"] else 0,
            ]
        )
    csv_text = output.getvalue()
    output.close()
    filename = f"energy_30days_{request.host.split(':')[0].replace('.', '_')}.csv"
    return Response(
        csv_text,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@bp.route("/api/export/meter_statistics")
@require_permission("meter.view")
def api_export_meter_statistics():
    target = request.args.get("target", "total")
    period = request.args.get("period", "day")
    days = request.args.get("days", 30, type=int)
    payload = build_meter_center_payload(target_source_key=target, period=period, days=days)
    period_key = "weekly" if period == "week" else ("monthly" if period == "month" else "daily")
    rows = payload.get("trend_breakdown", {}).get(period_key, [])

    meter_statistics = CONFIG.get("meter_statistics", {}) or {}
    abs_report_dir = os.path.join(str(resolve_report_dir(meter_statistics.get("report_dir"))), "center")
    os.makedirs(abs_report_dir, exist_ok=True)

    target_label = next(
        (item.get("label") for item in payload.get("trend_targets", []) if str(item.get("source_key")) == str(target)),
        "全部统计电表",
    )
    if not target_label:
        target_label = "全部统计电表"
    filename = f"meter_stats_{target}_{period}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv".replace(":", "_")
    file_path = os.path.join(abs_report_dir, filename)

    with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["target", "period_key", "consume_kwh"])
        for row in rows:
            writer.writerow([target_label, row.get("period"), row.get("consume")])

    return jsonify({"ok": 1, "file_path": file_path, "target": target, "period": period, "rows": len(rows)})


@bp.route("/api/export/meter_raw")
@require_permission("meter.view")
def api_export_meter_raw():
    meter_statistics = CONFIG.get("meter_statistics", {}) or {}
    abs_report_dir = os.path.join(str(resolve_report_dir(meter_statistics.get("report_dir"))), "raw")
    rows = get_all_meter_rows()
    file_path = export_meter_snapshot_csv(rows, abs_report_dir, prefix="meter_raw_manual")
    return jsonify(ok=1, file_path=file_path, rows=len(rows))


@bp.route("/api/set", methods=["POST"])
@require_permission("power.control")
def api_set():
    d = request.json
    cab = d.get("cab", 0)
    ch = d.get("ch")
    on = d.get("on")
    _append_power_control_trace("120_api_set_in", {
        "cab": cab,
        "ch": ch,
        "on": bool(on),
        "remote_addr": request.headers.get("X-Forwarded-For", request.remote_addr),
        "user_agent": request.headers.get("User-Agent", ""),
        "referer": request.headers.get("Referer", ""),
    })
    current_user = get_current_user()
    lock_key = f"power:{cab}:channel:{ch}"
    locked, lock_info = acquire_operation_lock(lock_key, current_user.username, "power_set", timeout_sec=2.5)
    if not locked:
        _append_power_control_trace("120_api_set_locked", {
            "cab": cab,
            "ch": ch,
            "on": bool(on),
            "owner": lock_info.get("owner"),
        })
        return jsonify(ok=0, msg=f"设备正由 {lock_info.get('owner')} 操作，请稍后再试", error="device_busy"), 409
    try:
        if not _cabinet_gateway_enabled():
            return _cabinet_gateway_required_response("电表服务未配置或未启用", cab_idx=cab, status_code=503)
        result = send_remote_cabinet_channel(cab, ch, on)
        _append_power_control_trace("120_api_set_out", {
            "cab": cab,
            "ch": ch,
            "on": bool(on),
            "result_ok": bool((result or {}).get("ok")),
            "result_ignored": bool((result or {}).get("ignored")),
            "verified": bool((result or {}).get("verified")),
            "write_ack": bool((result or {}).get("write_ack")),
            "fast_write_ack": bool((result or {}).get("fast_write_ack")),
            "fallback_write_ack": bool((result or {}).get("fallback_write_ack")),
            "result_msg": (result or {}).get("msg", ""),
            "gateway_source": (result or {}).get("gateway_source", "") or (((result or {}).get("status") or {}).get("gateway_source", "")),
            "runtime_error": (result or {}).get("runtime_error", "") or (((result or {}).get("status") or {}).get("runtime_error", "")),
            "status_channels": ((result or {}).get("status") or {}).get("channels_1_4"),
        })
        ok = bool((result or {}).get("ok"))
        cabinets = CONFIG.get("cabinets", []) or []
        cab_cfg = cabinets[cab] if 0 <= int(cab) < len(cabinets) else {}
        label_channel = _safe_cab_ui_text(cab_cfg, "label_channel", "通道")
        label_action = _safe_cab_ui_text(cab_cfg, "label_on" if on else "label_off", "合闸" if on else "断开")
        channel_cfg = next((item for item in (cab_cfg.get("channels_config") or []) if int(item.get("channel", -1) or -1) == int(ch)), {})
        device_name = str(cab_cfg.get("name") or f"强电柜{cab}")
        channel_name = str(channel_cfg.get("remark") or channel_cfg.get("name") or f"{label_channel}{ch}")
        try:
            record_event(
                category="power",
                event_type="command",
                source="api",
                source_detail=current_user.username,
                device_id=f"cabinet:{cab}",
                device_name=device_name,
                channel=str(ch),
                action="power_on" if on else "power_off",
                message=f"[强电柜] 控制命令 {device_name} {channel_name} {label_action}",
                result="success" if ok else "failed",
                confidence="confirmed" if ok else "unknown",
                cab_idx=int(cab),
                raw={"request": d, "result": result, "channel_name": channel_name},
            )
        except Exception:
            pass
        if ok:
            add_log(
                cab,
                f"操作: {label_channel}{ch} {label_action}",
            )
            log_audit_event(
                "power.channel.set",
                target=f"cabinet:{cab}:channel:{ch}",
                detail={"cabinet": cab, "channel": ch, "on": bool(on)},
            )
        return jsonify(result or {"ok": 1 if ok else 0})
    except Exception as exc:
        _append_power_control_trace("120_api_set_exception", {
            "cab": cab,
            "ch": ch,
            "on": bool(on),
            "error": str(exc),
        })
        return jsonify(ok=0, msg=str(exc))
    finally:
        release_operation_lock(lock_key, current_user.username)


@bp.route("/api/onekey_start")
@require_permission("power.control")
def api_start():
    cab_idx = request.args.get("cab", 0, type=int)
    current_user = get_current_user()
    lock_key = f"power:{cab_idx}:onekey"
    locked, lock_info = acquire_operation_lock(lock_key, current_user.username, "onekey_start", timeout_sec=5.0)
    if not locked:
        return jsonify(ok=0, msg=f"设备正由 {lock_info.get('owner')} 操作，请稍后再试", error="device_busy"), 409
    try:
        if not _cabinet_gateway_enabled():
            return _cabinet_gateway_required_response("电表服务未配置或未启用", cab_idx=cab_idx, status_code=503)
        if _cabinet_gateway_enabled():
            result = send_remote_cabinet_onekey(cab_idx, "start")
            if not bool((result or {}).get("ok")):
                return jsonify(result or {"ok": 0, "msg": "启动失败"})
            payload = result
        else:
            onekey_start(cab_idx)
            payload = {"ok": 1}
        log_audit_event("power.onekey_start", target=f"cabinet:{cab_idx}", detail={"cabinet": cab_idx})
        return jsonify(payload)
    except Exception as exc:
        return jsonify(ok=0, msg=str(exc))
    finally:
        release_operation_lock(lock_key, current_user.username)


@bp.route("/api/onekey_stop")
@require_permission("power.control")
def api_stop():
    cab_idx = request.args.get("cab", 0, type=int)
    current_user = get_current_user()
    lock_key = f"power:{cab_idx}:onekey"
    locked, lock_info = acquire_operation_lock(lock_key, current_user.username, "onekey_stop", timeout_sec=5.0)
    if not locked:
        return jsonify(ok=0, msg=f"设备正由 {lock_info.get('owner')} 操作，请稍后再试", error="device_busy"), 409
    try:
        if not _cabinet_gateway_enabled():
            return _cabinet_gateway_required_response("电表服务未配置或未启用", cab_idx=cab_idx, status_code=503)
        if _cabinet_gateway_enabled():
            result = send_remote_cabinet_onekey(cab_idx, "stop")
            if not bool((result or {}).get("ok")):
                return jsonify(result or {"ok": 0, "msg": "停止失败"})
            payload = result
        else:
            onekey_stop(cab_idx)
            payload = {"ok": 1}
        log_audit_event("power.onekey_stop", target=f"cabinet:{cab_idx}", detail={"cabinet": cab_idx})
        return jsonify(payload)
    except Exception as exc:
        return jsonify(ok=0, msg=str(exc))
    finally:
        release_operation_lock(lock_key, current_user.username)


@bp.route("/api/logs")
@require_permission("power.view")
def api_logs():
    cab_arg = request.args.get("cab")
    cab_idx = None if cab_arg in (None, "") else request.args.get("cab", type=int)
    if cab_idx is not None:
        if not _cabinet_gateway_enabled():
            return jsonify([])
        try:
            remote_payload = _filter_logs_by_cab(
                _decorate_logs(fetch_remote_cabinet_logs(cab_idx), cab_idx, "remote_cabinet_gateway"),
                cab_idx,
            )
            return jsonify(_sort_log_payloads(remote_payload))
        except Exception:
            return jsonify([])
    cache_key = "all" if cab_idx is None else str(cab_idx)
    now_ts = time.time()
    cached = LOG_RESPONSE_CACHE.get(cache_key)
    if cached and now_ts < float(cached.get("expires_at", 0.0) or 0.0):
        return jsonify(cached.get("payload", []))
    payload = None
    if cab_idx is None:
        local_rows = load_logs(None)
    else:
        # 强电详情页只显示当前电柜操作日志，不混入全局系统日志。
        local_rows = load_logs(cab_idx)
    local_payload = _filter_logs_by_cab(_decorate_logs(local_rows, cab_idx, "local_direct"), cab_idx)
    if _cabinet_gateway_enabled():
        try:
            remote_payload = _filter_logs_by_cab(
                _decorate_logs(fetch_remote_cabinet_logs(cab_idx), cab_idx, "remote_cabinet_gateway"),
                cab_idx,
            )
            payload = _merge_log_payloads(remote_payload, local_payload)
        except Exception:
            payload = None
    if payload is None:
        payload = local_payload
    payload = _sort_log_payloads(payload, limit=240)
    LOG_RESPONSE_CACHE[cache_key] = {"expires_at": now_ts + LOG_RESPONSE_TTL_SEC, "payload": payload}
    return jsonify(payload)


@bp.route("/api/logs/frontend", methods=["POST"])
def api_frontend_logs():
    try:
        data = request.get_json(silent=True) or {}
        scope = str(data.get("scope") or "unknown").strip() or "unknown"
        message = str(data.get("message") or "").strip() or "frontend_error"
        add_log(-1, f"[frontend:{scope}] {message}")
        return jsonify({"ok": 1})
    except Exception as exc:
        return jsonify({"ok": 0, "msg": str(exc)}), 500


@bp.route("/api/diagnose")
@require_permission("power.view")
def api_diagnose():
    import socket as _socket
    import modbus_core as mc

    results = []
    for i, cab in enumerate(CONFIG.get("cabinets", [])):
        ip, port = cab["ip"], int(cab["port"])
        item = {
            "idx": i,
            "name": cab.get("cabinet_name", f"电柜{i}"),
            "ip": ip,
            "port": port,
            "tcp": False,
            "modbus": False,
            "raw": None,
            "error": "",
        }
        try:
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect((ip, port))
            s.close()
            item["tcp"] = True
        except Exception as exc:
            item["error"] = f"TCP 连接失败: {exc}"
            results.append(item)
            continue
        try:
            res = mc.read_regs(i, 0x04B0, 4)
            item["modbus"] = res is not None
            if res:
                item["raw"] = res.hex(" ").upper()
            else:
                item["error"] = "Modbus 无响应"
        except Exception as exc:
            item["error"] = f"Modbus 异常: {exc}"
        results.append(item)
    return jsonify(results)
