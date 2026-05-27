# AI_MODULE: snmp_remote_agent_client
# AI_PURPOSE: 120 主控从 121 smart-snmp-agent 拉取 SNMP 缓存并写入本地 SNMP_STATUS。
# AI_BOUNDARY: 不执行本地 SNMP 轮询；只处理 HTTP 拉取、字段校验、缓存降级和状态标记。
# AI_DATA_FLOW: http://121:6916/status -> runtime.state.SNMP_STATUS -> /api/snmp/status -> 前端。
# AI_RUNTIME: background.snmp_update_loop 在远程模式下调用本模块循环。
# AI_RISK: 中，远程 agent 不可达时必须保留旧缓存，不能让页面直接清空。
# AI_SEARCH_KEYWORDS: remote snmp, 121, agent, pull, cache.

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any


def _now_iso() -> str:
    return datetime.now().isoformat()


def _get_config() -> dict[str, Any]:
    from config import CONFIG

    return CONFIG


def _get_snmp_status() -> dict[str, dict[str, Any]]:
    from runtime.state import SNMP_STATUS

    return SNMP_STATUS


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def get_remote_snmp_agent_config() -> dict[str, Any]:
    raw = _get_config().get("snmp_remote_agent", {})
    cfg = dict(raw if isinstance(raw, dict) else {})
    env_enabled = os.environ.get("SMART_CENTER_SNMP_REMOTE_ENABLED")
    enabled = _truthy(env_enabled) if env_enabled is not None else bool(cfg.get("enabled", False))
    base_url = str(os.environ.get("SMART_CENTER_SNMP_REMOTE_URL") or cfg.get("url") or "http://192.168.50.121:6916").strip().rstrip("/")
    return {
        "enabled": enabled,
        "url": base_url,
        "poll_interval_sec": max(1.0, _safe_float(os.environ.get("SMART_CENTER_SNMP_REMOTE_POLL_SEC") or cfg.get("poll_interval_sec"), 3.0)),
        "timeout_sec": max(0.5, _safe_float(os.environ.get("SMART_CENTER_SNMP_REMOTE_TIMEOUT_SEC") or cfg.get("timeout_sec"), 2.5)),
        "stale_after_sec": max(10.0, _safe_float(os.environ.get("SMART_CENTER_SNMP_REMOTE_STALE_SEC") or cfg.get("stale_after_sec"), 25.0)),
        "failure_offline_after": max(1, _safe_int(os.environ.get("SMART_CENTER_SNMP_REMOTE_FAILURE_OFFLINE_AFTER") or cfg.get("failure_offline_after"), 5)),
    }


def is_remote_snmp_agent_enabled() -> bool:
    return bool(get_remote_snmp_agent_config().get("enabled"))


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _fetch_json(url: str, timeout_sec: float) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "smart-center-snmp-remote/2026.05.28"})
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        body = resp.read()
        if int(getattr(resp, "status", 200) or 200) >= 400:
            raise RuntimeError(f"remote returned HTTP {getattr(resp, 'status', 0)}")
    payload = json.loads(body.decode("utf-8", "ignore"))
    if not isinstance(payload, dict):
        raise RuntimeError("remote payload is not object")
    return payload


def _mark_all_stale(error: Any, cfg: dict[str, Any], failure_count: int) -> None:
    now_iso = _now_iso()
    err_text = str(error or "remote SNMP agent unavailable")
    offline_after = int(cfg.get("failure_offline_after") or 5)
    snmp_status = _get_snmp_status()
    for device_id, current in list(snmp_status.items()):
        payload = dict(current or {})
        payload["snmp_remote_source"] = cfg.get("url")
        payload["snmp_remote_error"] = err_text
        payload["snmp_remote_failures"] = failure_count
        payload["last_checked_at"] = now_iso
        payload["last_error"] = err_text
        payload["last_error_at"] = now_iso
        payload["stale"] = True
        if failure_count >= offline_after:
            payload["online"] = False
            payload["status_level"] = "error"
            payload["status_label"] = "异常"
        else:
            payload["status_level"] = "stale"
            payload["status_label"] = "陈旧"
        snmp_status[device_id] = payload


def apply_remote_snmp_snapshot(snapshot: dict[str, Any], cfg: dict[str, Any]) -> int:
    devices = snapshot.get("devices", {})
    if not isinstance(devices, dict):
        raise RuntimeError("remote payload missing devices object")
    active_ids = {str(item.get("id")) for item in _get_config().get("snmp_devices", []) if isinstance(item, dict)}
    now_mono = time.monotonic()
    now_iso = _now_iso()
    applied = 0
    snmp_status = _get_snmp_status()
    for device_id, status in devices.items():
        safe_id = str(device_id)
        if active_ids and safe_id not in active_ids:
            continue
        if not isinstance(status, dict):
            continue
        payload = dict(status)
        payload["snmp_remote_source"] = cfg.get("url")
        payload["snmp_remote_received_at"] = now_iso
        payload["snmp_remote_agent"] = dict(snapshot.get("agent", {}) or {})
        payload["last_remote_pull_monotonic"] = now_mono
        payload["last_polled_monotonic"] = now_mono
        snmp_status[safe_id] = payload
        applied += 1
    if active_ids:
        for device_id in list(snmp_status.keys()):
            if device_id not in active_ids:
                snmp_status.pop(device_id, None)
    return applied


def snmp_remote_agent_loop() -> None:
    failure_count = 0
    while True:
        cfg = get_remote_snmp_agent_config()
        if not cfg.get("enabled"):
            time.sleep(5.0)
            continue
        try:
            snapshot = _fetch_json(f"{cfg['url']}/status", float(cfg.get("timeout_sec") or 2.5))
            apply_remote_snmp_snapshot(snapshot, cfg)
            failure_count = 0
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError, OSError) as exc:
            failure_count += 1
            _mark_all_stale(exc, cfg, failure_count)
        except Exception as exc:
            failure_count += 1
            _mark_all_stale(exc, cfg, failure_count)
        time.sleep(float(cfg.get("poll_interval_sec") or 3.0))
