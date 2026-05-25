# AI_MODULE: config_defaults_and_migrations
# AI_PURPOSE: 保存默认配置、配置归一化、旧字段兼容迁移和 config.json 持久化。
# AI_BOUNDARY: 不直接访问真实设备；设备通信应放在 modbus_core、services、drivers 或 background。
# AI_DATA_FLOW: /srv/smart-center-data/config.json -> CONFIG 全局对象 -> API、后台轮询、前端配置页。
# AI_RUNTIME: 应用启动时导入并归一化配置；配置中心保存时调用 save_config。
# AI_RISK: 高，默认值和迁移会影响强电、空调、SNMP、Agent、自动化等全系统行为。
# AI_COMPAT: 旧部署字段、前端表单字段、外部 Agent 配置字段不能随意删除。
# AI_SEARCH_KEYWORDS: CONFIG, save_config, normalize, DEFAULT_*, migration, config center.

import json
import os
import tempfile
from datetime import datetime
from copy import deepcopy
from urllib.parse import urlsplit, urlunsplit
from control_center_core import DEFAULT_CONTROL_CENTER, normalize_control_center
from paths import (
    CONFIG_FILE as CONFIG_FILE_PATH,
    PROJECTOR_BRANDS_FILE,
    ensure_parent_dir,
)

CONFIG_FILE = str(CONFIG_FILE_PATH)
SERVER_COMMANDS = {}

DEFAULT_UI_TEXT = {
    "title_main": "演播中控调度引擎", "system_config": "系统配置", "back_to_home": "返回主页",
    "save_config": "保存配置", "operation_log": "操作日志", "cabinet_info": "电柜信息",
    "ui_text_config": "界面文字配置", "label_cabinet_name": "电柜名称", "label_station_id": "站号",
    "label_comm_type": "通讯方式", "label_local_ip_port": "本机地址", "label_comm_status_title": "通讯状态：",
    "label_phase": "实时三相电参数", "label_phase_a": "A：", "label_phase_b": "B：", "label_phase_c": "C：",
    "label_energy": "累计电能统计", "label_today_energy": "今日累计：", "label_month_energy_suffix": "月累计电能统计：",
    "label_realtime_power": "实时功率(kW)：", "label_temp": "柜体温度", "label_humidity": "柜体湿度",
    "label_relay_title": "输出通道状态", "label_channel": "通道", "label_on": "合闸", "label_off": "断开",
    "label_mode_manual": "手动模式", "label_mode_remote": "远程模式", "label_mode_external": "外控模式",
    "label_mode_unknown": "未知模式", "label_kwh": "kWh", "onekey_start": "一键启动", "onekey_stop": "一键停止",
    "confirm_stop": "确定要停止该电柜所有通道吗？", "confirm_single_off": "确定要关闭此通道吗？",
    "alert_control_fail": "控制失败，请检查通讯！", "label_energy_chart": "近7日用电量统计",
    "label_day": "日期", "label_energy_consume": "用电量(kWh)", "comm_status_normal": "正常", "comm_status_error": "异常"
}

DEFAULT_SIDEBAR = [
    {"id": "dashboard", "icon": "📊", "name": "场馆总览", "sort": 1, "visible": True},
    {"id": "power", "icon": "⚡", "name": "强电控制", "sort": 2, "visible": True},
    {"id": "m32r", "icon": "🎛", "name": "M32R 控台", "sort": 3, "visible": True},
    {"id": "meter", "icon": "🔋", "name": "电表中心", "sort": 3, "visible": True},
    {"id": "current_collector", "icon": "∿", "name": "电流采集", "sort": 3.4, "visible": True},
    {"id": "ups", "icon": "🔌", "name": "UPS监测", "sort": 4, "visible": True},
    {"id": "light", "icon": "💡", "name": "场馆灯光", "sort": 5, "visible": True},
    {"id": "door", "icon": "🚪", "name": "门禁与监控", "sort": 6, "visible": True},
    {"id": "scene", "icon": "🎬", "name": "场景联动", "sort": 7, "visible": True},
    {"id": "server", "icon": "🖥️", "name": "服务器看板", "sort": 8, "visible": True},
    {"id": "projector", "icon": "🎥", "name": "投影机集群", "sort": 9, "visible": True},
    {"id": "universal", "icon": "🎛️", "name": "协议控制", "sort": 10, "visible": True},
    {"id": "local_model", "icon": "AI", "name": "本地模型", "sort": 10.5, "visible": True},
    {"id": "env", "icon": "🌡️", "name": "环境监测", "sort": 11, "visible": True},
    {"id": "auto", "icon": "🤖", "name": "自动化运行", "sort": 12, "visible": True}
]

DEFAULT_REGION = {"p_x1": 0.2, "p_y1": 0.2, "p_x2": 0.8, "p_y2": 0.8}

DEFAULT_DOOR_CONFIG = {
    "rtsp_url": "",
    "match_threshold": 1500,
    "match_thresholds": {"main": 1500, "aux": 1500},
    "ip": "192.168.50.51",
    "port": 50000,
    "preferred_detection_camera": "main",
    "camera_probe_timeout_sec": 4,
    "camera_reconnect_delay_sec": 2,
    "cameras": [
        {"key": "main", "name": "大门内", "rtsp_url": "rtsp://admin:lanjingkeji798@192.168.40.11:554/Streaming/Channels/101", "enabled": True, "host": "192.168.40.11"},
        {"key": "aux", "name": "大门外", "rtsp_url": "rtsp://admin:lanjingkeji798@192.168.40.41:554/Streaming/Channels/101", "enabled": True, "host": "192.168.40.41"},
    ],
    "view_slots": {"left": "main", "right": "aux"},
    "regions": {
        "main": {"p_x1": 0.2, "p_y1": 0.2, "p_x2": 0.8, "p_y2": 0.8},
        "aux": {"p_x1": 0.2, "p_y1": 0.2, "p_x2": 0.8, "p_y2": 0.8},
    },
    "region_pct": {"p_x1": 0.2, "p_y1": 0.2, "p_x2": 0.8, "p_y2": 0.8},
    "vision": {
        "enabled": False,
        "provider": "legacy",
        "http_url": "http://127.0.0.1:18080/infer/door_state",
        "request_timeout_ms": 700,
        "poll_interval_sec": 0.5,
        "fusion_enabled": True,
        "fusion_settle_frames": 3,
        "fusion_history_size": 8,
        "fusion_min_confidence": 0.55,
        "fusion_margin": 0.15,
        "allow_shared_reference": False,
        "camera_weights": {"main": 1.0, "aux": 1.0},
        "people_count_enabled": False,
        "zone_count_enabled": False,
        "zones": {
            "main": {},
            "aux": {},
        },
        "http_send_full_frame": False,
    },
}

DEFAULT_CURRENT_COLLECTOR = {
    "enabled": True,
    "name": "16路电流采集器",
    "source_mode": "poll",
    "transport": "tcp-rtu",
    "host": "192.168.50.109",
    "port": 502,
    "serial_port": "COM7",
    "baudrate": 9600,
    "bytesize": 8,
    "parity": "N",
    "stopbits": 1,
    "slave": 1,
    "register": 0x0000,
    "count": 16,
    "scale": 100.0,
    "multiplier": 1.0,
    "timeout": 2.0,
    "poll_interval": 5.0,
    "push_stale_seconds": 15.0,
    "push_allowed_hosts": ["127.0.0.1", "::1", "192.168.50.121", "100.122.235.56"],
    "push_token": "",
    "reject_sparse_push": False,
    "min_valid_channels": 0,
    "channels": [{"channel": index, "name": f"第{index}路", "visible": True} for index in range(1, 17)],
    "groups": [],
}


def _clone_rtsp_url_with_host(rtsp_url, host_value):
    base_url = str(rtsp_url or "").strip()
    host_value = str(host_value or "").strip()
    if not base_url or not host_value:
        return ""
    try:
        parsed = urlsplit(base_url)
    except Exception:
        return base_url
    if not parsed.scheme:
        return base_url

    port = parsed.port
    host_part = host_value
    if not host_value.startswith("[") and host_value.count(":") == 1:
        maybe_host, maybe_port = host_value.rsplit(":", 1)
        if maybe_port.isdigit():
            host_part = maybe_host
            port = int(maybe_port)

    if ":" in host_part and not host_part.startswith("["):
        host_part = f"[{host_part}]"

    auth = ""
    if parsed.username:
        auth = parsed.username
        if parsed.password is not None:
            auth += f":{parsed.password}"
        auth += "@"

    netloc = auth + host_part
    if port:
        netloc += f":{port}"

    return urlunsplit((parsed.scheme, netloc, parsed.path or "", parsed.query or "", parsed.fragment or ""))


def _normalize_door_region(region_value, fallback=None):
    fallback_region = deepcopy(fallback or DEFAULT_REGION)
    region = deepcopy(fallback_region)
    if isinstance(region_value, dict):
        for key in ("p_x1", "p_y1", "p_x2", "p_y2"):
            try:
                region[key] = float(region_value.get(key, region[key]))
            except Exception:
                region[key] = fallback_region[key]
    for key in ("p_x1", "p_y1", "p_x2", "p_y2"):
        region[key] = max(0.0, min(float(region.get(key, fallback_region[key])), 1.0))
    if region["p_x2"] <= region["p_x1"]:
        region["p_x1"] = fallback_region["p_x1"]
        region["p_x2"] = fallback_region["p_x2"]
    if region["p_y2"] <= region["p_y1"]:
        region["p_y1"] = fallback_region["p_y1"]
        region["p_y2"] = fallback_region["p_y2"]
    return region


def _sanitize_door_config(door_config):
    merged = deepcopy(DEFAULT_DOOR_CONFIG)
    if isinstance(door_config, dict):
        for key, value in door_config.items():
            if key == "region_pct" and isinstance(value, dict):
                merged["region_pct"].update(value)
            elif key == "cameras" and isinstance(value, list):
                normalized_cameras = []
                default_map = {str(item.get("key") or ""): deepcopy(item) for item in DEFAULT_DOOR_CONFIG["cameras"]}
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    key_name = str(item.get("key") or f"camera_{len(normalized_cameras) + 1}").strip() or f"camera_{len(normalized_cameras) + 1}"
                    base = deepcopy(default_map.get(key_name, {"key": key_name, "name": key_name, "rtsp_url": "", "enabled": True}))
                    base.update(item)
                    base["key"] = key_name
                    base["name"] = str(base.get("name") or key_name).strip() or key_name
                    base["rtsp_url"] = str(base.get("rtsp_url") or "").strip()
                    base["enabled"] = bool(base.get("enabled", True))
                    normalized_cameras.append(base)
                if normalized_cameras:
                    merged["cameras"] = normalized_cameras
            else:
                merged[key] = value
    if not isinstance(merged.get("cameras"), list) or not merged["cameras"]:
        merged["cameras"] = deepcopy(DEFAULT_DOOR_CONFIG["cameras"])
    legacy_rtsp = str(merged.get("rtsp_url") or "").strip()
    camera_map = {}
    normalized = []
    for idx, item in enumerate(merged["cameras"]):
        if not isinstance(item, dict):
            continue
        key_name = str(item.get("key") or f"camera_{idx + 1}").strip() or f"camera_{idx + 1}"
        payload = {
            "key": key_name,
            "name": str(item.get("name") or key_name).strip() or key_name,
            "rtsp_url": str(item.get("rtsp_url") or "").strip(),
            "enabled": bool(item.get("enabled", True)),
        }
        if item.get("host") is not None:
            payload["host"] = str(item.get("host") or "").strip()
        if item.get("note") is not None:
            payload["note"] = str(item.get("note") or "").strip()
        normalized.append(payload)
        camera_map[key_name] = payload
    if "main" not in camera_map:
        camera_map["main"] = {"key": "main", "name": "大门内", "rtsp_url": legacy_rtsp or "rtsp://admin:lanjingkeji798@192.168.40.11:554/Streaming/Channels/101", "enabled": True, "host": "192.168.40.11"}
        normalized.insert(0, camera_map["main"])
    elif legacy_rtsp and not camera_map["main"].get("rtsp_url"):
        camera_map["main"]["rtsp_url"] = legacy_rtsp
    if not str(camera_map.get("main", {}).get("host") or "").strip():
        camera_map["main"]["host"] = "192.168.40.11"
    if "aux" not in camera_map:
        camera_map["aux"] = {"key": "aux", "name": "大门外", "rtsp_url": "", "enabled": True, "host": "192.168.40.41"}
        normalized.append(camera_map["aux"])
    elif not str(camera_map["aux"].get("host") or "").strip():
        camera_map["aux"]["host"] = "192.168.40.41"
    main_rtsp = str(camera_map.get("main", {}).get("rtsp_url") or legacy_rtsp).strip()
    aux_host = str(camera_map.get("aux", {}).get("host") or "").strip()
    if aux_host and not str(camera_map.get("aux", {}).get("rtsp_url") or "").strip() and main_rtsp:
        camera_map["aux"]["rtsp_url"] = _clone_rtsp_url_with_host(main_rtsp, aux_host)
    merged["cameras"] = normalized
    merged["rtsp_url"] = str(camera_map.get("main", {}).get("rtsp_url") or legacy_rtsp).strip()
    merged["preferred_detection_camera"] = str(merged.get("preferred_detection_camera") or "main").strip() or "main"
    available_keys = [item["key"] for item in normalized]
    if merged["preferred_detection_camera"] not in available_keys and available_keys:
        merged["preferred_detection_camera"] = available_keys[0]

    raw_view_slots = merged.get("view_slots", {}) if isinstance(merged.get("view_slots"), dict) else {}
    default_left = "main" if "main" in camera_map else (available_keys[0] if available_keys else "main")
    default_right = "aux" if "aux" in camera_map else (available_keys[0] if available_keys else default_left)
    left_slot = str(raw_view_slots.get("left") or default_left).strip() or default_left
    right_slot = str(raw_view_slots.get("right") or default_right).strip() or default_right
    if left_slot not in available_keys:
        left_slot = default_left
    if right_slot not in available_keys:
        right_slot = default_right
    if left_slot == right_slot and len(available_keys) > 1:
        other_key = next((key for key in available_keys if key != right_slot), right_slot)
        if right_slot == default_right:
            left_slot = other_key
        else:
            right_slot = other_key
    merged["view_slots"] = {"left": left_slot, "right": right_slot}

    legacy_region = merged.get("region_pct") if isinstance(merged.get("region_pct"), dict) else DEFAULT_REGION
    raw_regions = merged.get("regions", {}) if isinstance(merged.get("regions"), dict) else {}
    normalized_regions = {}
    for key in available_keys:
        fallback_region = legacy_region if key == merged["preferred_detection_camera"] else DEFAULT_REGION
        normalized_regions[key] = _normalize_door_region(raw_regions.get(key), fallback=fallback_region)
    merged["regions"] = normalized_regions
    merged["region_pct"] = deepcopy(
        normalized_regions.get(merged["preferred_detection_camera"])
        or _normalize_door_region(legacy_region, fallback=DEFAULT_REGION)
    )
    try:
        merged["camera_probe_timeout_sec"] = max(1, min(int(merged.get("camera_probe_timeout_sec", 4) or 4), 20))
    except Exception:
        merged["camera_probe_timeout_sec"] = 4
    try:
        merged["camera_reconnect_delay_sec"] = max(1, min(int(merged.get("camera_reconnect_delay_sec", 2) or 2), 20))
    except Exception:
        merged["camera_reconnect_delay_sec"] = 2
    raw_thresholds = merged.get("match_thresholds", {}) if isinstance(merged.get("match_thresholds"), dict) else {}
    normalized_thresholds = {}
    for key in available_keys:
        raw_value = raw_thresholds.get(key, merged.get("match_threshold", 1500))
        try:
            normalized_thresholds[key] = max(100, min(int(raw_value), 500000))
        except Exception:
            normalized_thresholds[key] = 1500
    merged["match_thresholds"] = normalized_thresholds
    preferred_key = merged.get("preferred_detection_camera")
    if preferred_key in normalized_thresholds:
        merged["match_threshold"] = int(normalized_thresholds[preferred_key])
    else:
        try:
            merged["match_threshold"] = max(100, min(int(merged.get("match_threshold", 1500) or 1500), 500000))
        except Exception:
            merged["match_threshold"] = 1500
    default_vision = deepcopy(DEFAULT_DOOR_CONFIG.get("vision", {}))
    raw_vision = merged.get("vision", {}) if isinstance(merged.get("vision"), dict) else {}
    normalized_vision = deepcopy(default_vision)
    for key, value in raw_vision.items():
        if key == "camera_weights" and isinstance(value, dict):
            sanitized_weights = {}
            for weight_key, weight_value in value.items():
                key_name = str(weight_key or "").strip()
                if not key_name:
                    continue
                try:
                    sanitized_weights[key_name] = max(float(weight_value), 0.0)
                except Exception:
                    continue
            if sanitized_weights:
                normalized_vision["camera_weights"] = sanitized_weights
            continue
        normalized_vision[key] = value

    normalized_vision["enabled"] = bool(normalized_vision.get("enabled", False))
    normalized_vision["fusion_enabled"] = bool(normalized_vision.get("fusion_enabled", True))
    normalized_vision["allow_shared_reference"] = bool(normalized_vision.get("allow_shared_reference", False))
    normalized_vision["people_count_enabled"] = bool(normalized_vision.get("people_count_enabled", False))
    normalized_vision["zone_count_enabled"] = bool(normalized_vision.get("zone_count_enabled", False))
    normalized_vision["http_send_full_frame"] = bool(normalized_vision.get("http_send_full_frame", False))
    normalized_vision["provider"] = str(normalized_vision.get("provider") or "legacy").strip() or "legacy"
    normalized_vision["http_url"] = str(normalized_vision.get("http_url") or default_vision.get("http_url", "")).strip()
    try:
        normalized_vision["request_timeout_ms"] = max(100, min(int(normalized_vision.get("request_timeout_ms", 700) or 700), 5000))
    except Exception:
        normalized_vision["request_timeout_ms"] = 700
    try:
        normalized_vision["poll_interval_sec"] = max(0.1, min(float(normalized_vision.get("poll_interval_sec", 0.5) or 0.5), 5.0))
    except Exception:
        normalized_vision["poll_interval_sec"] = 0.5
    try:
        normalized_vision["fusion_settle_frames"] = max(1, min(int(normalized_vision.get("fusion_settle_frames", 3) or 3), 30))
    except Exception:
        normalized_vision["fusion_settle_frames"] = 3
    try:
        normalized_vision["fusion_history_size"] = max(2, min(int(normalized_vision.get("fusion_history_size", 8) or 8), 50))
    except Exception:
        normalized_vision["fusion_history_size"] = 8
    try:
        normalized_vision["fusion_min_confidence"] = max(0.0, min(float(normalized_vision.get("fusion_min_confidence", 0.55) or 0.55), 1.0))
    except Exception:
        normalized_vision["fusion_min_confidence"] = 0.55
    try:
        normalized_vision["fusion_margin"] = max(0.0, min(float(normalized_vision.get("fusion_margin", 0.15) or 0.15), 1.0))
    except Exception:
        normalized_vision["fusion_margin"] = 0.15
    if not isinstance(normalized_vision.get("camera_weights"), dict):
        normalized_vision["camera_weights"] = deepcopy(default_vision.get("camera_weights", {}))
    raw_zones = normalized_vision.get("zones", {}) if isinstance(normalized_vision.get("zones"), dict) else {}
    normalized_zones = {}
    for cam_key in available_keys:
        cam_zone_cfg = raw_zones.get(cam_key, {}) if isinstance(raw_zones.get(cam_key), dict) else {}
        zone_map = {}
        for zone_name, points in cam_zone_cfg.items():
            zone_key = str(zone_name or "").strip()
            if not zone_key or not isinstance(points, list):
                continue
            clean_points = []
            for pt in points:
                if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                    continue
                try:
                    px = max(0.0, min(float(pt[0]), 1.0))
                    py = max(0.0, min(float(pt[1]), 1.0))
                except Exception:
                    continue
                clean_points.append([px, py])
            if len(clean_points) >= 3:
                zone_map[zone_key] = clean_points
        normalized_zones[cam_key] = zone_map
    normalized_vision["zones"] = normalized_zones
    merged["vision"] = normalized_vision
    return merged


