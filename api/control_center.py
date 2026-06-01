# AI_MODULE: control_center_api
# AI_PURPOSE: 协议控制中心、命令包导入、泛型设备控制和调试执行入口。
# AI_BOUNDARY: 具体协议执行在 control_center_core.py；这里负责权限、锁、配置保存。
# AI_DATA_FLOW: 配置中心/泛型控制页面 -> /api/control_center/* -> control_center_core。
# AI_RUNTIME: 调试和泛型控制按钮调用。
# AI_RISK: 高，可能向 TCP/UDP/串口设备发送真实控制命令。
# AI_COMPAT: command_pack、device_id、command_id 和旧泛型控制字段需保留。
# AI_SEARCH_KEYWORDS: control center, command pack, tcp, udp, serial, generic.

from flask import Blueprint, jsonify, request

from auth.decorators import require_permission
from auth.operation_lock import acquire_operation_lock, release_operation_lock
from auth.session import get_current_user
from config import CONFIG, save_config
from control_center_core import (
    apply_niren_protocol_mode,
    apply_command_pack,
    execute_control,
    execute_control_center_command,
    generate_panel_from_commands,
    import_hirender_xlsx,
    list_builtin_command_packs,
    load_builtin_command_pack,
    load_command_pack,
    normalize_control_center,
)
from data_logger import add_log


bp = Blueprint("control_center", __name__)


def _resolved_config():
    return normalize_control_center(CONFIG.get("control_center"), CONFIG.get("custom_devices"))


def _save_control_center_config(control_center):
    normalized = normalize_control_center(control_center, CONFIG.get("custom_devices"))
    save_config({"control_center": normalized})
    return normalize_control_center(CONFIG.get("control_center"), CONFIG.get("custom_devices"))


@bp.route("/api/control_center/config", methods=["GET"])
@require_permission("control_center.view")
def api_control_center_config():
    return jsonify({"ok": 1, "control_center": _resolved_config()})


@bp.route("/api/control_center/execute", methods=["POST"])
@require_permission("control_center.control")
def api_control_center_execute():
    payload = request.json or {}
    current_user = get_current_user()
    control_id = str(payload.get("control_id") or "").strip()
    command_id = str(payload.get("command_id") or "").strip()
    target_group_id = str(payload.get("target_group_id") or "").strip()
    runtime_params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    value = payload.get("value")
    lock_key = f"control-center:{control_id or f'{command_id}@{target_group_id}'}"
    locked, lock_info = acquire_operation_lock(lock_key, current_user.username, "control_center_execute", timeout_sec=3.0)
    if not locked:
        return jsonify(
            {
                "ok": 0,
                "success": False,
                "error": "device_busy",
                "msg": f"控件正由 {lock_info.get('owner')} 操作，请稍后再试",
            }
        ), 409
    try:
        config = _resolved_config()
        if control_id:
            result = execute_control(config, control_id, params=runtime_params, value=value)
        else:
            result = execute_control_center_command(
                config,
                command_id=command_id,
                target_group_id=target_group_id,
                params=runtime_params,
                value=value,
            )
        add_log(-1, f"[协议控制中心] 执行 {(control_id or command_id or 'unknown')} -> {'成功' if result.get('ok') else '失败'}")
        return jsonify(result)
    finally:
        release_operation_lock(lock_key, current_user.username)


@bp.route("/api/control_center/save", methods=["POST"])
@require_permission("control_center.config")
def api_control_center_save():
    payload = request.json or {}
    control_center = payload.get("control_center")
    if not isinstance(control_center, dict):
        return jsonify({"ok": 0, "msg": "缺少 control_center 配置"}), 400
    saved = _save_control_center_config(control_center)
    add_log(-1, "[协议控制中心] 配置已单独保存")
    return jsonify({"ok": 1, "msg": "协议控制中心配置已保存", "control_center": saved})


@bp.route("/api/control_center/niren/mode", methods=["POST"])
@require_permission("control_center.config")
def api_control_center_niren_mode():
    payload = request.json or {}
    target_group_id = str(payload.get("target_group_id") or "").strip()
    mode = str(payload.get("mode") or "").strip()
    if not target_group_id or not mode:
        return jsonify({"ok": 0, "msg": "缺少 target_group_id 或 mode"}), 400
    try:
        result = apply_niren_protocol_mode(_resolved_config(), target_group_id, mode)
    except ValueError as exc:
        return jsonify({"ok": 0, "msg": str(exc)}), 400
    saved = _save_control_center_config(result.get("control_center"))
    add_log(-1, f"[协议控制中心] 泥人目标组 {target_group_id} 已切换为 {result.get('mode')}")
    return jsonify(
        {
            "ok": 1,
            "msg": "泥人协议模式已更新",
            "mode": result.get("mode"),
            "target_group_id": target_group_id,
            "changed_controls": result.get("changed_controls", 0),
            "control_center": saved,
        }
    )


