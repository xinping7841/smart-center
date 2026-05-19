import time
from datetime import datetime

from flask import Blueprint, jsonify, request

from audit import log_audit_event
from auth.decorators import require_permission
from config import CONFIG, save_config
from data_logger import add_log
from services.home_assistant_bridge import control_hvac as ha_control_hvac
from services.home_assistant_bridge import get_hvac_status as get_ha_hvac_status
from services.miio_hvac import miio_hvac_service
from services.xiaomi_cloud import fetch_xiaomi_cloud_devices, filter_xiaomi_devices

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


def _poll_device_status(device):
    protocol = _device_protocol(device)
    if protocol == "miio":
        return miio_hvac_service.get_status(device)
    if protocol in {"home_assistant", "homeassistant", "ha"}:
        return get_ha_hvac_status(device, CONFIG)
    return _default_status(device)


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


def refresh_hvac_status():
    devices = list(CONFIG.get("hvac_devices", []))
    active_ids = {str(item.get("id")) for item in devices}
    for device_id in list(HVAC_STATUS.keys()):
        if device_id not in active_ids:
            HVAC_STATUS.pop(device_id, None)

    for device in devices:
        device_id = str(device.get("id"))
        previous = dict(HVAC_STATUS.get(device_id, {}) or {})
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
    refresh_hvac_status()
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
        log_audit_event("hvac.control", target=str(device_id), detail=detail)
        return jsonify({"success": True, "msg": "控制成功", "result": str(result), "status": refreshed})

    except Exception as exc:
        add_log(-1, f"[空调] 设备 [{device_name}] 控制失败: {exc}")
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
