# AI_MODULE: hvac_api
# AI_PURPOSE: 空调状态读取、控制、Home Assistant/米家设备同步和空调运行状态事件记录。
# AI_BOUNDARY: 米家/HA 协议细节放在 services/home_assistant_bridge.py、services/miio_hvac.py、services/xiaomi_cloud.py。
# AI_DATA_FLOW: CONFIG.hvac_devices/home_assistant -> HA/miio -> HVAC_STATUS -> /api/hvac/status/control/devices。
# AI_RUNTIME: 空调页面、自动化规则和首页环境卡片会读取状态；控制动作会写审计/事件日志。
# AI_RISK: 高，可能真实开关空调；温度自动化依赖这里的状态和控制结果。
# AI_COMPAT: /api/hvac/status、/api/hvac/control、/api/hvac/devices 字段需保持前端和自动化兼容。
# AI_SEARCH_KEYWORDS: hvac, air conditioner, home_assistant, miio, xiaomi, temperature, climate.

import time
from datetime import datetime

from flask import Blueprint, jsonify, request

from audit import log_audit_event
from auth.decorators import require_permission
from config import CONFIG, save_config
from data_logger import add_log
from event_logger import record_event, record_state_change
from services.home_assistant_bridge import control_hvac as ha_control_hvac
from services.home_assistant_bridge import get_hvac_status as get_ha_hvac_status
from services.home_assistant_bridge import maybe_refresh_entity as maybe_refresh_ha_entity
from services.home_assistant_bridge import merge_ha_cfg
from services.miio_hvac import miio_hvac_service
from services.xiaomi_cloud import fetch_xiaomi_cloud_devices, filter_xiaomi_devices
from api.node_red import control_node_red_device, get_node_red_device_status
from log_config import get_logger
_log = get_logger(__name__)

bp = Blueprint("hvac", __name__)


HVAC_STATUS = {}
_STATE_CHANGE_LOG_CACHE = {}
_STATE_CHANGE_VALUE_CACHE = {}


def _now_iso():
    return datetime.now().isoformat()


def _find_device(device_id):
    return next(
        (item for item in CONFIG.get("hvac_devices", []) if str(item.get("id")) == str(device_id)),
        None,
    )


def _device_protocol(device):
    return str(device.get("protocol") or device.get("source_type") or "mock").strip().lower()


def _default_status(device):
    return {
        "id": str(device.get("id")),
        "name": str(device.get("name") or device.get("id") or "未命名空调"),
        "online": False,
        "power": False,
        "temp": None,
        "target_temp": None,
        "mode": "off",
        "updated_at": _now_iso(),
    }


def _node_red_device_id(device):
    return str(device.get("node_red_device_id") or device.get("external_id") or device.get("id") or "").strip()


def _node_red_hvac_status(device):
    node_red_device_id = _node_red_device_id(device)
    status = get_node_red_device_status(node_red_device_id)
    state = status.get("state") if isinstance(status.get("state"), dict) else {}
    metrics = status.get("metrics") if isinstance(status.get("metrics"), dict) else {}
    power_on = str(status.get("status") or "").lower() in {"on", "starting", "pending_ack", "partial"}
    return {
        "id": str(device.get("id") or node_red_device_id),
        "name": str(device.get("name") or status.get("device_name") or node_red_device_id or "Node-RED HVAC"),
        "online": bool(status.get("online")),
        "power": power_on,
        "temp": metrics.get("temp") or metrics.get("temperature") or state.get("temp"),
        "target_temp": state.get("target_temp") or state.get("target_temperature"),
        "mode": state.get("mode") or ("cool" if power_on else "off"),
        "fan_mode": state.get("fan_mode") or state.get("fan_speed"),
        "updated_at": status.get("updated_at") or _now_iso(),
        "display_text": status.get("display_text"),
        "health": status.get("health"),
        "source": "node-red",
    }


