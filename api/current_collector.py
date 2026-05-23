# AI_MODULE: current_collector_api
# AI_PURPOSE: 电流采集页面、实时读取、暂停展示、配置保存和组合回路状态接口。
# AI_BOUNDARY: Modbus 协议读取在 current_collector.py；这里负责 API 和页面。
# AI_DATA_FLOW: current_collector.STATE/read -> /api/current-collector/* -> current-collector 前端。
# AI_RUNTIME: 独立电流采集页面轮询，配置中心可调整显示/排序/组合。
# AI_RISK: 中，电流数据参与设备状态推断，配置错误会造成误判。
# AI_COMPAT: channel/group/visible/sort_order 配置和状态字段需兼容。
# AI_SEARCH_KEYWORDS: current collector, current, channel, group, pause, realtime.

import threading
import time
from copy import deepcopy
from datetime import datetime
import ipaddress

from flask import Blueprint, jsonify, render_template, request

from auth.decorators import require_permission
from config import CONFIG, save_config
from current_collector import (
    CurrentCollector,
    CurrentCollectorError,
    DEFAULT_CHANNEL_COUNT,
    DEFAULT_REGISTER_BASE_100X,
    DEFAULT_SCALE_100X,
    ModbusTcpTransport,
    RtuSerialTransport,
    RtuTcpBridgeTransport,
    registers_to_currents,
)
from data_logger import add_log


bp = Blueprint("current_collector", __name__)

DEFAULT_CURRENT_COLLECTOR = {
    "enabled": True,
    "name": "16路电流采集器",
    "source_mode": "poll",
    "transport": "tcp-rtu",
    "host": "192.168.50.109",
    "port": 502,
    "serial_port": "COM7",
    "baudrate": 9600,
    "bytesize": 8,
    "parity": "N",
    "stopbits": 1,
    "slave": 1,
    "register": DEFAULT_REGISTER_BASE_100X,
    "count": DEFAULT_CHANNEL_COUNT,
    "scale": DEFAULT_SCALE_100X,
    "multiplier": 1.0,
    "timeout": 2.0,
    "poll_interval": 5.0,
    "push_stale_seconds": 15.0,
    "push_allowed_hosts": ["127.0.0.1", "::1", "192.168.50.121", "100.122.235.56"],
    "push_token": "",
    "channels": [{"channel": index, "name": f"第{index}路", "visible": True} for index in range(1, 17)],
    "groups": [],
}

STATE_LOCK = threading.RLock()
READ_LOCK = threading.Lock()
STATE = {
    "online": False,
    "snapshot": None,
    "error": "not started",
    "updated_at": "",
    "poll_failures": 0,
    "source": "unknown",
}
POLL_THREAD_STARTED = False
POLL_THREAD_LOCK = threading.Lock()


def _coerce_int(value, default, minimum=None, maximum=None):
    try:
        parsed = int(str(value).strip(), 0)
    except Exception:
        parsed = int(default)
    if minimum is not None:
        parsed = max(int(minimum), parsed)
    if maximum is not None:
        parsed = min(int(maximum), parsed)
    return parsed


def _coerce_float(value, default, minimum=None, maximum=None):
    try:
        parsed = float(str(value).strip())
    except Exception:
        parsed = float(default)
    if minimum is not None:
        parsed = max(float(minimum), parsed)
    if maximum is not None:
        parsed = min(float(maximum), parsed)
    return parsed


def normalize_transport(value):
    raw = str(value or "").strip().lower()
    if raw in {"serial", "rtu", "rtu_serial"}:
        return "serial"
    if raw in {"tcp-rtu", "rtu-tcp", "tcp_bridge", "serial_server", "rtu_tcp"}:
        return "tcp-rtu"
    if raw in {"modbus-tcp", "modbus_tcp", "tcp"}:
        return "modbus-tcp"
    return "tcp-rtu"


