import json
import os
from datetime import datetime

from flask import request

from auth import get_current_user
from paths import AUDIT_LOG_FILE as AUDIT_LOG_PATH, ensure_parent_dir

AUDIT_LOG_FILE = str(AUDIT_LOG_PATH)


def load_audit_logs(limit=200):
    try:
        with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
            rows = json.load(f)
    except Exception:
        rows = []
    if not isinstance(rows, list):
        rows = []
    return rows[: max(1, int(limit or 200))]


def log_audit_event(action, target="", detail=None, status="ok"):
    try:
        with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
            rows = json.load(f)
    except Exception:
        rows = []

    if not isinstance(rows, list):
        rows = []

    user = get_current_user()
    entry = {
        "time": datetime.now().isoformat(),
        "action": str(action or "").strip(),
        "target": str(target or "").strip(),
        "status": str(status or "ok").strip() or "ok",
        "detail": detail if isinstance(detail, dict) else {"message": str(detail or "")},
        "user": {
            "username": user.username,
            "display_name": user.display_name or user.username,
            "role": user.role,
        },
        "request": {
            "method": request.method,
            "path": request.path,
            "remote_addr": request.headers.get("X-Forwarded-For", request.remote_addr or ""),
        },
    }
    rows.insert(0, entry)

    ensure_parent_dir(AUDIT_LOG_PATH)
    with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(rows[:1000], f, ensure_ascii=False, indent=2)
