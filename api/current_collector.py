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
)
from data_logger import add_log


bp = Blueprint("current_collector", __name__)

DEFAULT_CURRENT_COLLECTOR = {
    "enabled": True,
    "name": "16路电流采集器",
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


def update_state(snapshot=None, error=""):
    with STATE_LOCK:
        STATE["updated_at"] = datetime.now().isoformat(timespec="seconds")
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
    payload["enabled"] = bool(config.get("enabled", True))
    payload["config"] = config
    payload["channels"] = build_channel_rows(payload.get("snapshot"), config)
    payload["groups"] = build_group_rows(payload["channels"], config)
    return payload


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
        if config.get("enabled", True):
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
    ensure_poll_thread_started()
    return render_template("current_collector.html", config=CONFIG)


@bp.route("/api/current-collector/status")
@require_permission("meter.view")
def api_current_collector_status():
    ensure_poll_thread_started()
    return jsonify(state_payload())


@bp.route("/api/current-collector/read", methods=["GET", "POST"])
@require_permission("meter.view")
def api_current_collector_read():
    ensure_poll_thread_started()
    config = get_current_collector_config()
    if not config.get("enabled", True):
        return jsonify({"ok": False, **state_payload(), "message": "采集已关闭"}), 409
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
    add_log(-1, f"[电流采集] 已保存配置: {saved.get('transport')} {saved.get('host')}:{saved.get('port')}")
    if saved.get("enabled", True):
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
