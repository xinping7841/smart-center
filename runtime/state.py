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
    if source_type == "light":
        return _get_light_state(device_id, channel=channel)
    if source_type == "power":
        return _get_power_state(device_id, channel=channel)
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
