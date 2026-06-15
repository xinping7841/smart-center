# AI_MODULE: server_monitor_api_v2
# AI_PURPOSE: 服务器监控 API v2 — MAC 注册、心跳上报、GPU/磁盘/网络状态采集和 WOL 唤醒。
# AI_BOUNDARY: 不直接采集硬件数据；数据由 Agent 上报，本模块负责持久化和查询。
# AI_DATA_FLOW: 客户端 Agent 上报 -> /report 端点 -> SQLite monitor.db -> 服务器看板。
# AI_RUNTIME: node-120 生产服务，周期性清理旧数据。
# AI_RISK: 中，WOL 唤醒功能和心跳超时判断影响设备管理。
# AI_COMPAT: /report、/api/server/* 路由需保持外部兼容。
# AI_SEARCH_KEYWORDS: server monitor, agent report, WOL, MAC, GPU, heartbeat.
import json
import socket
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta

from flask import Blueprint, Response, jsonify, request

from config import SERVER_COMMANDS
from data_logger import add_log
from log_config import get_logger

_log = get_logger(__name__)


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
            _log.debug("non-critical error suppressed", exc_info=True)
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
            _log.debug("non-critical error suppressed", exc_info=True)
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
