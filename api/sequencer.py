import socket
import threading
import time
from copy import deepcopy
from datetime import datetime

import serial

from flask import Blueprint, jsonify, request

from audit import log_audit_event
from auth.decorators import require_permission
from auth.operation_lock import acquire_operation_lock, release_operation_lock
from auth.session import get_current_user
from config import CONFIG, save_config
from data_logger import add_log, load_logs

bp = Blueprint("sequencer", __name__)


DEFAULT_SEQUENCER_INFO = {
    "id": "sequencer_ds608_1",
    "name": "DS-608 时序电源",
    "brand": "DGH",
    "model": "DS-608",
    "sku": "DS-608",
    "device_type": "时序电源",
    "material": "铝合金",
    "color": "图片色",
    "protocol": "DGH 8路时序器",
    "comm_mode": "TCP",
    "ip": "192.168.50.53",
    "port": 8080,
    "com_port": "COM1",
    "address": 1,
    "baudrate": 19200,
    "data_bits": 8,
    "stop_bits": 1,
    "parity": "NONE",
    "channel_count": 8,
    "sequence_delay_ms": 500,
    "poll_interval_ms": 1200,
    "sort_order": 999,
    "visible": True,
    "channels_config": [{"channel": i, "name": f"CH{i}", "sort": i, "visible": True} for i in range(1, 9)],
}

SEQUENCER_STATUS = {}
_SERIAL_LOCKS = {}
_DEVICE_IO_LOCKS = {}


def get_serial_lock(com_port):
    key = str(com_port or "").upper()
    if key not in _SERIAL_LOCKS:
        _SERIAL_LOCKS[key] = threading.Lock()
    return _SERIAL_LOCKS[key]


def get_device_io_lock(seq):
    seq_id = str((seq or {}).get("id") or "").strip()
    if not seq_id:
        mode = str((seq or {}).get("comm_mode", "TCP")).upper()
        endpoint = f"{mode}:{(seq or {}).get('ip', '')}:{(seq or {}).get('port', '')}:{(seq or {}).get('com_port', '')}:{(seq or {}).get('address', '')}"
        seq_id = endpoint
    if seq_id not in _DEVICE_IO_LOCKS:
        _DEVICE_IO_LOCKS[seq_id] = threading.RLock()
    return _DEVICE_IO_LOCKS[seq_id]


def xor_checksum(address, mode, d1, d2):
    return (int(address) ^ int(mode) ^ int(d1) ^ int(d2)) & 0xFF


def build_short_frame(address, mode, d1=0x00, d2=0x00):
    cs = xor_checksum(address, mode, d1, d2)
    return bytes([0x55, int(address) & 0xFF, int(mode) & 0xFF, int(d1) & 0xFF, int(d2) & 0xFF, cs])


def frame_to_hex(data):
    if not data:
        return ""
    return data.hex(" ").upper()


def extract_status_frame(response):
    raw = bytes(response or b"")
    if len(raw) < 7:
        return None
    for idx in range(0, len(raw) - 6):
        if raw[idx] == 0x57 and raw[idx + 2] == 0xB0:
            return raw[idx : idx + 7]
    return None


def is_ack_response(response):
    raw = bytes(response or b"")
    return len(raw) >= 3 and raw[0] == 0x54


def recent_success_grace_seconds(seq):
    poll_interval = max(0.5, float(int(seq.get("poll_interval_ms", 1200) or 1200)) / 1000.0)
    sequence_delay = max(0.2, float(int(seq.get("sequence_delay_ms", 500) or 500)) / 1000.0)
    return max(2.5, min(8.0, poll_interval * 3.0), min(4.0, sequence_delay * 4.0))


def has_recent_success(seq, state):
    last_success = float((state or {}).get("last_success_monotonic", 0.0) or 0.0)
    if last_success <= 0:
        return False
    return (time.monotonic() - last_success) <= recent_success_grace_seconds(seq)


