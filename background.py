import json
import os
import re
import subprocess
import threading
import time
import struct
import sys
import socket
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from config import CONFIG, DEVICE_STATUS, METER_STATUS, LIGHT_STATUS, LIGHT_ONLINE, ENV_STATUS, SERVER_COMMANDS
import modbus_core as mc
from data_logger import add_log, init_daily_record, update_daily_record, get_daily_record, load_energy_log, _get_cab_data, init_generic_daily_record, update_generic_daily_record, get_generic_daily_record, export_meter_statistics_csv, export_meter_snapshot_csv
from drivers import create_device
from m32r_core import m32r_service
from runtime import automation as runtime_automation
from runtime import state as runtime_state
from runtime.env_history import record_env_lux_sample
from runtime.state import (
    LIGHT_DRIVERS,
    NVR_STATUS,
    PROXY_STATUS,
    PROJECTOR_STATUS,
    SCREEN_STATUS,
    SNMP_STATUS,
    STATUS_SNAPSHOT,
    UPS_STATUS,
)
from paths import resolve_report_dir
from services.home_assistant_bridge import get_env_state as get_ha_env_state
from services.mqtt_env_bridge import get_env_state as get_mqtt_env_state, sync_env_sensor_configs

LIGHT_META = {}

SNMP_MAX_WORKERS = int(os.environ.get("SMART_CENTER_SNMP_MAX_WORKERS", "4"))
SNMP_IDLE_SLEEP_SEC = float(os.environ.get("SMART_CENTER_SNMP_IDLE_SLEEP_SEC", "0.35"))
NVR_MAX_WORKERS = int(os.environ.get("SMART_CENTER_NVR_MAX_WORKERS", "2"))
NVR_IDLE_SLEEP_SEC = float(os.environ.get("SMART_CENTER_NVR_IDLE_SLEEP_SEC", "0.5"))
PROXY_REQUIRED_GOOGLE_URL = "https://www.google.com/generate_204"
PROXY_DEFAULT_CHECK_URLS = (
    PROXY_REQUIRED_GOOGLE_URL,
    "https://www.youtube.com/generate_204",
    "https://chatgpt.com",
    "https://github.com",
)
PROXY_TRAFFIC_EXIT_HOST = "172.16.201.169"
PROXY_TRAFFIC_EXIT_IFNAME = "enp1s0"
PROXY_TRAFFIC_EXIT_SSH_TARGET = "node-121"
PROXY_TRAFFIC_EXIT_LOCAL_USER = "xinping"
PROXY_CLIENT_RATE_CACHE = {}
PROXY_TRAFFIC_NIC_CACHE = {}
PROXY_CLIENT_MONITOR_CACHE = {}
STATE_CHANGE_LOG_CACHE = {}
STATE_CHANGE_VALUE_CACHE = {}


def _status_label(level):
    normalized = str(level or "").strip().lower()
    if normalized == "online":
        return "在线"
    if normalized == "stale":
        return "陈旧"
    if normalized == "error":
        return "异常"
    return "离线"


def _apply_poll_status_level(status):
    payload = dict(status or {})
    level = str(payload.get("status_level") or "").strip().lower()
    if level not in {"online", "stale", "error", "offline"}:
        online = bool(payload.get("online"))
        stale = bool(payload.get("stale"))
        has_error = bool(payload.get("last_error") or payload.get("error"))
        has_history = bool(payload.get("last_success_at") or payload.get("updated_at"))
        if online and stale:
            level = "stale"
        elif online:
            level = "online"
        elif has_error and has_history:
            level = "error"
        elif has_error:
            level = "error"
        else:
            level = "offline"
    payload["status_level"] = level
    payload["status_label"] = _status_label(level)
    return payload


def _build_poll_success(previous_status, fresh_status, now_iso, now_monotonic):
    payload = dict(previous_status or {})
    payload.update(dict(fresh_status or {}))
    payload["updated_at"] = now_iso
    payload["last_checked_at"] = now_iso
    payload["last_success_at"] = now_iso
    payload["last_polled_monotonic"] = now_monotonic
    payload["poll_failures"] = 0
    payload["stale"] = False
    payload["error"] = ""
    payload["last_error"] = ""
    payload["last_error_at"] = None
    payload["status_level"] = "online"
    return _apply_poll_status_level(payload)


def _build_poll_failure(
    previous_status,
    error,
    now_iso,
    now_monotonic,
    interval_sec,
    *,
    defaults=None,
    max_failures=3,
    grace_factor=3.5,
    min_grace_sec=15.0,
):
    payload = dict(defaults or {})
    payload.update(dict(previous_status or {}))
    next_failures = int(payload.get("poll_failures", 0) or 0) + 1
    last_polled = float(payload.get("last_polled_monotonic", 0.0) or 0.0)
    within_grace = bool(
        payload.get("online")
        and last_polled
        and (now_monotonic - last_polled) <= max(min_grace_sec, interval_sec * grace_factor)
        and next_failures < max_failures
    )
    err_text = str(error or "poll failed")
    payload["online"] = within_grace
    had_success = bool(payload.get("updated_at") or payload.get("last_success_at"))
    payload["stale"] = bool(had_success and not within_grace)
    payload["error"] = err_text
    payload["last_error"] = err_text
    payload["last_error_at"] = now_iso
    payload["last_checked_at"] = now_iso
    payload["last_polled_monotonic"] = now_monotonic
    payload["poll_failures"] = next_failures
    if not payload.get("updated_at"):
        payload["updated_at"] = None
    # Keep runtime poll clock fresh even when the device is intermittently unreachable.
    # This prevents immediate re-poll storms that can amplify packet loss.
    payload["last_polled_monotonic"] = now_monotonic
    payload.pop("status_level", None)
    payload.pop("status_label", None)
    return _apply_poll_status_level(payload)


def _poll_interval_sec(cfg, default_ms):
    return max(0.5, float(cfg.get("poll_interval_ms", default_ms) or default_ms) / 1000.0)


def _display_bool_state(value):
    return "开" if bool(value) else "关"


def _channel_label_from_config(cfg, ch_num, fallback_prefix="第"):
    for item in (cfg or {}).get("channels_config", []) or []:
        try:
            if int(item.get("channel", 0) or 0) != int(ch_num):
                continue
        except Exception:
            continue
        name = str(item.get("name") or "").strip()
        remark = str(item.get("remark") or item.get("usage") or item.get("description") or "").strip()
        if name and remark and remark not in name:
            return f"{name}({remark})"
        if name:
            return name
        if remark:
            return remark
    return f"{fallback_prefix}{ch_num}路"


def _changed_channel_text(previous, current, cfg=None):
    if not isinstance(previous, list) or not isinstance(current, list):
        return ""
    if not previous or not current:
        return ""
    pieces = []
    for idx, (old_value, new_value) in enumerate(zip(previous, current), start=1):
        if old_value is None or new_value is None:
            continue
        if bool(old_value) == bool(new_value):
            continue
        label = _channel_label_from_config(cfg or {}, idx)
        pieces.append(f"{label} {_display_bool_state(old_value)}->{_display_bool_state(new_value)}")
    return "、".join(pieces)


def _observed_channel_change_text(cache_key, current, cfg=None):
    if not isinstance(current, list) or not current:
        return ""
    normalized = [None if item is None else bool(item) for item in current]
    previous = STATE_CHANGE_VALUE_CACHE.get(cache_key)
    STATE_CHANGE_VALUE_CACHE[cache_key] = list(normalized)
    if previous is None:
        return ""
    return _changed_channel_text(list(previous), normalized, cfg)


def _record_detected_change(cache_key, message, *, cab_idx=-1, min_interval_sec=1.5):
    text = str(message or "").strip()
    if not text:
        return
    now_ts = time.time()
    previous = STATE_CHANGE_LOG_CACHE.get(cache_key) or {}
    if previous.get("message") == text and (now_ts - float(previous.get("ts", 0.0) or 0.0)) < min_interval_sec:
        return
    STATE_CHANGE_LOG_CACHE[cache_key] = {"message": text, "ts": now_ts}
    add_log(cab_idx, text)


def _record_env_status_sample(device_id):
    state = ENV_STATUS.get(str(device_id), {}) or {}
    record_env_lux_sample(
        device_id,
        state.get("lux"),
        sampled_at=state.get("updated_at"),
        online=state.get("online"),
    )


def _normalize_proxy_exit_traffic_config(cfg):
    payload = dict(cfg or {})
    payload["traffic_enabled"] = bool(payload.get("traffic_enabled", True))
    payload["traffic_source"] = "nic_ssh"
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


def _read_proxy_monitor_config():
    raw_cfg = CONFIG.get("proxy_monitor", {}) or {}
    if not isinstance(raw_cfg, dict):
        raw_cfg = {}

    enabled = bool(raw_cfg.get("enabled", True))
    host = str(raw_cfg.get("host") or "192.168.50.121").strip()
    try:
        port = int(raw_cfg.get("port", 3128) or 3128)
    except Exception:
        port = 3128
    if port <= 0:
        port = 3128

    try:
        timeout_sec = max(1.0, min(float(raw_cfg.get("timeout_sec", 6.0) or 6.0), 30.0))
    except Exception:
        timeout_sec = 6.0

    try:
        poll_interval_sec = max(3.0, min(float(raw_cfg.get("poll_interval_sec", 20.0) or 20.0), 600.0))
    except Exception:
        poll_interval_sec = 20.0
    poll_interval_sec = max(30.0, poll_interval_sec)

    urls = raw_cfg.get("check_urls")
    normalized_urls = []
    if isinstance(urls, list):
        for item in urls:
            url = str(item or "").strip()
            if url:
                normalized_urls.append(url)
    if not normalized_urls:
        normalized_urls = list(PROXY_DEFAULT_CHECK_URLS)
    if not any(_is_proxy_google_check_url(url) for url in normalized_urls):
        normalized_urls.insert(0, PROXY_REQUIRED_GOOGLE_URL)

    traffic_enabled = bool(raw_cfg.get("traffic_enabled", True))
    traffic_source = str(raw_cfg.get("traffic_source") or "auto").strip().lower()
    if traffic_source not in {"auto", "snmp", "server", "nic_ssh", "none"}:
        traffic_source = "auto"
    traffic_device_id = str(raw_cfg.get("traffic_device_id") or "").strip()
    traffic_host = str(raw_cfg.get("traffic_host") or "").strip()
    traffic_ifname = str(raw_cfg.get("traffic_ifname") or "").strip()
    traffic_ssh_target = str(raw_cfg.get("traffic_ssh_target") or raw_cfg.get("client_monitor_ssh_target") or "node-121").strip()
    traffic_local_user = str(raw_cfg.get("traffic_local_user") or raw_cfg.get("client_monitor_local_user") or "xinping").strip()
    try:
        traffic_timeout_sec = max(2.0, min(float(raw_cfg.get("traffic_timeout_sec", raw_cfg.get("client_monitor_timeout_sec", 6.0)) or 6.0), 20.0))
    except Exception:
        traffic_timeout_sec = 6.0
    try:
        traffic_ifindex = max(0, int(raw_cfg.get("traffic_ifindex", 0) or 0))
    except Exception:
        traffic_ifindex = 0
    try:
        client_monitor_recent_seconds = max(30, min(int(raw_cfg.get("client_monitor_recent_seconds", 300) or 300), 3600))
    except Exception:
        client_monitor_recent_seconds = 300
    try:
        client_monitor_tail_lines = max(500, min(int(raw_cfg.get("client_monitor_tail_lines", 8000) or 8000), 50000))
    except Exception:
        client_monitor_tail_lines = 8000
    client_monitor_tail_lines = min(client_monitor_tail_lines, 2000)
    try:
        client_monitor_timeout_sec = max(2.0, min(float(raw_cfg.get("client_monitor_timeout_sec", 6.0) or 6.0), 20.0))
    except Exception:
        client_monitor_timeout_sec = 6.0

    return _normalize_proxy_exit_traffic_config({
        "enabled": enabled,
        "host": host,
        "port": port,
        "timeout_sec": timeout_sec,
        "poll_interval_sec": poll_interval_sec,
        "check_urls": normalized_urls[:4],
        "traffic_enabled": traffic_enabled,
        "traffic_source": traffic_source,
        "traffic_device_id": traffic_device_id,
        "traffic_host": traffic_host,
        "traffic_ifindex": traffic_ifindex,
        "traffic_ifname": traffic_ifname,
        "traffic_ssh_target": traffic_ssh_target,
        "traffic_local_user": traffic_local_user,
        "traffic_timeout_sec": traffic_timeout_sec,
        "client_monitor_enabled": bool(raw_cfg.get("client_monitor_enabled", True)),
        "client_monitor_ssh_target": str(raw_cfg.get("client_monitor_ssh_target") or "node-121").strip(),
        "client_monitor_local_user": str(raw_cfg.get("client_monitor_local_user") or "xinping").strip(),
        "client_monitor_recent_seconds": client_monitor_recent_seconds,
        "client_monitor_tail_lines": client_monitor_tail_lines,
        "client_monitor_timeout_sec": client_monitor_timeout_sec,
    })


def _is_proxy_google_check_url(url):
    try:
        host = urllib.parse.urlparse(str(url or "")).hostname or ""
    except Exception:
        host = ""
    host = host.lower().strip(".")
    return host == "google.com" or host.endswith(".google.com")


def _proxy_check_name(url):
    try:
        host = urllib.parse.urlparse(str(url or "")).hostname or ""
    except Exception:
        host = ""
    host = host.lower().strip(".")
    if host == "google.com" or host.endswith(".google.com"):
        return "Google"
    if host == "youtube.com" or host.endswith(".youtube.com"):
        return "YouTube"
    if host == "chatgpt.com" or host.endswith(".chatgpt.com") or host.endswith(".openai.com"):
        return "ChatGPT"
    if host == "github.com" or host.endswith(".github.com"):
        return "GitHub"
    return host or str(url or "")


def _proxy_probe_tcp(host, port, timeout_sec):
    started = time.monotonic()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout_sec):
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return True, elapsed_ms, ""
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return False, elapsed_ms, str(exc)


def _proxy_probe_http_via_proxy(proxy_url, target_url, timeout_sec):
    started = time.monotonic()
    req = urllib.request.Request(url=str(target_url), method="HEAD", headers={"User-Agent": "smart-power-proxy-monitor/1.0"})
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url}),
        urllib.request.HTTPSHandler(),
        urllib.request.HTTPHandler(),
    )
    try:
        with opener.open(req, timeout=timeout_sec) as resp:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return True, int(getattr(resp, "status", 0) or 0), elapsed_ms, ""
    except urllib.error.HTTPError as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return True, int(getattr(exc, "code", 0) or 0), elapsed_ms, str(exc)
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return False, 0, elapsed_ms, str(exc)


