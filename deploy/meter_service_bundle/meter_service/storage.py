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
            if row:
                consume = max(float(row[1] or 0.0) - float(row[0] or 0.0), 0.0)
            else:
                consume = 0.0
        rows.append({"date": day_text, "consume": round(consume, 4), "is_today": idx == len(day_list) - 1})
    conn.close()
    return rows


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


def cleanup_history(keep_days=90):
    cutoff = (datetime.now().date() - timedelta(days=max(int(keep_days or 90), 1))).strftime("%Y-%m-%d")
    snapshot_cutoff = (datetime.now() - timedelta(days=max(int(keep_days or 90), 1))).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM meter_daily_records WHERE date < ?", (cutoff,))
    cur.execute("DELETE FROM meter_snapshots WHERE timestamp < ?", (snapshot_cutoff,))
    conn.commit()
    conn.close()