def humanize_exception(exc):
    text = str(exc or "").strip()
    lower = text.lower()
    if not text:
        return "未知通讯异常"
    if "timed out" in lower or "timeout" in lower:
        return "通讯超时，设备未在规定时间内返回"
    if "actively refused" in lower or "refused" in lower:
        return "目标端口拒绝连接，请检查 IP、端口或设备服务状态"
    if "unreachable" in lower:
        return "网络不可达，请检查网段、VLAN 或网关配置"
    if "reset by peer" in lower:
        return "连接被设备主动断开"
    if "could not open port" in lower:
        return "串口无法打开，请检查 COM 口是否存在或被占用"
    if "cannot find the file" in lower:
        return "串口不存在，请检查 COM 口名称"
    if "permissionerror" in lower or "access is denied" in lower:
        return "端口被占用或无权限访问"
    return text


def summarize_channels(channels):
    if not isinstance(channels, list) or not channels:
        return "无通道状态"
    on_list = [str(idx + 1) for idx, state in enumerate(channels) if bool(state)]
    off_list = [str(idx + 1) for idx, state in enumerate(channels) if not bool(state)]
    on_text = "、".join(on_list) if on_list else "无"
    off_text = "、".join(off_list) if off_list else "无"
    return f"开启: {on_text} | 关闭: {off_text}"


def build_log_device_prefix(seq):
    return f"[时序电源][{seq.get('id', '')}]"


def build_log_message(seq, action_text):
    return f"{build_log_device_prefix(seq)} {seq.get('name', seq.get('id'))} {action_text}"


def device_logs_map(devices, limit_per_device=6):
    all_logs = load_logs(None)
    device_map = {}
    for seq in devices:
        seq_id = str(seq.get("id") or "")
        seq_name = str(seq.get("name") or seq_id)
        matched = []
        prefix = build_log_device_prefix(seq)
        for item in all_logs:
            operation = str(item.get("operation", ""))
            if prefix in operation or (operation.startswith("[时序电源]") and seq_name in operation):
                matched.append(item)
                if len(matched) >= limit_per_device:
                    break
        device_map[seq_id] = matched
    return device_map


def normalize_sequencer(item=None, idx=0):
    seq = deepcopy(DEFAULT_SEQUENCER_INFO)
    if isinstance(item, dict):
        seq.update(item)
    seq["id"] = str(seq.get("id") or f"sequencer_{idx + 1}")
    seq["name"] = str(seq.get("name") or f"时序电源{idx + 1}")
    seq["comm_mode"] = str(seq.get("comm_mode", "TCP")).upper()
    seq["channel_count"] = int(seq.get("channel_count", 8) or 8)
    seq["address"] = int(seq.get("address", 1) or 1)
    seq["port"] = int(seq.get("port", 8080) or 8080)
    seq["baudrate"] = int(seq.get("baudrate", 19200) or 19200)
    seq["data_bits"] = int(seq.get("data_bits", 8) or 8)
    seq["stop_bits"] = int(seq.get("stop_bits", 1) or 1)
    seq["sequence_delay_ms"] = int(seq.get("sequence_delay_ms", 500) or 500)
    seq["poll_interval_ms"] = int(seq.get("poll_interval_ms", 1200) or 1200)
    seq["sort_order"] = int(seq.get("sort_order", 999) or 999)
    custom_channels = {
        int(c.get("channel", 0)): c
        for c in (seq.get("channels_config") or [])
        if isinstance(c, dict)
    }
    channels = []
    for ch in range(1, seq["channel_count"] + 1):
        channel_info = {"channel": ch, "name": f"CH{ch}", "sort": ch, "visible": True}
        if ch in custom_channels:
            channel_info.update(custom_channels[ch])
        channels.append(channel_info)
    seq["channels_config"] = channels
    return seq


def ensure_config_devices():
    sequencers = CONFIG.get("sequencers")
    if not isinstance(sequencers, list) or not sequencers:
        sequencers = [deepcopy(DEFAULT_SEQUENCER_INFO)]
        CONFIG["sequencers"] = sequencers

    normalized = []
    for idx, item in enumerate(sequencers):
        seq = normalize_sequencer(item, idx)
        normalized.append(seq)
    CONFIG["sequencers"] = normalized
    return normalized