def normalize_current_collector_config(raw_config=None):
    cfg = deepcopy(DEFAULT_CURRENT_COLLECTOR)
    if isinstance(raw_config, dict):
        cfg.update(raw_config)
    cfg["enabled"] = bool(cfg.get("enabled", True))
    cfg["name"] = str(cfg.get("name") or DEFAULT_CURRENT_COLLECTOR["name"]).strip() or DEFAULT_CURRENT_COLLECTOR["name"]
    source_mode = str(cfg.get("source_mode") or "poll").strip().lower()
    cfg["source_mode"] = source_mode if source_mode in {"poll", "push"} else "poll"
    cfg["transport"] = normalize_transport(cfg.get("transport"))
    cfg["host"] = str(cfg.get("host") or DEFAULT_CURRENT_COLLECTOR["host"]).strip() or DEFAULT_CURRENT_COLLECTOR["host"]
    cfg["serial_port"] = str(cfg.get("serial_port") or DEFAULT_CURRENT_COLLECTOR["serial_port"]).strip() or DEFAULT_CURRENT_COLLECTOR["serial_port"]
    cfg["port"] = _coerce_int(cfg.get("port"), 502, 1, 65535)
    cfg["baudrate"] = _coerce_int(cfg.get("baudrate"), 9600, 1200, 921600)
    cfg["bytesize"] = _coerce_int(cfg.get("bytesize"), 8, 5, 8)
    cfg["stopbits"] = _coerce_int(cfg.get("stopbits"), 1, 1, 2)
    parity = str(cfg.get("parity") or "N").strip().upper()
    cfg["parity"] = parity if parity in {"N", "E", "O", "M", "S"} else "N"
    cfg["slave"] = _coerce_int(cfg.get("slave"), 1, 1, 247)
    cfg["register"] = _coerce_int(cfg.get("register"), DEFAULT_REGISTER_BASE_100X, 0, 0xFFFF)
    cfg["count"] = _coerce_int(cfg.get("count"), DEFAULT_CHANNEL_COUNT, 1, 32)
    cfg["scale"] = _coerce_float(cfg.get("scale"), DEFAULT_SCALE_100X, 0.001, 1000000.0)
    cfg["multiplier"] = _coerce_float(cfg.get("multiplier"), 1.0, 0.0, 1000000.0)
    cfg["timeout"] = _coerce_float(cfg.get("timeout"), 1.0, 0.1, 10.0)
    cfg["poll_interval"] = _coerce_float(cfg.get("poll_interval"), 2.0, 0.5, 300.0)
    cfg["push_stale_seconds"] = _coerce_float(cfg.get("push_stale_seconds"), 15.0, 2.0, 300.0)
    raw_allowed_hosts = cfg.get("push_allowed_hosts")
    if isinstance(raw_allowed_hosts, str):
        raw_allowed_hosts = [item.strip() for item in raw_allowed_hosts.split(",")]
    if not isinstance(raw_allowed_hosts, list):
        raw_allowed_hosts = DEFAULT_CURRENT_COLLECTOR["push_allowed_hosts"]
    allowed_hosts = []
    for item in raw_allowed_hosts:
        host = str(item or "").strip()
        if host and host not in allowed_hosts:
            allowed_hosts.append(host)
    cfg["push_allowed_hosts"] = allowed_hosts or DEFAULT_CURRENT_COLLECTOR["push_allowed_hosts"].copy()
    cfg["push_token"] = str(cfg.get("push_token") or "").strip()
    raw_channels = cfg.get("channels") if isinstance(cfg.get("channels"), list) else []
    channel_map = {}
    for item in raw_channels:
        if not isinstance(item, dict):
            continue
        channel = _coerce_int(item.get("channel"), 0, 0, 999)
        if channel <= 0:
            continue
        channel_map[channel] = {
            "channel": channel,
            "name": str(item.get("name") or f"第{channel}路").strip() or f"第{channel}路",
            "visible": bool(item.get("visible", True)),
            "sort": _coerce_int(item.get("sort"), channel, 0, 9999),
        }
    cfg["channels"] = [
        channel_map.get(index, {"channel": index, "name": f"第{index}路", "visible": True, "sort": index})
        for index in range(1, cfg["count"] + 1)
    ]
    raw_groups = cfg.get("groups") if isinstance(cfg.get("groups"), list) else []
    groups = []
    for idx, item in enumerate(raw_groups, start=1):
        if not isinstance(item, dict):
            continue
        group_channels = []
        for channel in item.get("channels", []):
            channel_num = _coerce_int(channel, 0, 0, 999)
            if 1 <= channel_num <= cfg["count"] and channel_num not in group_channels:
                group_channels.append(channel_num)
        if not group_channels:
            continue
        groups.append({
            "id": str(item.get("id") or f"group_{idx}").strip() or f"group_{idx}",
            "name": str(item.get("name") or f"组合 {idx}").strip() or f"组合 {idx}",
            "channels": group_channels,
            "visible": bool(item.get("visible", True)),
            "sort": _coerce_int(item.get("sort"), idx, 0, 9999),
        })
    cfg["groups"] = groups
    return cfg


