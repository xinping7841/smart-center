import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in os.sys.path:
    os.sys.path.insert(0, ROOT_DIR)

from . import modbus_core as mc

from .config_store import load_config, save_config
from .reporting import export_reports_snapshot
from .storage import (
    cleanup_history,
    get_daily_record,
    get_history_rows,
    get_last_success_snapshot,
    get_period_start_energy,
    get_recent_power_samples,
    init_daily_record,
    insert_snapshot,
    reset_daily_record,
    update_daily_record,
    upsert_latest,
)

STATE_LOCK = threading.Lock()
LATEST_STATUS = {}
TRANSIENT_HOLD_SECONDS = 180
TRANSIENT_HOLD_FAILURES = 6
MAX_PARALLEL_POLLERS = max(1, min(int(os.getenv("METER_SERVICE_MAX_WORKERS", "3") or 3), 8))
POLL_INTERVAL_SECONDS = max(float(os.getenv("METER_SERVICE_POLL_INTERVAL", "3") or 3), 1.0)
POWER_SMOOTH_ALPHA = max(min(float(os.getenv("METER_SERVICE_POWER_SMOOTH_ALPHA", "0.38") or 0.38), 0.95), 0.05)
ENERGY_DAILY_JUMP_THRESHOLD = max(float(os.getenv("METER_SERVICE_DAILY_JUMP_THRESHOLD_KWH", "300.0") or 300.0), 50.0)


def _safe_float(value, default=0.0):
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value, default=0):
    try:
        if value in (None, ""):
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _median_value(values):
    nums = []
    for item in values or []:
        try:
            nums.append(float(item))
        except Exception:
            continue
    if not nums:
        return 0.0
    nums.sort()
    size = len(nums)
    mid = size // 2
    if size % 2 == 1:
        return nums[mid]
    return (nums[mid - 1] + nums[mid]) / 2.0


def _resolve_data_quality(row):
    if not bool((row or {}).get("online", False)):
        return "offline"
    if bool((row or {}).get("_using_cached_fallback", False)):
        return "fallback"
    if bool((row or {}).get("_degraded", False)):
        return "degraded"
    if _safe_int((row or {}).get("_failure_streak"), 0) > 0:
        return "unstable"
    return "ok"


def _stable_power_value(row):
    return max(
        _safe_float((row or {}).get("stable_realtime_power"), _safe_float((row or {}).get("_stable_power"), _safe_float((row or {}).get("realtime_power"), 0.0))),
        0.0,
    )


def _smooth_realtime_power(merged, current=None):
    merged = merged or {}
    current = current or {}
    meter_id = str(merged.get("id") or merged.get("meter_id") or "").strip()
    raw_power = max(_safe_float(merged.get("realtime_power"), 0.0), 0.0)
    prev_stable = max(_stable_power_value(current), 0.0)

    if prev_stable <= 0 and meter_id:
        history = get_recent_power_samples(meter_id, limit=5, scan_limit=24)
        if history:
            prev_stable = max(_median_value(history), 0.0)

    online = bool(merged.get("online", False))
    degraded = bool(merged.get("_degraded", False)) or bool(merged.get("_using_cached_fallback", False))
    if not online:
        stable = prev_stable if prev_stable > 0 else raw_power
    elif degraded:
        if prev_stable > 0:
            stable = (prev_stable * 0.82) + (raw_power * 0.18)
        else:
            stable = raw_power
    else:
        if prev_stable > 0:
            jump = abs(raw_power - prev_stable)
            jump_threshold = max(prev_stable * 0.8, 3.0)
            alpha = POWER_SMOOTH_ALPHA if jump <= jump_threshold else min(POWER_SMOOTH_ALPHA, 0.28)
            stable = (prev_stable * (1.0 - alpha)) + (raw_power * alpha)
        else:
            stable = raw_power
    stable = round(max(stable, 0.0), 4)
    merged["raw_realtime_power"] = round(raw_power, 4)
    merged["_stable_power"] = stable
    merged["stable_realtime_power"] = stable
    merged["effective_realtime_power"] = stable
    merged["data_quality"] = _resolve_data_quality(merged)
    return merged


def _poll_endpoint_key(job_type, cfg):
    cfg = cfg or {}
    if job_type == "cabinet":
        ip = str(cfg.get("ip", "") or "").strip()
        port = int(cfg.get("port", 502) or 502)
        return f"cabinet::{ip}:{port}"
    source_mode = str(cfg.get("source_mode", "standalone") or "standalone").strip().lower()
    if source_mode == "cabinet_linked" and _safe_int(cfg.get("bind_cabinet_idx", -1), -1) >= 0:
        return f"cabinet-linked::{_safe_int(cfg.get('bind_cabinet_idx', -1), -1)}"
    protocol = str(cfg.get("comm_mode", "TCP") or "TCP").upper()
    if protocol == "COM":
        return f"com::{str(cfg.get('com_port', 'COM1') or 'COM1').strip().upper()}"
    ip = str(cfg.get("ip", "") or "").strip()
    port = int(cfg.get("port", 502) or 502)
    return f"tcp::{ip}:{port}"


def _is_recent_status(current, seconds=20):
    updated_at = str((current or {}).get("updated_at") or "").strip()
    if not updated_at:
        return False
    try:
        age = (datetime.now() - datetime.fromisoformat(updated_at)).total_seconds()
        return age <= max(float(seconds or 0), 0.0)
    except Exception:
        return False


def _get_cached_success_status(meter_id, current=None, max_age_seconds=1800):
    candidates = []
    if current:
        candidates.append(deepcopy(current))
    try:
        persisted = get_last_success_snapshot(meter_id)
    except Exception:
        persisted = None
    if persisted:
        candidates.append(persisted)
    for candidate in candidates:
        if not candidate:
            continue
        if bool(candidate.get("_using_cached_fallback", False)):
            continue
        if _safe_float(candidate.get("electric_energy"), 0.0) <= 0 and _safe_float(candidate.get("realtime_power"), 0.0) <= 0:
            continue
        updated_at = str(candidate.get("updated_at") or "").strip()
        if updated_at:
            try:
                age = (datetime.now() - datetime.fromisoformat(updated_at)).total_seconds()
                if age > max(float(max_age_seconds or 0), 0.0):
                    continue
            except Exception:
                pass
        return deepcopy(candidate)
    return None


def _apply_cached_fallback(merged, cached_row, reason, energy_cache=None):
    if not cached_row:
        return False
    merged.update(deepcopy(cached_row))
    merged["online"] = True
    merged["_using_cached_fallback"] = True
    merged["_degraded"] = True
    merged["error"] = str(reason or "fallback: using last cached value")
    if energy_cache is not None:
        merged["_energy_cache"] = energy_cache
    merged["updated_at"] = datetime.now().isoformat()
    return True


def _mark_poll_success(merged):
    now_text = datetime.now().isoformat()
    merged["_failure_streak"] = 0
    merged["_last_success_at"] = now_text
    merged["_using_cached_fallback"] = False
    merged["_degraded"] = False
    merged["updated_at"] = now_text


def _current_failure_streak(current):
    return _safe_int((current or {}).get("_failure_streak"), 0)


def _can_hold_transient_online(current, grace_seconds=TRANSIENT_HOLD_SECONDS, max_failures=TRANSIENT_HOLD_FAILURES):
    if not current or not bool(current.get("online", False)):
        return False
    failure_streak = _current_failure_streak(current)
    if failure_streak >= max(int(max_failures or 0), 0):
        return False
    last_success_at = str(current.get("_last_success_at") or current.get("updated_at") or "").strip()
    if not last_success_at:
        return False
    try:
        age = (datetime.now() - datetime.fromisoformat(last_success_at)).total_seconds()
        return age <= max(float(grace_seconds or 0), 0.0)
    except Exception:
        return False


def _apply_transient_hold(merged, current, reason, energy_cache=None):
    if not _can_hold_transient_online(current):
        return False
    merged.update(deepcopy(current))
    merged["online"] = True
    merged["_using_cached_fallback"] = True
    merged["_degraded"] = True
    merged["_failure_streak"] = _current_failure_streak(current) + 1
    merged["error"] = str(reason or "fallback: transient communication jitter")
    if energy_cache is not None:
        merged["_energy_cache"] = energy_cache
    merged["updated_at"] = datetime.now().isoformat()
    return True


def _meter_sort_value(row):
    try:
        return int(row.get("sort_order", row.get("meter_sort_order", 999)) or 999)
    except Exception:
        return 999


def _sort_rows(rows):
    return sorted(rows, key=lambda row: (_meter_sort_value(row), str(row.get("display_name") or row.get("id") or "")))


def _serialize_type_counts(rows):
    counts = {}
    for row in rows:
        key = str(row.get("meter_mode") or "other")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _normalize_period_rows(rows, mode):
    grouped = {}
    for row in rows:
        date_text = str(row.get("date") or "")
        if len(date_text) != 10:
            continue
        if mode == "month":
            key = date_text[:7]
        elif mode == "week":
            dt = datetime.strptime(date_text, "%Y-%m-%d").date()
            year, week, _ = dt.isocalendar()
            key = f"{year}-W{week:02d}"
        else:
            key = date_text
        grouped[key] = grouped.get(key, 0.0) + _safe_float(row.get("consume"), 0.0)
    return [{"period": key, "consume": round(grouped[key], 4)} for key in sorted(grouped.keys())]


