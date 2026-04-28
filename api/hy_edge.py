import json
import os
import threading
import time
from datetime import datetime
from urllib import error, request

from flask import Blueprint, jsonify

from auth.decorators import require_permission
from config import CONFIG

bp = Blueprint("hy_edge", __name__)

_API_CACHE_LOCK = threading.Lock()
_API_CACHE_DATA = None
_API_CACHE_TS = 0.0
_API_CACHE_TTL_SEC = 2.0

_DEFAULT_STATUS_URL = "http://100.114.16.16:1880/edge/status"


def _now_iso():
    return datetime.now().isoformat()


def _safe_float(value, default=None):
    try:
        if value in (None, "", "-", "--"):
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value, default=0):
    number = _safe_float(value, None)
    if number is None:
        return default
    try:
        return int(number)
    except Exception:
        return default


def _fmt_num(value, digits=1, suffix=""):
    if value is None:
        return "--"
    try:
        number = float(value)
    except Exception:
        return str(value)
    if digits == 0:
        text = str(int(round(number)))
    else:
        text = f"{number:.{digits}f}".rstrip("0").rstrip(".")
    return f"{text}{suffix}"


def _fmt_percent(value):
    return _fmt_num(value, 1, "%")


def _fmt_byte_rate_from_bps(value):
    number = _safe_float(value, None)
    if number is None:
        return "--"
    number = max(0.0, number / 8.0)
    units = ["B/s", "KB/s", "MB/s", "GB/s", "TB/s"]
    idx = 0
    while abs(number) >= 1024 and idx < len(units) - 1:
        number /= 1024
        idx += 1
    digits = 0 if idx == 0 or abs(number) >= 100 else (1 if abs(number) >= 10 else 2)
    return f"{number:.{digits}f}".rstrip("0").rstrip(".") + f" {units[idx]}"


def _fmt_version(value):
    text = str(value or "").strip().strip('"')
    return text or "--"


def _fmt_seconds(value):
    if value is None:
        return "--"
    total = _safe_int(value, None)
    if total is None:
        return str(value)
    if total < 60:
        return f"{total}s"
    minutes, seconds = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h"


def _fmt_age(iso_text):
    text = str(iso_text or "").strip()
    if not text:
        return "--"
    try:
        stamp = datetime.fromisoformat(text)
        seconds = max(0, int((datetime.now(stamp.tzinfo) - stamp).total_seconds())) if stamp.tzinfo else max(0, int((datetime.now() - stamp).total_seconds()))
        return _fmt_seconds(seconds)
    except Exception:
        return text


def _build_metric(label, value, level=""):
    return {"label": str(label), "value": str(value), "level": str(level or "")}


def _first_present(payload, *keys):
    for key in keys:
        if payload.get(key) is not None:
            return payload.get(key)
    return None


def _service_text(service):
    service = service if isinstance(service, dict) else {}
    if service.get("active"):
        return "运行中"
    state = str(service.get("state") or "").strip().lower()
    if state in {"failed", "error"}:
        return "异常"
    if state in {"inactive", "dead", "deactivating"}:
        return "停止"
    return "--"


def _service_level(service):
    text = _service_text(service)
    if text == "异常":
        return "error"
    if text == "停止":
        return "warning"
    return ""


_UPS_MODE_LABELS = {
    "power_on_init": "启动中",
    "standby": "待机",
    "bypass": "旁路",
    "online": "在线模式",
    "battery": "电池供电",
    "battery_test": "电池测试",
    "fault": "故障",
    "frequency_convert": "变频模式",
    "eco": "ECO模式",
    "shutdown": "关机",
}

_UPS_ALERT_LABELS = {
    "mains_abnormal": "市电异常",
    "battery_low": "电池低电量",
    "bypass_active": "旁路中",
    "ups_fault": "UPS故障",
    "offline_type": "离线",
    "testing": "测试中",
    "shutdown_active": "关机中",
}


def _ups_mode_text(value):
    text = str(value or "").strip()
    return _UPS_MODE_LABELS.get(text, text or "--")


def _ups_alert_text(value):
    text = str(value or "").strip()
    return _UPS_ALERT_LABELS.get(text, text)