def _normalize_current_collector_config(raw_config):
    merged = deepcopy(DEFAULT_CURRENT_COLLECTOR)
    if isinstance(raw_config, dict):
        merged.update(raw_config)
    merged["enabled"] = bool(merged.get("enabled", True))
    merged["name"] = str(merged.get("name") or DEFAULT_CURRENT_COLLECTOR["name"]).strip() or DEFAULT_CURRENT_COLLECTOR["name"]
    source_mode = str(merged.get("source_mode") or "poll").strip().lower()
    merged["source_mode"] = source_mode if source_mode in {"poll", "push"} else "poll"
    transport = str(merged.get("transport") or "tcp-rtu").strip().lower()
    if transport in {"serial", "rtu", "rtu_serial"}:
        transport = "serial"
    elif transport in {"modbus-tcp", "modbus_tcp", "tcp"}:
        transport = "modbus-tcp"
    else:
        transport = "tcp-rtu"
    merged["transport"] = transport
    merged["host"] = str(merged.get("host") or DEFAULT_CURRENT_COLLECTOR["host"]).strip() or DEFAULT_CURRENT_COLLECTOR["host"]
    merged["serial_port"] = str(merged.get("serial_port") or DEFAULT_CURRENT_COLLECTOR["serial_port"]).strip() or DEFAULT_CURRENT_COLLECTOR["serial_port"]
    int_ranges = {
        "port": (502, 1, 65535),
        "baudrate": (9600, 1200, 921600),
        "bytesize": (8, 5, 8),
        "stopbits": (1, 1, 2),
        "slave": (1, 1, 247),
        "register": (0, 0, 65535),
        "count": (16, 1, 32),
        "min_valid_channels": (0, 0, 32),
    }
    for key, (default, minimum, maximum) in int_ranges.items():
        try:
            merged[key] = max(minimum, min(int(str(merged.get(key, default)).strip(), 0), maximum))
        except Exception:
            merged[key] = default
    for key, default, minimum, maximum in (
        ("scale", 100.0, 0.001, 1000000.0),
        ("multiplier", 1.0, 0.0, 1000000.0),
        ("timeout", 1.0, 0.1, 10.0),
        ("poll_interval", 2.0, 0.5, 300.0),
        ("push_stale_seconds", 15.0, 2.0, 300.0),
    ):
        try:
            merged[key] = max(minimum, min(float(merged.get(key, default)), maximum))
        except Exception:
            merged[key] = default
    parity = str(merged.get("parity") or "N").strip().upper()
    merged["parity"] = parity if parity in {"N", "E", "O", "M", "S"} else "N"
    raw_channels = merged.get("channels") if isinstance(merged.get("channels"), list) else []
    channel_map = {}
    for item in raw_channels:
        if not isinstance(item, dict):
            continue
        try:
            channel = int(item.get("channel") or 0)
        except Exception:
            channel = 0
        if channel <= 0:
            continue
        try:
            sort = int(item.get("sort") or channel)
        except Exception:
            sort = channel
        channel_map[channel] = {
            "channel": channel,
            "name": str(item.get("name") or f"第{channel}路").strip() or f"第{channel}路",
            "visible": bool(item.get("visible", True)),
            "sort": sort,
        }
    merged["channels"] = [
        channel_map.get(index, {"channel": index, "name": f"第{index}路", "visible": True, "sort": index})
        for index in range(1, int(merged.get("count", 16) or 16) + 1)
    ]
    raw_allowed_hosts = merged.get("push_allowed_hosts")
    if isinstance(raw_allowed_hosts, str):
        raw_allowed_hosts = [item.strip() for item in raw_allowed_hosts.split(",")]
    if not isinstance(raw_allowed_hosts, list):
        raw_allowed_hosts = DEFAULT_CURRENT_COLLECTOR["push_allowed_hosts"]
    allowed_hosts = []
    for item in raw_allowed_hosts:
        host = str(item or "").strip()
        if host and host not in allowed_hosts:
            allowed_hosts.append(host)
    merged["push_allowed_hosts"] = allowed_hosts or DEFAULT_CURRENT_COLLECTOR["push_allowed_hosts"].copy()
    merged["push_token"] = str(merged.get("push_token") or "").strip()
    raw_groups = merged.get("groups") if isinstance(merged.get("groups"), list) else []
    groups = []
    for idx, item in enumerate(raw_groups, start=1):
        if not isinstance(item, dict):
            continue
        group_channels = []
        for channel in item.get("channels", []):
            try:
                channel_num = int(channel)
            except Exception:
                channel_num = 0
            if 1 <= channel_num <= int(merged.get("count", 16) or 16) and channel_num not in group_channels:
                group_channels.append(channel_num)
        if not group_channels:
            continue
        try:
            sort = int(item.get("sort") or idx)
        except Exception:
            sort = idx
        groups.append({
            "id": str(item.get("id") or f"group_{idx}").strip() or f"group_{idx}",
            "name": str(item.get("name") or f"组合 {idx}").strip() or f"组合 {idx}",
            "channels": group_channels,
            "visible": bool(item.get("visible", True)),
            "sort": sort,
        })
    merged["groups"] = groups
    return merged

DEFAULT_ENV_FEATURES = {
    "temperature": True,
    "humidity": True,
    "illuminance": True,
    "contact": True,
    "light": True,
    "battery": True,
    "voltage": True,
    "noise": False,
    "pm25": False,
    "pm10": False,
    "pressure": False
}

DEFAULT_ENV_PRIMARY_METRIC = "auto"

DEFAULT_ENV_MQTT = {
    "host": "127.0.0.1",
    "port": 1883,
    "username": "",
    "password": "",
    "topic": "",
    "availability_topic": "",
    "client_id": "",
    "keepalive": 60,
    "qos": 0,
    "stale_after_sec": 7200,
    "tls": False,
    "field_map": {
        "temp": "temperature",
        "hum": "humidity",
        "pressure": "pressure",
        "lux": "illuminance",
        "noise": "noise",
        "pm25": "pm25",
        "pm10": "pm10"
    }
}

DEFAULT_ENV_PUSH = {
    "stale_after_sec": 1200
}

DEFAULT_HOME_ASSISTANT = {
    "enabled": True,
    "base_url": "http://192.168.50.121:8123",
    "token": "",
    "timeout_sec": 5,
    "verify_ssl": True,
    "stale_after_sec": 7200,
    "entities": {},
    "attribute_map": {}
}

DEFAULT_HVAC_DEVICE = {
    "id": "hvac_miio_1",
    "name": "米家空调伴侣2",
    "room_name": "",
    "sort_order": 999,
    "brand": "Xiaomi",
    "model": "",
    "protocol": "miio",
    "ip": "",
    "token": "",
    "poll_interval_ms": 5000,
    "visible": True,
    "enabled": True
}

DEFAULT_METER_FEATURES = {
    "voltage": True,
    "current": True,
    "power": True,
    "energy_total": True,
    "energy_daily": True,
    "energy_monthly": True,
    "temperature": False,
    "humidity": False
}

DEFAULT_METER_STATISTICS = {
    "summary_mode": "include_flag",
    "display_reset_enabled": False,
    "display_reset_from": "",
    "energy_display_mode": "display",
    "report_dir": "reports\\energy",
    "auto_export_enabled": True,
    "history_keep_days": 90,
    "default_trend_mode": "total",
    "remote_service_enabled": False,
    "remote_service_mode": "remote_overlay_local",
    "remote_service_url": "",
    "remote_service_timeout_sec": 15,
    "remote_sync_on_save": False,
    "reference_total_meter_source_key": "",
    "cabinet_gateway_enabled": False,
    "cabinet_gateway_url": "",
    "cabinet_gateway_timeout_sec": 5,
    "cabinet_gateway_sync_on_save": False
}

DEFAULT_AUTH_SETTINGS = {
    "auto_login_default_admin": True,
    "default_admin_username": "local-admin"
}

DEFAULT_METER_REGISTER_MAP = {
    "voltage_a": {"enabled": False, "fc": 3, "address": 0, "count": 1, "data_type": "u16", "scale": 0.1, "byte_order": "AB"},
    "voltage_b": {"enabled": False, "fc": 3, "address": 0, "count": 1, "data_type": "u16", "scale": 0.1, "byte_order": "AB"},
    "voltage_c": {"enabled": False, "fc": 3, "address": 0, "count": 1, "data_type": "u16", "scale": 0.1, "byte_order": "AB"},
    "voltage_ab": {"enabled": False, "fc": 3, "address": 0, "count": 1, "data_type": "u16", "scale": 0.1, "byte_order": "AB"},
    "voltage_bc": {"enabled": False, "fc": 3, "address": 0, "count": 1, "data_type": "u16", "scale": 0.1, "byte_order": "AB"},
    "voltage_ca": {"enabled": False, "fc": 3, "address": 0, "count": 1, "data_type": "u16", "scale": 0.1, "byte_order": "AB"},
    "current_a": {"enabled": False, "fc": 3, "address": 0, "count": 1, "data_type": "u16", "scale": 0.1, "byte_order": "AB"},
    "current_b": {"enabled": False, "fc": 3, "address": 0, "count": 1, "data_type": "u16", "scale": 0.1, "byte_order": "AB"},
    "current_c": {"enabled": False, "fc": 3, "address": 0, "count": 1, "data_type": "u16", "scale": 0.1, "byte_order": "AB"},
    "realtime_power": {"enabled": False, "fc": 3, "address": 0, "count": 2, "data_type": "u32", "scale": 0.001, "byte_order": "ABCD"},
    "reactive_power": {"enabled": False, "fc": 3, "address": 0, "count": 1, "data_type": "u16", "scale": 0.001, "byte_order": "AB"},
    "apparent_power": {"enabled": False, "fc": 3, "address": 0, "count": 1, "data_type": "u16", "scale": 0.001, "byte_order": "AB"},
    "power_factor": {"enabled": False, "fc": 3, "address": 0, "count": 1, "data_type": "u16", "scale": 0.001, "byte_order": "AB"},
    "frequency": {"enabled": False, "fc": 3, "address": 0, "count": 1, "data_type": "u16", "scale": 0.01, "byte_order": "AB"},
    "electric_energy": {"enabled": False, "fc": 3, "address": 0, "count": 2, "data_type": "u32", "scale": 0.01, "byte_order": "ABCD"},
    "cabinet_temp": {"enabled": False, "fc": 3, "address": 0, "count": 1, "data_type": "s16", "scale": 0.1, "byte_order": "AB"},
    "cabinet_humidity": {"enabled": False, "fc": 3, "address": 0, "count": 1, "data_type": "u16", "scale": 0.1, "byte_order": "AB"}
}

DEFAULT_SERVER_MONITOR = {
    "agent_host": "",
    "agent_port": 6899,
    "scan_networks": [],
    "scan_workers": 8
}

