import base64
from urllib.parse import quote
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime


_USER_AGENT = "smart-center-hikvision-nvr/1.0"


def _local_name(tag):
    return str(tag or "").split("}", 1)[-1].lower()


def _children(element, name=None):
    if element is None:
        return []
    if name is None:
        return list(element)
    target = str(name).lower()
    return [child for child in list(element) if _local_name(child.tag) == target]


def _first_child(element, *names):
    current = element
    for name in names:
        matches = _children(current, name)
        current = matches[0] if matches else None
        if current is None:
            return None
    return current


def _text(element, *names, default=""):
    target = _first_child(element, *names) if names else element
    if target is None or target.text is None:
        return default
    return str(target.text).strip()


def _bool_text(value):
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "online", "ok", "normal", "connected"}


def _int_text(value, default=None):
    try:
        return int(float(str(value).strip()))
    except Exception:
        return default


def _format_storage_mb(value):
    mb = _int_text(value)
    if mb is None:
        return "--"
    gb = mb / 1024.0
    if gb >= 1024:
        return f"{gb / 1024.0:.2f} TB"
    if gb >= 100:
        return f"{gb:.0f} GB"
    return f"{gb:.1f} GB"


def _format_uptime(seconds):
    total = _int_text(seconds, 0) or 0
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    if days > 0:
        return f"{days}天 {hours}小时"
    if hours > 0:
        return f"{hours}小时 {minutes}分"
    return f"{minutes}分"


def _make_opener(base_url, username, password):
    manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    manager.add_password(None, base_url, username or "", password or "")
    digest_handler = urllib.request.HTTPDigestAuthHandler(manager)
    return urllib.request.build_opener(digest_handler)


def _request_xml(opener, base_url, path, timeout_sec):
    url = f"{base_url}{path}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/xml,text/xml,*/*",
            "User-Agent": _USER_AGENT,
        },
    )
    with opener.open(request, timeout=timeout_sec) as response:
        payload = response.read(2 * 1024 * 1024)
    return ET.fromstring(payload)


def _request_bytes(opener, base_url, path, timeout_sec, accept="*/*"):
    url = f"{base_url}{path}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": _USER_AGENT,
        },
    )
    with opener.open(request, timeout=timeout_sec) as response:
        return response.read(4 * 1024 * 1024), response.headers.get("Content-Type") or "application/octet-stream"


def _parse_device_info(root):
    return {
        "device_name": _text(root, "deviceName"),
        "device_id": _text(root, "deviceID"),
        "model": _text(root, "model"),
        "serial_number": _text(root, "serialNumber"),
        "mac_address": _text(root, "macAddress"),
        "firmware_version": _text(root, "firmwareVersion"),
        "firmware_build": _text(root, "firmwareReleasedDate") or _text(root, "firmwareBuildDate"),
        "hardware_version": _text(root, "hardwareVersion"),
        "manufacturer": _text(root, "manufacturer"),
    }


def _parse_system_status(root):
    uptime_sec = _int_text(_text(root, "deviceUpTime"), 0)
    memory_usage = _int_text(_text(root, "memoryUsage"))
    memory_available = _int_text(_text(root, "memoryAvailable"))
    return {
        "device_time": _text(root, "currentDeviceTime"),
        "uptime_sec": uptime_sec,
        "uptime_text": _format_uptime(uptime_sec),
        "memory_usage_percent": memory_usage,
        "memory_available_kb": memory_available,
    }


def _parse_channels(root):
    channels = []
    for node in root.iter():
        if _local_name(node.tag) not in {"inputproxychannel", "channel"}:
            continue
        channel_id = _text(node, "id")
        if not channel_id:
            continue
        channels.append(
            {
                "id": channel_id,
                "name": _text(node, "name") or _text(node, "cameraName") or f"D{channel_id}",
                "ip": _text(node, "ipAddress") or _text(node, "srcInputPortDescriptor", "ipAddress"),
                "protocol": _text(node, "protocol") or _text(node, "manageProtocol"),
                "enabled": not (_text(node, "enable").lower() == "false"),
            }
        )
    return channels


def _parse_channel_status(root):
    statuses = {}
    for node in root.iter():
        if _local_name(node.tag) not in {"inputproxychannelstatus", "channelstatus"}:
            continue
        channel_id = _text(node, "id")
        if not channel_id:
            continue
        password_status = _text(node, "SecurityStatus", "PasswordStatus") or _text(node, "PasswordStatus")
        statuses[channel_id] = {
            "id": channel_id,
            "online": _bool_text(_text(node, "online")),
            "detect_result": _text(node, "chanDetectResult") or _text(node, "detectResult"),
            "streaming_status": _text(node, "streamingStatus"),
            "recording_status": _text(node, "recordingStatus"),
            "password_status": password_status,
        }
    return statuses


