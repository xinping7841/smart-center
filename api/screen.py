# AI_MODULE: screen_api
# AI_PURPOSE: 幕布升降停止控制、状态维护和配置保存接口。
# AI_BOUNDARY: 串口/TCP 命令组装在 screen_core.py，API 负责权限、锁和日志。
# AI_DATA_FLOW: 前端幕布按钮 -> /api/screen/control -> screen_core -> SCREEN_STATUS。
# AI_RUNTIME: 首页/投影相关页面调用。
# AI_RISK: 高，幕布动作是真实机械动作，必须保留锁和操作日志。
# AI_COMPAT: screen id、action、status 字段需兼容现有前端。
# AI_SEARCH_KEYWORDS: screen, lift, stop, up, down, rs232.

from flask import Blueprint, jsonify, request

from audit import log_audit_event
from auth.decorators import require_permission
from auth.operation_lock import acquire_operation_lock, release_operation_lock
from auth.session import get_current_user
from config import CONFIG, save_config
from data_logger import add_log
from runtime.state import SCREEN_STATUS

bp = Blueprint("screen", __name__)


def _find_screen(screen_id):
    return next((s for s in CONFIG.get("screens", []) if str(s.get("id")) == str(screen_id)), None)


def _default_screen_status(error_text="status_not_initialized"):
    return {
        "online": False,
        "position": 0,
        "height": 0,
        "action": "unknown",
        "is_moving": False,
        "remaining_time": 0,
        "error": error_text,
        "status_level": "offline",
        "status_label": "离线",
        "stale": False,
        "poll_failures": 0,
        "last_success_at": None,
        "last_checked_at": None,
        "last_error": error_text,
        "last_error_at": None,
    }


@bp.route("/api/screens")
@require_permission("screen.view")
def api_get_screens():
    from screen_core import get_all_screens

    screens = []
    for screen in get_all_screens():
        item = dict(screen)
        screen_id = str(item.get("id"))
        cached = SCREEN_STATUS.get(screen_id)
        if cached is not None:
            item["status"] = dict(cached)
        else:
            try:
                from screen_core import ScreenDriver

                status = dict(ScreenDriver(screen).get_status() or {})
                status["online"] = True
                status.setdefault("status_level", "online")
                status.setdefault("status_label", "在线")
                status.setdefault("stale", False)
                status.setdefault("poll_failures", 0)
                status.setdefault("last_success_at", None)
                status.setdefault("last_checked_at", None)
                status.setdefault("last_error", "")
                status.setdefault("last_error_at", None)
                item["status"] = status
            except Exception as exc:
                item["status"] = _default_screen_status(str(exc))
        screens.append(item)
    return jsonify({"screens": screens})


@bp.route("/api/screen/control", methods=["POST"])
@require_permission("screen.control")
def api_screen_control():
    from screen_core import ScreenDriver

    data = request.json or {}
    screen_cfg = _find_screen(data.get("screen_id"))
    if not screen_cfg:
        return jsonify({"success": False, "msg": "未找到幕布配置"})

    current_user = get_current_user()
    lock_key = f"screen:{screen_cfg.get('id')}"
    locked, lock_info = acquire_operation_lock(lock_key, current_user.username, "screen_control", timeout_sec=3.0)
    if not locked:
        return jsonify({"success": False, "msg": f"设备正由 {lock_info.get('owner')} 操作，请稍后再试", "error": "device_busy"}), 409
    try:
        driver = ScreenDriver(screen_cfg)
        success, res = driver.execute(data.get("command", {}))
        cmd_name = data.get("command", {}).get("name", "未命名命令")
        log_msg = f"[幕布] 控制 [{screen_cfg.get('name')}] - {cmd_name}: {'成功' if success else '失败'} - {res}"
        add_log(-1, log_msg)
        log_audit_event(
            "screen.command.execute",
            target=str(screen_cfg.get("id")),
            detail={"screen_id": screen_cfg.get("id"), "command": cmd_name, "success": bool(success)},
            status="ok" if success else "error",
        )
        return jsonify({"success": success, "response": res, "status": driver.get_status(), "log": log_msg})
    except Exception as exc:
        error_msg = f"[幕布] 控制 [{screen_cfg.get('name')}] - 异常: {exc}"
        add_log(-1, error_msg)
        log_audit_event(
            "screen.command.execute",
            target=str(screen_cfg.get("id")),
            detail={"screen_id": screen_cfg.get("id"), "error": str(exc)},
            status="error",
        )
        return jsonify({"success": False, "msg": str(exc), "log": error_msg})
    finally:
        release_operation_lock(lock_key, current_user.username)