def _compare_with_previous(rows):
    if len(rows) < 2:
        current = _safe_float(rows[-1]["consume"], 0.0) if rows else 0.0
        return {"current": round(current, 4), "previous": 0.0, "delta": round(current, 4), "delta_pct": None, "trend": "flat"}
    current = _safe_float(rows[-1]["consume"], 0.0)
    previous = _safe_float(rows[-2]["consume"], 0.0)
    delta = current - previous
    delta_pct = round(delta / previous * 100.0, 2) if previous > 0 else None
    return {"current": round(current, 4), "previous": round(previous, 4), "delta": round(delta, 4), "delta_pct": delta_pct, "trend": "up" if delta > 0 else ("down" if delta < 0 else "flat")}


def _resolve_history_energy_cap(target_rows, total_energy, display_total_energy, effective_total_energy):
    row_cap = sum(
        max(
            _safe_float(row.get("raw_electric_energy"), 0.0),
            _safe_float(row.get("electric_energy"), 0.0),
            _safe_float(row.get("display_electric_energy"), 0.0),
            _safe_float(row.get("effective_electric_energy"), 0.0),
        )
        for row in (target_rows or [])
    )
    if row_cap > 0:
        return row_cap
    return max(
        _safe_float(total_energy, 0.0),
        _safe_float(display_total_energy, 0.0),
        _safe_float(effective_total_energy, 0.0),
        0.0,
    )


def _is_unreasonable_history_consume(consume, energy_cap):
    value = _safe_float(consume, 0.0)
    cap = _safe_float(energy_cap, 0.0)
    if value <= 0 or cap <= 0:
        return False
    return value > (cap * 1.2)


def _sanitize_history_rows(daily_rows, period, energy_cap):
    cleaned_rows = []
    outlier_dates = []
    for row in daily_rows or []:
        item = dict(row or {})
        consume = _safe_float(item.get("consume"), 0.0)
        if _is_unreasonable_history_consume(consume, energy_cap):
            item["consume"] = 0.0
            item["_outlier"] = True
            outlier_dates.append(str(item.get("date") or ""))
        else:
            item["consume"] = round(max(consume, 0.0), 4)
        cleaned_rows.append(item)
    trend_breakdown = {
        "daily": [{"period": item.get("date") or "", "consume": item.get("consume", 0.0)} for item in cleaned_rows],
        "weekly": _normalize_period_rows(cleaned_rows, "week"),
        "monthly": _normalize_period_rows(cleaned_rows, "month"),
    }
    period_key = "weekly" if period == "week" else ("monthly" if period == "month" else "daily")
    comparison = _compare_with_previous(trend_breakdown.get(period_key, []))
    comparison["valid"] = not any(bool(item.get("_outlier")) for item in cleaned_rows[-2:])
    if not comparison["valid"]:
        comparison["reason"] = "history_outlier"
    return cleaned_rows, trend_breakdown, comparison, outlier_dates


def _apply_display_reset(value, meter_statistics):
    numeric = _safe_float(value, 0.0)
    reset_state = _resolve_display_reset_state(meter_statistics)
    if not reset_state.get("applied"):
        return round(numeric, 4)
    baseline_value = _safe_float(reset_state.get("value"), 0.0)
    return round(max(numeric - baseline_value, 0.0), 4)


def _normalize_display_reset_meter_values(meter_values):
    normalized = {}
    if not isinstance(meter_values, dict):
        return normalized
    for key, value in meter_values.items():
        text = str(key or "").strip()
        if not text:
            continue
        normalized[text] = round(_safe_float(value, 0.0), 4)
    return normalized


def _normalize_display_reset(meter_statistics):
    meter_statistics = meter_statistics or {}
    display_reset = meter_statistics.get("display_reset", {})
    if not isinstance(display_reset, dict):
        display_reset = {}
    enabled = bool(display_reset.get("enabled", meter_statistics.get("display_reset_enabled", False)))
    from_text = str(display_reset.get("from") or meter_statistics.get("display_reset_from") or "").strip()
    value = round(_safe_float(display_reset.get("value"), 0.0), 4)
    captured_at = str(display_reset.get("captured_at") or "").strip()
    pending = bool(display_reset.get("pending", False))
    if enabled and from_text and not captured_at and value <= 0:
        pending = True
    elif value > 0 and not captured_at and not pending:
        captured_at = from_text
    return {
        "enabled": enabled,
        "from": from_text,
        "value": value,
        "pending": pending,
        "captured_at": captured_at,
        "meter_values": _normalize_display_reset_meter_values(display_reset.get("meter_values")),
    }