def _parse_hdds(root):
    hdds = []
    for node in root.iter():
        if _local_name(node.tag) != "hdd":
            continue
        hdd_id = _text(node, "id")
        status = (_text(node, "status") or _text(node, "hddStatus")).lower()
        capacity = _text(node, "capacity")
        free_space = _text(node, "freeSpace")
        hdds.append(
            {
                "id": hdd_id,
                "name": _text(node, "hddName") or _text(node, "name") or f"HDD{hdd_id or ''}",
                "status": status or "--",
                "status_text": "正常" if status in {"ok", "normal"} else (status or "未知"),
                "property": _text(node, "property"),
                "type": _text(node, "type"),
                "capacity_mb": _int_text(capacity),
                "free_mb": _int_text(free_space),
                "capacity_text": _format_storage_mb(capacity),
                "free_text": _format_storage_mb(free_space),
            }
        )
    return hdds


def _merge_channel_data(channels, status_map, name_map):
    merged = []
    seen = set()
    for channel in channels:
        channel_id = str(channel.get("id") or "").strip()
        if not channel_id:
            continue
        status = dict(status_map.get(channel_id, {}) or {})
        name = str(name_map.get(channel_id) or channel.get("name") or f"D{channel_id}").strip()
        item = dict(channel)
        item.update(status)
        item["id"] = channel_id
        item["name"] = name
        item["online"] = bool(status.get("online", False))
        merged.append(item)
        seen.add(channel_id)
    for channel_id, status in status_map.items():
        if channel_id in seen:
            continue
        item = dict(status)
        item["id"] = str(channel_id)
        item["name"] = str(name_map.get(str(channel_id)) or f"D{channel_id}")
        item["online"] = bool(status.get("online", False))
        merged.append(item)
    merged.sort(key=lambda item: _int_text(item.get("id"), 9999) or 9999)
    return merged


def _load_channel_name_map(cfg):
    mapping = {}
    raw_map = cfg.get("channel_name_map")
    if isinstance(raw_map, dict):
        mapping.update({str(k): str(v) for k, v in raw_map.items() if str(v).strip()})
    inventory_path = str(cfg.get("camera_inventory_path") or "").strip()
    if inventory_path:
        try:
            import json

            with open(inventory_path, "r", encoding="utf-8") as handle:
                rows = json.load(handle)
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    channel = str(row.get("channel") or "").strip().upper()
                    name = str(row.get("name") or "").strip()
                    if channel.startswith("D") and channel[1:].isdigit() and name:
                        mapping[channel[1:]] = name
            elif isinstance(rows, dict):
                for key, row in rows.items():
                    channel = str(key or "").strip().upper()
                    name = str(row.get("name") if isinstance(row, dict) else row or "").strip()
                    if channel.startswith("D") and channel[1:].isdigit() and name:
                        mapping[channel[1:]] = name
        except Exception:
            pass
    return mapping


def _build_summary(status):
    channel_total = int(status.get("channel_total") or 0)
    channel_offline = int(status.get("channel_offline") or 0)
    hdd_total = int(status.get("hdd_total") or 0)
    hdd_error = int(status.get("hdd_error_count") or 0)
    weak_password = int(status.get("weak_password_count") or 0)
    risk_level = "normal"
    if hdd_error > 0:
        risk_level = "critical"
    elif channel_offline > 0 or weak_password > 0:
        risk_level = "warning"
    score = 100
    if hdd_total:
        score -= hdd_error * 25
    if channel_total:
        score -= round((channel_offline / max(1, channel_total)) * 35)
    score -= min(15, weak_password * 3)
    return {
        "risk_level": risk_level,
        "health_score": max(0, min(100, int(score))),
        "channel_total": channel_total,
        "channel_online": int(status.get("channel_online") or 0),
        "channel_offline": channel_offline,
        "hdd_total": hdd_total,
        "hdd_ok_count": int(status.get("hdd_ok_count") or 0),
        "hdd_error_count": hdd_error,
        "weak_password_count": weak_password,
    }