@bp.route("/api/screen/status")
@require_permission("screen.view")
def api_screen_status():
    screen_id = request.args.get("screen_id")
    screen_cfg = _find_screen(screen_id)
    if not screen_cfg:
        return jsonify({"error": "未找到幕布配置"})
    cached = SCREEN_STATUS.get(str(screen_id))
    if cached is not None:
        return jsonify(dict(cached))
    try:
        from screen_core import ScreenDriver

        status = dict(ScreenDriver(screen_cfg).get_status() or {})
        status["online"] = True
        status.setdefault("status_level", "online")
        status.setdefault("status_label", "在线")
        status.setdefault("stale", False)
        status.setdefault("poll_failures", 0)
        status.setdefault("last_success_at", None)
        status.setdefault("last_checked_at", None)
        status.setdefault("last_error", "")
        status.setdefault("last_error_at", None)
        return jsonify(status)
    except Exception as exc:
        return jsonify(_default_screen_status(str(exc)))


@bp.route("/api/screen/calibrate", methods=["POST"])
@require_permission("screen.control")
def api_screen_calibrate():
    from screen_core import ScreenDriver

    data = request.json or {}
    screen_cfg = _find_screen(data.get("screen_id"))
    if not screen_cfg:
        return jsonify({"success": False, "msg": "未找到幕布配置"})
    current_user = get_current_user()
    lock_key = f"screen_calibrate:{screen_cfg.get('id')}"
    locked, lock_info = acquire_operation_lock(lock_key, current_user.username, "screen_calibrate", timeout_sec=4.0)
    if not locked:
        return jsonify({"success": False, "msg": f"设备正由 {lock_info.get('owner')} 标定，请稍后再试", "error": "device_busy"}), 409
    try:
        driver = ScreenDriver(screen_cfg)
        success, res = driver.calibrate(data.get("position"))
        add_log(-1, f"[幕布] 标定 [{screen_cfg.get('name')}] - 位置: {data.get('position')}%")
        log_audit_event(
            "screen.calibrate",
            target=str(screen_cfg.get("id")),
            detail={"screen_id": screen_cfg.get("id"), "position": data.get("position")},
        )
        return jsonify({"success": success, "response": res, "status": driver.get_status()})
    except Exception as exc:
        return jsonify({"success": False, "msg": str(exc)})
    finally:
        release_operation_lock(lock_key, current_user.username)


@bp.route("/api/screen/config", methods=["POST"])
@require_permission("system.config")
def api_screen_config():
    data = request.json or {}
    screen_id = data.get("screen_id")
    for screen in CONFIG.get("screens", []):
        if str(screen.get("id")) == str(screen_id):
            screen.setdefault("screen_config", {})
            if data.get("total_height") is not None:
                screen["screen_config"]["total_height"] = float(data["total_height"])
            if data.get("total_time") is not None:
                screen["screen_config"]["total_time"] = float(data["total_time"])
            save_config(CONFIG)
            add_log(-1, f"[幕布] 配置 [{screen_id}] - 高度: {data.get('total_height')}m, 时间: {data.get('total_time')}s")
            log_audit_event(
                "screen.config.save",
                target=str(screen_id),
                detail={"screen_id": screen_id, "total_height": data.get("total_height"), "total_time": data.get("total_time")},
            )
            return jsonify({"success": True, "msg": "配置已保存"})
    return jsonify({"success": False, "msg": "未找到幕布配置"})