def _resolve_display_reset_state(meter_statistics, now_text=None):
    baseline = _normalize_display_reset(meter_statistics)
    current_text = str(now_text or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    due = bool(baseline.get("enabled") and baseline.get("from") and current_text >= str(baseline.get("from")))
    applied = bool(due and not baseline.get("pending") and (baseline.get("captured_at") or baseline.get("value") > 0))
    state = dict(baseline)
    state["due"] = due
    state["applied"] = applied
    state["pending_capture"] = bool(baseline.get("pending") and due)
    state["baseline_meter_count"] = len(baseline.get("meter_values", {}))
    return state


def _collect_display_reset_meter_values(rows):
    meter_values = {}
    for row in rows or []:
        value = round(_safe_float(row.get("electric_energy"), 0.0), 4)
        for key in (row.get("id"), row.get("meter_id"), row.get("source_key")):
            text = str(key or "").strip()
            if not text:
                continue
            meter_values[text] = value
    return meter_values


def _capture_display_reset_baseline_if_due(config, rows):
    meter_statistics = (config or {}).get("meter_statistics", {}) or {}
    reset_state = _resolve_display_reset_state(meter_statistics)
    if not reset_state.get("pending_capture"):
        return config, reset_state, False
    summary_rows = _filter_summary_rows(rows or [], meter_statistics)
    if not summary_rows:
        return config, reset_state, False
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_energy = sum(_safe_float(row.get("electric_energy"), 0.0) for row in summary_rows)
    new_display_reset = {
        "enabled": True,
        "from": str(reset_state.get("from") or "").strip(),
        "value": round(total_energy, 4),
        "pending": False,
        "captured_at": now_text,
        "meter_values": _collect_display_reset_meter_values(rows),
    }
    new_meter_statistics = dict(meter_statistics)
    new_meter_statistics["display_reset_enabled"] = True
    new_meter_statistics["display_reset_from"] = str(reset_state.get("from") or "").strip()
    new_meter_statistics["display_reset"] = new_display_reset
    new_config = dict(config or {})
    new_config["meter_statistics"] = new_meter_statistics
    saved_config = save_config(new_config)
    return saved_config, _resolve_display_reset_state(new_meter_statistics, now_text=now_text), True


def _get_row_display_reset_baseline(row, reset_state):
    if not reset_state.get("applied"):
        return 0.0
    meter_values = reset_state.get("meter_values", {}) or {}
    for key in (row.get("id"), row.get("meter_id"), row.get("source_key")):
        text = str(key or "").strip()
        if text and text in meter_values:
            return _safe_float(meter_values.get(text), 0.0)
    return 0.0


def _is_native_power_row(row):
    source_type = str((row or {}).get("source_type") or "").strip().lower()
    return source_type not in {"cabinet_meter", "calculated_meter"}


def _apply_row_display_reset(row, reset_state):
    raw_energy = _safe_float((row or {}).get("electric_energy"), 0.0)
    if not reset_state.get("applied"):
        return round(raw_energy, 4)
    baseline_value = _get_row_display_reset_baseline(row, reset_state)
    return round(max(raw_energy - baseline_value, 0.0), 4)


def _find_reference_row(rows, source_key):
    target = str(source_key or "").strip()
    if not target:
        return None
    candidates = {target, f"meter:{target}"}
    for row in rows or []:
        row_source_key = str(row.get("source_key") or "").strip()
        row_meter_id = str(row.get("meter_id") or row.get("id") or "").strip()
        if row_source_key in candidates or row_meter_id in candidates or row_meter_id == target:
            return row
    return None


def _build_reference_metric(current_value, reference_value):
    current = _safe_float(current_value, 0.0)
    reference = _safe_float(reference_value, 0.0)
    delta = current - reference
    delta_pct = round(delta / reference * 100.0, 2) if reference > 0 else None
    return {
        "current": round(current, 4),
        "reference": round(reference, 4),
        "delta": round(delta, 4),
        "delta_pct": delta_pct,
        "trend": "up" if delta > 0 else ("down" if delta < 0 else "flat"),
    }


def _build_reference_meter_payload(row):
    if not isinstance(row, dict):
        return None
    return {
        "source_key": str(row.get("source_key") or ""),
        "meter_id": str(row.get("meter_id") or row.get("id") or ""),
        "label": row.get("display_name") or row.get("name") or row.get("id") or "参考总表",
        "online": bool(row.get("online", False)),
        "realtime_power": round(_stable_power_value(row), 4),
        "daily_energy": round(_safe_float(row.get("daily_energy"), 0.0), 4),
        "monthly_energy": round(_safe_float(row.get("monthly_energy"), 0.0), 4),
        "electric_energy": round(_safe_float(row.get("electric_energy"), 0.0), 4),
        "display_electric_energy": round(_safe_float(row.get("display_electric_energy"), _safe_float(row.get("electric_energy"), 0.0)), 4),
        "effective_electric_energy": round(_safe_float(row.get("effective_electric_energy"), _safe_float(row.get("electric_energy"), 0.0)), 4),
    }


def _make_energy_cache(current, today):
    cache = (current or {}).get("_energy_cache")
    if isinstance(cache, dict):
        merged = deepcopy(cache)
        if not merged.get("date"):
            merged["date"] = today
        events = merged.get("events")
        if not isinstance(events, list):
            merged["events"] = []
        else:
            merged["events"] = events[-5:]
        return merged
    return {
        "date": today,
        "start_e": 0.0,
        "last_e": 0.0,
        "month_base": 0.0,
        "month_anchor": today[:7],
        "month_start_energy": 0.0,
        "month_reset_baseline": 0.0,
        "daily_energy": 0.0,
        "monthly_energy": 0.0,
        "events": [],
    }


def _read_meter_mapping_value(client, mapping):
    fc = int(mapping.get("fc", 3) or 3)
    address = int(mapping.get("address", 0) or 0)
    count = int(mapping.get("count", 1) or 1)
    pdu = mc.read_registers_by_client(client, fc, address, count)
    payload = mc.extract_register_bytes_from_pdu(pdu)
    if payload is None:
        return None
    value = mc.decode_register_bytes(payload, data_type=mapping.get("data_type", "u16"), scale=mapping.get("scale", 1.0), byte_order=mapping.get("byte_order", "AB"))
    return round(float(value), 4)


def _decode_meter_energy_preset(client, cfg):
    preset = str(cfg.get("energy_format_preset", "custom") or "custom")
    if preset == "custom":
        return None
    reg_addr = int((cfg.get("register_map", {}) or {}).get("electric_energy", {}).get("address", 0) or 0)
    multiplier = float(cfg.get("multiplier", 1.0) or 1.0)
    if preset in {"legacy_fmt1", "legacy_fmt4"}:
        pdu = mc.read_registers_by_client(client, 4, reg_addr, 2)
        payload = mc.extract_register_bytes_from_pdu(pdu)
        if not payload or len(payload) < 4:
            return None
        return round((int.from_bytes(payload[:4], "big", signed=False) / 100.0) * multiplier, 4)
    if preset == "legacy_fmt3":
        pdu = mc.read_registers_by_client(client, 3, reg_addr, 2)
        payload = mc.extract_register_bytes_from_pdu(pdu)
        if not payload or len(payload) < 4:
            return None
        value = int.from_bytes(bytes([payload[2], payload[3], payload[0], payload[1]]), "big", signed=False) / 100.0
        return round(value * multiplier, 4)
    mapping = (cfg.get("register_map", {}) or {}).get("electric_energy", {}) or {}
    value = _read_meter_mapping_value(client, mapping)
    if value is None:
        return None
    return round(float(value) * multiplier, 4)


def _apply_meter_ratio(key, value, cfg):
    if value is None:
        return None
    numeric = float(value)
    protocol_text = f"{cfg.get('protocol', '')} {cfg.get('model', '')}".lower()
    if "pd606" in protocol_text:
        return round(numeric, 4)
    if str(key).startswith("current_") or str(key) == "realtime_power":
        ratio = float(cfg.get("ct_ratio", 1.0) or 1.0)
        if ratio > 0:
            numeric *= ratio
    elif str(key) == "electric_energy":
        numeric *= float(cfg.get("multiplier", 1.0) or 1.0)
    return round(numeric, 4)


def _resolve_reset_cache_key_aliases(cache_key):
    cache_text = str(cache_key or "").strip()
    aliases = []

    def _append(value):
        text = str(value or "").strip()
        if text and text not in aliases:
            aliases.append(text)

    _append(cache_text)
    if cache_text.startswith("meter:"):
        _append(cache_text.split(":", 1)[1])
    if cache_text.startswith("cabinet:"):
        cab_idx = cache_text.split(":", 1)[1].strip()
        if cab_idx:
            _append(f"cabinet_meter_{cab_idx}")
    return aliases


def _resolve_monthly_reset_baseline(cache_key, today, reset_state):
    reset_state = reset_state or {}
    if not bool(reset_state.get("applied")):
        return 0.0
    reset_from = str(reset_state.get("from") or "").strip()
    reset_date = reset_from[:10] if len(reset_from) >= 10 else ""
    if not reset_date or reset_date > str(today):
        return 0.0
    if reset_date[:7] != str(today)[:7]:
        return 0.0
    meter_values = reset_state.get("meter_values", {}) or {}
    for alias in _resolve_reset_cache_key_aliases(cache_key):
        value = _safe_float(meter_values.get(alias), 0.0)
        if value > 0:
            return round(value, 4)
    return 0.0


def _resolve_month_start_baseline(cache_key, today, cache, fallback_energy):
    month_anchor = str(today)[:7]
    if str(cache.get("month_anchor") or "") != month_anchor:
        cache["month_anchor"] = month_anchor
        cache["month_start_energy"] = 0.0
        cache["month_reset_baseline"] = 0.0
    month_start_energy = _safe_float(cache.get("month_start_energy"), 0.0)
    if month_start_energy > 0:
        return month_start_energy
    month_start_date = f"{month_anchor}-01"
    baseline = get_period_start_energy(cache_key, month_start_date, str(today))
    if baseline is None:
        baseline = _safe_float(cache.get("start_e"), fallback_energy)
    cache["month_start_energy"] = round(_safe_float(baseline, fallback_energy), 4)
    return cache["month_start_energy"]


def _process_daily_energy(cache_key, today, energy_value, cache, reset_state=None):
    energy_num = max(float(energy_value or 0.0), 0.0)
    need_init = cache.get("date") != today or (_safe_float(cache.get("start_e"), 0.0) <= 0 and _safe_float(cache.get("last_e"), 0.0) <= 0)
    if need_init:
        if cache.get("date") != today:
            cache["events"] = []
        init_daily_record(cache_key, today, energy_num)
        rec = get_daily_record(cache_key, today)
        if rec and _safe_float(rec.get("start_energy"), 0.0) <= 0 and energy_num > 0:
            reset_daily_record(cache_key, today, energy_num)
            rec = get_daily_record(cache_key, today)
        cache["start_e"] = _safe_float((rec or {}).get("start_energy"), energy_num)
        cache["date"] = today
        if str(cache.get("month_anchor") or "") != str(today)[:7]:
            cache["month_anchor"] = str(today)[:7]
            cache["month_start_energy"] = 0.0
            cache["month_reset_baseline"] = 0.0
        if _safe_float(cache.get("last_e"), 0.0) <= 0:
            cache["last_e"] = energy_num

    # Protect today's counters from sudden baseline mismatch/outlier jumps.
    # If the implied daily increment is extremely large while meter value itself
    # does not have a comparable jump, re-anchor today's baseline to current energy.
    cached_start = _safe_float(cache.get("start_e"), 0.0)
    cached_last = _safe_float(cache.get("last_e"), 0.0)
    implied_daily = max(energy_num - cached_start, 0.0)
    live_delta = abs(energy_num - cached_last)
    if cached_start > 0 and implied_daily > ENERGY_DAILY_JUMP_THRESHOLD and live_delta <= 120.0:
        detected_at = datetime.now().isoformat()
        event_id = f"{cache_key}:{today}:{int(time.time())}:{int(energy_num * 10)}"
        events = cache.get("events")
        if not isinstance(events, list):
            events = []
        events.append(
            {
                "event_id": event_id,
                "type": "daily_counter_reanchor",
                "cache_key": str(cache_key or ""),
                "date": str(today),
                "detected_at": detected_at,
                "energy_value": round(energy_num, 4),
                "start_before": round(cached_start, 4),
                "last_before": round(cached_last, 4),
                "implied_daily_before": round(implied_daily, 4),
                "live_delta": round(live_delta, 4),
                "threshold": round(ENERGY_DAILY_JUMP_THRESHOLD, 4),
                "action": "reset_daily_record_to_current_energy",
            }
        )
        cache["events"] = events[-5:]
        reset_daily_record(cache_key, today, energy_num)
        rec = get_daily_record(cache_key, today)
        cache["start_e"] = _safe_float((rec or {}).get("start_energy"), energy_num)
        cache["last_e"] = energy_num
        cached_start = _safe_float(cache.get("start_e"), 0.0)

    daily = max(energy_num - cached_start, 0.0)
    cache["daily_energy"] = round(daily, 4)
    month_start_baseline = _resolve_month_start_baseline(cache_key, today, cache, energy_num)
    month_reset_baseline = _resolve_monthly_reset_baseline(cache_key, today, reset_state)
    cache["month_reset_baseline"] = round(month_reset_baseline, 4)
    # Monthly energy for each meter card always follows natural-month baseline:
    # from day 1 at 00:00 of the current month. Display reset should not alter it.
    month_baseline = month_start_baseline
    cache["month_base"] = round(month_baseline, 4)
    cache["monthly_energy"] = round(max(energy_num - month_baseline, 0.0), 4)
    if abs(energy_num - _safe_float(cache.get("last_e"), 0.0)) >= 0.1:
        update_daily_record(cache_key, today, energy_num)
        cache["last_e"] = energy_num


def _base_cabinet_meter_status(cab_idx, cfg):
    display_name = cfg.get("meter_display_name") or cfg.get("cabinet_name", f"电柜 {cab_idx + 1}")
    meter_mode = str(cfg.get("meter_mode", "type1") or "type1")
    return {
        "id": f"cabinet_meter_{cab_idx}",
        "meter_id": f"cabinet_meter_{cab_idx}",
        "source_type": "cabinet_meter",
        "source_key": f"cabinet:{cab_idx}",
        "cabinet_idx": cab_idx,
        "cabinet_name": cfg.get("cabinet_name", display_name),
        "display_name": display_name,
        "name": display_name,
        "meter_mode": meter_mode,
        "meter_kind": "柜内电表",
        "protocol": cfg.get("plc_type", "AV-100"),
        "comm_mode": "TCP",
        "area_name": cfg.get("meter_area_name", ""),
        "sort_order": int(cfg.get("meter_sort_order", cab_idx + 1) or (cab_idx + 1)),
        "meter_sort_order": int(cfg.get("meter_sort_order", cab_idx + 1) or (cab_idx + 1)),
        "visible_in_meter_center": bool(cfg.get("meter_visible_in_center", True)),
        "include_in_totals": bool(cfg.get("meter_include_in_totals", True)),
        "include_in_reports": bool(cfg.get("meter_include_in_reports", True)),
        "ip": cfg.get("ip", ""),
        "port": int(cfg.get("port", 502) or 502),
        "station_id": int(cfg.get("station_id", 1) or 1),
        "ct_ratio": float(cfg.get("ct_ratio", 1.0) or 1.0),
        "online": False,
        "updated_at": datetime.now().isoformat(),
        "realtime_power": 0.0,
        "electric_energy": 0.0,
        "daily_energy": 0.0,
        "monthly_energy": 0.0,
        "voltage_a": 0.0,
        "voltage_b": 0.0,
        "voltage_c": 0.0,
        "voltage_ab": 0.0,
        "voltage_bc": 0.0,
        "voltage_ca": 0.0,
        "current_a": 0.0,
        "current_b": 0.0,
        "current_c": 0.0,
        "reactive_power": 0.0,
        "apparent_power": 0.0,
        "power_factor": 0.0,
        "frequency": 0.0,
        "cabinet_temp": 0.0,
        "cabinet_humidity": 0.0,
        "channel_count": int(cfg.get("channel_count", 0) or 0),
        "channels_1_4": [False] * max(int(cfg.get("channel_count", 0) or 0), 0),
        "channel_on_count": 0,
        "work_mode": "未知",
        "error": "",
    }


def _poll_cabinet_meter_once(cab_idx, cfg, today, reset_state=None):
    meter_id = f"cabinet_meter_{cab_idx}"
    with STATE_LOCK:
        current = deepcopy(LATEST_STATUS.get(meter_id, {}))
    merged = _base_cabinet_meter_status(cab_idx, cfg)
    merged.update(current)
    energy_cache = _make_energy_cache(current, today)
    cached_success = _get_cached_success_status(meter_id, current=current)
    client = None
    try:
        client = mc.make_client(
            cfg.get("ip", ""),
            int(cfg.get("port", 502) or 502),
            int(cfg.get("station_id", 1) or 1),
            timeout=max(float(cfg.get("timeout_sec", 1.5) or 1.5), 0.5),
            protocol=str(cfg.get("plc_type", "AV-100") or "AV-100"),
        )
        if not client.connect():
            if _apply_transient_hold(merged, current, "fallback: transient connection failed, keeping last live value", energy_cache=energy_cache):
                return merged
            if _apply_cached_fallback(merged, cached_success, "fallback: connection failed, showing last cached value", energy_cache=energy_cache):
                return merged
            merged["error"] = "连接失败"
            merged["online"] = False
            merged["_failure_streak"] = _current_failure_streak(current) + 1
            merged["_energy_cache"] = energy_cache
            merged["updated_at"] = datetime.now().isoformat()
            return merged
        mode = str(cfg.get("meter_mode", "type1") or "type1")
        ct_ratio = float(cfg.get("ct_ratio", 1.0) or 1.0)
        p_env = mc.read_registers_by_client(client, 3, 0x04B0, 16)
        p_curr = mc.read_registers_by_client(client, 3, 0x05DC, 12)
        relay = mc.parse_pdu_relay(mc.read_registers_by_client(client, 1, 0, min(max(int(cfg.get("channel_count", 0) or 0), 1), 16)), int(cfg.get("channel_count", 0) or 0)) or []
        p_mode = mc.read_registers_by_client(client, 3, 0x00A2, 1)
        hum, temp = mc.parse_av100_env(p_env)
        va, vb, vc, ia, ib, ic, energy = mc.parse_av100_meter(p_env, p_curr, mode=mode, ct_ratio=ct_ratio)
        merged["cabinet_humidity"] = round(float(hum or 0.0), 1)
        merged["cabinet_temp"] = round(float(temp or 0.0), 1)
        merged["voltage_a"] = round(float(va or 0.0), 1)
        merged["voltage_b"] = round(float(vb or 0.0), 1)
        merged["voltage_c"] = round(float(vc or 0.0), 1)
        merged["current_a"] = round(float(ia or 0.0), 3 if mode == "type4" else 1)
        merged["current_b"] = round(float(ib or 0.0), 3 if mode == "type4" else 1)
        merged["current_c"] = round(float(ic or 0.0), 3 if mode == "type4" else 1)
        merged["electric_energy"] = round(float(energy or 0.0), 4)
        merged["realtime_power"] = round(((merged["voltage_a"] * merged["current_a"]) + (merged["voltage_b"] * merged["current_b"]) + (merged["voltage_c"] * merged["current_c"])) / 1000.0, 4)
        relay_bits = list((relay or [])[:merged["channel_count"]])
        if len(relay_bits) < merged["channel_count"]:
            relay_bits.extend([False] * (merged["channel_count"] - len(relay_bits)))
        merged["channels_1_4"] = [bool(item) for item in relay_bits]
        merged["channel_on_count"] = sum(1 for item in merged["channels_1_4"] if item)
        if p_mode and len(p_mode) >= 5:
            mode_val = p_mode[-1]
            merged["work_mode"] = {0: "手动模式", 1: "远程模式", 2: "外控模式", 3: "外控模式"}.get(mode_val, "未知")
        merged["online"] = True
        merged["error"] = ""
        _mark_poll_success(merged)
        _process_daily_energy(f"cabinet:{cab_idx}", today, merged["electric_energy"], energy_cache, reset_state=reset_state)
        merged["daily_energy"] = energy_cache["daily_energy"]
        merged["monthly_energy"] = energy_cache["monthly_energy"]
    except Exception as exc:
        if _apply_transient_hold(merged, current, f"fallback: transient error: {str(exc)}", energy_cache=energy_cache):
            return merged
        if _apply_cached_fallback(merged, cached_success, f"fallback: {str(exc)}", energy_cache=energy_cache):
            return merged
        merged["online"] = False
        merged["_failure_streak"] = _current_failure_streak(current) + 1
        merged["error"] = str(exc)
    finally:
        try:
            if client:
                client.close()
        except Exception:
            pass
    merged["_energy_cache"] = energy_cache
    merged["updated_at"] = datetime.now().isoformat()
    return merged


def _base_meter_status(cfg):
    meter_id = str(cfg.get("id", "")).strip()
    return {
        "id": meter_id,
        "meter_id": meter_id,
        "source_type": "standalone_meter",
        "source_key": f"meter:{meter_id}",
        "display_name": cfg.get("name", meter_id),
        "name": cfg.get("name", meter_id),
        "meter_mode": cfg.get("meter_type", "direct"),
        "meter_kind": cfg.get("meter_kind", "独立电表"),
        "protocol": cfg.get("protocol", "Modbus-RTU/TCP"),
        "comm_mode": cfg.get("comm_mode", "TCP"),
        "area_name": cfg.get("area_name", ""),
        "sort_order": int(cfg.get("sort_order", 999) or 999),
        "visible_in_meter_center": bool(cfg.get("visible_in_meter_center", cfg.get("visible", True))),
        "include_in_totals": bool(cfg.get("include_in_totals", True)),
        "include_in_reports": bool(cfg.get("include_in_reports", True)),
        "online": False,
        "updated_at": datetime.now().isoformat(),
        "realtime_power": 0.0,
        "electric_energy": 0.0,
        "daily_energy": 0.0,
        "monthly_energy": 0.0,
        "voltage_a": 0.0,
        "voltage_b": 0.0,
        "voltage_c": 0.0,
        "voltage_ab": 0.0,
        "voltage_bc": 0.0,
        "voltage_ca": 0.0,
        "current_a": 0.0,
        "current_b": 0.0,
        "current_c": 0.0,
        "reactive_power": 0.0,
        "apparent_power": 0.0,
        "power_factor": 0.0,
        "frequency": 0.0,
        "error": "",
    }


def _resolve_source_candidates(source_id):
    source_id = str(source_id or "").strip()
    candidates = []
    if source_id:
        candidates.append(source_id)
    if source_id.startswith("meter:"):
        meter_id = source_id.split(":", 1)[1].strip()
        if meter_id:
            candidates.append(meter_id)
    if source_id.startswith("cabinet:"):
        cab_idx = source_id.split(":", 1)[1].strip()
        if cab_idx:
            candidates.append(f"cabinet_meter_{cab_idx}")
    return [item for idx, item in enumerate(candidates) if item and item not in candidates[:idx]]


def _is_usable_source_row(row):
    if not row:
        return False
    if bool(row.get("online", False)):
        return True
    return _safe_float(row.get("electric_energy"), 0.0) > 0 or _safe_float(row.get("realtime_power"), 0.0) > 0


def _resolve_source_row(source_id, local_state):
    candidates = _resolve_source_candidates(source_id)
    if not candidates:
        return None

    for candidate in candidates:
        direct = local_state.get(candidate)
        if bool((direct or {}).get("online", False)):
            return deepcopy(direct)
    for candidate in candidates:
        direct = local_state.get(candidate)
        if _is_usable_source_row(direct):
            return deepcopy(direct)

    with STATE_LOCK:
        latest_snapshot = deepcopy(LATEST_STATUS)
    for candidate in candidates:
        current = latest_snapshot.get(candidate)
        if bool((current or {}).get("online", False)):
            return current
    for candidate in candidates:
        current = latest_snapshot.get(candidate)
        if _is_usable_source_row(current):
            return current

    for candidate in candidates:
        persisted = get_last_success_snapshot(candidate)
        if persisted:
            persisted = deepcopy(persisted)
            persisted["_resolved_from_persisted"] = True
            persisted["_using_cached_fallback"] = True
            persisted["_degraded"] = True
            persisted["online"] = True
            if not str(persisted.get("error") or "").strip():
                persisted["error"] = "fallback: using persisted source snapshot"
            return persisted
    return None


def _pick_first_value(*values, default=0.0):
    for value in values:
        if value not in (None, ""):
            return value
    return default


def _combine_numeric_values(left_value, right_value, operator="subtract", clamp_min=None):
    left_num = _safe_float(left_value, 0.0)
    right_num = _safe_float(right_value, 0.0)
    result = left_num + right_num if str(operator) == "add" else left_num - right_num
    if clamp_min is not None and result < clamp_min:
        result = clamp_min
    return round(result, 4)


def _build_calculated_meter_status(cfg, local_state, today, current=None, reset_state=None):
    current = current or {}
    meter_id = str(cfg.get("id", "")).strip()
    merged = _base_meter_status(cfg)
    merged.update(current)
    merged["source_type"] = "calculated_meter"
    merged["source_mode"] = "calculated"
    merged["calc_left_source_id"] = str(cfg.get("calc_left_source_id", "") or "").strip()
    merged["calc_right_source_id"] = str(cfg.get("calc_right_source_id", "") or "").strip()
    merged["calc_operator"] = str(cfg.get("calc_operator", "subtract") or "subtract").strip().lower()

    energy_cache = _make_energy_cache(current, today)
    left_row = _resolve_source_row(merged["calc_left_source_id"], local_state)
    right_row = _resolve_source_row(merged["calc_right_source_id"], local_state)
    cached_success = _get_cached_success_status(meter_id, current=current, max_age_seconds=7200)

    missing_parts = []
    if not merged["calc_left_source_id"]:
        missing_parts.append("missing left source")
    elif not left_row:
        missing_parts.append(f"left source not found: {merged['calc_left_source_id']}")
    if not merged["calc_right_source_id"]:
        missing_parts.append("missing right source")
    elif not right_row:
        missing_parts.append(f"right source not found: {merged['calc_right_source_id']}")

    if not missing_parts and left_row and right_row:
        operator = merged["calc_operator"] if merged["calc_operator"] in {"add", "subtract"} else "subtract"
        merged["meter_kind"] = str(cfg.get("meter_kind") or "calculated_meter")
        for key in ("current_a", "current_b", "current_c", "realtime_power", "reactive_power", "apparent_power"):
            clamp_min = 0.0 if key.startswith("current_") or key == "apparent_power" else None
            merged[key] = _combine_numeric_values(left_row.get(key), right_row.get(key), operator=operator, clamp_min=clamp_min)

        merged["electric_energy"] = _combine_numeric_values(left_row.get("electric_energy"), right_row.get("electric_energy"), operator=operator, clamp_min=0.0)

        for key in ("voltage_a", "voltage_b", "voltage_c", "voltage_ab", "voltage_bc", "voltage_ca", "power_factor", "frequency", "cabinet_temp", "cabinet_humidity"):
            merged[key] = round(_safe_float(_pick_first_value(left_row.get(key), right_row.get(key), default=0.0), 0.0), 4)

        merged["channel_count"] = _safe_int(_pick_first_value(left_row.get("channel_count"), right_row.get("channel_count"), default=0), 0)
        merged["channel_on_count"] = _safe_int(_pick_first_value(left_row.get("channel_on_count"), right_row.get("channel_on_count"), default=0), 0)
        merged["work_mode"] = str(_pick_first_value(left_row.get("work_mode"), right_row.get("work_mode"), default="calculated") or "calculated")

        left_online = bool(left_row.get("online", False))
        right_online = bool(right_row.get("online", False))
        merged["online"] = left_online or right_online

        source_errors = []
        if not left_online:
            source_errors.append(f"left offline: {left_row.get('display_name') or merged['calc_left_source_id']}")
        if not right_online:
            source_errors.append(f"right offline: {right_row.get('display_name') or merged['calc_right_source_id']}")
        merged["error"] = "; ".join(source_errors)
        merged["_degraded"] = bool(source_errors)
        if merged["online"] and not source_errors:
            _mark_poll_success(merged)

        _process_daily_energy(f"meter:{meter_id}", today, merged["electric_energy"], energy_cache, reset_state=reset_state)
        merged["daily_energy"] = energy_cache["daily_energy"]
        merged["monthly_energy"] = energy_cache["monthly_energy"]

    if missing_parts:
        if not _apply_cached_fallback(merged, cached_success, "; ".join(missing_parts), energy_cache=energy_cache):
            merged["online"] = False
            merged["_failure_streak"] = _current_failure_streak(current) + 1
            merged["error"] = "; ".join(missing_parts)

    merged["_energy_cache"] = energy_cache
    merged["updated_at"] = datetime.now().isoformat()
    return merged


def _poll_standalone_meter_once(cfg, today, reset_state=None):
    meter_id = str(cfg.get("id", "")).strip()
    with STATE_LOCK:
        current = deepcopy(LATEST_STATUS.get(meter_id, {}))
    merged = _base_meter_status(cfg)
    merged.update(current)
    energy_cache = _make_energy_cache(current, today)
    cached_success = _get_cached_success_status(meter_id, current=current)
    protocol = str(cfg.get("comm_mode", "TCP")).upper()
    client_protocol = "RTU_OVER_TCP" if protocol == "RTU_OVER_TCP" else "AV-100"
    client = None
    try:
        if protocol == "COM":
            merged["error"] = "当前 Docker 版本暂未启用本地 COM 采集"
        else:
            client = mc.make_client(
                cfg.get("ip", ""),
                int(cfg.get("port", 502) or 502),
                int(cfg.get("station_id", 1) or 1),
                timeout=max(float(cfg.get("timeout_sec", 1.5) or 1.5), 0.5),
                protocol=client_protocol,
            )
            if client.connect():
                register_map = cfg.get("register_map", {}) or {}
                for key, mapping in register_map.items():
                    if not isinstance(mapping, dict) or not mapping.get("enabled", False):
                        continue
                    value = _decode_meter_energy_preset(client, cfg) if key == "electric_energy" and str(cfg.get("energy_format_preset", "custom") or "custom") != "custom" else _read_meter_mapping_value(client, mapping)
                    if value is not None:
                        merged[key] = round(float(value), 4) if key == "electric_energy" and str(cfg.get("energy_format_preset", "custom") or "custom") != "custom" else _apply_meter_ratio(key, value, cfg)
                merged["online"] = True
                merged["error"] = ""
                _mark_poll_success(merged)
                energy_value = float(merged.get("electric_energy") or 0.0)
                _process_daily_energy(f"meter:{meter_id}", today, energy_value, energy_cache, reset_state=reset_state)
                merged["daily_energy"] = energy_cache["daily_energy"]
                merged["monthly_energy"] = energy_cache["monthly_energy"]
            else:
                if _apply_transient_hold(merged, current, "fallback: transient connection failed, keeping last live value", energy_cache=energy_cache):
                    return merged
                if _apply_cached_fallback(merged, cached_success, "fallback: connection failed, showing last cached value", energy_cache=energy_cache):
                    return merged
                merged["error"] = "连接失败"
                merged["_failure_streak"] = _current_failure_streak(current) + 1
        if protocol == "COM":
            merged["online"] = False
            merged["_failure_streak"] = _current_failure_streak(current) + 1
    except Exception as exc:
        if _apply_transient_hold(merged, current, f"fallback: transient error: {str(exc)}", energy_cache=energy_cache):
            return merged
        if _apply_cached_fallback(merged, cached_success, f"fallback: {str(exc)}", energy_cache=energy_cache):
            return merged
        merged["online"] = False
        merged["_failure_streak"] = _current_failure_streak(current) + 1
        merged["error"] = str(exc)
    finally:
        try:
            if client:
                client.close()
        except Exception:
            pass
    merged["_energy_cache"] = energy_cache
    merged["updated_at"] = datetime.now().isoformat()
    return merged


def _preserve_previous_row(meter_id, current, today, reason):
    if not current:
        return None
    merged = deepcopy(current)
    energy_cache = _make_energy_cache(current, today)
    cached_success = _get_cached_success_status(meter_id, current=current, max_age_seconds=7200)
    if _apply_transient_hold(merged, current, reason, energy_cache=energy_cache):
        return merged
    if _apply_cached_fallback(merged, cached_success, reason, energy_cache=energy_cache):
        return merged
    merged["online"] = bool(current.get("online", False))
    merged["_using_cached_fallback"] = True
    merged["_degraded"] = True
    merged["_failure_streak"] = _current_failure_streak(current) + 1
    merged["error"] = str(reason or "fallback: keeping previous meter state")
    merged["_energy_cache"] = energy_cache
    merged["updated_at"] = datetime.now().isoformat()
    return merged


def poll_once():
    config = load_config()
    cabinet_configs = list(config.get("cabinets", []))
    meter_configs = list(config.get("meters", []))
    meter_statistics = config.get("meter_statistics", {}) or {}
    display_reset_state = _resolve_display_reset_state(meter_statistics)
    today = datetime.now().strftime("%Y-%m-%d")
    with STATE_LOCK:
        previous_state = deepcopy(LATEST_STATUS)
    local_state = {}
    calculated_meter_configs = []
    poll_jobs = []
    active_physical_meter_ids = set()
    order = 0
    for cab_idx, cfg in enumerate(cabinet_configs):
        meter_id = f"cabinet_meter_{cab_idx}"
        active_physical_meter_ids.add(meter_id)
        poll_jobs.append((order, meter_id, "cabinet", cab_idx, cfg))
        order += 1
    for cfg in meter_configs:
        if not cfg.get("enabled", True):
            continue
        meter_id = str(cfg.get("id", "")).strip()
        if not meter_id:
            continue
        source_mode = str(cfg.get("source_mode", "standalone") or "standalone").strip().lower()
        if source_mode == "calculated":
            calculated_meter_configs.append(cfg)
            continue
        if source_mode == "cabinet_linked" and _safe_int(cfg.get("bind_cabinet_idx", -1), -1) >= 0:
            continue
        active_physical_meter_ids.add(meter_id)
        poll_jobs.append((order, meter_id, "standalone", None, cfg))
        order += 1

    results = []
    processed_meter_ids = set()
    if poll_jobs:
        endpoint_groups = {}
        for job_order, meter_id, job_type, cab_idx, cfg in poll_jobs:
            endpoint_key = _poll_endpoint_key(job_type, cfg)
            endpoint_groups.setdefault(endpoint_key, []).append((job_order, meter_id, job_type, cab_idx, cfg))

        ordered_groups = [
            sorted(group_jobs, key=lambda item: item[0])
            for _, group_jobs in sorted(endpoint_groups.items(), key=lambda item: min(job[0] for job in item[1]))
        ]

        def run_group(group_jobs):
            group_results = []
            for job_order, meter_id, job_type, cab_idx, cfg in group_jobs:
                try:
                    if job_type == "cabinet":
                        merged = _poll_cabinet_meter_once(cab_idx, cfg, today, reset_state=display_reset_state)
                    else:
                        merged = _poll_standalone_meter_once(cfg, today, reset_state=display_reset_state)
                except Exception as exc:
                    merged = _preserve_previous_row(meter_id, previous_state.get(meter_id), today, f"fallback: poll worker error: {str(exc)}")
                if merged:
                    group_results.append((job_order, meter_id, merged))
            return group_results

        worker_count = min(MAX_PARALLEL_POLLERS, len(ordered_groups))
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="meter-poll") as executor:
            future_map = {executor.submit(run_group, group_jobs): group_jobs for group_jobs in ordered_groups}
            for future in as_completed(future_map):
                group_results = future.result()
                for job_order, meter_id, merged in group_results:
                    results.append((job_order, merged))
                    processed_meter_ids.add(meter_id)

    for _, merged in sorted(results, key=lambda item: item[0]):
        merged = _smooth_realtime_power(merged, current=previous_state.get(merged.get("id")))
        local_state[merged["id"]] = merged
        upsert_latest(merged)
        insert_snapshot(merged)

    missing_meter_ids = sorted(active_physical_meter_ids - processed_meter_ids)
    for meter_id in missing_meter_ids:
        preserved = _preserve_previous_row(meter_id, previous_state.get(meter_id), today, "fallback: poll cycle returned no result")
        if not preserved:
            continue
        preserved = _smooth_realtime_power(preserved, current=previous_state.get(meter_id))
        local_state[meter_id] = preserved
        upsert_latest(preserved)
        insert_snapshot(preserved)

    for cfg in calculated_meter_configs:
        meter_id = str(cfg.get("id", "")).strip()
        if not meter_id:
            continue
        current = deepcopy(previous_state.get(meter_id, {}))
        merged = _build_calculated_meter_status(cfg, local_state, today, current=current, reset_state=display_reset_state)
        merged = _smooth_realtime_power(merged, current=current)
        local_state[meter_id] = merged
        upsert_latest(merged)
        insert_snapshot(merged)

    with STATE_LOCK:
        LATEST_STATUS.clear()
        LATEST_STATUS.update(local_state)
    config, _, _ = _capture_display_reset_baseline_if_due(config, list(local_state.values()))
    cleanup_history((config.get("meter_statistics", {}) or {}).get("history_keep_days", 90))
    return
    for cfg in meter_configs:
        if not cfg.get("enabled", True):
            continue
        meter_id = str(cfg.get("id", "")).strip()
        if not meter_id:
            continue
        source_mode = str(cfg.get("source_mode", "standalone") or "standalone").strip().lower()
        if source_mode == "calculated":
            calculated_meter_configs.append(cfg)
            continue
        if source_mode == "cabinet_linked" and _safe_int(cfg.get("bind_cabinet_idx", -1), -1) >= 0:
            continue
        with STATE_LOCK:
            current = deepcopy(LATEST_STATUS.get(meter_id, {}))
        merged = _base_meter_status(cfg)
        merged.update(current)
        energy_cache = current.get("_energy_cache", {"date": today, "start_e": 0.0, "last_e": 0.0, "month_base": 0.0, "daily_energy": 0.0, "monthly_energy": 0.0})
        cached_success = _get_cached_success_status(meter_id, current=current)
        protocol = str(cfg.get("comm_mode", "TCP")).upper()
        client_protocol = "RTU_OVER_TCP" if protocol == "RTU_OVER_TCP" else "AV-100"
        client = None
        try:
            if protocol == "COM":
                merged["error"] = "当前 Docker 版暂未启用本地 COM 采集"
            else:
                client = mc.make_client(cfg.get("ip", ""), int(cfg.get("port", 502) or 502), int(cfg.get("station_id", 1) or 1), timeout=max(float(cfg.get("timeout_sec", 1.5) or 1.5), 0.5), protocol=client_protocol)
                if client.connect():
                    register_map = cfg.get("register_map", {}) or {}
                    for key, mapping in register_map.items():
                        if not isinstance(mapping, dict) or not mapping.get("enabled", False):
                            continue
                        value = _decode_meter_energy_preset(client, cfg) if key == "electric_energy" and str(cfg.get("energy_format_preset", "custom") or "custom") != "custom" else _read_meter_mapping_value(client, mapping)
                        if value is not None:
                            merged[key] = round(float(value), 4) if key == "electric_energy" and str(cfg.get("energy_format_preset", "custom") or "custom") != "custom" else _apply_meter_ratio(key, value, cfg)
                    merged["online"] = True
                    merged["error"] = ""
                    _mark_poll_success(merged)
                    energy_value = float(merged.get("electric_energy") or 0.0)
                    _process_daily_energy(f"meter:{meter_id}", today, energy_value, energy_cache)
                    merged["daily_energy"] = energy_cache["daily_energy"]
                    merged["monthly_energy"] = energy_cache["monthly_energy"]
                else:
                    if _apply_transient_hold(merged, current, "fallback: transient connection failed, keeping last live value", energy_cache=energy_cache):
                        local_state[meter_id] = merged
                        upsert_latest(merged)
                        insert_snapshot(merged)
                        continue
                    if _apply_cached_fallback(merged, cached_success, "fallback: connection failed, showing last cached value", energy_cache=energy_cache):
                        local_state[meter_id] = merged
                        upsert_latest(merged)
                        insert_snapshot(merged)
                        continue
                    merged["error"] = "连接失败"
                    merged["_failure_streak"] = _current_failure_streak(current) + 1
        except Exception as exc:
            if _apply_transient_hold(merged, current, f"fallback: transient error: {str(exc)}", energy_cache=energy_cache):
                local_state[meter_id] = merged
                upsert_latest(merged)
                insert_snapshot(merged)
                continue
            if _apply_cached_fallback(merged, cached_success, f"fallback: {str(exc)}", energy_cache=energy_cache):
                local_state[meter_id] = merged
                upsert_latest(merged)
                insert_snapshot(merged)
                continue
            merged["online"] = False
            merged["_failure_streak"] = _current_failure_streak(current) + 1
            merged["error"] = str(exc)
        finally:
            try:
                if client:
                    client.close()
            except Exception:
                pass
        merged["_energy_cache"] = energy_cache
        merged["updated_at"] = datetime.now().isoformat()
        local_state[meter_id] = merged
        upsert_latest(merged)
        insert_snapshot(merged)
    for cfg in calculated_meter_configs:
        meter_id = str(cfg.get("id", "")).strip()
        if not meter_id:
            continue
        with STATE_LOCK:
            current = deepcopy(LATEST_STATUS.get(meter_id, {}))
        merged = _build_calculated_meter_status(cfg, local_state, today, current=current)
        local_state[meter_id] = merged
        upsert_latest(merged)
        insert_snapshot(merged)
    with STATE_LOCK:
        LATEST_STATUS.clear()
        LATEST_STATUS.update(local_state)
    cleanup_history((config.get("meter_statistics", {}) or {}).get("history_keep_days", 90))


