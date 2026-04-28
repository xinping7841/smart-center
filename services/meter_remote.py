import json
import urllib.parse
import urllib.request
from urllib.error import URLError

from config import CONFIG

REMOTE_METER_TIMEOUT_DEFAULT_SEC = 15
REMOTE_METER_TIMEOUT_MIN_SEC = 8


def safe_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def get_remote_meter_service_base():
    meter_statistics = CONFIG.get("meter_statistics", {}) or {}
    if not bool(meter_statistics.get("remote_service_enabled", False)):
        return ""
    return str(meter_statistics.get("remote_service_url", "") or "").strip().rstrip("/")


def get_remote_meter_timeout():
    meter_statistics = CONFIG.get("meter_statistics", {}) or {}
    try:
        raw_timeout = meter_statistics.get(
            "remote_service_timeout_sec",
            REMOTE_METER_TIMEOUT_DEFAULT_SEC,
        )
        return max(
            REMOTE_METER_TIMEOUT_MIN_SEC,
            min(int(raw_timeout or REMOTE_METER_TIMEOUT_DEFAULT_SEC), 120),
        )
    except Exception:
        return REMOTE_METER_TIMEOUT_DEFAULT_SEC


def get_remote_meter_service_mode():
    meter_statistics = CONFIG.get("meter_statistics", {}) or {}
    mode = str(meter_statistics.get("remote_service_mode", "remote_overlay_local") or "remote_overlay_local").strip().lower()
    allowed = {"remote_only", "local_only", "remote_overlay_local", "local_overlay_remote"}
    return mode if mode in allowed else "remote_overlay_local"


def fetch_remote_meter_payload(target_source_key="total", period="day", days=7):
    base = get_remote_meter_service_base()
    if not base:
        return None
    query = urllib.parse.urlencode({
        "target": target_source_key or "total",
        "period": period or "day",
        "days": int(days or 7),
    })
    url = f"{base}/api/meters?{query}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=get_remote_meter_timeout()) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_remote_meter_health():
    base = get_remote_meter_service_base()
    if not base:
        return {"ok": 0, "msg": "未启用远程电表服务", "base": ""}
    url = f"{base}/api/health"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=max(get_remote_meter_timeout(), 3)) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return {"ok": 1, "base": base, "health": payload}
    except URLError as exc:
        return {"ok": 0, "base": base, "msg": str(exc)}
    except Exception as exc:
        return {"ok": 0, "base": base, "msg": str(exc)}


def push_remote_meter_config(payload):
    base = get_remote_meter_service_base()
    if not base:
        return {"ok": 0, "msg": "未启用远程电表服务"}
    url = f"{base}/api/config/sync"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=max(get_remote_meter_timeout(), 8)) as resp:
        return json.loads(resp.read().decode("utf-8"))


def normalize_meter_source_key(value):
    text = str(value or "").strip()
    if text.startswith("cabinet_meter_"):
        suffix = text.split("_")[-1]
        if suffix.isdigit():
            return f"cabinet:{suffix}"
    return text


def index_meter_rows(rows):
    indexed = {}
    for row in rows or []:
        source_key = str(row.get("source_key") or "").strip()
        meter_id = str(row.get("id") or row.get("meter_id") or "").strip()
        if source_key:
            indexed[source_key] = row
        if meter_id:
            indexed[meter_id] = row
    return indexed


def is_remote_payload_unstable(remote_payload, local_payload):
    if not isinstance(remote_payload, dict):
        return True
    remote_rows = list(remote_payload.get("meters", []) or [])
    if not remote_rows:
        return True
    local_rows = list((local_payload or {}).get("meters", []) or [])
    remote_total = len(remote_rows)
    remote_offline = sum(1 for row in remote_rows if not bool(row.get("online", False)))
    remote_degraded = sum(
        1
        for row in remote_rows
        if bool(row.get("_degraded", False)) or bool(row.get("_using_cached_fallback", False))
    )
    local_online = sum(1 for row in local_rows if bool(row.get("online", False)))
    remote_online = sum(1 for row in remote_rows if bool(row.get("online", False)))
    offline_ratio = (remote_offline / remote_total) if remote_total else 1.0
    degraded_ratio = (remote_degraded / remote_total) if remote_total else 1.0
    if remote_online <= 0 and local_online > 0:
        return True
    if remote_total >= 4 and remote_offline >= 2 and offline_ratio >= 0.25:
        return True
    if remote_total >= 4 and remote_degraded >= 3 and degraded_ratio >= 0.4:
        return True
    return False


def should_overlay_with_candidate(base_row, candidate_row):
    if not isinstance(candidate_row, dict):
        return False
    if not bool(candidate_row.get("visible_in_meter_center", True)):
        return False
    candidate_online = bool(candidate_row.get("online", False))
    candidate_degraded = bool(candidate_row.get("_degraded", False)) or bool(candidate_row.get("_using_cached_fallback", False))
    candidate_power = safe_float(candidate_row.get("realtime_power"), 0.0)
    candidate_energy = safe_float(candidate_row.get("electric_energy"), 0.0)
    candidate_has_usable_data = candidate_power > 0 or candidate_energy > 0
    if not candidate_online and not (candidate_degraded and candidate_has_usable_data):
        return False
    if not isinstance(base_row, dict):
        return True
    if not bool(base_row.get("online", False)):
        return True
    base_power = safe_float(base_row.get("realtime_power"), 0.0)
    base_energy = safe_float(base_row.get("electric_energy"), 0.0)
    if base_power <= 0 and candidate_power > 0:
        return True
    if base_energy <= 0 and candidate_energy > 0:
        return True
    return False


def stabilize_remote_meter_rows(rows):
    stabilized = []
    for row in rows or []:
        item = dict(row or {})
        degraded = bool(item.get("_degraded", False)) or bool(item.get("_using_cached_fallback", False))
        has_usable_data = (
            safe_float(item.get("electric_energy"), 0.0) > 0
            or safe_float(item.get("realtime_power"), 0.0) > 0
            or safe_float(item.get("voltage_a"), 0.0) > 0
            or safe_float(item.get("voltage_b"), 0.0) > 0
            or safe_float(item.get("voltage_c"), 0.0) > 0
        )
        if degraded and has_usable_data:
            item["online"] = True
        stabilized.append(item)
    return stabilized