def _config():
    raw = CONFIG.get("hy_edge", {})
    raw = raw if isinstance(raw, dict) else {}
    return {
        "enabled": raw.get("enabled", True) is not False,
        "status_url": str(raw.get("status_url") or os.environ.get("HY_EDGE_STATUS_URL") or _DEFAULT_STATUS_URL).strip(),
        "timeout_sec": max(1.0, float(raw.get("timeout_sec") or os.environ.get("HY_EDGE_STATUS_TIMEOUT_SEC") or 4.0)),
        "title": str(raw.get("title") or "HY506-异地机房").strip() or "HY506-异地机房",
        "tag": str(raw.get("tag") or "HY506").strip() or "HY506",
    }


def _fetch_status(status_url, timeout_sec):
    started_at = time.monotonic()
    req = request.Request(status_url, headers={"Accept": "application/json"})
    with request.urlopen(req, timeout=timeout_sec) as resp:
        body = resp.read()
        code = getattr(resp, "status", 200)
    if code < 200 or code >= 300:
        raise RuntimeError(f"http_{code}")
    payload = json.loads(body.decode("utf-8"))
    return payload, int((time.monotonic() - started_at) * 1000)


def _build_router_card(tag, payload):
    online = bool(payload.get("online"))
    alerts = []
    storage = payload.get("storage") or []
    root_usage = None
    for item in storage:
        if str(item.get("name") or "").strip() == "/":
            root_usage = _safe_float(item.get("used_percent"), None)
            break
    if root_usage is not None and root_usage >= 95:
        alerts.append(f"根分区占用 {_fmt_percent(root_usage)}")
    cpu_idle = _safe_float(payload.get("cpu_idle_percent"), None)
    cpu_used = _safe_float(payload.get("cpu_used_percent"), None)
    if cpu_used is None and cpu_idle is not None:
        cpu_used = max(0, min(100, 100 - cpu_idle))
    mem_used = _safe_float(payload.get("mem_used_percent"), None)
    if mem_used is None:
        mem_total = _safe_float(payload.get("mem_total_kb"), None)
        mem_available = _safe_float(payload.get("mem_available_kb"), None)
        if mem_total and mem_available is not None:
            mem_used = max(0, min(100, ((mem_total - mem_available) / mem_total) * 100))
    if cpu_used is not None and cpu_used >= 85:
        alerts.append(f"CPU 占用 {_fmt_percent(cpu_used)}")
    if mem_used is not None and mem_used >= 85:
        alerts.append(f"内存占用 {_fmt_percent(mem_used)}")
    online_ports = _safe_int(payload.get("interface_online_count"), 0)
    total_ports = _safe_int(payload.get("if_number"), 0)
    if not online_ports:
        online_ports = _safe_int(payload.get("interface_visible_count"), 0)
    wan_out_bps = _first_present(payload, "wan_out_bps", "out_bps")
    wan_in_bps = _first_present(payload, "wan_in_bps", "in_bps")
    return {
        "id": "router",
        "title": "网关_A700S",
        "subtitle": str(payload.get("host") or "--"),
        "kind": "network",
        "online": online,
        "chips": [
            {"text": "A700S", "tone": ""},
            {"text": "在线" if online else "离线", "tone": "online" if online else "error"},
            {"text": _fmt_version(payload.get("sys_name")), "tone": ""},
        ],
        "metrics": [
            _build_metric("CPU占用", _fmt_percent(cpu_used), "warning" if cpu_used is not None and cpu_used >= 85 else ""),
            _build_metric("内存占用", _fmt_percent(mem_used), "warning" if mem_used is not None and mem_used >= 85 else ""),
            _build_metric("WAN上下行", f"↑ {_fmt_byte_rate_from_bps(wan_out_bps)} / ↓ {_fmt_byte_rate_from_bps(wan_in_bps)}"),
            _build_metric("接口在线", f"{_fmt_num(online_ports, 0)} / {_fmt_num(total_ports, 0)}"),
        ],
        "alerts": alerts,
        "note": f"运行 {payload.get('sys_uptime') or '--'}",
    }


