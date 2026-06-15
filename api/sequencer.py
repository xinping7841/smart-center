# AI_MODULE: sequencer_api
# AI_PURPOSE: 8 路时序电源状态读取、单路控制、顺序开关和测试接口。
# AI_BOUNDARY: 只处理时序器协议和 API；强电柜控制在 api/power.py。
# AI_DATA_FLOW: CONFIG.sequencers -> TCP/串口十六进制指令 -> SEQUENCER_STATUS -> 前端。
# AI_RUNTIME: 首页和时序电源页面轮询/控制。
# AI_RISK: 高，关闭时序电源会影响投影、LED、机柜等现场设备。
# AI_COMPAT: DS-608/DGH 十六进制命令、单路/顺序/全部控制语义必须保持。
# AI_SEARCH_KEYWORDS: sequencer, DS-608, DGH, hex, channel, sequence power.

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
from event_logger import record_event, record_state_change
from log_config import get_logger
_log = get_logger(__name__)

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
_STATE_CHANGE_LOG_CACHE = {}
_STATE_CHANGE_VALUE_CACHE = {}


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


def _display_bool_state(value):
    return "开" if bool(value) else "关"


def _channel_label_from_config(seq, ch_num):
    for item in (seq or {}).get("channels_config", []) or []:
        try:
            if int(item.get("channel", 0) or 0) != int(ch_num):
                continue
        except Exception:
            continue
        name = str(item.get("name") or "").strip()
        remark = str(item.get("remark") or item.get("usage") or item.get("description") or "").strip()
        if name and remark and remark not in name:
            return f"{name}({remark})"
        if name:
            return name
        if remark:
            return remark
    return f"第{ch_num}路"


def _changed_channel_text(previous, current, seq):
    if not isinstance(previous, list) or not isinstance(current, list):
        return ""
    if not previous or not current:
        return ""
    pieces = []
    for idx, (old_value, new_value) in enumerate(zip(previous, current), start=1):
        if old_value is None or new_value is None:
            continue
        if bool(old_value) == bool(new_value):
            continue
        pieces.append(f"{_channel_label_from_config(seq, idx)} {_display_bool_state(old_value)}->{_display_bool_state(new_value)}")
    return "、".join(pieces)


def _observed_channel_change_text(cache_key, current, seq):
    if not isinstance(current, list) or not current:
        return ""
    normalized = [None if item is None else bool(item) for item in current]
    previous = _STATE_CHANGE_VALUE_CACHE.get(cache_key)
    _STATE_CHANGE_VALUE_CACHE[cache_key] = list(normalized)
    if previous is None:
        return ""
    return _changed_channel_text(list(previous), normalized, seq)


def _record_detected_change(cache_key, message, min_interval_sec=1.5):
    text = str(message or "").strip()
    if not text:
        return
    now_ts = time.time()
    previous = _STATE_CHANGE_LOG_CACHE.get(cache_key) or {}
    if previous.get("message") == text and (now_ts - float(previous.get("ts", 0.0) or 0.0)) < min_interval_sec:
        return
    _STATE_CHANGE_LOG_CACHE[cache_key] = {"message": text, "ts": now_ts}
    add_log(-1, text)


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
                seq_id = str(seq.get("id") or seq.get("ip") or seq.get("name") or "")
                changed_text = _observed_channel_change_text(f"sequencer:{seq_id}:channels:observed", parsed["channels"], seq)
                if changed_text:
                    seq_name = str(seq.get("name") or seq_id or "时序电源")
                    _record_detected_change(
                        f"sequencer:{seq_id}:channels",
                        f"[状态变化][时序电源] {seq_name} {changed_text}（外部/轮询识别）",
                    )
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


def channels_match(channels, expected):
    if not isinstance(channels, list) or not isinstance(expected, list):
        return False
    if len(channels) < len(expected):
        return False
    return all(bool(channels[idx]) == bool(value) for idx, value in enumerate(expected))


def channel_matches(channels, channel, expected_on):
    if not isinstance(channels, list):
        return False
    index = int(channel) - 1
    if index < 0 or index >= len(channels):
        return False
    return bool(channels[index]) == bool(expected_on)


def poll_until_confirmed(seq, expected_channels=None, channel=None, expected_on=None, attempts=3, retry_delay=0.16):
    state = get_or_init_status(seq)
    for attempt in range(max(1, int(attempts))):
        if attempt > 0:
            time.sleep(retry_delay * attempt)
        state = poll_sequencer_once(seq, retries=1, retry_delay=0.1)
        channels = state.get("channels") or []
        if expected_channels is not None and channels_match(channels, expected_channels):
            return True, state
        if channel is not None and channel_matches(channels, channel, expected_on):
            return True, state
        if expected_channels is None and channel is None and state.get("online"):
            return True, state
    return False, state


