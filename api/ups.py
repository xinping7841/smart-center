# AI_MODULE: ups_api
# AI_PURPOSE: UPS 状态接口和必要控制动作入口。
# AI_BOUNDARY: UPS 协议解析在 ups_core.py；这里负责权限、锁和前端兼容响应。
# AI_DATA_FLOW: UPS_STATUS/ups_core -> /api/ups/status/control -> static/js/views/ups.js。
# AI_RUNTIME: 首页和 UPS 页面轮询；120 本地 UPS 当前以 RS232 直连为主。
# AI_RISK: 高，UPS 关机/告警涉及供电安全。
# AI_COMPAT: /api/ups/status 的 battery/load/input/output 字段需保持兼容。
# AI_SEARCH_KEYWORDS: ups, rs232, battery, load, shutdown, serial.

from flask import Blueprint, jsonify, request

from audit import log_audit_event
from auth.decorators import require_permission
from auth.operation_lock import acquire_operation_lock, release_operation_lock
from auth.session import get_current_user
from config import CONFIG
from data_logger import add_log
from runtime.control_safety import guard_device_control
from runtime.state import UPS_STATUS

bp = Blueprint("ups", __name__)


def _default_ups_status():
    return {
        "online": False,
        "error": "status_not_initialized",
        "status_level": "offline",
        "status_label": "离线",
        "stale": False,
        "poll_failures": 0,
        "last_success_at": None,
        "last_checked_at": None,
        "last_error": "status_not_initialized",
        "last_error_at": None,
    }


@bp.route("/api/ups/status")
@require_permission("ups.view")
def api_ups_status():
    data = {}
    for cfg in CONFIG.get("ups_devices", []):
        ups_id = str(cfg.get("id"))
        status = dict(UPS_STATUS.get(ups_id, {}))
        if not status:
            status = _default_ups_status()
        status["config"] = {
            "id": ups_id,
            "name": cfg.get("name", ups_id),
            "brand": cfg.get("brand", "SANTAK"),
            "model": cfg.get("model", ""),
            "protocol": cfg.get("protocol", "SANTAK Castle RS232"),
            "comm_mode": cfg.get("comm_mode", "TCP"),
            "ip": cfg.get("ip", ""),
            "port": cfg.get("port", ""),
            "com_port": cfg.get("com_port", ""),
            "shutdown_delay": cfg.get("shutdown_delay", ".3"),
            "visible": cfg.get("visible", True),
        }
        data[ups_id] = status
    return jsonify(data)


@bp.route("/api/ups/control", methods=["POST"])
@require_permission("ups.control")
def api_ups_control():
    data = request.json or {}
    ups_id = str(data.get("id") or "")
    action = str(data.get("action") or "shutdown")
    cfg = next((item for item in CONFIG.get("ups_devices", []) if str(item.get("id")) == ups_id), None)
    if not cfg:
        return jsonify({"success": False, "message": "未找到 UPS 配置"}), 404

    guard = guard_device_control(action, ups_id, payload=data, category="ups")
    if guard:
        response, status_code = guard
        return jsonify(response), status_code

    current_user = get_current_user()
    lock_key = f"ups:{ups_id}"
    locked, lock_info = acquire_operation_lock(lock_key, current_user.username, action, timeout_sec=4.0)
    if not locked:
        return jsonify({"success": False, "message": f"设备正由 {lock_info.get('owner')} 操作，请稍后再试", "error": "device_busy"}), 409
    try:
        from ups_core import UpsDriver

        driver = UpsDriver(cfg)
        if action == "shutdown":
            delay_text = str(data.get("delay") or cfg.get("shutdown_delay", ".3"))
            success, response = driver.shutdown(delay_text)
            if success:
                add_log(-1, f"[UPS] 设备 [{cfg.get('name', ups_id)}] 下发延时关机指令 S{delay_text}")
            log_audit_event(
                "ups.command.execute",
                target=ups_id,
                detail={"ups_id": ups_id, "action": action, "delay": delay_text, "success": bool(success)},
                status="ok" if success else "error",
            )
            return jsonify({"success": success, "response": response, "command": f"S{delay_text}"})
        return jsonify({"success": False, "message": f"不支持的动作: {action}"}), 400
    except Exception as exc:
        log_audit_event("ups.command.execute", target=ups_id, detail={"ups_id": ups_id, "error": str(exc)}, status="error")
        return jsonify({"success": False, "message": str(exc)}), 500
    finally:
        release_operation_lock(lock_key, current_user.username)
