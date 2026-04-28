import threading
import time
from copy import deepcopy
from datetime import datetime, timedelta

from . import modbus_core as mc
from .config_store import load_config, save_config
from .service import get_latest_rows, poll_once
from .storage import get_history_rows


_LOCKS = {}
_ACTION_LOGS = {}
_ACTION_LOGS_LOCK = threading.Lock()


def _safe_float(value, default=0.0):
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value, default=0):
    try:
        if value in (None, ""):
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _cabinet_lock(cab_idx):
    lock = _LOCKS.get(int(cab_idx))
    if lock is None:
        lock = threading.Lock()
        _LOCKS[int(cab_idx)] = lock
    return lock


def _add_log(cab_idx, operation, status="ok", detail=None):
    entry = {
        "time": datetime.now().isoformat(),
        "cab_idx": int(cab_idx),
        "operation": str(operation or ""),
        "status": str(status or "ok"),
        "detail": detail if isinstance(detail, dict) else {},
    }
    with _ACTION_LOGS_LOCK:
        items = _ACTION_LOGS.setdefault(int(cab_idx), [])
        items.insert(0, entry)
        del items[120:]
    return entry


def get_action_logs(cab_idx=None, keep_seconds=86400 * 30):
    cutoff = datetime.now() - timedelta(seconds=max(int(keep_seconds or 0), 0))
    with _ACTION_LOGS_LOCK:
        if cab_idx is None:
            merged = []
            for items in _ACTION_LOGS.values():
                merged.extend(items)
        else:
            merged = list(_ACTION_LOGS.get(int(cab_idx), []))
    filtered = []
    for item in merged:
        try:
            if datetime.fromisoformat(str(item.get("time") or "")) >= cutoff:
                filtered.append(dict(item))
        except Exception:
            filtered.append(dict(item))
    filtered.sort(key=lambda item: str(item.get("time") or ""), reverse=True)
    return filtered


def _display_name(cfg, cab_idx):
    return cfg.get("meter_display_name") or cfg.get("cabinet_name") or f"电柜{int(cab_idx) + 1}"


def _base_status(cab_idx, cfg):
    count = max(1, _safe_int(cfg.get("channel_count", 8), 8))
    name = _display_name(cfg, cab_idx)
    return {
        "cab_idx": int(cab_idx),
        "cabinet_name": name,
        "display_name": name,
        "comm_status": False,
        "online": False,
        "channels_1_4": [False] * count,
        "channel_count": count,
        "channel_on_count": 0,
        "cabinet_temp": 0.0,
        "cabinet_humidity": 0.0,
        "voltage_a": 0.0,
        "voltage_b": 0.0,
        "voltage_c": 0.0,
        "current_a": 0.0,
        "current_b": 0.0,
        "current_c": 0.0,
        "electric_energy": 0.0,
        "daily_energy": 0.0,
        "monthly_energy": 0.0,
        "realtime_power": 0.0,
        "work_mode": "未知",
        "updated_at": "",
        "error": "",
        "gateway_source": "meter_service_cache",
    }


def _find_cached_cabinet_row(cab_idx):
    meter_id = f"cabinet_meter_{int(cab_idx)}"
    source_key = f"cabinet:{int(cab_idx)}"
    for row in get_latest_rows():
        if (
            str(row.get("id") or "") == meter_id
            or str(row.get("meter_id") or "") == meter_id
            or str(row.get("source_key") or "") == source_key
        ):
            return deepcopy(row)
    return None


def _normalize_channel_bits(bits, count):
    items = list(bits or [])[:count]
    if len(items) < count:
        items.extend([False] * (count - len(items)))
    return [bool(item) for item in items]


def _resolve_work_mode(mode_val, cab_cfg):
    ui_text = cab_cfg.get("ui_text", {}) or {}
    if mode_val == 0:
        return ui_text.get("label_mode_manual", "手动")
    if mode_val == 1:
        return ui_text.get("label_mode_remote", "远程")
    if mode_val in (2, 3):
        return ui_text.get("label_mode_external", "外控")
    return ui_text.get("label_mode_unknown", "未知")


