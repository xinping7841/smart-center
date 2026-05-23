import json
import socket
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta

from flask import Blueprint, Response, jsonify, request

from config import SERVER_COMMANDS
from data_logger import add_log

bp = Blueprint('server', __name__)
DB_FILE = "monitor.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS machines (
            mac TEXT PRIMARY KEY,
            hostname TEXT,
            ip TEXT,
            last_online TEXT,
            data TEXT,
            is_manual INTEGER DEFAULT 0,
            custom_name TEXT
        )"""
    )
    for col, defval in [
        ("sort_order", "INTEGER DEFAULT 999"),
        ("remark", "TEXT DEFAULT ''"),
        ("card_size", "TEXT DEFAULT 'normal'"),
    ]:
        try:
            c.execute(f"ALTER TABLE machines ADD COLUMN {col} {defval}")
        except Exception:
            pass
    c.execute(
        """CREATE TABLE IF NOT EXISTS metrics_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac TEXT,
            timestamp TEXT,
            data TEXT
        )"""
    )
    conn.commit()
    conn.close()


def clean_old_history():
    while True:
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute(
                "DELETE FROM metrics_history WHERE timestamp < ?",
                ((datetime.now() - timedelta(hours=1)).isoformat(),),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass
        time.sleep(600)


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_server_host_from_request():
    host = request.headers.get("host", "").split(":")[0]
    if not host or host in ["127.0.0.1", "localhost"]:
        host = get_local_ip()
    return host