def _build_switch_card(tag, payload):
    online = bool(payload.get("online"))
    mac_count = _safe_int(payload.get("bridge_mac_count"), 0)
    interface_count = _safe_int(payload.get("if_number"), 0)
    return {
        "id": "switch",
        "title": "交换机_S7128MT",
        "subtitle": str(payload.get("host") or "--"),
        "kind": "network",
        "online": online,
        "chips": [
            {"text": "S7128MT", "tone": ""},
            {"text": "在线" if online else "离线", "tone": "online" if online else "error"},
            {"text": _fmt_version(payload.get("sys_name")), "tone": ""},
        ],
        "metrics": [
            _build_metric("总接口", _fmt_num(interface_count, 0)),
            _build_metric("VLAN", _fmt_num(len(payload.get("vlans") or []), 0)),
            _build_metric("MAC", _fmt_num(mac_count, 0)),
            _build_metric("可见端口", _fmt_num(payload.get("interface_count_visible"), 0)),
        ],
        "alerts": [],
        "note": f"系统运行 {payload.get('sys_uptime') or '--'}",
    }


def _build_ups_card(tag, payload):
    online = bool(payload.get("online"))
    alerts = [_ups_alert_text(item) for item in (payload.get("status_bits") or {}).get("active_labels") or [] if item != "buzzer_active"]
    load_percent = _safe_float(payload.get("load_percent"), None)
    if load_percent is not None and load_percent >= 80:
        alerts.append(f"UPS 负载 {_fmt_percent(load_percent)}")
    backup_time = _safe_int(payload.get("backup_time_seconds"), 0)
    if online and backup_time > 0 and backup_time <= 600:
        alerts.append(f"后备时间 {_fmt_seconds(backup_time)}")
    return {
        "id": "ups",
        "title": "UPS_C1K",
        "subtitle": "串口采集",
        "kind": "ups",
        "online": online,
        "chips": [
            {"text": "C1K", "tone": ""},
            {"text": "在线" if online else "离线", "tone": "online" if online else "error"},
            {"text": _ups_mode_text(payload.get("system_mode")), "tone": ""},
        ],
        "metrics": [
            _build_metric("输入/输出", f"{_fmt_num(payload.get('input_voltage'), 1, 'V')} / {_fmt_num(payload.get('output_voltage'), 1, 'V')}"),
            _build_metric("电池容量", _fmt_percent(payload.get("battery_capacity_percent"))),
            _build_metric("负载率", _fmt_percent(load_percent), "warning" if load_percent is not None and load_percent >= 80 else ""),
            _build_metric("后备时间", _fmt_seconds(payload.get("backup_time_seconds"))),
        ],
        "alerts": alerts[:4],
        "note": f"温度 {_fmt_num(payload.get('temperature'), 1, '°C')} · 轮询 {_fmt_num(payload.get('poll_cost_ms'), 0, 'ms')}",
    }


def _build_local_card(tag, payload):
    has_local = bool(payload)
    disk_used = _safe_float(payload.get("disk_used_percent"), None)
    mem_used = _safe_float(payload.get("mem_used_percent"), None)
    alerts = []
    if disk_used is not None and disk_used >= 85:
        alerts.append(f"磁盘占用 {_fmt_percent(disk_used)}")
    if mem_used is not None and mem_used >= 85:
        alerts.append(f"内存占用 {_fmt_percent(mem_used)}")
    services = payload.get("services") if isinstance(payload.get("services"), dict) else {}
    node_red = services.get("node_red") or {}
    node_xiaobao = services.get("node_xiaobao") or {}
    if has_local and _service_text(node_red) not in {"运行中", "--"}:
        alerts.append(f"Node-RED {_service_text(node_red)}")
    if has_local and _service_text(node_xiaobao) not in {"运行中", "--"}:
        alerts.append(f"节点小宝 {_service_text(node_xiaobao)}")
    return {
        "id": "local",
        "title": "Ubuntu_254",
        "subtitle": str(payload.get("hostname") or "--"),
        "kind": "host",
        "online": has_local,
        "chips": [
            {"text": "主机", "tone": ""},
            {"text": "在线" if has_local else "离线", "tone": "online" if has_local else "error"},
            {"text": str(payload.get("kernel") or "--"), "tone": ""},
        ],
        "metrics": [
            _build_metric("负载 1/5/15", f"{_fmt_num(payload.get('load_1'))} / {_fmt_num(payload.get('load_5'))} / {_fmt_num(payload.get('load_15'))}"),
            _build_metric("内存", _fmt_percent(mem_used), "warning" if mem_used is not None and mem_used >= 85 else ""),
            _build_metric("Node-RED", _service_text(node_red), _service_level(node_red)),
            _build_metric("节点小宝", _service_text(node_xiaobao), _service_level(node_xiaobao)),
        ],
        "alerts": alerts,
        "note": f"运行 {_fmt_seconds(payload.get('uptime_seconds'))} · 磁盘剩余 {_fmt_num(payload.get('disk_free_gb'), 1, ' GB')}",
    }


