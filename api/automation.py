# AI_MODULE: automation_api
# AI_PURPOSE: 自动化/场景联动规则的状态、日志、开关和配置更新接口。
# AI_BOUNDARY: 条件实时求值和执行状态在 runtime/automation.py；这里保持配置保存和接口兼容。
# AI_DATA_FLOW: CONFIG.automation_rules -> runtime automation snapshot -> /api/automation/status/logs -> 前端节点画布。
# AI_RUNTIME: 自动化页面轮询；配置中心保存规则；后台线程按条件触发场景。
# AI_RISK: 高，规则可能触发空调、灯光、强电、时序电源和场景批量动作。
# AI_COMPAT: 旧规则字段、compound 条件、前置条件和日志字段需要兼容。
# AI_SEARCH_KEYWORDS: automation, scene, rule, condition, trigger, precondition, node canvas.

from datetime import datetime

from flask import Blueprint, jsonify, request

from audit import log_audit_event
from auth.decorators import require_permission
from config import DEFAULT_AUTOMATION_CONDITION, DEFAULT_AUTOMATION_SCHEDULE
from config import CONFIG, save_config
from data_logger import add_log, load_logs
from event_logger import query_events
from runtime.automation import execute_scene, get_automation_runtime_snapshot

bp = Blueprint("automation", __name__)


def _to_int(value, default=0, minimum=None, maximum=None):
    try:
        result = int(float(value))
    except Exception:
        result = int(default)
    if minimum is not None:
        result = max(int(minimum), result)
    if maximum is not None:
        result = min(int(maximum), result)
    return result


def _to_float(value, default=0.0, minimum=None, maximum=None):
    try:
        result = float(value)
    except Exception:
        result = float(default)
    if minimum is not None:
        result = max(float(minimum), result)
    if maximum is not None:
        result = min(float(maximum), result)
    return result


def _normalize_hhmm(value, fallback="00:00"):
    text = str(value or "").strip()
    if not text:
        return fallback
    parts = text.split(":", 1)
    if len(parts) != 2:
        return fallback
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except Exception:
        return fallback
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return fallback
    return f"{hour:02d}:{minute:02d}"


def _parse_log_time(value):
    text = str(value or "").strip()
    if not text:
        return 0.0
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).timestamp()
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except Exception:
            continue
    return 0.0


def _is_automation_log(item):
    operation = str(item.get("operation") or "")
    category = str(item.get("category") or "")
    markers = ("[automation]", "[scene]", "[自动化]", "[场景]")
    if any(marker in operation for marker in markers):
        return True
    return category in {"automation", "scene"}


def _event_to_automation_log(item):
    message = str(item.get("message") or "").strip()
    action = str(item.get("action") or "").strip()
    category = str(item.get("category") or "").strip()
    event_type = str(item.get("event_type") or "").strip()
    source = str(item.get("source") or "").strip()
    operation = message or action or f"[automation] {category or event_type or source}".strip()
    return {
        "time": item.get("time") or "",
        "cab_idx": item.get("cab_idx", -1),
        "operation": operation,
        "category": "automation" if source == "automation" or event_type == "automation" else (category or "automation"),
        "status": item.get("result") or "ok",
        "detail": {
            "event_id": item.get("id"),
            "event_type": event_type,
            "source": source,
            "source_category": category,
            "action": action,
            "device_id": item.get("device_id") or "",
            "device_name": item.get("device_name") or "",
        },
    }