def meter_poll_loop():
    while True:
        try:
            poll_once()
        except Exception:
            pass
        time.sleep(POLL_INTERVAL_SECONDS)


def get_latest_rows():
    with STATE_LOCK:
        rows = [deepcopy(item) for item in LATEST_STATUS.values()]
    return _sort_rows(rows)


def build_meter_diagnostics_payload():
    config = load_config()
    rows = get_latest_rows()
    now = datetime.now()
    diagnostics_rows = []
    for row in rows:
        display_name = row.get("display_name") or row.get("name") or row.get("id") or "未命名电表"
        updated_at = str(row.get("updated_at") or "").strip()
        age_seconds = None
        if updated_at:
            try:
                age_seconds = max((now - datetime.fromisoformat(updated_at)).total_seconds(), 0.0)
            except Exception:
                age_seconds = None
        voltage_values = [
            _safe_float(row.get("voltage_a"), 0.0),
            _safe_float(row.get("voltage_b"), 0.0),
            _safe_float(row.get("voltage_c"), 0.0),
        ]
        current_values = [
            _safe_float(row.get("current_a"), 0.0),
            _safe_float(row.get("current_b"), 0.0),
            _safe_float(row.get("current_c"), 0.0),
        ]
        diagnostics = []
        if not bool(row.get("online", False)):
            diagnostics.append("离线")
        if bool(row.get("_using_cached_fallback", False)):
            diagnostics.append("正在使用缓存值")
        if bool(row.get("_degraded", False)):
            diagnostics.append("通信降级中")
        if age_seconds is not None and age_seconds > max(POLL_INTERVAL_SECONDS * 4, 20):
            diagnostics.append(f"数据延迟 {round(age_seconds, 1)} 秒")
        if bool(row.get("online", False)) and all(value <= 0 for value in voltage_values) and all(value <= 0 for value in current_values):
            diagnostics.append("在线但三相电压电流均为 0")
        if any(value > 300 for value in voltage_values):
            diagnostics.append("存在超过 300V 的电压值")
        if any(value < 150 and value > 0 for value in voltage_values):
            diagnostics.append("存在异常偏低电压值")
        if _safe_float(row.get("realtime_power"), 0.0) > 300:
            diagnostics.append("实时功率偏大，建议核对倍率")
        if max(current_values) > 1000:
            diagnostics.append("电流值偏大，建议核对 CT 倍率")
        if _safe_float(row.get("electric_energy"), 0.0) < 0:
            diagnostics.append("累计电能为负值")
        if _safe_float(row.get("realtime_power"), 0.0) < 0:
            diagnostics.append("实时功率为负值")
        if str(row.get("source_type") or "") == "standalone_meter" and _safe_float(row.get("electric_energy"), 0.0) > 0 and _safe_float(row.get("daily_energy"), 0.0) == 0 and _safe_float(row.get("monthly_energy"), 0.0) == 0:
            diagnostics.append("今日/月电量仍为 0，需核对计量基线")
        error_text = str(row.get("error") or "").strip()
        if error_text:
            diagnostics.append(error_text)

        diagnostics_rows.append(
            {
                **deepcopy(row),
                "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
                "diagnostics": diagnostics,
                "diagnostic_level": "error" if any(item in diagnostics for item in ("离线", "累计电能为负值", "实时功率为负值")) else ("warn" if diagnostics else "ok"),
                "display_protocol": row.get("protocol") or row.get("meter_mode") or row.get("source_type") or "",
            }
        )

    meter_statistics = config.get("meter_statistics", {}) or {}
    quality_counts = _build_quality_counts(diagnostics_rows)
    return {
        "generated_at": now.isoformat(),
        "service": "meter_service",
        "remote_service_mode": str(meter_statistics.get("remote_service_mode", "") or ""),
        "poll_interval_seconds": float(POLL_INTERVAL_SECONDS),
        "meters": diagnostics_rows,
        "summary": {
            "total": len(diagnostics_rows),
            "online": sum(1 for row in diagnostics_rows if bool(row.get("online", False))),
            "offline": sum(1 for row in diagnostics_rows if not bool(row.get("online", False))),
            "fallback": sum(1 for row in diagnostics_rows if bool(row.get("_using_cached_fallback", False))),
            "degraded": sum(1 for row in diagnostics_rows if bool(row.get("_degraded", False))),
            "with_diagnostics": sum(1 for row in diagnostics_rows if row.get("diagnostics")),
            "quality_counts": quality_counts,
        },
    }