def _is_http_probe_healthy(status_code):
    try:
        code = int(status_code or 0)
    except Exception:
        return False
    return code in {200, 204, 301, 302, 307, 308, 403}


def _set_proxy_status(payload):
    PROXY_STATUS["default"] = dict(payload or {})
    PROXY_STATUS["office_proxy"] = dict(payload or {})


def _format_rate_text(bits_per_sec):
    try:
        mbps = float(bits_per_sec or 0.0) / 1000.0 / 1000.0
    except Exception:
        mbps = 0.0
    if mbps <= 0:
        return "0.000 Mbps"
    if mbps < 1:
        return f"{mbps:.3f} Mbps"
    return f"{mbps:.2f} Mbps"


def _format_bytes_text(byte_count):
    try:
        size = float(byte_count or 0.0)
    except Exception:
        size = 0.0
    if size <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while size >= 1024.0 and idx < len(units) - 1:
        size /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(size)} {units[idx]}"
    return f"{size:.1f} {units[idx]}"


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _candidate_proxy_traffic_sources(cfg):
    source = str(cfg.get("traffic_source") or "auto").strip().lower()
    if source == "none":
        return []
    if source == "snmp":
        return ["snmp"]
    if source == "server":
        return ["server"]
    if source == "nic_ssh":
        return ["nic_ssh"]
    return ["nic_ssh", "snmp", "server"]


def _resolve_proxy_snmp_candidates(cfg):
    target_id = str(cfg.get("traffic_device_id") or "").strip()
    target_host = str(cfg.get("traffic_host") or "").strip()
    proxy_host = str(cfg.get("host") or "").strip()
    devices = list(CONFIG.get("snmp_devices", []) or [])
    ranked = []
    for item in devices:
        if not isinstance(item, dict):
            continue
        if item.get("enabled", True) is False:
            continue
        device_id = str(item.get("id") or "").strip()
        host = str(item.get("host") or item.get("ip") or "").strip()
        if not device_id:
            continue
        rank = 100
        if target_id and device_id == target_id:
            rank = 0
        elif target_host and host and host == target_host:
            rank = 1
        elif proxy_host and host and host == proxy_host:
            rank = 2
        elif target_id or target_host:
            continue
        else:
            rank = 50
        ranked.append((rank, item))
    ranked.sort(key=lambda pair: pair[0])
    return [item for _, item in ranked]


def _pick_interface_row(rows, cfg):
    if not isinstance(rows, list):
        return None
    preferred_ifindex = _safe_int(cfg.get("traffic_ifindex"), 0)
    preferred_ifname = str(cfg.get("traffic_ifname") or "").strip().lower()
    prepared = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        kind = str(row.get("kind") or "").strip().lower()
        in_bps = _safe_float(row.get("in_rate_bps"), 0.0)
        out_bps = _safe_float(row.get("out_rate_bps"), 0.0)
        total_bps = _safe_float(row.get("total_rate_bps"), 0.0)
        if total_bps <= 0:
            total_bps = in_bps + out_bps
        speed_bps = _safe_float(row.get("speed_bps"), 0.0)
        prepared.append(
            {
                "raw": row,
                "index": _safe_int(row.get("index"), 0),
                "name": name,
                "kind": kind,
                "in_bps": max(0.0, in_bps),
                "out_bps": max(0.0, out_bps),
                "total_bps": max(0.0, total_bps),
                "speed_bps": max(0.0, speed_bps),
            }
        )
    if not prepared:
        return None

    if preferred_ifindex > 0:
        for item in prepared:
            if item["index"] == preferred_ifindex:
                return item
    if preferred_ifname:
        for item in prepared:
            if preferred_ifname in item["name"].lower():
                return item

    kind_rank = {"wan": 0, "physical": 1, "bond": 2, "lan": 3, "bridge": 4, "other": 5, "virtual": 6}
    prepared.sort(
        key=lambda item: (
            kind_rank.get(item["kind"], 9),
            -item["total_bps"],
            -item["speed_bps"],
            item["name"],
        )
    )
    return prepared[0]


def _proxy_traffic_from_snmp(cfg, now_iso):
    candidates = _resolve_proxy_snmp_candidates(cfg)
    if not candidates:
        return None, "未匹配到 SNMP 设备"
    for dev in candidates:
        device_id = str(dev.get("id") or "").strip()
        status = dict(SNMP_STATUS.get(device_id, {}) or {})
        summary = dict(status.get("summary", {}) or {})
        interface_rows = list(summary.get("interface_rows", []) or [])
        selected = _pick_interface_row(interface_rows, cfg)
        if not selected:
            continue
        in_bps = selected["in_bps"]
        out_bps = selected["out_bps"]
        return {
            "enabled": True,
            "available": True,
            "rx_bps": round(in_bps, 2),
            "tx_bps": round(out_bps, 2),
            "rx_mbps": round(in_bps / 1000.0 / 1000.0, 3),
            "tx_mbps": round(out_bps / 1000.0 / 1000.0, 3),
            "rx_text": _format_rate_text(in_bps),
            "tx_text": _format_rate_text(out_bps),
            "source": "snmp",
            "device_id": device_id,
            "host": str(dev.get("host") or dev.get("ip") or ""),
            "ifindex": int(selected["index"] or 0),
            "ifname": str(selected["name"] or ""),
            "updated_at": now_iso,
            "error": "",
        }, ""
    return None, "SNMP 已匹配但无接口流量数据"


def _proxy_traffic_from_server(cfg, now_iso):
    target_id = str(cfg.get("traffic_device_id") or "").strip()
    target_host = str(cfg.get("traffic_host") or cfg.get("host") or "").strip()
    rows = _machine_rows()
    chosen = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        mac = str(row.get("mac") or "").strip()
        ip = str(row.get("ip") or "").strip()
        host = str(row.get("hostname") or "").strip()
        if target_id and mac == target_id:
            chosen = row
            break
        if target_host and (ip == target_host or host == target_host):
            chosen = row
            break
    if not chosen:
        return None, "未匹配到服务器监控主机"
    status = dict(chosen.get("status", {}) or {})
    tx_kb_s = _safe_float(status.get("net_sent_kb_s"), 0.0)
    rx_kb_s = _safe_float(status.get("net_recv_kb_s"), 0.0)
    tx_bps = max(0.0, tx_kb_s * 1024.0 * 8.0)
    rx_bps = max(0.0, rx_kb_s * 1024.0 * 8.0)
    return {
        "enabled": True,
        "available": True,
        "rx_bps": round(rx_bps, 2),
        "tx_bps": round(tx_bps, 2),
        "rx_mbps": round(rx_bps / 1000.0 / 1000.0, 3),
        "tx_mbps": round(tx_bps / 1000.0 / 1000.0, 3),
        "rx_text": _format_rate_text(rx_bps),
        "tx_text": _format_rate_text(tx_bps),
        "source": "server",
        "device_id": str(chosen.get("mac") or ""),
        "host": str(chosen.get("ip") or ""),
        "ifindex": 0,
        "ifname": "aggregate",
        "updated_at": now_iso,
        "error": "",
    }, ""


def _proxy_traffic_from_ssh_nic(cfg, now_iso):
    ssh_target = str(cfg.get("traffic_ssh_target") or cfg.get("client_monitor_ssh_target") or "").strip()
    if not ssh_target:
        return None, "missing traffic ssh target"
    ifname = str(cfg.get("traffic_ifname") or "enp1s0").strip() or "enp1s0"
    local_user = str(cfg.get("traffic_local_user") or cfg.get("client_monitor_local_user") or "").strip()
    timeout_sec = float(cfg.get("traffic_timeout_sec") or cfg.get("client_monitor_timeout_sec") or 6.0)
    remote_cmd = (
        f"test -d /sys/class/net/{ifname} || exit 4; "
        f"printf 'ifname=%s\\n' {ifname}; "
        f"printf 'rx=%s\\n' $(cat /sys/class/net/{ifname}/statistics/rx_bytes 2>/dev/null); "
        f"printf 'tx=%s\\n' $(cat /sys/class/net/{ifname}/statistics/tx_bytes 2>/dev/null); "
        f"printf 'state=%s\\n' $(cat /sys/class/net/{ifname}/operstate 2>/dev/null); "
        f"ip -4 -br addr show dev {ifname} 2>/dev/null | awk '{{print \"addr=\"$3}}'"
    )
    connect_timeout = max(4, min(int(timeout_sec) - 1, 12))
    ssh_cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={connect_timeout}",
        "-o",
        "ConnectionAttempts=2",
        ssh_target,
        remote_cmd,
    ]
    if local_user:
        ssh_cmd = ["sudo", "-n", "-u", local_user] + ssh_cmd
    try:
        proc = subprocess.run(ssh_cmd, text=True, capture_output=True, timeout=timeout_sec)
    except Exception as exc:
        return None, str(exc)
    if proc.returncode != 0:
        return None, (proc.stderr or f"ssh exited {proc.returncode}").strip()
    values = {}
    for line in (proc.stdout or "").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    rx_bytes = _safe_int(values.get("rx"), -1)
    tx_bytes = _safe_int(values.get("tx"), -1)
    if rx_bytes < 0 or tx_bytes < 0:
        return None, "invalid nic traffic counters"
    now_mono = time.monotonic()
    cache_key = f"{ssh_target}:{ifname}"
    prev = PROXY_TRAFFIC_NIC_CACHE.get(cache_key)
    rx_bps = 0.0
    tx_bps = 0.0
    if prev:
        delta_sec = max(0.5, now_mono - float(prev.get("ts") or now_mono))
        rx_delta = rx_bytes - int(prev.get("rx") or 0)
        tx_delta = tx_bytes - int(prev.get("tx") or 0)
        if rx_delta >= 0:
            rx_bps = rx_delta * 8.0 / delta_sec
        if tx_delta >= 0:
            tx_bps = tx_delta * 8.0 / delta_sec
    PROXY_TRAFFIC_NIC_CACHE[cache_key] = {"ts": now_mono, "rx": rx_bytes, "tx": tx_bytes}
    return {
        "enabled": True,
        "available": True,
        "rx_bps": round(max(0.0, rx_bps), 2),
        "tx_bps": round(max(0.0, tx_bps), 2),
        "rx_mbps": round(max(0.0, rx_bps) / 1000.0 / 1000.0, 3),
        "tx_mbps": round(max(0.0, tx_bps) / 1000.0 / 1000.0, 3),
        "rx_text": _format_rate_text(rx_bps),
        "tx_text": _format_rate_text(tx_bps),
        "source": "nic_ssh",
        "device_id": ssh_target,
        "host": str(values.get("addr") or ""),
        "ifindex": 0,
        "ifname": ifname,
        "operstate": str(values.get("state") or ""),
        "rx_bytes": rx_bytes,
        "tx_bytes": tx_bytes,
        "updated_at": now_iso,
        "error": "",
    }, ""


def _build_proxy_traffic_payload(cfg, previous_status, now_iso):
    if not bool(cfg.get("traffic_enabled", True)):
        return {
            "enabled": False,
            "available": False,
            "rx_bps": 0.0,
            "tx_bps": 0.0,
            "rx_mbps": 0.0,
            "tx_mbps": 0.0,
            "rx_text": "--",
            "tx_text": "--",
            "source": str(cfg.get("traffic_source") or "none"),
            "device_id": "",
            "host": "",
            "ifindex": 0,
            "ifname": "",
            "updated_at": now_iso,
            "error": "traffic monitor disabled",
        }

    last = dict((previous_status or {}).get("traffic", {}) or {})
    errors = []
    for source in _candidate_proxy_traffic_sources(cfg):
        if source == "snmp":
            payload, err = _proxy_traffic_from_snmp(cfg, now_iso)
        elif source == "server":
            payload, err = _proxy_traffic_from_server(cfg, now_iso)
        elif source == "nic_ssh":
            payload, err = _proxy_traffic_from_ssh_nic(cfg, now_iso)
        else:
            payload, err = None, "unsupported traffic source"
        if payload and payload.get("available"):
            return payload
        if err:
            errors.append(str(err))

    return {
        "enabled": True,
        "available": False,
        "rx_bps": 0.0,
        "tx_bps": 0.0,
        "rx_mbps": 0.0,
        "tx_mbps": 0.0,
        "rx_text": "--",
        "tx_text": "--",
        "source": str(cfg.get("traffic_source") or "auto"),
        "device_id": str(last.get("device_id") or ""),
        "host": str(last.get("host") or ""),
        "ifindex": _safe_int(last.get("ifindex"), 0),
        "ifname": str(last.get("ifname") or ""),
        "updated_at": now_iso,
        "error": "；".join(errors[:2]) if errors else "暂无流量数据",
    }


