# AI_MODULE: node_red_gateway_api
# AI_PURPOSE: Proxy unified Node-RED device control/status and receive pushed device state.
# AI_BOUNDARY: Node-RED owns protocol inference; this module normalizes transport and display state.
# AI_DATA_FLOW: Browser/Node-RED -> /api/node-red/* -> Node-RED HTTP endpoints / in-memory cache.
# AI_RUNTIME: Protocol Control page, future HVAC/projector/light integrations.
# AI_RISK: Medium-high; control calls can operate real devices through Node-RED.
# AI_COMPAT: Keep /api/node-red/device-state, /api/node-red/device/<id>/status/control stable.

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import os
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Blueprint, jsonify, request

from audit import log_audit_event
from auth.decorators import require_permission
from auth.operation_lock import acquire_operation_lock, release_operation_lock
from auth.session import get_current_user
from data_logger import add_log
from event_logger import record_event

bp = Blueprint("node_red", __name__)

NODE_RED_BASE_URL = os.environ.get("SMART_CENTER_NODE_RED_URL", "http://192.168.50.121:1880").rstrip("/")
HTTP_TIMEOUT_SEC = float(os.environ.get("SMART_CENTER_NODE_RED_TIMEOUT_SEC", "5"))
PUSH_TOKEN = os.environ.get("SMART_CENTER_NODE_RED_PUSH_TOKEN", "").strip()
CONTROL_COOLDOWN_SEC = float(os.environ.get("SMART_CENTER_NODE_RED_CONTROL_COOLDOWN_SEC", "0"))
CONTROL_INFLIGHT_TTL_SEC = max(HTTP_TIMEOUT_SEC * 2 + 3.0, 5.0)

DEVICE_REGISTRY = {
    "courtyard_light": {
        "device_id": "courtyard_light",
        "device_name": "\u5ead\u9662\u706f",
        "device_type": "rf_light",
        "status_path": "/rf/courtyard/status",
        "control_path": "/rf/courtyard/control",
        "capabilities": ["on", "off", "status", "push_state", "health.serial"],
        "sort": 10,
        "single_toggle": True,
        "control_cooldown_sec": 0,
    },
    "hall1_projector": {
        "device_id": "hall1_projector",
        "device_name": "1\u53f7\u5385\u6295\u5f71\u673a",
        "device_type": "projector_group",
        "status_path": "/projector/hall1/status",
        "control_path": "/projector/hall1/control",
        "capabilities": ["on", "off", "status", "push_state", "protect", "metrics.current", "health.collector"],
        "sort": 20,
        "single_toggle": False,
    },
    "hall1_hvac": {
        "device_id": "hall1_hvac",
        "device_name": "1\u53f7\u5385\u7a7a\u8c03",
        "device_type": "hvac_group",
        "status_path": "/device/hall1_hvac/status",
        "control_path": "/device/hall1_hvac/control",
        "capabilities": ["on", "off", "status", "push_state", "protect"],
        "sort": 30,
        "single_toggle": False,
    },
    "hall1_wall_socket": {
        "device_id": "hall1_wall_socket",
        "device_name": "1\u53f7\u5385\u5899\u63d2",
        "device_type": "relay_socket",
        "status_path": "/device/hall1_wall_socket/status",
        "control_path": "/device/hall1_wall_socket/control",
        "capabilities": ["on", "off", "status", "push_state"],
        "sort": 40,
        "single_toggle": True,
    },
    "hall1_lighting": {
        "device_id": "hall1_lighting",
        "device_name": "1\u53f7\u5385\u7167\u660e",
        "device_type": "lighting_group",
        "status_path": "/device/hall1_lighting/status",
        "control_path": "/device/hall1_lighting/control",
        "capabilities": ["on", "off", "status", "push_state"],
        "sort": 50,
        "single_toggle": True,
    },
}

STATE_CACHE = {}
CONTROL_COOLDOWNS = {}
CONTROL_IN_PROGRESS = {}
CONTROL_IN_PROGRESS_LOCK = threading.Lock()