def _poll_device_status(device):
    protocol = _device_protocol(device)
    if protocol == "miio":
        return miio_hvac_service.get_status(device)
    if protocol in {"home_assistant", "homeassistant", "ha"}:
        return get_ha_hvac_status(device, CONFIG)
    if protocol in {"node_red", "nodered", "node-red"}:
        return _node_red_hvac_status(device)
    return _default_status(device)


def _maybe_refresh_stale_ha_device(device, status):
    protocol = _device_protocol(device)
    if protocol not in {"home_assistant", "homeassistant", "ha"}:
        return False
    age_sec = status.get("ha_state_age_sec", status.get("age_sec")) if isinstance(status, dict) else None
    try:
        age_value = float(age_sec)
    except Exception:
        _log.debug("error in fallback path", exc_info=True)
        return False
    if age_value < 600:
        return False
    ha_cfg = merge_ha_cfg(device or {}, CONFIG)
    entity_id = str(ha_cfg.get("entity_id") or "").strip()
    return maybe_refresh_ha_entity(entity_id, ha_cfg, min_interval_sec=300)


def _execute_control(device, action, payload):
    protocol = _device_protocol(device)
    if protocol == "miio":
        return miio_hvac_service.control(
            device,
            action,
            temperature=payload.get("temperature"),
            mode=payload.get("mode"),
            fan_mode=payload.get("fan_mode") or payload.get("fan_speed"),
        )
    if protocol in {"home_assistant", "homeassistant", "ha"}:
        return ha_control_hvac(
            device,
            action,
            CONFIG,
            temperature=payload.get("temperature"),
            mode=payload.get("mode"),
            fan_mode=payload.get("fan_mode") or payload.get("fan_speed"),
        )
    if protocol in {"node_red", "nodered", "node-red"}:
        action_map = {"power_on": "on", "on": "on", "power_off": "off", "off": "off", "toggle": "toggle"}
        node_red_action = action_map.get(str(action).strip().lower())
        if not node_red_action:
            raise RuntimeError("Node-RED HVAC only supports on/off/toggle")
        return control_node_red_device(_node_red_device_id(device), node_red_action, source="hvac_api")
    return True, "mock_success", "mock"


def _format_hvac_value(value):
    if isinstance(value, bool):
        return "开" if value else "关"
    if value in (None, ""):
        return "空"
    return str(value)


def _record_detected_change(cache_key, message, min_interval_sec=1.5):
    text = str(message or "").strip()
    if not text:
        return
    now_ts = time.time()
    previous = _STATE_CHANGE_LOG_CACHE.get(cache_key) or {}
    if previous.get("message") == text and (now_ts - float(previous.get("ts", 0.0) or 0.0)) < min_interval_sec:
        return
    _STATE_CHANGE_LOG_CACHE[cache_key] = {"message": text, "ts": now_ts}
    add_log(-1, text)


def _log_hvac_status_change(device, previous, current):
    if not isinstance(current, dict):
        return
    device_id = str(device.get("id") or current.get("id") or "")
    cache_key = f"hvac:{device_id}:status:observed"
    previous = _STATE_CHANGE_VALUE_CACHE.get(cache_key)
    _STATE_CHANGE_VALUE_CACHE[cache_key] = dict(current)
    if not isinstance(previous, dict) or not previous:
        return
    fields = [
        ("online", "在线"),
        ("power", "电源"),
        ("mode", "模式"),
        ("target_temp", "设定温度"),
        ("fan_mode", "风速"),
        ("fan_speed", "风速"),
    ]
    changes = []
    seen_labels = set()
    for key, label in fields:
        if label in seen_labels:
            continue
        old_value = previous.get(key)
        new_value = current.get(key)
        if old_value == new_value:
            continue
        if old_value in (None, "") and new_value in (None, ""):
            continue
        seen_labels.add(label)
        changes.append(f"{label} {_format_hvac_value(old_value)}->{_format_hvac_value(new_value)}")
    if not changes:
        return
    device_name = str(device.get("name") or current.get("name") or device_id or "空调")
    _record_detected_change(
        f"hvac:{device_id}:status",
        f"[状态变化][空调] {device_name} {'、'.join(changes)}（外部/轮询识别）",
    )