def get_or_init_status(seq):
    seq_id = str(seq.get("id"))
    if seq_id not in SEQUENCER_STATUS:
        SEQUENCER_STATUS[seq_id] = {
            "online": False,
            "locked": False,
            "mode": "时序模式",
            "startup_mode": "手动",
            "running": False,
            "channels": [False] * int(seq.get("channel_count", 8)),
            "last_action": "待机",
            "last_command_hex": "",
            "last_response_hex": "",
            "error": "",
            "updated_at": None,
            "last_success_at": None,
            "last_success_monotonic": 0.0,
            "last_polled_monotonic": 0.0,
            "poll_failures": 0,
        }
    state = SEQUENCER_STATUS[seq_id]
    channels = state.get("channels") or []
    if len(channels) != int(seq.get("channel_count", 8)):
        state["channels"] = (channels + [False] * int(seq.get("channel_count", 8)))[: int(seq.get("channel_count", 8))]
    state.setdefault("last_success_monotonic", 0.0)
    state.setdefault("poll_failures", 0)
    return state


def read_socket_reply(sock, timeout):
    deadline = time.monotonic() + max(timeout, 0.1)
    chunks = []
    last_data_at = 0.0
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        sock.settimeout(min(0.18, max(0.05, remaining)))
        try:
            chunk = sock.recv(64)
        except socket.timeout:
            chunk = b""
        if chunk:
            chunks.append(chunk)
            last_data_at = time.monotonic()
            if extract_status_frame(b"".join(chunks)):
                break
            continue
        if chunks and last_data_at and (time.monotonic() - last_data_at) >= 0.08:
            break
    return b"".join(chunks)


def read_serial_reply(ser, timeout):
    deadline = time.monotonic() + max(timeout, 0.1)
    chunks = []
    last_data_at = 0.0
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        ser.timeout = min(0.18, max(0.05, remaining))
        waiting = getattr(ser, "in_waiting", 0) or 0
        chunk = ser.read(waiting if waiting > 0 else 64)
        if chunk:
            chunks.append(chunk)
            last_data_at = time.monotonic()
            if extract_status_frame(b"".join(chunks)):
                break
            continue
        if chunks and last_data_at and (time.monotonic() - last_data_at) >= 0.08:
            break
    return b"".join(chunks)


def send_frame(seq, payload, expect_reply=True, timeout=1.2):
    mode = str(seq.get("comm_mode", "TCP")).upper()
    if mode == "COM":
        com_port = seq.get("com_port", "COM1")
        parity = str(seq.get("parity", "NONE")).upper()
        parity_map = {
            "NONE": serial.PARITY_NONE,
            "N": serial.PARITY_NONE,
            "ODD": serial.PARITY_ODD,
            "O": serial.PARITY_ODD,
            "EVEN": serial.PARITY_EVEN,
            "E": serial.PARITY_EVEN,
        }
        with get_serial_lock(com_port):
            with serial.Serial(
                com_port,
                baudrate=int(seq.get("baudrate", 19200)),
                bytesize=int(seq.get("data_bits", 8)),
                stopbits=int(seq.get("stop_bits", 1)),
                parity=parity_map.get(parity, serial.PARITY_NONE),
                timeout=timeout,
            ) as ser:
                ser.reset_input_buffer()
                ser.write(payload)
                ser.flush()
                if not expect_reply:
                    return True, b""
                time.sleep(0.05)
                data = read_serial_reply(ser, timeout)
                return True, data

    ip = str(seq.get("ip", "")).strip()
    port = int(seq.get("port", 8080))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect((ip, port))
        sock.sendall(payload)
        if not expect_reply:
            return True, b""
        time.sleep(0.05)
        data = read_socket_reply(sock, timeout)
        return True, data


def parse_status_response(response, channel_count=8):
    frame = extract_status_frame(response)
    if not frame or len(frame) < 7:
        return None
    d1, d2, d3 = frame[3], frame[4], frame[5]
    channels = []
    for idx in range(channel_count):
        bit = 7 - idx
        # DS-608 实测状态位语义：1=该路开启，0=该路关闭。
        is_on = ((d2 >> bit) & 0x01) == 1
        channels.append(is_on)
    return {
        "lcd_on": (d1 & 0x01) == 0,
        "locked": ((d1 >> 1) & 0x01) == 1,
        "running": ((d1 >> 2) & 0x01) == 1,
        "channels": channels,
        "mask_bits": d3,
    }