def _read_live_cabinet_runtime(cab_cfg):
    client = None
    try:
        plc = str(cab_cfg.get("plc_type", "AV-100") or "AV-100")
        channel_count = max(_safe_int(cab_cfg.get("channel_count", 8), 8), 1)
        client = mc.make_client(
            cab_cfg.get("ip", ""),
            int(cab_cfg.get("port", 502) or 502),
            int(cab_cfg.get("station_id", 1) or 1),
            timeout=max(float(cab_cfg.get("timeout_sec", 1.5) or 1.5), 0.5),
            protocol=plc,
        )
        if not client.connect():
            return None

        runtime = {
            "online": True,
            "comm_status": True,
            "gateway_source": "meter_service_cache+plc_live",
        }

        if "Smart" in plc:
            p_mode = client.send(0x03, (0x03).to_bytes(2, "big") + (1).to_bytes(2, "big"))
            time.sleep(0.05)
            p_relay = client.send(0x03, (0x05).to_bytes(2, "big") + channel_count.to_bytes(2, "big"))
            bits = mc.parse_pdu_relay(p_relay, channel_count) if p_relay else None
            if bits is not None:
                runtime["channels_1_4"] = _normalize_channel_bits(bits, channel_count)
            if p_mode:
                runtime["work_mode"] = _resolve_work_mode(p_mode[-1], cab_cfg)
        else:
            p_relay = client.send(0x01, (0).to_bytes(2, "big") + channel_count.to_bytes(2, "big"))
            bits = mc.parse_pdu_relay(p_relay, channel_count) if p_relay else None
            if bits is not None:
                runtime["channels_1_4"] = _normalize_channel_bits(bits, channel_count)
            p_mode = client.send(0x03, (0x00A2).to_bytes(2, "big") + (1).to_bytes(2, "big"))
            if p_mode:
                runtime["work_mode"] = _resolve_work_mode(p_mode[-1], cab_cfg)

        if "channels_1_4" in runtime:
            runtime["channel_on_count"] = sum(1 for state in runtime["channels_1_4"] if state)
        return runtime
    except Exception as exc:
        return {
            "online": False,
            "comm_status": False,
            "gateway_source": "meter_service_cache+plc_live_error",
            "runtime_error": str(exc),
        }
    finally:
        try:
            if client:
                client.close()
        except Exception:
            pass


def poll_cabinet_status(cab_idx, force=False):
    cfg = list(load_config().get("cabinets", []))
    cab_idx = int(cab_idx or 0)
    if cab_idx < 0 or cab_idx >= len(cfg):
        raise IndexError("cabinet not found")
    cab_cfg = cfg[cab_idx]
    if force:
        poll_once()

    row = _find_cached_cabinet_row(cab_idx)
    if row:
        row["comm_status"] = bool(row.get("online", False))
        row["gateway_source"] = "meter_service_cache"
        row["cab_idx"] = cab_idx
        row["channel_count"] = max(_safe_int(cab_cfg.get("channel_count", 8), 8), 1)
        row["channels_1_4"] = _normalize_channel_bits(row.get("channels_1_4"), row["channel_count"])
        row["channel_on_count"] = sum(1 for state in row["channels_1_4"] if state)

        live_runtime = _read_live_cabinet_runtime(cab_cfg)
        if isinstance(live_runtime, dict):
            if live_runtime.get("channels_1_4") is not None:
                row["channels_1_4"] = _normalize_channel_bits(live_runtime.get("channels_1_4"), row["channel_count"])
                row["channel_on_count"] = sum(1 for state in row["channels_1_4"] if state)
            if live_runtime.get("work_mode"):
                row["work_mode"] = live_runtime.get("work_mode")
            if live_runtime.get("gateway_source"):
                row["gateway_source"] = live_runtime.get("gateway_source")
            if live_runtime.get("comm_status") is not None:
                row["comm_status"] = bool(live_runtime.get("comm_status"))
                row["online"] = bool(live_runtime.get("online", row.get("online", False)))
            if live_runtime.get("runtime_error"):
                row["runtime_error"] = live_runtime.get("runtime_error")
        return row

    merged = _base_status(cab_idx, cab_cfg)
    live_runtime = _read_live_cabinet_runtime(cab_cfg)
    if isinstance(live_runtime, dict):
        merged.update({k: v for k, v in live_runtime.items() if v is not None})
        merged["channels_1_4"] = _normalize_channel_bits(merged.get("channels_1_4"), merged["channel_count"])
        merged["channel_on_count"] = sum(1 for state in merged["channels_1_4"] if state)
        if merged.get("online"):
            merged["updated_at"] = datetime.now().isoformat()
            return merged
    merged["error"] = merged.get("runtime_error") or "暂无缓存数据"
    merged["updated_at"] = datetime.now().isoformat()
    return merged


def get_cached_or_poll_status(cab_idx, force=False):
    return poll_cabinet_status(cab_idx, force=force)


