# AI_MODULE: runtime_state_cache
# AI_PURPOSE: 保存后台轮询和 API 共享的进程内状态缓存，避免每次请求直接访问慢设备。
# AI_BOUNDARY: 不做设备通信、不做业务推断；这里只定义状态容器和轻量快照工具。
# AI_DATA_FLOW: background/services 写入状态字典 -> api 读取 -> 前端渲染。
# AI_RUNTIME: Python 进程内内存状态，服务重启后重新由后台轮询填充。
# AI_RISK: 中，字段名变化会影响多个 API 和前端页面；缓存陈旧会导致状态显示滞后。
# AI_COMPAT: SNMP_STATUS、UPS_STATUS、PROJECTOR_STATUS 等全局对象名称需稳定。
# AI_SEARCH_KEYWORDS: runtime state, cache, SNMP_STATUS, UPS_STATUS, PROJECTOR_STATUS.

from config import CONFIG, DEVICE_STATUS, ENV_STATUS, LIGHT_ONLINE, LIGHT_STATUS, METER_STATUS


LIGHT_DRIVERS = {}
PROJECTOR_STATUS = {}
SCREEN_STATUS = {}
UPS_STATUS = {}
SNMP_STATUS = {}
PROXY_STATUS = {}

STATUS_SNAPSHOT = {
    "projectors": PROJECTOR_STATUS,
    "screens": SCREEN_STATUS,
    "meters": METER_STATUS,
    "ups": UPS_STATUS,
    "snmp": SNMP_STATUS,
    "proxy": PROXY_STATUS,
}


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
                "engine": door_status_info.get("engine", "legacy"),
                "confidence": door_status_info.get("confidence", 0.0),
                "people_count": door_status_info.get("people_count", 0),
                "zone_counts": door_status_info.get("zone_counts", {}),
                "camera_votes": door_status_info.get("camera_votes", {}),
                "detection_camera": door_status_info.get("detection_camera"),
                "updated_at": door_status_info.get("updated_at"),
                "online": True,
            }
    except Exception:
        return {"status": "unknown", "online": False}


def _vision_status_snapshot():
    try:
        from api.door import door_status_info, status_lock

        with status_lock:
            zone_counts = door_status_info.get("zone_counts", {})
            if not isinstance(zone_counts, dict):
                zone_counts = {}
            automation_fields = door_status_info.get("automation_fields", {})
            if not isinstance(automation_fields, dict):
                automation_fields = {}
            return {
                "door_status": door_status_info.get("transition_status") or door_status_info.get("current_status"),
                "door_confidence": door_status_info.get("confidence", 0.0),
                "door_engine": door_status_info.get("engine", "legacy"),
                "people_count": door_status_info.get("people_count", 0),
                "zone_counts": zone_counts,
                "camera_votes": door_status_info.get("camera_votes", {}),
                "detection_camera": door_status_info.get("detection_camera"),
                "updated_at": door_status_info.get("updated_at"),
                "automation_fields": automation_fields,
                "online": True,
                **automation_fields,
            }
    except Exception:
        return {"online": False}


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
        "cabinet_humidity": cab.get("cabinet_humidity"),
    }
    for idx, value in enumerate(channels, start=1):
        state[f"channel_{idx}"] = value
    if channel:
        channel_idx = int(channel)
        if 1 <= channel_idx <= len(channels):
            state["channel_state"] = channels[channel_idx - 1]
    return state


def _get_sequencer_state(dev_id, channel=None):
    target_id = str(dev_id)
    try:
        from api.sequencer import SEQUENCER_STATUS, ensure_config_devices, get_or_init_status

        seq = next((item for item in ensure_config_devices() if str(item.get("id")) == target_id), None)
        if not seq:
            return None
        raw_state = dict(SEQUENCER_STATUS.get(target_id) or get_or_init_status(seq) or {})
        channel_count = int(seq.get("channel_count", 8) or 8)
        channels = list(raw_state.get("channels") or [])
        channels = (channels + [False] * channel_count)[:channel_count]
        online = bool(raw_state.get("online", False))
        state = {
            "id": target_id,
            "name": seq.get("name") or target_id,
            "online": online,
            "channel_count": channel_count,
            "channels": [bool(item) for item in channels],
            "on_count": sum(1 for item in channels if bool(item)),
            "off_count": sum(1 for item in channels if not bool(item)),
            "all_on": bool(online and channel_count > 0 and all(bool(item) for item in channels)),
            "all_off": bool(online and channel_count > 0 and not any(bool(item) for item in channels)),
            "running": bool(raw_state.get("running", False)),
            "locked": bool(raw_state.get("locked", False)),
            "mode": raw_state.get("mode"),
            "last_action": raw_state.get("last_action"),
            "updated_at": raw_state.get("updated_at"),
            "last_success_at": raw_state.get("last_success_at"),
            "error": raw_state.get("error", ""),
        }
        for idx, value in enumerate(channels, start=1):
            state[f"channel_{idx}"] = bool(value)
        if channel:
            channel_idx = int(channel)
            if 1 <= channel_idx <= channel_count:
                state["channel_state"] = bool(channels[channel_idx - 1])
        return state
    except Exception:
        return None


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
                "agent_task_exists": agent.get("task_exists", False),
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
            "work_mode": cab.get("work_mode"),
        }
    return None


def _get_hvac_state(dev_id):
    target_id = str(dev_id)
    try:
        from api.hvac import HVAC_STATUS

        status = HVAC_STATUS.get(target_id)
        if isinstance(status, dict):
            state = dict(status)
            if "fan_mode" not in state and "fan_speed" in state:
                state["fan_mode"] = state.get("fan_speed")
            if "fan_speed" not in state and "fan_mode" in state:
                state["fan_speed"] = state.get("fan_mode")
            return state
    except Exception:
        pass

    for device in CONFIG.get("hvac_devices", []):
        if str(device.get("id")) == target_id:
            return {
                "id": target_id,
                "name": device.get("name") or target_id,
                "online": False,
                "power": False,
                "mode": "off",
                "hvac_action": "off",
                "temp": None,
                "target_temp": None,
                "fan_speed": None,
                "fan_mode": None,
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
    if source_type == "snmp":
        return SNMP_STATUS.get(str(device_id))
    if source_type == "proxy":
        default_state = PROXY_STATUS.get("default")
        if device_id in [None, "", "default"]:
            return default_state
        return PROXY_STATUS.get(str(device_id))
    if source_type == "server":
        return _get_server_state(device_id)
    if source_type == "meter":
        return _get_meter_state(device_id)
    if source_type == "hvac":
        return _get_hvac_state(device_id)
    if source_type == "light":
        return _get_light_state(device_id, channel=channel)
    if source_type == "power":
        return _get_power_state(device_id, channel=channel)
    if source_type == "sequencer":
        return _get_sequencer_state(device_id, channel=channel)
    if source_type == "door":
        return _door_status_snapshot()
    if source_type == "vision":
        return _vision_status_snapshot()
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