def _clean_proxy_client_ip(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("[") and "]:" in text:
        text = text[1:text.rfind("]:")]
    elif ":" in text:
        text = text.rsplit(":", 1)[0]
    if text.startswith("::ffff:"):
        text = text[7:]
    text = text.strip("[]")
    if text in {"127.0.0.1", "::1", "localhost"}:
        return ""
    return text


def _parse_proxy_ss_clients(text, now_mono):
    clients = {}
    current_ip = ""
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(("ESTAB", "FIN-WAIT", "CLOSE-WAIT", "SYN-")):
            parts = line.split()
            peer = parts[4] if len(parts) >= 5 else ""
            current_ip = _clean_proxy_client_ip(peer)
            if not current_ip:
                continue
            item = clients.setdefault(
                current_ip,
                {
                    "ip": current_ip,
                    "active_connections": 0,
                    "tcp_sent_bytes": 0,
                    "tcp_received_bytes": 0,
                    "tx_bps": 0.0,
                    "rx_bps": 0.0,
                    "last_active_monotonic": now_mono,
                },
            )
            item["active_connections"] += 1
            item["last_active_monotonic"] = now_mono
            continue
        if not current_ip:
            continue
        item = clients.setdefault(current_ip, {"ip": current_ip, "active_connections": 0, "tcp_sent_bytes": 0, "tcp_received_bytes": 0, "tx_bps": 0.0, "rx_bps": 0.0, "last_active_monotonic": now_mono})
        sent_match = re.search(r"bytes_sent:(\d+)", line)
        recv_match = re.search(r"bytes_received:(\d+)", line)
        if sent_match:
            item["tcp_sent_bytes"] += int(sent_match.group(1))
        if recv_match:
            item["tcp_received_bytes"] += int(recv_match.group(1))

    for ip, item in clients.items():
        totals = (int(item.get("tcp_sent_bytes") or 0), int(item.get("tcp_received_bytes") or 0))
        prev = PROXY_CLIENT_RATE_CACHE.get(ip)
        if prev:
            delta_sec = max(0.5, now_mono - float(prev.get("ts") or now_mono))
            sent_delta = max(0, totals[0] - int(prev.get("sent") or 0))
            recv_delta = max(0, totals[1] - int(prev.get("recv") or 0))
            item["tx_bps"] = round(sent_delta * 8.0 / delta_sec, 2)
            item["rx_bps"] = round(recv_delta * 8.0 / delta_sec, 2)
        PROXY_CLIENT_RATE_CACHE[ip] = {"ts": now_mono, "sent": totals[0], "recv": totals[1]}
    stale_before = now_mono - 900.0
    for ip, prev in list(PROXY_CLIENT_RATE_CACHE.items()):
        if float(prev.get("ts") or 0) < stale_before:
            PROXY_CLIENT_RATE_CACHE.pop(ip, None)
    return clients


def _parse_proxy_access_clients(text, now_epoch, recent_seconds):
    clients = {}
    cutoff = float(now_epoch) - float(recent_seconds)
    for raw_line in str(text or "").splitlines():
        parts = raw_line.split()
        if len(parts) < 5:
            continue
        try:
            ts = float(parts[0])
        except Exception:
            continue
        if ts < cutoff:
            continue
        ip = _clean_proxy_client_ip(parts[2])
        if not ip:
            continue
        try:
            bytes_out = int(parts[4])
        except Exception:
            bytes_out = 0
        item = clients.setdefault(ip, {"ip": ip, "recent_requests": 0, "recent_bytes": 0, "last_seen_epoch": ts})
        item["recent_requests"] += 1
        item["recent_bytes"] += max(0, bytes_out)
        item["last_seen_epoch"] = max(float(item.get("last_seen_epoch") or 0), ts)
    return clients


def _run_proxy_client_monitor_command(cfg):
    ssh_target = str(cfg.get("client_monitor_ssh_target") or "").strip()
    if not ssh_target:
        return "", "missing ssh target"
    local_user = str(cfg.get("client_monitor_local_user") or "").strip()
    timeout_sec = float(cfg.get("client_monitor_timeout_sec") or 6.0)
    tail_lines = int(cfg.get("client_monitor_tail_lines") or 8000)
    remote_cmd = (
        "printf '__SS__\\n'; "
        "ss -Htin sport = :3128 2>/dev/null || true; "
        "printf '\\n__ACCESS__\\n'; "
        f"sudo -n tail -n {tail_lines} /var/log/squid/access.log 2>/dev/null || true"
    )
    ssh_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=4", ssh_target, remote_cmd]
    if local_user:
        ssh_cmd = ["sudo", "-n", "-u", local_user] + ssh_cmd
    try:
        proc = subprocess.run(ssh_cmd, text=True, capture_output=True, timeout=timeout_sec)
    except Exception as exc:
        return "", str(exc)
    if proc.returncode != 0:
        return proc.stdout or "", (proc.stderr or f"ssh exited {proc.returncode}").strip()
    return proc.stdout or "", ""


def _build_proxy_clients_payload(cfg, now_iso):
    if not bool(cfg.get("client_monitor_enabled", True)):
        return {
            "enabled": False,
            "available": False,
            "source": "disabled",
            "active_client_count": 0,
            "total_active_connections": 0,
            "recent_client_count": 0,
            "recent_seconds": int(cfg.get("client_monitor_recent_seconds") or 300),
            "clients": [],
            "updated_at": now_iso,
            "error": "client monitor disabled",
        }
    cache_key = "{}:{}:{}".format(
        str(cfg.get("client_monitor_ssh_target") or "").strip(),
        int(cfg.get("client_monitor_recent_seconds") or 300),
        int(cfg.get("client_monitor_tail_lines") or 8000),
    )
    now_mono_for_cache = time.monotonic()
    cache_ttl = max(10.0, min(float(cfg.get("poll_interval_sec") or 30.0) * 0.75, 30.0))
    cached_payload = PROXY_CLIENT_MONITOR_CACHE.get(cache_key)
    if cached_payload and now_mono_for_cache - float(cached_payload.get("monotonic") or 0.0) < cache_ttl:
        payload = dict(cached_payload.get("payload") or {})
        payload["cached"] = True
        payload["updated_at"] = payload.get("updated_at") or now_iso
        return payload
    output, error = _run_proxy_client_monitor_command(cfg)
    if error and not output:
        payload = {
            "enabled": True,
            "available": False,
            "source": "ssh-ss-squid",
            "active_client_count": 0,
            "total_active_connections": 0,
            "recent_client_count": 0,
            "recent_seconds": int(cfg.get("client_monitor_recent_seconds") or 300),
            "clients": [],
            "updated_at": now_iso,
            "error": error,
        }
        PROXY_CLIENT_MONITOR_CACHE[cache_key] = {"monotonic": now_mono_for_cache, "payload": dict(payload)}
        return payload
    ss_text = ""
    access_text = ""
    if "__ACCESS__" in output:
        before_access, access_text = output.split("__ACCESS__", 1)
        ss_text = before_access.split("__SS__", 1)[-1] if "__SS__" in before_access else before_access
    else:
        ss_text = output.split("__SS__", 1)[-1] if "__SS__" in output else output
    now_mono = time.monotonic()
    now_epoch = time.time()
    recent_seconds = int(cfg.get("client_monitor_recent_seconds") or 300)
    active_map = _parse_proxy_ss_clients(ss_text, now_mono)
    recent_map = _parse_proxy_access_clients(access_text, now_epoch, recent_seconds)
    ip_set = set(active_map) | set(recent_map)
    clients = []
    for ip in sorted(ip_set):
        active = active_map.get(ip, {})
        recent = recent_map.get(ip, {})
        tx_bps = _safe_float(active.get("tx_bps"), 0.0)
        rx_bps = _safe_float(active.get("rx_bps"), 0.0)
        recent_bytes = int(recent.get("recent_bytes") or 0)
        last_seen_epoch = float(recent.get("last_seen_epoch") or 0.0)
        clients.append(
            {
                "ip": ip,
                "active": int(active.get("active_connections") or 0) > 0,
                "active_connections": int(active.get("active_connections") or 0),
                "tx_bps": round(tx_bps, 2),
                "rx_bps": round(rx_bps, 2),
                "tx_text": _format_rate_text(tx_bps),
                "rx_text": _format_rate_text(rx_bps),
                "recent_requests": int(recent.get("recent_requests") or 0),
                "recent_bytes": recent_bytes,
                "recent_bytes_text": _format_bytes_text(recent_bytes),
                "last_seen_at": datetime.fromtimestamp(last_seen_epoch).isoformat() if last_seen_epoch > 0 else None,
            }
        )
    clients.sort(key=lambda item: (not item.get("active"), -int(item.get("active_connections") or 0), -int(item.get("recent_bytes") or 0), item.get("ip") or ""))
    total_download_bps = sum(_safe_float(item.get("tx_bps"), 0.0) for item in clients)
    total_upload_bps = sum(_safe_float(item.get("rx_bps"), 0.0) for item in clients)
    payload = {
        "enabled": True,
        "available": True,
        "source": "ssh-ss-squid",
        "active_client_count": sum(1 for item in clients if item.get("active")),
        "total_active_connections": sum(int(item.get("active_connections") or 0) for item in clients),
        "recent_client_count": len([item for item in clients if int(item.get("recent_requests") or 0) > 0]),
        "recent_seconds": recent_seconds,
        "download_bps": round(total_download_bps, 2),
        "upload_bps": round(total_upload_bps, 2),
        "download_text": _format_rate_text(total_download_bps),
        "upload_text": _format_rate_text(total_upload_bps),
        "clients": clients[:80],
        "updated_at": now_iso,
        "error": error or "",
    }
    PROXY_CLIENT_MONITOR_CACHE[cache_key] = {"monotonic": now_mono_for_cache, "payload": dict(payload)}
    return payload


def proxy_update_loop():
    while True:
        cfg = _read_proxy_monitor_config()
        now_iso = datetime.now().isoformat()
        now_mono = time.monotonic()
        previous_status = dict(PROXY_STATUS.get("default", {}) or {})
        traffic_payload = _build_proxy_traffic_payload(cfg, previous_status, now_iso)
        clients_payload = _build_proxy_clients_payload(cfg, now_iso)

        if not cfg.get("enabled", True):
            _set_proxy_status(
                {
                    "id": "office_proxy",
                    "name": "office_proxy",
                    "host": cfg.get("host"),
                    "port": int(cfg.get("port", 0) or 0),
                    "enabled": False,
                    "online": False,
                    "stale": False,
                    "status_level": "offline",
                    "status_label": "离线",
                    "error": "proxy monitor disabled",
                    "last_error": "proxy monitor disabled",
                    "updated_at": now_iso,
                    "last_checked_at": now_iso,
                    "last_success_at": None,
                    "poll_failures": 0,
                    "healthy_target_count": 0,
                    "check_count": 0,
                    "checks": [],
                    "traffic": traffic_payload,
                    "clients": clients_payload,
                }
            )
            time.sleep(max(3.0, float(cfg.get("poll_interval_sec", 20.0) or 20.0)))
            continue

        host = str(cfg.get("host") or "").strip()
        port = int(cfg.get("port", 0) or 0)
        timeout_sec = float(cfg.get("timeout_sec", 6.0) or 6.0)
        poll_interval_sec = float(cfg.get("poll_interval_sec", 20.0) or 20.0)
        check_urls = list(cfg.get("check_urls") or PROXY_DEFAULT_CHECK_URLS)
        if not host or port <= 0:
            failure = _build_poll_failure(
                previous_status,
                "invalid proxy host/port",
                now_iso,
                now_mono,
                poll_interval_sec,
                defaults={
                    "id": "office_proxy",
                    "name": "office_proxy",
                    "host": host,
                    "port": port,
                    "enabled": True,
                    "checks": [],
                    "healthy_target_count": 0,
                    "check_count": 0,
                    "traffic": traffic_payload,
                    "clients": clients_payload,
                },
            )
            _set_proxy_status(failure)
            time.sleep(poll_interval_sec)
            continue

        tcp_ok, tcp_latency_ms, tcp_error = _proxy_probe_tcp(host, port, timeout_sec)
        proxy_url = f"http://{host}:{port}"
        checks = []
        healthy_targets = 0
        google_check = None
        for url in check_urls:
            ok, status_code, latency_ms, error_text = _proxy_probe_http_via_proxy(proxy_url, url, timeout_sec)
            is_healthy = bool(ok and _is_http_probe_healthy(status_code))
            if is_healthy:
                healthy_targets += 1
            check_item = {
                "url": url,
                "ok": bool(ok),
                "healthy": is_healthy,
                "required": bool(_is_proxy_google_check_url(url)),
                "name": _proxy_check_name(url),
                "status_code": int(status_code or 0),
                "latency_ms": int(latency_ms or 0),
                "error": str(error_text or ""),
            }
            checks.append(check_item)
            if check_item["required"] and google_check is None:
                google_check = check_item

        google_ok = bool(google_check and google_check.get("healthy"))
        overall_ok = bool(tcp_ok and checks and google_ok)
        if overall_ok:
            success_payload = _build_poll_success(
                previous_status,
                {
                    "id": "office_proxy",
                    "name": "office_proxy",
                    "host": host,
                    "port": port,
                    "enabled": True,
                    "online": True,
                    "tcp_ok": bool(tcp_ok),
                    "tcp_latency_ms": int(tcp_latency_ms or 0),
                    "healthy_target_count": int(healthy_targets),
                    "check_count": int(len(checks)),
                    "required_check": google_check or {},
                    "google_ok": True,
                    "google_latency_ms": int((google_check or {}).get("latency_ms") or 0),
                    "google_status_code": int((google_check or {}).get("status_code") or 0),
                    "checks": checks,
                    "traffic": traffic_payload,
                    "clients": clients_payload,
                },
                now_iso,
                now_mono,
            )
            _set_proxy_status(success_payload)
        else:
            if tcp_error:
                combined_error = tcp_error
            elif google_check and not google_check.get("healthy"):
                combined_error = google_check.get("error") or f"Google check failed ({google_check.get('status_code') or 0})"
            elif not google_check:
                combined_error = "Google check missing"
            else:
                combined_error = next((item.get("error") for item in checks if not item.get("healthy")), "proxy check failed")
            failure_payload = _build_poll_failure(
                previous_status,
                combined_error,
                now_iso,
                now_mono,
                poll_interval_sec,
                defaults={
                    "id": "office_proxy",
                    "name": "office_proxy",
                    "host": host,
                    "port": port,
                    "enabled": True,
                    "tcp_ok": bool(tcp_ok),
                    "tcp_latency_ms": int(tcp_latency_ms or 0),
                    "healthy_target_count": int(healthy_targets),
                    "check_count": int(len(checks)),
                    "required_check": google_check or {},
                    "google_ok": False,
                    "google_latency_ms": int((google_check or {}).get("latency_ms") or 0),
                    "google_status_code": int((google_check or {}).get("status_code") or 0),
                    "checks": checks,
                    "traffic": traffic_payload,
                    "clients": clients_payload,
                },
            )
            _set_proxy_status(failure_payload)
            prev_level = str(previous_status.get("status_level") or "").strip().lower()
            next_level = str(failure_payload.get("status_level") or "").strip().lower()
            if prev_level != next_level or next_level in {"error", "offline"}:
                add_log(-1, f"[proxy-monitor] abnormal status: {host}:{port} -> {next_level} ({combined_error})")

        time.sleep(poll_interval_sec)


def m32r_update_loop():
    auto_connected = False
    while True:
        try:
            cfg = CONFIG.get("m32r", {}) or {}
            if cfg.get("auto_connect") and cfg.get("host") and not auto_connected:
                try:
                    m32r_service.connect()
                    auto_connected = True
                except Exception:
                    pass
            if not cfg.get("auto_connect"):
                auto_connected = False
            m32r_service.configure(cfg)
            m32r_service.tick()
            sleep_ms = max(300, int(cfg.get("poll_interval_ms", 1200) or 1200))
            time.sleep(sleep_ms / 1000.0)
        except Exception:
            time.sleep(1.0)


def sequencer_update_loop():
    from api.sequencer import ensure_config_devices, get_or_init_status, poll_sequencer_once
    while True:
        devices = list(ensure_config_devices())
        due_devices = []
        now = time.monotonic()
        for dev in devices:
            state = get_or_init_status(dev)
            interval_ms = max(300, int(dev.get("poll_interval_ms", 1200) or 1200))
            last_polled = float(state.get("last_polled_monotonic", 0.0) or 0.0)
            if (now - last_polled) * 1000 >= interval_ms:
                due_devices.append(dev)
        if due_devices:
            for dev in due_devices:
                try:
                    poll_sequencer_once(dev)
                except Exception:
                    pass
        time.sleep(0.2)


def init_light_drivers():
    global LIGHT_DRIVERS
    for drv in LIGHT_DRIVERS.values():
        try:
            drv.disconnect()
        except Exception:
            pass
    LIGHT_DRIVERS.clear()
    LIGHT_STATUS.clear()
    LIGHT_ONLINE.clear()
    LIGHT_META.clear()

    for cfg in CONFIG.get("light_devices", []):
        cfg["type"] = "light"
        dev_id = cfg["id"]
        try:
            LIGHT_DRIVERS[dev_id] = create_device(cfg)
            LIGHT_STATUS[dev_id] = [None] * cfg.get("channels", 8)
            LIGHT_ONLINE[dev_id] = False
            LIGHT_META[dev_id] = _apply_poll_status_level(
                {
                    "online": False,
                    "stale": False,
                    "poll_failures": 0,
                    "status_text": "offline",
                    "device_status_text": "offline",
                    "channel_state_known": False,
                    "inputs": [None] * int(cfg.get("input_count", 0) or 0),
                }
            )
        except Exception as e:
            add_log(-1, f"[灯光] 驱动加载失败: {str(e)}")


def poll_single_light(dev_id, light_cfg=None):
    cfg = light_cfg or next((item for item in CONFIG.get("light_devices", []) if item.get("id") == dev_id), {}) or {}
    interval_sec = _poll_interval_sec(cfg, 1000)
    now_iso = datetime.now().isoformat()
    now_monotonic = time.monotonic()
    previous_meta = dict(LIGHT_META.get(dev_id, {}) or {})
    drv = LIGHT_DRIVERS.get(dev_id)
    if not drv:
        fallback = _build_poll_failure(
            previous_meta,
            "light driver unavailable",
            now_iso,
            now_monotonic,
            interval_sec,
            defaults={
                "status_text": "offline",
                "device_status_text": "offline",
                "channel_state_known": False,
            },
        )
        LIGHT_META[dev_id] = fallback
        LIGHT_ONLINE[dev_id] = bool(fallback.get("online"))
        return
    try:
        res = dict(drv.read_status() or {})
        channels = list(res.get("channels", []) or [])
        inputs = list(res.get("inputs", []) or [])
        device_status_text = str(res.get("status_text", "unknown") or "unknown")
        if res.get("online"):
            LIGHT_STATUS[dev_id] = channels
            changed_text = _observed_channel_change_text(f"light:{dev_id}:channels:observed", channels, cfg)
            if changed_text:
                device_name = str(cfg.get("name") or cfg.get("id") or dev_id)
                message = f"[状态变化][灯光] {device_name} {changed_text}（轮询识别）"
                _record_detected_change(f"light:{dev_id}:channels", message)
                try:
                    record_state_change(
                        category="light",
                        device_id=str(dev_id),
                        device_name=device_name,
                        message=message,
                        source="poller",
                        changes=[{"text": changed_text}],
                        raw={"channels": channels, "inputs": inputs},
                    )
                except Exception:
                    pass
            input_changed_text = _observed_channel_change_text(f"light:{dev_id}:inputs:observed", inputs, {"channels_config": cfg.get("input_channels_config", [])})
            if input_changed_text:
                device_name = str(cfg.get("name") or cfg.get("id") or dev_id)
                message = f"[状态变化][输入] {device_name} {input_changed_text}（轮询识别）"
                _record_detected_change(f"light:{dev_id}:inputs", message)
                try:
                    record_state_change(
                        category="input",
                        device_id=str(dev_id),
                        device_name=device_name,
                        message=message,
                        source="poller",
                        changes=[{"text": input_changed_text}],
                        raw={"inputs": inputs},
                    )
                except Exception:
                    pass
            next_meta = _build_poll_success(
                previous_meta,
                {
                    "online": True,
                    "status_text": device_status_text,
                    "device_status_text": device_status_text,
                    "channel_state_known": any(ch is not None for ch in channels),
                    "inputs": inputs,
                    "input_state_known": any(item is not None for item in inputs),
                    "raw_status": res.get("raw_status", {}),
                },
                now_iso,
                now_monotonic,
            )
        else:
            next_meta = _build_poll_failure(
                previous_meta,
                res.get("error") or f"light offline ({device_status_text})",
                now_iso,
                now_monotonic,
                interval_sec,
                defaults={
                    "status_text": device_status_text,
                    "device_status_text": device_status_text,
                    "channel_state_known": any(ch is not None for ch in channels),
                    "inputs": inputs,
                    "input_state_known": any(item is not None for item in inputs),
                    "raw_status": res.get("raw_status", {}),
                },
            )
        LIGHT_META[dev_id] = next_meta
        LIGHT_ONLINE[dev_id] = bool(next_meta.get("online"))
    except Exception as e:
        fallback = _build_poll_failure(
            previous_meta,
            e,
            now_iso,
            now_monotonic,
            interval_sec,
            defaults={
                "status_text": "offline",
                "device_status_text": "offline",
                "channel_state_known": False,
            },
        )
        LIGHT_META[dev_id] = fallback
        LIGHT_ONLINE[dev_id] = bool(fallback.get("online"))


def light_update_loop():
    while True:
        light_configs = list(CONFIG.get("light_devices", []))
        active_ids = {cfg.get("id") for cfg in light_configs}
        for dev_id in list(LIGHT_META.keys()):
            if dev_id not in active_ids:
                LIGHT_META.pop(dev_id, None)
                LIGHT_ONLINE.pop(dev_id, None)
                LIGHT_STATUS.pop(dev_id, None)
        due_devices = []
        now = time.monotonic()
        for cfg in light_configs:
            dev_id = cfg.get("id")
            state = LIGHT_META.get(dev_id, {}) or {}
            interval_ms = max(500, int(cfg.get("poll_interval_ms", 1000) or 1000))
            last_polled = float(state.get("last_polled_monotonic", 0.0) or 0.0)
            if (now - last_polled) * 1000 >= interval_ms:
                due_devices.append((dev_id, cfg))
        for dev_id, cfg in due_devices:
            try:
                poll_single_light(dev_id, cfg)
            except Exception:
                pass
        time.sleep(0.2)


def poll_single_projector(proj_cfg):
    proj_id = str(proj_cfg.get("id"))
    now_iso = datetime.now().isoformat()
    now_monotonic = time.monotonic()
    interval_sec = _poll_interval_sec(proj_cfg, 5000)
    previous_status = dict(PROJECTOR_STATUS.get(proj_id, {}) or {})
    try:
        from projector_core import ProjectorDriver
        status = dict(ProjectorDriver(proj_cfg).get_status() or {})
        if str(proj_cfg.get("control_type") or "") == "inferred_rs232":
            merged = dict(previous_status or {})
            merged.update(status)
            merged["updated_at"] = now_iso
            merged["last_checked_at"] = now_iso
            if status.get("online"):
                merged["last_success_at"] = now_iso
                merged["poll_failures"] = 0
                merged["stale"] = False
            else:
                merged["poll_failures"] = int(merged.get("poll_failures", 0) or 0) + 1
            merged["last_polled_monotonic"] = now_monotonic
            merged["last_error"] = "" if status.get("error") in [None, "", "正常"] else str(status.get("error"))
            merged["last_error_at"] = None if not merged["last_error"] else now_iso
            merged["status_level"] = status.get("status_level") or ("online" if status.get("online") else "error")
            PROJECTOR_STATUS[proj_id] = _apply_poll_status_level(merged)
        elif status.get("online"):
            PROJECTOR_STATUS[proj_id] = _build_poll_success(previous_status, status, now_iso, now_monotonic)
        else:
            PROJECTOR_STATUS[proj_id] = _build_poll_failure(
                previous_status,
                status.get("error") or "projector offline",
                now_iso,
                now_monotonic,
                interval_sec,
                defaults={"power": "unknown"},
            )
    except Exception as e:
        PROJECTOR_STATUS[proj_id] = _build_poll_failure(
            previous_status,
            e,
            now_iso,
            now_monotonic,
            interval_sec,
            defaults={"power": "unknown"},
        )


def projector_update_loop():
    while True:
        projectors = list(CONFIG.get("projectors", []))
        active_ids = {str(item.get("id")) for item in projectors}
        for proj_id in list(PROJECTOR_STATUS.keys()):
            if proj_id not in active_ids:
                PROJECTOR_STATUS.pop(proj_id, None)
        due_projectors = []
        now = time.monotonic()
        for proj in projectors:
            proj_id = str(proj.get("id"))
            state = PROJECTOR_STATUS.get(proj_id, {}) or {}
            interval_ms = max(1000, int(proj.get("poll_interval_ms", 5000) or 5000))
            last_polled = float(state.get("last_polled_monotonic", 0.0) or 0.0)
            if (now - last_polled) * 1000 >= interval_ms:
                due_projectors.append(proj)
        for proj in due_projectors:
            try:
                poll_single_projector(proj)
            except Exception:
                pass
        time.sleep(0.5)


def hvac_update_loop():
    while True:
        try:
            from api.hvac import refresh_hvac_status
            refresh_hvac_status()
        except Exception:
            pass
        time.sleep(5)


def poll_single_screen(screen_cfg):
    screen_id = str(screen_cfg.get("id"))
    now_iso = datetime.now().isoformat()
    now_monotonic = time.monotonic()
    interval_sec = _poll_interval_sec(screen_cfg, 1000)
    previous_status = dict(SCREEN_STATUS.get(screen_id, {}) or {})
    try:
        from screen_core import ScreenDriver
        status = dict(ScreenDriver(screen_cfg).get_status() or {})
        status["online"] = True
        SCREEN_STATUS[screen_id] = _build_poll_success(previous_status, status, now_iso, now_monotonic)
    except Exception as e:
        SCREEN_STATUS[screen_id] = _build_poll_failure(
            previous_status,
            e,
            now_iso,
            now_monotonic,
            interval_sec,
            defaults={
                "position": None,
                "height": None,
                "action": "unknown",
                "is_moving": False,
            },
        )


def screen_update_loop():
    while True:
        screens = list(CONFIG.get("screens", []))
        active_ids = {str(item.get("id")) for item in screens}
        for screen_id in list(SCREEN_STATUS.keys()):
            if screen_id not in active_ids:
                SCREEN_STATUS.pop(screen_id, None)
        due_screens = []
        now = time.monotonic()
        for screen_cfg in screens:
            screen_id = str(screen_cfg.get("id"))
            state = SCREEN_STATUS.get(screen_id, {}) or {}
            interval_ms = max(500, int(screen_cfg.get("poll_interval_ms", 1000) or 1000))
            last_polled = float(state.get("last_polled_monotonic", 0.0) or 0.0)
            if (now - last_polled) * 1000 >= interval_ms:
                due_screens.append(screen_cfg)
        for screen_cfg in due_screens:
            try:
                poll_single_screen(screen_cfg)
            except Exception:
                pass
        time.sleep(0.2)


def poll_single_ups(ups_cfg):
    ups_id = str(ups_cfg.get("id"))
    now_iso = datetime.now().isoformat()
    now_monotonic = time.monotonic()
    interval_sec = _poll_interval_sec(ups_cfg, 3000)
    previous_status = dict(UPS_STATUS.get(ups_id, {}) or {})
    try:
        from ups_core import UpsDriver
        status = dict(UpsDriver(ups_cfg).get_status() or {})
        UPS_STATUS[ups_id] = _build_poll_success(previous_status, status, now_iso, now_monotonic)
    except Exception as e:
        UPS_STATUS[ups_id] = _build_poll_failure(previous_status, e, now_iso, now_monotonic, interval_sec)


def ups_update_loop():
    while True:
        devices = list(CONFIG.get("ups_devices", []))
        active_ids = {str(item.get("id")) for item in devices}
        for ups_id in list(UPS_STATUS.keys()):
            if ups_id not in active_ids:
                UPS_STATUS.pop(ups_id, None)
        due_devices = []
        now = time.monotonic()
        for cfg in devices:
            if not cfg.get("visible", True):
                continue
            ups_id = str(cfg.get("id"))
            state = UPS_STATUS.get(ups_id, {}) or {}
            interval_ms = max(500, int(cfg.get("poll_interval_ms", 3000) or 3000))
            last_polled = float(state.get("last_polled_monotonic", 0.0) or 0.0)
            if (now - last_polled) * 1000 >= interval_ms:
                due_devices.append(cfg)
        if due_devices:
            for cfg in due_devices:
                try:
                    poll_single_ups(cfg)
                except Exception:
                    pass
        time.sleep(0.3)


def poll_single_snmp(snmp_cfg):
    device_id = str(snmp_cfg.get("id"))
    previous_status = dict(SNMP_STATUS.get(device_id, {}) or {})
    interval_sec = _poll_interval_sec(snmp_cfg, 5000)
    try:
        from snmp_core import poll_snmp_device

        status = dict(poll_snmp_device(snmp_cfg, previous_status=previous_status) or {})
        now_monotonic = time.monotonic()
        now_iso = datetime.now().isoformat()
        if bool(status.get("online")):
            SNMP_STATUS[device_id] = _build_poll_success(previous_status, status, now_iso, now_monotonic)
        else:
            SNMP_STATUS[device_id] = _build_poll_failure(
                previous_status,
                status.get("error") or "SNMP poll returned offline",
                now_iso,
                now_monotonic,
                interval_sec,
                defaults={
                    "summary": dict(status.get("summary", {}) or previous_status.get("summary", {}) or {}),
                    "alert_counts": dict(status.get("alert_counts", {}) or previous_status.get("alert_counts", {}) or {}),
                },
            )
    except Exception as e:
        now_monotonic = time.monotonic()
        now_iso = datetime.now().isoformat()
        SNMP_STATUS[device_id] = _build_poll_failure(
            previous_status,
            e,
            now_iso,
            now_monotonic,
            interval_sec,
            defaults={"summary": {}, "alert_counts": {}},
        )


def snmp_update_loop():
    # pysnmp/pyasn1 on the current 32-bit Python 3.14 runtime is unstable and can
    # trigger a sustained exception storm plus high memory pressure. Keep the rest
    # of the control system available by pausing background SNMP polling here.
    if struct.calcsize("P") * 8 <= 32 and sys.version_info >= (3, 14):
        while True:
            for device_id, state in list(SNMP_STATUS.items()):
                fallback = dict(state or {})
                fallback["online"] = False
                fallback["stale"] = True
                fallback["error"] = "SNMP polling paused on 32-bit Python 3.14 runtime"
                fallback["last_error"] = fallback["error"]
                fallback["last_checked_at"] = datetime.now().isoformat()
                SNMP_STATUS[device_id] = fallback
            time.sleep(10.0)
    executor = ThreadPoolExecutor(max_workers=SNMP_MAX_WORKERS, thread_name_prefix="snmp-poll")
    in_flight = {}
    try:
        while True:
            devices = list(CONFIG.get("snmp_devices", []))
            active_ids = {str(item.get("id")) for item in devices}
            for device_id in list(SNMP_STATUS.keys()):
                if device_id not in active_ids:
                    SNMP_STATUS.pop(device_id, None)
                    in_flight.pop(device_id, None)

            done_ids = []
            for device_id, future in list(in_flight.items()):
                if future.done():
                    try:
                        future.result()
                    except Exception:
                        pass
                    done_ids.append(device_id)
            for device_id in done_ids:
                in_flight.pop(device_id, None)

            due_devices = []
            now = time.monotonic()
            for cfg in devices:
                if cfg.get("enabled", True) is False:
                    continue
                if cfg.get("visible", True) is False:
                    continue
                device_id = str(cfg.get("id"))
                if device_id in in_flight:
                    continue
                state = SNMP_STATUS.get(device_id, {}) or {}
                interval_ms = max(1000, int(cfg.get("poll_interval_ms", 5000) or 5000))
                last_polled = float(state.get("last_polled_monotonic", 0.0) or 0.0)
                if (now - last_polled) * 1000 >= interval_ms:
                    due_devices.append(cfg)
            if due_devices:
                due_devices.sort(
                    key=lambda item: float(
                        (SNMP_STATUS.get(str(item.get("id")), {}) or {}).get("last_polled_monotonic", 0.0) or 0.0
                    )
                )
                available_slots = max(0, SNMP_MAX_WORKERS - len(in_flight))
                for cfg in due_devices[:available_slots]:
                    device_id = str(cfg.get("id"))
                    try:
                        in_flight[device_id] = executor.submit(poll_single_snmp, cfg)
                    except Exception:
                        pass
            time.sleep(SNMP_IDLE_SLEEP_SEC)
    finally:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass


def poll_single_nvr(nvr_cfg):
    device_id = str(nvr_cfg.get("id"))
    previous_status = dict(NVR_STATUS.get(device_id, {}) or {})
    interval_sec = _poll_interval_sec(nvr_cfg, 10000)
    try:
        from services.hikvision_nvr import poll_hikvision_nvr

        status = dict(poll_hikvision_nvr(nvr_cfg) or {})
        now_monotonic = time.monotonic()
        now_iso = datetime.now().isoformat()
        if bool(status.get("online")):
            merged = _build_poll_success(previous_status, status, now_iso, now_monotonic)
            status_level = str(status.get("status_level") or "").strip().lower()
            if status_level in {"online", "stale", "error", "offline"}:
                merged["status_level"] = status_level
                merged = _apply_poll_status_level(merged)
            NVR_STATUS[device_id] = merged
        else:
            NVR_STATUS[device_id] = _build_poll_failure(
                previous_status,
                status.get("error") or "NVR poll returned offline",
                now_iso,
                now_monotonic,
                interval_sec,
                defaults={
                    "summary": dict(status.get("summary", {}) or previous_status.get("summary", {}) or {}),
                    "channels": list(status.get("channels", []) or previous_status.get("channels", []) or []),
                    "hdds": list(status.get("hdds", []) or previous_status.get("hdds", []) or []),
                },
            )
    except Exception as e:
        now_monotonic = time.monotonic()
        now_iso = datetime.now().isoformat()
        NVR_STATUS[device_id] = _build_poll_failure(
            previous_status,
            e,
            now_iso,
            now_monotonic,
            interval_sec,
            defaults={
                "summary": dict(previous_status.get("summary", {}) or {}),
                "channels": list(previous_status.get("channels", []) or []),
                "hdds": list(previous_status.get("hdds", []) or []),
            },
        )


def nvr_update_loop():
    executor = ThreadPoolExecutor(max_workers=max(1, NVR_MAX_WORKERS), thread_name_prefix="nvr-poll")
    in_flight = {}
    try:
        while True:
            devices = list(CONFIG.get("nvr_devices", []))
            active_ids = {str(item.get("id")) for item in devices}
            for device_id in list(NVR_STATUS.keys()):
                if device_id not in active_ids:
                    NVR_STATUS.pop(device_id, None)
                    in_flight.pop(device_id, None)

            done_ids = []
            for device_id, future in list(in_flight.items()):
                if future.done():
                    try:
                        future.result()
                    except Exception:
                        pass
                    done_ids.append(device_id)
            for device_id in done_ids:
                in_flight.pop(device_id, None)

            due_devices = []
            now = time.monotonic()
            for cfg in devices:
                if cfg.get("enabled", True) is False or cfg.get("visible", True) is False:
                    continue
                device_id = str(cfg.get("id"))
                if device_id in in_flight:
                    continue
                state = NVR_STATUS.get(device_id, {}) or {}
                interval_ms = max(2000, int(cfg.get("poll_interval_ms", 10000) or 10000))
                last_polled = float(state.get("last_polled_monotonic", 0.0) or 0.0)
                if (now - last_polled) * 1000 >= interval_ms:
                    due_devices.append(cfg)
            if due_devices:
                due_devices.sort(
                    key=lambda item: float(
                        (NVR_STATUS.get(str(item.get("id")), {}) or {}).get("last_polled_monotonic", 0.0) or 0.0
                    )
                )
                available_slots = max(0, max(1, NVR_MAX_WORKERS) - len(in_flight))
                for cfg in due_devices[:available_slots]:
                    device_id = str(cfg.get("id"))
                    try:
                        in_flight[device_id] = executor.submit(poll_single_nvr, cfg)
                    except Exception:
                        pass
            time.sleep(NVR_IDLE_SLEEP_SEC)
    finally:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass


def _machine_rows():
    try:
        from api.server import load_machine_rows, serialize_machine_rows
        return serialize_machine_rows(load_machine_rows())
    except Exception:
        return []


def _door_status_snapshot():
    try:
        from api.door import door_status_info, status_lock
        with status_lock:
            show = door_status_info.get("transition_status") or door_status_info.get("current_status")
            return {
                "status": show,
                "diff_c": door_status_info.get("diff_c", 0),
                "diff_o": door_status_info.get("diff_o", 0),
                "online": True
            }
    except Exception:
        return {"status": "unknown", "online": False}


def _parse_number(value):
    try:
        return float(value)
    except Exception:
        return None


def _compare_value(current, op, target):
    if op in ["is_true", "true"]:
        return bool(current) is True
    if op in ["is_false", "false"]:
        return bool(current) is False

    current_num = _parse_number(current)
    target_num = _parse_number(target)
    if current_num is not None and target_num is not None:
        if op == ">":
            return current_num > target_num
        if op == ">=":
            return current_num >= target_num
        if op == "<":
            return current_num < target_num
        if op == "<=":
            return current_num <= target_num
        if op == "==":
            return current_num == target_num
        if op == "!=":
            return current_num != target_num

    current_text = "" if current is None else str(current)
    target_text = "" if target is None else str(target)
    if op == "==":
        return current_text == target_text
    if op == "!=":
        return current_text != target_text
    if op == "contains":
        return target_text in current_text
    return False


def _compare_with_hysteresis(current, op, target, hysteresis, was_true):
    current_num = _parse_number(current)
    target_num = _parse_number(target)
    hysteresis_num = _parse_number(hysteresis) or 0
    if hysteresis_num <= 0 or current_num is None or target_num is None:
        return _compare_value(current, op, target)

    if op == ">":
        return current_num > (target_num - hysteresis_num if was_true else target_num)
    if op == ">=":
        return current_num >= (target_num - hysteresis_num if was_true else target_num)
    if op == "<":
        return current_num < (target_num + hysteresis_num if was_true else target_num)
    if op == "<=":
        return current_num <= (target_num + hysteresis_num if was_true else target_num)
    return _compare_value(current, op, target)


def _get_light_state(dev_id, channel=None):
    channels = LIGHT_STATUS.get(dev_id, [])
    online = bool(LIGHT_ONLINE.get(dev_id, False))
    state = {"online": online, "channel_count": len(channels)}
    for idx, value in enumerate(channels, start=1):
        state[f"channel_{idx}"] = value
    if channel:
        channel_idx = int(channel)
        if 1 <= channel_idx <= len(channels):
            state["channel_state"] = channels[channel_idx - 1]
    return state


def _get_power_state(dev_id, channel=None):
    try:
        cab_idx = int(dev_id)
    except Exception:
        return None
    cab = DEVICE_STATUS.get(cab_idx)
    if cab is None:
        return None
    channels = cab.get("channels_1_4", []) or []
    state = {
        "online": bool(cab.get("comm_status", False)),
        "work_mode": cab.get("work_mode"),
        "realtime_power": cab.get("realtime_power"),
        "daily_energy": cab.get("daily_energy"),
        "monthly_energy": cab.get("monthly_energy"),
        "cabinet_temp": cab.get("cabinet_temp"),
        "cabinet_humidity": cab.get("cabinet_humidity")
    }
    for idx, value in enumerate(channels, start=1):
        state[f"channel_{idx}"] = value
    if channel:
        channel_idx = int(channel)
        if 1 <= channel_idx <= len(channels):
            state["channel_state"] = channels[channel_idx - 1]
    return state


def _get_server_state(dev_id):
    target_id = str(dev_id)
    for machine in _machine_rows():
        if str(machine.get("mac")) == target_id:
            status = machine.get("status", {}) or {}
            agent = machine.get("agent_status", {}) or {}
            return {
                "online": bool(machine.get("is_online", False)),
                "hostname": machine.get("hostname"),
                "ip": machine.get("ip"),
                "asset_group": machine.get("asset_group", ""),
                "cpu_percent": status.get("cpu_percent"),
                "mem_percent": status.get("mem_percent"),
                "disk_percent": status.get("disk_percent"),
                "net_sent_kb_s": status.get("net_sent_kb_s"),
                "net_recv_kb_s": status.get("net_recv_kb_s"),
                "agent_version": agent.get("version"),
                "agent_task_exists": agent.get("task_exists", False)
            }
    return None


def _get_meter_state(dev_id):
    target_id = str(dev_id)
    meter = METER_STATUS.get(target_id)
    if meter is not None:
        return meter
    if target_id.startswith("cabinet_meter_"):
        try:
            cab_idx = int(target_id.replace("cabinet_meter_", ""))
        except Exception:
            return None
        cab = DEVICE_STATUS.get(cab_idx)
        if cab is None:
            return None
        return {
            "online": bool(cab.get("comm_status", False)),
            "voltage_a": cab.get("voltage_a"),
            "voltage_b": cab.get("voltage_b"),
            "voltage_c": cab.get("voltage_c"),
            "current_a": cab.get("current_a"),
            "current_b": cab.get("current_b"),
            "current_c": cab.get("current_c"),
            "realtime_power": cab.get("realtime_power"),
            "electric_energy": cab.get("electric_energy"),
            "daily_energy": cab.get("daily_energy"),
            "monthly_energy": cab.get("monthly_energy"),
            "cabinet_temp": cab.get("cabinet_temp"),
            "cabinet_humidity": cab.get("cabinet_humidity"),
            "work_mode": cab.get("work_mode")
        }
    return None


def get_state_snapshot(source_type, device_id, prop=None, channel=None):
    source_type = str(source_type or "env")
    if source_type == "env":
        return ENV_STATUS.get(str(device_id))
    if source_type == "projector":
        return PROJECTOR_STATUS.get(str(device_id))
    if source_type == "screen":
        return SCREEN_STATUS.get(str(device_id))
    if source_type == "ups":
        return UPS_STATUS.get(str(device_id))
    if source_type == "server":
        return _get_server_state(device_id)
    if source_type == "meter":
        return _get_meter_state(device_id)
    if source_type == "light":
        return _get_light_state(device_id, channel=channel)
    if source_type == "power":
        return _get_power_state(device_id, channel=channel)
    if source_type == "door":
        return _door_status_snapshot()
    return None


def get_state_value(source_type, device_id, prop, channel=None):
    snapshot = get_state_snapshot(source_type, device_id, prop=prop, channel=channel)
    if snapshot is None:
        return False, None, None
    if prop in [None, "", "value"]:
        return True, snapshot, snapshot
    if prop == "channel_state" and channel:
        return True, snapshot.get("channel_state"), snapshot
    return True, snapshot.get(prop), snapshot


def _wait_for_condition(condition, timeout_ms=60000, poll_ms=500):
    started_at = time.time()
    timeout_sec = max(float(timeout_ms or 0) / 1000.0, 0)
    poll_sec = max(float(poll_ms or 0) / 1000.0, 0.2)
    source_type = condition.get("source_type", "env")
    device_id = condition.get("device_id")
    prop = condition.get("prop", "online")
    op = condition.get("op", "==")
    value = condition.get("value")
    hysteresis = condition.get("hysteresis", 0)
    channel = condition.get("channel")

    while True:
        ok, current_value, _ = get_state_value(source_type, device_id, prop, channel=channel)
        if ok and _compare_with_hysteresis(current_value, op, value, hysteresis, False):
            return True, current_value
        if timeout_sec > 0 and (time.time() - started_at) >= timeout_sec:
            return False, current_value
        time.sleep(poll_sec)


def _find_screen_action_command(screen_cfg, action_name):
    for cmd in screen_cfg.get("commands", []) or []:
        if str(cmd.get("action")) == str(action_name):
            return cmd
    return None


def _execute_screen_action(screen_cfg, action):
    from screen_core import ScreenDriver

    driver = ScreenDriver(screen_cfg)
    action_type = action.get("action_type", action.get("action", "stop"))
    if action_type == "set_position":
        target_position = float(action.get("target_position", 0))
        plan = driver.set_position(target_position)
        move_cmd = _find_screen_action_command(screen_cfg, plan["direction"])
        stop_cmd = _find_screen_action_command(screen_cfg, "stop")
        if not move_cmd or not stop_cmd:
            return False, "缺少幕布上升/下降/停止命令，无法执行定位"
        success, res = driver.execute(move_cmd)
        if not success:
            return success, res
        time.sleep(max(float(plan.get("move_time", 0)), 0))
        return driver.execute(stop_cmd)

    command = {
        "action": action_type,
        "payload": action.get("payload", ""),
        "format": action.get("format", "hex"),
        "name": action.get("name", action_type)
    }
    return driver.execute(command)


def _do_binary_action(sys_type, action, state):
    channel = action.get("channel")
    if sys_type == "light":
        drv = LIGHT_DRIVERS.get(action.get("device_id"))
        if drv:
            drv.control_channel(channel, state)
    elif sys_type == "power":
        mc.set_channel(int(action.get("device_id", 0)), channel, state)


def _get_scene_action_params(action):
    params = action.get("params")
    if isinstance(params, dict):
        return params
    if isinstance(params, str) and params.strip():
        try:
            parsed = json.loads(params)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}