STATUS_TEXT = {
    "on": "\u4eae",
    "off": "\u6697",
    "starting": "\u5f00\u673a\u4e2d",
    "stopping": "\u5173\u673a\u4e2d",
    "pending_ack": "\u6267\u884c\u4e2d",
    "partial": "\u90e8\u5206\u5f00\u542f",
    "unknown": "\u672a\u77e5",
    "error": "\u5f02\u5e38",
    "offline": "\u79bb\u7ebf",
}


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _node_red_request(path, method="GET", payload=None):
    url = f"{NODE_RED_BASE_URL}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            try:
                body = json.loads(text) if text else {}
            except Exception:
                body = {"raw": text}
            return int(resp.status), body
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else {}
        except Exception:
            body = {"raw": raw}
        return int(exc.code), body
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(str(exc)) from exc


def _device_meta(device_id):
    return deepcopy(DEVICE_REGISTRY.get(str(device_id) or "") or {})


def _cooldown_seconds(meta):
    try:
        return max(float(meta.get("control_cooldown_sec", CONTROL_COOLDOWN_SEC) or 0), 0.0)
    except Exception:
        return CONTROL_COOLDOWN_SEC


def _cooldown_key(device_id):
    return str(device_id or "").strip()


def _cooldown_remaining(device_id, meta=None, now_ts=None):
    meta = meta or _device_meta(device_id)
    cooldown_sec = _cooldown_seconds(meta)
    if cooldown_sec <= 0:
        return 0.0
    now_ts = float(now_ts or time.monotonic())
    last_ts = float(CONTROL_COOLDOWNS.get(_cooldown_key(device_id), 0.0) or 0.0)
    return max(cooldown_sec - (now_ts - last_ts), 0.0)


def _mark_control_cooldown(device_id, now_ts=None):
    CONTROL_COOLDOWNS[_cooldown_key(device_id)] = float(now_ts or time.monotonic())


def _control_inflight_remaining(device_id, now_ts=None):
    key = _cooldown_key(device_id)
    now_ts = float(now_ts or time.monotonic())
    with CONTROL_IN_PROGRESS_LOCK:
        current = CONTROL_IN_PROGRESS.get(key) or {}
        expires_at = float(current.get("expires_at", 0.0) or 0.0)
        if expires_at <= now_ts:
            CONTROL_IN_PROGRESS.pop(key, None)
            return 0.0
        return max(expires_at - now_ts, 0.0)


def _begin_control_inflight(device_id, owner="", action=""):
    key = _cooldown_key(device_id)
    now_ts = time.monotonic()
    with CONTROL_IN_PROGRESS_LOCK:
        current = CONTROL_IN_PROGRESS.get(key) or {}
        expires_at = float(current.get("expires_at", 0.0) or 0.0)
        if expires_at > now_ts:
            current = deepcopy(current)
            current["remaining_sec"] = round(expires_at - now_ts, 1)
            return False, current
        CONTROL_IN_PROGRESS[key] = {
            "owner": str(owner or ""),
            "action": str(action or ""),
            "started_at": now_ts,
            "expires_at": now_ts + CONTROL_INFLIGHT_TTL_SEC,
        }
        return True, deepcopy(CONTROL_IN_PROGRESS[key])


def _finish_control_inflight(device_id):
    with CONTROL_IN_PROGRESS_LOCK:
        CONTROL_IN_PROGRESS.pop(_cooldown_key(device_id), None)


def _extract_status(payload, state):
    status = payload.get("status") or state.get("status")
    power = payload.get("power")
    if not status and isinstance(power, dict):
        status = power.get("status")
    return str(status or "unknown").strip().lower() or "unknown"