def _sanitize_rule_updates(rule, payload):
    trigger_type = str(payload.get("trigger_type") or rule.get("trigger_type") or "condition").strip().lower()
    if trigger_type not in {"condition", "schedule", "mixed", "compound"}:
        trigger_type = "condition"
    rule["trigger_type"] = trigger_type

    condition = dict(DEFAULT_AUTOMATION_CONDITION)
    condition.update(rule.get("condition") if isinstance(rule.get("condition"), dict) else {})
    incoming_condition = payload.get("condition") if isinstance(payload.get("condition"), dict) else {}
    condition.update(incoming_condition)

    condition["source_type"] = str(condition.get("source_type") or "env").strip() or "env"
    condition["device_id"] = str(condition.get("device_id") or "").strip()
    condition["prop"] = str(condition.get("prop") or "lux").strip() or "lux"
    condition["op"] = str(condition.get("op") or "<").strip() or "<"
    if condition["op"] not in {">", ">=", "<", "<=", "==", "!=", "contains", "is_true", "is_false", "true", "false"}:
        condition["op"] = "<"

    condition["value"] = _to_float(condition.get("value", 0), 0.0, -999999.0, 999999.0)
    condition["debounce_sec"] = _to_int(condition.get("debounce_sec", 0), 0, 0, 86400)
    condition["hysteresis"] = _to_float(condition.get("hysteresis", 0), 0.0, 0.0, 999999.0)
    condition["consecutive_hits"] = _to_int(condition.get("consecutive_hits", 1), 1, 1, 3600)
    crossing_mode = str(condition.get("crossing_mode") or "none").strip().lower()
    if crossing_mode not in {"none", "cross_down", "cross_up"}:
        crossing_mode = "none"
    condition["crossing_mode"] = crossing_mode
    rearm_raw = str(condition.get("rearm_value") or "").strip()
    if rearm_raw:
        try:
            condition["rearm_value"] = _to_float(rearm_raw, 0.0, -999999.0, 999999.0)
        except Exception:
            condition["rearm_value"] = ""
    else:
        condition["rearm_value"] = ""
    condition["window_bootstrap_sec"] = _to_int(condition.get("window_bootstrap_sec", 0), 0, 0, 86400)
    rule["condition"] = condition

    schedule = dict(DEFAULT_AUTOMATION_SCHEDULE)
    schedule.update(rule.get("schedule") if isinstance(rule.get("schedule"), dict) else {})
    incoming_schedule = payload.get("schedule") if isinstance(payload.get("schedule"), dict) else {}
    schedule.update(incoming_schedule)

    day_type = str(schedule.get("day_type") or "everyday").strip().lower()
    if day_type not in {"everyday", "workday", "weekend", "custom"}:
        day_type = "everyday"
    schedule["day_type"] = day_type
    schedule["time"] = _normalize_hhmm(schedule.get("time"), "08:00")
    schedule["time_start"] = _normalize_hhmm(schedule.get("time_start"), "00:00")
    schedule["time_end"] = _normalize_hhmm(schedule.get("time_end"), "23:59")
    days = schedule.get("days") if isinstance(schedule.get("days"), list) else []
    schedule["days"] = [str(item) for item in days if str(item) in {"0", "1", "2", "3", "4", "5", "6"}]
    rule["schedule"] = schedule

    if "action_scene_id" in payload:
        rule["action_scene_id"] = str(payload.get("action_scene_id") or "").strip()

    if "enabled" in payload:
        rule["enabled"] = bool(payload.get("enabled"))


@bp.route("/api/automation/toggle", methods=["POST"])
@require_permission("automation.edit")
def api_automation_toggle():
    data = request.json or {}
    rule_id = data.get("id")
    is_enabled = bool(data.get("enabled"))

    for rule in CONFIG.get("automations", []):
        if str(rule.get("id")) != str(rule_id):
            continue

        rule["enabled"] = is_enabled
        save_config(CONFIG)

        action_text = "启用" if is_enabled else "停用"
        rule_name = str(rule.get("name") or rule_id or "未命名规则")
        add_log(-1, f"[自动化] 规则 [{rule_name}] 已{action_text}")
        log_audit_event(
            "automation.toggle",
            target=str(rule_id or ""),
            detail={"rule_id": rule_id, "enabled": is_enabled, "rule_name": rule_name},
        )
        return jsonify({"success": True})

    log_audit_event(
        "automation.toggle",
        target=str(rule_id or ""),
        detail={"rule_id": rule_id, "enabled": is_enabled, "error": "rule_not_found"},
        status="error",
    )
    return jsonify({"success": False, "msg": "未找到自动化规则"}), 404


