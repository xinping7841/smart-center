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
    "hvac": "??",
    "power": "??",
    "light": "??",
    "sequencer": "????",
    "projector": "???",
    "screen": "??",
    "server": "???",
    "automation": "???",
    "system": "??",
    "door": "??",
}

EVENT_TYPE_LABELS = {
    "command": "????",
    "state_change": "????",
    "automation": "???",
    "audit": "??",
    "error": "??",
    "health": "????",
}

SOURCE_LABELS = {
    "user": "??",
    "api": "API",
    "automation": "???",
    "poller": "????",
    "device": "????",
    "external": "????",
    "ha": "Home Assistant",
    "miio": "miio",
    "system": "??",
    "unknown": "??",
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
    cutoff = now_ts - PENDING_TTL_SEC
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


def record_legacy_operation(cab_idx, operation, category="system", status="ok", detail=None, actor=None):
    detail = detail if isinstance(detail, dict) else {}
    source = str(detail.get("source") or "system")
    event_type = str(detail.get("event_type") or "audit")
    record_event(
        category=category or _infer_category(operation),
        event_type=event_type,
        source=source,
        source_detail=(actor or {}).get("username") if isinstance(actor, dict) else "",
        message=str(operation or ""),
        result=status or "ok",
        cab_idx=cab_idx if isinstance(cab_idx, int) else None,
        raw={"legacy": True, "detail": detail, "actor": actor or {}},
    )


def _infer_category(operation):
    text = str(operation or "")
    if "??" in text or "hvac" in text.lower():
        return "hvac"
    if "??" in text or "??" in text or "??" in text or "??" in text:
        return "power"
    if "??" in text:
        return "light"
    if "??" in text or "sequencer" in text.lower():
        return "sequencer"
    if "???" in text or "automation" in text.lower() or "scene" in text.lower():
        return "automation"
    if "??" in text:
        return "projector"
    if "??" in text:
        return "screen"
    if "???" in text:
        return "server"
    if "??" in text:
        return "door"
    return "system"


# Initialize lazily but early enough to fail silently only on individual writes.
try:
    init_event_log_db()
except Exception:
    pass