def poll_sequencer_once(seq, retries=2, retry_delay=0.12):
    state = get_or_init_status(seq)
    query = build_short_frame(seq.get("address", 1), 0xA8, 0x00, 0x00)
    with get_device_io_lock(seq):
        try:
            response = b""
            parsed = None
            ok = False
            for attempt in range(max(1, int(retries) + 1)):
                ok, response = send_frame(seq, query, expect_reply=True, timeout=1.2)
                if not ok:
                    raise RuntimeError("发送失败")
                parsed = parse_status_response(response, int(seq.get("channel_count", 8)))
                if parsed:
                    break
                if attempt < int(retries):
                    time.sleep(retry_delay * (attempt + 1))

            state["last_command_hex"] = frame_to_hex(query)
            state["last_response_hex"] = frame_to_hex(response)
            state["updated_at"] = datetime.now().isoformat()
            state["last_polled_monotonic"] = time.monotonic()

            if parsed:
                state["online"] = True
                state["locked"] = parsed["locked"]
                state["running"] = parsed["running"]
                state["channels"] = parsed["channels"]
                state["mode"] = "时序模式"
                state["error"] = ""
                state["last_action"] = "轮询更新"
                state["last_success_at"] = state["updated_at"]
                state["last_success_monotonic"] = state["last_polled_monotonic"]
                state["poll_failures"] = 0
                return state

            state["poll_failures"] = int(state.get("poll_failures", 0) or 0) + 1
            if has_recent_success(seq, state) and int(state.get("poll_failures", 0) or 0) < 3:
                state["online"] = True
                state["error"] = ""
                if is_ack_response(response):
                    state["last_action"] = "指令确认 / 等待状态刷新"
                return state

            state["online"] = False
            state["error"] = "状态返回格式无效" if response else "设备无状态回包"
            return state
        except Exception as exc:
            state["updated_at"] = datetime.now().isoformat()
            state["last_polled_monotonic"] = time.monotonic()
            state["poll_failures"] = int(state.get("poll_failures", 0) or 0) + 1
            if has_recent_success(seq, state) and int(state.get("poll_failures", 0) or 0) < 3:
                state["online"] = True
                state["error"] = ""
                return state
            state["online"] = False
            state["error"] = humanize_exception(exc)
            return state


def control_sequencer(seq, action, channel=None):
    address = int(seq.get("address", 1))
    if action == "toggle_channel":
        if not channel:
            raise ValueError("缺少通道号")
        current = get_or_init_status(seq)["channels"]
        is_on = not bool(current[channel - 1])
        frame = build_short_frame(address, 0xA0 if is_on else 0xA1, 0x00, int(channel))
        action_text = f"第{channel}路{'开启' if is_on else '关闭'}"
    elif action == "channel_on":
        if not channel:
            raise ValueError("缺少通道号")
        frame = build_short_frame(address, 0xA0, 0x00, int(channel))
        action_text = f"第{channel}路开启"
    elif action == "channel_off":
        if not channel:
            raise ValueError("缺少通道号")
        frame = build_short_frame(address, 0xA1, 0x00, int(channel))
        action_text = f"第{channel}路关闭"
    elif action == "sequence_on":
        frame = build_short_frame(address, 0xA4, 0x00, 0x00)
        action_text = "顺序开启"
    elif action == "sequence_off":
        frame = build_short_frame(address, 0xA5, 0x00, 0x00)
        action_text = "逆序关闭"
    elif action == "all_on":
        frame = build_short_frame(address, 0xA2, 0x00, 0x00)
        action_text = "全部开启"
    elif action == "all_off":
        frame = build_short_frame(address, 0xA3, 0x00, 0x00)
        action_text = "全部关闭"
    elif action == "toggle_lock":
        state = get_or_init_status(seq)
        lock_on = not bool(state.get("locked", False))
        frame = bytes.fromhex(f"55 {address:02X} AE {'AA 00 05' if lock_on else '55 00 FA'}")
        action_text = "锁定设备" if lock_on else "解除锁定"
    else:
        raise ValueError("不支持的操作")

    state = get_or_init_status(seq)
    settle_delay = max(0.18, min(0.65, float(int(seq.get("sequence_delay_ms", 500) or 500)) / 1000.0 * 0.5))
    with get_device_io_lock(seq):
        ok, response = send_frame(seq, frame, expect_reply=True, timeout=0.45)
        state["last_command_hex"] = frame_to_hex(frame)
        state["last_response_hex"] = frame_to_hex(response)
        state["last_action"] = action_text
        state["updated_at"] = datetime.now().isoformat()
        if settle_delay > 0:
            time.sleep(settle_delay)
        poll_sequencer_once(seq, retries=3, retry_delay=0.14)
    add_log(-1, build_log_message(seq, action_text))
    return {
        "success": ok,
        "command": frame_to_hex(frame),
        "response": frame_to_hex(response),
        "state": get_or_init_status(seq),
    }