def set_channel_state(cab_idx, channel, is_on):
    cfg = list(load_config().get("cabinets", []))
    cab_idx = int(cab_idx or 0)
    channel = int(channel or 0)
    if cab_idx < 0 or cab_idx >= len(cfg):
        raise IndexError("cabinet not found")
    if channel <= 0:
        raise ValueError("invalid channel")
    cab_cfg = cfg[cab_idx]
    lock = _cabinet_lock(cab_idx)
    with lock:
        client = None
        try:
            client = mc.make_client(
                cab_cfg.get("ip", ""),
                int(cab_cfg.get("port", 502) or 502),
                int(cab_cfg.get("station_id", 1) or 1),
                timeout=max(float(cab_cfg.get("timeout_sec", 1.5) or 1.5), 0.5),
                protocol=str(cab_cfg.get("plc_type", "AV-100") or "AV-100"),
            )
            if not client.connect():
                raise RuntimeError("连接失败")
            if "Smart" in str(cab_cfg.get("plc_type", "")):
                reg = 0x05 + channel - 1
                payload = reg.to_bytes(2, "big") + (b"\x00\x01" if bool(is_on) else b"\x00\x00")
                ok = client.send(0x06, payload) is not None
            else:
                reg = 0x03EB + (channel - 1) * 2 if bool(is_on) else 0x03EC + (channel - 1) * 2
                ok = client.send(0x05, reg.to_bytes(2, "big") + b"\xFF\x00") is not None
            if not ok:
                raise RuntimeError("控制失败")
            time.sleep(0.08)
            status = poll_cabinet_status(cab_idx, force=False)
            _add_log(cab_idx, f"通道 {channel} {'闭合' if bool(is_on) else '断开'}", status="ok", detail={"channel": channel, "on": bool(is_on)})
            return {"ok": 1, "status": status, "verified": False, "msg": "指令已下发，状态稍后自动刷新"}
        except Exception as exc:
            _add_log(cab_idx, f"通道 {channel} 控制失败", status="error", detail={"channel": channel, "on": bool(is_on), "error": str(exc)})
            return {"ok": 0, "msg": str(exc)}
        finally:
            try:
                if client:
                    client.close()
            except Exception:
                pass


def onekey_action(cab_idx, action):
    cfg = list(load_config().get("cabinets", []))
    cab_idx = int(cab_idx or 0)
    if cab_idx < 0 or cab_idx >= len(cfg):
        raise IndexError("cabinet not found")
    cab_cfg = cfg[cab_idx]
    plc = str(cab_cfg.get("plc_type", "AV-100") or "AV-100")
    normalized = str(action or "").strip().lower()
    if normalized not in {"start", "stop"}:
        raise ValueError("invalid action")
    lock = _cabinet_lock(cab_idx)
    with lock:
        client = None
        try:
            client = mc.make_client(
                cab_cfg.get("ip", ""),
                int(cab_cfg.get("port", 502) or 502),
                int(cab_cfg.get("station_id", 1) or 1),
                timeout=max(float(cab_cfg.get("timeout_sec", 1.5) or 1.5), 0.5),
                protocol=plc,
            )
            if not client.connect():
                raise RuntimeError("连接失败")
            if "Smart" in plc:
                payload = bytes([0x00, 0x00, 0x00, 0x01]) if normalized == "start" else bytes([0x00, 0x01, 0x00, 0x01])
                ok = client.send(0x06, payload) is not None
            else:
                payload = b"\x03\xE8\xFF\x00" if normalized == "start" else b"\x03\xE9\xFF\x00"
                ok = client.send(0x05, payload) is not None
            if not ok:
                raise RuntimeError("控制失败")
            time.sleep(0.08)
            status = poll_cabinet_status(cab_idx, force=False)
            _add_log(cab_idx, f"一键{'启动' if normalized == 'start' else '停止'}", status="ok")
            return {"ok": 1, "status": status, "verified": False, "msg": "指令已下发，状态稍后自动刷新"}
        except Exception as exc:
            _add_log(cab_idx, f"一键{normalized}失败", status="error", detail={"error": str(exc)})
            return {"ok": 0, "msg": str(exc)}
        finally:
            try:
                if client:
                    client.close()
            except Exception:
                pass


def get_cabinet_energy_history(cab_idx, days=7):
    cache_key = f"cabinet:{int(cab_idx or 0)}"
    current = get_cached_or_poll_status(cab_idx, force=False)
    return get_history_rows(cache_key, current_daily=_safe_float((current or {}).get("daily_energy"), 0.0), days=days)


def build_gateway_health():
    cfg = load_config()
    rows = []
    for cab_idx, cab in enumerate(cfg.get("cabinets", [])):
        current = get_cached_or_poll_status(cab_idx, force=False)
        rows.append(
            {
                "cab_idx": cab_idx,
                "name": _display_name(cab, cab_idx),
                "ip": cab.get("ip"),
                "port": cab.get("port"),
                "online": bool((current or {}).get("online", False)),
                "updated_at": (current or {}).get("updated_at"),
                "error": (current or {}).get("error", "") or (current or {}).get("runtime_error", ""),
            }
        )
    return {
        "ok": 1,
        "service": "cabinet_gateway",
        "cabinet_count": len(cfg.get("cabinets", [])),
        "gateway_enabled": True,
        "cabinets": rows,
    }


def sync_gateway_config(payload):
    cfg = load_config()
    next_cfg = deepcopy(cfg)
    if isinstance(payload, dict):
        if isinstance(payload.get("cabinets"), list):
            next_cfg["cabinets"] = payload.get("cabinets", [])
        meter_statistics = next_cfg.get("meter_statistics", {}) or {}
        incoming_ms = payload.get("meter_statistics", {}) or {}
        meter_statistics.update(incoming_ms)
        next_cfg["meter_statistics"] = meter_statistics
    return save_config(next_cfg)
