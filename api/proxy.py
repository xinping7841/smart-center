# AI_MODULE: proxy_monitor_api
# AI_PURPOSE: 121 代理服务状态、链路测试、客户端使用和网卡流量摘要接口。
# AI_BOUNDARY: 不直接配置代理服务；只读取 background 写入的 PROXY_STATUS。
# AI_DATA_FLOW: background 采集 node-121/squid/NIC -> PROXY_STATUS -> /api/proxy/status。
# AI_RUNTIME: 代理监控页轮询。
# AI_RISK: 中，流量/在线判断错误会影响网络排障。
# AI_COMPAT: Google/YouTube/GPT/GitHub 测试状态和 Mbps 字段需兼容前端。
# AI_SEARCH_KEYWORDS: proxy, squid, node-121, traffic, Mbps, google, youtube.

from flask import Blueprint, jsonify

from auth.decorators import require_permission
from config import CONFIG
from runtime.state import PROXY_STATUS


bp = Blueprint("proxy", __name__)

PROXY_TRAFFIC_EXIT_HOST = "172.16.201.169"
PROXY_TRAFFIC_EXIT_IFNAME = "enp1s0"
PROXY_TRAFFIC_EXIT_SOURCE = "nic_ssh"
PROXY_TRAFFIC_EXIT_SSH_TARGET = "node-121"
PROXY_TRAFFIC_EXIT_LOCAL_USER = "xinping"


def _normalize_proxy_exit_traffic_config(config_payload):
    payload = dict(config_payload or {})
    payload["traffic_enabled"] = bool(payload.get("traffic_enabled", True))
    payload["traffic_source"] = PROXY_TRAFFIC_EXIT_SOURCE
    payload["traffic_device_id"] = ""
    payload["traffic_host"] = PROXY_TRAFFIC_EXIT_HOST
    payload["traffic_ifindex"] = 0
    payload["traffic_ifname"] = PROXY_TRAFFIC_EXIT_IFNAME
    payload["traffic_ssh_target"] = str(
        payload.get("traffic_ssh_target") or PROXY_TRAFFIC_EXIT_SSH_TARGET
    ).strip() or PROXY_TRAFFIC_EXIT_SSH_TARGET
    payload["traffic_local_user"] = str(
        payload.get("traffic_local_user") or PROXY_TRAFFIC_EXIT_LOCAL_USER
    ).strip() or PROXY_TRAFFIC_EXIT_LOCAL_USER
    return payload


def _normalize_proxy_exit_traffic_status(status, config_payload):
    traffic = dict((status or {}).get("traffic", {}) or {})
    if str(traffic.get("source") or "").strip().lower() == PROXY_TRAFFIC_EXIT_SOURCE:
        return

    status["traffic"] = {
        "enabled": bool(config_payload.get("traffic_enabled", True)),
        "available": False,
        "rx_bps": 0.0,
        "tx_bps": 0.0,
        "rx_mbps": 0.0,
        "tx_mbps": 0.0,
        "rx_text": "--",
        "tx_text": "--",
        "source": PROXY_TRAFFIC_EXIT_SOURCE,
        "device_id": str(config_payload.get("traffic_ssh_target") or PROXY_TRAFFIC_EXIT_SSH_TARGET),
        "host": PROXY_TRAFFIC_EXIT_HOST,
        "ifindex": 0,
        "ifname": PROXY_TRAFFIC_EXIT_IFNAME,
        "updated_at": None,
        "error": "waiting for 172 exit nic traffic sample",
    }