def _normalize_device_payload(device_id, payload, meta=None, transport_error="", include_control_pending=True):
    meta = meta or _device_meta(device_id)
    payload = payload if isinstance(payload, dict) else {}
    health = payload.get("health") if isinstance(payload.get("health"), dict) else {}
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    status = _extract_status(payload, state)
    alarm = bool(health.get("alarm", False))
    health_status = str(health.get("status") or "ok").strip().lower() or "ok"
    online = payload.get("online")
    if online is None:
        online = not alarm and not transport_error
    if transport_error:
        online = False
        alarm = True
        health_status = "node_red_unreachable"
        health = dict(health)
        health.update({"status": health_status, "alarm": True, "message": transport_error})
        status = "unknown"
    display_status = "error" if alarm or (health_status and health_status != "ok") else (status if online else "offline")
    normalized = {
        "source": payload.get("source") or "node-red",
        "gateway": payload.get("gateway") or "192.168.50.121",
        "device_id": payload.get("device_id") or meta.get("device_id") or device_id,
        "device_name": payload.get("device_name") or payload.get("name") or meta.get("device_name") or device_id,
        "device_type": payload.get("device_type") or meta.get("device_type") or "node_red_device",
        "online": bool(online),
        "status": status,
        "display_status": display_status,
        "display_text": STATUS_TEXT.get(display_status) or STATUS_TEXT.get(status) or status or "\u672a\u77e5",
        "health": health or {"status": health_status, "alarm": alarm, "message": "normal"},
        "state": state,
        "metrics": metrics,
        "capabilities": payload.get("capabilities") if isinstance(payload.get("capabilities"), list) else meta.get("capabilities", ["status"]),
        "updated_at": payload.get("updated_at") or state.get("updated_at") or _now_iso(),
        "raw": payload,
        "meta": {k: v for k, v in meta.items() if k not in {"status_path", "control_path"}},
    }
    normalized["control_cooldown_sec"] = _cooldown_seconds(meta)
    normalized["cooldown_remaining_sec"] = round(_cooldown_remaining(device_id, meta=meta), 1)
    pending_remaining = _control_inflight_remaining(device_id) if include_control_pending else 0.0
    normalized["control_pending"] = pending_remaining > 0
    normalized["control_pending_remaining_sec"] = round(pending_remaining, 1)
    if isinstance(payload.get("power"), dict):
        normalized["power"] = payload.get("power")
    return normalized


def get_node_red_device_status(device_id, include_control_pending=True):
    meta = _device_meta(device_id)
    if not meta:
        raise KeyError(device_id)
    try:
        code, payload = _node_red_request(meta["status_path"], "GET")
        if code >= 400:
            raise RuntimeError(f"HTTP {code}: {payload}")
        normalized = _normalize_device_payload(device_id, payload, meta=meta, include_control_pending=include_control_pending)
    except Exception as exc:
        cached = deepcopy(STATE_CACHE.get(device_id) or {})
        normalized = _normalize_device_payload(
            device_id,
            cached,
            meta=meta,
            transport_error=f"Node-RED status endpoint not ready: {exc}",
            include_control_pending=include_control_pending,
        )
    STATE_CACHE[device_id] = normalized
    return normalized


def control_node_red_device(device_id, action, source="central_control"):
    meta = _device_meta(device_id)
    if not meta:
        raise KeyError(device_id)
    normalized_action = str(action or "").strip().lower()
    if normalized_action not in {"on", "off", "toggle", "status"}:
        raise ValueError("action must be on/off/toggle/status")
    if normalized_action == "status":
        return True, get_node_red_device_status(device_id), "node_red"
    if normalized_action == "toggle":
        current = get_node_red_device_status(device_id)
        normalized_action = "off" if str(current.get("status") or "").lower() == "on" else "on"
    remaining = _cooldown_remaining(device_id, meta=meta)
    if remaining > 0:
        raise RuntimeError(f"\u5f00\u5173\u4fdd\u62a4\u51b7\u5374\u4e2d\uff0c\u8bf7 {max(1, int(round(remaining)))} \u79d2\u540e\u518d\u8bd5")
    inflight_started, inflight_info = _begin_control_inflight(device_id, owner=source, action=normalized_action)
    if not inflight_started:
        retry_sec = max(1, int(round(float(inflight_info.get("remaining_sec", 1) or 1))))
        raise RuntimeError(f"\u8bbe\u5907\u6307\u4ee4\u6267\u884c\u4e2d\uff0c\u7b49\u5f85\u72b6\u6001\u56de\u8bfb\u5b8c\u6210\uff0c\u8bf7 {retry_sec} \u79d2\u540e\u518d\u8bd5")
    finish_inflight = False
    try:
        code, result = _node_red_request(meta["control_path"], "POST", {"action": normalized_action, "source": source})
        if code >= 400:
            raise RuntimeError(f"HTTP {code}: {result}")
        success = bool(result.get("success", True)) if isinstance(result, dict) else True
        if success and _cooldown_seconds(meta) > 0:
            _mark_control_cooldown(device_id)
        if success:
            status_code, status_payload = _node_red_request(meta["status_path"], "GET")
            if status_code >= 400:
                raise RuntimeError(f"status readback HTTP {status_code}: {status_payload}")
            normalized = _normalize_device_payload(device_id, status_payload, meta=meta, include_control_pending=False)
            finish_inflight = True
        else:
            normalized = _normalize_device_payload(
                device_id,
                result if isinstance(result, dict) else {},
                meta=meta,
                include_control_pending=False,
            )
            finish_inflight = True
        STATE_CACHE[device_id] = normalized
        return success, normalized, "node_red"
    finally:
        if finish_inflight:
            _finish_control_inflight(device_id)