def refresh_hvac_status(refresh_stale=False, stale_refresh_limit=3):
    devices = list(CONFIG.get("hvac_devices", []))
    active_ids = {str(item.get("id")) for item in devices}
    for device_id in list(HVAC_STATUS.keys()):
        if device_id not in active_ids:
            HVAC_STATUS.pop(device_id, None)

    stale_refresh_count = 0
    for device in devices:
        device_id = str(device.get("id"))
        previous = dict(HVAC_STATUS.get(device_id, {}) or {})
        current = _poll_device_status(device)
        if refresh_stale and stale_refresh_count < stale_refresh_limit and _maybe_refresh_stale_ha_device(device, current):
            stale_refresh_count += 1
            time.sleep(0.15)
            current = _poll_device_status(device)
        HVAC_STATUS[device_id] = current
        _log_hvac_status_change(device, previous, current)


@bp.route("/api/hvac/devices")
@require_permission("hvac.view")
def get_hvac_devices():
    devices = CONFIG.get("hvac_devices", [])
    return jsonify({"devices": devices})


@bp.route("/api/hvac/status")
@require_permission("hvac.view")
def get_hvac_status():
    refresh_stale = str(request.args.get("refresh_stale") or request.args.get("refresh_ha") or "").strip().lower() in {"1", "true", "yes", "on"}
    refresh_hvac_status(refresh_stale=refresh_stale)
    device_id = request.args.get("device_id")
    if device_id:
        status = HVAC_STATUS.get(str(device_id), {"online": False, "temp": None, "mode": "off"})
        return jsonify(status)
    return jsonify(HVAC_STATUS)


@bp.route("/api/hvac/debug")
@require_permission("hvac.view")
def get_hvac_debug():
    device_id = request.args.get("device_id")
    if not device_id:
        return jsonify({"success": False, "msg": "缺少 device_id 参数"}), 400

    device = _find_device(device_id)
    if not device:
        return jsonify({"success": False, "msg": "找不到空调设备配置"}), 404

    status = _poll_device_status(device)
    return jsonify(
        {
            "success": True,
            "device": device,
            "status": status,
            "miio_available": miio_hvac_service.is_available(),
        }
    )


@bp.route("/api/hvac/control", methods=["POST"])
@require_permission("hvac.control")
def control_hvac():
    data = request.json or {}
    device_id = data.get("device_id")
    action = str(data.get("action") or "").strip()

    device = _find_device(device_id)
    if not device:
        log_audit_event(
            "hvac.control",
            target=str(device_id or ""),
            detail={"device_id": device_id, "action": action, "error": "device_not_found"},
            status="error",
        )
        return jsonify({"success": False, "msg": "找不到空调设备配置"}), 404

    device_name = str(device.get("name") or device_id or "未命名空调")

    correlation_id = record_event(
        category="hvac",
        event_type="command",
        source="api",
        source_detail=str(getattr(getattr(request, "headers", {}), "get", lambda *_: "")("X-Forwarded-For", request.remote_addr) or request.remote_addr or ""),
        device_id=str(device_id or ""),
        device_name=device_name,
        entity_id=str(((device.get("home_assistant") or {}).get("entity_id") or device.get("entity_id") or "")),
        action=action,
        message=f"[空调] 控制命令 [{device_name}] -> {action}",
        result="sent",
        raw={"payload": data},
    ).get("correlation_id", "")

    try:
        ok, result, driver_class = _execute_control(device, action, data)
        if not ok:
            raise RuntimeError(str(result))

        refreshed = _poll_device_status(device)
        HVAC_STATUS[str(device_id)] = refreshed

        detail = {
            "device_id": device_id,
            "device_name": device_name,
            "action": action,
            "driver_class": driver_class,
        }
        if action == "set_temp":
            detail["temperature"] = data.get("temperature")
        if action == "set_mode":
            detail["mode"] = data.get("mode")
        if action == "set_fan_mode":
            detail["fan_mode"] = data.get("fan_mode") or data.get("fan_speed")

        add_log(-1, f"[空调] 控制成功 [{device_name}] -> {action}")
        try:
            record_event(
                category="hvac",
                event_type="command",
                source="api",
                device_id=str(device_id or ""),
                device_name=device_name,
                entity_id=str(((device.get("home_assistant") or {}).get("entity_id") or device.get("entity_id") or "")),
                action=action,
                message=f"[空调] 控制成功 [{device_name}] -> {action}",
                result="success",
                confidence="confirmed",
                correlation_id=correlation_id,
                raw={"detail": detail, "result": str(result), "status": refreshed},
            )
        except Exception:
            _log.debug("non-critical error suppressed", exc_info=True)
            pass
        log_audit_event("hvac.control", target=str(device_id), detail=detail)
        return jsonify({"success": True, "msg": "控制成功", "result": str(result), "status": refreshed})

    except Exception as exc:
        add_log(-1, f"[空调] 设备 [{device_name}] 控制失败: {exc}")
        try:
            record_event(
                category="hvac",
                event_type="command",
                source="api",
                device_id=str(device_id or ""),
                device_name=device_name,
                entity_id=str(((device.get("home_assistant") or {}).get("entity_id") or device.get("entity_id") or "")),
                action=action,
                message=f"[空调] 设备 [{device_name}] 控制失败: {exc}",
                result="failed",
                confidence="confirmed",
                correlation_id=correlation_id,
                raw={"error": str(exc)},
            )
        except Exception:
            _log.debug("non-critical error suppressed", exc_info=True)
            pass
        log_audit_event(
            "hvac.control",
            target=str(device_id),
            detail={"device_id": device_id, "device_name": device_name, "action": action, "error": str(exc)},
            status="error",
        )
        return jsonify({"success": False, "msg": str(exc)}), 500