def get_current_collector_config():
    cfg = normalize_current_collector_config(CONFIG.get("current_collector"))
    CONFIG["current_collector"] = cfg
    return cfg


def save_current_collector_config(next_config):
    CONFIG["current_collector"] = normalize_current_collector_config(next_config)
    save_config(CONFIG)
    return CONFIG["current_collector"]


def build_transport(config):
    transport = normalize_transport(config.get("transport"))
    if transport == "serial":
        return RtuSerialTransport(
            config["serial_port"],
            config["baudrate"],
            config["bytesize"],
            config["parity"],
            config["stopbits"],
            config["timeout"],
        )
    if transport == "tcp-rtu":
        return RtuTcpBridgeTransport(config["host"], config["port"], config["timeout"])
    if transport == "modbus-tcp":
        return ModbusTcpTransport(config["host"], config["port"], config["timeout"])
    raise CurrentCollectorError(f"unsupported transport={transport}")


def read_current_once():
    config = get_current_collector_config()
    if config.get("source_mode") == "push":
        raise CurrentCollectorError("current collector is in push mode; waiting for Node-RED report")
    with READ_LOCK:
        with build_transport(config) as transport:
            collector = CurrentCollector(
                transport,
                slave=config["slave"],
                register_base=config["register"],
                channel_count=config["count"],
                scale=config["scale"],
                multiplier=config["multiplier"],
            )
            return collector.read_once().as_dict()


def update_state(snapshot=None, error="", source="poll"):
    with STATE_LOCK:
        STATE["updated_at"] = datetime.now().isoformat(timespec="seconds")
        STATE["source"] = source
        if snapshot is not None:
            STATE["online"] = True
            STATE["snapshot"] = snapshot
            STATE["error"] = ""
            STATE["poll_failures"] = 0
        else:
            STATE["error"] = str(error or "read failed")
            STATE["poll_failures"] = int(STATE.get("poll_failures") or 0) + 1
            if STATE["poll_failures"] >= 3 or STATE.get("snapshot") is None:
                STATE["online"] = False


def state_payload():
    config = get_current_collector_config()
    with STATE_LOCK:
        payload = dict(STATE)
    if config.get("source_mode") == "push" and payload.get("online") and payload.get("updated_at"):
        age = _seconds_since_iso(payload.get("updated_at"))
        if age is not None and age > float(config.get("push_stale_seconds") or 15.0):
            payload["online"] = False
            payload["error"] = f"Node-RED push stale: {round(age, 1)}s"
            payload["stale_seconds"] = round(age, 1)
    payload["enabled"] = bool(config.get("enabled", True))
    payload["config"] = config
    payload["channels"] = build_channel_rows(payload.get("snapshot"), config)
    payload["groups"] = build_group_rows(payload["channels"], config)
    return payload