def _validate_push_token():
    if not PUSH_TOKEN:
        return True
    provided = request.headers.get("X-Node-Red-Token") or request.args.get("token") or ""
    return str(provided).strip() == PUSH_TOKEN


@bp.route("/api/node-red/devices")
@require_permission("control_center.view")
def api_node_red_devices():
    refresh = str(request.args.get("refresh") or "1").lower() not in {"0", "false", "no"}
    devices = []
    include_unavailable = str(request.args.get("include_unavailable") or "0").lower() in {"1", "true", "yes"}
    allowed_types = {"rf_light", "lighting", "light"}
    for device_id, meta in sorted(DEVICE_REGISTRY.items(), key=lambda item: int(item[1].get("sort", 999))):
        if str(meta.get("device_type") or "") not in allowed_types:
            continue
        if refresh:
            device = get_node_red_device_status(device_id)
        else:
            device = deepcopy(STATE_CACHE.get(device_id)) or _normalize_device_payload(device_id, {}, meta=meta)
        health_status = str((device.get("health") or {}).get("status") or "")
        if include_unavailable or device.get("online") or health_status != "node_red_unreachable":
            devices.append(device)
    return jsonify({"ok": 1, "devices": devices, "gateway": NODE_RED_BASE_URL})


@bp.route("/api/node-red/device/<device_id>/status")
@require_permission("control_center.view")
def api_node_red_device_status(device_id):
    if device_id not in DEVICE_REGISTRY:
        return jsonify({"ok": 0, "msg": f"unknown Node-RED device: {device_id}"}), 404
    return jsonify({"ok": 1, "device": get_node_red_device_status(device_id)})