DEFAULT_PROXY_MONITOR = {
    "enabled": True,
    "host": "192.168.50.121",
    "port": 3128,
    "timeout_sec": 6.0,
    "poll_interval_sec": 30.0,
    "check_urls": [
        "https://www.google.com/generate_204",
        "https://www.youtube.com/generate_204",
        "https://chatgpt.com",
        "https://github.com",
    ],
    "traffic_enabled": True,
    "traffic_source": "nic_ssh",
    "traffic_device_id": "",
    "traffic_host": "172.16.201.169",
    "traffic_ifindex": 0,
    "traffic_ifname": "enp1s0",
    "traffic_ssh_target": "node-121",
    "traffic_local_user": "xinping",
    "traffic_timeout_sec": 6.0,
    "client_monitor_enabled": True,
    "client_monitor_ssh_target": "node-121",
    "client_monitor_local_user": "xinping",
    "client_monitor_recent_seconds": 300,
    "client_monitor_tail_lines": 2000,
    "client_monitor_timeout_sec": 6.0,
}

DEFAULT_SNMP_OID_MAP = {
    "sys_descr": "1.3.6.1.2.1.1.1.0",
    "sys_object_id": "1.3.6.1.2.1.1.2.0",
    "sys_uptime": "1.3.6.1.2.1.1.3.0",
    "sys_contact": "1.3.6.1.2.1.1.4.0",
    "sys_name": "1.3.6.1.2.1.1.5.0",
    "sys_location": "1.3.6.1.2.1.1.6.0",
    "if_number": "1.3.6.1.2.1.2.1.0"
}

DEFAULT_SNMP_CUSTOM_OIDS = [
    {"name": "hr_memory_size_kb", "oid": "1.3.6.1.2.1.25.2.2.0", "value_type": "int", "scale": 1, "unit": "KB", "precision": 0, "enabled": True},
    {"name": "hr_system_processes", "oid": "1.3.6.1.2.1.25.1.6.0", "value_type": "int", "scale": 1, "unit": "", "precision": 0, "enabled": True},
    {"name": "hr_system_users", "oid": "1.3.6.1.2.1.25.1.5.0", "value_type": "int", "scale": 1, "unit": "", "precision": 0, "enabled": True}
]

DEFAULT_SNMP_CUSTOM_OIDS_NAS = DEFAULT_SNMP_CUSTOM_OIDS + [
    {"name": "ucd_load_1", "oid": "1.3.6.1.4.1.2021.10.1.3.1", "value_type": "float", "scale": 1, "unit": "", "precision": 2, "enabled": True},
    {"name": "ucd_load_5", "oid": "1.3.6.1.4.1.2021.10.1.3.2", "value_type": "float", "scale": 1, "unit": "", "precision": 2, "enabled": True},
    {"name": "ucd_load_15", "oid": "1.3.6.1.4.1.2021.10.1.3.3", "value_type": "float", "scale": 1, "unit": "", "precision": 2, "enabled": True},
    {"name": "ucd_mem_total_kb", "oid": "1.3.6.1.4.1.2021.4.5.0", "value_type": "int", "scale": 1, "unit": "KB", "precision": 0, "enabled": True},
    {"name": "ucd_mem_available_kb", "oid": "1.3.6.1.4.1.2021.4.6.0", "value_type": "int", "scale": 1, "unit": "KB", "precision": 0, "enabled": True},
    {"name": "ucd_mem_buffer_kb", "oid": "1.3.6.1.4.1.2021.4.14.0", "value_type": "int", "scale": 1, "unit": "KB", "precision": 0, "enabled": True},
    {"name": "ucd_mem_cached_kb", "oid": "1.3.6.1.4.1.2021.4.15.0", "value_type": "int", "scale": 1, "unit": "KB", "precision": 0, "enabled": True},
    {"name": "cpu_user_percent", "oid": "1.3.6.1.4.1.2021.11.9.0", "value_type": "float", "scale": 1, "unit": "%", "precision": 1, "enabled": True},
    {"name": "cpu_system_percent", "oid": "1.3.6.1.4.1.2021.11.10.0", "value_type": "float", "scale": 1, "unit": "%", "precision": 1, "enabled": True},
    {"name": "cpu_idle_percent", "oid": "1.3.6.1.4.1.2021.11.11.0", "value_type": "float", "scale": 1, "unit": "%", "precision": 1, "enabled": True},
]

DEFAULT_SNMP_CUSTOM_OIDS_QNAP = DEFAULT_SNMP_CUSTOM_OIDS_NAS + [
    {"name": "qnap_cpu_usage_percent", "oid": "1.3.6.1.4.1.24681.1.2.1.0", "value_type": "float", "scale": 1, "unit": "%", "precision": 1, "enabled": True},
    {"name": "vendor_memory_total", "oid": "1.3.6.1.4.1.24681.1.2.2.0", "value_type": "auto", "scale": 1, "unit": "", "precision": 0, "enabled": True},
    {"name": "vendor_memory_free", "oid": "1.3.6.1.4.1.24681.1.2.3.0", "value_type": "auto", "scale": 1, "unit": "", "precision": 0, "enabled": True},
]

DEFAULT_SNMP_CUSTOM_OIDS_ROUTER = [
    {"name": "hr_memory_size_kb", "oid": "1.3.6.1.2.1.25.2.2.0", "value_type": "int", "scale": 1, "unit": "KB", "precision": 0, "enabled": True},
    {"name": "hr_system_processes", "oid": "1.3.6.1.2.1.25.1.6.0", "value_type": "int", "scale": 1, "unit": "", "precision": 0, "enabled": True},
    {"name": "hr_system_users", "oid": "1.3.6.1.2.1.25.1.5.0", "value_type": "int", "scale": 1, "unit": "", "precision": 0, "enabled": True},
    {"name": "ucd_load_1", "oid": "1.3.6.1.4.1.2021.10.1.3.1", "value_type": "float", "scale": 1, "unit": "", "precision": 2, "enabled": True},
    {"name": "ucd_load_5", "oid": "1.3.6.1.4.1.2021.10.1.3.2", "value_type": "float", "scale": 1, "unit": "", "precision": 2, "enabled": True},
    {"name": "ucd_load_15", "oid": "1.3.6.1.4.1.2021.10.1.3.3", "value_type": "float", "scale": 1, "unit": "", "precision": 2, "enabled": True},
    {"name": "cpu_user_percent", "oid": "1.3.6.1.4.1.2021.11.9.0", "value_type": "float", "scale": 1, "unit": "%", "precision": 1, "enabled": True},
    {"name": "cpu_system_percent", "oid": "1.3.6.1.4.1.2021.11.10.0", "value_type": "float", "scale": 1, "unit": "%", "precision": 1, "enabled": True},
    {"name": "cpu_idle_percent", "oid": "1.3.6.1.4.1.2021.11.11.0", "value_type": "float", "scale": 1, "unit": "%", "precision": 1, "enabled": True},
    {"name": "temperature_c", "oid": "1.3.6.1.4.1.2021.13.16.2.1.3.1", "value_type": "float", "scale": 0.1, "unit": "°C", "precision": 1, "enabled": True},
    {"name": "cpu_temperature_c", "oid": "1.3.6.1.4.1.2021.13.16.2.1.3.1", "value_type": "float", "scale": 0.1, "unit": "°C", "precision": 1, "enabled": True},
    {"name": "session_count", "oid": "1.3.6.1.4.1.2021.255.1.1.1.0", "value_type": "int", "scale": 1, "unit": "", "precision": 0, "enabled": True},
    {"name": "network_connections", "oid": "1.3.6.1.4.1.2021.255.1.1.1.0", "value_type": "int", "scale": 1, "unit": "", "precision": 0, "enabled": True},
    {"name": "nat_sessions", "oid": "1.3.6.1.4.1.2021.255.1.1.2.0", "value_type": "int", "scale": 1, "unit": "", "precision": 0, "enabled": True},
    {"name": "online_clients", "oid": "1.3.6.1.4.1.2021.255.1.1.3.0", "value_type": "int", "scale": 1, "unit": "", "precision": 0, "enabled": True},
    {"name": "ap_count", "oid": "1.3.6.1.4.1.2021.255.1.1.4.0", "value_type": "int", "scale": 1, "unit": "", "precision": 0, "enabled": True},
]

DEFAULT_SNMP_CUSTOM_OIDS_SWITCH = []


def _normalize_snmp_device_type(value):
    text = str(value or "").strip().lower()
    if text in {"nas", "storage"}:
        return "nas"
    if text in {"router", "gateway", "route"}:
        return "router"
    if text in {"switch", "sw"}:
        return "switch"
    return "network"


def _dedupe_snmp_custom_oids(items):
    normalized = []
    seen = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        oid = str(item.get("oid", "")).strip()
        if not name or not oid:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "name": name,
                "oid": oid,
                "value_type": item.get("value_type", "auto"),
                "scale": item.get("scale", 1),
                "unit": item.get("unit", ""),
                "precision": item.get("precision", 0),
                "enabled": item.get("enabled", True),
            }
        )
    return normalized


def build_default_snmp_custom_oids(device_type, brand="", model=""):
    normalized_type = _normalize_snmp_device_type(device_type)
    brand_text = str(brand or "").strip().lower()
    model_text = str(model or "").strip().lower()

    if normalized_type == "switch":
        return _dedupe_snmp_custom_oids(DEFAULT_SNMP_CUSTOM_OIDS_SWITCH)
    if normalized_type == "router":
        return _dedupe_snmp_custom_oids(DEFAULT_SNMP_CUSTOM_OIDS_ROUTER)
    if normalized_type == "nas":
        if "qnap" in brand_text or "ts-" in model_text:
            return _dedupe_snmp_custom_oids(DEFAULT_SNMP_CUSTOM_OIDS_QNAP)
        return _dedupe_snmp_custom_oids(DEFAULT_SNMP_CUSTOM_OIDS_NAS)
    return _dedupe_snmp_custom_oids(DEFAULT_SNMP_CUSTOM_OIDS)

DEFAULT_SNMP_WALK_ROOTS = [
    "1.3.6.1.2.1.1",
    "1.3.6.1.2.1.25.3.3.1.2",
    "1.3.6.1.2.1.25.2.3.1.3",
    "1.3.6.1.2.1.25.2.3.1.4",
    "1.3.6.1.2.1.25.2.3.1.5",
    "1.3.6.1.2.1.25.2.3.1.6",
    "1.3.6.1.2.1.31.1.1.1.1",
    "1.3.6.1.2.1.31.1.1.1.6",
    "1.3.6.1.2.1.31.1.1.1.10",
    "1.3.6.1.2.1.31.1.1.1.18",
    "1.3.6.1.2.1.2.2.1.5",
    "1.3.6.1.2.1.2.2.1.7",
    "1.3.6.1.2.1.2.2.1.8"
]

DEFAULT_QNAP_STORAGE_ALIASES = {
    "/share/ZFS2_DATA": "Web",
    "/share/ZFS3_DATA": "Public",
    "/share/ZFS18_DATA": "市场部",
    "/share/ZFS19_DATA": "研学部",
    "/share/ZFS20_DATA": "研学部加密",
    "/share/ZFS21_DATA": "研学部加密内部研发资料",
    "/share/ZFS22_DATA": "XR",
    "/share/ZFS23_DATA": "ubuntu01",
    "/share/ZFS29_DATA": "技术部",
    "/share/ZFS530_DATA": "LUN_0",
}


def _is_qnap_snmp_device(snmp):
    brand_text = str((snmp or {}).get("brand") or "").strip().lower()
    model_text = str((snmp or {}).get("model") or "").strip().lower()
    host_text = str((snmp or {}).get("host") or "").strip()
    name_text = str((snmp or {}).get("name") or "").strip().lower()
    return (
        "qnap" in brand_text
        or "ts-" in model_text
        or host_text == "192.168.30.145"
        or "威联通" in name_text
    )

DEFAULT_M32R = {
    "enabled": False,
    "host": "192.168.50.32",
    "port": 10023,
    "name": "Midas M32R",
    "channel_count": 16,
    "bank_start": 1,
    "poll_interval_ms": 1200,
    "keepalive_sec": 5,
    "auto_connect": False,
    "auto_sync": False,
    "sync_direction": "mixer_to_pc",
    "known_mixers": []
}

DEFAULT_APPLE_AUDIO = {
    "enabled": True,
    "provider": "nas_music_tag",
    "player_mode": "nas_http",
    "player_host": "",
    "output_mode": "system_default",
    "auth_state": "NAS ready",
    "outputs": [],
    "nas_music_roots": [],
    "nas_music_exclude_dirs": [],
    "nas_auto_scan_on_start": True,
    "m32_channel_mode": "stereo_pair",
    "m32_channel_left": 17,
    "m32_channel_right": 18,
    "m32_label": "Music Player",
    "m32_prepare_level": 0.68,
    "m32_prepare_main": False
}

DEFAULT_SEQUENCER = {
    "id": "sequencer_ds608_1",
    "name": "DS-608 时序电源",
    "brand": "DGH",
    "model": "DS-608",
    "sku": "DS-608",
    "device_type": "时序器",
    "material": "铝合金",
    "color": "图片色",
    "protocol": "DGH 8路时序器",
    "comm_mode": "TCP",
    "ip": "192.168.50.53",
    "port": 8080,
    "address": 1,
    "baudrate": 19200,
    "data_bits": 8,
    "stop_bits": 1,
    "parity": "NONE",
    "channel_count": 8,
    "sequence_delay_ms": 500,
    "visible": True,
    "channels_config": [
        {"channel": 1, "name": "CH1", "sort": 1, "visible": True},
        {"channel": 2, "name": "CH2", "sort": 2, "visible": True},
        {"channel": 3, "name": "CH3", "sort": 3, "visible": True},
        {"channel": 4, "name": "CH4", "sort": 4, "visible": True},
        {"channel": 5, "name": "CH5", "sort": 5, "visible": True},
        {"channel": 6, "name": "CH6", "sort": 6, "visible": True},
        {"channel": 7, "name": "CH7", "sort": 7, "visible": True},
        {"channel": 8, "name": "CH8", "sort": 8, "visible": True}
    ]
}

DEFAULT_DASHBOARD_SECTIONS = {
    "stats": {"title": "顶部统计", "visible": True, "sort": 10},
    "projector": {"title": "投影机总览", "visible": True, "sort": 20},
    "hy_edge": {"title": "HY506-异地机房", "visible": True, "sort": 25},
    "sequencer": {"title": "时序电源", "visible": True, "sort": 25},
    "ups_compact": {"title": "UPS状态", "visible": True, "sort": 23},
    "ups": {"title": "UPS状态", "visible": True, "sort": 26},
    "snmp": {"title": "SNMP设备", "visible": True, "sort": 27.2},
    "screen": {"title": "幕布状态", "visible": True, "sort": 30},
    "light_compact": {"title": "灯光控制显示", "visible": True, "sort": 26},
    "power_compact": {"title": "强电柜状态", "visible": True, "sort": 27},
    "server_compact": {"title": "机器状态", "visible": True, "sort": 28},
    "power_quick": {"title": "强电快捷控制", "visible": False, "sort": 40},
    "light_quick": {"title": "灯光快捷控制", "visible": False, "sort": 50},
    "system_logs": {"title": "系统操作日志", "visible": True, "sort": 60}
}