def _build_payload(status_url, timeout_sec, title, tag):
    try:
        remote, elapsed_ms = _fetch_status(status_url, timeout_sec)
    except error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        return {
            "enabled": True,
            "online": False,
            "status_level": "offline",
            "status_label": "离线",
            "error": str(reason),
            "fetched_at": _now_iso(),
            "summary": {
                "title": title,
                "tag": tag,
                "card_total": 0,
                "online_count": 0,
                "alert_count": 0,
                "response_time_ms": None,
                "site": tag,
                "cache_mode": "--",
                "high_age_text": "--",
                "low_age_text": "--",
            },
            "cards": [],
            "remote": {},
        }
    except Exception as exc:
        return {
            "enabled": True,
            "online": False,
            "status_level": "offline",
            "status_label": "离线",
            "error": str(exc),
            "fetched_at": _now_iso(),
            "summary": {
                "title": title,
                "tag": tag,
                "card_total": 0,
                "online_count": 0,
                "alert_count": 0,
                "response_time_ms": None,
                "site": tag,
                "cache_mode": "--",
                "high_age_text": "--",
                "low_age_text": "--",
            },
            "cards": [],
            "remote": {},
        }

    devices = dict(remote.get("devices") or {})
    local = dict(remote.get("local") or {})
    cards = [
        _build_router_card(tag, devices.get("router_192_168_9_1") or {}),
        _build_switch_card(tag, devices.get("switch_192_168_9_2") or {}),
        _build_ups_card(tag, devices.get("ups_serial") or {}),
        _build_local_card(tag, local),
    ]
    online_count = sum(1 for item in cards if item.get("online"))
    alert_count = sum(1 for item in cards if item.get("alerts"))
    return {
        "enabled": True,
        "online": True,
        "status_level": "online",
        "status_label": "在线",
        "error": "",
        "fetched_at": _now_iso(),
        "summary": {
            "title": title,
            "tag": tag,
            "card_total": len(cards),
            "online_count": online_count,
            "alert_count": alert_count,
            "response_time_ms": elapsed_ms,
            "site": str(remote.get("site") or tag),
            "cache_mode": str(remote.get("mode") or "--"),
            "high_age_text": _fmt_age((remote.get("cache") or {}).get("high_collected_at")),
            "low_age_text": _fmt_age((remote.get("cache") or {}).get("low_collected_at")),
            "served_at": str(remote.get("served_at") or ""),
        },
        "cards": cards,
        "remote": remote,
    }


@bp.route("/api/hy-edge/status")
@require_permission("snmp.view")
def api_hy_edge_status():
    global _API_CACHE_DATA, _API_CACHE_TS

    cfg = _config()
    if not cfg["enabled"]:
        return jsonify(
            {
                "enabled": False,
                "online": False,
                "status_level": "offline",
                "status_label": "停用",
                "error": "disabled",
                "fetched_at": _now_iso(),
                "summary": {
                    "title": cfg["title"],
                    "tag": cfg["tag"],
                    "card_total": 0,
                    "online_count": 0,
                    "alert_count": 0,
                    "response_time_ms": None,
                    "site": cfg["tag"],
                    "cache_mode": "--",
                    "high_age_text": "--",
                    "low_age_text": "--",
                },
                "cards": [],
                "remote": {},
            }
        )

    now = time.monotonic()
    with _API_CACHE_LOCK:
        if _API_CACHE_DATA is not None and (now - _API_CACHE_TS) <= _API_CACHE_TTL_SEC:
            return jsonify(_API_CACHE_DATA)

    payload = _build_payload(cfg["status_url"], cfg["timeout_sec"], cfg["title"], cfg["tag"])
    payload["config"] = {
        "status_url": cfg["status_url"],
        "timeout_sec": cfg["timeout_sec"],
        "title": cfg["title"],
        "tag": cfg["tag"],
    }

    with _API_CACHE_LOCK:
        _API_CACHE_DATA = payload
        _API_CACHE_TS = time.monotonic()

    return jsonify(payload)
