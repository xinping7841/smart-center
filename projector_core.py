import socket
import serial
import threading
import hashlib
import time
import traceback
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from paths import PROJECTOR_BRANDS_FILE, RUNTIME_DIR, ensure_parent_dir

BRANDS_FILE = str(PROJECTOR_BRANDS_FILE)

INFERRED_PROJECTOR_STATE_FILE = str(RUNTIME_DIR / "projector_inferred_state.json")
INFERRED_PROJECTOR_STATE_LOCK = threading.Lock()
INFERRED_PROJECTOR_METER_CACHE = {"expires_at": 0.0, "payload": {}}


def _utc_ts():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def _read_inferred_projector_state():
    try:
        with open(INFERRED_PROJECTOR_STATE_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _write_inferred_projector_state(state):
    from pathlib import Path
    ensure_parent_dir(Path(INFERRED_PROJECTOR_STATE_FILE))
    tmp_path = f"{INFERRED_PROJECTOR_STATE_FILE}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, INFERRED_PROJECTOR_STATE_FILE)


def _current_inferred_meter_power(cabinet_idx=0):
    meter = _read_remote_cabinet_meter(cabinet_idx)
    power_kw = meter.get("stable_realtime_power")
    if power_kw is None:
        power_kw = meter.get("effective_realtime_power")
    if power_kw is None:
        power_kw = meter.get("realtime_power")
    try:
        return float(power_kw), meter
    except Exception:
        return None, meter



def _normalize_projector_hex(value):
    return "".join(ch for ch in str(value or "").upper() if ch in "0123456789ABCDEF")


def _inferred_gateway_status(projector_cfg, timeout=1.8):
    url = str((projector_cfg or {}).get("inferred_gateway_status_url") or "").strip()
    if not url:
        return {}
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", "ignore"))
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _inferred_gateway_control(projector_cfg, action, dry_run=False, timeout=8.0):
    url = str((projector_cfg or {}).get("inferred_gateway_control_url") or "").strip()
    if not url:
        return None
    try:
        import urllib.request
        body = json.dumps({"action": action, "dry_run": bool(dry_run), "source": "smart-center"}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", "ignore"))
        return payload if isinstance(payload, dict) else {"success": False, "error": "invalid gateway response"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _merge_inferred_gateway_runtime(projector_cfg, runtime):
    gateway = _inferred_gateway_status(projector_cfg)
    command_state = gateway.get("command_state") if isinstance(gateway, dict) else None
    if not isinstance(command_state, dict):
        return runtime, gateway
    merged = dict(runtime or {})
    gateway_ts = _parse_iso_like_ts(command_state.get("last_command_at"))
    local_ts = _parse_iso_like_ts(merged.get("last_command_at"))
    if gateway_ts and (not local_ts or gateway_ts >= local_ts):
        for key in [
            "last_intent", "last_command_at", "last_command_ok", "last_command_payload",
            "last_response", "last_command_source", "updated_at"
        ]:
            if command_state.get(key) is not None:
                merged[key] = command_state.get(key)
        merged["gateway_command_state"] = command_state
    return merged, gateway

def _inferred_targets(projector_cfg):
    targets = (projector_cfg or {}).get("inferred_targets")
    if isinstance(targets, list) and targets:
        normalized = []
        for idx, item in enumerate(targets, start=1):
            if not isinstance(item, dict):
                continue
            ip = str(item.get("ip") or "").strip()
            if not ip:
                continue
            normalized.append({
                "id": str(item.get("id") or f"target_{idx}"),
                "name": str(item.get("name") or ip),
                "ip": ip,
                "port": int(item.get("port", (projector_cfg or {}).get("port", 502)) or 502),
            })
        if normalized:
            return normalized
    ip = str((projector_cfg or {}).get("ip") or "").strip()
    if not ip:
        return []
    return [{
        "id": str((projector_cfg or {}).get("id") or "target_1"),
        "name": str((projector_cfg or {}).get("name") or ip),
        "ip": ip,
        "port": int((projector_cfg or {}).get("port", 502) or 502),
    }]


def get_inferred_projector_command_baseline(projector_cfg):
    if str((projector_cfg or {}).get("control_type") or "") != "inferred_rs232":
        return None, {}
    cabinet_idx = int((projector_cfg or {}).get("inferred_cabinet_idx", 0) or 0)
    return _current_inferred_meter_power(cabinet_idx)


def get_inferred_projector_runtime(projector_id=None):
    with INFERRED_PROJECTOR_STATE_LOCK:
        state = _read_inferred_projector_state()
    if projector_id is None:
        return state
    return dict((state.get(str(projector_id)) or {}) if isinstance(state.get(str(projector_id)), dict) else {})


def record_inferred_projector_command(projector_cfg, command_config, success, response=None, baseline_kw=None, meter=None):
    if str((projector_cfg or {}).get("control_type") or "") != "inferred_rs232":
        return
    proj_id = str(projector_cfg.get("id") or "")
    if not proj_id:
        return
    command = command_config or {}
    payload = str(command.get("payload") or "").strip().upper()
    name = str(command.get("name") or command.get("id") or "").strip()
    intent = None
    on_payload = str(projector_cfg.get("inferred_power_on_payload") or "23 50 57 52 30 2C 31 21").strip().upper()
    off_payload = str(projector_cfg.get("inferred_power_off_payload") or "23 50 57 52 30 2C 30 21").strip().upper()
    if payload.replace(" ", "") == on_payload.replace(" ", "") or name in {"开机", "power_on"} or "开机" in name:
        intent = "on"
    elif payload.replace(" ", "") == off_payload.replace(" ", "") or name in {"关机", "power_off"} or "关机" in name:
        intent = "off"
    if not intent:
        return
    now = _utc_ts()
    if baseline_kw is None or meter is None:
        cabinet_idx = int(projector_cfg.get("inferred_cabinet_idx", 0) or 0)
        baseline_kw, meter = _current_inferred_meter_power(cabinet_idx)
    with INFERRED_PROJECTOR_STATE_LOCK:
        state = _read_inferred_projector_state()
        item = dict(state.get(proj_id) or {})
        item.update({
            "last_command_ok": bool(success),
            "last_command_payload": payload,
            "last_response": str(response or "")[:500],
            "command_meter_updated_at": meter.get("updated_at") if isinstance(meter, dict) else None,
            "name": projector_cfg.get("name") or proj_id,
            "ip": projector_cfg.get("ip"),
        })
        if success:
            item.update({
                "last_intent": intent,
                "last_command_at": now,
                "command_baseline_kw": baseline_kw,
            })
        else:
            item["last_failed_intent"] = intent
            item["last_failed_at"] = now
        state[proj_id] = item
        _write_inferred_projector_state(state)


def _parse_iso_like_ts(value):
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        from datetime import datetime
        normalized = text.replace("Z", "+00:00")
        if len(normalized) >= 5 and normalized[-5] in ["+", "-"] and normalized[-3] != ":":
            normalized = normalized[:-2] + ":" + normalized[-2:]
        return datetime.fromisoformat(normalized).timestamp()
    except Exception:
        return None


def _tcp_port_open(ip, port, timeout=1.2):
    try:
        with socket.create_connection((ip, int(port)), timeout=timeout):
            return True, ""
    except Exception as exc:
        return False, str(exc)


def _read_remote_cabinet_meter(cabinet_idx=0, timeout=2.0):
    now = time.time()
    cached = INFERRED_PROJECTOR_METER_CACHE.get("payload") or {}
    if now < float(INFERRED_PROJECTOR_METER_CACHE.get("expires_at") or 0.0) and cached:
        item = cached.get(cabinet_idx)
        if item is not None:
            return dict(item)
    url = os.environ.get("SMART_CENTER_REMOTE_METER_URL", "http://192.168.50.121:6901/api/diagnostics/meters")
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", "ignore"))
        cache_map = {}
        for item in payload.get("meters") or []:
            idx = item.get("cabinet_idx")
            if idx is None and str(item.get("id") or "").startswith("cabinet_meter_"):
                try:
                    idx = int(str(item.get("id")).replace("cabinet_meter_", ""))
                except Exception:
                    idx = None
            if idx is not None:
                try:
                    cache_map[int(idx)] = dict(item)
                except Exception:
                    pass
        INFERRED_PROJECTOR_METER_CACHE.update({"expires_at": now + 1.5, "payload": cache_map})
        if cabinet_idx in cache_map:
            return dict(cache_map[cabinet_idx])
    except Exception as exc:
        return {"online": False, "error": str(exc)}
    return {"online": False, "error": "cabinet meter not found"}


def infer_rs232_projector_status(projector_cfg):
    cfg = dict(projector_cfg or {})
    proj_id = str(cfg.get("id") or "")
    runtime = get_inferred_projector_runtime(proj_id)
    runtime, gateway_status = _merge_inferred_gateway_runtime(cfg, runtime)
    now = time.time()
    targets = _inferred_targets(cfg)
    target_status = []
    for target in targets:
        ok, err = _tcp_port_open(target["ip"], target.get("port", 502))
        target_status.append({
            "id": target.get("id"),
            "name": target.get("name"),
            "ip": target.get("ip"),
            "port": target.get("port", 502),
            "online": ok,
            "error": err,
        })
    if isinstance(gateway_status, dict) and gateway_status.get("targets"):
        gateway_targets = gateway_status.get("targets")
        if isinstance(gateway_targets, list):
            target_status = gateway_targets
    target_total = len(target_status)
    target_online = sum(1 for item in target_status if item.get("online"))
    tcp_online = bool(target_total and target_online == target_total)
    tcp_degraded = bool(target_total and 0 < target_online < target_total)
    tcp_error = "; ".join(f"{item.get('name') or item.get('ip')}:{item.get('error')}" for item in target_status if not item.get("online")) or "missing targets"
    cabinet_idx = int(cfg.get("inferred_cabinet_idx", 0) or 0)
    channel_idx = int(cfg.get("inferred_power_channel", 4) or 4)
    meter = _read_remote_cabinet_meter(cabinet_idx)
    channels = meter.get("channels_1_4") if isinstance(meter.get("channels_1_4"), list) else []
    power_feed_on = None
    if 1 <= channel_idx <= len(channels):
        power_feed_on = bool(channels[channel_idx - 1])
    power_kw = meter.get("stable_realtime_power")
    if power_kw is None:
        power_kw = meter.get("effective_realtime_power")
    if power_kw is None:
        power_kw = meter.get("realtime_power")
    try:
        power_kw = float(power_kw)
    except Exception:
        power_kw = None

    last_intent = str(runtime.get("last_intent") or "").lower()
    last_command_ok = runtime.get("last_command_ok")
    last_command_at = runtime.get("last_command_at")
    baseline_kw = runtime.get("command_baseline_kw")
    try:
        baseline_kw = float(baseline_kw)
    except Exception:
        baseline_kw = None
    last_ts = _parse_iso_like_ts(last_command_at)
    age_sec = (now - last_ts) if last_ts else None
    on_threshold_kw = float(cfg.get("inferred_on_threshold_kw", 7.0) or 7.0)
    standby_max_kw = float(cfg.get("inferred_standby_max_kw", 3.0) or 3.0)
    on_delta_kw = float(cfg.get("inferred_on_delta_kw", 1.0) or 1.0)
    off_delta_kw = float(cfg.get("inferred_off_delta_kw", on_delta_kw) or on_delta_kw)
    absolute_power_enabled = bool(cfg.get("inferred_absolute_power_enabled", False))
    warmup_sec = float(cfg.get("inferred_warmup_sec", 300) or 300)
    cooldown_sec = float(cfg.get("inferred_cooldown_sec", 240) or 240)
    command_trust_sec = float(cfg.get("inferred_command_trust_sec", 180) or 180)
    power_verify_sec = float(cfg.get("inferred_power_verify_sec", 120) or 120)
    low_power_grace_sec = float(cfg.get("inferred_low_power_grace_sec", min(20, power_verify_sec)) or min(20, power_verify_sec))
    delta_kw = (power_kw - baseline_kw) if (power_kw is not None and baseline_kw is not None) else None
    drop_kw = (baseline_kw - power_kw) if (power_kw is not None and baseline_kw is not None) else None
    command_success = last_command_ok is not False
    low_power_veto = bool(absolute_power_enabled and power_kw is not None and power_kw < standby_max_kw)

    status = {
        "online": bool(tcp_online),
        "power": "unknown",
        "source": "推断状态",
        "source_name": "串口服务器 + 电柜功率",
        "lamp_hours": None,
        "lamp_state": None,
        "temp_status": "不支持查询",
        "error": "正常" if tcp_online else (tcp_error or "串口服务器离线"),
        "manufacturer": cfg.get("fixed_manufacturer") or "RS232 控制",
        "product_name": cfg.get("fixed_model") or "无反馈投影机",
        "software_version": cfg.get("fixed_software_version") or "推断型",
        "class_version": "状态推断",
        "other_info": "",
        "error_details": {},
        "inferred": True,
        "inference_basis": "",
        "inferred_targets": target_status,
        "target_online_count": target_online,
        "target_total_count": target_total,
        "last_command_at": last_command_at,
        "last_intent": last_intent or None,
        "last_command_source": runtime.get("last_command_source"),
        "gateway_status": gateway_status if isinstance(gateway_status, dict) else {},
        "power_feed_on": power_feed_on,
        "meter_power_kw": power_kw,
        "command_baseline_kw": baseline_kw,
        "power_delta_kw": delta_kw,
        "meter_updated_at": meter.get("updated_at"),
        "status_level": "online" if tcp_online else ("stale" if tcp_degraded else "error"),
    }

    def finalize_status():
        age_text = f"，上次指令 {int(age_sec)} 秒前" if age_sec is not None else "，暂无指令记录"
        if delta_kw is not None:
            pwr_text = f"总功率 {power_kw:.2f}kW，变化 {delta_kw:+.2f}kW"
        elif power_kw is not None:
            pwr_text = f"总功率 {power_kw:.2f}kW"
        else:
            pwr_text = "总功率未知"
        feed_text = "供电合闸" if power_feed_on else ("供电未知" if power_feed_on is None else "供电断开")
        target_text = f"串口服务器 {target_online}/{target_total} 在线" if target_total else "串口服务器未配置"
        status["inference_basis"] = f"{target_text}，{feed_text}，{pwr_text}{age_text}"
        status["other_info"] = status["inference_basis"]
        if (
            status.get("error") == "正常"
            and status.get("power") not in ["warning", "unknown"]
            and status.get("status_level") != "stale"
        ):
            status["status_level"] = "online"
        return status

    if not tcp_online:
        status["power"] = "unknown"
        status["status_level"] = "stale" if tcp_degraded else "error"
        status["inference_basis"] = f"串口服务器在线 {target_online}/{target_total}，{tcp_error}"
        if not tcp_degraded:
            return status
    if power_feed_on is False:
        status["power"] = "off"
        status["lamp_state"] = "无供电"
        status["inference_basis"] = f"电柜第 {channel_idx} 路断开"
        return status
    if low_power_veto:
        if last_intent == "on" and command_success and age_sec is not None and age_sec <= low_power_grace_sec:
            status["power"] = "warming"
            status["lamp_state"] = "启动校验中"
            status["source_name"] = "121网关指令 + 低功率校验"
            status["status_level"] = "stale"
        elif last_intent == "on" and command_success and age_sec is not None and age_sec <= power_verify_sec:
            status["power"] = "warning"
            status["lamp_state"] = "疑似未启动"
            status["error"] = "总功率低于待机阈值"
            status["source_name"] = "电柜功率优先"
            status["status_level"] = "stale"
        else:
            status["power"] = "off"
            status["lamp_state"] = "待机"
            status["source_name"] = "电柜功率优先"
        return finalize_status()

    if absolute_power_enabled and power_kw is not None and power_kw >= on_threshold_kw and last_intent != "off":
        status["power"] = "on"
        status["lamp_state"] = "疑似运行" if not last_intent else "开启"
    elif last_intent == "on":
        if command_success and age_sec is not None and age_sec <= command_trust_sec:
            status["power"] = "on"
            status["lamp_state"] = "开启" if delta_kw is not None and delta_kw >= on_delta_kw else "网关已开机"
            status["source_name"] = "121网关指令 + 电柜校验"
        elif delta_kw is not None and delta_kw >= on_delta_kw:
            status["power"] = "on"
            status["lamp_state"] = "开启"
        elif baseline_kw is None and absolute_power_enabled and power_kw is not None and power_kw >= on_threshold_kw:
            status["power"] = "on"
            status["lamp_state"] = "开启"
        elif command_success and age_sec is not None and age_sec <= max(warmup_sec, command_trust_sec):
            status["power"] = "on"
            status["lamp_state"] = "网关已开机"
            status["source_name"] = "121网关指令 + 电柜校验"
        elif age_sec is not None and age_sec <= min(warmup_sec, power_verify_sec):
            status["power"] = "warming"
            status["lamp_state"] = "启动中"
        elif delta_kw is not None and delta_kw < max(on_delta_kw * 0.35, 0.3):
            status["power"] = "warning"
            status["lamp_state"] = "疑似未启动"
            status["error"] = "开机后功率未上升"
            status["status_level"] = "stale"
        elif baseline_kw is None and absolute_power_enabled and power_kw is not None and power_kw < standby_max_kw:
            status["power"] = "warning"
            status["lamp_state"] = "疑似未启动"
            status["error"] = "开机后功率未上升"
            status["status_level"] = "stale"
        else:
            status["power"] = "unknown"
            status["lamp_state"] = "待确认"
    elif last_intent == "off":
        if command_success and age_sec is not None and age_sec <= command_trust_sec:
            status["power"] = "off"
            status["lamp_state"] = "待机" if drop_kw is not None and drop_kw >= off_delta_kw else "网关已关机"
            status["source_name"] = "121网关指令 + 电柜校验"
        elif drop_kw is not None and drop_kw >= off_delta_kw:
            status["power"] = "off"
            status["lamp_state"] = "待机"
        elif baseline_kw is None and absolute_power_enabled and power_kw is not None and power_kw < standby_max_kw:
            status["power"] = "off"
            status["lamp_state"] = "待机"
        elif command_success and age_sec is not None and age_sec <= max(cooldown_sec, command_trust_sec):
            status["power"] = "off"
            status["lamp_state"] = "网关已关机"
            status["source_name"] = "121网关指令 + 电柜校验"
        elif age_sec is not None and age_sec <= min(cooldown_sec, power_verify_sec) and (
            drop_kw is None or drop_kw >= max(off_delta_kw * 0.35, 0.3)
        ):
            status["power"] = "cooling"
            status["lamp_state"] = "冷却中"
        elif drop_kw is not None and drop_kw < max(off_delta_kw * 0.35, 0.3):
            status["power"] = "warning"
            status["lamp_state"] = "疑似仍在运行"
            status["error"] = "关机后功率仍偏高"
            status["status_level"] = "stale"
        elif baseline_kw is None and absolute_power_enabled and power_kw is not None and power_kw >= on_threshold_kw:
            status["power"] = "warning"
            status["lamp_state"] = "疑似仍在运行"
            status["error"] = "关机后功率仍偏高"
            status["status_level"] = "stale"
        else:
            status["power"] = "off"
            status["lamp_state"] = "待机"
    else:
        if absolute_power_enabled and power_kw is not None and power_kw >= on_threshold_kw:
            status["power"] = "on"
            status["lamp_state"] = "疑似运行"
        elif absolute_power_enabled and power_kw is not None and power_kw < standby_max_kw:
            status["power"] = "off"
            status["lamp_state"] = "待机"
        else:
            status["power"] = "unknown"
            status["lamp_state"] = "等待控制记录"

    return finalize_status()

DEFAULT_SERIES_BY_BRAND = {
    "appotronics": "dh",
    "epson": "pjlink",
    "generic": "pjlink",
    "smile": "ek",
    "smile_ek": "ek",
}

BRAND_DISPLAY_NAMES = {
    "appotronics": "光峰",
    "epson": "爱普生",
    "generic": "通用",
    "smile": "视美乐",
}

PROJECTOR_COMMAND_NAME_MAPS = {
    ("smile", "ek"): {
        "power_on": "开机",
        "power_off": "关机",
        "source_pc": "切换到 PC",
        "source_vga": "切换到 VGA",
        "source_dvi": "切换到 DVI",
        "source_hdmi1": "切换到 HDMI1",
        "source_hdmi2": "切换到 HDMI2",
        "source_dp": "切换到 DP",
        "mute_on": "静音黑屏开启",
        "mute_off": "静音黑屏关闭",
        "freeze_on": "冻结画面开启",
        "freeze_off": "冻结画面关闭",
        "volume_up": "音量加",
        "volume_down": "音量减",
        "menu_on": "打开菜单",
        "menu_off": "关闭菜单",
        "key_up": "方向上",
        "key_down": "方向下",
        "key_left": "方向左",
        "key_right": "方向右",
        "key_enter": "确认",
        "key_exit": "返回",
        "auto_adjust": "自动调整",
        "lamp_eco": "灯泡节能模式",
        "lamp_normal": "灯泡标准模式",
        "power_status": "查询开关机状态",
        "source_status": "查询信号源",
        "volume_status": "查询音量",
        "mute_status": "查询静音黑屏状态",
        "temp_status": "查询温度状态",
        "lamp_status": "查询灯泡状态",
    },
    ("appotronics", "uh"): {
        "power_on": "开机",
        "power_off": "关机",
        "get_power_state": "查询开关机状态",
        "get_temperature": "查询温度",
        "get_lamp_hours": "查询灯泡时长",
        "get_signal_source": "查询信号源",
    },
    ("appotronics", "uk"): {
        "power_on": "开机",
        "power_off": "关机",
        "get_power_state": "查询开关机状态",
        "get_lamp_hours": "查询灯泡时长",
        "source_hdmi1": "切换 HDMI1",
    },
    ("appotronics", "du"): {
        "power_on": "开机",
        "power_off": "关机",
        "get_power_state": "查询开关机状态",
        "get_temperature": "查询温度",
        "get_product_info": "查询产品信息",
    },
    ("appotronics", "m"): {
        "power_on": "开机",
        "power_off": "关机",
        "get_power_state": "查询开关机状态",
        "get_lamp_hours": "查询灯泡时长",
        "get_signal_source": "查询信号源",
    },
    ("appotronics", "f"): {
        "power_on": "开机",
        "power_off": "关机",
        "get_power_state": "查询开关机状态",
        "get_lamp_hours": "查询灯泡时长",
        "get_signal_source": "查询信号源",
    },
    ("appotronics", "s"): {
        "get_power_state": "查询开关机状态",
    },
    ("appotronics", "gt"): {
        "power_on": "开机",
        "power_off": "关机",
        "get_power_state": "查询开关机状态",
        "get_signal_source": "查询信号源",
    },
}

PROJECTOR_SERIES_TEXT_MAP = {
    ("appotronics", "uh"): ("光峰 UH 系列", "光峰 UH 系列"),
    ("appotronics", "uk"): ("光峰 UK 系列", "光峰 UK 系列"),
    ("appotronics", "du"): ("光峰 DU 系列", "光峰 DU 系列"),
    ("appotronics", "m"): ("光峰 M 系列", "光峰 M 系列"),
    ("appotronics", "f"): ("光峰 F 系列", "光峰 F 系列"),
    ("appotronics", "s"): ("光峰 S 系列", "光峰 S 系列"),
    ("appotronics", "gt"): ("光峰 G/T 系列", "光峰 G/T 系列"),
    ("smile", "ek"): ("视美乐 EK 系列", "视美乐 EK 系列"),
}

PROJECTOR_CONNECTION_TEXT_MAP = {
    "appotronics_uh_tcp": "网络接入 (TCP)",
    "appotronics_uk_tcp": "网络接入 (TCP)",
    "appotronics_du_tcp": "网络接入 (TCP)",
    "appotronics_m_tcp": "网络接入 (TCP)",
    "appotronics_f_tcp": "网络接入 (TCP)",
    "appotronics_s_udp": "网络接入 (UDP)",
    "appotronics_gt_tcp": "网络接入 (TCP)",
    "smile_ek_tcp": "TCP 网口 / 串口服务器透传",
    "smile_ek_com": "本机串口 COM",
    "pjlink": "PJLink",
}

def looks_garbled_text(value):
    if not isinstance(value, str):
        return True
    text = value.strip()
    if not text:
        return True
    return any(token in text for token in ["?", "锛", "馃", "篇胆赤", "狼双", "高桁", "寮€", "闂"])

def sanitize_brand_library(lib):
    if not isinstance(lib, dict):
        return lib
    for brand in lib.get("brands", []):
        raw_brand = str(brand.get("brand") or brand.get("id") or "").strip()
        brand_id, series_id = normalize_brand_series(raw_brand, brand.get("series"))
        series_key = (brand_id, series_id)
        if series_key in PROJECTOR_SERIES_TEXT_MAP:
            proper_name, proper_display_name = PROJECTOR_SERIES_TEXT_MAP[series_key]
            if looks_garbled_text(brand.get("name")):
                brand["name"] = proper_name
            if looks_garbled_text(brand.get("display_name")):
                brand["display_name"] = proper_display_name
        elif brand_id in BRAND_DISPLAY_NAMES and looks_garbled_text(brand.get("name")):
            brand["name"] = brand.get("display_name") or BRAND_DISPLAY_NAMES[brand_id]

        for conn in (brand.get("connection_types") or {}).values():
            conn_id = str(conn.get("id") or "").strip()
            if conn_id in PROJECTOR_CONNECTION_TEXT_MAP and looks_garbled_text(conn.get("name")):
                conn["name"] = PROJECTOR_CONNECTION_TEXT_MAP[conn_id]
            if looks_garbled_text(conn.get("icon")):
                conn["icon"] = ""

        cmd_map = PROJECTOR_COMMAND_NAME_MAPS.get((brand_id, series_id), {})
        for cmd in brand.get("commands", []) or []:
            fallback_name = cmd_map.get(str(cmd.get("id", "")).strip())
            if fallback_name and looks_garbled_text(cmd.get("name")):
                cmd["name"] = fallback_name
            if looks_garbled_text(cmd.get("icon")):
                cmd["icon"] = ""
    return lib


def normalize_brand_series(brand_id, series_id=None):
    """兼容历史配置中的品牌/系列写法。"""
    brand_id = (brand_id or "").strip()
    series_id = (series_id or "").strip()

    alias_map = {
        "appotronics_dh": ("appotronics", "dh"),
        "appotronics_uh": ("appotronics", "uh"),
        "appotronics_uk": ("appotronics", "uk"),
        "appotronics_du": ("appotronics", "du"),
        "appotronics_m": ("appotronics", "m"),
        "appotronics_f": ("appotronics", "f"),
        "appotronics_s": ("appotronics", "s"),
        "appotronics_gt": ("appotronics", "gt"),
        "epson_pjlink": ("epson", "pjlink"),
        "generic_pjlink": ("generic", "pjlink"),
        "pjlink": ("generic", "pjlink"),
        "smile_ek": ("smile", "ek"),
    }
    if brand_id in alias_map:
        alias_brand, alias_series = alias_map[brand_id]
        return alias_brand, series_id or alias_series

    if not series_id:
        series_id = DEFAULT_SERIES_BY_BRAND.get(brand_id, "")
    return brand_id, series_id


def extract_brand_key(brand):
    raw_brand = brand.get("brand") or brand.get("id", "")
    brand_id, _ = normalize_brand_series(raw_brand, brand.get("series"))
    if brand_id:
        return brand_id
    raw_id = brand.get("id", "")
    return raw_id.split("_")[0] if "_" in raw_id else raw_id

def load_brand_library():
    """加载品牌命令库"""
    if os.path.exists(BRANDS_FILE):
        try:
            with open(BRANDS_FILE, "r", encoding="utf-8") as f:
                return sanitize_brand_library(json.load(f))
        except:
            pass
    return {"brands": []}

def get_all_brands():
    """获取所有品牌列表 (仅品牌)"""
    lib = load_brand_library()
    brand_map = {}
    for brand in lib.get("brands", []):
        brand_key = extract_brand_key(brand)
        if not brand_key:
            continue
        item = brand_map.setdefault(brand_key, {
            "id": brand_key,
            "name": BRAND_DISPLAY_NAMES.get(brand_key, brand.get("display_name") or brand.get("name") or brand_key),
            "series_count": 0
        })
        item["series_count"] += 1
    return list(brand_map.values())

def get_brand_series(brand_id):
    """获取品牌下的所有系列"""
    lib = load_brand_library()
    series_list = []

    brand_id, default_series = normalize_brand_series(brand_id, "")
    for brand in lib.get("brands", []):
        item_brand, item_series = normalize_brand_series(brand.get("brand") or brand.get("id", ""), brand.get("series"))
        if item_brand == brand_id:
            series_list.append({
                "id": item_series or default_series or (brand["id"].split("_")[-1] if "_" in brand["id"] else "default"),
                "name": brand.get("name", ""),
                "display_name": brand.get("display_name", ""),
                "commands": brand.get("commands", []),
                "connection_types": brand.get("connection_types", {}),
                "status_queries": brand.get("status_queries", {}),
                "status_parse": brand.get("status_parse", {})
            })
    
    return series_list

def get_series_info(brand_id, series_id):
    """获取指定系列的详细信息"""
    brand_id, series_id = normalize_brand_series(brand_id, series_id)
    series_list = get_brand_series(brand_id)
    for series in series_list:
        if series["id"] == series_id:
            return series
    return None

def get_series_commands(brand_id, series_id):
    """获取指定系列的命令列表"""
    series = get_series_info(brand_id, series_id)
    if series:
        return series.get("commands", [])
    return []

def get_brand_commands(brand_id):
    """兼容旧接口：按品牌返回默认系列命令。"""
    brand_id, series_id = normalize_brand_series(brand_id, "")
    if not series_id:
        series_list = get_brand_series(brand_id)
        if not series_list:
            return []
        series_id = series_list[0]["id"]
    return get_series_commands(brand_id, series_id)

def get_connection_types(brand_id, series_id):
    """获取系列支持的所有连接类型"""
    series = get_series_info(brand_id, series_id)
    if series:
        return series.get("connection_types", {})
    return {}

def get_connection_type_name(brand_id, series_id, connection_type):
    """获取连接类型的显示名称"""
    conn_types = get_connection_types(brand_id, series_id)
    for key, info in conn_types.items():
        if info.get("id") == connection_type:
            return info.get("name", connection_type)
    return connection_type

def get_brand_info(brand_id):
    """获取品牌的详细信息"""
    lib = load_brand_library()
    for brand in lib.get("brands", []):
        if brand["id"] == brand_id:
            return brand
    return None

def get_command_by_id(brand_id, series_id, cmd_id):
    """根据品牌、系列和命令 ID 获取具体命令配置"""
    commands = get_series_commands(brand_id, series_id)
    for cmd in commands:
        if cmd["id"] == cmd_id:
            return cmd
    return None

class ProjectorDriver:
    def __init__(self, config):
        self.cfg = dict(config or {})
        for key in ["ip", "com_port", "password", "device_id", "fid", "name", "id"]:
            value = self.cfg.get(key)
            if isinstance(value, str):
                self.cfg[key] = value.strip().replace(" ", "") if key == "ip" else value.strip()
        self.lock = threading.Lock()
        self.brand_id = self.cfg.get("brand_id", "custom")
        self.series_id = self.cfg.get("series_id", "")
        self.normalized_brand_id, self.normalized_series_id = normalize_brand_series(self.brand_id, self.series_id)
        self.control_type = self.cfg.get("control_type", "pjlink")
        
    def execute(self, cmd_config):
        print(f"\n[Projector DEBUG] =========================================")
        print(f"[Projector DEBUG] 准备控制投影机：{self.cfg.get('name', '未命名')} (ID: {self.cfg.get('id')})")
        print(f"[Projector DEBUG] 品牌：{self.brand_id} | 协议：{self.control_type}")
        print(f"[Projector DEBUG] 前端传入参数：{cmd_config}")
        
        # 兼容旧版的纯字符串调用
        if isinstance(cmd_config, str):
            cmd_id = cmd_config
            brand_cmds = get_series_commands(self.normalized_brand_id, self.normalized_series_id) or get_brand_commands(self.brand_id)
            cmd_def = next((c for c in brand_cmds if c["id"] == cmd_id), None)
            
            if cmd_def:
                fmt = cmd_def.get("default_format", "str")
                payload = self._get_payload(cmd_def, fmt)
            else:
                # 回退到旧版逻辑
                if cmd_config == "power_on":
                    payload, fmt = ("%1POWR 1", "str") if self.control_type == "pjlink" else ("23 30 30 30 30 20 31 0D", "hex")
                elif cmd_config == "power_off":
                    payload, fmt = ("%1POWR 0", "str") if self.control_type == "pjlink" else ("23 30 30 30 30 20 30 0D", "hex")
                else:
                    payload, fmt = (cmd_config, "str")
        else:
            # 新版字典调用
            payload = cmd_config.get("payload", "")
            fmt = cmd_config.get("format", "hex")
            payload = self._apply_runtime_payload_rules(payload, fmt)

        print(f"[Projector DEBUG] 最终解析 -> 协议模式：[{self.control_type}], 格式：[{fmt}], Payload: [{payload}]")

        if self.control_type == "inferred_rs232":
            return self._send_inferred_rs232_group(payload, fmt)

        if self.control_type == "pjlink":
            if fmt == "hex":
                try:
                    payload = bytes.fromhex(payload.replace(" ", "")).decode("ascii")
                except Exception:
                    pass
            return self._send_pjlink(payload)
        elif self.control_type in [
            "smile_ek_tcp", "custom_tcp",
            "appotronics_uh_tcp", "appotronics_uk_tcp", "appotronics_du_tcp",
            "appotronics_m_tcp", "appotronics_f_tcp", "appotronics_gt_tcp"
        ]:
            return self._send_tcp_raw(payload, fmt)
        elif self.control_type in ["smile_ek_udp", "custom_udp", "appotronics_s_udp"]:
            return self._send_udp_raw(payload, fmt)
        elif self.control_type in ["smile_ek_com", "rs232", "custom_com"]:
            return self._send_rs232(payload, fmt)
        elif self.control_type == "appotronics_dh_tcp":
            return self._send_appotronics_dh_tcp(payload, fmt)

        return False, f"不支持的控制类型：{self.control_type}"

    def _send_inferred_rs232_group(self, payload_raw, fmt):
        on_payload = str(self.cfg.get("inferred_power_on_payload") or "23 50 57 52 30 2C 31 21")
        off_payload = str(self.cfg.get("inferred_power_off_payload") or "23 50 57 52 30 2C 30 21")
        normalized = _normalize_projector_hex(payload_raw) if fmt == "hex" else _normalize_projector_hex(str(payload_raw or "").encode("utf-8").hex())
        action = None
        if normalized == _normalize_projector_hex(on_payload):
            action = "on"
        elif normalized == _normalize_projector_hex(off_payload):
            action = "off"
        if action and self.cfg.get("inferred_gateway_control_url"):
            gateway_result = _inferred_gateway_control(self.cfg, action)
            if isinstance(gateway_result, dict):
                ok = bool(gateway_result.get("success"))
                return ok, json.dumps(gateway_result, ensure_ascii=False)[:1000]

        targets = _inferred_targets(self.cfg)
        if not targets:
            return False, "未配置串口服务器目标"
        try:
            payload = self._build_transport_payload(payload_raw, fmt)
        except Exception as exc:
            return False, f"指令格式错误: {exc}"

        results = []
        all_ok = True
        for target in targets:
            ip = target["ip"]
            port = int(target.get("port", 502) or 502)
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(4.0)
                    s.connect((ip, port))
                    s.sendall(payload)
                    time.sleep(0.15)
                    s.settimeout(0.6)
                    try:
                        resp = s.recv(1024)
                    except Exception:
                        resp = b""
                results.append({
                    "name": target.get("name") or ip,
                    "ip": ip,
                    "ok": True,
                    "response": resp.hex(" ").upper() if resp else "",
                })
            except Exception as exc:
                all_ok = False
                results.append({
                    "name": target.get("name") or ip,
                    "ip": ip,
                    "ok": False,
                    "error": str(exc),
                })
        ok_count = sum(1 for item in results if item.get("ok"))
        detail = "；".join(
            f"{item.get('name')}:{'成功' if item.get('ok') else item.get('error', '失败')}"
            for item in results
        )
        return all_ok, f"组控完成 {ok_count}/{len(results)}，{detail}"
    
    def _apply_runtime_payload_rules(self, payload, fmt):
        payload = payload or ""
        if self.normalized_brand_id == "smile":
            payload = self._replace_smile_device_id(payload, fmt)
        if self.control_type == "pjlink":
            payload = self._normalize_pjlink_payload(payload, fmt)
        return payload

    def _normalize_pjlink_payload(self, payload, fmt):
        if fmt != "str":
            return payload
        text = str(payload or "").strip()
        legacy_map = {
            "%1FREZ 1": "%2FREZ 1",
            "%1FREZ 0": "%2FREZ 0",
            "%1FREZ ?": "%2FREZ ?",
        }
        return legacy_map.get(text, text)

    def _replace_smile_device_id(self, payload, fmt):
        device_id = str(self.cfg.get("device_id", self.cfg.get("fid", "0"))).strip() or "0"
        if fmt == "hex":
            try:
                payload_bytes = bytes.fromhex(payload.replace(" ", ""))
                if len(payload_bytes) >= 5:
                    new_payload = bytearray(payload_bytes)
                    for i in range(len(new_payload)):
                        if new_payload[i:i+1] == b',':
                            if i > 0:
                                new_payload[i-1:i] = device_id[-1:].encode('utf-8')
                            break
                    payload = new_payload.hex(' ').upper()
            except Exception as e:
                print(f"[Projector DEBUG] ID replace failed: {str(e)}")
            return payload
        try:
            import re
            pattern = r'#([A-Z]+)(\d+),'
            match = re.search(pattern, payload)
            if match:
                cmd_prefix = match.group(1)
                old_id = match.group(2)
                payload = payload.replace(f'#{cmd_prefix}{old_id},', f'#{cmd_prefix}{device_id},')
        except Exception as e:
            print(f"[Projector DEBUG] ID replace failed (str): {str(e)}")
        return payload

    def _build_transport_payload(self, payload_raw, fmt):
        if fmt == "hex":
            return bytes.fromhex((payload_raw or "").replace(" ", ""))
        return (payload_raw or "").encode("utf-8").decode("unicode_escape").encode("utf-8")

    def _decode_smile_response(self, data):
        if data is None:
            return ""
        if isinstance(data, str):
            return data.strip()
        return data.decode("utf-8", errors="ignore").replace("\x00", "").strip()

    def _send_smile_transport(self, payload_raw, fmt="str"):
        payload = self._build_transport_payload(payload_raw, fmt)

        if self.control_type in ["smile_ek_tcp", "custom_tcp"]:
            ip = self.cfg.get("ip")
            port = int(self.cfg.get("port", 502))
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3.0)
                s.connect((ip, port))
                s.sendall(payload)
                time.sleep(0.25)
                try:
                    return True, s.recv(1024)
                except socket.timeout:
                    return True, b""

        if self.control_type in ["smile_ek_udp", "custom_udp"]:
            ip = self.cfg.get("ip")
            port = int(self.cfg.get("port", 502))
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(2.0)
                s.sendto(payload, (ip, port))
                try:
                    data, _ = s.recvfrom(1024)
                    return True, data
                except socket.timeout:
                    return True, b""

        if self.control_type in ["smile_ek_com", "rs232", "custom_com"]:
            com_port = self.cfg.get("com_port")
            baudrate = int(self.cfg.get("baudrate", 19200))
            with self.lock:
                with serial.Serial(com_port, baudrate, timeout=1.5) as ser:
                    ser.reset_input_buffer()
                    ser.write(payload)
                    time.sleep(0.25)
                    return True, ser.read_all()

        return False, f"unsupported transport: {self.control_type}"

    def _send_smile_query(self, payload, fmt="str"):
        normalized = self._apply_runtime_payload_rules(payload, fmt).strip()
        candidates = [normalized]
        if normalized and not normalized.endswith("!"):
            candidates.append(normalized + "!")

        last_text = ""
        last_error = ""
        for candidate in candidates:
            try:
                success, raw_res = self._send_smile_transport(candidate, fmt)
            except Exception as e:
                success, raw_res = False, str(e)
            text = self._decode_smile_response(raw_res)
            if success and text:
                return True, text
            if success:
                last_text = text
            else:
                last_error = text or str(raw_res or "")
        return False, last_error or last_text

    def _parse_smile_kv_response(self, response):
        text = str(response or "").strip()
        if not text:
            return None, None
        if ":" in text:
            text = text.split(":", 1)[-1].strip()
        if text.startswith("#"):
            text = text[1:]
        if text.endswith("!"):
            text = text[:-1].strip()
        if "," not in text:
            return text.strip().upper(), None
        key, value = text.split(",", 1)
        return key.strip().upper(), value.strip()

    def _parse_smile_response_value(self, response):
        text = str(response or "").strip()
        if not text:
            return None
        if ":" in text:
            text = text.split(":", 1)[-1].strip()
        if "：" in text:
            text = text.split("：", 1)[-1].strip()
        if text.startswith("#"):
            text = text[1:]
        if "," in text:
            text = text.split(",", 1)[-1].strip()
        if text.endswith("!"):
            text = text[:-1].strip()
        return text or None

    def _parse_smile_response_value(self, response):
        text = str(response or "").strip()
        if not text:
            return None
        if ":" in text:
            text = text.split(":", 1)[-1].strip()
        if text.startswith("#"):
            text = text[1:]
        if "," in text:
            text = text.split(",", 1)[-1].strip()
        if text.endswith("!"):
            text = text[:-1].strip()
        return text or None

    def _get_payload(self, cmd_def, fmt):
        """读取命令定义中的 payload，并应用运行时的动态替换规则。"""
        if fmt == "hex":
            payload = cmd_def.get("payload_hex", "")
        else:
            payload = cmd_def.get("payload_str", "")
        return self._apply_runtime_payload_rules(payload, fmt)

    def _send_pjlink(self, command):
        ip = self.cfg.get("ip")
        port = int(self.cfg.get("port", 4352))
        password = self.cfg.get("password", "")
        print(f"[Projector DEBUG] [PJLink] 正在连接 -> {ip}:{port}")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3.0)
                s.connect((ip, port))
                print(f"[Projector DEBUG] [PJLink] TCP 连接成功，等待设备握手...")
                
                init_res = s.recv(1024).decode('utf-8').strip()
                print(f"[Projector DEBUG] [PJLink] 收到握手回码 -> {init_res}")
                
                prefix = ""
                if init_res.startswith("PJLINK 1"):
                    rand_str = init_res.split(" ")[2]
                    prefix = hashlib.md5((rand_str + password).encode('utf-8')).hexdigest()
                    print(f"[Projector DEBUG] [PJLink] 已计算 MD5 认证前缀")
                elif not init_res.startswith("PJLINK 0"):
                    return False, f"PJLink 握手异常：{init_res}"

                full_cmd = f"{prefix}{command}\r"
                print(f"[Projector DEBUG] [PJLink] 最终发出报文 -> {full_cmd.strip()}")
                s.sendall(full_cmd.encode('utf-8'))
                
                res = s.recv(1024).decode('utf-8').strip()
                print(f"[Projector DEBUG] [PJLink] 投影机最终返回 -> {res}")
                
                if "ERR" in res: return False, f"投影机报错：{res}"
                return True, res
        except Exception as e:
            err_msg = f"{str(e)}"
            print(f"[Projector DEBUG] [PJLink] 发生致命错误：{err_msg}\n{traceback.format_exc()}")
            return False, f"PJLink 通讯失败：{err_msg}"

    def _open_pjlink_session(self):
        ip = self.cfg.get("ip")
        port = int(self.cfg.get("port", 4352))
        password = self.cfg.get("password", "")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.5)
        s.connect((ip, port))
        init_res = s.recv(1024).decode('utf-8', errors='ignore').strip()

        prefix = ""
        if init_res.startswith("PJLINK 1"):
            parts = init_res.split(" ")
            rand_str = parts[2] if len(parts) > 2 else ""
            prefix = hashlib.md5((rand_str + password).encode('utf-8')).hexdigest()
        elif not init_res.startswith("PJLINK 0"):
            s.close()
            raise RuntimeError(f"PJLink 握手异常：{init_res}")
        return s, prefix

    def _recv_pjlink_response(self, session):
        session.settimeout(1.5)
        data = b""
        deadline = time.time() + 2.0
        while time.time() < deadline:
            try:
                chunk = session.recv(1)
            except socket.timeout:
                break
            if not chunk:
                break
            data += chunk
            if chunk == b"\r":
                break

        # Some PJLink devices append NUL bytes or repeat the same response line.
        session.settimeout(0.05)
        while True:
            try:
                extra = session.recv(1)
            except Exception:
                break
            if not extra:
                break
            if extra == b"\x00":
                continue
            data += extra
            if extra == b"\r":
                break

        text = data.decode("utf-8", errors="ignore").replace("\x00", "").strip()
        if "\r" in text:
            parts = [item.strip() for item in text.split("\r") if item.strip()]
            if parts:
                if len(parts) >= 2 and len(set(parts)) == 1:
                    text = parts[0]
                else:
                    text = parts[-1]
        return text

    def _send_pjlink_on_session(self, session, prefix, command):
        full_cmd = f"{prefix}{command}\r"
        session.sendall(full_cmd.encode('utf-8'))
        res = self._recv_pjlink_response(session)
        if "ERR" in res:
            return False, f"投影机报错：{res}"
        return True, res

    def _send_tcp_raw(self, payload_raw, fmt):
        ip = self.cfg.get("ip")
        port = int(self.cfg.get("port", 502))
        print(f"[Projector DEBUG] [TCP 透传] 正在连接 -> {ip}:{port}")
        print(f"[Projector DEBUG] [TCP 透传] 超时设置：连接 5 秒，读取 2 秒")
        try:
            if fmt == "hex":
                payload = bytes.fromhex(payload_raw.replace(" ", ""))
            else:
                payload = payload_raw.encode('utf-8').decode('unicode_escape').encode('utf-8')
                
            print(f"[Projector DEBUG] [TCP 透传] 实际发出的 16 进制数据 -> {payload.hex(' ').upper()}")
            
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5.0)  # 增加连接超时到 5 秒
                print(f"[Projector DEBUG] [TCP 透传] 开始连接...")
                s.connect((ip, port))
                print(f"[Projector DEBUG] [TCP 透传] 连接成功，正在发送...")
                s.sendall(payload)
                print(f"[Projector DEBUG] [TCP 透传] 数据已发送，等待响应...")
                
                time.sleep(0.3)  # 增加等待时间到 300ms
                try:
                    s.settimeout(2.0)  # 增加读取超时到 2 秒
                    res = s.recv(1024)
                    if res:
                        print(f"[Projector DEBUG] [TCP 透传] 收到的 16 进制返回 -> {res.hex(' ').upper()}")
                        return True, f"网关返回：{res.hex(' ').upper()}"
                    else:
                        print(f"[Projector DEBUG] [TCP 透传] 连接被关闭，网关没有返回数据")
                        return True, "已发送 (网关无返回)"
                except socket.timeout:
                    print(f"[Projector DEBUG] [TCP 透传] 读取超时！网关没有返回数据 (这通常是正常的)")
                    return True, "已发送 (网关无返回)"
                except Exception as e:
                    print(f"[Projector DEBUG] [TCP 透传] 接收异常：{str(e)}")
                    return True, "已发送 (接收异常)"
        except socket.timeout:
            print(f"[Projector DEBUG] [TCP 透传] 连接超时！请检查 IP 地址和端口是否正确")
            return False, f"连接超时，请检查网络配置 (IP: {ip}, Port: {port})"
        except ConnectionRefusedError:
            print(f"[Projector DEBUG] [TCP 透传] 连接被拒绝！目标设备可能未开机或端口未开放")
            return False, f"连接被拒绝，请检查设备是否开机 (IP: {ip}, Port: {port})"
        except Exception as e:
            print(f"[Projector DEBUG] [TCP 透传] 发生异常：{str(e)}\n{traceback.format_exc()}")
            return False, f"TCP 透传通讯失败：{str(e)}"

    def _send_udp_raw(self, payload_raw, fmt):
        ip = self.cfg.get("ip")
        port = int(self.cfg.get("port", 502))
        print(f"[Projector DEBUG] [UDP 透传] 正在发送 -> {ip}:{port}")
        try:
            if fmt == "hex":
                payload = bytes.fromhex(payload_raw.replace(" ", ""))
            else:
                payload = payload_raw.encode('utf-8').decode('unicode_escape').encode('utf-8')
                
            print(f"[Projector DEBUG] [UDP 透传] 实际发出的 16 进制数据 -> {payload.hex(' ').upper()}")
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(3.0)
            sock.sendto(payload, (ip, port))
            print(f"[Projector DEBUG] [UDP 透传] 数据已发送")
            sock.close()
            
            return True, "UDP 已发送"
        except Exception as e:
            print(f"[Projector DEBUG] [UDP 透传] 发生异常：{str(e)}\n{traceback.format_exc()}")
            return False, f"UDP 透传通讯失败：{str(e)}"

    def _send_rs232(self, payload_raw, fmt):
        com_port = self.cfg.get("com_port")
        baudrate = int(self.cfg.get("baudrate", 9600))
        print(f"[Projector DEBUG] [串口 RS232] 准备打开本地串口 -> {com_port} (波特率：{baudrate})")
        
        with self.lock:
            try:
                if fmt == "hex":
                    payload = bytes.fromhex(payload_raw.replace(" ", ""))
                else:
                    payload = payload_raw.encode('utf-8').decode('unicode_escape').encode('utf-8')
                
                print(f"[Projector DEBUG] [串口 RS232] 实际发出的 16 进制数据 -> {payload.hex(' ').upper()}")
                with serial.Serial(com_port, baudrate, timeout=1.5) as ser:
                    ser.flushInput()
                    ser.write(payload)
                    time.sleep(0.2)
                    res = ser.read_all()
                    
                    if not res:
                        print(f"[Projector DEBUG] [串口 RS232] 投影机未返回任何数据")
                    else:
                        print(f"[Projector DEBUG] [串口 RS232] 收到返回数据 -> HEX: {res.hex(' ').upper()} | STR: {res.decode('utf-8', errors='ignore')}")
                        
                    return True, f"串口返回：{res.hex(' ').upper() if fmt=='hex' else res.decode('utf-8', errors='ignore')}"
            except Exception as e:
                print(f"[Projector DEBUG] [串口 RS232] 发生异常：{str(e)}\n{traceback.format_exc()}")
                return False, f"串口通讯失败：{str(e)}"

    def _send_appotronics_dh_tcp(self, payload, fmt):
        """光峰 DH 系列 TCP 协议 (端口 9761)"""
        ip = self.cfg.get("ip")
        port = int(self.cfg.get("port", 9761))

        print(f"\n{'='*60}")
        print(f"[光峰 DH TCP] 开始发送指令")
        print(f"{'='*60}")
        print(f"[光峰 DH TCP] 目标地址: {ip}:{port}")
        print(f"[光峰 DH TCP] 投影机名称: {self.cfg.get('name', '未命名')}")

        try:
            # 解析 payload
            if fmt == "hex":
                payload_bytes = bytes.fromhex(payload.replace(" ", ""))
            else:
                payload_bytes = payload.encode('utf-8')

            print(f"[光峰 DH TCP] 原始指令 (HEX): {payload}")
            print(f"[光峰 DH TCP] 字节长度: {len(payload_bytes)} bytes")
            print(f"[光峰 DH TCP] 字节数据: {' '.join(f'{b:02X}' for b in payload_bytes)}")

            # 建立 TCP 连接
            print(f"[光峰 DH TCP] 正在建立 TCP 连接...")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5.0)
                s.connect((ip, port))
                print(f"[光峰 DH TCP] [OK] TCP 连接成功")

                # 发送数据
                print(f"[光峰 DH TCP] 正在发送数据...")
                s.sendall(payload_bytes)
                print(f"[光峰 DH TCP] [OK] 数据发送成功")

                # 等待响应
                print(f"[光峰 DH TCP] 等待设备响应...")
                time.sleep(0.5)
                s.settimeout(3.0)

                try:
                    res = s.recv(1024)
                    if res:
                        res_hex = ' '.join(f'{b:02X}' for b in res)
                        print(f"[光峰 DH TCP] [OK] 收到响应:")
                        print(f"[光峰 DH TCP]   响应长度: {len(res)} bytes")
                        print(f"[光峰 DH TCP]   响应数据: {res_hex}")
                        print(f"{'='*60}\n")
                        return True, f"控制完成，响应：{res_hex}"
                    else:
                        print(f"[光峰 DH TCP] [WARN] 连接被关闭，无响应数据")
                        print(f"{'='*60}\n")
                        return True, "已发送 (无响应)"

                except socket.timeout:
                    print(f"[光峰 DH TCP] [WARN] 读取超时 (3秒内无响应)")
                    print(f"[光峰 DH TCP] 注: 部分指令可能不返回数据，这是正常的")
                    print(f"{'='*60}\n")
                    return True, "已发送 (超时无响应)"

        except socket.timeout:
            print(f"[光峰 DH TCP] [ERROR] 连接超时")
            print(f"[光峰 DH TCP] 请检查:")
            print(f"[光峰 DH TCP]   1. IP 地址是否正确: {ip}")
            print(f"[光峰 DH TCP]   2. 端口是否正确: {port}")
            print(f"[光峰 DH TCP]   3. 网络是否连通")
            print(f"{'='*60}\n")
            return False, f"连接超时 (IP: {ip}, Port: {port})"

        except ConnectionRefusedError:
            print(f"[光峰 DH TCP] [ERROR] 连接被拒绝")
            print(f"[光峰 DH TCP] 可能原因:")
            print(f"[光峰 DH TCP]   1. 投影机未开机")
            print(f"[光峰 DH TCP]   2. 端口 {port} 未开放")
            print(f"[光峰 DH TCP]   3. 防火墙阻止连接")
            print(f"{'='*60}\n")
            return False, f"连接被拒绝 (IP: {ip}, Port: {port})"

        except Exception as e:
            print(f"[光峰 DH TCP] [ERROR] 发生异常: {str(e)}")
            print(f"[光峰 DH TCP] 异常详情:")
            import traceback
            print(traceback.format_exc())
            print(f"{'='*60}\n")
            return False, f"通讯失败：{str(e)}"

    def _tcp_ping(self):
        """TCP 连通性检测"""
        ip = self.cfg.get("ip")
        port = int(self.cfg.get("port", 9761))
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((ip, port))
                return True
        except:
            return False

    def _extract_response_hex(self, res):
        if not isinstance(res, str):
            return ""
        for marker in ["响应:", "鍝嶅簲:", ":"]:
            if marker in res:
                res = res.split(marker, 1)[-1]
        return res.strip().replace(" ", "")

    def _query_appotronics_dh_hex(self, payload_hex):
        success, res = self._send_appotronics_dh_tcp(payload_hex, "hex")
        if not success:
            return None
        try:
            res_hex = self._extract_response_hex(res)
            return bytes.fromhex(res_hex) if res_hex else None
        except Exception:
            return None

    def get_status(self):
        """查询投影机状态 (电源、输入源、灯泡、故障等)。"""
        status = {
            "online": False,
            "power": "unknown",
            "temp": None,
            "temp_status": None,
            "lamp_hours": None,
            "lamp_state": None,
            "filter_hours": None,
            "lamp_model": None,
            "filter_model": None,
            "source": None,
            "source_code": None,
            "source_name": None,
            "error": None,
            "error_code": None,
            "error_details": None,
            "av_mute": None,
            "freeze_status": None,
            "input_list": [],
            "input_list_labels": [],
            "input_resolution": None,
            "recommended_resolution": None,
            "device_name": None,
            "manufacturer": None,
            "product_name": None,
            "other_info": None,
            "class_version": None,
            "serial_number": None,
            "software_version": None
        }

        if self.control_type == "inferred_rs232":
            return infer_rs232_projector_status(self.cfg)

        if self.control_type == "pjlink":
            power_map = {
                "0": "off",
                "1": "on",
                "2": "cooling",
                "3": "warming"
            }
            input_type_map = {
                "1": "RGB",
                "2": "VIDEO",
                "3": "DIGITAL",
                "4": "STORAGE",
                "5": "NETWORK"
            }
            input_label_map = {
                "11": "VGA1",
                "12": "VGA2",
                "13": "DVI",
                "21": "VIDEO1",
                "22": "VIDEO2",
                "31": "HDMI1",
                "32": "HDMI2",
                "33": "HDMI3",
                "51": "NETWORK",
                "52": "HDBASET"
            }
            av_map = {
                "11": "仅视频静音",
                "21": "仅音频静音",
                "31": "视音频静音",
                "30": "关闭"
            }

            def format_input_code(code):
                code = (code or "").strip()
                if not code:
                    return None
                if code in input_label_map:
                    return input_label_map[code]
                if len(code) >= 2:
                    return f"{input_type_map.get(code[0], 'INPUT')}{code[1:]}"
                return code
            erst_level_map = {
                "0": "正常",
                "1": "预警",
                "2": "故障"
            }

            try:
                session, prefix = self._open_pjlink_session()
            except Exception as e:
                status["error"] = str(e)
                return status

            def send_query(command):
                return self._send_pjlink_on_session(session, prefix, command)

            try:
                success, res = send_query("%1POWR ?")
                if not success:
                    status["error"] = res
                    return status

                status["online"] = True
                if "=" in res:
                    power_code = res.split("=", 1)[-1].strip()
                    status["power"] = power_map.get(power_code, power_code or "unknown")

                success, res = send_query("%1INPT ?")
                if success and "=" in res:
                    source_code = res.split("=", 1)[-1].strip()
                    status["source_code"] = source_code
                    status["source"] = format_input_code(source_code) or source_code
                elif not success and isinstance(res, str) and "ERR2" in res:
                    status["source"] = "查询不支持"

                success, res = send_query("%1AVMT ?")
                if success and "=" in res:
                    av_code = res.split("=", 1)[-1].strip()
                    status["av_mute"] = av_map.get(av_code, av_code)

                success, res = send_query("%1LAMP ?")
                if success and "=" in res:
                    lamp_info = res.split("=", 1)[-1].strip().split()
                    if lamp_info:
                        try:
                            status["lamp_hours"] = int(lamp_info[0])
                        except Exception:
                            status["lamp_hours"] = lamp_info[0]
                    if len(lamp_info) >= 2:
                        status["lamp_state"] = "开启" if lamp_info[1] == "1" else ("关闭" if lamp_info[1] == "0" else lamp_info[1])
                elif not success and isinstance(res, str) and any(code in res for code in ["ERR1", "ERR2"]):
                    status["lamp_hours"] = None
                    status["lamp_state"] = "不支持"

                success, res = send_query("%1ERST ?")
                if success and "=" in res:
                    erst_value = res.split("=", 1)[-1].strip()
                    status["error_code"] = erst_value
                    if len(erst_value) >= 6:
                        detail_keys = ["fan", "lamp", "temperature", "cover", "filter", "other"]
                        status["error_details"] = {
                            key: erst_level_map.get(erst_value[idx], "??")
                            for idx, key in enumerate(detail_keys)
                        }
                        status["temp_status"] = status["error_details"]["temperature"]
                        if "2" in erst_value[:6]:
                            status["error"] = "故障"
                        elif "1" in erst_value[:6]:
                            status["error"] = "预警"
                        else:
                            status["error"] = "正常"
                    else:
                        status["error"] = erst_value

                success, res = send_query("%1INST ?")
                if success and "=" in res:
                    status["input_list"] = [item for item in res.split("=", 1)[-1].strip().split(" ") if item]
                    status["input_list_labels"] = [format_input_code(item) or item for item in status["input_list"]]

                info_commands = {
                    "device_name": "%1NAME ?",
                    "manufacturer": "%1INF1 ?",
                    "product_name": "%1INF2 ?",
                    "other_info": "%1INFO ?",
                    "class_version": "%1CLSS ?"
                }
                for key, command in info_commands.items():
                    success, res = send_query(command)
                    if success and "=" in res:
                        value = res.split("=", 1)[-1].strip()
                        status[key] = value or None
                    elif not success and isinstance(res, str):
                        if "ERR1" in res:
                            status[key] = "不支持"
                        elif "ERR3" in res:
                            status[key] = "当前不可用"

                if status.get("class_version") == "2":
                    class2_queries = {
                        "serial_number": "%2SNUM ?",
                        "software_version": "%2SVER ?",
                        "input_resolution": "%2IRES ?",
                        "recommended_resolution": "%2RRES ?",
                        "filter_model": "%2RFIL ?",
                        "lamp_model": "%2RLMP ?",
                        "freeze_status": "%2FREZ ?"
                    }
                    for key, command in class2_queries.items():
                        success, res = send_query(command)
                        if success and "=" in res:
                            value = res.split("=", 1)[-1].strip()
                            if key == "freeze_status":
                                status[key] = "开启" if value == "1" else ("关闭" if value == "0" else (value or None))
                            elif key == "input_resolution":
                                status[key] = None if value in ["-", "*", ""] else value
                            elif key == "recommended_resolution":
                                status[key] = "不适用" if value == "NA" else (value or None)
                            elif key == "software_version":
                                status[key] = value or None
                            else:
                                status[key] = value or None
                        elif isinstance(res, str):
                            if "ERR1" in res:
                                status[key] = "不支持"
                            elif "ERR3" in res:
                                status[key] = "当前不可用"

                    success, res = send_query("%2FILT ?")
                    if success and "=" in res:
                        filt_value = res.split("=", 1)[-1].strip()
                        if filt_value not in ["ERR1", "ERR2", "NA", ""]:
                            try:
                                status["filter_hours"] = int(filt_value)
                            except Exception:
                                status["filter_hours"] = filt_value
                        elif filt_value == "NA":
                            status["filter_hours"] = "不适用"
                    elif isinstance(res, str):
                        if "ERR1" in res:
                            status["filter_hours"] = "不支持"
                        elif "ERR3" in res:
                            status["filter_hours"] = "当前不可用"

                    source_code = status.get("source_code")
                    if source_code:
                        success, res = send_query(f"%2INNM ? {source_code}")
                        if success and "=" in res:
                            status["source_name"] = res.split("=", 1)[-1].strip() or None

                return status
            finally:
                try:
                    session.close()
                except Exception:
                    pass

        if self.control_type == "appotronics_dh_tcp":
            status["online"] = self._tcp_ping()
            if not status["online"]:
                return status

            power_resp = self._query_appotronics_dh_hex("EB 90 00 0C 00 00 08 01 80 5B 00 6B")
            if power_resp and len(power_resp) >= 11:
                try:
                    data_byte = power_resp[10]
                    power_map = {
                        0x00: "off",
                        0x01: "off",
                        0x02: "on",
                        0x03: "cooling",
                        0x04: "warning",
                        0x05: "warming"
                    }
                    status["power"] = power_map.get(data_byte, "unknown")
                    if data_byte == 0x04:
                        status["error"] = "告警"
                except Exception as e:
                    print(f"[光峰 DH] 电源状态解析失败: {e}")

            power_on_state_resp = self._query_appotronics_dh_hex("EB 90 00 0C 00 00 08 02 00 0C 00 9D")
            if power_on_state_resp and len(power_on_state_resp) >= 11:
                try:
                    power_on_state = power_on_state_resp[10]
                    if status["power"] in [None, "unknown", "warning"]:
                        status["power"] = "on" if power_on_state == 0x01 else "off"
                except Exception:
                    pass

            temp_resp = self._query_appotronics_dh_hex("EB 90 00 0C 00 00 08 01 80 5C 00 6C")
            if temp_resp and len(temp_resp) >= 11:
                try:
                    status["temp"] = int(temp_resp[10])
                except Exception:
                    pass

            lamp_resp = self._query_appotronics_dh_hex("EB 90 00 0C 00 00 08 01 80 61 00 71")
            if lamp_resp and len(lamp_resp) >= 14:
                try:
                    status["lamp_hours"] = int.from_bytes(lamp_resp[10:14], byteorder="big", signed=False)
                except Exception:
                    pass

            power_save_resp = self._query_appotronics_dh_hex("EB 90 00 0C 00 00 08 01 80 0A 00 1A")
            if power_save_resp and len(power_save_resp) >= 11:
                try:
                    save_byte = power_save_resp[10]
                    status["other_info"] = f"节能模式: {'开启' if save_byte == 0x01 else '关闭'}"
                except Exception:
                    pass

            power_mode_resp = self._query_appotronics_dh_hex("EB 90 00 0C 00 00 08 02 00 0E 00 9F")
            if power_mode_resp and len(power_mode_resp) >= 11:
                try:
                    mode_byte = power_mode_resp[10]
                    mode_text = "待机" if mode_byte == 0x00 else ("上电自启" if mode_byte == 0x01 else f"未知({mode_byte})")
                    if status.get("other_info"):
                        status["other_info"] += f" | 上电模式: {mode_text}"
                    else:
                        status["other_info"] = f"上电模式: {mode_text}"
                except Exception:
                    pass

            return status

        if self.normalized_brand_id == "smile" and self.control_type in ["smile_ek_tcp", "smile_ek_udp", "smile_ek_com", "rs232"]:
            query_map = {
                "power": "#PWR0,?",
                "source": "#SOUR0,?",
                "volume": "#VOL0,?",
                "av_mute": "#AVMT0,?",
                "temp": "#TEMP0,?",
                "lamp": "#LAMP0,?"
            }
            source_map = {
                "01": "PC",
                "02": "VGA",
                "03": "DVI",
                "17": "HDMI1",
                "18": "HDMI2",
                "19": "DP"
            }
            power_success, power_res = self._send_smile_query(query_map["power"], "str")
            _, power_value = self._parse_smile_kv_response(power_res)
            power_value = power_value or self._parse_smile_response_value(power_res)
            if power_success:
                status["online"] = True
                if power_value in ["1", "01", "ON", "on"]:
                    status["power"] = "on"
                elif power_value in ["0", "00", "OFF", "off"]:
                    status["power"] = "off"
                elif power_value in ["2", "02"]:
                    status["power"] = "cooling"
                elif power_value in ["3", "03"]:
                    status["power"] = "warming"
                elif power_value:
                    status["power"] = power_value
            else:
                status["error"] = power_res or "电源状态查询失败"
                return status

            source_success, source_res = self._send_smile_query(query_map["source"], "str")
            _, source_value = self._parse_smile_kv_response(source_res)
            source_value = source_value or self._parse_smile_response_value(source_res)
            if source_success and source_value:
                status["source_code"] = source_value
                status["source"] = source_map.get(source_value, source_value)
                status["source_name"] = status["source"]

            mute_success, mute_res = self._send_smile_query(query_map["av_mute"], "str")
            _, mute_value = self._parse_smile_kv_response(mute_res)
            mute_value = mute_value or self._parse_smile_response_value(mute_res)
            if mute_success and mute_value is not None:
                status["av_mute"] = "开启" if mute_value in ["1", "01", "ON", "on"] else ("关闭" if mute_value in ["0", "00", "OFF", "off"] else mute_value)

            volume_success, volume_res = self._send_smile_query(query_map["volume"], "str")
            _, volume_value = self._parse_smile_kv_response(volume_res)
            volume_value = volume_value or self._parse_smile_response_value(volume_res)
            if volume_success and volume_value:
                status["other_info"] = f"音量: {volume_value}"

            temp_success, temp_res = self._send_smile_query(query_map["temp"], "str")
            _, temp_value = self._parse_smile_kv_response(temp_res)
            temp_value = temp_value or self._parse_smile_response_value(temp_res)
            if temp_success and temp_value:
                try:
                    status["temp"] = int(float(temp_value))
                    status["temp_status"] = "正常" if status["temp"] < 60 else "预警"
                except Exception:
                    status["temp_status"] = temp_value

            lamp_success, lamp_res = self._send_smile_query(query_map["lamp"], "str")
            _, lamp_value = self._parse_smile_kv_response(lamp_res)
            lamp_value = lamp_value or self._parse_smile_response_value(lamp_res)
            if lamp_success and lamp_value:
                lamp_parts = [item for item in lamp_value.replace("/", " ").split() if item]
                if lamp_parts:
                    try:
                        status["lamp_hours"] = int(float(lamp_parts[0]))
                    except Exception:
                        status["lamp_hours"] = lamp_parts[0]
                if len(lamp_parts) >= 2:
                    lamp_state_value = lamp_parts[1]
                    status["lamp_state"] = "开启" if lamp_state_value in ["1", "01", "ON", "on"] else ("关闭" if lamp_state_value in ["0", "00", "OFF", "off"] else lamp_state_value)
                elif status["power"] == "on":
                    status["lamp_state"] = "开启"
                elif status["power"] == "off":
                    status["lamp_state"] = "关闭"

            status["manufacturer"] = status.get("manufacturer") or "视美乐"
            status["product_name"] = status.get("product_name") or self.cfg.get("fixed_model") or self.cfg.get("name")
            status["software_version"] = status.get("software_version") or self.cfg.get("fixed_software_version")

            if not status["error"]:
                status["error"] = "正常"
            return status

        # 加载状态查询配置
        series_info = get_series_info(self.normalized_brand_id, self.normalized_series_id)
        status_queries = series_info.get('status_queries', {}) if series_info else {}
        status_parse = series_info.get('status_parse', {}) if series_info else {}

        # 无状态查询配置时，用 TCP ping 判断在线
        if not status_queries:
            status["online"] = self._tcp_ping()
            return status
        
        # 查询电源状态
        if 'power' in status_queries:
            query_hex = status_queries['power']
            success, res = self.execute({"payload": query_hex, "format": "hex"})
            if success:
                status["online"] = True
                # 解析 DH 系列电源状态响应
                if status_parse and 'power' in status_parse:
                    # 响应格式：AA 01 01 02 00 00 00 XX (XX=01 开机，02 关机等)
                    try:
                        res_hex = res.replace(" ", "").upper()
                        if len(res_hex) >= 2:
                            status_code = res_hex[-2:]  # 最后两个字符
                            status["power"] = status_parse['power'].get(status_code, f"未知 ({status_code})")
                    except Exception as e:
                        print(f"[状态查询] 电源状态解析失败：{e}")
                else:
                    # 旧版解析逻辑
                    if "1" in res:
                        status["power"] = "on"
                    elif "0" in res:
                        status["power"] = "off"
        
        # 查询温度
        if 'temperature' in status_queries:
            query_hex = status_queries['temperature']
            success, res = self.execute({"payload": query_hex, "format": "hex"})
            if success:
                try:
                    # DH 系列温度响应解析
                    res_hex = res.replace(" ", "").upper()
                    if len(res_hex) >= 4:
                        # 假设温度值在响应的特定位置
                        temp_val = int(res_hex[-4:-2], 16)
                        status["temp"] = temp_val
                except Exception as e:
                    print(f"[状态查询] 温度解析失败：{e}")
        
        # 查询灯泡时长
        if 'lamp_hours' in status_queries:
            query_hex = status_queries['lamp_hours']
            success, res = self.execute({"payload": query_hex, "format": "hex"})
            if success:
                try:
                    # DH 系列灯泡时长响应解析
                    res_hex = res.replace(" ", "").upper()
                    if len(res_hex) >= 8:
                        # 假设时长值在响应的特定位置 (4 字节)
                        hours_val = int(res_hex[-8:-4], 16)
                        status["lamp_hours"] = hours_val
                except Exception as e:
                    print(f"[状态查询] 灯泡时长解析失败：{e}")
        
        # 查询信号源状态
        if 'signal_source' in status_queries:
            query_hex = status_queries['signal_source']
            success, res = self.execute({"payload": query_hex, "format": "hex"})
            if success:
                try:
                    # 解析 DH 系列信号源状态
                    if status_parse and 'signal_source' in status_parse:
                        res_hex = res.replace(" ", "").upper()
                        if len(res_hex) >= 2:
                            source_code = res_hex[-2:]
                            status["source"] = status_parse['signal_source'].get(source_code, f"未知 ({source_code})")
                except Exception as e:
                    print(f"[状态查询] 信号源解析失败：{e}")
        
        # 查询错误状态
        if 'error' in status_queries:
            query_hex = status_queries['error']
            success, res = self.execute({"payload": query_hex, "format": "hex"})
            if success:
                try:
                    res_hex = res.replace(" ", "").upper()
                    if len(res_hex) >= 2:
                        error_code = res_hex[-2:]
                        if error_code == "00":
                            status["error"] = "正常"
                        else:
                            status["error"] = f"错误 ({error_code})"
                except Exception as e:
                    print(f"[状态查询] 错误状态解析失败：{e}")
        
        return status
