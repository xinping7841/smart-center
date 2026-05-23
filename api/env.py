# AI_MODULE: environment_api
# AI_PURPOSE: 环境传感器状态、光照历史、HA/MQTT/Modbus 环境数据调试接口。
# AI_BOUNDARY: 不负责空调控制；环境数据只作为展示和自动化条件来源。
# AI_DATA_FLOW: ENV_STATUS/HA/MQTT/Modbus -> /api/env/status -> env/hvac/dashboard 前端。
# AI_RUNTIME: 首页、环境页、空调空间卡片和自动化条件会读取。
# AI_RISK: 中，温湿度/光照数据会影响自动化判断，离线和 stale 逻辑要准确。
# AI_COMPAT: env_sensors、features、primary_metric、battery 等字段需保持兼容。
# AI_SEARCH_KEYWORDS: env, temperature, humidity, illuminance, contact, battery, HA.

from copy import deepcopy

from flask import Blueprint, jsonify, request

from config import CONFIG, ENV_STATUS
import modbus_core as mc
from runtime.env_history import build_env_lux_trend, get_env_lux_history, record_env_lux_sample
from services.home_assistant_bridge import get_env_debug as get_ha_env_debug
from services.mqtt_env_bridge import get_env_debug as get_mqtt_env_debug

bp = Blueprint("env", __name__)


@bp.route("/api/env/status")
def api_env_status():
    payload = {}
    for device_id, state in (ENV_STATUS or {}).items():
        item = dict(state or {})
        trend = build_env_lux_trend(
            device_id,
            current_lux=item.get("lux"),
            threshold=None,
            op="<",
        )
        if trend.get("available") or trend.get("estimate_to_threshold_sec") is not None:
            item["lux_trend"] = trend
        history = get_env_lux_history(device_id, limit=12)
        if history:
            item["lux_history"] = history
        payload[str(device_id)] = item
    return jsonify(payload)


def _ensure_env_status(device_id):
    if device_id not in ENV_STATUS:
        ENV_STATUS[device_id] = {
            "online": False,
            "temp": 0,
            "hum": 0,
            "lux": 0,
            "noise": 0,
            "pm25": 0,
            "pm10": 0,
            "pressure": 0,
        }
    return ENV_STATUS[device_id]


def _masked_debug_device(cfg):
    device = deepcopy(cfg or {})
    ha_cfg = device.get("home_assistant")
    if isinstance(ha_cfg, dict) and ha_cfg.get("token"):
        ha_cfg["token"] = "***"
    mqtt_cfg = device.get("mqtt")
    if isinstance(mqtt_cfg, dict) and mqtt_cfg.get("password"):
        mqtt_cfg["password"] = "***"
    return device


@bp.route("/api/env/debug")
def api_env_debug():
    device_id = request.args.get("device_id")
    if not device_id:
        return jsonify({"success": False, "msg": "缺少 device_id 参数"}), 400

    cfg = next((d for d in CONFIG.get("env_sensors", []) if str(d.get("id")) == str(device_id)), None)
    if not cfg:
        return jsonify({"success": False, "msg": "找不到环境传感器配置"}), 404

    source_type = str(cfg.get("source_type") or "modbus").strip().lower()

    if source_type == "mqtt":
        debug = get_mqtt_env_debug(device_id)
        if not debug:
            return jsonify({"success": False, "msg": "MQTT 环境传感器尚未初始化"}), 500
        return jsonify({"success": True, "device": _masked_debug_device(cfg), "debug": debug})

    if source_type in {"home_assistant", "homeassistant", "ha"}:
        return jsonify({"success": True, "device": _masked_debug_device(cfg), "debug": get_ha_env_debug(cfg, CONFIG)})

    start_addr = request.args.get("start", cfg.get("register_start", 500))
    reg_count = request.args.get("count", cfg.get("register_count", 8))
    station_id = cfg.get("station_id", 1)
    ip = cfg.get("ip")
    port = cfg.get("port")
    req = b""

    try:
        start_addr = int(start_addr)
        reg_count = int(reg_count)
        station_id = int(station_id)
        port = int(port)
        client = mc.ModbusClient(ip, port, station_id, protocol="PRSense")
        req = start_addr.to_bytes(2, "big") + reg_count.to_bytes(2, "big")
        raw = client.send(0x03, req)
        parsed = mc.parse_prsense_env(raw) if raw else None

        return jsonify(
            {
                "success": True,
                "device": {
                    "id": cfg.get("id"),
                    "name": cfg.get("name"),
                    "ip": ip,
                    "port": port,
                    "station_id": station_id,
                    "features": cfg.get("features", {}),
                },
                "request": {
                    "function_code": 3,
                    "start_addr": start_addr,
                    "register_count": reg_count,
                    "payload_hex": req.hex(" ").upper() if req else None,
                },
                "response": {
                    "raw_hex": raw.hex(" ").upper() if raw else None,
                    "parsed": parsed,
                },
            }
        )
    except Exception as e:
        return jsonify(
            {
                "success": False,
                "device": {
                    "id": cfg.get("id"),
                    "name": cfg.get("name"),
                    "ip": ip,
                    "port": port,
                    "station_id": station_id,
                    "features": cfg.get("features", {}),
                },
                "request": {
                    "function_code": 3,
                    "start_addr": start_addr,
                    "register_count": reg_count,
                    "payload_hex": req.hex(" ").upper() if req else None,
                },
                "msg": str(e),
            }
        ), 500


@bp.route("/api/env/push", methods=["POST"])
def api_env_push():
    data = request.json or {}
    device_id = str(data.get("device_id") or "").strip()
    if not device_id:
        return jsonify({"success": False, "msg": "缺少 device_id 参数"}), 400

    cfg = next((d for d in CONFIG.get("env_sensors", []) if str(d.get("id")) == device_id), None)
    if not cfg:
        return jsonify({"success": False, "msg": "找不到环境传感器配置"}), 404

    source_type = str(cfg.get("source_type") or "modbus").strip().lower()
    if source_type != "push":
        return jsonify({"success": False, "msg": "该设备不是 push 类型环境传感器"}), 400

    status = _ensure_env_status(device_id)
    field_names = [
        "temp",
        "hum",
        "lux",
        "noise",
        "pm25",
        "pm10",
        "pressure",
        "battery",
        "linkquality",
        "rssi",
        "opening",
        "contact",
        "contact_text",
        "light",
        "light_text",
        "mac_address",
        "device_title",
        "model",
    ]
    updated = {"online": True}

    for field in field_names:
        if field in data:
            value = data.get(field)
            if field in {"opening", "contact", "contact_text", "light", "light_text"}:
                if value is None or value == "" or value == "未知":
                    continue
            updated[field] = value

    updated["updated_at"] = data.get("updated_at") or __import__("datetime").datetime.now().isoformat()
    status.update(updated)
    record_env_lux_sample(device_id, status.get("lux"), sampled_at=updated.get("updated_at"), online=status.get("online"))
    return jsonify({"success": True, "device_id": device_id, "status": status})
