# AI_MODULE: snmp_api
# AI_PURPOSE: SNMP 设备状态接口，提供 NAS、交换机、网关等网络设备的概览和详情数据。
# AI_BOUNDARY: 不在请求里做完整 walk；重型轮询在 background/snmp_core，API 只整理缓存和必要即时测试。
# AI_DATA_FLOW: snmp_core/background -> SNMP_STATUS -> /api/snmp/status -> static/js/views/snmp.js。
# AI_RUNTIME: SNMP 页面和首页摘要会调用，响应体可能很大，要优先支持缓存和紧凑字段。
# AI_RISK: 中，字段错误会导致容量、端口、VLAN、告警展示不准；过慢会拖慢页面。
# AI_COMPAT: /api/snmp/status 和 /api/snmp/test 的设备 id、summary、metrics、walk 字段需保持兼容。
# AI_SEARCH_KEYWORDS: snmp, qnap, ikuai, h3c, vlan, interface, storage, oid.

from datetime import datetime
import threading
import time

from flask import Blueprint, jsonify, request

from auth.decorators import require_permission
from config import CONFIG
from runtime.state import SNMP_STATUS
from snmp_core import poll_snmp_device

bp = Blueprint("snmp", __name__)


_SNMP_API_CACHE_LOCK = threading.Lock()
_SNMP_API_CACHE = {}
_SNMP_API_CACHE_TTL_SEC = 1.0
_SNMP_API_COMPACT_CACHE_TTL_SEC = 3.0
_SNMP_COMPACT_SUMMARY_KEYS = {
    "alert_counts",
    "ap_count",
    "contact_text",
    "cpu_avg_percent",
    "cpu_core_count",
    "cpu_model",
    "cpu_peak_percent",
    "cpu_temperature_c",
    "device_type",
    "disk_count",
    "fan_count",
    "gpu_metrics",
    "health_score",
    "interface_preview",
    "interface_rows",
    "interface_summary",
    "ikuai_summary",
    "location_text",
    "memory_alert_level",
    "memory_available_text",
    "memory_total_text",
    "memory_usage_percent",
    "memory_used_text",
    "nat_sessions",
    "network_connections",
    "network_top_rows",
    "online_clients",
    "physical_top_rows",
    "poll_elapsed_sec",
    "process_count",
    "qnap_ssh_summary",
    "risk_level",
    "session_count",
    "storage_count",
    "storage_critical_count",
    "storage_rows",
    "storage_top_rows",
    "storage_warning_count",
    "sys_descr_text",
    "system_temperature_c",
    "temperature_rows",
    "ucd_load_1",
    "ucd_load_15",
    "ucd_load_5",
    "uptime_text",
    "user_count",
    "vendor_memory_free_text",
    "vendor_memory_total_text",
    "disk_rows",
    "disk_top_rows",
    "fan_rows",
    "wan_top_rows",
    "lan_top_rows",
}
_SNMP_COMPACT_INTERFACE_KEYS = {
    "active_count",
    "active_in_rate_bps",
    "active_in_rate_text",
    "active_out_rate_bps",
    "active_out_rate_text",
    "active_top_rows",
    "active_total_rate_bps",
    "active_total_rate_text",
    "aggregate_in_rate_bps",
    "aggregate_in_rate_text",
    "aggregate_out_rate_bps",
    "aggregate_out_rate_text",
    "aggregate_total_rate_bps",
    "aggregate_total_rate_text",
    "bond_count",
    "bond_names",
    "bridge_count",
    "bridge_fdb_rows",
    "bridge_learned_mac_count",
    "bridge_mac_count",
    "bridge_names",
    "bridge_port_mac_rows",
    "bridge_port_count",
    "bridge_vlan_rows",
    "bridge_vlan_count",
    "busy_port_count",
    "configured_access_count",
    "configured_port_count",
    "configured_port_rows",
    "configured_trunk_count",
    "configured_vlan_count",
    "configured_vlan_rows",
    "configured_vlan_traffic_rows",
    "delta_discard_port_count",
    "delta_error_port_count",
    "discard_port_count",
    "down_count",
    "down_rows",
    "error_port_count",
    "interface_sample_count",
    "interface_total_count",
    "lan_count",
    "lan_names",
    "physical_count",
    "physical_down_count",
    "physical_names",
    "physical_unknown_count",
    "physical_up_count",
    "port_preview_rows",
    "switch_port_rows",
    "top_busy_port_rows",
    "high_utilization_port_rows",
    "top_names",
    "unknown_count",
    "unknown_rows",
    "up_count",
    "uplink_count",
    "vlan_gateway_rows",
    "vlan_traffic_rows",
    "virtual_count",
    "virtual_names",
    "wan_count",
    "wan_names",
}
_SNMP_COMPACT_STATUS_KEYS = {
    "cache_age_sec",
    "custom_metrics",
    "device_type",
    "error",
    "host",
    "if_number",
    "last_checked_age_sec",
    "last_checked_at",
    "last_error",
    "last_error_at",
    "last_success_at",
    "online",
    "poll_failures",
    "port",
    "retries",
    "stale",
    "status_label",
    "status_level",
    "summary",
    "sys_name",
    "timeout_sec",
    "updated_at",
    "version",
    "walk_enabled",
    "walk_error",
    "walk_total_oids",
    "walk_truncated",
}
_SNMP_COMPACT_CONFIG_KEYS = {
    "id",
    "name",
    "brand",
    "model",
    "device_type",
    "protocol",
    "version",
    "host",
    "port",
    "poll_interval_ms",
    "visible",
    "enabled",
    "walk_enabled",
}