@bp.route("/api/node-red/device/<device_id>/control", methods=["POST"])
@require_permission("control_center.control")
def api_node_red_device_control(device_id):
    meta = _device_meta(device_id)
    if not meta:
        return jsonify({"ok": 0, "success": False, "msg": f"unknown Node-RED device: {device_id}"}), 404
    payload = request.json or {}
    action = str(payload.get("action") or "").strip().lower()
    if action not in {"on", "off", "toggle", "status"}:
        return jsonify({"ok": 0, "success": False, "msg": "action must be on/off/toggle/status"}), 400
    if action == "toggle":
        current = get_node_red_device_status(device_id)
        action = "off" if str(current.get("status") or "").lower() == "on" else "on"
    if action == "status":
        return jsonify({"ok": 1, "success": True, "device": get_node_red_device_status(device_id)})

    current_user = get_current_user()
    lock_key = f"node-red:{device_id}"
    locked, lock_info = acquire_operation_lock(lock_key, current_user.username, "node_red_control", timeout_sec=3.0)
    if not locked:
        return jsonify({"ok": 0, "success": False, "error": "device_busy", "msg": f"device is being operated by {lock_info.get('owner')}, retry later"}), 409
    try:
        remaining = _cooldown_remaining(device_id, meta=meta)
        if remaining > 0:
            seconds = max(1, int(round(remaining)))
            return jsonify({
                "ok": 0,
                "success": False,
                "error": "cooldown",
                "msg": f"\u5f00\u5173\u4fdd\u62a4\u51b7\u5374\u4e2d\uff0c\u8bf7 {seconds} \u79d2\u540e\u518d\u8bd5",
                "retry_after_sec": seconds,
                "device": _normalize_device_payload(device_id, deepcopy(STATE_CACHE.get(device_id) or {}), meta=meta),
            }), 429
        inflight_started, inflight_info = _begin_control_inflight(device_id, owner=current_user.username, action=action)
        if not inflight_started:
            retry_sec = max(1, int(round(float(inflight_info.get("remaining_sec", 1) or 1))))
            return jsonify({
                "ok": 0,
                "success": False,
                "error": "device_busy",
                "msg": "\u8bbe\u5907\u6307\u4ee4\u6267\u884c\u4e2d\uff0c\u7b49\u5f85\u72b6\u6001\u56de\u8bfb\u5b8c\u6210",
                "retry_after_sec": retry_sec,
                "device": _normalize_device_payload(device_id, deepcopy(STATE_CACHE.get(device_id) or {}), meta=meta),
            }), 409
        finish_inflight = False
        try:
            code, result = _node_red_request(meta["control_path"], "POST", {"action": action, "source": "central_control"})
            if code >= 400:
                raise RuntimeError(f"HTTP {code}: {result}")
            success = bool(result.get("success", True)) if isinstance(result, dict) else True
            if success and _cooldown_seconds(meta) > 0:
                _mark_control_cooldown(device_id)
            if success:
                status_code, status_payload = _node_red_request(meta["status_path"], "GET")
                if status_code >= 400:
                    raise RuntimeError(f"status readback HTTP {status_code}: {status_payload}")
                normalized = _normalize_device_payload(device_id, status_payload, meta=meta, include_control_pending=False)
                finish_inflight = True
            else:
                normalized = _normalize_device_payload(
                    device_id,
                    result if isinstance(result, dict) else {},
                    meta=meta,
                    include_control_pending=False,
                )
                finish_inflight = True
        finally:
            if finish_inflight:
                _finish_control_inflight(device_id)
        STATE_CACHE[device_id] = normalized
        add_log(-1, f"[Node-RED] {meta.get('device_name')} -> {action} {'ok' if success else 'failed'}")
        record_event(
            category="control_center",
            event_type="command",
            source="api",
            device_id=device_id,
            device_name=meta.get("device_name") or device_id,
            action=action,
            result="success" if success else "failed",
            message=f"[Node-RED] {meta.get('device_name') or device_id} -> {action}",
            raw={"response": result, "http_status": code},
        )
        log_audit_event("node_red.control", target=device_id, detail={"action": action, "result": result}, status="success" if success else "error")
        return jsonify({"ok": 1 if success else 0, "success": success, "action": action, "response": result, "device": normalized}), (200 if success else max(400, code))
    except Exception as exc:
        add_log(-1, f"[Node-RED] {meta.get('device_name')} -> {action} failed: {exc}")
        log_audit_event("node_red.control", target=device_id, detail={"action": action, "error": str(exc)}, status="error")
        return jsonify({"ok": 0, "success": False, "msg": str(exc), "device": _normalize_device_payload(device_id, {}, meta=meta, transport_error=str(exc))}), 502
    finally:
        release_operation_lock(lock_key, current_user.username)


@bp.route("/api/node-red/device-state", methods=["POST"])
def api_node_red_device_state_push():
    if not _validate_push_token():
        return jsonify({"success": False, "ok": 0, "msg": "invalid token"}), 403
    payload = request.json or {}
    device_id = str(payload.get("device_id") or "").strip()
    if not device_id:
        return jsonify({"success": False, "ok": 0, "msg": "missing device_id"}), 400
    meta = _device_meta(device_id)
    normalized = _normalize_device_payload(device_id, payload, meta=meta or {"device_id": device_id})
    STATE_CACHE[device_id] = normalized
    add_log(-1, f"[Node-RED] state push {normalized.get('device_name')} -> {normalized.get('display_text')}")
    return jsonify({"success": True, "ok": 1, "device_id": device_id})
