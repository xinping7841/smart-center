# AI_MODULE: universal_control_api
# AI_PURPOSE: 旧泛型控制兼容入口，把历史 universal 请求转到 control_center_core。
# AI_BOUNDARY: 新协议能力应优先放到 control_center_core 和配置中心。
# AI_DATA_FLOW: 旧前端/外部调用 -> /api/universal/control -> control_center_core。
# AI_RUNTIME: 为旧页面和外部系统保留。
# AI_RISK: 高，可能发送真实设备控制命令。
# AI_COMPAT: /api/universal/control 请求格式不能随意破坏。
# AI_SEARCH_KEYWORDS: universal, legacy control, generic device, compatibility.

from flask import Blueprint, jsonify, request

from auth.decorators import require_permission
from auth.operation_lock import acquire_operation_lock, release_operation_lock
from auth.session import get_current_user
from config import CONFIG
from control_center_core import execute_control_center_command, normalize_control_center
from data_logger import add_log

bp = Blueprint('universal', __name__)

@bp.route('/api/universal/control', methods=['POST'])
@require_permission("light.control")
def api_universal_control():
    data = request.json or {}
    dev_cfg = next((d for d in CONFIG.get("custom_devices", []) if str(d.get("id")) == str(data.get("device_id"))), None)
    if not dev_cfg:
        return jsonify({"success": False, "msg": "找不到设备配置"})
    current_user = get_current_user()
    lock_key = f"universal:{dev_cfg.get('id')}"
    locked, lock_info = acquire_operation_lock(lock_key, current_user.username, "universal_control", timeout_sec=3.0)
    if not locked:
        return jsonify({"success": False, "msg": f"设备正由 {lock_info.get('owner')} 操作，请稍后再试", "error": "device_busy"}), 409
    try:
        cmd = data.get("command", {})
        compat_command = {
            "id": "__legacy_runtime_command__",
            "name": "Legacy Runtime Command",
            "protocol": str(dev_cfg.get("interface") or "tcp").strip().lower(),
            "format": str(cmd.get("format") or "str").strip().lower(),
            "payload_template": str(cmd.get("payload") or ""),
            "wait_ms": cmd.get("wait_ms", 0),
            "params": [],
            "line_ending": "none",
            "enabled": True,
        }
        compat_target = {
            "id": "__legacy_runtime_target__",
            "name": str(dev_cfg.get("name") or dev_cfg.get("id") or "legacy"),
            "protocol": str(dev_cfg.get("interface") or "tcp").strip().lower(),
            "mode": "single",
            "host": str(dev_cfg.get("ip") or dev_cfg.get("host") or ""),
            "port": dev_cfg.get("port", 0),
            "com_port": str(dev_cfg.get("com_port") or "COM1"),
            "baudrate": dev_cfg.get("baudrate", 9600),
            "timeout_ms": dev_cfg.get("timeout_ms", 2000),
            "wait_ms": cmd.get("wait_ms", 0),
            "enabled": True,
        }
        compat_config = normalize_control_center(CONFIG.get("control_center"), CONFIG.get("custom_devices"))
        compat_config["command_library"] = [compat_command]
        compat_config["target_groups"] = [compat_target]
        result = execute_control_center_command(
            compat_config,
            "__legacy_runtime_command__",
            "__legacy_runtime_target__",
            params=cmd.get("params") if isinstance(cmd.get("params"), dict) else {},
        )
        success = bool(result.get("ok"))
        first_response = ""
        if result.get("results"):
            first_item = result["results"][0]
            first_response = first_item.get("response") or first_item.get("error") or ""
        add_log(-1, f"[泛型设备] 控制 [{data.get('device_id')}]: {'成功' if success else '失败'}")
        return jsonify({"success": success, "response": first_response, "detail": result})
    finally:
        release_operation_lock(lock_key, current_user.username)
