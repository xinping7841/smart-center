# AI_MODULE: projector_api
# AI_PURPOSE: 投影机状态、控制命令、状态推断和投影机品牌命令库接口。
# AI_BOUNDARY: 协议细节和推断逻辑在 projector_core.py；这里负责权限、锁、审计和响应。
# AI_DATA_FLOW: 前端投影机卡片 -> /api/projector/* -> projector_core -> PROJECTOR_STATUS。
# AI_RUNTIME: 首页/投影机集群页面调用，部分控制会经过 121 网关或串口服务器。
# AI_RISK: 高，开关机会影响真实投影设备，测试前要确认现场允许。
# AI_COMPAT: /api/projector/status/control 的状态字段和 command_id 需保持兼容。
# AI_SEARCH_KEYWORDS: projector, pjlink, rs232, gateway, power on, power off.

from flask import Blueprint, jsonify, request

from audit import log_audit_event
from auth.decorators import require_permission
from auth.operation_lock import acquire_operation_lock, release_operation_lock
from auth.session import get_current_user
from config import CONFIG
from data_logger import add_log
from runtime.state import PROJECTOR_STATUS
from api.node_red import get_node_red_device_status

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


def _merge_hall1_node_red_status(status):
    try:
        node_red = get_node_red_device_status("hall1_projector")
    except Exception as exc:
        status["node_red_error"] = str(exc)
        return status
    if not isinstance(node_red, dict) or not node_red.get("online"):
        return status
    power = node_red.get("power") if isinstance(node_red.get("power"), dict) else {}
    health = node_red.get("health") if isinstance(node_red.get("health"), dict) else {}
    node_power = str(power.get("status") or node_red.get("status") or "unknown").lower()
    if node_power in {"on", "off", "starting", "stopping", "pending_ack", "partial"}:
        status["power"] = node_power
    status["online"] = bool(node_red.get("online"))
    status["status_level"] = "online" if status.get("online") else "offline"
    status["status_label"] = "\u5728\u7ebf" if status.get("online") else "\u79bb\u7ebf"
    status["error"] = "\u6b63\u5e38" if not health.get("alarm") else "\u5f02\u5e38"
    status["gateway_status"] = node_red.get("raw") or node_red
    status["source"] = "node-red"
    status["status_note"] = power.get("note") or health.get("message") or status.get("status_note")
    status["inference_basis"] = "Node-RED \u7535\u6d41\u91c7\u96c6\u63a8\u65ad"
    status["target_online_count"] = (node_red.get("raw") or {}).get("target_online_count", status.get("target_online_count"))
    status["target_total_count"] = (node_red.get("raw") or {}).get("target_total_count", status.get("target_total_count"))
    status["updated_at"] = node_red.get("updated_at") or status.get("updated_at")
    return status


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
        command_payload = data.get("command", {})
        baseline_kw = None
        baseline_meter = None
        if str(proj_cfg.get("control_type") or "") == "inferred_rs232":
            try:
                from projector_core import get_inferred_projector_command_baseline

                baseline_kw, baseline_meter = get_inferred_projector_command_baseline(proj_cfg)
            except Exception:
                baseline_kw, baseline_meter = None, None
        success, res = ProjectorDriver(proj_cfg).execute(command_payload)
        if str(proj_cfg.get("control_type") or "") == "inferred_rs232":
            try:
                from projector_core import infer_rs232_projector_status, record_inferred_projector_command

                record_inferred_projector_command(proj_cfg, command_payload, success, res, baseline_kw, baseline_meter)
                PROJECTOR_STATUS[str(proj_cfg.get("id"))] = infer_rs232_projector_status(proj_cfg)
            except Exception as infer_exc:
                add_log(-1, f"[投影机] 推断状态更新失败 [{proj_cfg.get('name', proj_cfg.get('id'))}]: {infer_exc}")
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
        if str(proj.get("control_type") or "") == "inferred_rs232":
            try:
                from projector_core import infer_rs232_projector_status

                fresh = infer_rs232_projector_status(proj)
                if proj_id == "proj_infer_hall1":
                    fresh = _merge_hall1_node_red_status(dict(fresh))
                PROJECTOR_STATUS[proj_id] = fresh
                statuses[proj_id] = dict(fresh)
                continue
            except Exception as exc:
                cached = PROJECTOR_STATUS.get(proj_id)
                if cached is not None:
                    fallback = dict(cached)
                    fallback["last_error"] = str(exc)
                    fallback["status_level"] = fallback.get("status_level") or "stale"
                    statuses[proj_id] = fallback
                    continue
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
