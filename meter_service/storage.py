import json
import os
import sqlite3
from datetime import datetime, timedelta

from .config_store import DATA_DIR

DB_PATH = os.path.join(DATA_DIR, "meter_service.db")


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS meter_latest (
            meter_id TEXT PRIMARY KEY,
            source_type TEXT,
            display_name TEXT,
            area_name TEXT,
            online INTEGER,
            payload_json TEXT,
            updated_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS meter_daily_records (
            cache_key TEXT,
            date TEXT,
            start_energy REAL,
            end_energy REAL,
            PRIMARY KEY (cache_key, date)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS meter_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meter_id TEXT,
            timestamp TEXT,
            electric_energy REAL,
            realtime_power REAL,
            payload_json TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_meter_snapshots_meter_time
        ON meter_snapshots (meter_id, timestamp)
        """
    )
    conn.commit()
    conn.close()


def upsert_latest(row):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO meter_latest (meter_id, source_type, display_name, area_name, online, payload_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(meter_id) DO UPDATE SET
            source_type=excluded.source_type,
            display_name=excluded.display_name,
            area_name=excluded.area_name,
            online=excluded.online,
            payload_json=excluded.payload_json,
            updated_at=excluded.updated_at
        """,
        (
            str(row.get("id") or ""),
            str(row.get("source_type") or ""),
            str(row.get("display_name") or row.get("name") or row.get("id") or ""),
            str(row.get("area_name") or ""),
            1 if bool(row.get("online", False)) else 0,
            json.dumps(row, ensure_ascii=False),
            str(row.get("updated_at") or datetime.now().isoformat()),
        ),
    )
    conn.commit()
    conn.close()


def insert_snapshot(row):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO meter_snapshots (meter_id, timestamp, electric_energy, realtime_power, payload_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            str(row.get("id") or ""),
            str(row.get("updated_at") or datetime.now().isoformat()),
            float(row.get("electric_energy") or 0.0),
            float(row.get("realtime_power") or 0.0),
            json.dumps(row, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()


def get_daily_record(cache_key, date_text):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT start_energy, end_energy FROM meter_daily_records WHERE cache_key=? AND date=?",
        (cache_key, date_text),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"start_energy": float(row[0] or 0.0), "end_energy": float(row[1] or 0.0)}


def init_daily_record(cache_key, date_text, current_energy):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO meter_daily_records (cache_key, date, start_energy, end_energy)
        VALUES (?, ?, ?, ?)
        """,
        (cache_key, date_text, float(current_energy or 0.0), float(current_energy or 0.0)),
    )
    conn.commit()
    conn.close()


def reset_daily_record(cache_key, date_text, current_energy):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO meter_daily_records (cache_key, date, start_energy, end_energy)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(cache_key, date) DO UPDATE SET
            start_energy=excluded.start_energy,
            end_energy=excluded.end_energy
        """,
        (cache_key, date_text, float(current_energy or 0.0), float(current_energy or 0.0)),
    )
    conn.commit()
    conn.close()


def update_daily_record(cache_key, date_text, current_energy):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT start_energy, end_energy FROM meter_daily_records WHERE cache_key=? AND date=?",
        (cache_key, date_text),
    )
    row = cur.fetchone()
    if row:
        end_energy = max(float(row[1] or 0.0), float(current_energy or 0.0))
        cur.execute(
            "UPDATE meter_daily_records SET end_energy=? WHERE cache_key=? AND date=?",
            (end_energy, cache_key, date_text),
        )
    else:
        cur.execute(
            "INSERT INTO meter_daily_records (cache_key, date, start_energy, end_energy) VALUES (?, ?, ?, ?)",
            (cache_key, date_text, float(current_energy or 0.0), float(current_energy or 0.0)),
        )
    conn.commit()
    conn.close()


def get_history_rows(cache_key, current_daily=0.0, days=30):
    days = max(1, int(days or 30))
    today = datetime.now().date()
    day_list = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days - 1, -1, -1)]
    snapshot_estimates = _get_snapshot_daily_estimates(cache_key, day_list[:-1])
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    rows = []
    for idx, day_text in enumerate(day_list):
        if idx == len(day_list) - 1:
            consume = max(float(current_daily or 0.0), 0.0)
        else:
            cur.execute(
                "SELECT start_energy, end_energy FROM meter_daily_records WHERE cache_key=? AND date=?",
                (cache_key, day_text),
            )
            row = cur.fetchone()
            estimated_consume = _safe_float(snapshot_estimates.get(day_text), None)
            if row:
                consume = max(float(row[1] or 0.0) - float(row[0] or 0.0), 0.0)
                if estimated_consume is not None:
                    if consume <= 0:
                        consume = max(float(estimated_consume), 0.0)
                    elif consume > max(float(estimated_consume) * 4.0, float(estimated_consume) + 200.0, 1000.0):
                        consume = max(float(estimated_consume), 0.0)
            else:
                consume = max(float(estimated_consume or 0.0), 0.0)
        rows.append({"date": day_text, "consume": round(consume, 4), "is_today": idx == len(day_list) - 1})
    conn.close()
    return rows


