# AI_MODULE: event_logger
# AI_PURPOSE: Central event-log database writer/query helper for device state changes, controls, audits, and diagnostics.
# AI_BOUNDARY: Does not decide business actions or permissions; callers supply already-classified events and command metadata.
# AI_DATA_FLOW: API/background/service events -> SQLite event log -> query_events and frontend log views.
# AI_RUNTIME: Imported by many modules on node-120; initializes schema lazily under a process lock.
# AI_RISK: Medium. Lost, duplicated, or misclassified events make HA/device freshness and control audits harder to diagnose.
# AI_COMPAT: Preserve event_logs.db schema, category names, and query result fields used by /api/events and dashboards.
# AI_SEARCH_KEYWORDS: event log, audit, SQLite, query_events, device freshness, pending command.
import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta

from paths import EVENT_LOG_DB_FILE, ensure_parent_dir

_DB_PATH = str(EVENT_LOG_DB_FILE)
_LOCK = threading.RLock()
_SCHEMA_READY = False
_PENDING_COMMANDS = []
_PENDING_TTL_SEC = 120


CATEGORY_LABELS = {
    "hvac": "空调",
    "power": "强电",
    "light": "灯光",
    "sequencer": "时序电源",
    "projector": "投影机",
    "screen": "幕布",
    "server": "服务器",
    "automation": "自动化",
    "system": "系统",
    "door": "门禁",
    "meter": "电表",
    "ups": "UPS",
    "snmp": "SNMP",
    "nvr": "监控",
    "current_collector": "电流采集",
    "local_model": "本地模型",
}

EVENT_TYPE_LABELS = {
    "command": "控制命令",
    "state_change": "状态变化",
    "automation": "自动化",
    "audit": "审计",
    "error": "异常",
    "health": "健康检查",
    "config": "配置变更",
}

SOURCE_LABELS = {
    "user": "人工",
    "api": "API",
    "automation": "自动化",
    "poller": "轮询识别",
    "device": "设备回报",
    "external": "外部变化",
    "ha": "Home Assistant",
    "miio": "miio",
    "system": "系统",
    "unknown": "未知",
}


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def new_correlation_id(prefix="evt"):
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _json_dumps(value):
    if value in (None, ""):
        return ""
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return json.dumps(str(value), ensure_ascii=False)


def _json_loads(value, default=None):
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _as_text(value):
    if value is None:
        return ""
    return str(value)