def get_runtime_health_snapshot(window_seconds=600):
    rows = get_latest_rows()
    now = datetime.now()
    active_rows = []
    for row in rows:
        updated_at = str(row.get("updated_at") or "").strip()
        if not updated_at:
            continue
        try:
            age = (now - datetime.fromisoformat(updated_at)).total_seconds()
        except Exception:
            continue
        if age <= max(float(window_seconds or 0), 0.0):
            active_rows.append(row)
    fallback_rows = [row for row in active_rows if bool(row.get("_using_cached_fallback", False))]
    degraded_rows = [row for row in active_rows if bool(row.get("_degraded", False))]
    failure_rows = [row for row in active_rows if _safe_int(row.get("_failure_streak"), 0) > 0]
    top_failures = sorted(
        [
            {
                "meter_id": row.get("id"),
                "display_name": row.get("display_name") or row.get("name") or row.get("id"),
                "failure_streak": _safe_int(row.get("_failure_streak"), 0),
                "error": str(row.get("error") or ""),
                "updated_at": row.get("updated_at"),
            }
            for row in failure_rows
        ],
        key=lambda item: (-int(item.get("failure_streak") or 0), str(item.get("display_name") or "")),
    )[:8]
    return {
        "window_seconds": int(window_seconds or 600),
        "active_meter_count": len(active_rows),
        "fallback_meter_count": len(fallback_rows),
        "degraded_meter_count": len(degraded_rows),
        "failure_meter_count": len(failure_rows),
        "top_failures": top_failures,
    }