@bp.route("/api/automation/test", methods=["POST"])
@require_permission("automation.edit")
def api_automation_test():
    data = request.json or {}
    rule_id = str(data.get("id") or data.get("rule_id") or "").strip()
    if not rule_id:
        return jsonify({"success": False, "ok": False, "msg": "缺少自动化规则ID"}), 400

    rule = next(
        (item for item in CONFIG.get("automations", []) if str(item.get("id") or "").strip() == rule_id),
        None,
    )
    if not rule:
        log_audit_event(
            "automation.test",
            target=rule_id,
            detail={"rule_id": rule_id, "error": "rule_not_found"},
            status="error",
        )
        return jsonify({"success": False, "ok": False, "msg": "未找到自动化规则", "rule_id": rule_id}), 404

    rule_name = str(rule.get("name") or rule_id or "未命名规则")
    scene_id = str(rule.get("action_scene_id") or "").strip()
    if not scene_id:
        message = f"规则 [{rule_name}] 未绑定执行场景"
        add_log(-1, f"[自动化] 测试执行失败: {message}")
        log_audit_event(
            "automation.test",
            target=rule_id,
            detail={"rule_id": rule_id, "rule_name": rule_name, "error": "scene_missing"},
            status="error",
        )
        return (
            jsonify(
                {
                    "success": False,
                    "ok": False,
                    "msg": message,
                    "rule_id": rule_id,
                    "rule_name": rule_name,
                    "scene_id": scene_id,
                }
            ),
            400,
        )

    add_log(-1, f"[自动化] 手动测试规则: [{rule_name}] -> {scene_id}")
    ok, message = execute_scene(scene_id, async_mode=False, return_detail=True)
    ok = bool(ok)
    status = "ok" if ok else "error"
    log_message = message or ("场景执行完成" if ok else "场景执行失败")
    add_log(-1, f"[自动化] 手动测试结果: [{rule_name}] -> {'成功' if ok else '失败'} ({log_message})")
    log_audit_event(
        "automation.test",
        target=rule_id,
        detail={
            "rule_id": rule_id,
            "rule_name": rule_name,
            "scene_id": scene_id,
            "ok": ok,
            "message": log_message,
        },
        status=status,
    )
    return jsonify(
        {
            "success": ok,
            "ok": ok,
            "msg": log_message,
            "rule_id": rule_id,
            "rule_name": rule_name,
            "scene_id": scene_id,
        }
    )


@bp.route("/api/automation/status")
@require_permission("automation.view")
def api_automation_status():
    return jsonify({"ok": True, **get_automation_runtime_snapshot()})


@bp.route("/api/automation/logs")
@require_permission("automation.view")
def api_automation_logs():
    rule_name = str(request.args.get("name") or "").strip()
    limit = _to_int(request.args.get("limit"), 80, 20, 200)
    matched = []
    for item in load_logs(None):
        operation = str(item.get("operation") or "")
        if not _is_automation_log(item):
            continue
        if rule_name and rule_name not in operation:
            continue
        matched.append(item)
    try:
        event_payload = query_events(event_type="automation", limit=limit, offset=0)
        for event in event_payload.get("items", []):
            converted = _event_to_automation_log(event)
            operation = str(converted.get("operation") or "")
            if rule_name and rule_name not in operation:
                continue
            matched.append(converted)
    except Exception:
        pass

    seen = set()
    unique = []
    for item in matched:
        parsed_time = _parse_log_time(item.get("time"))
        key = (
            str(int(parsed_time)) if parsed_time else str(item.get("time") or ""),
            str(item.get("operation") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    matched = unique
    matched.sort(key=lambda entry: (_parse_log_time(entry.get("time")), str(entry.get("operation") or "")), reverse=True)
    return jsonify({"ok": True, "items": matched[:limit], "total": len(matched), "limit": limit})


@bp.route("/api/automation/update", methods=["POST"])
@require_permission("automation.edit")
def api_automation_update():
    data = request.json or {}
    rule_id = str(data.get("id") or "").strip()
    if not rule_id:
        return jsonify({"success": False, "msg": "缺少规则ID"}), 400

    for rule in CONFIG.get("automations", []):
        if str(rule.get("id") or "").strip() != rule_id:
            continue
        _sanitize_rule_updates(rule, data)
        save_config(CONFIG)
        rule_name = str(rule.get("name") or rule_id or "未命名规则")
        add_log(-1, f"[自动化] 规则 [{rule_name}] 条件已更新")
        log_audit_event(
            "automation.update",
            target=rule_id,
            detail={
                "rule_id": rule_id,
                "trigger_type": rule.get("trigger_type"),
                "condition": rule.get("condition"),
                "schedule": rule.get("schedule"),
                "action_scene_id": rule.get("action_scene_id"),
                "enabled": bool(rule.get("enabled")),
            },
        )
        return jsonify({"success": True, "rule": rule})

    log_audit_event(
        "automation.update",
        target=rule_id,
        detail={"rule_id": rule_id, "error": "rule_not_found"},
        status="error",
    )
    return jsonify({"success": False, "msg": "未找到自动化规则"}), 404
