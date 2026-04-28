from flask import Blueprint, jsonify, request

from audit import log_audit_event
from auth.decorators import require_permission
from auth.operation_lock import acquire_operation_lock, release_operation_lock
from auth.session import get_current_user
from config import CONFIG
from data_logger import add_log
from runtime.state import PROJECTOR_STATUS

bp = Blueprint("projector", __name__)


def _default_projector_status():
    return {
        "online": False,
        "power": "unknown",
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


@bp.route("/api/projector/control", methods=["POST"])
@require_permission("projector.control")
def api_projector_control():
    data = request.json or {}
    proj_cfg = next((p for p in CONFIG.get("projectors", []) if str(p.get("id")) == str(data.get("device_id"))), None)
    if not proj_cfg:
        return jsonify({"success": False, "msg": "未找到投影机配置"})

    from projector_core import ProjectorDriver

    current_user = get_current_user()
    lock_key = f"projector:{proj_cfg.get('id')}"
    locked, lock_info = acquire_operation_lock(lock_key, current_user.username, "projector_control", timeout_sec=3.0)
    if not locked:
        return jsonify({"success": False, "msg": f"设备正由 {lock_info.get('owner')} 操作，请稍后再试", "error": "device_busy"}), 409
    try:
        success, res = ProjectorDriver(proj_cfg).execute(data.get("command", {}))
        cmd_name = data.get("command", {}).get("name", "未命名命令")
        log_msg = (
            f"[投影机] 控制 [{proj_cfg.get('name', proj_cfg.get('id'))}] - {cmd_name}: "
            f"{'成功' if success else '失败'} - {res}"
        )
        add_log(-1, log_msg)
        log_audit_event(
            "projector.command.execute",
            target=str(proj_cfg.get("id")),
            detail={"device_id": proj_cfg.get("id"), "command": cmd_name, "success": bool(success)},
            status="ok" if success else "error",
        )
        return jsonify({"success": success, "response": res, "log": log_msg})
    except Exception as exc:
        error_msg = f"[投影机] 控制 [{proj_cfg.get('name', proj_cfg.get('id'))}] - 异常: {exc}"
        add_log(-1, error_msg)
        log_audit_event(
            "projector.command.execute",
            target=str(proj_cfg.get("id")),
            detail={"device_id": proj_cfg.get("id"), "error": str(exc)},
            status="error",
        )
        return jsonify({"success": False, "msg": str(exc), "log": error_msg})
    finally:
        release_operation_lock(lock_key, current_user.username)


@bp.route("/api/projector/status")
@require_permission("projector.view")
def api_projector_status():
    statuses = {}
    for proj in CONFIG.get("projectors", []):
        proj_id = str(proj.get("id"))
        cached = PROJECTOR_STATUS.get(proj_id)
        if cached is not None:
            statuses[proj_id] = dict(cached)
            continue
        statuses[proj_id] = _default_projector_status()
    return jsonify(statuses)


@bp.route("/api/projector/brands")
@require_permission("projector.view")
def api_projector_brands():
    from projector_core import get_all_brands

    return jsonify({"brands": get_all_brands()})


@bp.route("/api/projector/brand_commands")
@require_permission("projector.view")
def api_projector_brand_commands():
    from projector_core import get_brand_commands

    brand_id = request.args.get("brand_id")
    if not brand_id:
        return jsonify({"error": "请提供 brand_id 参数"}), 400
    return jsonify({"commands": get_brand_commands(brand_id)})


@bp.route("/api/projector/series")
@require_permission("projector.view")
def api_projector_series():
    from projector_core import get_brand_series

    brand_id = request.args.get("brand_id")
    if not brand_id:
        return jsonify({"error": "请提供 brand_id 参数"}), 400
    return jsonify({"series": get_brand_series(brand_id)})


@bp.route("/api/projector/series_info")
@require_permission("projector.view")
def api_projector_series_info():
    from projector_core import get_connection_types, get_series_info

    brand_id = request.args.get("brand_id")
    series_id = request.args.get("series_id")
    if not brand_id or not series_id:
        return jsonify({"error": "请提供 brand_id 和 series_id 参数"}), 400
    return jsonify(
        {
            "series_info": get_series_info(brand_id, series_id),
            "connection_types": get_connection_types(brand_id, series_id),
        }
    )


@bp.route("/api/projector/series_commands")
@require_permission("projector.view")
def api_projector_series_commands():
    from projector_core import get_series_commands

    brand_id = request.args.get("brand_id")
    series_id = request.args.get("series_id")
    if not brand_id or not series_id:
        return jsonify({"error": "请提供 brand_id 和 series_id 参数"}), 400
    return jsonify({"commands": get_series_commands(brand_id, series_id)})