DEFAULT_LOGIN_PAGE_TEXT = {
    "browser_title": "中控系统登录",
    "badge_text": "Smart Power Monitor",
    "hero_title": "场馆中控系统登录",
    "hero_description": "统一管理强电、灯光、时序电源、UPS、电表统计与服务器看板。登录后根据账号权限展示可查看和可操作的模块。",
    "feature_1_title": "访问控制",
    "feature_1_body": "按账号精细控制可见模块与操作权限",
    "feature_2_title": "设备保护",
    "feature_2_body": "核心控制接口支持服务端占用锁，避免多人同时误操作",
    "feature_3_title": "运行方式",
    "feature_3_body": "本地中控界面与 NAS 电力服务可独立部署",
    "form_title": "登录账号",
    "form_description": "首次会进入登录页。勾选“记住我”后，本机会记住用户名和密码，方便值班人员快速进入。",
    "username_label": "用户名",
    "username_placeholder": "例如 local-admin",
    "password_label": "密码",
    "password_placeholder": "请输入密码",
    "remember_label": "记住我",
    "remember_hint": "登录后自动跳转到中控主页",
    "submit_text": "进入中控系统"
}

SMILE_EK_COMMAND_NAME_MAP = {
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
    "lamp_status": "查询灯泡状态"
}

PROJECTOR_COMMAND_NAME_MAPS = {
    ("smile", "ek"): SMILE_EK_COMMAND_NAME_MAP,
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
    "pjlink": "PJLink"
}

def _looks_garbled_text(value):
    if not isinstance(value, str):
        return True
    text = value.strip()
    if not text:
        return True
    garbled_tokens = ["?", "锛", "馃", "篇胆赤", "狼双", "高桁", "寮€", "闂"]
    return any(token in text for token in garbled_tokens)


def _sanitize_login_page_text(login_page_text):
    sanitized = DEFAULT_LOGIN_PAGE_TEXT.copy()
    if not isinstance(login_page_text, dict):
        return sanitized, True

    changed = False
    for key, fallback in DEFAULT_LOGIN_PAGE_TEXT.items():
        value = login_page_text.get(key, fallback)
        if _looks_garbled_text(value):
            sanitized[key] = fallback
            changed = changed or value != fallback
        else:
            sanitized[key] = value

    for key, value in login_page_text.items():
        if key not in sanitized:
            sanitized[key] = value

    return sanitized, changed


def _write_config_file(config_data):
    ensure_parent_dir(CONFIG_FILE_PATH)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{CONFIG_FILE_PATH.name}.",
        suffix=".tmp",
        dir=str(CONFIG_FILE_PATH.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, CONFIG_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

def _sanitize_projector_command_names(projector_cfg):
    if not isinstance(projector_cfg, dict):
        return projector_cfg
    brand_id = str(projector_cfg.get("brand_id", "")).strip()
    series_id = str(projector_cfg.get("series_id", "")).strip()
    if not series_id and brand_id == "smile":
        series_id = "ek"
    cmd_map = PROJECTOR_COMMAND_NAME_MAPS.get((brand_id, series_id), {})
    if not cmd_map:
        return projector_cfg
    commands = projector_cfg.get("commands") or []
    for cmd in commands:
        cmd_id = str(cmd.get("id", "")).strip()
        fallback_name = cmd_map.get(cmd_id)
        if fallback_name and _looks_garbled_text(cmd.get("name")):
            cmd["name"] = fallback_name
        if _looks_garbled_text(cmd.get("icon")):
            cmd["icon"] = ""
    return projector_cfg

def _resolve_projector_brand_command_id(projector_cfg):
    brand_id = str(projector_cfg.get("brand_id", "")).strip()
    control_type = str(projector_cfg.get("control_type", "")).strip()
    custom_protocol = str(projector_cfg.get("custom_protocol", "")).strip()
    if control_type == "pjlink":
        if brand_id == "epson":
            return "epson_pjlink"
        return "generic_pjlink"
    if brand_id == "custom" and custom_protocol == "pjlink":
        return "generic_pjlink"
    return None

def _load_projector_brand_commands_by_id(brand_cmd_id):
    try:
        with open(PROJECTOR_BRANDS_FILE, "r", encoding="utf-8") as f:
            data = sanitize_projector_brand_library(json.load(f))
    except Exception:
        return []
    for brand in data.get("brands", []):
        if str(brand.get("id", "")).strip() == str(brand_cmd_id).strip():
            return brand.get("commands", []) or []
    return []

def _merge_missing_projector_commands(projector_cfg):
    if not isinstance(projector_cfg, dict):
        return projector_cfg
    brand_cmd_id = _resolve_projector_brand_command_id(projector_cfg)
    if not brand_cmd_id:
        return projector_cfg
    source_commands = _load_projector_brand_commands_by_id(brand_cmd_id)
    if not source_commands:
        return projector_cfg
    existing = projector_cfg.get("commands") or []
    existing_ids = {str(cmd.get("id", "")).strip() for cmd in existing}
    for cmd in source_commands:
        cmd_id = str(cmd.get("id", "")).strip()
        if not cmd_id or cmd_id in existing_ids or not cmd.get("visible", True):
            continue
        existing.append({
            "id": cmd_id,
            "name": cmd.get("name", cmd_id),
            "payload": cmd.get("payload_hex" if cmd.get("default_format") == "hex" else "payload_str", ""),
            "format": cmd.get("default_format", "str"),
            "show_on_home": cmd.get("show_on_home", False),
            "sort": cmd.get("sort", 99),
            "icon": cmd.get("icon", "")
        })
        existing_ids.add(cmd_id)
    projector_cfg["commands"] = existing
    return projector_cfg

def sanitize_projector_brand_library(brand_library):
    if not isinstance(brand_library, dict):
        return brand_library
    for brand in brand_library.get("brands", []):
        raw_brand = str(brand.get("brand") or brand.get("id") or "").strip()
        brand_id = "smile" if "smile" in raw_brand else ("appotronics" if "appotronics" in raw_brand else raw_brand)
        series_id = str(brand.get("series") or "").strip()
        series_key = (brand_id, series_id)

        if series_key in PROJECTOR_SERIES_TEXT_MAP:
            proper_name, proper_display_name = PROJECTOR_SERIES_TEXT_MAP[series_key]
            if _looks_garbled_text(brand.get("name")):
                brand["name"] = proper_name
            if _looks_garbled_text(brand.get("display_name")):
                brand["display_name"] = proper_display_name

        for conn in (brand.get("connection_types") or {}).values():
            conn_id = str(conn.get("id") or "").strip()
            if conn_id in PROJECTOR_CONNECTION_TEXT_MAP and _looks_garbled_text(conn.get("name")):
                conn["name"] = PROJECTOR_CONNECTION_TEXT_MAP[conn_id]

        cmd_name_map = PROJECTOR_COMMAND_NAME_MAPS.get(series_key, {})
        for cmd in brand.get("commands", []) or []:
            cmd_id = str(cmd.get("id", "")).strip()
            fallback_name = cmd_name_map.get(cmd_id)
            if fallback_name and _looks_garbled_text(cmd.get("name")):
                cmd["name"] = fallback_name
            if _looks_garbled_text(cmd.get("icon")):
                cmd["icon"] = ""
    return brand_library

DEFAULT_CABINET = {
    "cabinet_name": "主电柜", "station_id": 50, "comm_type": "以太网", "ip": "192.168.50.6", "port": 502, 
    "channel_count": 8, "plc_type": "AV-100", "meter_mode": "type1", "ct_ratio": 1.0, "ui_text": DEFAULT_UI_TEXT.copy()
}

DEFAULT_AUTOMATION_CONDITION = {
    "source_type": "env",
    "device_id": "",
    "prop": "lux",
    "op": "<",
    "value": 0,
    "debounce_sec": 0,
    "hysteresis": 0,
    "consecutive_hits": 1,
    "crossing_mode": "none",
    "rearm_value": "",
    "window_bootstrap_sec": 0,
}

DEFAULT_AUTOMATION_SCHEDULE = {
    "day_type": "everyday",
    "time": "08:00",
    "time_start": "00:00",
    "time_end": "23:59",
}

OUTDOOR_ENV_SENSOR_ID_ALIASES = {
    "env_sensor_outdoor",
    "outdoor_env_sensor",
    "env_outdoor_sensor",
}

OUTDOOR_LIGHT_NAME_HINTS = (
    "户外",
    "庭院",
    "院灯",
    "花园",
    "室外",
    "外场",
    "景观",
    "围墙",
    "门头",
)

ENV_MAIN_SENSOR_NAME_HINTS = (
    "光照温湿度",
    "温湿度变送器",
    "温湿度",
    "环境",
    "气象",
)

ENV_CONTACT_SENSOR_HINTS = (
    "门窗",
    "门磁",
    "开关",
    "contact",
    "door",
    "window",
)

GENERIC_DEVICE_COMMAND_NAME_MAP = {
    "FF AA EE EE DD": "开启",
    "FF AA EE EE CC": "停止",
    "FF AA EE EE EE": "关闭",
    "99 03 8D 66 34 58 99": "开-户外灯",
    "99 03 8D 66 32 58 99": "关-户外灯",
}

GENERIC_DEVICE_COMMAND_PLACEHOLDER_NAMES = {
    "",
    "指令",
    "命令",
    "功能",
    "command",
    "cmd",
}

OUTDOOR_UNIVERSAL_COMMAND_PAYLOADS = {
    "on": ("99 03 8D 66 34 58 99", "FF AA EE EE DD"),
    "off": ("99 03 8D 66 32 58 99", "FF AA EE EE EE"),
    "stop": ("FF AA EE EE CC",),
}

OUTDOOR_UNIVERSAL_COMMAND_NAME_HINTS = {
    "on": ("开-户外灯", "开启户外灯", "开灯", "开启", "打开", "上升", "up", "open", "on"),
    "off": ("关-户外灯", "关闭户外灯", "关灯", "关闭", "下降", "down", "close", "off"),
    "stop": ("停止", "stop"),
}

OUTDOOR_NODE_RED_DEVICE_ID = "courtyard_light"
OUTDOOR_LOW_LUX_ON_THRESHOLD = 200
OUTDOOR_LOW_LUX_REARM_VALUE = 260
OUTDOOR_SCHEDULED_OFF_TIME = "21:00"
OUTDOOR_SCHEDULED_OFF_WINDOW_END = "21:30"


def _normalize_automation_rule(rule):
    if not isinstance(rule, dict):
        return None
    normalized = deepcopy(rule)
    if "id" not in normalized or not str(normalized.get("id", "")).strip():
        normalized["id"] = f"auto_{int(datetime.now().timestamp() * 1000)}"
    normalized["name"] = str(normalized.get("name") or normalized["id"])
    normalized["enabled"] = bool(normalized.get("enabled", False))
    trigger_type = str(normalized.get("trigger_type") or "condition").strip().lower()
    if trigger_type not in {"condition", "schedule", "mixed", "compound"}:
        trigger_type = "condition"
    normalized["trigger_type"] = trigger_type
    normalized["action_scene_id"] = str(normalized.get("action_scene_id") or "")

    merged_condition = deepcopy(DEFAULT_AUTOMATION_CONDITION)
    condition = normalized.get("condition")
    if isinstance(condition, dict):
        merged_condition.update(condition)
    normalized["condition"] = merged_condition

    merged_schedule = deepcopy(DEFAULT_AUTOMATION_SCHEDULE)
    schedule = normalized.get("schedule")
    if isinstance(schedule, dict):
        merged_schedule.update(schedule)
    normalized["schedule"] = merged_schedule
    if not isinstance(normalized.get("preconditions"), list):
        normalized["preconditions"] = []
    normalized["precondition_mode"] = str(normalized.get("precondition_mode") or "all").strip().lower()
    if normalized["precondition_mode"] not in {"all", "any"}:
        normalized["precondition_mode"] = "all"
    if not isinstance(normalized.get("triggers"), list):
        normalized["triggers"] = []
    normalized["trigger_mode"] = str(normalized.get("trigger_mode") or "any").strip().lower()
    if normalized["trigger_mode"] not in {"any", "all"}:
        normalized["trigger_mode"] = "any"
    return normalized


def _maybe_add_outdoor_midnight_off_rule(loaded_config):
    automations = loaded_config.get("automations", [])
    if not isinstance(automations, list) or not automations:
        return False

    existing_ids = {str(item.get("id") or "").strip() for item in automations if isinstance(item, dict)}
    if "auto_outdoor_light_24_off" in existing_ids:
        return False

    off_rule = next(
        (
            item
            for item in automations
            if isinstance(item, dict) and str(item.get("id") or "").strip() == "auto_outdoor_light_20_off"
        ),
        None,
    )
    if not off_rule:
        return False

    scene_id = str(off_rule.get("action_scene_id") or "").strip()
    if not scene_id:
        return False

    midnight_rule = _normalize_automation_rule(
        {
            "id": "auto_outdoor_light_24_off",
            "name": "庭院灯午夜兜底关灯",
            "enabled": bool(off_rule.get("enabled", True)),
            "trigger_type": "schedule",
            "action_scene_id": scene_id,
            "condition": deepcopy(DEFAULT_AUTOMATION_CONDITION),
            "schedule": {
                "day_type": "everyday",
                "time": "00:00",
                "time_start": "00:00",
                "time_end": "00:30",
            },
        }
    )
    automations.append(midnight_rule)
    return True


def _select_preferred_outdoor_env_sensor_id(loaded_config):
    sensors = loaded_config.get("env_sensors", [])
    if not isinstance(sensors, list) or not sensors:
        return ""

    fallback_id = ""
    best_id = ""
    best_score = -1
    for sensor in sensors:
        if not isinstance(sensor, dict):
            continue
        sensor_id = str(sensor.get("id") or "").strip()
        if not sensor_id:
            continue
        if not fallback_id:
            fallback_id = sensor_id
        features = sensor.get("features")
        if not isinstance(features, dict):
            features = {}
        has_lux = features.get("illuminance", True) is not False
        if not has_lux:
            continue
        has_temp = features.get("temperature", True) is not False
        has_hum = features.get("humidity", True) is not False
        sensor_text = " ".join(
            str(sensor.get(key) or "").strip().lower()
            for key in ("id", "name", "model", "note", "source_type")
        )
        is_contact_like = any(hint in sensor_text for hint in ENV_CONTACT_SENSOR_HINTS)
        score = 10
        if has_temp:
            score += 8
        if has_hum:
            score += 8
        if has_temp and has_hum:
            score += 8
        if any(hint in sensor_text for hint in ENV_MAIN_SENSOR_NAME_HINTS):
            score += 12
        if is_contact_like:
            score -= 30
        if score > best_score:
            best_score = score
            best_id = sensor_id
    return best_id or fallback_id


def _maybe_upgrade_outdoor_light_on_rule(loaded_config):
    automations = loaded_config.get("automations", [])
    if not isinstance(automations, list) or not automations:
        return False

    valid_env_ids = {
        str(sensor.get("id") or "").strip()
        for sensor in loaded_config.get("env_sensors", [])
        if isinstance(sensor, dict) and str(sensor.get("id") or "").strip()
    }
    preferred_env_id = _select_preferred_outdoor_env_sensor_id(loaded_config)
    changed = False
    for item in automations:
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "").strip() != "auto_outdoor_light_low_lux_on":
            continue

        condition = item.get("condition")
        if not isinstance(condition, dict):
            condition = {}
            item["condition"] = condition

        schedule = item.get("schedule")
        if not isinstance(schedule, dict):
            schedule = {}
            item["schedule"] = schedule

        current_device_id = str(condition.get("device_id") or "").strip()
        current_sensor = next(
            (
                sensor
                for sensor in loaded_config.get("env_sensors", [])
                if isinstance(sensor, dict) and str(sensor.get("id") or "").strip() == current_device_id
            ),
            None,
        )
        current_sensor_text = " ".join(
            str((current_sensor or {}).get(key) or "").strip().lower()
            for key in ("id", "name", "model", "note", "source_type")
        )
        current_is_contact_like = bool(current_sensor) and any(
            hint in current_sensor_text for hint in ENV_CONTACT_SENSOR_HINTS
        )
        if preferred_env_id and (
            not current_device_id
            or current_device_id in OUTDOOR_ENV_SENSOR_ID_ALIASES
            or current_device_id not in valid_env_ids
            or current_is_contact_like
        ):
            if current_device_id != preferred_env_id:
                condition["device_id"] = preferred_env_id
                changed = True
        if str(item.get("trigger_type") or "").strip().lower() != "mixed":
            item["trigger_type"] = "mixed"
            changed = True
        if str(schedule.get("time_start") or "").strip() in {"", "00:00"}:
            schedule["time_start"] = "16:00"
            changed = True
        if str(schedule.get("time_end") or "").strip() == "":
            schedule["time_end"] = "19:59"
            changed = True
        if str(condition.get("crossing_mode") or "").strip().lower() != "cross_down":
            condition["crossing_mode"] = "cross_down"
            changed = True
        if condition.get("value") != OUTDOOR_LOW_LUX_ON_THRESHOLD:
            condition["value"] = OUTDOOR_LOW_LUX_ON_THRESHOLD
            changed = True
        if str(condition.get("rearm_value") or "").strip() == "":
            condition["rearm_value"] = OUTDOOR_LOW_LUX_REARM_VALUE
            changed = True
        elif condition.get("rearm_value") != OUTDOOR_LOW_LUX_REARM_VALUE:
            condition["rearm_value"] = OUTDOOR_LOW_LUX_REARM_VALUE
            changed = True
        if float(condition.get("window_bootstrap_sec", 0) or 0) <= 0:
            condition["window_bootstrap_sec"] = 180
            changed = True

    return changed