def _execute_scene_action(action):
    sys_type = action.get("sub_system", "light")
    act_type = action.get("action_type", "on" if action.get("is_open", True) else "off")
    jog_ms = int(action.get("jog_time_ms", 1000) or 1000)

    if sys_type == "server":
        mac = str(action.get("device_id"))
        if act_type == "wake":
            try:
                from wakeonlan import send_magic_packet
                send_magic_packet(mac)
                add_log(-1, f"[服务器] 已发送网络唤醒: {mac}")
            except Exception as e:
                add_log(-1, f"[服务器] 网络唤醒失败: {str(e)}")
        elif act_type in ["shutdown", "restart", "refresh"]:
            SERVER_COMMANDS[mac] = act_type
        return

    if sys_type == "projector":
        proj_cfg = next((p for p in CONFIG.get("projectors", []) if str(p.get("id")) == str(action.get("device_id"))), None)
        if proj_cfg:
            from projector_core import ProjectorDriver
            cmd_payload = {"payload": action.get("payload", ""), "format": action.get("format", "hex")}
            if action.get("command"):
                cmd_payload = action.get("command")
            success, res = ProjectorDriver(proj_cfg).execute(cmd_payload)
            if not success:
                add_log(-1, f"[投影机] 场景执行失败: {res}")
        return

    if sys_type == "screen":
        screen_cfg = next((s for s in CONFIG.get("screens", []) if str(s.get("id")) == str(action.get("device_id"))), None)
        if screen_cfg:
            success, res = _execute_screen_action(screen_cfg, action)
            if not success:
                add_log(-1, f"[幕布] 场景执行失败: {res}")
        return

    if sys_type == "universal":
        dev_cfg = next((d for d in CONFIG.get("custom_devices", []) if str(d.get("id")) == str(action.get("device_id"))), None)
        if dev_cfg:
            from universal_core import UniversalDriver
            UniversalDriver(dev_cfg).execute_command({
                "payload": action.get("payload", ""),
                "format": action.get("format", "str"),
                "wait_ms": action.get("wait_ms", 0)
            })
        return

    if sys_type == "control_center":
        from control_center_core import execute_control, execute_control_center_command

        control_cfg = CONFIG.get("control_center") or {}
        control_mode = str(action.get("control_mode") or action.get("action_type") or "").strip().lower()
        if control_mode not in {"control", "command"}:
            control_mode = "control" if str(action.get("control_id") or "").strip() else "command"
        runtime_params = _get_scene_action_params(action)
        value = action.get("value")

        try:
            if control_mode == "control":
                control_id = str(action.get("control_id") or action.get("device_id") or "").strip()
                if not control_id:
                    add_log(-1, "[协议控制] 场景执行失败: 缺少 control_id")
                    return
                result = execute_control(control_cfg, control_id, params=runtime_params, value=value)
            else:
                command_id = str(action.get("command_id") or action.get("device_id") or "").strip()
                target_group_id = str(action.get("target_group_id") or "").strip()
                if not command_id or not target_group_id:
                    add_log(-1, "[协议控制] 场景执行失败: 缺少 command_id 或 target_group_id")
                    return
                result = execute_control_center_command(
                    control_cfg,
                    command_id=command_id,
                    target_group_id=target_group_id,
                    params=runtime_params,
                    value=value,
                )
        except Exception as exc:
            add_log(-1, f"[协议控制] 场景执行异常: {str(exc)}")
            return

        if not result.get("ok"):
            add_log(-1, f"[协议控制] 场景执行失败: {result.get('msg') or result.get('error') or '未知错误'}")
        return

    if sys_type == "wait":
        wait_type = action.get("wait_type", "duration")
        if wait_type == "duration":
            time.sleep(max(float(action.get("duration_ms", action.get("delay_ms", 0)) or 0) / 1000.0, 0))
            return
        condition = {
            "source_type": action.get("source_type", "screen"),
            "device_id": action.get("device_id"),
            "prop": action.get("prop", "position"),
            "op": action.get("op", ">="),
            "value": action.get("value", action.get("target_position", 0)),
            "hysteresis": action.get("hysteresis", 0),
            "channel": action.get("channel")
        }
        ok, current_value = _wait_for_condition(
            condition,
            timeout_ms=action.get("timeout_ms", 60000),
            poll_ms=action.get("poll_ms", 500)
        )
        if not ok:
            add_log(-1, f"[场景] 等待条件超时: {condition}，当前值={current_value}")
        return

    if act_type == "on":
        _do_binary_action(sys_type, action, True)
    elif act_type == "off":
        _do_binary_action(sys_type, action, False)
    elif act_type == "jog":
        _do_binary_action(sys_type, action, True)
        time.sleep(jog_ms / 1000.0)
        _do_binary_action(sys_type, action, False)


