import csv
import glob
import json
import os
from datetime import datetime, timedelta, date
from config import CONFIG, DEVICE_STATUS
from event_logger import record_legacy_operation
from paths import (
    DATA_DIR,
    ENERGY_LOG_FILE as ENERGY_LOG_PATH,
    OPERATION_LOG_FILE as LOG_FILE_PATH,
    ensure_parent_dir,
)

BASE_DIR = str(DATA_DIR)
PROJECT_NAME = os.path.basename(str(DATA_DIR))
LOG_FILE = str(LOG_FILE_PATH)
ENERGY_LOG_FILE = str(ENERGY_LOG_PATH)
ENERGY_HISTORY_DAYS = 30
_LOG_CACHE = {"mtime": 0.0, "logs": []}


def _safe_float(value, default=0.0):
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _read_json_file(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _cutoff_date_str(days=ENERGY_HISTORY_DAYS):
    return (date.today() - timedelta(days=max(days - 1, 0))).strftime("%Y-%m-%d")


def _normalize_daily_records(records, keep_days=ENERGY_HISTORY_DAYS):
    if not isinstance(records, list):
        return []
    cutoff = _cutoff_date_str(keep_days)
    grouped = {}
    for item in records:
        if not isinstance(item, dict):
            continue
        day = str(item.get("date") or "").strip()
        if len(day) != 10 or day < cutoff:
            continue
        try:
            start_energy = float(item.get("start_energy", 0) or 0)
            end_energy = float(item.get("end_energy", start_energy) or start_energy)
        except Exception:
            continue
        end_energy = max(end_energy, start_energy)
        if day not in grouped:
            grouped[day] = {"date": day, "start_energy": start_energy, "end_energy": end_energy}
        else:
            grouped[day]["start_energy"] = min(grouped[day]["start_energy"], start_energy)
            grouped[day]["end_energy"] = max(grouped[day]["end_energy"], end_energy)
    return [grouped[key] for key in sorted(grouped.keys())]


def _normalize_energy_log(data):
    normalized = {}
    if not isinstance(data, dict):
        data = {}
    for key, value in data.items():
        key_text = str(key)
        if key_text.isdigit() or ":" in key_text:
            cab_data = value if isinstance(value, dict) else {}
            normalized[key_text] = {
                "daily_records": _normalize_daily_records(cab_data.get("daily_records", [])),
                "monthly_records": cab_data.get("monthly_records", {}) if isinstance(cab_data.get("monthly_records", {}), dict) else {}
            }
    normalized["last_sync_time"] = str(data.get("last_sync_time") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return normalized


def _merge_energy_logs(base_data, incoming_data):
    merged = _normalize_energy_log(base_data)
    incoming = _normalize_energy_log(incoming_data)
    for key, cab_data in incoming.items():
        if not str(key).isdigit():
            continue
        if key not in merged:
            merged[key] = {"daily_records": [], "monthly_records": {}}
        merged[key]["daily_records"] = _normalize_daily_records(
            list(merged[key].get("daily_records", [])) + list(cab_data.get("daily_records", []))
        )
        merged[key]["monthly_records"] = {
            **merged[key].get("monthly_records", {}),
            **cab_data.get("monthly_records", {})
        }
    merged["last_sync_time"] = max(
        str(merged.get("last_sync_time") or ""),
        str(incoming.get("last_sync_time") or "")
    ) or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return merged


def _merge_power_history_only(base_data, incoming_data):
    merged = _normalize_energy_log(base_data)
    incoming = _normalize_energy_log(incoming_data)
    cabinet_keys = {str(idx) for idx in range(len(CONFIG.get("cabinets", [])))}
    for key in cabinet_keys:
        cab_data = incoming.get(key)
        if not isinstance(cab_data, dict):
            continue
        if key not in merged:
            merged[key] = {"daily_records": [], "monthly_records": {}}
        merged[key]["daily_records"] = _normalize_daily_records(
            list(merged[key].get("daily_records", [])) + list(cab_data.get("daily_records", []))
        )
        merged[key]["monthly_records"] = {
            **(cab_data.get("monthly_records", {}) if isinstance(cab_data.get("monthly_records", {}), dict) else {}),
            **merged[key].get("monthly_records", {}),
        }
    merged["last_sync_time"] = max(
        str(merged.get("last_sync_time") or ""),
        str(incoming.get("last_sync_time") or "")
    ) or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return merged


def _candidate_energy_log_files():
    parent_dir = os.path.dirname(BASE_DIR)
    patterns = [
        os.path.join(parent_dir, f"{PROJECT_NAME}_backup_*", "energy_log.json"),
        os.path.join(parent_dir, "project_backups", f"{PROJECT_NAME}_backup_*", "energy_log.json"),
    ]
    files = []
    for pattern in patterns:
        files.extend(glob.glob(pattern))
    return sorted({os.path.abspath(path) for path in files if os.path.abspath(path) != os.path.abspath(ENERGY_LOG_FILE)})


def _normalize_operation_logs(logs):
    if not isinstance(logs, list):
        return []
    normalized = []
    seen = set()
    for item in logs:
        if not isinstance(item, dict):
            continue
        time_text = str(item.get("time") or "").strip()
        operation = str(item.get("operation") or "").strip()
        if not time_text or not operation:
            continue
        normalized_item = dict(item)
        normalized_item["time"] = time_text
        normalized_item["operation"] = operation
        key = (
            time_text,
            str(normalized_item.get("cab_idx")),
            operation,
            str(normalized_item.get("category") or ""),
            str(normalized_item.get("status") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        normalized.append(normalized_item)
    normalized.sort(key=lambda entry: str(entry.get("time") or ""), reverse=True)
    return normalized[:500]


def _candidate_operation_log_files():
    candidates = []
    current_path = os.path.abspath(LOG_FILE)
    legacy_local = os.path.abspath(os.path.join(os.path.dirname(__file__), "operation_logs.json"))
    if legacy_local != current_path and os.path.exists(legacy_local):
        candidates.append(legacy_local)

    parent_dir = os.path.dirname(BASE_DIR)
    patterns = [
        os.path.join(parent_dir, f"{PROJECT_NAME}_backup_*", "operation_logs.json"),
        os.path.join(parent_dir, "project_backups", f"{PROJECT_NAME}_backup_*", "operation_logs.json"),
    ]
    for pattern in patterns:
        candidates.extend(glob.glob(pattern))
    return sorted({os.path.abspath(path) for path in candidates if os.path.abspath(path) != current_path})


def restore_operation_logs_from_backups():
    current = _read_json_file(LOG_FILE, [])
    merged = _normalize_operation_logs(current)
    changed = False
    for backup_path in _candidate_operation_log_files():
        backup_logs = _read_json_file(backup_path, [])
        combined = _normalize_operation_logs(merged + backup_logs)
        if combined != merged:
            merged = combined
            changed = True
    if changed:
        ensure_parent_dir(LOG_FILE_PATH)
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        try:
            _LOG_CACHE["mtime"] = os.path.getmtime(LOG_FILE)
            _LOG_CACHE["logs"] = merged
        except Exception:
            _LOG_CACHE["mtime"] = 0.0
            _LOG_CACHE["logs"] = merged
    return merged


def restore_energy_log_from_backups():
    current = _read_json_file(ENERGY_LOG_FILE, {})
    merged = _normalize_energy_log(current)
    # 旧备份里包含过异常电表数据，不能整份直接回灌。
    # 这里只安全回补强电柜历史，避免首页/详情页出现历史丢失。
    for backup_path in _candidate_energy_log_files():
        merged = _merge_power_history_only(merged, _read_json_file(backup_path, {}))
    if current != merged:
        save_energy_log(merged)
    return merged

def init_energy_log():
    if not os.path.exists(ENERGY_LOG_FILE):
        energy_log = {"last_sync_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        ensure_parent_dir(ENERGY_LOG_PATH)
        with open(ENERGY_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(energy_log, f, ensure_ascii=False, indent=2)

def load_logs(cab_idx=None):
    if not os.path.exists(LOG_FILE): 
        return []
    try:
        mtime = os.path.getmtime(LOG_FILE)
        if _LOG_CACHE["mtime"] != mtime:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            _LOG_CACHE["mtime"] = mtime
            _LOG_CACHE["logs"] = loaded if isinstance(loaded, list) else []
        logs = list(_LOG_CACHE["logs"])
    except: 
        return []
        
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()
    if cab_idx is not None:
        filtered = [l for l in logs if l.get("cab_idx") == cab_idx and l.get("time", "") > cutoff]
    else:
        filtered = [l for l in logs if l.get("time", "") > cutoff]
    return filtered

def add_log(cab_idx, operation):
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            logs = json.load(f)
    except:
        logs = []
        
    new_entry = {"time": datetime.now().isoformat(), "cab_idx": cab_idx, "operation": operation}
    logs.insert(0, new_entry)
    
    ensure_parent_dir(LOG_FILE_PATH)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs[:500], f, ensure_ascii=False, indent=2)
    try:
        _LOG_CACHE["mtime"] = os.path.getmtime(LOG_FILE)
        _LOG_CACHE["logs"] = logs[:500]
    except Exception:
        _LOG_CACHE["mtime"] = 0.0
        _LOG_CACHE["logs"] = logs[:500]
    try:
        record_legacy_operation(cab_idx, operation)
    except Exception:
        pass


def add_structured_log(cab_idx, operation, category="system", detail=None, actor=None, status="ok"):
    detail = detail if isinstance(detail, dict) else {}
    actor = actor if isinstance(actor, dict) else {}
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            logs = json.load(f)
    except Exception:
        logs = []

    if not isinstance(logs, list):
        logs = []

    new_entry = {
        "time": datetime.now().isoformat(),
        "cab_idx": cab_idx,
        "operation": operation,
        "category": str(category or "system"),
        "status": str(status or "ok"),
        "detail": detail,
        "actor": actor,
    }
    logs.insert(0, new_entry)

    ensure_parent_dir(LOG_FILE_PATH)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs[:500], f, ensure_ascii=False, indent=2)
    try:
        _LOG_CACHE["mtime"] = os.path.getmtime(LOG_FILE)
        _LOG_CACHE["logs"] = logs[:500]
    except Exception:
        _LOG_CACHE["mtime"] = 0.0
        _LOG_CACHE["logs"] = logs[:500]
    try:
        event_detail = dict(detail)
        event_detail.setdefault("source", "system")
        record_legacy_operation(cab_idx, operation, category=category, status=status, detail=event_detail, actor=actor)
    except Exception:
        pass

def load_energy_log():
    return _normalize_energy_log(_read_json_file(ENERGY_LOG_FILE, {}))

def save_energy_log(data):
    try:
        data = _normalize_energy_log(data)
        data["last_sync_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ensure_parent_dir(ENERGY_LOG_PATH)
        with open(ENERGY_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except: 
        pass

init_energy_log()
restore_energy_log_from_backups()
restore_operation_logs_from_backups()

def _get_cab_data(log_data, cab_idx):
    c_str = str(cab_idx)
    if c_str not in log_data: 
        log_data[c_str] = {"daily_records": [], "monthly_records": {}}
    return log_data[c_str]


def _normalize_reset_baseline(reset_cfg):
    baseline = {"enabled": False, "from": "", "value": 0.0}
    if isinstance(reset_cfg, dict):
        baseline["enabled"] = bool(reset_cfg.get("enabled", False))
        baseline["from"] = str(reset_cfg.get("from") or "").strip()
        baseline["value"] = _safe_float(reset_cfg.get("value", 0.0), 0.0)
    return baseline


def get_display_reset_baseline():
    meter_statistics = CONFIG.get("meter_statistics", {}) or {}
    baseline = _normalize_reset_baseline(meter_statistics.get("display_reset", {}))
    if baseline["from"]:
        return baseline
    legacy_enabled = bool(meter_statistics.get("display_reset_enabled", False))
    legacy_from = str(meter_statistics.get("display_reset_from") or "").strip()
    if legacy_enabled and legacy_from:
        return {"enabled": True, "from": legacy_from, "value": 0.0}
    return baseline


def apply_display_reset(value, when_text=None):
    numeric = _safe_float(value, 0.0)
    baseline = get_display_reset_baseline()
    if not baseline.get("enabled"):
        return round(numeric, 4)
    baseline_from = str(baseline.get("from") or "").strip()
    if not baseline_from:
        return round(numeric, 4)
    current_text = str(when_text or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if current_text < baseline_from:
        return round(numeric, 4)
    baseline_value = _safe_float(baseline.get("value", 0.0), 0.0)
    return round(max(numeric - baseline_value, 0.0), 4)


def calculate_display_reset_delta(current_total):
    baseline = get_display_reset_baseline()
    current = _safe_float(current_total, 0.0)
    if not baseline.get("enabled"):
        return round(current, 4)
    baseline_from = str(baseline.get("from") or "").strip()
    if not baseline_from:
        return round(current, 4)
    current_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if current_text < baseline_from:
        return round(current, 4)
    baseline_value = _safe_float(baseline.get("value", 0.0), 0.0)
    return round(max(current - baseline_value, 0.0), 4)

def get_daily_record(cab_idx, date_str):
    log_data = load_energy_log()
    cab_data = _get_cab_data(log_data, cab_idx)
    return next((r for r in cab_data["daily_records"] if r["date"] == date_str), None)

def init_daily_record(cab_idx, date_str, current_energy):
    log_data = load_energy_log()
    cab_data = _get_cab_data(log_data, cab_idx)
    record = next((r for r in cab_data["daily_records"] if r["date"] == date_str), None)
    
    if not record:
        cab_data["daily_records"].append({"date": date_str, "start_energy": current_energy, "end_energy": current_energy})
        cab_data["daily_records"].sort(key=lambda x: x["date"])
        save_energy_log(log_data)
    else:
        # 【核心修复】：历史脏数据自愈算法
        # 如果之前因为通讯故障存了一个0作为起步电量，现在读到了真实大电量，强行修复起步基准线
        if record["start_energy"] == 0 and current_energy > 10:
            record["start_energy"] = current_energy
            if record["end_energy"] < current_energy:
                record["end_energy"] = current_energy
            save_energy_log(log_data)

def update_daily_record(cab_idx, date_str, current_energy):
    log_data = load_energy_log()
    cab_data = _get_cab_data(log_data, cab_idx)
    record = next((r for r in cab_data["daily_records"] if r["date"] == date_str), None)
    if record:
        # 异常跳变防波堤：只有当前读数比记录大，才更新结束电量，过滤掉通讯闪断带来的 0 值
        if current_energy > record["end_energy"]:
            record["end_energy"] = current_energy
            save_energy_log(log_data)
    else:
        init_daily_record(cab_idx, date_str, current_energy)

def calculate_daily_energy(cab_idx, date_str):
    record = get_daily_record(cab_idx, date_str)
    if not record: return 0.0
    return round(record["end_energy"] - record["start_energy"], 1)

def get_energy_history_data(cab_idx, days=ENERGY_HISTORY_DAYS):
    if cab_idx not in DEVICE_STATUS: return []
    days = max(1, int(days or ENERGY_HISTORY_DAYS))
    day_list = [(date.today() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days - 1, -1, -1)]
    data = []
    for i, day in enumerate(day_list):
        consume = DEVICE_STATUS[cab_idx].get("daily_energy", 0) if i == len(day_list) - 1 else calculate_daily_energy(cab_idx, day)
        consume = round(max(consume, 0.0), 1)
        data.append({"date": day, "consume": consume, "is_today": i == len(day_list) - 1})
    return data


def get_7days_energy_data(cab_idx):
    return get_energy_history_data(cab_idx, 7)


def get_30days_energy_data(cab_idx):
    return get_energy_history_data(cab_idx, ENERGY_HISTORY_DAYS)


def export_energy_history_rows(days=ENERGY_HISTORY_DAYS):
    days = max(1, int(days or ENERGY_HISTORY_DAYS))
    rows = []
    for cab_idx, cab in enumerate(CONFIG.get("cabinets", [])):
        for item in get_energy_history_data(cab_idx, days):
            rows.append({
                "cab_idx": cab_idx,
                "cabinet_name": cab.get("cabinet_name", f"电柜{cab_idx}"),
                "date": item.get("date"),
                "consume_kwh": round(float(item.get("consume", 0) or 0), 1),
                "is_today": bool(item.get("is_today"))
            })
    return rows


def get_energy_cache_key(source_type, source_id):
    return f"{source_type}:{source_id}"


def get_generic_daily_record(source_type, source_id, date_str):
    log_data = load_energy_log()
    cab_data = _get_cab_data(log_data, get_energy_cache_key(source_type, source_id))
    return next((r for r in cab_data["daily_records"] if r["date"] == date_str), None)


def init_generic_daily_record(source_type, source_id, date_str, current_energy):
    log_data = load_energy_log()
    cab_data = _get_cab_data(log_data, get_energy_cache_key(source_type, source_id))
    record = next((r for r in cab_data["daily_records"] if r["date"] == date_str), None)
    if not record:
        cab_data["daily_records"].append({"date": date_str, "start_energy": current_energy, "end_energy": current_energy})
        cab_data["daily_records"].sort(key=lambda x: x["date"])
        save_energy_log(log_data)
    else:
        if record["start_energy"] == 0 and current_energy > 0:
            record["start_energy"] = current_energy
            if record["end_energy"] < current_energy:
                record["end_energy"] = current_energy
            save_energy_log(log_data)


def update_generic_daily_record(source_type, source_id, date_str, current_energy):
    log_data = load_energy_log()
    cab_data = _get_cab_data(log_data, get_energy_cache_key(source_type, source_id))
    record = next((r for r in cab_data["daily_records"] if r["date"] == date_str), None)
    if record:
        if current_energy > record["end_energy"]:
            record["end_energy"] = current_energy
            save_energy_log(log_data)
    else:
        init_generic_daily_record(source_type, source_id, date_str, current_energy)


def calculate_generic_daily_energy(source_type, source_id, date_str):
    record = get_generic_daily_record(source_type, source_id, date_str)
    if not record:
        return 0.0
    return round(max(_safe_float(record.get("end_energy")) - _safe_float(record.get("start_energy")), 0.0), 4)


def get_generic_energy_history_data(source_type, source_id, current_daily=0.0, days=ENERGY_HISTORY_DAYS):
    days = max(1, int(days or ENERGY_HISTORY_DAYS))
    day_list = [(date.today() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days - 1, -1, -1)]
    rows = []
    for i, day in enumerate(day_list):
        consume = _safe_float(current_daily if i == len(day_list) - 1 else calculate_generic_daily_energy(source_type, source_id, day), 0.0)
        rows.append({
            "date": day,
            "consume": round(max(consume, 0.0), 4),
            "is_today": i == len(day_list) - 1
        })
    return rows


def _group_period_rows(rows, mode):
    grouped = {}
    for row in rows:
        date_text = str(row.get("date") or "")
        if len(date_text) != 10:
            continue
        try:
            dt = datetime.strptime(date_text, "%Y-%m-%d").date()
        except Exception:
            continue
        consume = _safe_float(row.get("consume"), 0.0)
        if mode == "week":
            year, week, _ = dt.isocalendar()
            key = f"{year}-W{week:02d}"
        elif mode == "month":
            key = dt.strftime("%Y-%m")
        else:
            key = date_text
        grouped[key] = grouped.get(key, 0.0) + consume
    return [{"period": key, "consume": round(grouped[key], 4)} for key in sorted(grouped.keys())]


def summarize_period_rows(rows):
    daily = [{"period": str(item.get("date") or ""), "consume": round(_safe_float(item.get("consume"), 0.0), 4)} for item in rows]
    return {
        "daily": daily,
        "weekly": _group_period_rows(rows, "week"),
        "monthly": _group_period_rows(rows, "month"),
    }


def compare_with_previous(rows):
    ordered = [item for item in rows if str(item.get("period") or "").strip()]
    if len(ordered) < 2:
        current = _safe_float(ordered[-1]["consume"], 0.0) if ordered else 0.0
        return {
            "current": round(current, 4),
            "previous": 0.0,
            "delta": round(current, 4),
            "delta_pct": None,
            "trend": "flat"
        }
    current = _safe_float(ordered[-1]["consume"], 0.0)
    previous = _safe_float(ordered[-2]["consume"], 0.0)
    delta = current - previous
    if previous > 0:
        delta_pct = round(delta / previous * 100.0, 2)
    else:
        delta_pct = None
    trend = "up" if delta > 0 else ("down" if delta < 0 else "flat")
    return {
        "current": round(current, 4),
        "previous": round(previous, 4),
        "delta": round(delta, 4),
        "delta_pct": delta_pct,
        "trend": trend
    }


def export_meter_statistics_csv(target_label, rows, report_dir, prefix="meter_stats"):
    os.makedirs(report_dir, exist_ok=True)
    filename = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    file_path = os.path.join(report_dir, filename)
    with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["target", "period_key", "consume_kwh"])
        for row in rows:
            writer.writerow([target_label, row.get("period"), row.get("consume")])
    return file_path


def export_meter_snapshot_csv(rows, report_dir, prefix="meter_raw_snapshot"):
    os.makedirs(report_dir, exist_ok=True)
    filename = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    file_path = os.path.join(report_dir, filename)
    headers = [
        "source_key", "source_type", "meter_id", "display_name", "area_name",
        "visible_in_meter_center", "include_in_totals", "include_in_reports",
        "online", "protocol", "ip", "port", "station_id",
        "realtime_power", "daily_energy", "monthly_energy", "electric_energy",
        "voltage_a", "voltage_b", "voltage_c",
        "current_a", "current_b", "current_c",
        "power_factor", "frequency", "updated_at"
    ]
    with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([
                row.get("source_key", ""),
                row.get("source_type", ""),
                row.get("meter_id", row.get("id", "")),
                row.get("display_name") or row.get("cabinet_name") or row.get("id", ""),
                row.get("area_name", ""),
                1 if bool(row.get("visible_in_meter_center", True)) else 0,
                1 if bool(row.get("include_in_totals", True)) else 0,
                1 if bool(row.get("include_in_reports", True)) else 0,
                1 if bool(row.get("online", False)) else 0,
                row.get("protocol", ""),
                row.get("ip", ""),
                row.get("port", ""),
                row.get("station_id", ""),
                round(_safe_float(row.get("realtime_power"), 0.0), 4),
                round(_safe_float(row.get("daily_energy"), 0.0), 4),
                round(_safe_float(row.get("monthly_energy"), 0.0), 4),
                round(_safe_float(row.get("electric_energy"), 0.0), 4),
                round(_safe_float(row.get("voltage_a"), 0.0), 4),
                round(_safe_float(row.get("voltage_b"), 0.0), 4),
                round(_safe_float(row.get("voltage_c"), 0.0), 4),
                round(_safe_float(row.get("current_a"), 0.0), 4),
                round(_safe_float(row.get("current_b"), 0.0), 4),
                round(_safe_float(row.get("current_c"), 0.0), 4),
                round(_safe_float(row.get("power_factor"), 0.0), 4),
                round(_safe_float(row.get("frequency"), 0.0), 4),
                row.get("updated_at", "")
            ])
    return file_path