def _maybe_upgrade_outdoor_light_off_rule(loaded_config):
    automations = loaded_config.get("automations", [])
    if not isinstance(automations, list) or not automations:
        return False

    changed = False
    for item in automations:
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "").strip() != "auto_outdoor_light_20_off":
            continue

        if str(item.get("name") or "").strip() != "户外灯晚九点自动关灯":
            item["name"] = "户外灯晚九点自动关灯"
            changed = True

        schedule = item.get("schedule")
        if not isinstance(schedule, dict):
            schedule = {}
            item["schedule"] = schedule
            changed = True
        desired_schedule = {
            "time": OUTDOOR_SCHEDULED_OFF_TIME,
            "time_start": OUTDOOR_SCHEDULED_OFF_TIME,
            "time_end": OUTDOOR_SCHEDULED_OFF_WINDOW_END,
        }
        for key, value in desired_schedule.items():
            if str(schedule.get(key) or "").strip() != value:
                schedule[key] = value
                changed = True

    return changed


def _contains_outdoor_hint(value):
    text = str(value or "").strip().lower()
    if not text:
        return False
    return any(hint in text for hint in OUTDOOR_LIGHT_NAME_HINTS)


def _normalize_command_payload(payload):
    text = str(payload or "").strip().upper().replace(",", " ")
    return " ".join(text.split())


def _is_placeholder_command_name(value):
    text = str(value or "").strip().lower()
    return text in {item.lower() for item in GENERIC_DEVICE_COMMAND_PLACEHOLDER_NAMES}


def _sanitize_custom_device_command_names(device_cfg):
    if not isinstance(device_cfg, dict):
        return False
    changed = False
    commands = device_cfg.get("commands")
    if not isinstance(commands, list):
        return False
    for cmd in commands:
        if not isinstance(cmd, dict):
            continue
        normalized_payload = _normalize_command_payload(cmd.get("payload"))
        fallback_name = GENERIC_DEVICE_COMMAND_NAME_MAP.get(normalized_payload)
        current_name = str(cmd.get("name") or "").strip()
        if fallback_name and (_looks_garbled_text(current_name) or _is_placeholder_command_name(current_name)):
            if current_name != fallback_name:
                cmd["name"] = fallback_name
                changed = True
    return changed


def _find_universal_device_command(device_cfg, role):
    if not isinstance(device_cfg, dict):
        return None
    commands = device_cfg.get("commands")
    if not isinstance(commands, list):
        return None

    payload_candidates = {
        _normalize_command_payload(item)
        for item in OUTDOOR_UNIVERSAL_COMMAND_PAYLOADS.get(str(role or "").strip().lower(), ())
        if str(item or "").strip()
    }
    if payload_candidates:
        for cmd in commands:
            if not isinstance(cmd, dict):
                continue
            if _normalize_command_payload(cmd.get("payload")) in payload_candidates:
                return cmd

    name_hints = tuple(
        str(item or "").strip().lower()
        for item in OUTDOOR_UNIVERSAL_COMMAND_NAME_HINTS.get(str(role or "").strip().lower(), ())
        if str(item or "").strip()
    )
    if not name_hints:
        return None
    for cmd in commands:
        if not isinstance(cmd, dict):
            continue
        name_text = str(cmd.get("name") or "").strip().lower()
        if not name_text:
            continue
        if any(hint in name_text for hint in name_hints):
            return cmd
    return None


def _normalize_outdoor_universal_device(device):
    if not isinstance(device, dict):
        return False
    if not _find_universal_device_command(device, "on") or not _find_universal_device_command(device, "off"):
        return False
    changed = False
    if str(device.get("name") or "").strip() in {"", "新泛型设备"}:
        device["name"] = "庭院灯"
        changed = True
    return changed


def _normalize_outdoor_universal_devices(loaded_config):
    custom_devices = loaded_config.get("custom_devices", [])
    if not isinstance(custom_devices, list):
        return False
    changed = False
    for device in custom_devices:
        if _normalize_outdoor_universal_device(device):
            changed = True
    return changed


def _select_preferred_outdoor_universal_device(loaded_config):
    custom_devices = loaded_config.get("custom_devices", [])
    if not isinstance(custom_devices, list) or not custom_devices:
        return None

    valid_devices = []
    best_device = None
    best_score = -1
    for device in custom_devices:
        if not isinstance(device, dict):
            continue
        _normalize_outdoor_universal_device(device)
        device_id = str(device.get("id") or "").strip()
        if not device_id:
            continue
        valid_devices.append(device)
        score = 0
        if _contains_outdoor_hint(device.get("name")):
            score += 10
        host_text = str(device.get("ip") or device.get("host") or "").strip()
        if host_text == "192.168.50.254":
            score += 6
        if _find_universal_device_command(device, "on"):
            score += 8
        if _find_universal_device_command(device, "off"):
            score += 8
        commands = device.get("commands")
        if isinstance(commands, list) and len(commands) >= 2:
            score += 1
            command_names = " ".join(str(cmd.get("name") or "").strip().lower() for cmd in commands if isinstance(cmd, dict))
            if "户外灯" in command_names:
                score += 10
        if score > best_score:
            best_score = score
            best_device = device

    if best_device and best_score > 0:
        return best_device
    if len(valid_devices) == 1:
        return valid_devices[0]
    return None


def _select_preferred_outdoor_light_device_id(loaded_config):
    light_devices = loaded_config.get("light_devices", [])
    if not isinstance(light_devices, list) or not light_devices:
        return ""

    best_device_id = ""
    best_score = -1
    rf_tcp_candidates = []
    for light in light_devices:
        if not isinstance(light, dict):
            continue
        device_id = str(light.get("id") or "").strip()
        if not device_id:
            continue

        score = 0
        if _contains_outdoor_hint(light.get("name")):
            score += 10
        if str(light.get("brand") or "").strip().upper() == "RF_TCP":
            score += 6
            rf_tcp_candidates.append(device_id)
        try:
            if int(light.get("channels", 0) or 0) == 1:
                score += 2
        except Exception:
            pass

        for channel_cfg in light.get("channels_config", []) or []:
            if _contains_outdoor_hint(channel_cfg.get("name")):
                score += 4
                break

        if score > best_score:
            best_score = score
            best_device_id = device_id

    if best_score > 0:
        return best_device_id
    if len(rf_tcp_candidates) == 1:
        return rf_tcp_candidates[0]
    return ""


def _maybe_restore_outdoor_light_scenes(loaded_config):
    automations = loaded_config.get("automations", [])
    scenes = loaded_config.get("scenes", [])
    if not isinstance(automations, list) or not isinstance(scenes, list):
        return False

    required_scene_ids = {
        str(item.get("action_scene_id") or "").strip()
        for item in automations
        if isinstance(item, dict)
        and str(item.get("id") or "").strip() in {
            "auto_outdoor_light_low_lux_on",
            "auto_outdoor_light_20_off",
            "auto_outdoor_light_24_off",
        }
        and str(item.get("action_scene_id") or "").strip()
    }
    if not required_scene_ids:
        return False

    scene_map = {
        str(scene.get("id") or "").strip(): scene
        for scene in scenes
        if isinstance(scene, dict) and str(scene.get("id") or "").strip()
    }
    next_sort = 1
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        try:
            next_sort = max(next_sort, int(scene.get("sort", 0) or 0) + 1)
        except Exception:
            continue

    def _desired_scene(scene_id, action_type):
        scene_name = "庭院灯自动开灯" if action_type == "on" else "庭院灯自动关灯"
        return {
            "id": scene_id,
            "name": scene_name,
            "sort": 0,
            "visible": False,
            "auto_generated": True,
            "auto_generated_key": "outdoor_light",
            "actions": [
                {
                    "sub_system": "node_red",
                    "device_id": OUTDOOR_NODE_RED_DEVICE_ID,
                    "action_type": action_type,
                    "delay_ms": 0,
                }
            ],
        }

    changed = False
    desired_pairs = (
        ("scene_outdoor_light_on", "on"),
        ("scene_outdoor_light_off", "off"),
    )
    for scene_id, action_type in desired_pairs:
        if scene_id not in required_scene_ids:
            continue

        desired = _desired_scene(scene_id, action_type)
        if desired is None:
            continue
        scene = scene_map.get(scene_id)
        if scene is None:
            desired["sort"] = next_sort
            next_sort += 1
            scenes.append(desired)
            scene_map[scene_id] = desired
            changed = True
            continue

        auto_generated = bool(scene.get("auto_generated")) or str(scene.get("auto_generated_key") or "").strip() == "outdoor_light"
        actions = scene.get("actions")
        if not isinstance(actions, list) or not actions:
            scene["actions"] = desired["actions"]
            changed = True
        elif auto_generated:
            if scene.get("actions") != desired["actions"]:
                scene["actions"] = desired["actions"]
                changed = True

        if auto_generated:
            if str(scene.get("name") or "") != desired["name"]:
                scene["name"] = desired["name"]
                changed = True
            if scene.get("visible", False) is not False:
                scene["visible"] = False
                changed = True
            if str(scene.get("auto_generated_key") or "") != "outdoor_light":
                scene["auto_generated_key"] = "outdoor_light"
                changed = True
            if scene.get("auto_generated") is not True:
                scene["auto_generated"] = True
                changed = True

    return changed