def poll_hikvision_nvr(cfg):
    scheme = "https" if str(cfg.get("scheme") or cfg.get("protocol_scheme") or "http").lower() == "https" else "http"
    host = str(cfg.get("host") or cfg.get("ip") or "").strip()
    if not host:
        raise ValueError("NVR host is empty")
    port = int(cfg.get("port", 80) or 80)
    timeout_sec = max(1.0, min(float(cfg.get("timeout_sec", 5.0) or 5.0), 30.0))
    base_url = f"{scheme}://{host}:{port}"
    opener = _make_opener(base_url, str(cfg.get("username") or ""), str(cfg.get("password") or ""))
    name_map = _load_channel_name_map(cfg)

    device_info = _parse_device_info(_request_xml(opener, base_url, "/ISAPI/System/deviceInfo", timeout_sec))
    system_status = _parse_system_status(_request_xml(opener, base_url, "/ISAPI/System/status", timeout_sec))
    channels = _parse_channels(_request_xml(opener, base_url, "/ISAPI/ContentMgmt/InputProxy/channels", timeout_sec))
    channel_status = _parse_channel_status(_request_xml(opener, base_url, "/ISAPI/ContentMgmt/InputProxy/channels/status", timeout_sec))
    hdds = _parse_hdds(_request_xml(opener, base_url, "/ISAPI/ContentMgmt/Storage/hdd", timeout_sec))

    merged_channels = _merge_channel_data(channels, channel_status, name_map)
    if cfg.get("expected_channel_count") and len(merged_channels) < int(cfg.get("expected_channel_count") or 0):
        existing = {str(item.get("id")) for item in merged_channels}
        for idx in range(1, int(cfg.get("expected_channel_count") or 0) + 1):
            channel_id = str(idx)
            if channel_id not in existing:
                merged_channels.append({"id": channel_id, "name": name_map.get(channel_id, f"D{channel_id}"), "online": False})
        merged_channels.sort(key=lambda item: _int_text(item.get("id"), 9999) or 9999)

    online_channels = [item for item in merged_channels if item.get("online")]
    offline_channels = [item for item in merged_channels if not item.get("online")]
    hdd_ok = [item for item in hdds if str(item.get("status") or "").lower() in {"ok", "normal"}]
    hdd_error = [item for item in hdds if item not in hdd_ok]
    weak_password = [
        item for item in merged_channels
        if str(item.get("password_status") or "").strip()
        and str(item.get("password_status") or "").strip().lower() not in {"strong", "safe", "normal", "ok"}
    ]
    capacity_mb = sum(int(item.get("capacity_mb") or 0) for item in hdds)
    free_mb = sum(int(item.get("free_mb") or 0) for item in hdds)
    status_level = "online"
    if hdd_error:
        status_level = "error"
    elif offline_channels or weak_password:
        status_level = "stale"
    payload = {
        "online": True,
        "status_level": status_level,
        "status_label": "正常" if status_level == "online" else ("异常" if status_level == "error" else "关注"),
        "device_info": device_info,
        "device_time": system_status.get("device_time"),
        "uptime_sec": system_status.get("uptime_sec"),
        "uptime_text": system_status.get("uptime_text"),
        "memory_usage_percent": system_status.get("memory_usage_percent"),
        "memory_available_kb": system_status.get("memory_available_kb"),
        "hdds": hdds,
        "hdd_total": len(hdds),
        "hdd_ok_count": len(hdd_ok),
        "hdd_error_count": len(hdd_error),
        "hdd_capacity_mb": capacity_mb,
        "hdd_free_mb": free_mb,
        "hdd_capacity_text": _format_storage_mb(capacity_mb),
        "hdd_free_text": _format_storage_mb(free_mb),
        "channels": merged_channels,
        "channel_total": len(merged_channels),
        "channel_online": len(online_channels),
        "channel_offline": len(offline_channels),
        "offline_channels": offline_channels,
        "weak_password_count": len(weak_password),
        "weak_password_channels": weak_password,
        "checked_source": "hikvision_isapi",
    }
    payload["summary"] = _build_summary(payload)
    return payload


def fetch_hikvision_snapshot(cfg, channel_id, stream="2"):
    scheme = "https" if str(cfg.get("scheme") or cfg.get("protocol_scheme") or "http").lower() == "https" else "http"
    host = str(cfg.get("host") or cfg.get("ip") or "").strip()
    if not host:
        raise ValueError("NVR host is empty")
    port = int(cfg.get("port", 80) or 80)
    timeout_sec = max(1.0, min(float(cfg.get("snapshot_timeout_sec", cfg.get("timeout_sec", 5.0)) or 5.0), 30.0))
    base_url = f"{scheme}://{host}:{port}"
    opener = _make_opener(base_url, str(cfg.get("username") or ""), str(cfg.get("password") or ""))
    channel_num = _int_text(channel_id)
    if channel_num is None or channel_num <= 0:
        raise ValueError("Invalid NVR channel")
    stream_text = str(stream or cfg.get("snapshot_stream") or "2").strip().lower()
    stream_idx = 1 if stream_text in {"1", "main", "mainstream", "primary"} else 2
    hik_channel = f"{channel_num}{stream_idx:02d}"
    return _request_bytes(
        opener,
        base_url,
        f"/ISAPI/Streaming/channels/{hik_channel}/picture",
        timeout_sec,
        accept="image/jpeg,image/*,*/*",
    )


def build_hikvision_rtsp_url(cfg, channel_id, stream="2"):
    host = str(cfg.get("rtsp_host") or cfg.get("host") or cfg.get("ip") or "").strip()
    if not host:
        raise ValueError("NVR host is empty")
    try:
        port = int(cfg.get("rtsp_port", 554) or 554)
    except Exception:
        port = 554
    username = quote(str(cfg.get("username") or ""), safe="")
    password = quote(str(cfg.get("password") or ""), safe="")
    channel_num = _int_text(channel_id)
    if channel_num is None or channel_num <= 0:
        raise ValueError("Invalid NVR channel")
    stream_text = str(stream or cfg.get("live_stream") or cfg.get("snapshot_stream") or "2").strip().lower()
    stream_idx = 1 if stream_text in {"1", "main", "mainstream", "primary"} else 2
    hik_channel = f"{channel_num}{stream_idx:02d}"
    auth = f"{username}:{password}@" if username or password else ""
    return f"rtsp://{auth}{host}:{port}/Streaming/Channels/{hik_channel}"


def build_basic_auth_header(username, password):
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"