def execute_scene(scene_id, async_mode=True):
    def _run():
        scene = next((s for s in CONFIG.get("scenes", []) if str(s["id"]) == str(scene_id)), None)
        if not scene:
            return
        scene_key = str(scene.get("id"))
        if _SCENE_RUNNING.get(scene_key):
            add_log(-1, f"[场景] 跳过重复触发，场景仍在执行中: {scene['name']}")
            return

        _SCENE_RUNNING[scene_key] = True
        try:
            add_log(-1, f"[场景] 开始执行场景: {scene['name']}")

            for action in scene.get("actions", []):
                delay = int(action.get("delay_ms", 0) or 0)
                if delay > 0:
                    time.sleep(delay / 1000.0)
                _execute_scene_action(action)

            add_log(-1, f"[场景] 场景执行完成: {scene['name']}")
        finally:
            _SCENE_RUNNING[scene_key] = False

    if async_mode:
        threading.Thread(target=_run, daemon=True).start()
        return True
    _run()
    return True


def onekey_start(cab_idx):
    threading.Thread(target=_onekey_start_task, args=(cab_idx,), daemon=True).start()
    return True


def _onekey_start_task(cab_idx):
    conf = CONFIG["cabinets"][cab_idx]
    plc = conf.get("plc_type", "AV-100")
    try:
        if "Smart" not in plc:
            mc.clients[cab_idx].send(0x05, b"\x03\xE8\xFF\x00")
        else:
            mc.clients[cab_idx].send(0x06, bytes([0x00, 0x00, 0x00, 0x01]))
        add_log(cab_idx, "一键启动指令已下发")
    except Exception:
        pass