def _filter_summary_rows(rows, meter_statistics):
    mode = str(meter_statistics.get("summary_mode", "include_flag") or "include_flag")
    filtered = []
    for row in rows:
        include = bool(row.get("include_in_totals", True))
        visible = bool(row.get("visible_in_meter_center", True))
        if not visible:
            continue
        if mode == "visible_only":
            if include:
                filtered.append(row)
        else:
            if include:
                filtered.append(row)
    return filtered


def _sum_rows_power(rows):
    return sum(_stable_power_value(row) for row in (rows or []))


def _sum_rows_native_power(rows):
    return sum(_stable_power_value(row) for row in (rows or []) if _is_native_power_row(row))


def _build_quality_counts(rows):
    counts = {"ok": 0, "degraded": 0, "fallback": 0, "offline": 0, "unstable": 0}
    for row in rows or []:
        key = str(row.get("data_quality") or _resolve_data_quality(row)).strip().lower() or "ok"
        if key not in counts:
            counts[key] = 0
        counts[key] += 1
    return counts


def _resolve_target(rows, target_source_key):
    key = str(target_source_key or "total")
    if key == "total":
        return {"target": "total", "label": "全部统计电表", "rows": rows}
    if key.startswith("area:"):
        area_name = key.split(":", 1)[1].strip()
        area_rows = [row for row in rows if str(row.get("area_name") or "").strip() == area_name]
        return {"target": key, "label": f"{area_name}（区域）", "rows": area_rows}
    row = next((item for item in rows if str(item.get("source_key")) == key), None)
    if not row:
        return None
    return {"target": key, "label": row.get("display_name") or row.get("id"), "rows": [row]}