@contextmanager
def _connect():
    ensure_parent_dir(EVENT_LOG_DB_FILE)
    conn = sqlite3.connect(_DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_event_log_db():
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _LOCK:
        if _SCHEMA_READY:
            return
        with _connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS event_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time TEXT NOT NULL,
                    level TEXT NOT NULL DEFAULT 'info',
                    category TEXT NOT NULL DEFAULT 'system',
                    event_type TEXT NOT NULL DEFAULT 'audit',
                    source TEXT NOT NULL DEFAULT 'system',
                    source_detail TEXT NOT NULL DEFAULT '',
                    device_id TEXT NOT NULL DEFAULT '',
                    device_name TEXT NOT NULL DEFAULT '',
                    entity_id TEXT NOT NULL DEFAULT '',
                    channel TEXT NOT NULL DEFAULT '',
                    action TEXT NOT NULL DEFAULT '',
                    old_state TEXT NOT NULL DEFAULT '',
                    new_state TEXT NOT NULL DEFAULT '',
                    message TEXT NOT NULL DEFAULT '',
                    result TEXT NOT NULL DEFAULT '',
                    confidence TEXT NOT NULL DEFAULT '',
                    correlation_id TEXT NOT NULL DEFAULT '',
                    cab_idx INTEGER,
                    changes_json TEXT NOT NULL DEFAULT '',
                    raw_json TEXT NOT NULL DEFAULT '',
                    created_ts REAL NOT NULL
                )
                """
            )
            for idx in [
                "time", "category", "event_type", "source", "device_id", "device_name", "action", "result", "correlation_id"
            ]:
                conn.execute(f"CREATE INDEX IF NOT EXISTS idx_event_logs_{idx} ON event_logs({idx})")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_event_logs_search ON event_logs(category, event_type, source, time)")
        _SCHEMA_READY = True


def _prune_pending(now_ts=None):
    now_ts = float(now_ts or time.time())
    cutoff = now_ts - _PENDING_TTL_SEC
    _PENDING_COMMANDS[:] = [item for item in _PENDING_COMMANDS if float(item.get("ts", 0.0) or 0.0) >= cutoff]


def record_event(
    *,
    category="system",
    event_type="audit",
    source="system",
    message="",
    level="info",
    source_detail="",
    device_id="",
    device_name="",
    entity_id="",
    channel="",
    action="",
    old_state="",
    new_state="",
    result="",
    confidence="",
    correlation_id="",
    cab_idx=None,
    changes=None,
    raw=None,
    register_command=False,
    timestamp=None,
):
    init_event_log_db()
    event_time = timestamp or now_iso()
    corr = str(correlation_id or "").strip()
    if not corr and event_type == "command":
        corr = new_correlation_id(str(category or "evt"))
    row = {
        "time": event_time,
        "level": _as_text(level or "info"),
        "category": _as_text(category or "system"),
        "event_type": _as_text(event_type or "audit"),
        "source": _as_text(source or "system"),
        "source_detail": _as_text(source_detail),
        "device_id": _as_text(device_id),
        "device_name": _as_text(device_name),
        "entity_id": _as_text(entity_id),
        "channel": _as_text(channel),
        "action": _as_text(action),
        "old_state": _as_text(old_state),
        "new_state": _as_text(new_state),
        "message": _as_text(message),
        "result": _as_text(result),
        "confidence": _as_text(confidence),
        "correlation_id": corr,
        "cab_idx": cab_idx if isinstance(cab_idx, int) else None,
        "changes_json": _json_dumps(changes),
        "raw_json": _json_dumps(raw),
        "created_ts": time.time(),
    }
    with _LOCK:
        with _connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO event_logs (
                    time, level, category, event_type, source, source_detail, device_id, device_name,
                    entity_id, channel, action, old_state, new_state, message, result, confidence,
                    correlation_id, cab_idx, changes_json, raw_json, created_ts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["time"], row["level"], row["category"], row["event_type"], row["source"], row["source_detail"],
                    row["device_id"], row["device_name"], row["entity_id"], row["channel"], row["action"], row["old_state"],
                    row["new_state"], row["message"], row["result"], row["confidence"], row["correlation_id"], row["cab_idx"],
                    row["changes_json"], row["raw_json"], row["created_ts"],
                ),
            )
            row["id"] = cur.lastrowid
        if register_command or event_type == "command":
            _prune_pending(row["created_ts"])
            _PENDING_COMMANDS.append({
                "ts": row["created_ts"],
                "time": row["time"],
                "category": row["category"],
                "device_id": row["device_id"],
                "entity_id": row["entity_id"],
                "channel": row["channel"],
                "action": row["action"],
                "correlation_id": row["correlation_id"],
                "source": row["source"],
                "message": row["message"],
            })
    return row


def find_recent_command(category, device_id="", entity_id="", channel="", window_sec=30, actions=None):
    now_ts = time.time()
    action_set = {str(item) for item in actions or [] if str(item)}
    with _LOCK:
        _prune_pending(now_ts)
        for item in reversed(_PENDING_COMMANDS):
            if str(item.get("category")) != str(category):
                continue
            if device_id and str(item.get("device_id")) != str(device_id):
                continue
            if entity_id and str(item.get("entity_id")) != str(entity_id):
                continue
            if channel and str(item.get("channel")) != str(channel):
                continue
            if action_set and str(item.get("action")) not in action_set:
                continue
            if now_ts - float(item.get("ts", 0.0) or 0.0) <= float(window_sec):
                return dict(item)
    return None


def record_state_change(
    *,
    category,
    device_id="",
    device_name="",
    entity_id="",
    channel="",
    old_state="",
    new_state="",
    message="",
    source="poller",
    source_detail="",
    changes=None,
    raw=None,
    cab_idx=None,
    match_window_sec=45,
):
    command = find_recent_command(category, device_id=device_id, entity_id=entity_id, channel=channel, window_sec=match_window_sec)
    if command:
        result = "confirmed"
        confidence = "confirmed"
        correlation_id = command.get("correlation_id", "")
        event_source = command.get("source") or source or "api"
    else:
        result = "external_detected"
        confidence = "unknown"
        correlation_id = ""
        event_source = source or "poller"
    return record_event(
        category=category,
        event_type="state_change",
        source=event_source,
        source_detail=source_detail,
        device_id=device_id,
        device_name=device_name,
        entity_id=entity_id,
        channel=channel,
        old_state=old_state,
        new_state=new_state,
        message=message,
        result=result,
        confidence=confidence,
        correlation_id=correlation_id,
        cab_idx=cab_idx,
        changes=changes,
        raw=raw,
    )


def _row_to_dict(row):
    item = dict(row)
    item["changes"] = _json_loads(item.pop("changes_json", ""), []) or []
    item["raw"] = _json_loads(item.pop("raw_json", ""), {}) or {}
    item["category_label"] = CATEGORY_LABELS.get(item.get("category"), item.get("category") or "")
    item["event_type_label"] = EVENT_TYPE_LABELS.get(item.get("event_type"), item.get("event_type") or "")
    item["source_label"] = SOURCE_LABELS.get(item.get("source"), item.get("source") or "")
    return item


def query_events(
    *,
    category="",
    event_type="",
    source="",
    result="",
    device_id="",
    q="",
    limit=100,
    offset=0,
    hours=None,
):
    init_event_log_db()
    clauses = []
    params = []
    if category:
        clauses.append("category = ?")
        params.append(category)
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)
    if source:
        clauses.append("source = ?")
        params.append(source)
    if result:
        clauses.append("result = ?")
        params.append(result)
    if device_id:
        clauses.append("device_id = ?")
        params.append(device_id)
    if q:
        like = f"%{q}%"
        clauses.append("(message LIKE ? OR device_name LIKE ? OR device_id LIKE ? OR entity_id LIKE ? OR action LIKE ? OR source_detail LIKE ?)")
        params.extend([like, like, like, like, like, like])
    if hours:
        try:
            cutoff = (datetime.now() - timedelta(hours=float(hours))).isoformat(timespec="seconds")
            clauses.append("time >= ?")
            params.append(cutoff)
        except Exception:
            pass
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    safe_limit = max(1, min(int(limit or 100), 500))
    safe_offset = max(0, int(offset or 0))
    with _LOCK:
        with _connect() as conn:
            total = conn.execute(f"SELECT COUNT(*) AS n FROM event_logs{where}", params).fetchone()["n"]
            rows = conn.execute(
                f"SELECT * FROM event_logs{where} ORDER BY time DESC, id DESC LIMIT ? OFFSET ?",
                params + [safe_limit, safe_offset],
            ).fetchall()
    return {"items": [_row_to_dict(row) for row in rows], "total": int(total or 0), "limit": safe_limit, "offset": safe_offset}



def _contains_any(text, needles):
    return any(item and item in text for item in needles)


def _extract_bracket_value(text, marker):
    prefix = f"[{marker}]"
    if prefix not in text:
        return ""
    tail = text.split(prefix, 1)[1].strip()
    if tail.startswith("[") and "]" in tail:
        return tail.split("]", 1)[0].lstrip("[")
    return ""


def _infer_action(text):
    lower = text.lower()
    pairs = [
        ("power_on", ["power_on", "开机", "开启", "打开", "开灯", "合闸", "启动"]),
        ("power_off", ["power_off", "关机", "关闭", "关灯", "断开", "停止"]),
        ("set_temp", ["set_temp", "设定温度", "温度"]),
        ("set_mode", ["set_mode", "模式"]),
        ("set_fan_mode", ["set_fan_mode", "风速", "风量"]),
        ("status_change", ["状态变化", "->", "离线", "在线"]),
        ("scene_start", ["scene] start", "场景", "start:"]),
        ("scene_completed", ["scene] completed", "completed:"]),
        ("automation_triggered", ["automation] triggered", "自动化", "triggered:"]),
        ("config", ["配置", "保存"]),
    ]
    for action, needles in pairs:
        if any(needle.lower() in lower for needle in needles):
            return action
    return ""


def _infer_device_name(text, category):
    lower = text.lower()
    if "[scene]" in lower:
        tail = text.split(":", 1)[1].strip() if ":" in text else text
        return tail[:80]
    if "automation] triggered" in lower:
        if "[" in text and "]" in text:
            parts = text.split("[")
            if len(parts) >= 3 and "]" in parts[2]:
                return parts[2].split("]", 1)[0].strip()
    bracket = _extract_bracket_value(text, CATEGORY_LABELS.get(category, ""))
    if bracket and bracket != CATEGORY_LABELS.get(category):
        return bracket
    if "[" in text and "]" in text:
        parts = [part for part in text.split("[") if "]" in part]
        if len(parts) >= 2:
            maybe = parts[1].split("]", 1)[0].strip()
            if maybe and maybe not in CATEGORY_LABELS.values() and maybe not in {"scene", "automation"}:
                return maybe
    for sep in ("] ", "]", "：", ":"):
        if sep in text:
            tail = text.split(sep, 1)[1].strip()
            for token in (" 已执行", " 控制", " 电源", " - ", ":", "："):
                if token in tail:
                    tail = tail.split(token, 1)[0].strip()
            if 1 <= len(tail) <= 80:
                return tail
    return ""


def infer_legacy_event(operation, category="", status="ok", detail=None):
    text = str(operation or "")
    lower = text.lower()
    detail = detail if isinstance(detail, dict) else {}
    inferred_category = str(category or "").strip()
    if not inferred_category or inferred_category == "system":
        if _contains_any(text, ["空调", "[hvac]"]) or "hvac" in lower:
            inferred_category = "hvac"
        elif _contains_any(text, ["强电", "电柜", "回路", "合闸", "断开"]) or "power" in lower:
            inferred_category = "power"
        elif _contains_any(text, ["灯光", "户外灯", "庭院灯", "开灯", "关灯"]) or "light" in lower:
            inferred_category = "light"
        elif _contains_any(text, ["时序电源", "时序器"]) or "sequencer" in lower:
            inferred_category = "sequencer"
        elif _contains_any(text, ["投影机", "投影"]) or "projector" in lower:
            inferred_category = "projector"
        elif _contains_any(text, ["幕布"]) or "screen" in lower:
            inferred_category = "screen"
        elif _contains_any(text, ["服务器", "主机"]) or "server" in lower:
            inferred_category = "server"
        elif _contains_any(text, ["自动化", "场景联动"]) or "automation" in lower or "[scene]" in lower:
            inferred_category = "automation"
        elif _contains_any(text, ["门禁", "大门"]) or "door" in lower:
            inferred_category = "door"
        elif _contains_any(text, ["电表", "能耗"]) or "meter" in lower:
            inferred_category = "meter"
        elif _contains_any(text, ["UPS"]):
            inferred_category = "ups"
        elif _contains_any(text, ["SNMP", "NAS", "交换机"]):
            inferred_category = "snmp"
        elif _contains_any(text, ["电流采集", "采集器"]):
            inferred_category = "current_collector"
        else:
            inferred_category = "system"

    if "状态变化" in text or "->" in text:
        event_type = "state_change"
        source = "poller"
        result = "external_detected"
    elif "自动化" in text or "automation" in lower or "[scene]" in lower:
        event_type = "automation"
        source = "automation"
        result = status or "ok"
    elif any(token in text for token in ("控制", "执行", "命令", "开机", "关机", "合闸", "断开", "开灯", "关灯")):
        event_type = "command"
        source = str(detail.get("source") or "api")
        result = status or ("success" if "成功" in text or "已执行" in text else "sent")
    elif "失败" in text or "异常" in text or "错误" in text:
        event_type = "error"
        source = str(detail.get("source") or "system")
        result = status or "error"
    else:
        event_type = str(detail.get("event_type") or "audit")
        source = str(detail.get("source") or "system")
        result = status or "ok"

    if "失败" in text or "异常" in text or str(status).lower() in {"error", "failed", "fail"}:
        result = "error" if result in {"ok", "sent"} else result
    if "成功" in text or "已执行" in text:
        result = "success" if event_type == "command" else result

    return {
        "category": inferred_category,
        "event_type": event_type,
        "source": source,
        "device_name": str(detail.get("device_name") or _infer_device_name(text, inferred_category)),
        "device_id": str(detail.get("device_id") or ""),
        "entity_id": str(detail.get("entity_id") or ""),
        "channel": str(detail.get("channel") or ""),
        "action": str(detail.get("action") or _infer_action(text)),
        "result": result,
    }


def record_legacy_operation(cab_idx, operation, category="", status="ok", detail=None, actor=None):
    detail = detail if isinstance(detail, dict) else {}
    actor = actor if isinstance(actor, dict) else {}
    meta = infer_legacy_event(operation, category=category, status=status, detail=detail)
    record_event(
        category=meta["category"],
        event_type=meta["event_type"],
        source=meta["source"],
        source_detail=actor.get("username") or str(detail.get("source_detail") or ""),
        device_id=meta["device_id"],
        device_name=meta["device_name"],
        entity_id=meta["entity_id"],
        channel=meta["channel"],
        action=meta["action"],
        message=str(operation or ""),
        result=meta["result"],
        cab_idx=cab_idx if isinstance(cab_idx, int) else None,
        raw={"legacy": True, "detail": detail, "actor": actor, "inferred": meta},
        register_command=meta["event_type"] == "command",
    )


def _infer_category(operation):
    return infer_legacy_event(operation).get("category") or "system"


# Initialize lazily but early enough to fail silently only on individual writes.
try:
    init_event_log_db()
except Exception:
    pass