def _safe_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _cache_key_to_snapshot_meter_id(cache_key):
    key = str(cache_key or "").strip()
    if not key:
        return ""
    if key.startswith("meter:"):
        return key.split(":", 1)[1].strip()
    if key.startswith("cabinet:"):
        cab_idx = key.split(":", 1)[1].strip()
        return f"cabinet_meter_{cab_idx}" if cab_idx else ""
    return key


def _daily_consume_from_snapshot_values(values):
    nums = [float(v) for v in (values or []) if _safe_float(v, 0.0) > 0]
    if len(nums) < 6:
        return None
    nums.sort()
    size = len(nums)
    # Use a median-centered cluster to avoid mixed-scale glitches (same day dual ranges).
    mid_idx = size // 2
    median = nums[mid_idx] if size % 2 == 1 else (nums[mid_idx - 1] + nums[mid_idx]) / 2.0
    deviations = sorted(abs(v - median) for v in nums)
    d_size = len(deviations)
    d_mid = d_size // 2
    mad = deviations[d_mid] if d_size % 2 == 1 else (deviations[d_mid - 1] + deviations[d_mid]) / 2.0
    if mad <= 0:
        mad = max(median * 0.001, 1.0)
    # Allow normal intra-day growth but exclude far-away secondary clusters.
    band = max((6.0 * mad), (median * 0.2), 100.0)
    window = [v for v in nums if abs(v - median) <= band]
    if len(window) < max(6, int(size * 0.35)):
        low_idx = max(min(int(size * 0.1), size - 1), 0)
        high_idx = max(min(int(size * 0.9), size - 1), low_idx)
        window = nums[low_idx : high_idx + 1]
    if not window:
        return 0.0
    window.sort()
    w_size = len(window)
    w_low_idx = max(min(int(w_size * 0.05), w_size - 1), 0)
    w_high_idx = max(min(int(w_size * 0.95), w_size - 1), w_low_idx)
    return round(max(window[w_high_idx] - window[w_low_idx], 0.0), 4)


def _get_snapshot_daily_estimates(cache_key, day_list):
    days = [str(item or "").strip() for item in (day_list or []) if str(item or "").strip()]
    if not days:
        return {}
    meter_id = _cache_key_to_snapshot_meter_id(cache_key)
    if not meter_id:
        return {}
    day_from = min(days)
    day_to_date = datetime.strptime(max(days), "%Y-%m-%d").date() + timedelta(days=1)
    day_to = day_to_date.strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT timestamp, electric_energy
        FROM meter_snapshots
        WHERE meter_id=? AND timestamp>=? AND timestamp<? AND electric_energy>0
        ORDER BY timestamp ASC
        """,
        (meter_id, f"{day_from}T00:00:00", f"{day_to}T00:00:00"),
    )
    day_values = {}
    for ts, value in cur.fetchall():
        day_text = str(ts or "")[:10]
        if day_text in days:
            day_values.setdefault(day_text, []).append(float(value or 0.0))
    conn.close()
    result = {}
    for day_text in days:
        estimate = _daily_consume_from_snapshot_values(day_values.get(day_text, []))
        if estimate is not None:
            result[day_text] = round(max(float(estimate), 0.0), 4)
    return result


def get_period_start_energy(cache_key, date_from, date_to):
    date_from = str(date_from or "").strip()
    date_to = str(date_to or "").strip()
    if not cache_key or not date_from or not date_to:
        return None
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT date, start_energy
        FROM meter_daily_records
        WHERE cache_key=? AND date>=? AND date<=?
        ORDER BY date ASC
        LIMIT 1
        """,
        (cache_key, date_from, date_to),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return float(row[1] or 0.0)


def get_last_success_snapshot(meter_id, limit=240):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT payload_json
        FROM meter_snapshots
        WHERE meter_id=?
        ORDER BY id DESC
        LIMIT ?
        """,
        (str(meter_id or ""), max(int(limit or 240), 1)),
    )
    rows = cur.fetchall()
    conn.close()
    for row in rows:
        try:
            payload = json.loads(row[0] or "{}")
        except Exception:
            continue
        if bool(payload.get("online", False)):
            return payload
    return None


def get_recent_power_samples(meter_id, limit=5, scan_limit=24):
    limit = max(int(limit or 5), 1)
    scan_limit = max(int(scan_limit or (limit * 4)), limit)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT realtime_power
        FROM meter_snapshots
        WHERE meter_id=?
        ORDER BY id DESC
        LIMIT ?
        """,
        (str(meter_id or ""), scan_limit),
    )
    rows = cur.fetchall()
    conn.close()
    samples = []
    for row in rows:
        try:
            value = float(row[0] or 0.0)
        except Exception:
            continue
        if value < 0:
            continue
        samples.append(value)
        if len(samples) >= limit:
            break
    samples.reverse()
    return samples


def cleanup_history(keep_days=90):
    cutoff = (datetime.now().date() - timedelta(days=max(int(keep_days or 90), 1))).strftime("%Y-%m-%d")
    snapshot_cutoff = (datetime.now() - timedelta(days=max(int(keep_days or 90), 1))).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM meter_daily_records WHERE date < ?", (cutoff,))
    cur.execute("DELETE FROM meter_snapshots WHERE timestamp < ?", (snapshot_cutoff,))
    conn.commit()
    conn.close()
