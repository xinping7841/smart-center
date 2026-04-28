import json
import time
import urllib.error
import urllib.parse
import urllib.request

from config import CONFIG


REMOTE_CABINET_STATUS_CACHE = {}
REMOTE_CABINET_STATUS_CACHE_TTL_SEC = 4.0


def _safe_int(value, default=0):
    try:
        if value in (None, ""):
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def clear_remote_cabinet_status_cache(cab_idx=None):
    if cab_idx is None:
        REMOTE_CABINET_STATUS_CACHE.clear()
        return
    target = int(cab_idx or 0)
    for key in list(REMOTE_CABINET_STATUS_CACHE.keys()):
        try:
            if int(key[1]) == target:
                REMOTE_CABINET_STATUS_CACHE.pop(key, None)
        except Exception:
            continue


def _store_remote_cabinet_status_cache(base, cab_idx, payload):
    if not isinstance(payload, dict):
        return
    REMOTE_CABINET_STATUS_CACHE[(base, int(cab_idx or 0))] = {
        "ts": time.monotonic(),
        "payload": dict(payload),
    }


def get_cabinet_gateway_base():
    meter_statistics = CONFIG.get("meter_statistics", {}) or {}
    explicit_base = str(meter_statistics.get("cabinet_gateway_url", "") or "").strip().rstrip("/")
    if explicit_base and bool(meter_statistics.get("cabinet_gateway_enabled", False)):
        return explicit_base

    # Reuse the NAS meter service as the cabinet gateway when it is already enabled.
    remote_base = str(meter_statistics.get("remote_service_url", "") or "").strip().rstrip("/")
    if remote_base and bool(meter_statistics.get("remote_service_enabled", False)):
        return remote_base

    if bool(meter_statistics.get("cabinet_gateway_enabled", False)):
        return explicit_base
    return ""


def get_cabinet_gateway_timeout():
    meter_statistics = CONFIG.get("meter_statistics", {}) or {}
    timeout = _safe_int(meter_statistics.get("cabinet_gateway_timeout_sec", 0), 0)
    if timeout > 0:
        return max(1, timeout)
    remote_timeout = _safe_int(meter_statistics.get("remote_service_timeout_sec", 5), 5)
    return max(1, remote_timeout)


def _request_json(url, *, method="GET", payload=None, timeout=None):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout or get_cabinet_gateway_timeout()) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = ""
        if body:
            try:
                payload = json.loads(body)
                message = payload.get("msg") or payload.get("message") or payload.get("error")
                if message:
                    raise RuntimeError(str(message)) from exc
            except json.JSONDecodeError:
                pass
        raise RuntimeError(f"HTTP {exc.code}") from exc


def fetch_gateway_health():
    base = get_cabinet_gateway_base()
    if not base:
        return {"ok": 0, "msg": "cabinet_gateway_disabled", "base": ""}
    try:
        return {"ok": 1, "base": base, "health": _request_json(f"{base}/api/cabinet/health")}
    except Exception as exc:
        return {"ok": 0, "base": base, "msg": str(exc)}


def fetch_remote_cabinet_status(cab_idx):
    base = get_cabinet_gateway_base()
    if not base:
        raise RuntimeError("cabinet gateway disabled")
    cache_key = (base, int(cab_idx or 0))
    cached = REMOTE_CABINET_STATUS_CACHE.get(cache_key)
    now = time.monotonic()
    if cached and now - float(cached.get("ts") or 0.0) < REMOTE_CABINET_STATUS_CACHE_TTL_SEC:
        payload = dict(cached.get("payload") or {})
        payload["cache_hit"] = True
        return payload
    query = urllib.parse.urlencode({"cab": int(cab_idx or 0)})
    payload = _request_json(f"{base}/api/cabinet/status?{query}")
    _store_remote_cabinet_status_cache(base, cab_idx, payload or {})
    return payload


def fetch_remote_cabinet_logs(cab_idx):
    base = get_cabinet_gateway_base()
    if not base:
        raise RuntimeError("cabinet gateway disabled")
    if cab_idx is None:
        return _request_json(f"{base}/api/cabinet/logs")
    query = urllib.parse.urlencode({"cab": int(cab_idx or 0)})
    return _request_json(f"{base}/api/cabinet/logs?{query}")


def fetch_remote_cabinet_energy_history(cab_idx, days=7):
    base = get_cabinet_gateway_base()
    if not base:
        raise RuntimeError("cabinet gateway disabled")
    query = urllib.parse.urlencode({"cab": int(cab_idx or 0), "days": max(1, _safe_int(days, 7))})
    return _request_json(f"{base}/api/cabinet/energy_history?{query}")


def send_remote_cabinet_channel(cab_idx, channel, is_on):
    base = get_cabinet_gateway_base()
    if not base:
        raise RuntimeError("cabinet gateway disabled")
    clear_remote_cabinet_status_cache(cab_idx)
    result = _request_json(
        f"{base}/api/cabinet/set",
        method="POST",
        payload={"cab": int(cab_idx or 0), "ch": int(channel or 0), "on": bool(is_on)},
        timeout=max(get_cabinet_gateway_timeout(), 6),
    )
    status = (result or {}).get("status") if isinstance(result, dict) else None
    if isinstance(status, dict):
        _store_remote_cabinet_status_cache(base, cab_idx, status)
    else:
        clear_remote_cabinet_status_cache(cab_idx)
    return result


def send_remote_cabinet_onekey(cab_idx, action):
    base = get_cabinet_gateway_base()
    if not base:
        raise RuntimeError("cabinet gateway disabled")
    normalized = str(action or "").strip().lower()
    if normalized not in {"start", "stop"}:
        raise ValueError("unsupported cabinet action")
    clear_remote_cabinet_status_cache(cab_idx)
    result = _request_json(
        f"{base}/api/cabinet/onekey",
        method="POST",
        payload={"cab": int(cab_idx or 0), "action": normalized},
        timeout=max(get_cabinet_gateway_timeout(), 8),
    )
    status = (result or {}).get("status") if isinstance(result, dict) else None
    if isinstance(status, dict):
        _store_remote_cabinet_status_cache(base, cab_idx, status)
    else:
        clear_remote_cabinet_status_cache(cab_idx)
    return result


def push_remote_cabinet_config(payload):
    base = get_cabinet_gateway_base()
    if not base:
        return {"ok": 0, "msg": "cabinet_gateway_disabled"}
    return _request_json(
        f"{base}/api/cabinet/config/sync",
        method="POST",
        payload=payload,
        timeout=max(get_cabinet_gateway_timeout(), 10),
    )