def _resolved_proxy_monitor_config():
    raw_cfg = CONFIG.get("proxy_monitor", {}) or {}
    if not isinstance(raw_cfg, dict):
        raw_cfg = {}
    try:
        port = int(raw_cfg.get("port", 3128) or 3128)
    except Exception:
        port = 3128
    try:
        timeout_sec = float(raw_cfg.get("timeout_sec", 6.0) or 6.0)
    except Exception:
        timeout_sec = 6.0
    try:
        poll_interval_sec = float(raw_cfg.get("poll_interval_sec", 20.0) or 20.0)
    except Exception:
        poll_interval_sec = 20.0
    poll_interval_sec = max(30.0, poll_interval_sec)
    try:
        traffic_ifindex = int(raw_cfg.get("traffic_ifindex", 0) or 0)
    except Exception:
        traffic_ifindex = 0
    try:
        client_monitor_recent_seconds = int(raw_cfg.get("client_monitor_recent_seconds", 300) or 300)
    except Exception:
        client_monitor_recent_seconds = 300
    client_monitor_recent_seconds = max(30, min(client_monitor_recent_seconds, 3600))
    try:
        client_monitor_tail_lines = int(raw_cfg.get("client_monitor_tail_lines", 8000) or 8000)
    except Exception:
        client_monitor_tail_lines = 8000
    client_monitor_tail_lines = max(500, min(client_monitor_tail_lines, 2000))
    try:
        client_monitor_timeout_sec = float(raw_cfg.get("client_monitor_timeout_sec", 6.0) or 6.0)
    except Exception:
        client_monitor_timeout_sec = 6.0
    client_monitor_timeout_sec = max(2.0, min(client_monitor_timeout_sec, 20.0))
    traffic_source = str(raw_cfg.get("traffic_source") or "nic_ssh").strip().lower()
    if traffic_source not in {"auto", "snmp", "server", "nic_ssh", "none"}:
        traffic_source = "nic_ssh"
    return _normalize_proxy_exit_traffic_config({
        "enabled": bool(raw_cfg.get("enabled", True)),
        "host": str(raw_cfg.get("host") or "192.168.50.121").strip(),
        "port": port,
        "timeout_sec": timeout_sec,
        "poll_interval_sec": poll_interval_sec,
        "check_urls": list(raw_cfg.get("check_urls") or ["https://www.google.com", "https://chatgpt.com"]),
        "traffic_enabled": bool(raw_cfg.get("traffic_enabled", True)),
        "traffic_source": traffic_source,
        "traffic_device_id": str(raw_cfg.get("traffic_device_id") or "").strip(),
        "traffic_host": str(raw_cfg.get("traffic_host") or "").strip(),
        "traffic_ifindex": traffic_ifindex,
        "traffic_ifname": str(raw_cfg.get("traffic_ifname") or "").strip(),
        "traffic_ssh_target": str(raw_cfg.get("traffic_ssh_target") or "node-121").strip(),
        "traffic_local_user": str(raw_cfg.get("traffic_local_user") or "xinping").strip(),
        "traffic_timeout_sec": float(raw_cfg.get("traffic_timeout_sec", 6.0) or 6.0),
        "client_monitor_enabled": bool(raw_cfg.get("client_monitor_enabled", True)),
        "client_monitor_ssh_target": str(raw_cfg.get("client_monitor_ssh_target") or "node-121").strip(),
        "client_monitor_local_user": str(raw_cfg.get("client_monitor_local_user") or "xinping").strip(),
        "client_monitor_recent_seconds": client_monitor_recent_seconds,
        "client_monitor_tail_lines": client_monitor_tail_lines,
        "client_monitor_timeout_sec": client_monitor_timeout_sec,
    })


def _empty_clients_payload(config_payload):
    return {
        "enabled": bool(config_payload.get("client_monitor_enabled", True)),
        "available": False,
        "source": "ssh-ss-squid",
        "active_client_count": 0,
        "total_active_connections": 0,
        "recent_client_count": 0,
        "recent_seconds": int(config_payload.get("client_monitor_recent_seconds") or 300),
        "download_bps": 0.0,
        "upload_bps": 0.0,
        "download_text": "0 bps",
        "upload_text": "0 bps",
        "clients": [],
        "updated_at": None,
        "error": "client monitor not initialized",
    }


@bp.route("/api/proxy/status")
@require_permission("server.view")
def api_proxy_status():
    status = dict(PROXY_STATUS.get("default", {}) or {})
    config_payload = _resolved_proxy_monitor_config()
    if not status:
        status = {
            "id": "office_proxy",
            "name": "office_proxy",
            "enabled": bool(config_payload.get("enabled", True)),
            "online": False,
            "stale": True,
            "status_level": "offline",
            "status_label": "离线",
            "error": "proxy monitor not initialized",
            "last_error": "proxy monitor not initialized",
            "updated_at": None,
            "last_checked_at": None,
            "last_success_at": None,
            "poll_failures": 0,
            "host": config_payload.get("host"),
            "port": config_payload.get("port"),
            "healthy_target_count": 0,
            "check_count": 0,
            "checks": [],
            "traffic": {
                "enabled": bool(config_payload.get("traffic_enabled", True)),
                "available": False,
                "rx_bps": 0.0,
                "tx_bps": 0.0,
                "rx_mbps": 0.0,
                "tx_mbps": 0.0,
                "rx_text": "--",
                "tx_text": "--",
                "source": str(config_payload.get("traffic_source") or "nic_ssh"),
                "device_id": "",
                "host": "",
                "ifindex": 0,
                "ifname": "",
                "updated_at": None,
                "error": "traffic monitor not initialized",
            },
            "clients": _empty_clients_payload(config_payload),
        }
    elif not isinstance(status.get("clients"), dict):
        status["clients"] = _empty_clients_payload(config_payload)
    _normalize_proxy_exit_traffic_status(status, config_payload)
    status["config"] = config_payload
    return jsonify(status)
