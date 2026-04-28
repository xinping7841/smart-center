from flask import Blueprint, jsonify

from auth.decorators import require_permission
from config import CONFIG
from runtime.state import PROXY_STATUS


bp = Blueprint("proxy", __name__)


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
    try:
        traffic_ifindex = int(raw_cfg.get("traffic_ifindex", 0) or 0)
    except Exception:
        traffic_ifindex = 0
    traffic_source = str(raw_cfg.get("traffic_source") or "auto").strip().lower()
    if traffic_source not in {"auto", "snmp", "server", "none"}:
        traffic_source = "auto"
    return {
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
                "source": str(config_payload.get("traffic_source") or "auto"),
                "device_id": "",
                "host": "",
                "ifindex": 0,
                "ifname": "",
                "updated_at": None,
                "error": "traffic monitor not initialized",
            },
        }
    status["config"] = config_payload
    return jsonify(status)
