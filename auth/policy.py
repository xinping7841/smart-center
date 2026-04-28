from datetime import datetime

from .permissions import PERMISSION_COMPATIBILITY, get_role_permissions, is_control_permission


def _safe_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return bool(default)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return int(default)


def _parse_datetime(value):
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _parse_hhmm(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        hour, minute = text.split(":", 1)
        return _safe_int(hour, -1), _safe_int(minute, -1)
    except Exception:
        return None


def _now_in_time_range(now_dt, start_text, end_text):
    start = _parse_hhmm(start_text)
    end = _parse_hhmm(end_text)
    if not start or not end:
        return True
    start_minutes = start[0] * 60 + start[1]
    end_minutes = end[0] * 60 + end[1]
    now_minutes = now_dt.hour * 60 + now_dt.minute
    if start_minutes <= end_minutes:
        return start_minutes <= now_minutes <= end_minutes
    return now_minutes >= start_minutes or now_minutes <= end_minutes


def _get_schedule_mode(schedule):
    return str((schedule or {}).get("mode") or "always").strip().lower()


def _get_allowed_weekdays(schedule):
    raw = (schedule or {}).get("weekdays")
    if not isinstance(raw, list):
        return []
    allowed = []
    for item in raw:
        idx = _safe_int(item, -1)
        if 0 <= idx <= 6:
            allowed.append(idx)
    return sorted(set(allowed))


def _match_schedule(schedule, now_dt):
    schedule = schedule if isinstance(schedule, dict) else {}
    if not _safe_bool(schedule.get("enabled", False), False):
        return True
    mode = _get_schedule_mode(schedule)
    weekday = now_dt.weekday()
    allowed_weekdays = _get_allowed_weekdays(schedule)
    if mode == "weekdays" and weekday > 4:
        return False
    if mode == "weekends" and weekday < 5:
        return False
    if mode == "custom_days" and allowed_weekdays and weekday not in allowed_weekdays:
        return False
    slots = schedule.get("slots")
    if isinstance(slots, list) and slots:
        enabled_slots = [slot for slot in slots if isinstance(slot, dict) and _safe_bool(slot.get("enabled", True), True)]
        if enabled_slots:
            return any(_now_in_time_range(now_dt, slot.get("start"), slot.get("end")) for slot in enabled_slots)
    return _now_in_time_range(now_dt, schedule.get("start"), schedule.get("end"))


def resolve_permission_grant(user, permission):
    role_permissions = get_role_permissions(getattr(user, "role", "guest"))
    explicit_permissions = set(getattr(user, "permissions", []) or [])
    granted_set = explicit_permissions or role_permissions
    permission_key = str(permission or "").strip()
    granted = permission_key in granted_set or any(alias in granted_set for alias in PERMISSION_COMPATIBILITY.get(permission_key, set()))
    allowed = bool(granted)
    reason = "granted" if allowed else "permission_not_granted"
    flags = getattr(user, "account_flags", {}) if isinstance(getattr(user, "account_flags", {}), dict) else {}
    temporary_access = getattr(user, "temporary_access", {}) if isinstance(getattr(user, "temporary_access", {}), dict) else {}
    control_schedule = getattr(user, "control_schedule", {}) if isinstance(getattr(user, "control_schedule", {}), dict) else {}
    now_dt = datetime.now()

    if _safe_bool(flags.get("frozen", False), False):
        return {"allowed": False, "reason": "account_frozen", "time_window_active": False, "temporary_override": False}
    if _safe_bool(flags.get("temporarily_disabled", False), False):
        return {"allowed": False, "reason": "account_temporarily_disabled", "time_window_active": False, "temporary_override": False}
    disable_until = _parse_datetime(flags.get("disable_until"))
    if disable_until and now_dt <= disable_until:
        return {"allowed": False, "reason": "account_temporarily_disabled_until", "time_window_active": False, "temporary_override": False}

    if not allowed:
        return {"allowed": False, "reason": reason, "time_window_active": False, "temporary_override": False}

    if not is_control_permission(permission):
        return {"allowed": True, "reason": "granted", "time_window_active": True, "temporary_override": False}

    if str(getattr(user, "account_category", "") or "").lower() == "admin" or str(getattr(user, "role", "") or "").lower() == "admin":
        return {"allowed": True, "reason": "admin_bypass", "time_window_active": True, "temporary_override": False}

    temporary_granted = _safe_bool(temporary_access.get("control_enabled", False), False)
    temporary_until = _parse_datetime(temporary_access.get("control_until"))
    if temporary_granted and (temporary_until is None or now_dt <= temporary_until):
        return {"allowed": True, "reason": "temporary_control_access", "time_window_active": True, "temporary_override": True}

    if _safe_bool(temporary_access.get("control_blocked", False), False):
        blocked_until = _parse_datetime(temporary_access.get("control_blocked_until"))
        if blocked_until is None or now_dt <= blocked_until:
            return {"allowed": False, "reason": "temporary_control_blocked", "time_window_active": False, "temporary_override": True}

    matched = _match_schedule(control_schedule, now_dt)
    if not matched:
        return {"allowed": False, "reason": "outside_control_schedule", "time_window_active": False, "temporary_override": False}

    return {"allowed": True, "reason": "within_control_schedule", "time_window_active": True, "temporary_override": False}