def onekey_stop(cab_idx):
    threading.Thread(target=_onekey_stop_task, args=(cab_idx,), daemon=True).start()
    return True


def _onekey_stop_task(cab_idx):
    conf = CONFIG["cabinets"][cab_idx]
    plc = conf.get("plc_type", "AV-100")
    try:
        if "Smart" not in plc:
            mc.clients[cab_idx].send(0x05, b"\x03\xE9\xFF\x00")
        else:
            mc.clients[cab_idx].send(0x06, bytes([0x00, 0x01, 0x00, 0x01]))
        add_log(cab_idx, "一键停止指令已下发")
    except Exception:
        pass


_CAB_CACHE = {}


def poll_single_cabinet(idx):
    if idx not in _CAB_CACHE:
        _CAB_CACHE[idx] = {"last_e": -1, "date": "", "start_e": 0, "month_base": 0}
    cache = _CAB_CACHE[idx]
    conf = CONFIG["cabinets"][idx]
    plc = conf.get("plc_type", "AV-100")
    try:
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        if "AV-100" in plc:
            p_relay = mc.read_coils(idx, 0, conf["channel_count"])
            p_env = mc.read_regs(idx, 0x04B0, 16)
            p_curr = mc.read_regs(idx, 0x05DC, 12)
            p_mode = mc.read_regs(idx, 0x00A2, 1)

            if not p_env:
                raise Exception()

            DEVICE_STATUS[idx]["comm_status"] = True
            bits = mc.parse_pdu_relay(p_relay, conf["channel_count"])
            if bits:
                DEVICE_STATUS[idx]["channels_1_4"] = bits
                changed_text = _observed_channel_change_text(f"cabinet:{idx}:channels:observed", bits, conf)
                if changed_text:
                    cabinet_name = str(conf.get("cabinet_name") or conf.get("name") or f"电柜{idx + 1}")
                    message = f"[状态变化][强电柜] {cabinet_name} {changed_text}（外部/轮询识别）"
                    _record_detected_change(f"cabinet:{idx}:channels", message, cab_idx=idx)
                    try:
                        record_state_change(
                            category="power",
                            device_id=f"cabinet:{idx}",
                            device_name=cabinet_name,
                            message=message,
                            source="poller",
                            cab_idx=idx,
                            changes=[{"text": changed_text}],
                            raw={"channels": bits},
                        )
                    except Exception:
                        pass

            hum, temp = mc.parse_av100_env(p_env)
            DEVICE_STATUS[idx].update({"cabinet_humidity": hum, "cabinet_temp": temp})

            meter_mode = conf.get("meter_mode", "type1")
            ct_ratio = float(conf.get("ct_ratio", 1.0))

            if meter_mode == "debug":
                add_log(idx, f"[调试] 寻址报文 -> 04B0: {p_env.hex(' ').upper()} | 05DC: {p_curr.hex(' ').upper()}")
            else:
                va, vb, vc, ia, ib, ic, energy = mc.parse_av100_meter(p_env, p_curr, mode=meter_mode, ct_ratio=ct_ratio)
                DEVICE_STATUS[idx].update({
                    "voltage_a": va, "voltage_b": vb, "voltage_c": vc,
                    "current_a": ia, "current_b": ib, "current_c": ic,
                    "electric_energy": energy,
                    "realtime_power": round((va * ia + vb * ib + vc * ic) / 1000.0, 2)
                })
                _process_energy(idx, today, energy, cache)

            if p_mode:
                DEVICE_STATUS[idx]["work_mode"] = mc.parse_av100_mode(p_mode, conf)

        else:
            p_mode = mc.read_regs(idx, 0x03, 1)
            time.sleep(0.1)
            p_relay = mc.read_regs(idx, 0x05, conf["channel_count"])
            time.sleep(0.1)
            p_energy = mc.read_regs(idx, 0x0B, 2)
            time.sleep(0.1)
            p_env = mc.read_regs(idx, 0x0D, 2)
            time.sleep(0.1)
            p_pwr = mc.read_regs(idx, 0x0F, 6)

            if not p_relay:
                raise Exception()
            DEVICE_STATUS[idx]["comm_status"] = True
            bits = mc.parse_pdu_relay(p_relay, conf["channel_count"])
            if bits:
                DEVICE_STATUS[idx]["channels_1_4"] = bits
                changed_text = _observed_channel_change_text(f"cabinet:{idx}:channels:observed", bits, conf)
                if changed_text:
                    cabinet_name = str(conf.get("cabinet_name") or conf.get("name") or f"电柜{idx + 1}")
                    message = f"[状态变化][强电柜] {cabinet_name} {changed_text}（外部/轮询识别）"
                    _record_detected_change(f"cabinet:{idx}:channels", message, cab_idx=idx)
                    try:
                        record_state_change(
                            category="power",
                            device_id=f"cabinet:{idx}",
                            device_name=cabinet_name,
                            message=message,
                            source="poller",
                            cab_idx=idx,
                            changes=[{"text": changed_text}],
                            raw={"channels": bits},
                        )
                    except Exception:
                        pass
            if p_energy:
                e = int.from_bytes(p_energy[3:7], "big") * 0.1
                DEVICE_STATUS[idx]["electric_energy"] = e
                _process_energy(idx, today, e, cache)

            env = mc.parse_pdu_smart_env(p_env)
            if env:
                DEVICE_STATUS[idx].update({"cabinet_temp": env[0], "cabinet_humidity": env[1]})
            pwr = mc.parse_pdu_smart_pwr(p_pwr)
            if pwr:
                DEVICE_STATUS[idx].update({
                    "voltage_a": pwr[0], "voltage_b": pwr[1], "voltage_c": pwr[2],
                    "current_a": pwr[3], "current_b": pwr[4], "current_c": pwr[5]
                })
                DEVICE_STATUS[idx]["realtime_power"] = round((pwr[0] * pwr[3] + pwr[1] * pwr[4] + pwr[2] * pwr[5]) / 1000.0, 2)
            if p_mode:
                try:
                    DEVICE_STATUS[idx]["work_mode"] = [
                        conf["ui_text"]["label_mode_manual"],
                        conf["ui_text"]["label_mode_remote"],
                        conf["ui_text"]["label_mode_external"]
                    ][p_mode[-1]]
                except Exception:
                    pass

    except Exception:
        DEVICE_STATUS[idx]["comm_status"] = False