def load_config():
    loaded_config = {"cabinets": [], "meters": [], "ups_devices": [], "snmp_devices": [], "nvr_devices": [], "light_devices": [], "scenes": [], "door_config": DEFAULT_DOOR_CONFIG.copy(), "sequencers": []}
    config_file_exists = os.path.exists(CONFIG_FILE)
    config_needs_persist = False
    if config_file_exists:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded_config.update(json.load(f))
        except: pass
        
    if not loaded_config.get("cabinets"): loaded_config["cabinets"] = [DEFAULT_CABINET.copy()]
    if "global_text" not in loaded_config: loaded_config["global_text"] = DEFAULT_UI_TEXT.copy()
    if "projectors" not in loaded_config: loaded_config["projectors"] = []
    if "custom_devices" not in loaded_config:
        loaded_config["custom_devices"] = []
    else:
        custom_devices_changed = False
        for device in loaded_config.get("custom_devices", []):
            if _sanitize_custom_device_command_names(device):
                custom_devices_changed = True
        outdoor_payloads = {"99 03 8D 66 34 58 99", "99 03 8D 66 32 58 99"}
        for device in loaded_config.get("custom_devices", []):
            commands = device.get("commands", []) if isinstance(device.get("commands"), list) else []
            for command in commands:
                command_text = f"{device.get('name', '')} {command.get('name', '')} {command.get('payload', '')}"
                if "户外灯" in command_text or str(command.get("payload") or "").strip() in outdoor_payloads:
                    if command.get("show_on_home") is not False:
                        command["show_on_home"] = False
                        custom_devices_changed = True
        if _normalize_outdoor_universal_devices(loaded_config):
            custom_devices_changed = True
        if custom_devices_changed:
            config_needs_persist = config_file_exists
    normalized_control_center = normalize_control_center(loaded_config.get("control_center"), loaded_config.get("custom_devices"))
    if loaded_config.get("control_center") != normalized_control_center:
        config_needs_persist = config_file_exists
    loaded_config["control_center"] = normalized_control_center
    if "home_assistant" not in loaded_config or not isinstance(loaded_config["home_assistant"], dict):
        loaded_config["home_assistant"] = deepcopy(DEFAULT_HOME_ASSISTANT)
    else:
        merged_home_assistant = deepcopy(DEFAULT_HOME_ASSISTANT)
        for key, value in loaded_config["home_assistant"].items():
            if key in {"entities", "attribute_map"} and isinstance(value, dict):
                merged_home_assistant[key].update(value)
            else:
                merged_home_assistant[key] = value
        loaded_config["home_assistant"] = merged_home_assistant
    if "hvac_devices" not in loaded_config or not isinstance(loaded_config["hvac_devices"], list): loaded_config["hvac_devices"] = []
    if "env_sensors" not in loaded_config: loaded_config["env_sensors"] = []
    if "snmp_devices" not in loaded_config or not isinstance(loaded_config["snmp_devices"], list): loaded_config["snmp_devices"] = []
    if "nvr_devices" not in loaded_config or not isinstance(loaded_config["nvr_devices"], list): loaded_config["nvr_devices"] = []
    if "ups_devices" not in loaded_config or not isinstance(loaded_config["ups_devices"], list): loaded_config["ups_devices"] = []
    if "meters" not in loaded_config or not isinstance(loaded_config["meters"], list): loaded_config["meters"] = []
    loaded_config["current_collector"] = _normalize_current_collector_config(loaded_config.get("current_collector"))
    if "automations" not in loaded_config:
        loaded_config["automations"] = []
    else:
        normalized_automations = []
        automations_changed = False
        for rule in loaded_config["automations"]:
            normalized_rule = _normalize_automation_rule(rule)
            if normalized_rule is None:
                automations_changed = True
                continue
            if normalized_rule != rule:
                automations_changed = True
            normalized_automations.append(normalized_rule)
        loaded_config["automations"] = normalized_automations
        if automations_changed:
            config_needs_persist = config_file_exists
    if "sequencers" not in loaded_config or not isinstance(loaded_config["sequencers"], list): loaded_config["sequencers"] = []
    if "meter_statistics" not in loaded_config or not isinstance(loaded_config["meter_statistics"], dict):
        loaded_config["meter_statistics"] = DEFAULT_METER_STATISTICS.copy()
    else:
        merged_meter_statistics = DEFAULT_METER_STATISTICS.copy()
        merged_meter_statistics.update(loaded_config["meter_statistics"])
        loaded_config["meter_statistics"] = merged_meter_statistics
    if "auth_settings" not in loaded_config or not isinstance(loaded_config["auth_settings"], dict):
        loaded_config["auth_settings"] = DEFAULT_AUTH_SETTINGS.copy()
        config_needs_persist = config_file_exists
    else:
        merged_auth_settings = DEFAULT_AUTH_SETTINGS.copy()
        merged_auth_settings.update(loaded_config["auth_settings"])
        loaded_config["auth_settings"] = merged_auth_settings
    if "login_page_text" not in loaded_config or not isinstance(loaded_config["login_page_text"], dict):
        loaded_config["login_page_text"] = DEFAULT_LOGIN_PAGE_TEXT.copy()
        config_needs_persist = config_file_exists
    else:
        loaded_config["login_page_text"], login_page_text_changed = _sanitize_login_page_text(
            loaded_config["login_page_text"]
        )
        config_needs_persist = config_needs_persist or login_page_text_changed
    loaded_config["door_config"] = _sanitize_door_config(loaded_config.get("door_config"))
    if "server_monitor" not in loaded_config or not isinstance(loaded_config["server_monitor"], dict):
        loaded_config["server_monitor"] = DEFAULT_SERVER_MONITOR.copy()
    else:
        merged_server_monitor = DEFAULT_SERVER_MONITOR.copy()
        merged_server_monitor.update(loaded_config["server_monitor"])
        if not isinstance(merged_server_monitor.get("scan_networks"), list):
            raw_networks = merged_server_monitor.get("scan_networks", "")
            if isinstance(raw_networks, str):
                merged_server_monitor["scan_networks"] = [item.strip() for item in raw_networks.replace(";", ",").split(",") if item.strip()]
            else:
                merged_server_monitor["scan_networks"] = []
        loaded_config["server_monitor"] = merged_server_monitor
    if "proxy_monitor" not in loaded_config or not isinstance(loaded_config["proxy_monitor"], dict):
        loaded_config["proxy_monitor"] = DEFAULT_PROXY_MONITOR.copy()
    else:
        merged_proxy_monitor = DEFAULT_PROXY_MONITOR.copy()
        merged_proxy_monitor.update(loaded_config["proxy_monitor"])
        if not isinstance(merged_proxy_monitor.get("check_urls"), list):
            merged_proxy_monitor["check_urls"] = list(DEFAULT_PROXY_MONITOR["check_urls"])
        try:
            merged_proxy_monitor["port"] = max(1, int(merged_proxy_monitor.get("port", 3128) or 3128))
        except Exception:
            merged_proxy_monitor["port"] = 3128
        try:
            merged_proxy_monitor["timeout_sec"] = max(1.0, min(float(merged_proxy_monitor.get("timeout_sec", 6.0) or 6.0), 30.0))
        except Exception:
            merged_proxy_monitor["timeout_sec"] = 6.0
        try:
            merged_proxy_monitor["poll_interval_sec"] = max(3.0, min(float(merged_proxy_monitor.get("poll_interval_sec", 20.0) or 20.0), 600.0))
        except Exception:
            merged_proxy_monitor["poll_interval_sec"] = 20.0
        merged_proxy_monitor["enabled"] = bool(merged_proxy_monitor.get("enabled", True))
        merged_proxy_monitor["host"] = str(merged_proxy_monitor.get("host") or DEFAULT_PROXY_MONITOR["host"]).strip()
        cleaned_urls = []
        for item in merged_proxy_monitor.get("check_urls", []):
            url = str(item or "").strip()
            if url:
                cleaned_urls.append(url)
        if not cleaned_urls:
            cleaned_urls = list(DEFAULT_PROXY_MONITOR["check_urls"])
        if not any(("google.com" in url.lower()) for url in cleaned_urls):
            cleaned_urls.insert(0, DEFAULT_PROXY_MONITOR["check_urls"][0])
        for default_url in DEFAULT_PROXY_MONITOR["check_urls"]:
            try:
                default_host = urlsplit(default_url).hostname or ""
            except Exception:
                default_host = ""
            if default_host and not any(default_host in str(urlsplit(url).hostname or "") for url in cleaned_urls):
                cleaned_urls.append(default_url)
        merged_proxy_monitor["check_urls"] = cleaned_urls[:6]
        traffic_source = str(merged_proxy_monitor.get("traffic_source") or DEFAULT_PROXY_MONITOR["traffic_source"]).strip().lower()
        if traffic_source not in {"auto", "snmp", "server", "nic_ssh", "none"}:
            traffic_source = DEFAULT_PROXY_MONITOR["traffic_source"]
        merged_proxy_monitor["traffic_enabled"] = bool(merged_proxy_monitor.get("traffic_enabled", True))
        merged_proxy_monitor["traffic_source"] = traffic_source
        merged_proxy_monitor["traffic_device_id"] = str(merged_proxy_monitor.get("traffic_device_id") or "").strip()
        merged_proxy_monitor["traffic_host"] = str(merged_proxy_monitor.get("traffic_host") or DEFAULT_PROXY_MONITOR["traffic_host"]).strip()
        merged_proxy_monitor["traffic_ifname"] = str(merged_proxy_monitor.get("traffic_ifname") or DEFAULT_PROXY_MONITOR["traffic_ifname"]).strip()
        merged_proxy_monitor["traffic_ssh_target"] = str(merged_proxy_monitor.get("traffic_ssh_target") or DEFAULT_PROXY_MONITOR["traffic_ssh_target"]).strip()
        merged_proxy_monitor["traffic_local_user"] = str(merged_proxy_monitor.get("traffic_local_user") or DEFAULT_PROXY_MONITOR["traffic_local_user"]).strip()
        try:
            merged_proxy_monitor["traffic_ifindex"] = max(0, int(merged_proxy_monitor.get("traffic_ifindex", 0) or 0))
        except Exception:
            merged_proxy_monitor["traffic_ifindex"] = 0
        try:
            merged_proxy_monitor["traffic_timeout_sec"] = max(2.0, min(float(merged_proxy_monitor.get("traffic_timeout_sec", 6.0) or 6.0), 20.0))
        except Exception:
            merged_proxy_monitor["traffic_timeout_sec"] = 6.0
        merged_proxy_monitor["client_monitor_enabled"] = bool(merged_proxy_monitor.get("client_monitor_enabled", True))
        merged_proxy_monitor["client_monitor_ssh_target"] = str(merged_proxy_monitor.get("client_monitor_ssh_target") or DEFAULT_PROXY_MONITOR["client_monitor_ssh_target"]).strip()
        merged_proxy_monitor["client_monitor_local_user"] = str(merged_proxy_monitor.get("client_monitor_local_user") or DEFAULT_PROXY_MONITOR["client_monitor_local_user"]).strip()
        try:
            merged_proxy_monitor["client_monitor_recent_seconds"] = max(30, min(int(merged_proxy_monitor.get("client_monitor_recent_seconds", 300) or 300), 3600))
        except Exception:
            merged_proxy_monitor["client_monitor_recent_seconds"] = 300
        try:
            merged_proxy_monitor["client_monitor_tail_lines"] = max(500, min(int(merged_proxy_monitor.get("client_monitor_tail_lines", 8000) or 8000), 50000))
        except Exception:
            merged_proxy_monitor["client_monitor_tail_lines"] = 8000
        try:
            merged_proxy_monitor["client_monitor_timeout_sec"] = max(2.0, min(float(merged_proxy_monitor.get("client_monitor_timeout_sec", 6.0) or 6.0), 20.0))
        except Exception:
            merged_proxy_monitor["client_monitor_timeout_sec"] = 6.0
        loaded_config["proxy_monitor"] = merged_proxy_monitor
    if "m32r" not in loaded_config or not isinstance(loaded_config["m32r"], dict):
        loaded_config["m32r"] = DEFAULT_M32R.copy()
    else:
        merged_m32r = DEFAULT_M32R.copy()
        merged_m32r.update(loaded_config["m32r"])
        try:
            merged_m32r["port"] = int(merged_m32r.get("port", 10023) or 10023)
        except Exception:
            merged_m32r["port"] = 10023
        try:
            merged_m32r["channel_count"] = max(1, min(int(merged_m32r.get("channel_count", 16) or 16), 32))
        except Exception:
            merged_m32r["channel_count"] = 16
        try:
            merged_m32r["bank_start"] = max(1, min(int(merged_m32r.get("bank_start", 1) or 1), 32))
        except Exception:
            merged_m32r["bank_start"] = 1
        try:
            merged_m32r["poll_interval_ms"] = max(300, int(merged_m32r.get("poll_interval_ms", 1200) or 1200))
        except Exception:
            merged_m32r["poll_interval_ms"] = 1200
        try:
            merged_m32r["keepalive_sec"] = max(2, min(int(merged_m32r.get("keepalive_sec", 5) or 5), 9))
        except Exception:
            merged_m32r["keepalive_sec"] = 5
        if not isinstance(merged_m32r.get("known_mixers"), list):
            merged_m32r["known_mixers"] = []
        loaded_config["m32r"] = merged_m32r
    if "apple_audio" not in loaded_config or not isinstance(loaded_config["apple_audio"], dict):
        loaded_config["apple_audio"] = deepcopy(DEFAULT_APPLE_AUDIO)
    else:
        merged_apple_audio = deepcopy(DEFAULT_APPLE_AUDIO)
        merged_apple_audio.update(loaded_config["apple_audio"])
        if not isinstance(merged_apple_audio.get("outputs"), list):
            merged_apple_audio["outputs"] = []
        loaded_config["apple_audio"] = merged_apple_audio

    raw_dashboard_sections = loaded_config.get("dashboard_sections")
    merged_dashboard_sections = {
        key: value.copy() for key, value in DEFAULT_DASHBOARD_SECTIONS.items()
    }
    if isinstance(raw_dashboard_sections, dict):
        for key, defaults in merged_dashboard_sections.items():
            existing = raw_dashboard_sections.get(key)
            if isinstance(existing, dict):
                defaults.update(existing)
    loaded_config["dashboard_sections"] = merged_dashboard_sections
    
    if "users" in loaded_config: del loaded_config["users"]

    if "sidebar" not in loaded_config: 
        loaded_config["sidebar"] = DEFAULT_SIDEBAR.copy()
    else:
        loaded_config["sidebar"] = [nav for nav in loaded_config["sidebar"] if nav["id"] not in ["universal", "automation", "env", "auto", "users"]]
        if not any(nav["id"] == "m32r" for nav in loaded_config["sidebar"]): loaded_config["sidebar"].append({"id": "m32r", "icon": "🎛", "name": "M32R 控台", "sort": 3, "visible": True})
        if not any(nav["id"] == "meter" for nav in loaded_config["sidebar"]): loaded_config["sidebar"].append({"id": "meter", "icon": "🔋", "name": "电表中心", "sort": 3, "visible": True})
        if not any(nav["id"] == "current_collector" for nav in loaded_config["sidebar"]): loaded_config["sidebar"].append({"id": "current_collector", "icon": "∿", "name": "电流采集", "sort": 3.4, "visible": True})
        if not any(nav["id"] == "ups" for nav in loaded_config["sidebar"]): loaded_config["sidebar"].append({"id": "ups", "icon": "🔌", "name": "UPS监测", "sort": 4, "visible": True})
        if not any(nav["id"] == "snmp" for nav in loaded_config["sidebar"]): loaded_config["sidebar"].append({"id": "snmp", "icon": "🛰", "name": "SNMP监测", "sort": 4, "visible": True})
        if not any(nav["id"] == "camera_preview" for nav in loaded_config["sidebar"]): loaded_config["sidebar"].append({"id": "camera_preview", "icon": "🎦", "name": "监控预览", "sort": 4.3, "visible": True})
        if not any(nav["id"] == "proxy" for nav in loaded_config["sidebar"]): loaded_config["sidebar"].append({"id": "proxy", "icon": "🌐", "name": "代理监控", "sort": 4.4, "visible": True})
        if not any(nav["id"] == "projector" for nav in loaded_config["sidebar"]): loaded_config["sidebar"].append({"id": "projector", "icon": "🎥", "name": "投影机集群", "sort": 7, "visible": True})
        if not any(nav["id"] == "universal" for nav in loaded_config["sidebar"]): loaded_config["sidebar"].append({"id": "universal", "icon": "🎛️", "name": "协议控制", "sort": 8, "visible": True})
        if not any(nav["id"] == "env" for nav in loaded_config["sidebar"]): loaded_config["sidebar"].append({"id": "env", "icon": "🌡️", "name": "环境监测", "sort": 9, "visible": True})
        if not any(nav["id"] == "local_model" for nav in loaded_config["sidebar"]): loaded_config["sidebar"].append({"id": "local_model", "icon": "AI", "name": "本地模型", "sort": 9.5, "visible": True})
        if not any(nav["id"] == "auto" for nav in loaded_config["sidebar"]): loaded_config["sidebar"].append({"id": "auto", "icon": "🤖", "name": "自动化运行", "sort": 10, "visible": True})

    for cab in loaded_config["cabinets"]:
        if "ui_text" not in cab: cab["ui_text"] = DEFAULT_UI_TEXT.copy()
        if "meter_mode" not in cab: cab["meter_mode"] = "type1"
        if "ct_ratio" not in cab: cab["ct_ratio"] = 1.0
        if "meter_display_name" not in cab: cab["meter_display_name"] = cab.get("cabinet_name", "电柜电表")
        if "meter_area_name" not in cab: cab["meter_area_name"] = ""
        if "meter_sort_order" not in cab: cab["meter_sort_order"] = loaded_config["cabinets"].index(cab) + 1
        if "meter_visible_in_center" not in cab: cab["meter_visible_in_center"] = True
        if "meter_include_in_totals" not in cab: cab["meter_include_in_totals"] = True
        if "meter_include_in_reports" not in cab: cab["meter_include_in_reports"] = True
        cab["channel_count"] = int(cab.get("channel_count", 8))
        if "channels_config" not in cab:
            cab["channels_config"] = [{"channel": i, "name": f"回路 {i}", "remark": "", "sort": i, "visible": True, "span": 1} for i in range(1, cab["channel_count"] + 1)]
        for channel_cfg in cab.get("channels_config", []) or []:
            if "remark" not in channel_cfg:
                channel_cfg["remark"] = ""

    for light in loaded_config["light_devices"]:
        light["channels"] = int(light.get("channels", 8))
        if "brand" not in light: light["brand"] = "COXE"
        if "port" not in light: light["port"] = 502
        if str(light.get("brand") or "").strip().upper() in {"NIREN_POE_KP", "POE_KP_I101"}:
            light["port"] = int(light.get("port") or 44489)
            light["channels"] = max(1, min(int(light.get("channels") or 1), 64))
            light["input_count"] = max(0, min(int(light.get("input_count", 1) or 0), 64))
            if "relay_protocol" not in light: light["relay_protocol"] = "rtu_over_tcp"
            if "input_start_address" not in light: light["input_start_address"] = 0
            if "input_active_level" not in light: light["input_active_level"] = "high"
            if "retry_count" not in light: light["retry_count"] = 3
            if "retry_delay_ms" not in light: light["retry_delay_ms"] = 350
        if "status_read_mode" not in light: light["status_read_mode"] = "coil"
        if "status_start_address" not in light: light["status_start_address"] = 0
        if "write_start_address" not in light: light["write_start_address"] = 0
        if "timeout_sec" not in light: light["timeout_sec"] = 2.0
        if "post_command_delay_ms" not in light: light["post_command_delay_ms"] = 500
        if "status_cache_ttl_ms" not in light: light["status_cache_ttl_ms"] = 250
        if "command_on" not in light: light["command_on"] = "on"
        if "command_off" not in light: light["command_off"] = "off"
        if "command_off3" not in light: light["command_off3"] = "off3"
        if "status_command" not in light: light["status_command"] = "status"
        if "ping_command" not in light: light["ping_command"] = "ping"
        if "dashboard_action_buttons" not in light or not isinstance(light["dashboard_action_buttons"], list):
            light["dashboard_action_buttons"] = []
        if "channels_config" not in light:
            light["channels_config"] = [{"channel": i, "name": f"第{i}路", "sort": i, "visible": True, "span": 1} for i in range(1, light["channels"] + 1)]
        if "input_channels_config" not in light or not isinstance(light.get("input_channels_config"), list):
            light["input_channels_config"] = [{"channel": i, "name": f"输入{i}", "sort": i, "visible": True, "span": 1} for i in range(1, int(light.get("input_count", 0) or 0) + 1)]
        if int(light.get("input_count", 0) or 0) > 0:
            existing_inputs = {
                int(item.get("channel") or 0): item
                for item in light.get("input_channels_config", [])
                if isinstance(item, dict)
            }
            light["input_channels_config"] = [
                {
                    "channel": i,
                    "name": str((existing_inputs.get(i) or {}).get("name") or f"输入{i}"),
                    "sort": int((existing_inputs.get(i) or {}).get("sort") or i),
                    "visible": bool((existing_inputs.get(i) or {}).get("visible", True)),
                    "span": int((existing_inputs.get(i) or {}).get("span") or 1),
                }
                for i in range(1, int(light.get("input_count", 0) or 0) + 1)
            ]

    for env in loaded_config["env_sensors"]:
        if "source_type" not in env:
            env["source_type"] = "modbus"
        if "register_start" not in env: env["register_start"] = 500
        if "register_count" not in env: env["register_count"] = 8
        if "features" not in env or not isinstance(env["features"], dict):
            env["features"] = DEFAULT_ENV_FEATURES.copy()
        else:
            merged_features = DEFAULT_ENV_FEATURES.copy()
            merged_features.update(env["features"])
            env["features"] = merged_features
        primary_metric = str(env.get("primary_metric", DEFAULT_ENV_PRIMARY_METRIC) or DEFAULT_ENV_PRIMARY_METRIC).strip().lower()
        if primary_metric not in {
            "auto",
            "temperature",
            "humidity",
            "illuminance",
            "contact",
            "light",
            "battery",
            "voltage",
            "noise",
            "pm25",
            "pm10",
            "pressure",
        }:
            primary_metric = DEFAULT_ENV_PRIMARY_METRIC
        env["primary_metric"] = primary_metric
        if "mqtt" not in env or not isinstance(env["mqtt"], dict):
            env["mqtt"] = deepcopy(DEFAULT_ENV_MQTT)
        else:
            merged_mqtt = deepcopy(DEFAULT_ENV_MQTT)
            for key, value in env["mqtt"].items():
                if key == "field_map" and isinstance(value, dict):
                    merged_mqtt["field_map"].update(value)
                else:
                    merged_mqtt[key] = value
            env["mqtt"] = merged_mqtt
        if "push" not in env or not isinstance(env["push"], dict):
            env["push"] = deepcopy(DEFAULT_ENV_PUSH)
        else:
            merged_push = deepcopy(DEFAULT_ENV_PUSH)
            merged_push.update(env["push"])
            env["push"] = merged_push
        if "home_assistant" not in env or not isinstance(env["home_assistant"], dict):
            env["home_assistant"] = deepcopy(DEFAULT_HOME_ASSISTANT)
        else:
            merged_ha = deepcopy(DEFAULT_HOME_ASSISTANT)
            for key, value in env["home_assistant"].items():
                if key in {"entities", "attribute_map"} and isinstance(value, dict):
                    merged_ha[key].update(value)
                else:
                    merged_ha[key] = value
            env["home_assistant"] = merged_ha

    for hvac in loaded_config["hvac_devices"]:
        merged_hvac = DEFAULT_HVAC_DEVICE.copy()
        merged_hvac.update(hvac)
        merged_hvac_ha = deepcopy(DEFAULT_HOME_ASSISTANT)
        if isinstance(hvac.get("home_assistant"), dict):
            for key, value in hvac["home_assistant"].items():
                if key in {"entities", "attribute_map"} and isinstance(value, dict):
                    merged_hvac_ha[key].update(value)
                else:
                    merged_hvac_ha[key] = value
        merged_hvac["home_assistant"] = merged_hvac_ha
        hvac.clear()
        hvac.update(merged_hvac)

    for meter in loaded_config["meters"]:
        if "id" not in meter or not str(meter.get("id", "")).strip():
            meter["id"] = f"meter_{int(datetime.now().timestamp() * 1000)}"
        if "name" not in meter: meter["name"] = "新电表"
        if "source_mode" not in meter: meter["source_mode"] = "standalone"
        if "meter_kind" not in meter: meter["meter_kind"] = "独立电表"
        if "meter_type" not in meter: meter["meter_type"] = "direct"
        if "energy_format_preset" not in meter: meter["energy_format_preset"] = "custom"
        if "brand" not in meter: meter["brand"] = ""
        if "model" not in meter: meter["model"] = ""
        if "protocol" not in meter: meter["protocol"] = "Modbus-RTU/TCP"
        if "comm_mode" not in meter: meter["comm_mode"] = "TCP"
        if "ip" not in meter: meter["ip"] = ""
        if "port" not in meter: meter["port"] = 502
        if "station_id" not in meter: meter["station_id"] = 1
        if "com_port" not in meter: meter["com_port"] = "COM1"
        if "baudrate" not in meter: meter["baudrate"] = 9600
        if "data_bits" not in meter: meter["data_bits"] = 8
        if "stop_bits" not in meter: meter["stop_bits"] = 1
        if "parity" not in meter: meter["parity"] = "NONE"
        if "ct_ratio" not in meter: meter["ct_ratio"] = 1.0
        if "multiplier" not in meter: meter["multiplier"] = 1.0
        if "poll_interval_ms" not in meter: meter["poll_interval_ms"] = 2000
        if "bind_cabinet_idx" not in meter: meter["bind_cabinet_idx"] = -1
        if "sort_order" not in meter: meter["sort_order"] = 100 + loaded_config["meters"].index(meter) + 1
        if "visible" not in meter: meter["visible"] = True
        if "visible_in_meter_center" not in meter: meter["visible_in_meter_center"] = meter.get("visible", True)
        if "enabled" not in meter: meter["enabled"] = True
        if "include_in_totals" not in meter: meter["include_in_totals"] = True
        if "include_in_reports" not in meter: meter["include_in_reports"] = True
        if "area_name" not in meter: meter["area_name"] = ""
        if "calc_left_source_id" not in meter: meter["calc_left_source_id"] = ""
        if "calc_right_source_id" not in meter: meter["calc_right_source_id"] = ""
        if "calc_operator" not in meter: meter["calc_operator"] = "subtract"
        if "calc_note" not in meter: meter["calc_note"] = ""
        if "register_map" not in meter or not isinstance(meter["register_map"], dict):
            meter["register_map"] = deepcopy(DEFAULT_METER_REGISTER_MAP)
        else:
            merged_register_map = deepcopy(DEFAULT_METER_REGISTER_MAP)
            for map_key, defaults in merged_register_map.items():
                existing_map = meter["register_map"].get(map_key)
                if isinstance(existing_map, dict):
                    defaults.update(existing_map)
            meter["register_map"] = merged_register_map
        if "features" not in meter or not isinstance(meter["features"], dict):
            meter["features"] = DEFAULT_METER_FEATURES.copy()
        else:
            merged_features = DEFAULT_METER_FEATURES.copy()
            merged_features.update(meter["features"])
            meter["features"] = merged_features

    for ups in loaded_config["ups_devices"]:
        if "id" not in ups or not str(ups.get("id", "")).strip():
            ups["id"] = f"ups_{int(datetime.now().timestamp() * 1000)}"
        if "name" not in ups: ups["name"] = "山特 UPS"
        if "brand" not in ups: ups["brand"] = "SANTAK"
        if "model" not in ups: ups["model"] = "C1K"
        if "protocol" not in ups: ups["protocol"] = "SANTAK Castle RS232"
        if "comm_mode" not in ups: ups["comm_mode"] = "TCP"
        if "ip" not in ups: ups["ip"] = ""
        if "port" not in ups: ups["port"] = 23
        if "com_port" not in ups: ups["com_port"] = "COM1"
        if "baudrate" not in ups: ups["baudrate"] = 2400
        if "data_bits" not in ups: ups["data_bits"] = 8
        if "stop_bits" not in ups: ups["stop_bits"] = 1
        if "parity" not in ups: ups["parity"] = "NONE"
        if "timeout_sec" not in ups: ups["timeout_sec"] = 2.0
        if "poll_interval_ms" not in ups: ups["poll_interval_ms"] = 3000
        if "shutdown_delay" not in ups: ups["shutdown_delay"] = ".3"
        if "query_retries" not in ups: ups["query_retries"] = 4
        if "retry_backoff_ms" not in ups: ups["retry_backoff_ms"] = 200
        if "frame_settle_ms" not in ups: ups["frame_settle_ms"] = 120
        if "response_window_ms" not in ups: ups["response_window_ms"] = 1300
        if "require_parenthesized_frame" not in ups: ups["require_parenthesized_frame"] = True
        if "command_gap_ms" not in ups: ups["command_gap_ms"] = 80
        if "fallback_cache_ttl_sec" not in ups: ups["fallback_cache_ttl_sec"] = 600.0
        if "visible" not in ups: ups["visible"] = True
        try:
            ups["timeout_sec"] = max(0.5, min(float(ups.get("timeout_sec", 2.0) or 2.0), 15.0))
        except Exception:
            ups["timeout_sec"] = 2.0
        try:
            ups["poll_interval_ms"] = max(500, min(int(ups.get("poll_interval_ms", 3000) or 3000), 60000))
        except Exception:
            ups["poll_interval_ms"] = 3000
        try:
            ups["query_retries"] = max(0, min(int(ups.get("query_retries", 2) or 2), 5))
        except Exception:
            ups["query_retries"] = 2
        try:
            ups["retry_backoff_ms"] = max(0, min(int(ups.get("retry_backoff_ms", 120) or 120), 2000))
        except Exception:
            ups["retry_backoff_ms"] = 120
        try:
            ups["frame_settle_ms"] = max(20, min(int(ups.get("frame_settle_ms", 80) or 80), 1000))
        except Exception:
            ups["frame_settle_ms"] = 80
        try:
            ups["response_window_ms"] = max(200, min(int(ups.get("response_window_ms", 900) or 900), 5000))
        except Exception:
            ups["response_window_ms"] = 900
        try:
            ups["command_gap_ms"] = max(0, min(int(ups.get("command_gap_ms", 35) or 35), 2000))
        except Exception:
            ups["command_gap_ms"] = 35
        try:
            ups["fallback_cache_ttl_sec"] = max(5.0, min(float(ups.get("fallback_cache_ttl_sec", 600.0) or 600.0), 86400.0))
        except Exception:
            ups["fallback_cache_ttl_sec"] = 600.0
        ups["require_parenthesized_frame"] = bool(ups.get("require_parenthesized_frame", True))

    for nvr in loaded_config["nvr_devices"]:
        if "id" not in nvr or not str(nvr.get("id", "")).strip():
            nvr["id"] = f"nvr_{int(datetime.now().timestamp() * 1000)}"
        if "name" not in nvr: nvr["name"] = "录像机"
        if "brand" not in nvr: nvr["brand"] = "Hikvision"
        if "model" not in nvr: nvr["model"] = ""
        if "protocol" not in nvr: nvr["protocol"] = "Hikvision ISAPI"
        if "scheme" not in nvr: nvr["scheme"] = "http"
        if "host" not in nvr: nvr["host"] = nvr.get("ip", "")
        if "port" not in nvr: nvr["port"] = 80
        if "username" not in nvr: nvr["username"] = ""
        if "password" not in nvr: nvr["password"] = ""
        if "expected_channel_count" not in nvr: nvr["expected_channel_count"] = 0
        if "camera_inventory_path" not in nvr: nvr["camera_inventory_path"] = ""
        if "timeout_sec" not in nvr: nvr["timeout_sec"] = 5.0
        if "snapshot_timeout_sec" not in nvr: nvr["snapshot_timeout_sec"] = 5.0
        if "snapshot_stream" not in nvr: nvr["snapshot_stream"] = "2"
        if "snapshot_cache_ttl_sec" not in nvr: nvr["snapshot_cache_ttl_sec"] = 1.5
        if "poll_interval_ms" not in nvr: nvr["poll_interval_ms"] = 10000
        if "enabled" not in nvr: nvr["enabled"] = True
        if "visible" not in nvr: nvr["visible"] = True
        try:
            nvr["port"] = max(1, min(int(nvr.get("port", 80) or 80), 65535))
        except Exception:
            nvr["port"] = 80
        try:
            nvr["expected_channel_count"] = max(0, min(int(nvr.get("expected_channel_count", 0) or 0), 256))
        except Exception:
            nvr["expected_channel_count"] = 0
        try:
            nvr["timeout_sec"] = max(1.0, min(float(nvr.get("timeout_sec", 5.0) or 5.0), 30.0))
        except Exception:
            nvr["timeout_sec"] = 5.0
        try:
            nvr["snapshot_timeout_sec"] = max(1.0, min(float(nvr.get("snapshot_timeout_sec", 5.0) or 5.0), 30.0))
        except Exception:
            nvr["snapshot_timeout_sec"] = 5.0
        try:
            nvr["snapshot_cache_ttl_sec"] = max(0.0, min(float(nvr.get("snapshot_cache_ttl_sec", 1.5) or 1.5), 15.0))
        except Exception:
            nvr["snapshot_cache_ttl_sec"] = 1.5
        try:
            nvr["poll_interval_ms"] = max(2000, min(int(nvr.get("poll_interval_ms", 10000) or 10000), 300000))
        except Exception:
            nvr["poll_interval_ms"] = 10000

    if not loaded_config["snmp_devices"]:
        loaded_config["snmp_devices"] = [
            {
                "id": "snmp_fnnas_192_168_50_254",
                "name": "飞牛 NAS",
                "brand": "飞牛",
                "model": "fnOS",
                "device_type": "nas",
                "protocol": "SNMP",
                "version": "v2c",
                "host": "192.168.50.254",
                "port": 161,
                "community": "MyMonitor2026!",
                "timeout_sec": 3.0,
                "retries": 2,
                "poll_interval_ms": 4000,
                "enabled": True,
                "visible": True,
                "security_level": "noAuthNoPriv",
                "username": "",
                "auth_protocol": "SHA",
                "auth_password": "",
                "priv_protocol": "AES",
                "priv_password": "",
                "source_ip": "",
                "context_name": "",
                "walk_enabled": True,
                "walk_roots": deepcopy(DEFAULT_SNMP_WALK_ROOTS) + [
                    "1.3.6.1.4.1.2021.4",
                    "1.3.6.1.4.1.2021.10",
                    "1.3.6.1.4.1.2021.11",
                    "1.3.6.1.4.1.2021.13",
                    "1.3.6.1.4.1.8072"
                ],
                "walk_max_oids": 512,
                "walk_sample_limit": 12,
                "walk_interval_ms": 12000,
                "walk_roots_per_cycle": 4,
                "oid_map": deepcopy(DEFAULT_SNMP_OID_MAP),
                "custom_oids": build_default_snmp_custom_oids("nas", "椋炵墰", "fnOS")
            },
            {
                "id": "snmp_qnap_192_168_30_145",
                "name": "威联通 NAS",
                "brand": "QNAP",
                "model": "TS-X73A",
                "device_type": "nas",
                "protocol": "SNMP",
                "version": "v2c",
                "host": "192.168.30.145",
                "port": 161,
                "community": "admin123",
                "timeout_sec": 3.0,
                "retries": 2,
                "poll_interval_ms": 4000,
                "enabled": True,
                "visible": True,
                "security_level": "noAuthNoPriv",
                "username": "",
                "auth_protocol": "SHA",
                "auth_password": "",
                "priv_protocol": "AES",
                "priv_password": "",
                "source_ip": "",
                "context_name": "",
                "walk_enabled": True,
                "walk_roots": deepcopy(DEFAULT_SNMP_WALK_ROOTS) + [
                    "1.3.6.1.4.1.24681.1.2.2",
                    "1.3.6.1.4.1.24681.1.2.3",
                    "1.3.6.1.4.1.24681.1.2.11",
                    "1.3.6.1.4.1.55062.2.10.2.1",
                    "1.3.6.1.4.1.55062.2.12.9.1"
                ],
                "walk_max_oids": 512,
                "walk_sample_limit": 12,
                "walk_interval_ms": 12000,
                "walk_roots_per_cycle": 4,
                "ssh_enrich_enabled": False,
                "storage_aliases": deepcopy(DEFAULT_QNAP_STORAGE_ALIASES),
                "oid_map": deepcopy(DEFAULT_SNMP_OID_MAP),
                "custom_oids": build_default_snmp_custom_oids("nas", "QNAP", "TS-X73A")
            },
            {
                "id": "snmp_ikuai_192_168_99_3",
                "name": "爱快",
                "brand": "iKuai",
                "model": "3.7.21",
                "device_type": "router",
                "protocol": "SNMP",
                "version": "v2c",
                "host": "192.168.99.3",
                "port": 161,
                "community": "iKuai",
                "timeout_sec": 3.0,
                "retries": 2,
                "poll_interval_ms": 4000,
                "enabled": True,
                "visible": True,
                "security_level": "noAuthNoPriv",
                "username": "",
                "auth_protocol": "SHA",
                "auth_password": "",
                "priv_protocol": "AES",
                "priv_password": "",
                "source_ip": "",
                "context_name": "",
                "walk_enabled": True,
                "walk_roots": deepcopy(DEFAULT_SNMP_WALK_ROOTS) + [
                    "1.3.6.1.2.1.2.2.1.10",
                    "1.3.6.1.2.1.2.2.1.13",
                    "1.3.6.1.2.1.2.2.1.14",
                    "1.3.6.1.2.1.2.2.1.16",
                    "1.3.6.1.2.1.2.2.1.19",
                    "1.3.6.1.2.1.2.2.1.20"
                ],
                "walk_max_oids": 512,
                "walk_sample_limit": 12,
                "walk_interval_ms": 14000,
                "walk_roots_per_cycle": 4,
                "oid_map": deepcopy(DEFAULT_SNMP_OID_MAP),
                "custom_oids": build_default_snmp_custom_oids("router", "iKuai", "3.7.21")
            },
            {
                "id": "snmp_h3c_192_168_99_1",
                "name": "H3C Switch",
                "brand": "H3C",
                "model": "S5130V2-28S-LI",
                "device_type": "switch",
                "protocol": "SNMP",
                "version": "v2c",
                "host": "192.168.99.1",
                "port": 161,
                "community": "H3C",
                "timeout_sec": 4.0,
                "retries": 2,
                "poll_interval_ms": 4000,
                "enabled": True,
                "visible": True,
                "security_level": "noAuthNoPriv",
                "username": "",
                "auth_protocol": "SHA",
                "auth_password": "",
                "priv_protocol": "AES",
                "priv_password": "",
                "source_ip": "192.168.50.120",
                "context_name": "",
                "walk_enabled": True,
                "walk_roots": [
                    "1.3.6.1.2.1.1",
                    "1.3.6.1.2.1.2.2.1.2",
                    "1.3.6.1.2.1.2.2.1.5",
                    "1.3.6.1.2.1.2.2.1.7",
                    "1.3.6.1.2.1.2.2.1.8",
                    "1.3.6.1.2.1.2.2.1.10",
                    "1.3.6.1.2.1.2.2.1.13",
                    "1.3.6.1.2.1.2.2.1.14",
                    "1.3.6.1.2.1.2.2.1.16",
                    "1.3.6.1.2.1.2.2.1.19",
                    "1.3.6.1.2.1.2.2.1.20",
                    "1.3.6.1.2.1.31.1.1.1.1",
                    "1.3.6.1.2.1.31.1.1.1.18",
                    "1.3.6.1.2.1.31.1.1.1.6",
                    "1.3.6.1.2.1.31.1.1.1.10",
                    "1.3.6.1.2.1.31.1.1.1.15"
                ],
                "walk_max_oids": 1200,
                "walk_sample_limit": 12,
                "walk_interval_ms": 18000,
                "walk_roots_per_cycle": 8,
                "oid_map": deepcopy(DEFAULT_SNMP_OID_MAP),
                "custom_oids": build_default_snmp_custom_oids("switch", "H3C", "S5130V2-28S-LI")
            }
        ]

    for snmp in loaded_config["snmp_devices"]:
        if "id" not in snmp or not str(snmp.get("id", "")).strip():
            snmp["id"] = f"snmp_{int(datetime.now().timestamp() * 1000)}"
        if "name" not in snmp: snmp["name"] = "SNMP 设备"
        if "brand" not in snmp: snmp["brand"] = ""
        if "model" not in snmp: snmp["model"] = ""
        if "device_type" not in snmp: snmp["device_type"] = "network"
        if "protocol" not in snmp: snmp["protocol"] = "SNMP"
        if "version" not in snmp: snmp["version"] = "v2c"
        if "host" not in snmp: snmp["host"] = snmp.get("ip", "")
        if "port" not in snmp: snmp["port"] = 161
        if "community" not in snmp: snmp["community"] = "public"
        if "timeout_sec" not in snmp: snmp["timeout_sec"] = 2.0
        if "retries" not in snmp: snmp["retries"] = 1
        if "poll_interval_ms" not in snmp: snmp["poll_interval_ms"] = 5000
        if "enabled" not in snmp: snmp["enabled"] = True
        if "visible" not in snmp: snmp["visible"] = True
        if "security_level" not in snmp: snmp["security_level"] = "noAuthNoPriv"
        if "username" not in snmp: snmp["username"] = ""
        if "auth_protocol" not in snmp: snmp["auth_protocol"] = "SHA"
        if "auth_password" not in snmp: snmp["auth_password"] = ""
        if "priv_protocol" not in snmp: snmp["priv_protocol"] = "AES"
        if "priv_password" not in snmp: snmp["priv_password"] = ""
        if "source_ip" not in snmp: snmp["source_ip"] = ""
        if "context_name" not in snmp: snmp["context_name"] = ""
        if "walk_enabled" not in snmp: snmp["walk_enabled"] = True
        if "walk_roots" not in snmp or not isinstance(snmp["walk_roots"], list):
            snmp["walk_roots"] = deepcopy(DEFAULT_SNMP_WALK_ROOTS)
        else:
            snmp["walk_roots"] = [str(item or "").strip() for item in snmp["walk_roots"] if str(item or "").strip()]
        if "walk_max_oids" not in snmp: snmp["walk_max_oids"] = 256
        if "walk_sample_limit" not in snmp: snmp["walk_sample_limit"] = 12
        if "walk_interval_ms" not in snmp: snmp["walk_interval_ms"] = 20000
        if "walk_roots_per_cycle" not in snmp: snmp["walk_roots_per_cycle"] = 0
        if "ssh_enrich_enabled" not in snmp: snmp["ssh_enrich_enabled"] = False
        if "storage_aliases" not in snmp or not isinstance(snmp["storage_aliases"], dict): snmp["storage_aliases"] = {}
        if _is_qnap_snmp_device(snmp):
            if snmp.get("ssh_enrich_enabled") is not False:
                snmp["ssh_enrich_enabled"] = False
                config_needs_persist = config_file_exists
            merged_qnap_aliases = deepcopy(DEFAULT_QNAP_STORAGE_ALIASES)
            merged_qnap_aliases.update(snmp.get("storage_aliases") or {})
            if snmp.get("storage_aliases") != merged_qnap_aliases:
                snmp["storage_aliases"] = merged_qnap_aliases
                config_needs_persist = config_file_exists
        if "oid_map" not in snmp or not isinstance(snmp["oid_map"], dict):
            snmp["oid_map"] = deepcopy(DEFAULT_SNMP_OID_MAP)
        else:
            merged_oid_map = deepcopy(DEFAULT_SNMP_OID_MAP)
            merged_oid_map.update(snmp["oid_map"])
            snmp["oid_map"] = merged_oid_map
        default_custom_oids = build_default_snmp_custom_oids(
            snmp.get("device_type"),
            snmp.get("brand"),
            snmp.get("model"),
        )
        if "custom_oids" not in snmp or not isinstance(snmp["custom_oids"], list):
            snmp["custom_oids"] = default_custom_oids
        else:
            normalized_custom_oids = []
            for item in snmp["custom_oids"]:
                if not isinstance(item, dict):
                    continue
                normalized_custom_oids.append({
                    "name": item.get("name", ""),
                    "oid": item.get("oid", ""),
                    "value_type": item.get("value_type", "auto"),
                    "scale": item.get("scale", 1),
                    "unit": item.get("unit", ""),
                    "precision": item.get("precision", 0),
                    "enabled": item.get("enabled", True),
                })
            merged_custom_oids = _dedupe_snmp_custom_oids(default_custom_oids + normalized_custom_oids)
            snmp["custom_oids"] = merged_custom_oids

    loaded_config["projectors"] = [
        _sanitize_projector_command_names(_merge_missing_projector_commands(proj))
        for proj in loaded_config.get("projectors", [])
    ]

    if _maybe_add_outdoor_midnight_off_rule(loaded_config):
        config_needs_persist = config_file_exists
    if _maybe_upgrade_outdoor_light_on_rule(loaded_config):
        config_needs_persist = config_file_exists
    if _maybe_upgrade_outdoor_light_off_rule(loaded_config):
        config_needs_persist = config_file_exists
    if _normalize_outdoor_universal_devices(loaded_config):
        config_needs_persist = config_file_exists
    if _maybe_restore_outdoor_light_scenes(loaded_config):
        config_needs_persist = config_file_exists

    if config_needs_persist:
        try:
            _write_config_file(loaded_config)
        except Exception:
            pass

    return loaded_config