def snapshot(seq):
    state = get_or_init_status(seq)
    channel_items = []
    for idx, cfg in enumerate(seq.get("channels_config") or []):
        channel_items.append({
            "channel": cfg.get("channel", idx + 1),
            "name": cfg.get("name", f"CH{idx + 1}"),
            "visible": cfg.get("visible", True),
            "state": bool((state.get("channels") or [False] * seq.get("channel_count", 8))[idx]),
        })
    return {
        "id": seq["id"],
        "name": seq.get("name") or seq["id"],
        "brand": seq.get("brand", "DGH"),
        "model": seq.get("model", "DS-608"),
        "sku": seq.get("sku", "DS-608"),
        "device_type": seq.get("device_type", "时序电源"),
        "protocol": seq.get("protocol", "DGH 8路时序器"),
        "comm_mode": str(seq.get("comm_mode", "TCP")).upper(),
        "ip": seq.get("ip", ""),
        "port": seq.get("port", 8080),
        "com_port": seq.get("com_port", "COM1"),
        "address": int(seq.get("address", 1)),
        "baudrate": int(seq.get("baudrate", 19200)),
        "data_bits": int(seq.get("data_bits", 8)),
        "stop_bits": int(seq.get("stop_bits", 1)),
        "parity": seq.get("parity", "NONE"),
        "channel_count": int(seq.get("channel_count", 8)),
        "poll_interval_ms": int(seq.get("poll_interval_ms", 1200)),
        "sort_order": int(seq.get("sort_order", 999)),
        "online": bool(state.get("online", False)),
        "locked": bool(state.get("locked", False)),
        "mode": state.get("mode", "时序模式"),
        "startup_mode": state.get("startup_mode", "手动"),
        "running": bool(state.get("running", False)),
        "last_action": state.get("last_action", "待机"),
        "last_command_hex": state.get("last_command_hex", ""),
        "last_response_hex": state.get("last_response_hex", ""),
        "error": state.get("error", ""),
        "error_display": state.get("error", ""),
        "updated_at": state.get("updated_at"),
        "last_success_at": state.get("last_success_at"),
        "channel_summary": summarize_channels([item.get("state") for item in channel_items]),
        "channels": channel_items,
    }


def run_connectivity_test(seq):
    query = build_short_frame(seq.get("address", 1), 0xA8, 0x00, 0x00)
    with get_device_io_lock(seq):
        ok, response = send_frame(seq, query, expect_reply=True, timeout=1.5)
    parsed = parse_status_response(response, int(seq.get("channel_count", 8)))
    if parsed:
        message = "通讯正常，已收到状态回包"
    elif is_ack_response(response):
        message = "已收到设备确认帧，状态帧尚未返回"
    else:
        message = "已建立连接，但状态回包为空或格式无效" if response else "设备无状态回包"
    return {
        "success": bool(ok and parsed),
        "message": message,
        "command": frame_to_hex(query),
        "response": frame_to_hex(response),
        "parsed": parsed,
        "channel_summary": summarize_channels((parsed or {}).get("channels") or []),
    }