def _seconds_since_iso(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            now = datetime.now(dt.tzinfo)
        else:
            now = datetime.now()
        return max((now - dt).total_seconds(), 0.0)
    except Exception:
        return None


def _is_push_source_allowed(config):
    token = str(config.get("push_token") or "").strip()
    if token:
        provided = request.headers.get("X-Current-Collector-Token") or request.args.get("token") or ""
        if str(provided).strip() != token:
            return False, "invalid token"
    allowed_hosts = {str(item or "").strip() for item in config.get("push_allowed_hosts", []) if str(item or "").strip()}
    if not allowed_hosts:
        return True, ""
    remote_addr = str(request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",", 1)[0].strip()
    if remote_addr in allowed_hosts:
        return True, ""
    try:
        remote_ip = ipaddress.ip_address(remote_addr)
    except Exception:
        return False, f"source host not allowed: {remote_addr}"
    for item in allowed_hosts:
        try:
            if remote_ip in ipaddress.ip_network(item, strict=False):
                return True, ""
        except Exception:
            continue
    return False, f"source host not allowed: {remote_addr}"


def _coerce_number_list(values, count, *, default=None, digits=3):
    if not isinstance(values, list):
        values = []
    rows = []
    for index in range(count):
        value = values[index] if index < len(values) else default
        if value is None or value == "":
            rows.append(default)
            continue
        try:
            number = float(value)
            rows.append(round(number, digits))
        except Exception:
            rows.append(default)
    return rows


def normalize_push_snapshot(payload, config):
    payload = payload if isinstance(payload, dict) else {}
    count = int(config.get("count") or DEFAULT_CHANNEL_COUNT)
    raw_registers = payload.get("raw_registers")
    currents = payload.get("currents")
    if currents is None and isinstance(payload.get("channels"), dict):
        channels_map = payload.get("channels") or {}
        currents = [channels_map.get(f"C{index:02d}", channels_map.get(str(index))) for index in range(1, count + 1)]
    if raw_registers is not None and currents is None:
        currents = registers_to_currents(raw_registers, config.get("scale"), config.get("multiplier"))
    currents = _coerce_number_list(currents, count, default=None, digits=3)
    raw_registers = _coerce_number_list(raw_registers, count, default=None, digits=0)
    if not any(value is not None for value in currents):
        raise ValueError("push payload must include currents or raw_registers")
    channel_map = {f"C{index + 1:02d}": value for index, value in enumerate(currents)}
    return {
        "online": True,
        "transport": "node-red-push",
        "slave": _coerce_int(payload.get("slave"), config.get("slave"), 1, 247),
        "register_base": payload.get("register_base") or f"0x{int(config.get('register') or 0):04X}",
        "scale": _coerce_float(payload.get("scale"), config.get("scale"), 0.001, 1000000.0),
        "multiplier": _coerce_float(payload.get("multiplier"), config.get("multiplier"), 0.0, 1000000.0),
        "channel_count": count,
        "currents": currents,
        "channels": channel_map,
        "raw_registers": raw_registers,
        "request_hex": str(payload.get("request_hex") or "").strip(),
        "response_hex": str(payload.get("response_hex") or "").strip(),
        "gateway": str(payload.get("gateway") or "node-121").strip() or "node-121",
        "collected_at": str(payload.get("collected_at") or datetime.now().isoformat(timespec="seconds")).strip(),
    }


def build_channel_rows(snapshot, config):
    snapshot = snapshot or {}
    currents = list(snapshot.get("currents") or [])
    raw_registers = list(snapshot.get("raw_registers") or [])
    channels = []
    for item in config.get("channels", []):
        index = int(item.get("channel") or 0)
        if index <= 0:
            continue
        value = currents[index - 1] if index - 1 < len(currents) else None
        raw_value = raw_registers[index - 1] if index - 1 < len(raw_registers) else None
        channels.append({
            "channel": index,
            "name": item.get("name") or f"第{index}路",
            "visible": bool(item.get("visible", True)),
            "sort": int(item.get("sort") or index),
            "current": value,
            "raw_register": raw_value,
        })
    return channels


def build_group_rows(channels, config):
    channel_map = {int(item.get("channel") or 0): item for item in channels}
    groups = []
    for item in sorted(config.get("groups", []), key=lambda g: (int(g.get("sort") or 9999), str(g.get("name") or ""))):
        group_channels = []
        total_current = 0.0
        active_channels = []
        valid_count = 0
        for channel in item.get("channels", []):
            channel_num = int(channel or 0)
            row = channel_map.get(channel_num)
            if not row:
                continue
            current = row.get("current")
            if current is not None:
                try:
                    current_num = float(current)
                except Exception:
                    current_num = 0.0
                total_current += current_num
                valid_count += 1
                if abs(current_num) > 0.001:
                    active_channels.append(channel_num)
            group_channels.append({
                "channel": channel_num,
                "name": row.get("name") or f"第{channel_num}路",
                "current": current,
            })
        groups.append({
            "id": item.get("id"),
            "name": item.get("name") or "组合",
            "visible": bool(item.get("visible", True)),
            "sort": int(item.get("sort") or 9999),
            "channels": group_channels,
            "channel_numbers": [row["channel"] for row in group_channels],
            "active_channels": active_channels,
            "total_current": round(total_current, 3),
            "valid_count": valid_count,
        })
    return groups


def poll_loop():
    while True:
        config = get_current_collector_config()
        if config.get("enabled", True) and config.get("source_mode") != "push":
            try:
                update_state(read_current_once())
            except Exception as exc:
                update_state(error=str(exc))
        time.sleep(float(config.get("poll_interval") or 2.0))


def ensure_poll_thread_started():
    global POLL_THREAD_STARTED
    with POLL_THREAD_LOCK:
        if POLL_THREAD_STARTED:
            return
        thread = threading.Thread(target=poll_loop, name="current-collector-poll", daemon=True)
        thread.start()
        POLL_THREAD_STARTED = True


@bp.route("/current-collector")
@require_permission("meter.view")
def current_collector_page():
    if get_current_collector_config().get("source_mode") != "push":
        ensure_poll_thread_started()
    return render_template("current_collector.html", config=CONFIG)


@bp.route("/api/current-collector/status")
@require_permission("meter.view")
def api_current_collector_status():
    if get_current_collector_config().get("source_mode") != "push":
        ensure_poll_thread_started()
    return jsonify(state_payload())


@bp.route("/api/current-collector/read", methods=["GET", "POST"])
@require_permission("meter.view")
def api_current_collector_read():
    config = get_current_collector_config()
    if not config.get("enabled", True):
        return jsonify({"ok": False, **state_payload(), "message": "采集已关闭"}), 409
    if config.get("source_mode") == "push":
        return jsonify({"ok": True, "message": "push mode uses latest Node-RED report", **state_payload()})
    ensure_poll_thread_started()
    try:
        update_state(read_current_once())
        return jsonify({"ok": True, **state_payload()})
    except Exception as exc:
        update_state(error=str(exc))
        return jsonify({"ok": False, **state_payload()}), 502


@bp.route("/api/current-collector/enabled", methods=["POST"])
@require_permission("meter.config")
def api_current_collector_enabled():
    data = request.get_json(silent=True) or {}
    config = get_current_collector_config()
    config["enabled"] = bool(data.get("enabled"))
    config = save_current_collector_config(config)
    if not config["enabled"]:
        update_state(error="采集已关闭")
        add_log(-1, "[电流采集] 已关闭后台采集")
    else:
        add_log(-1, "[电流采集] 已开启后台采集")
        if config.get("source_mode") != "push":
            try:
                update_state(read_current_once())
            except Exception as exc:
                update_state(error=str(exc))
                return jsonify({"ok": False, **state_payload()}), 502
    return jsonify({"ok": True, **state_payload()})


@bp.route("/api/current-collector/config", methods=["POST"])
@require_permission("meter.config")
def api_current_collector_config():
    data = request.get_json(silent=True) or {}
    current = get_current_collector_config()
    next_config = deepcopy(current)
    for key in (
        "enabled",
        "name",
        "transport",
        "source_mode",
        "host",
        "port",
        "serial_port",
        "baudrate",
        "bytesize",
        "parity",
        "stopbits",
        "slave",
        "register",
        "count",
        "scale",
        "multiplier",
        "timeout",
        "poll_interval",
        "push_stale_seconds",
        "push_allowed_hosts",
        "push_token",
    ):
        if key in data:
            next_config[key] = data[key]
    if isinstance(data.get("channels"), list):
        next_config["channels"] = data["channels"]
    if isinstance(data.get("groups"), list):
        next_config["groups"] = data["groups"]
    try:
        saved = save_current_collector_config(next_config)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc), **state_payload()}), 400
    add_log(-1, f"[电流采集] 已保存配置: {saved.get('source_mode')} {saved.get('transport')} {saved.get('host')}:{saved.get('port')}")
    if saved.get("enabled", True) and saved.get("source_mode") != "push":
        try:
            update_state(read_current_once())
        except Exception as exc:
            update_state(error=str(exc))
            return jsonify({"ok": False, **state_payload()}), 502
    return jsonify({"ok": True, **state_payload()})


@bp.route("/api/current-collector/health")
@require_permission("meter.view")
def api_current_collector_health():
    payload = state_payload()
    return jsonify({"ok": bool(payload.get("online")), "updated_at": payload.get("updated_at"), "error": payload.get("error")})


@bp.route("/api/current-collector/push", methods=["POST"])
def api_current_collector_push():
    config = get_current_collector_config()
    allowed, reason = _is_push_source_allowed(config)
    if not allowed:
        return jsonify({"ok": False, "success": False, "msg": reason}), 403
    if config.get("source_mode") != "push":
        return jsonify({"ok": False, "success": False, "msg": "current collector is not in push mode"}), 409
    if not config.get("enabled", True):
        return jsonify({"ok": False, "success": False, "msg": "current collector disabled"}), 409
    payload = request.get_json(silent=True) or {}
    try:
        snapshot = normalize_push_snapshot(payload, config)
        update_state(snapshot, source="node-red")
    except Exception as exc:
        update_state(error=f"push parse failed: {exc}", source="node-red")
        return jsonify({"ok": False, "success": False, "msg": str(exc), **state_payload()}), 400
    return jsonify({"ok": True, "success": True, "updated_at": STATE.get("updated_at"), "channels": len(snapshot.get("currents") or [])})