CONFIG = load_config()

def save_config(new_config):
    global CONFIG
    CONFIG.update(new_config)
    CONFIG["door_config"] = _sanitize_door_config(CONFIG.get("door_config"))
    CONFIG["automations"] = [
        rule for rule in (
            _normalize_automation_rule(item) for item in CONFIG.get("automations", [])
        )
        if rule is not None
    ]
    _maybe_add_outdoor_midnight_off_rule(CONFIG)
    _maybe_upgrade_outdoor_light_on_rule(CONFIG)
    _maybe_upgrade_outdoor_light_off_rule(CONFIG)
    for device in CONFIG.get("custom_devices", []):
        _sanitize_custom_device_command_names(device)
    CONFIG["control_center"] = normalize_control_center(CONFIG.get("control_center"), CONFIG.get("custom_devices"))
    _maybe_restore_outdoor_light_scenes(CONFIG)
    if "projectors" in CONFIG:
        CONFIG["projectors"] = [
            _sanitize_projector_command_names(_merge_missing_projector_commands(proj))
            for proj in CONFIG.get("projectors", [])
        ]
    auth_settings = CONFIG.get("auth_settings")
    if not isinstance(auth_settings, dict):
        auth_settings = {}
    merged_auth_settings = DEFAULT_AUTH_SETTINGS.copy()
    merged_auth_settings.update(auth_settings)
    CONFIG["auth_settings"] = merged_auth_settings
    CONFIG["login_page_text"], _ = _sanitize_login_page_text(CONFIG.get("login_page_text"))
    _write_config_file(CONFIG)