@bp.route("/api/sequencer/status")
@require_permission("sequencer.view")
def api_sequencer_status():
    raw_devices = ensure_config_devices()
    devices = [snapshot(seq) for seq in raw_devices]
    logs_map = device_logs_map(raw_devices, limit_per_device=6)
    logs = [item for item in load_logs(None) if "[时序电源]" in str(item.get("operation", ""))][:20]
    for device in devices:
        device["logs"] = logs_map.get(str(device.get("id")), [])
    return jsonify({"devices": devices, "logs": logs})


@bp.route("/api/sequencer/control", methods=["POST"])
@require_permission("sequencer.control")
def api_sequencer_control():
    payload = request.json or {}
    seq_id = str(payload.get("id") or "")
    action = str(payload.get("action") or "")
    channel = payload.get("channel")
    current_user = get_current_user()
    seq = next((item for item in ensure_config_devices() if item["id"] == seq_id), None)
    if not seq:
        log_audit_event(
            "sequencer.control",
            target=seq_id,
            detail={"id": seq_id, "action": action, "channel": channel, "error": "device_not_found"},
            status="error",
        )
        return jsonify({"success": False, "message": "未找到时序电源设备"}), 404
    lock_key = f"sequencer:{seq_id}"
    locked, lock_info = acquire_operation_lock(lock_key, current_user.username, action, timeout_sec=2.5)
    if not locked:
        return jsonify({
            "success": False,
            "message": f"设备正在被 [{lock_info.get('owner')}] 操作，请稍后再试",
            "error": "device_busy",
        }), 409
    try:
        result = control_sequencer(seq, action, int(channel) if channel not in (None, "") else None)
        log_audit_event(
            "sequencer.control",
            target=seq_id,
            detail={"id": seq_id, "action": action, "channel": channel, "command": result["command"]},
        )
        return jsonify({"success": True, "command": result["command"], "response": result["response"], "device": snapshot(seq)})
    except Exception as exc:
        log_audit_event(
            "sequencer.control",
            target=seq_id,
            detail={"id": seq_id, "action": action, "channel": channel, "error": str(exc)},
            status="error",
        )
        return jsonify({"success": False, "message": str(exc)}), 400
    finally:
        release_operation_lock(lock_key, current_user.username)


@bp.route("/api/sequencer/test", methods=["POST"])
@require_permission("sequencer.view")
def api_sequencer_test():
    payload = request.json or {}
    seq_id = str(payload.get("id") or "")
    test_type = str(payload.get("type") or "connectivity")
    device_payload = payload.get("device")

    if isinstance(device_payload, dict):
        seq = normalize_sequencer(device_payload)
    else:
        seq = next((item for item in ensure_config_devices() if item["id"] == seq_id), None)

    if not seq:
        return jsonify({"success": False, "message": "未找到时序电源设备"}), 404

    try:
        if test_type == "status":
            state = poll_sequencer_once(seq)
            return jsonify({
                "success": bool(state.get("online")),
                "message": "状态查询完成" if state.get("online") else (state.get("error") or "状态查询失败"),
                "device": snapshot(seq),
                "channel_summary": summarize_channels(state.get("channels") or []),
            })
        if test_type in ["channel_on", "channel_off"]:
            channel = int(payload.get("channel") or 1)
            result = control_sequencer(seq, test_type, channel)
            device = snapshot(seq)
            return jsonify({
                "success": True,
                "message": f"已执行第{channel}路{'开启' if test_type == 'channel_on' else '关闭'}测试",
                "command": result["command"],
                "response": result["response"],
                "device": device,
                "channel_summary": summarize_channels([item.get("state") for item in (device.get("channels") or [])]),
            })

        result = run_connectivity_test(seq)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"success": False, "message": humanize_exception(exc)}), 400


@bp.route("/api/sequencer/save_defaults", methods=["POST"])
@require_permission("system.config")
def api_sequencer_save_defaults():
    current = CONFIG.get("sequencers")
    if not isinstance(current, list) or not current:
        CONFIG["sequencers"] = [deepcopy(DEFAULT_SEQUENCER_INFO)]
        save_config(CONFIG)
        log_audit_event("sequencer.defaults.save", target="sequencers", detail={"created_default": True})
    else:
        log_audit_event("sequencer.defaults.save", target="sequencers", detail={"created_default": False})
    return jsonify({"success": True, "devices": [snapshot(seq) for seq in ensure_config_devices()]})