def _process_energy(idx, today, e, cache):
    cache_date = str(cache.get("date", "") or "")
    cache_start = float(cache.get("start_e", 0.0) or 0.0)
    cache_last = float(cache.get("last_e", 0.0) or 0.0)
    need_init = cache_date != today or (cache_start <= 0 and cache_last <= 0)
    if need_init:
        init_daily_record(idx, today, e)
        rec = get_daily_record(idx, today)
        cache.update({"start_e": rec["start_energy"] if rec else e, "date": today})
        log = load_energy_log()
        cab_data = _get_cab_data(log, idx)
        cache["month_base"] = sum(
            max(r["end_energy"] - r["start_energy"], 0)
            for r in cab_data.get("daily_records", [])
            if r["date"].startswith(today[:7]) and r["date"] != today
        )
        if cache_last <= 0:
            cache["last_e"] = e
    daily = max(e - cache["start_e"], 0)
    DEVICE_STATUS[idx].update({
        "daily_energy": round(daily, 1),
        "monthly_energy": round(cache["month_base"] + daily, 1),
        "current_month": datetime.now().month
    })
    if abs(e - cache["last_e"]) >= 0.1:
        update_daily_record(idx, today, e)
        cache["last_e"] = e


def _process_generic_energy(source_type, source_id, today, energy_value, cache):
    cache_date = str(cache.get("date", "") or "")
    cache_start = float(cache.get("start_e", 0.0) or 0.0)
    cache_last = float(cache.get("last_e", 0.0) or 0.0)
    need_init = cache_date != today or (cache_start <= 0 and cache_last <= 0)
    if need_init:
        init_generic_daily_record(source_type, source_id, today, energy_value)
        rec = get_generic_daily_record(source_type, source_id, today)
        cache.update({"start_e": rec["start_energy"] if rec else energy_value, "date": today})
        log = load_energy_log()
        cab_data = _get_cab_data(log, f"{source_type}:{source_id}")
        cache["month_base"] = sum(
            max(r["end_energy"] - r["start_energy"], 0)
            for r in cab_data.get("daily_records", [])
            if r["date"].startswith(today[:7]) and r["date"] != today
        )
        if cache_last <= 0:
            cache["last_e"] = energy_value
    daily = max(energy_value - cache["start_e"], 0)
    cache["daily_energy"] = round(daily, 1)
    cache["monthly_energy"] = round(cache["month_base"] + daily, 1)
    if abs(energy_value - cache["last_e"]) >= 0.1:
        update_generic_daily_record(source_type, source_id, today, energy_value)
        cache["last_e"] = energy_value


def _read_meter_mapping_value(client, mapping):
    fc = int(mapping.get("fc", 3) or 3)
    address = int(mapping.get("address", 0) or 0)
    count = int(mapping.get("count", 1) or 1)
    pdu = mc.read_registers_by_client(client, fc, address, count)
    payload = mc.extract_register_bytes_from_pdu(pdu)
    if payload is None:
        return None
    value = mc.decode_register_bytes(
        payload,
        data_type=mapping.get("data_type", "u16"),
        scale=mapping.get("scale", 1.0),
        byte_order=mapping.get("byte_order", "AB")
    )
    return round(float(value), 4)


def _apply_meter_ratio(key, value, cfg):
    if value is None:
        return None
    key = str(key or "")
    numeric = float(value)
    protocol_text = f"{cfg.get('protocol', '')} {cfg.get('model', '')}".lower()
    if "pd606" in protocol_text:
        return round(numeric, 4)
    if key.startswith("current_") or key == "realtime_power":
        ratio = float(cfg.get("ct_ratio", 1.0) or 1.0)
        if ratio > 0:
            numeric *= ratio
    elif key == "electric_energy":
        multiplier = float(cfg.get("multiplier", 1.0) or 1.0)
        numeric *= multiplier
    return round(numeric, 4)


def _decode_meter_energy_preset(client, cfg):
    preset = str(cfg.get("energy_format_preset", "custom") or "custom")
    if preset == "custom":
        return None
    reg_addr = int((cfg.get("register_map", {}) or {}).get("electric_energy", {}).get("address", 0) or 0)
    if reg_addr < 0:
        return None
    multiplier = float(cfg.get("multiplier", 1.0) or 1.0)
    if preset == "legacy_fmt1":
        pdu = mc.read_registers_by_client(client, 4, reg_addr, 2)
        payload = mc.extract_register_bytes_from_pdu(pdu)
        if not payload or len(payload) < 4:
            return None
        value = int.from_bytes(payload[:4], "big", signed=False) / 100.0
        return round(value * multiplier, 4)
    if preset == "legacy_fmt2":
        pdu = mc.read_registers_by_client(client, 4, reg_addr, 2)
        payload = mc.extract_register_bytes_from_pdu(pdu)
        if not payload or len(payload) < 4:
            return None
        value = struct.unpack(">f", payload[:4])[0] / 1000.0
        return round(float(value) * multiplier, 4)
    if preset == "legacy_fmt3":
        pdu = mc.read_registers_by_client(client, 3, reg_addr, 2)
        payload = mc.extract_register_bytes_from_pdu(pdu)
        if not payload or len(payload) < 4:
            return None
        value = int.from_bytes(bytes([payload[2], payload[3], payload[0], payload[1]]), "big", signed=False) / 100.0
        return round(value * multiplier, 4)
    if preset == "legacy_fmt4":
        pdu = mc.read_registers_by_client(client, 4, reg_addr, 2)
        payload = mc.extract_register_bytes_from_pdu(pdu)
        if not payload or len(payload) < 4:
            return None
        value = int.from_bytes(payload[:4], "big", signed=False) / 100.0
        return round(value * multiplier, 4)
    mapping = (cfg.get("register_map", {}) or {}).get("electric_energy", {}) or {}
    value = _read_meter_mapping_value(client, mapping)
    if value is None:
        return None
    return round(float(value) * multiplier, 4)


def _safe_meter_number(value, default=0.0):
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _get_meter_source_snapshot(source_id):
    source_id = str(source_id or "").strip()
    if not source_id:
        return None
    if source_id.startswith("cabinet_meter_"):
        try:
            cab_idx = int(source_id.replace("cabinet_meter_", ""))
        except Exception:
            return None
        cab = DEVICE_STATUS.get(cab_idx)
        if not cab:
            return None
        cab_cfg = (CONFIG.get("cabinets", []) or [])[cab_idx] if cab_idx < len(CONFIG.get("cabinets", [])) else {}
        return {
            "id": source_id,
            "name": cab_cfg.get("cabinet_name", f"电柜 {cab_idx + 1}"),
            "online": bool(cab.get("comm_status", False)),
        "voltage_a": cab.get("voltage_a", 0.0),
        "voltage_b": cab.get("voltage_b", 0.0),
        "voltage_c": cab.get("voltage_c", 0.0),
        "voltage_ab": cab.get("voltage_ab", 0.0),
        "voltage_bc": cab.get("voltage_bc", 0.0),
        "voltage_ca": cab.get("voltage_ca", 0.0),
        "current_a": cab.get("current_a", 0.0),
        "current_b": cab.get("current_b", 0.0),
        "current_c": cab.get("current_c", 0.0),
        "realtime_power": cab.get("realtime_power", 0.0),
        "reactive_power": cab.get("reactive_power", 0.0),
        "apparent_power": cab.get("apparent_power", 0.0),
        "power_factor": cab.get("power_factor", 0.0),
        "frequency": cab.get("frequency", 0.0),
        "electric_energy": cab.get("electric_energy", 0.0),
        "daily_energy": cab.get("daily_energy", 0.0),
        "monthly_energy": cab.get("monthly_energy", 0.0),
        }
    if source_id in METER_STATUS:
        status = dict(METER_STATUS.get(source_id, {}) or {})
        status["id"] = source_id
        status["name"] = status.get("name") or source_id
        return status
    return None


def _calculate_meter_value(left_value, right_value, operator):
    left_num = _safe_meter_number(left_value, 0.0)
    right_num = _safe_meter_number(right_value, 0.0)
    if operator == "add":
        return round(left_num + right_num, 4)
    return round(max(left_num - right_num, 0.0), 4)


def _build_calculated_meter_status(cfg):
    meter_id = str(cfg.get("id"))
    left_id = str(cfg.get("calc_left_source_id", "") or "")
    right_id = str(cfg.get("calc_right_source_id", "") or "")
    operator = str(cfg.get("calc_operator", "subtract") or "subtract")
    left = _get_meter_source_snapshot(left_id)
    right = _get_meter_source_snapshot(right_id)
    if not left:
        return {
            "id": meter_id,
            "name": cfg.get("name", meter_id),
            "online": False,
            "error": "计算来源 A 不存在或无数据",
            "updated_at": datetime.now().isoformat(),
        }
    if not right:
        return {
            "id": meter_id,
            "name": cfg.get("name", meter_id),
            "online": False,
            "error": "计算来源 B 不存在或无数据",
            "updated_at": datetime.now().isoformat(),
        }
    online = bool(left.get("online", False)) and bool(right.get("online", False))
    merged = {
        "id": meter_id,
        "name": cfg.get("name", meter_id),
        "online": online,
        "source_mode": "calculated",
        "meter_kind": cfg.get("meter_kind", "区域计算电表"),
        "meter_type": cfg.get("meter_type", "calculated"),
        "protocol": cfg.get("protocol", "A-B 计算"),
        "comm_mode": "CALC",
        "ct_ratio": float(cfg.get("ct_ratio", 1.0) or 1.0),
        "multiplier": 1.0,
        "calc_operator": operator,
        "calc_left_source_id": left_id,
        "calc_right_source_id": right_id,
        "calc_left_name": left.get("name") or left_id,
        "calc_right_name": right.get("name") or right_id,
        "voltage_a": _safe_meter_number(left.get("voltage_a"), 0.0),
        "voltage_b": _safe_meter_number(left.get("voltage_b"), 0.0),
        "voltage_c": _safe_meter_number(left.get("voltage_c"), 0.0),
        "voltage_ab": _safe_meter_number(left.get("voltage_ab"), 0.0),
        "voltage_bc": _safe_meter_number(left.get("voltage_bc"), 0.0),
        "voltage_ca": _safe_meter_number(left.get("voltage_ca"), 0.0),
        "current_a": _calculate_meter_value(left.get("current_a"), right.get("current_a"), operator),
        "current_b": _calculate_meter_value(left.get("current_b"), right.get("current_b"), operator),
        "current_c": _calculate_meter_value(left.get("current_c"), right.get("current_c"), operator),
        "realtime_power": _calculate_meter_value(left.get("realtime_power"), right.get("realtime_power"), operator),
        "reactive_power": _calculate_meter_value(left.get("reactive_power"), right.get("reactive_power"), operator),
        "apparent_power": _calculate_meter_value(left.get("apparent_power"), right.get("apparent_power"), operator),
        "power_factor": _safe_meter_number(left.get("power_factor"), 0.0),
        "frequency": _safe_meter_number(left.get("frequency"), 0.0),
        "electric_energy": _calculate_meter_value(left.get("electric_energy"), right.get("electric_energy"), operator),
        "daily_energy": _calculate_meter_value(left.get("daily_energy"), right.get("daily_energy"), operator),
        "monthly_energy": _calculate_meter_value(left.get("monthly_energy"), right.get("monthly_energy"), operator),
        "cabinet_temp": None,
        "cabinet_humidity": None,
        "updated_at": datetime.now().isoformat(),
    }
    if online:
        merged["error"] = ""
    else:
        merged["error"] = "计算源离线"
    return merged


def update_loop():
    while True:
        meter_statistics = CONFIG.get("meter_statistics", {}) or {}
        cabinet_gateway_enabled = bool(meter_statistics.get("cabinet_gateway_enabled", False)) or bool(
            meter_statistics.get("remote_service_enabled", False)
        )
        if cabinet_gateway_enabled:
            time.sleep(2)
            continue
        cabs = CONFIG.get("cabinets", [])
        if cabs:
            for idx in range(len(cabs)):
                try:
                    poll_single_cabinet(idx)
                except Exception:
                    pass
        time.sleep(2)