# 【关键修复点】：把 channel_map 放回来，防止其他老文件导入报错
channel_map = {1: (0x03EB, 0x03EC), 2: (0x03ED, 0x03EE), 3: (0x03EF, 0x03F0), 4: (0x03F1, 0x03F2), 5: (0x03F3, 0x03F4), 6: (0x03F5, 0x03F6), 7: (0x03F7, 0x03F8), 8: (0x03F9, 0x03FA)}

def get_default_status():
    return {"channels_1_4": [False]*8, "cabinet_temp": 0, "cabinet_humidity": 0, "voltage_a": 0, "voltage_b": 0, "voltage_c": 0, "current_a": 0, "current_b": 0, "current_c": 0, "electric_energy": 0, "daily_energy": 0.0, "monthly_energy": 0.0, "realtime_power": 0.0, "current_month": datetime.now().month, "work_mode": "未知", "comm_status": True}

DEVICE_STATUS = {i: get_default_status() for i in range(len(CONFIG["cabinets"]))}
METER_STATUS = {}
LIGHT_STATUS = {}
LIGHT_ONLINE = {}
ENV_STATUS = {}

def get_projector_brands():
    """获取所有投影机品牌列表"""
    try:
        with open(PROJECTOR_BRANDS_FILE, "r", encoding="utf-8") as f:
            data = sanitize_projector_brand_library(json.load(f))
            return data.get("brands", [])
    except:
        return []

def get_brand_commands(brand_id):
    """获取指定品牌的命令列表"""
    brands = get_projector_brands()
    for brand in brands:
        if brand["id"] == brand_id:
            return brand.get("commands", [])
    return []

def normalize_projector_config(proj_cfg):
    """标准化投影机配置，确保包含必要的字段"""
    if not proj_cfg:
        return None
    
    normalized = proj_cfg.copy()
    
    if "brand_id" not in normalized:
        normalized["brand_id"] = "epson"
    if "series_id" not in normalized:
        if normalized["brand_id"] in ["epson", "generic"]:
            normalized["series_id"] = "pjlink"
        elif normalized["brand_id"] == "smile":
            normalized["series_id"] = "ek"
        elif normalized["brand_id"] == "custom":
            normalized["series_id"] = "custom"
        else:
            normalized["series_id"] = "dh"
    
    if "control_type" not in normalized:
        if normalized["brand_id"] in ["epson", "generic"]:
            normalized["control_type"] = "pjlink"
        elif normalized["brand_id"] == "smile":
            normalized["control_type"] = "smile_ek_tcp"
        elif normalized["brand_id"] == "custom":
            normalized["control_type"] = "pjlink"
            normalized["custom_protocol"] = normalized.get("custom_protocol", "pjlink")
        else:
            normalized["control_type"] = "appotronics_dh_tcp"
    
    if "commands" not in normalized or not normalized["commands"]:
        load_brand_id = normalized["brand_id"]
        if normalized["brand_id"] == "custom" and normalized.get("custom_protocol", "pjlink") == "pjlink":
            load_brand_id = "generic_pjlink"
        brand_cmds = get_brand_commands(load_brand_id)
        if brand_cmds:
            normalized["commands"] = []
            for cmd in brand_cmds:
                if cmd.get("visible", True):
                    normalized["commands"].append({
                        "id": cmd["id"],
                        "name": cmd["name"],
                        "payload": cmd.get("payload_hex" if cmd.get("default_format") == "hex" else "payload_str", ""),
                        "format": cmd.get("default_format", "str"),
                        "show_on_home": cmd.get("show_on_home", False),
                        "sort": cmd.get("sort", 99),
                        "icon": cmd.get("icon", "🔌")
                    })
    
    return normalized