@bp.route("/api/hvac/config", methods=["POST"])
@require_permission("system.config")
def save_hvac_config():
    data = request.json or {}
    devices = data.get("devices", [])
    CONFIG["hvac_devices"] = devices
    save_config(CONFIG)
    add_log(-1, "[空调] 系统配置已更新")
    log_audit_event(
        "hvac.config.save",
        target="hvac_devices",
        detail={"device_count": len(devices) if isinstance(devices, list) else 0},
    )
    return jsonify({"success": True, "msg": "配置已保存"})


@bp.route("/api/hvac/xiaomi/token_lookup", methods=["POST"])
@require_permission("system.config")
def hvac_xiaomi_token_lookup():
    data = request.json or {}
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "").strip()
    locale = str(data.get("locale") or "all").strip().lower()
    ip = str(data.get("ip") or "").strip()
    model = str(data.get("model") or "").strip()
    keyword = str(data.get("keyword") or "").strip()

    if not username or not password:
        return jsonify({"success": False, "msg": "缺少小米账号或密码"}), 400

    try:
        devices = fetch_xiaomi_cloud_devices(username=username, password=password, locale=locale)
        filtered = filter_xiaomi_devices(devices, ip=ip, model=model, keyword=keyword)
        masked = []
        for item in filtered:
            masked.append(
                {
                    "did": item.get("did"),
                    "name": item.get("name"),
                    "model": item.get("model"),
                    "ip": item.get("ip"),
                    "description": item.get("description"),
                    "mac": item.get("mac"),
                    "locale": item.get("locale"),
                    "token": item.get("token"),
                }
            )

        log_audit_event(
            "hvac.xiaomi.token_lookup",
            target=ip or keyword or model or username,
            detail={"locale": locale, "ip": ip, "model": model, "keyword": keyword, "match_count": len(masked)},
        )
        return jsonify({"success": True, "matches": masked, "count": len(masked)})
    except Exception as exc:
        log_audit_event(
            "hvac.xiaomi.token_lookup",
            target=ip or keyword or model or username,
            detail={"locale": locale, "ip": ip, "model": model, "keyword": keyword, "error": str(exc)},
            status="error",
        )
        return jsonify({"success": False, "msg": str(exc)}), 500