def meter_update_loop():
    while True:
        today = datetime.now().strftime("%Y-%m-%d")
        meter_configs = list(CONFIG.get("meters", []))
        active_ids = {str(item.get("id")) for item in meter_configs}
        calculated_configs = []
        for meter_id in list(METER_STATUS.keys()):
            if meter_id not in active_ids:
                METER_STATUS.pop(meter_id, None)

        for cfg in meter_configs:
            meter_id = str(cfg.get("id"))
            if str(cfg.get("source_mode", "standalone")) == "calculated":
                calculated_configs.append(cfg)
                continue
            if not cfg.get("enabled", True):
                METER_STATUS[meter_id] = {
                    "id": meter_id,
                    "name": cfg.get("name", meter_id),
                    "online": False,
                    "error": "已停用",
                    "updated_at": datetime.now().isoformat()
                }
                continue
            bind_cabinet_idx = int(cfg.get("bind_cabinet_idx", -1) or -1)
            current = METER_STATUS.get(meter_id, {})
            energy_cache = current.get("_energy_cache", {
                "date": today,
                "start_e": 0.0,
                "last_e": 0.0,
                "month_base": 0.0,
                "daily_energy": 0.0,
                "monthly_energy": 0.0
            })
            merged = {
                "id": meter_id,
                "name": cfg.get("name", meter_id),
                "online": False,
                "source_mode": cfg.get("source_mode", "standalone"),
                "meter_kind": cfg.get("meter_kind", "独立电表"),
                "meter_type": cfg.get("meter_type", "direct"),
                "protocol": cfg.get("protocol", "Modbus-RTU/TCP"),
                "comm_mode": cfg.get("comm_mode", "TCP"),
                "ct_ratio": float(cfg.get("ct_ratio", 1.0) or 1.0),
                "multiplier": float(cfg.get("multiplier", 1.0) or 1.0),
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
                "cabinet_temp": None,
                "cabinet_humidity": None,
                "updated_at": datetime.now().isoformat()
            }
            merged.update(current)

            if str(cfg.get("source_mode", "standalone")) == "cabinet_linked" and bind_cabinet_idx >= 0:
                cab = DEVICE_STATUS.get(bind_cabinet_idx)
                cab_cfg = (CONFIG.get("cabinets", []) or [])[bind_cabinet_idx] if bind_cabinet_idx < len(CONFIG.get("cabinets", [])) else {}
                if cab:
                    merged.update({
                        "online": bool(cab.get("comm_status", False)),
                        "realtime_power": cab.get("realtime_power", 0.0),
                        "electric_energy": cab.get("electric_energy", 0.0),
                        "daily_energy": cab.get("daily_energy", 0.0),
                        "monthly_energy": cab.get("monthly_energy", 0.0),
                        "voltage_a": cab.get("voltage_a", 0.0),
                        "voltage_b": cab.get("voltage_b", 0.0),
                        "voltage_c": cab.get("voltage_c", 0.0),
                        "voltage_ab": cab.get("voltage_ab", 0.0),
                        "voltage_bc": cab.get("voltage_bc", 0.0),
                        "voltage_ca": cab.get("voltage_ca", 0.0),
                        "current_a": cab.get("current_a", 0.0),
                        "current_b": cab.get("current_b", 0.0),
                        "current_c": cab.get("current_c", 0.0),
                        "reactive_power": cab.get("reactive_power", 0.0),
                        "apparent_power": cab.get("apparent_power", 0.0),
                        "power_factor": cab.get("power_factor", 0.0),
                        "frequency": cab.get("frequency", 0.0),
                        "cabinet_temp": cab.get("cabinet_temp"),
                        "cabinet_humidity": cab.get("cabinet_humidity"),
                        "work_mode": cab.get("work_mode", "未知"),
                        "bound_cabinet_name": cab_cfg.get("cabinet_name", f"电柜 {bind_cabinet_idx + 1}")
                    })
                else:
                    merged["online"] = False
            else:
                protocol = str(cfg.get("comm_mode", "TCP")).upper()
                client_protocol = "RTU_OVER_TCP" if protocol == "RTU_OVER_TCP" else "AV-100"
                client = None
                try:
                    if protocol == "COM":
                        merged.update({"online": False, "error": "COM 读取模板待补充"})
                    else:
                        client = mc.make_client(
                            cfg.get("ip", ""),
                            int(cfg.get("port", 502) or 502),
                            int(cfg.get("station_id", 1) or 1),
                            timeout=max(float(cfg.get("timeout_sec", 1.5) or 1.5), 0.5),
                            protocol=client_protocol
                        )
                        if client.connect():
                            register_map = cfg.get("register_map", {}) or {}
                            for key, mapping in register_map.items():
                                if not isinstance(mapping, dict) or not mapping.get("enabled", False):
                                    continue
                                if key == "electric_energy" and str(cfg.get("energy_format_preset", "custom") or "custom") != "custom":
                                    value = _decode_meter_energy_preset(client, cfg)
                                else:
                                    value = _read_meter_mapping_value(client, mapping)
                                if value is not None:
                                    if key == "electric_energy" and str(cfg.get("energy_format_preset", "custom") or "custom") != "custom":
                                        merged[key] = round(float(value), 4)
                                    else:
                                        merged[key] = _apply_meter_ratio(key, value, cfg)
                            merged["online"] = True
                            merged["error"] = ""
                            if merged.get("electric_energy") is not None:
                                energy_value = float(merged.get("electric_energy") or 0.0)
                                _process_generic_energy("meter", meter_id, today, energy_value, energy_cache)
                                merged["daily_energy"] = energy_cache["daily_energy"]
                                merged["monthly_energy"] = energy_cache["monthly_energy"]
                        else:
                            merged.update({"online": False, "error": "连接失败"})
                except Exception as e:
                    merged.update({"online": False, "error": str(e)})
                finally:
                    try:
                        if client:
                            client.close()
                    except Exception:
                        pass
                merged["_energy_cache"] = energy_cache

            METER_STATUS[meter_id] = merged

        for cfg in calculated_configs:
            meter_id = str(cfg.get("id"))
            if not cfg.get("enabled", True):
                METER_STATUS[meter_id] = {
                    "id": meter_id,
                    "name": cfg.get("name", meter_id),
                    "online": False,
                    "error": "已停用",
                    "updated_at": datetime.now().isoformat()
                }
                continue
            METER_STATUS[meter_id] = _build_calculated_meter_status(cfg)

        time.sleep(2)


def env_update_loop():
    while True:
        sync_env_sensor_configs(CONFIG.get("env_sensors", []))
        for cfg in CONFIG.get("env_sensors", []):
            dev_id = cfg["id"]
            if dev_id not in ENV_STATUS:
                ENV_STATUS[dev_id] = {
                    "online": False,
                    "temp": 0,
                    "hum": 0,
                    "lux": 0,
                    "noise": 0,
                    "pm25": 0,
                    "pm10": 0,
                    "pressure": 0
                }
            source_type = str(cfg.get("source_type") or "modbus").strip().lower()
            if source_type == "mqtt":
                state = get_mqtt_env_state(cfg)
                if state:
                    ENV_STATUS[dev_id].update(state)
                    _record_env_status_sample(dev_id)
                else:
                    ENV_STATUS[dev_id]["online"] = False
                continue
            if source_type == "push":
                updated_at = ENV_STATUS[dev_id].get("updated_at")
                stale_after_sec = max(30, int(cfg.get("push", {}).get("stale_after_sec", 1200) or 1200))
                if updated_at:
                    try:
                        last_dt = datetime.fromisoformat(str(updated_at))
                        ENV_STATUS[dev_id]["age_sec"] = max(0, int((datetime.now() - last_dt).total_seconds()))
                        ENV_STATUS[dev_id]["online"] = ENV_STATUS[dev_id]["age_sec"] <= stale_after_sec
                    except Exception:
                        ENV_STATUS[dev_id]["online"] = False
                else:
                    ENV_STATUS[dev_id]["online"] = False
                continue
            if source_type in {"home_assistant", "homeassistant", "ha"}:
                state = get_ha_env_state(cfg, CONFIG)
                if state:
                    ENV_STATUS[dev_id].update(state)
                    _record_env_status_sample(dev_id)
                else:
                    ENV_STATUS[dev_id]["online"] = False
                continue
            try:
                client = mc.ModbusClient(cfg["ip"], int(cfg["port"]), int(cfg.get("station_id", 1)), protocol="PRSense")
                if client.connect():
                    start_addr = int(cfg.get("register_start", 500))
                    reg_count = int(cfg.get("register_count", 8))
                    req = start_addr.to_bytes(2, "big") + reg_count.to_bytes(2, "big")
                    res = client.send(0x03, req)
                    if res:
                        parsed = mc.parse_prsense_env(res)
                        if parsed:
                            ENV_STATUS[dev_id].update({
                                "online": True,
                                "temp": parsed["temperature"],
                                "hum": parsed["humidity"],
                                "lux": parsed["illuminance"],
                                "noise": parsed["noise"],
                                "pm25": parsed["pm25"],
                                "pm10": parsed["pm10"],
                                "pressure": parsed["pressure"],
                                "updated_at": datetime.now().isoformat()
                            })
                            _record_env_status_sample(dev_id)
                            continue
            except Exception:
                pass
            ENV_STATUS[dev_id]["online"] = False
        time.sleep(2)


_AUTO_STATE = {}
_SCENE_RUNNING = {}
_METER_REPORT_STATE = {"last_daily": "", "last_weekly": "", "last_monthly": ""}
_DISPLAY_RESET_SNAPSHOT_KEY = "_display_reset_last_snapshot"


def _get_rule_state(rule_id):
    if rule_id not in _AUTO_STATE:
        _AUTO_STATE[rule_id] = {
            "latched": False,
            "condition_true": False,
            "hits": 0,
            "active_since": None,
            "last_schedule_key": ""
        }
    return _AUTO_STATE[rule_id]


def _day_match(schedule, now):
    day_type = schedule.get("day_type", "everyday")
    wd = now.weekday()
    if day_type == "everyday":
        return True
    if day_type == "workday":
        return wd < 5
    if day_type == "weekend":
        return wd >= 5
    if day_type == "custom":
        return str(wd) in [str(item) for item in schedule.get("days", [])]
    return True


def _evaluate_condition(cond, state, now):
    source_type = cond.get("source_type", "env")
    device_id = cond.get("device_id")
    prop = cond.get("prop", "lux")
    op = cond.get("op", "<")
    value = cond.get("value", 0)
    hysteresis = cond.get("hysteresis", 0)
    debounce_sec = max(float(cond.get("debounce_sec", 0) or 0), 0)
    consecutive_hits = max(int(cond.get("consecutive_hits", 1) or 1), 1)
    channel = cond.get("channel")

    ok, current_value, _ = get_state_value(source_type, device_id, prop, channel=channel)
    if not ok:
        state["condition_true"] = False
        state["hits"] = 0
        state["active_since"] = None
        return False, current_value

    raw_match = _compare_with_hysteresis(current_value, op, value, hysteresis, state["condition_true"])
    if raw_match:
        state["hits"] += 1
        if state["active_since"] is None:
            state["active_since"] = now.timestamp()
    else:
        state["hits"] = 0
        state["active_since"] = None

    stable = raw_match
    if stable and state["hits"] < consecutive_hits:
        stable = False
    if stable and debounce_sec > 0:
        stable = (now.timestamp() - (state["active_since"] or now.timestamp())) >= debounce_sec

    state["condition_true"] = raw_match
    return stable, current_value


def automation_engine_loop():
    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_key = now.strftime("%Y-%m-%d %H:%M")

        for rule in CONFIG.get("automations", []):
            rid = rule["id"]
            state = _get_rule_state(rid)

            if not rule.get("enabled", False):
                _AUTO_STATE[rid] = {
                    "latched": False,
                    "condition_true": False,
                    "hits": 0,
                    "active_since": None,
                    "last_schedule_key": ""
                }
                continue

            trigger_type = rule.get("trigger_type", "condition")
            schedule = rule.get("schedule", {})
            condition = rule.get("condition", {})
            day_match = _day_match(schedule, now)
            trigger_matched = False

            if trigger_type == "schedule":
                if day_match and current_time == schedule.get("time") and state["last_schedule_key"] != current_key:
                    trigger_matched = True
                    state["last_schedule_key"] = current_key
            else:
                cond_match, current_value = _evaluate_condition(condition, state, now)
                if trigger_type == "condition":
                    trigger_matched = cond_match
                elif trigger_type == "mixed":
                    in_window = day_match and (schedule.get("time_start", "00:00") <= current_time <= schedule.get("time_end", "23:59"))
                    trigger_matched = cond_match and in_window
                if not trigger_matched and condition.get("log_current_value", False):
                    add_log(-1, f"[自动化] 规则 [{rule['name']}] 当前值: {current_value}")

            if trigger_matched and not state["latched"]:
                state["latched"] = True
                add_log(-1, f"[自动化] 触发规则: [{rule['name']}]")
                execute_scene(rule.get("action_scene_id"))
            elif not trigger_matched:
                state["latched"] = False

        time.sleep(1)


def meter_statistics_maintenance_loop():
    while True:
        try:
            meter_statistics = CONFIG.get("meter_statistics", {}) or {}
            abs_report_dir = str(resolve_report_dir(meter_statistics.get("report_dir")))
            center_report_dir = os.path.join(abs_report_dir, "center")
            raw_report_dir = os.path.join(abs_report_dir, "raw")
            auto_export_enabled = bool(meter_statistics.get("auto_export_enabled", True))
            now = datetime.now()
            current_time = now.strftime("%H:%M")
            today_key = now.strftime("%Y-%m-%d")
            week_key = f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"
            month_key = now.strftime("%Y-%m")

            if auto_export_enabled and current_time == "00:05" and _METER_REPORT_STATE.get("last_daily") != today_key:
                from api.power import build_meter_center_payload, get_all_meter_rows
                payload = build_meter_center_payload(target_source_key="total", period="day", days=32)
                rows = payload.get("trend_breakdown", {}).get("daily", [])
                export_meter_statistics_csv("全部统计电表", rows, center_report_dir, prefix="meter_daily")
                export_meter_snapshot_csv(get_all_meter_rows(), raw_report_dir, prefix="meter_raw_daily")
                _METER_REPORT_STATE["last_daily"] = today_key

            if auto_export_enabled and now.weekday() == 0 and current_time == "00:10" and _METER_REPORT_STATE.get("last_weekly") != week_key:
                from api.power import build_meter_center_payload, get_all_meter_rows
                payload = build_meter_center_payload(target_source_key="total", period="week", days=90)
                rows = payload.get("trend_breakdown", {}).get("weekly", [])
                export_meter_statistics_csv("全部统计电表", rows, center_report_dir, prefix="meter_weekly")
                export_meter_snapshot_csv(get_all_meter_rows(), raw_report_dir, prefix="meter_raw_weekly")
                _METER_REPORT_STATE["last_weekly"] = week_key

            if auto_export_enabled and now.day == 1 and current_time == "00:15" and _METER_REPORT_STATE.get("last_monthly") != month_key:
                from api.power import build_meter_center_payload, get_all_meter_rows
                payload = build_meter_center_payload(target_source_key="total", period="month", days=400)
                rows = payload.get("trend_breakdown", {}).get("monthly", [])
                export_meter_statistics_csv("全部统计电表", rows, center_report_dir, prefix="meter_monthly")
                export_meter_snapshot_csv(get_all_meter_rows(), raw_report_dir, prefix="meter_raw_monthly")
                _METER_REPORT_STATE["last_monthly"] = month_key

            display_reset_enabled = bool(meter_statistics.get("display_reset_enabled", False))
            display_reset_from = str(meter_statistics.get("display_reset_from") or "").strip()
            if display_reset_enabled and display_reset_from:
                display_reset = meter_statistics.get("display_reset", {})
                if not isinstance(display_reset, dict):
                    display_reset = {}
                snapshot_key = f"{display_reset_from}|{display_reset.get('value', '')}"
                if now.strftime("%Y-%m-%d %H:%M:%S") >= display_reset_from and CONFIG.get(_DISPLAY_RESET_SNAPSHOT_KEY) != snapshot_key:
                    total_energy = 0.0
                    for idx, cab in DEVICE_STATUS.items():
                        total_energy += _safe_meter_number(cab.get("electric_energy"), 0.0)
                    for meter_id, meter in METER_STATUS.items():
                        if meter_id.startswith("cabinet_meter_"):
                            continue
                        if meter.get("include_in_totals", True):
                            total_energy += _safe_meter_number(meter.get("electric_energy"), 0.0)
                    meter_statistics["display_reset"] = {
                        "enabled": True,
                        "from": display_reset_from,
                        "value": round(total_energy, 4)
                    }
                    CONFIG["meter_statistics"] = meter_statistics
                    CONFIG[_DISPLAY_RESET_SNAPSHOT_KEY] = f"{display_reset_from}|{round(total_energy, 4)}"
            time.sleep(20)
        except Exception:
            time.sleep(20)


# Compatibility exports while the codebase is being split.
get_state_snapshot = runtime_state.get_state_snapshot
get_state_value = runtime_state.get_state_value
execute_scene = runtime_automation.execute_scene
automation_engine_loop = runtime_automation.automation_engine_loop