@bp.route("/api/control_center/packs", methods=["GET"])
@require_permission("control_center.view")
def api_control_center_packs():
    return jsonify({"ok": 1, "packs": list_builtin_command_packs()})


@bp.route("/api/control_center/import/pack", methods=["POST"])
@require_permission("control_center.config")
def api_control_center_import_pack():
    payload = request.json or {}
    overwrite = bool(payload.get("overwrite", False))
    include_panels = bool(payload.get("include_panels", True))
    existing = _resolved_config()

    if payload.get("builtin_pack_id"):
        pack = load_builtin_command_pack(payload.get("builtin_pack_id"))
    elif payload.get("path"):
        pack = load_command_pack(payload.get("path"))
    elif isinstance(payload.get("pack"), dict):
        pack = load_command_pack(payload.get("pack"))
    else:
        return jsonify({"ok": 0, "msg": "缺少内置包 ID、文件路径或 JSON 包内容"}), 400

    applied = apply_command_pack(existing, pack, overwrite=overwrite, include_panels=include_panels)
    saved = _save_control_center_config(applied.get("control_center"))
    pack_meta = applied.get("pack", {})
    add_log(
        -1,
        f"[协议控制中心] 已导入指令包 {pack_meta.get('name') or pack_meta.get('id') or 'unknown'} "
        f"(目标组 {applied['imported'].get('targets', 0)} / 指令 {applied['imported'].get('commands', 0)} / 面板 {applied['imported'].get('panels', 0)})",
    )
    return jsonify(
        {
            "ok": 1,
            "msg": f"已导入指令包：{pack_meta.get('name') or pack_meta.get('id') or 'unknown'}",
            "pack": pack_meta,
            "imported": applied.get("imported", {}),
            "control_center": saved,
        }
    )


@bp.route("/api/control_center/generate_panel", methods=["POST"])
@require_permission("control_center.config")
def api_control_center_generate_panel():
    payload = request.json or {}
    generated = generate_panel_from_commands(
        _resolved_config(),
        category=str(payload.get("category") or "").strip(),
        target_group_id=str(payload.get("target_group_id") or "").strip(),
        panel_name=str(payload.get("panel_name") or "").strip(),
        show_on_home=bool(payload.get("show_on_home", False)),
        command_ids=payload.get("command_ids"),
    )
    saved = _save_control_center_config(generated.get("control_center"))
    add_log(-1, f"[协议控制中心] 已生成控制面板 {generated.get('panel_name')} ({generated.get('control_count', 0)} 个控件)")
    return jsonify(
        {
            "ok": 1,
            "msg": f"已生成控制面板：{generated.get('panel_name')}",
            "panel_id": generated.get("panel_id"),
            "panel_name": generated.get("panel_name"),
            "control_count": generated.get("control_count"),
            "control_center": saved,
        }
    )


@bp.route("/api/control_center/import/hirender", methods=["POST"])
@require_permission("control_center.config")
def api_control_center_import_hirender():
    payload = request.json or {}
    path = str(payload.get("path") or "").strip()
    if not path:
        return jsonify({"ok": 0, "msg": "缺少 Hirender Excel 路径"}), 400

    imported = import_hirender_xlsx(path)
    existing = _resolved_config()
    commands = list(existing.get("command_library", []))
    command_map = {str(item.get("id") or "").strip(): item for item in commands if isinstance(item, dict)}
    imported_count = 0
    for item in imported.get("commands", []):
        command_map[str(item.get("id") or "").strip()] = item
        imported_count += 1
    existing["command_library"] = sorted(command_map.values(), key=lambda row: (str(row.get("category") or ""), str(row.get("name") or "")))

    template_target = imported.get("target_group_template", {})
    targets = list(existing.get("target_groups", []))
    if template_target and not any(str(item.get("id") or "") == str(template_target.get("id") or "") for item in targets):
        targets.append(template_target)
    existing["target_groups"] = targets
    saved = _save_control_center_config(existing)
    add_log(-1, f"[协议控制中心] 已导入 Hirender 指令 {imported_count} 条")
    return jsonify(
        {
            "ok": 1,
            "msg": f"已导入 {imported_count} 条 Hirender 指令",
            "default_port": imported.get("default_port"),
            "target_group_template": template_target,
            "control_center": saved,
        }
    )