def _resolve_history_cache_key(row):
    row = row or {}
    source_key = str(row.get("source_key") or "").strip()
    if source_key.startswith("meter:") or source_key.startswith("cabinet:"):
        return source_key
    source_type = str(row.get("source_type") or "").strip().lower()
    if source_type == "cabinet_meter":
        cab_idx = row.get("cabinet_idx", None)
        if cab_idx not in (None, ""):
            try:
                return f"cabinet:{int(cab_idx)}"
            except Exception:
                pass
    meter_id = str(row.get("meter_id") or row.get("id") or "").strip()
    if meter_id:
        return f"meter:{meter_id}"
    return ""


def build_meter_payload(target_source_key="total", period="day", days=7):
    config = load_config()
    meter_statistics = config.get("meter_statistics", {}) or {}
    display_reset_state = _resolve_display_reset_state(meter_statistics)
    rows = get_latest_rows()
    jump_events = []
    jump_event_ids = set()
    energy_display_mode = str(meter_statistics.get("energy_display_mode", "display") or "display")
    for row in rows:
        raw_energy = _safe_float(row.get("electric_energy"), 0.0)
        display_energy = _apply_row_display_reset(row, display_reset_state)
        row["raw_electric_energy"] = round(raw_energy, 4)
        row["display_electric_energy"] = round(display_energy, 4)
        row["effective_electric_energy"] = round(display_energy if energy_display_mode != "raw" else raw_energy, 4)
        row["display_reset_baseline"] = round(_get_row_display_reset_baseline(row, display_reset_state), 4)
        row["display_reset_applied"] = bool(display_reset_state.get("applied"))
        row["power_is_estimated"] = not _is_native_power_row(row)
        row["data_quality"] = str(row.get("data_quality") or _resolve_data_quality(row))
        row["effective_realtime_power"] = round(_stable_power_value(row), 4)
        row["stable_realtime_power"] = round(_stable_power_value(row), 4)
        row["raw_realtime_power"] = round(max(_safe_float(row.get("raw_realtime_power"), _safe_float(row.get("realtime_power"), 0.0)), 0.0), 4)
        cache_events = ((row.get("_energy_cache") or {}).get("events") or [])
        if isinstance(cache_events, list):
            for item in cache_events:
                if not isinstance(item, dict):
                    continue
                event_id = str(item.get("event_id") or "").strip()
                if not event_id or event_id in jump_event_ids:
                    continue
                jump_event_ids.add(event_id)
                event_payload = dict(item)
                event_payload["meter_id"] = str(row.get("meter_id") or row.get("id") or "")
                event_payload["display_name"] = row.get("display_name") or row.get("name") or row.get("id") or ""
                event_payload["source_key"] = str(row.get("source_key") or "")
                jump_events.append(event_payload)
    jump_events = sorted(jump_events, key=lambda item: str(item.get("detected_at") or ""), reverse=True)
    visible_rows = [row for row in rows if bool(row.get("visible_in_meter_center", True))]
    summary_rows = _filter_summary_rows(rows, meter_statistics)
    total_power = _sum_rows_native_power(summary_rows)
    estimated_total_power = _sum_rows_power(summary_rows)
    raw_total_daily = sum(_safe_float(row.get("daily_energy"), 0.0) for row in summary_rows)
    total_monthly = sum(_safe_float(row.get("monthly_energy"), 0.0) for row in summary_rows)
    total_energy = sum(_safe_float(row.get("electric_energy"), 0.0) for row in summary_rows)
    display_total_energy = _apply_display_reset(total_energy, meter_statistics)
    reset_from = str(display_reset_state.get("from") or "").strip()
    reset_is_today = bool(display_reset_state.get("applied")) and bool(reset_from) and reset_from[:10] == datetime.now().strftime("%Y-%m-%d")
    total_daily = display_total_energy if reset_is_today else raw_total_daily
    effective_total_energy = display_total_energy if energy_display_mode != "raw" else total_energy
    targets = [{"source_key": "total", "label": "全部统计电表", "type": "total"}]
    area_names = sorted({str(row.get("area_name") or "").strip() for row in visible_rows if str(row.get("area_name") or "").strip()})
    for area_name in area_names:
        targets.append({"source_key": f"area:{area_name}", "label": f"{area_name}（区域）", "type": "area", "area_name": area_name})
    targets.extend([{"source_key": row.get("source_key"), "label": row.get("display_name") or row.get("id"), "type": row.get("source_type"), "area_name": row.get("area_name", "")} for row in visible_rows])
    resolved = _resolve_target(summary_rows, target_source_key)
    target_rows = resolved.get("rows", []) if resolved else []
    day_map = {}
    if resolved and target_rows:
        for row in target_rows:
            history_key = _resolve_history_cache_key(row)
            if not history_key:
                continue
            history = get_history_rows(history_key, current_daily=row.get("daily_energy", 0.0), days=days)
            for item in history:
                day_map[item["date"]] = day_map.get(item["date"], 0.0) + _safe_float(item.get("consume"), 0.0)
    daily_rows = [{"date": day_text, "consume": round(day_map[day_text], 4), "is_today": day_text == datetime.now().strftime("%Y-%m-%d")} for day_text in sorted(day_map.keys())]
    history_energy_cap = _resolve_history_energy_cap(target_rows, total_energy, display_total_energy, effective_total_energy)
    daily_rows, trend_breakdown, comparison, history_outlier_dates = _sanitize_history_rows(daily_rows, period, history_energy_cap)
    reference_source_key = str(meter_statistics.get("reference_total_meter_source_key", "") or "").strip()
    reference_row = _find_reference_row(rows, reference_source_key)
    reference_meter = _build_reference_meter_payload(reference_row)
    compare_to_reference = {}
    if reference_meter:
        compare_to_reference = {
            "power": {"available": False, "disabled": True, "reason": "power_comparison_disabled"},
            "daily_energy": _build_reference_metric(total_daily, reference_meter.get("daily_energy")),
            "monthly_energy": _build_reference_metric(total_monthly, reference_meter.get("monthly_energy")),
            "electric_energy": _build_reference_metric(effective_total_energy, reference_meter.get("effective_electric_energy")),
        }
    quality_counts = _build_quality_counts(visible_rows)
    raw_total_power = sum(max(_safe_float(row.get("raw_realtime_power"), _safe_float(row.get("realtime_power"), 0.0)), 0.0) for row in summary_rows)
    return {
        "summary": {
            "total": len(visible_rows),
            "online": sum(1 for row in visible_rows if bool(row.get("online", False))),
            "offline": max(len(visible_rows) - sum(1 for row in visible_rows if bool(row.get("online", False))), 0),
            "total_realtime_power": round(total_power, 2),
            "card_total_realtime_power": round(estimated_total_power, 2),
            "estimated_total_realtime_power": round(estimated_total_power, 2),
            "stable_total_realtime_power": round(estimated_total_power, 2),
            "raw_total_realtime_power": round(raw_total_power, 2),
            "total_daily_energy": round(total_daily, 1),
            "raw_total_daily_energy": round(raw_total_daily, 1),
            "total_monthly_energy": round(total_monthly, 1),
            "total_electric_energy": round(total_energy, 1),
            "display_total_electric_energy": round(display_total_energy, 1),
            "effective_total_electric_energy": round(effective_total_energy, 1),
            "energy_display_mode": energy_display_mode,
            "display_reset_enabled": bool(display_reset_state.get("enabled")),
            "display_reset_from": reset_from,
            "display_reset_value": round(_safe_float(display_reset_state.get("value"), 0.0), 4),
            "display_reset_pending": bool(display_reset_state.get("pending")),
            "display_reset_due": bool(display_reset_state.get("due")),
            "display_reset_applied": bool(display_reset_state.get("applied")),
            "display_reset_captured_at": str(display_reset_state.get("captured_at") or ""),
            "display_reset_baseline_meter_count": int(display_reset_state.get("baseline_meter_count") or 0),
            "type_counts": _serialize_type_counts(visible_rows),
            "quality_counts": quality_counts,
            "comparison_day": comparison,
            "reference_total_meter_source_key": reference_source_key,
            "reference_meter": reference_meter,
            "compare_to_reference": compare_to_reference,
            "daily_jump_reset_count": len(jump_events),
        },
        "meters": visible_rows,
        "trend": daily_rows,
        "trend_breakdown": trend_breakdown,
        "trend_target": resolved.get("target") if resolved else None,
        "trend_target_label": resolved.get("label") if resolved else "",
        "trend_period": period,
        "trend_days": days,
        "trend_targets": targets,
        "history_outlier_dates": history_outlier_dates,
        "meter_alerts": {
            "daily_jump_resets": jump_events[:20],
        },
        "dashboard_summary": {
            "power": round(estimated_total_power, 2),
            "estimated_power": round(estimated_total_power, 2),
            "stable_power": round(estimated_total_power, 2),
            "raw_power": round(raw_total_power, 2),
            "daily_energy": round(total_daily, 1),
            "raw_daily_energy": round(raw_total_daily, 1),
            "monthly_energy": round(total_monthly, 1),
            "electric_energy": round(total_energy, 1),
            "display_electric_energy": round(display_total_energy, 1),
            "effective_electric_energy": round(effective_total_energy, 1),
            "energy_display_mode": energy_display_mode,
            "display_reset_enabled": bool(display_reset_state.get("enabled")),
            "display_reset_from": reset_from,
            "display_reset_value": round(_safe_float(display_reset_state.get("value"), 0.0), 4),
            "display_reset_pending": bool(display_reset_state.get("pending")),
            "display_reset_due": bool(display_reset_state.get("due")),
            "display_reset_applied": bool(display_reset_state.get("applied")),
            "display_reset_captured_at": str(display_reset_state.get("captured_at") or ""),
            "comparison_day": comparison,
            "reference_total_meter_source_key": reference_source_key,
            "reference_meter": reference_meter,
            "compare_to_reference": compare_to_reference,
            "quality_counts": quality_counts,
            "daily_jump_reset_count": len(jump_events),
        },
    }


def sync_config(payload):
    config = load_config()
    config["cabinets"] = list(payload.get("cabinets", []))
    config["meters"] = list(payload.get("meters", []))
    current_ms = config.get("meter_statistics", {}) or {}
    current_ms.update(payload.get("meter_statistics", {}) or {})
    config["meter_statistics"] = current_ms
    return save_config(config)


def export_reports_now():
    config = load_config()
    meter_statistics = config.get("meter_statistics", {}) or {}
    payload = build_meter_payload(
        target_source_key=str(meter_statistics.get("default_trend_mode", "total") or "total"),
        period="day",
        days=max(int(meter_statistics.get("history_keep_days", 90) or 90), 35),
    )
    payload["data_source"] = "meter_service"
    return export_reports_snapshot(payload, meter_statistics)


def report_export_loop():
    time.sleep(5)
    while True:
        try:
            export_reports_now()
        except Exception:
            pass
        time.sleep(60)


def start_background_threads():
    threading.Thread(target=meter_poll_loop, daemon=True).start()
    threading.Thread(target=report_export_loop, daemon=True).start()