def _parse_updated_at(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _status_label(level):
    normalized = str(level or "").strip().lower()
    if normalized == "online":
        return "在线"
    if normalized == "stale":
        return "陈旧"
    if normalized == "error":
        return "异常"
    return "离线"


def _apply_status_level(status):
    payload = dict(status or {})
    online = bool(payload.get("online"))
    stale = bool(payload.get("stale"))
    has_error = bool(payload.get("last_error") or payload.get("error"))
    has_history = bool(payload.get("last_success_at") or payload.get("updated_at"))
    if online and stale:
        level = "stale"
    elif online:
        level = "online"
    elif has_error and has_history:
        level = "error"
    elif has_error:
        level = "error"
    else:
        level = "offline"
    payload["status_level"] = level
    payload["status_label"] = _status_label(level)
    return payload


def _truthy_query_arg(name):
    return str(request.args.get(name, "")).strip().lower() in {"1", "true", "yes", "on", "compact", "dashboard"}


def _pick_keys(source, keys):
    if not isinstance(source, dict):
        return {}
    return {key: source[key] for key in keys if key in source}


def _limit_sequence(value, limit):
    if not isinstance(value, list):
        return value
    return value[:limit]


def _compact_interface_summary(interface_summary):
    compact = _pick_keys(interface_summary, _SNMP_COMPACT_INTERFACE_KEYS)
    for key in ("wan_names", "lan_names", "bond_names", "bridge_names", "physical_names", "top_names", "virtual_names"):
        if key in compact:
            compact[key] = _limit_sequence(compact[key], 8)
    if isinstance(compact.get("active_top_rows"), list):
        compact["active_top_rows"] = compact["active_top_rows"][:8]
    for key, limit in (
        ("switch_port_rows", 10),
        ("top_busy_port_rows", 6),
        ("high_utilization_port_rows", 6),
        ("configured_port_rows", 0),
        ("configured_vlan_rows", 0),
        ("configured_vlan_traffic_rows", 0),
        ("vlan_traffic_rows", 0),
        ("vlan_gateway_rows", 0),
        ("port_preview_rows", 4),
        ("down_rows", 8),
        ("bridge_port_mac_rows", 0),
        ("bridge_vlan_rows", 0),
        ("bridge_fdb_rows", 0),
    ):
        if isinstance(compact.get(key), list):
            compact[key] = compact[key][:limit]
    return compact


def _compact_summary(summary):
    if not isinstance(summary, dict):
        summary = {}
    compact = _pick_keys(summary, _SNMP_COMPACT_SUMMARY_KEYS)
    compact["alert_counts"] = dict(compact.get("alert_counts", {}) or {})
    compact["interface_summary"] = _compact_interface_summary(summary.get("interface_summary", {}) or {})
    if isinstance(compact.get("gpu_metrics"), list):
        compact["gpu_metrics"] = compact["gpu_metrics"][:4]
    for key, limit in (
        ("network_top_rows", 4),
        ("physical_top_rows", 4),
        ("wan_top_rows", 8),
        ("lan_top_rows", 8),
        ("storage_rows", 24),
        ("storage_top_rows", 12),
        ("disk_rows", 16),
        ("disk_top_rows", 12),
        ("fan_rows", 12),
    ):
        if isinstance(compact.get(key), list):
            compact[key] = compact[key][:limit]
    if isinstance(compact.get("interface_rows"), list):
        compact["interface_rows"] = compact["interface_rows"][:4]
    return compact


def _compact_config(config):
    return _pick_keys(config, _SNMP_COMPACT_CONFIG_KEYS)


def _compact_status(status):
    compact = _pick_keys(status, _SNMP_COMPACT_STATUS_KEYS)
    compact["summary"] = _compact_summary((status or {}).get("summary", {}) or {})
    compact["config"] = _compact_config((status or {}).get("config", {}) or {})
    if isinstance(compact.get("custom_metrics"), list):
        compact["custom_metrics"] = compact["custom_metrics"][:16]
    return compact


def _build_snmp_config_payload(cfg, *, compact=False):
    payload = {
        "id": str(cfg.get("id")),
        "name": cfg.get("name", cfg.get("id")),
        "brand": cfg.get("brand", ""),
        "model": cfg.get("model", ""),
        "device_type": cfg.get("device_type", "network"),
        "protocol": cfg.get("protocol", "SNMP"),
        "version": cfg.get("version", "v2c"),
        "host": cfg.get("host", cfg.get("ip", "")),
        "port": cfg.get("port", 161),
        "poll_interval_ms": cfg.get("poll_interval_ms", 5000),
        "visible": cfg.get("visible", True),
        "enabled": cfg.get("enabled", True),
        "walk_enabled": cfg.get("walk_enabled", False),
    }
    if compact:
        return payload
    payload.update(
        {
            "walk_roots": cfg.get("walk_roots", []),
            "walk_max_oids": cfg.get("walk_max_oids", 256),
            "walk_sample_limit": cfg.get("walk_sample_limit", 12),
            "walk_interval_ms": cfg.get("walk_interval_ms", 20000),
            "walk_roots_per_cycle": cfg.get("walk_roots_per_cycle", 0),
            "source_ip": cfg.get("source_ip", ""),
            "timeout_sec": cfg.get("timeout_sec", 2.0),
            "retries": cfg.get("retries", 1),
        }
    )
    return payload


def _build_snmp_status_snapshot(cfg):
    device_id = str(cfg.get("id"))
    cached = dict(SNMP_STATUS.get(device_id, {}) or {})
    if not cached:
        cached = {
            "online": False,
            "summary": {},
            "alert_counts": {},
            "updated_at": None,
            "last_checked_at": None,
            "error": "" if cfg.get("enabled", True) else "disabled",
            "poll_failures": 0,
            "stale": False,
        }

    interval_sec = max(2.0, float(cfg.get("poll_interval_ms", 5000) or 5000) / 1000.0)
    walk_interval_sec = max(
        interval_sec,
        float(cfg.get("walk_interval_ms", cfg.get("poll_interval_ms", 5000)) or cfg.get("poll_interval_ms", 5000)) / 1000.0,
    )
    stale_grace_sec = max(
        45.0 if cfg.get("walk_enabled", False) else 15.0,
        interval_sec * (10.0 if cfg.get("walk_enabled", False) else 3.5),
        walk_interval_sec * (2.0 if cfg.get("walk_enabled", False) else 1.0),
    )
    updated_at = _parse_updated_at(cached.get("updated_at"))
    last_checked_at = _parse_updated_at(cached.get("last_checked_at")) or updated_at
    now = datetime.now()
    cache_age_sec = max(0.0, (now - updated_at).total_seconds()) if updated_at else None
    checked_age_sec = max(0.0, (now - last_checked_at).total_seconds()) if last_checked_at else None
    cached["cache_age_sec"] = round(cache_age_sec, 1) if cache_age_sec is not None else None
    cached["last_checked_age_sec"] = round(checked_age_sec, 1) if checked_age_sec is not None else None
    cached["stale"] = bool(
        cached.get("stale")
        or (cache_age_sec is not None and cache_age_sec > stale_grace_sec)
    )

    if not updated_at and cfg.get("enabled", True):
        cached["error"] = cached.get("error") or "等待后台轮询"

    if cfg.get("enabled", True) is False:
        cached["online"] = False
        cached["error"] = "disabled"
        cached["stale"] = False
    elif cached["stale"] and int(cached.get("poll_failures", 0) or 0) >= 3:
        cached["online"] = False

    return _apply_status_level(cached)


@bp.route("/api/snmp/status")
@require_permission("snmp.view")
def api_snmp_status():
    compact = _truthy_query_arg("compact") or _truthy_query_arg("summary")
    cache_key = "compact" if compact else "full"
    cache_ttl = _SNMP_API_COMPACT_CACHE_TTL_SEC if compact else _SNMP_API_CACHE_TTL_SEC
    now = time.monotonic()
    with _SNMP_API_CACHE_LOCK:
        cached = _SNMP_API_CACHE.get(cache_key)
        if cached and (now - cached["ts"]) <= cache_ttl:
            return jsonify(cached["data"])

    data = {}
    for cfg in CONFIG.get("snmp_devices", []):
        device_id = str(cfg.get("id"))
        status = _build_snmp_status_snapshot(cfg)
        walk_values = dict(status.get("walk_values", {}) or {})
        if walk_values:
            status["walk_samples"] = [
                {"oid": oid, "value": value}
                for oid, value in list(walk_values.items())[:12]
            ]
        status.pop("walk_values", None)
        status.pop("previous_walk_values", None)
        status.pop("raw_oids", None)
        status["config"] = _build_snmp_config_payload(cfg, compact=compact)
        data[device_id] = _compact_status(status) if compact else status
    with _SNMP_API_CACHE_LOCK:
        _SNMP_API_CACHE[cache_key] = {"data": data, "ts": time.monotonic()}
    return jsonify(data)


@bp.route("/api/snmp/test", methods=["POST"])
@require_permission("system.config")
def api_snmp_test():
    payload = request.json or {}
    device = payload.get("device") if isinstance(payload.get("device"), dict) else payload
    status = poll_snmp_device(device or {})
    ok = bool(status.get("online", False))
    return jsonify(
        {
            "success": ok,
            "status": status,
            "message": "" if ok else status.get("error", "SNMP test failed"),
        }
    )