def set_control_state_fields(state, command, response, action_text):
    state["last_command_hex"] = frame_to_hex(command)
    state["last_response_hex"] = frame_to_hex(response)
    state["last_action"] = action_text
    state["updated_at"] = datetime.now().isoformat()


def control_sequencer(seq, action, channel=None):
    address = int(seq.get("address", 1))
    channel_count = int(seq.get("channel_count", 8))
    step_delay = max(0.12, min(1.5, float(int(seq.get("sequence_delay_ms", 500) or 500)) / 1000.0))
    settle_delay = max(0.18, min(0.65, step_delay * 0.5))
    retry_delay = max(0.16, min(0.5, step_delay * 0.45))
    confirm_attempts = 3 if action in ("sequence_on", "sequence_off", "all_on", "all_off") else 2
    state = get_or_init_status(seq)
    # Refresh before control so toggle actions use the real device state, not a stale cache.
    if action in ("toggle_channel", "toggle_lock", "sequence_on", "sequence_off", "all_on", "all_off"):
        poll_sequencer_once(seq, retries=2, retry_delay=0.12)
    current_channels = list((state.get("channels") or [False] * channel_count)[:channel_count])
    if len(current_channels) < channel_count:
        current_channels += [False] * (channel_count - len(current_channels))

    steps = []
    if action == "toggle_channel":
        if not channel:
            raise ValueError("缺少通道号")
        is_on = not bool(current_channels[channel - 1])
        frame = build_short_frame(address, 0xA0 if is_on else 0xA1, 0x00, int(channel))
        action_text = f"第{channel}路{'开启' if is_on else '关闭'}"
        steps = [{"frame": frame, "channel": int(channel), "expected_on": is_on, "label": action_text}]
    elif action == "channel_on":
        if not channel:
            raise ValueError("缺少通道号")
        frame = build_short_frame(address, 0xA0, 0x00, int(channel))
        action_text = f"第{channel}路开启"
        steps = [{"frame": frame, "channel": int(channel), "expected_on": True, "label": action_text}]
    elif action == "channel_off":
        if not channel:
            raise ValueError("缺少通道号")
        frame = build_short_frame(address, 0xA1, 0x00, int(channel))
        action_text = f"第{channel}路关闭"
        steps = [{"frame": frame, "channel": int(channel), "expected_on": False, "label": action_text}]
    elif action == "sequence_on":
        repair_steps = [
            {"frame": build_short_frame(address, 0xA0, 0x00, ch), "channel": ch, "expected_on": True, "label": f"第{ch}路开启"}
            for ch in range(1, channel_count + 1)
        ]
        steps = [{
            "frame": build_short_frame(address, 0xA4, 0x00, 0x00),
            "expected_channels": [True] * channel_count,
            "label": "顺序开启",
            "post_delay": max(step_delay * channel_count + 0.35, 1.2),
            "max_attempts": 1,
            "repair_steps": repair_steps,
        }]
        action_text = "顺序开启"
    elif action == "sequence_off":
        repair_steps = [
            {"frame": build_short_frame(address, 0xA1, 0x00, ch), "channel": ch, "expected_on": False, "label": f"第{ch}路关闭"}
            for ch in range(channel_count, 0, -1)
        ]
        steps = [{
            "frame": build_short_frame(address, 0xA5, 0x00, 0x00),
            "expected_channels": [False] * channel_count,
            "label": "顺序关闭",
            "post_delay": max(step_delay * channel_count + 0.35, 1.2),
            "max_attempts": 1,
            "repair_steps": repair_steps,
        }]
        action_text = "顺序关闭"
    elif action == "all_on":
        # DS-608 all-channel immediate command uses broadcast address 00.
        frame = build_short_frame(0x00, 0xAC, 0x00, 0x00)
        action_text = "全部开启"
        steps = [{"frame": frame, "expected_channels": [True] * channel_count, "label": action_text}]
    elif action == "all_off":
        # DS-608 all-channel immediate command uses broadcast address 00.
        frame = build_short_frame(0x00, 0xAD, 0x00, 0x00)
        action_text = "全部关闭"
        steps = [{"frame": frame, "expected_channels": [False] * channel_count, "label": action_text}]
    elif action == "toggle_lock":
        lock_on = not bool(state.get("locked", False))
        frame = bytes.fromhex(f"55 {address:02X} AE {'AA 00 05' if lock_on else '55 00 FA'}")
        action_text = "锁定设备" if lock_on else "解除锁定"
        steps = [{"frame": frame, "label": action_text}]
    else:
        raise ValueError("不支持的操作")

    ok_all = True
    failed_steps = []
    commands = []
    responses = []
    with get_device_io_lock(seq):
        if action == "sequence_on" and not any(current_channels):
            time.sleep(max(0.75, step_delay))
        def execute_step(step, idx=0, total=1):
            step_ok = False
            frame = step["frame"]
            last_response = b""
            step_attempts = int(step.get("max_attempts", confirm_attempts) or confirm_attempts)
            for attempt in range(step_attempts):
                ok, response = send_frame(seq, frame, expect_reply=True, timeout=0.95)
                last_response = response
                commands.append(frame)
                responses.append(response)
                set_control_state_fields(state, frame, response, action_text)
                time.sleep(float(step.get("post_delay", settle_delay) or settle_delay))

                if "expected_channels" in step:
                    confirmed, _ = poll_until_confirmed(
                        seq,
                        expected_channels=step["expected_channels"],
                        attempts=2,
                        retry_delay=retry_delay,
                    )
                elif "channel" in step:
                    confirmed, _ = poll_until_confirmed(
                        seq,
                        channel=step["channel"],
                        expected_on=step["expected_on"],
                        attempts=2,
                        retry_delay=retry_delay,
                    )
                else:
                    confirmed = bool(ok and (is_ack_response(response) or response))

                if confirmed:
                    step_ok = True
                    break
                if attempt < step_attempts - 1:
                    time.sleep(retry_delay * (attempt + 1))

            if not step_ok and step.get("repair_steps"):
                repair_ok = True
                for repair_idx, repair_step in enumerate(step.get("repair_steps") or []):
                    if not execute_step(repair_step, repair_idx, len(step.get("repair_steps") or [])):
                        repair_ok = False
                if repair_ok:
                    if "expected_channels" in step:
                        step_ok, _ = poll_until_confirmed(
                            seq,
                            expected_channels=step["expected_channels"],
                            attempts=3,
                            retry_delay=retry_delay,
                        )
                    else:
                        step_ok = True

            if not step_ok:
                failed_steps.append(step.get("label") or frame_to_hex(frame))
            set_control_state_fields(state, frame, last_response, action_text)
            if idx < total - 1:
                time.sleep(step_delay)
            return step_ok

        for idx, step in enumerate(steps):
            step_ok = execute_step(step, idx, len(steps))
            ok_all = ok_all and step_ok
        state["last_action"] = action_text
        state["updated_at"] = datetime.now().isoformat()
        if settle_delay > 0:
            time.sleep(settle_delay)
        poll_sequencer_once(seq, retries=3, retry_delay=0.14)
        state["last_action"] = action_text if ok_all else f"{action_text}未完全确认"
        state["error"] = "" if ok_all else f"未确认: {'、'.join(failed_steps)}"
    log_message = build_log_message(seq, action_text)
    add_log(-1, log_message)
    try:
        seq_id = str(seq.get("id") or seq.get("ip") or seq.get("name") or "")
        record_event(
            category="sequencer",
            event_type="command",
            source="api",
            device_id=seq_id,
            device_name=str(seq.get("name") or seq_id or "时序电源"),
            action=str(action or action_text or ""),
            channel=str(channel or ""),
            message=log_message,
            result="success" if ok_all else "failed",
            confidence="confirmed" if ok_all else "unknown",
            raw={"commands": [frame_to_hex(item) for item in commands], "responses": [frame_to_hex(item) for item in responses]},
        )
    except Exception:
        _log.debug("non-critical error suppressed", exc_info=True)
        pass
    command_text = " ; ".join(frame_to_hex(item) for item in commands)
    response_text = " ; ".join(frame_to_hex(item) for item in responses)
    return {
        "success": ok_all,
        "command": command_text,
        "response": response_text,
        "message": "执行完成并已确认状态" if ok_all else f"部分动作未确认: {'、'.join(failed_steps)}",
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
        status_code = 200 if result.get("success") else 409
        return jsonify({
            "success": bool(result.get("success")),
            "message": result.get("message", ""),
            "command": result["command"],
            "response": result["response"],
            "device": snapshot(seq),
        }), status_code
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
                "success": bool(result.get("success")),
                "message": f"已执行第{channel}路{'开启' if test_type == 'channel_on' else '关闭'}测试",
                "command": result["command"],
                "response": result["response"],
                "device": device,
                "channel_summary": summarize_channels([item.get("state") for item in (device.get("channels") or [])]),
            }), 200 if result.get("success") else 409

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
