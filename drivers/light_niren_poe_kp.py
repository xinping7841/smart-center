# AI_MODULE: light_driver_niren_poe
# AI_PURPOSE: 日能 POE 键盘面板灯光驱动 — POE 供电的键控灯光面板。
# AI_BOUNDARY: 仅日能 POE 面板；不处理其他灯光协议。
# AI_DATA_FLOW: CONFIG.light_groups -> UDP/TCP -> POE 面板 -> 继电器。
# AI_SEARCH_KEYWORDS: niren, POE, keypad, light, relay.
import socket
import threading
import time

from .base import BaseDriver
from log_config import get_logger

_log = get_logger(__name__)



def _crc16_modbus(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc.to_bytes(2, "little")


def _check_crc(frame):
    return len(frame) >= 4 and _crc16_modbus(frame[:-2]) == frame[-2:]


class NirenPoeKpRelayDriver(BaseDriver):
    """Niren POE-KP-I101 network relay.

    The vendor's "Modbus TCP/RTU" TCPServer mode accepts Modbus-RTU frames over
    TCP. Some firmware builds do not acknowledge writes consistently, so writes
    are verified by a read-back when an ACK is missing.
    """

    def __init__(self, config):
        super().__init__(config)
        self.dev_lock = threading.RLock()
        self.sock = None
        self.last_error = ""
        self.last_protocol = ""

    def connect(self):
        self.is_online = True
        return True

    def disconnect(self):
        self._close_socket()
        self.is_online = False

    def _timeout(self):
        try:
            return max(float(self.config.get("timeout_sec", 1.2) or 1.2), 0.3)
        except Exception:
            return 1.2

    def _post_command_delay(self):
        try:
            return max(float(self.config.get("post_command_delay_ms", 350) or 350) / 1000.0, 0.0)
        except Exception:
            return 0.35

    def _protocol(self):
        return str(self.config.get("relay_protocol") or self.config.get("protocol_variant") or "rtu_over_tcp").strip().lower()

    def _slave_id(self):
        try:
            return int(self.config.get("slave_id", 1) or 1) & 0xFF
        except Exception:
            return 1

    def _channel_count(self):
        try:
            return max(1, min(int(self.config.get("channels", 1) or 1), 64))
        except Exception:
            return 1

    def _input_count(self):
        try:
            return max(0, min(int(self.config.get("input_count", 1) or 0), 64))
        except Exception:
            return 1

    def _host_port(self):
        return str(self.config.get("ip") or "").strip(), int(self.config.get("port") or 44489)

    def _close_socket(self):
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                _log.debug("non-critical error suppressed", exc_info=True)
                pass
            try:
                self.sock.close()
            except Exception:
                _log.debug("non-critical error suppressed", exc_info=True)
                pass
            self.sock = None

    def _open_socket(self, timeout):
        host, port = self._host_port()
        if self.sock is None:
            self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        return self.sock

    def _recv_response(self, sock, timeout):
        chunks = []
        end_at = time.monotonic() + timeout
        while time.monotonic() < end_at:
            try:
                part = sock.recv(260)
            except socket.timeout:
                break
            if not part:
                self._close_socket()
                break
            chunks.append(part)
            if self._looks_complete(b"".join(chunks)):
                break
        return b"".join(chunks)

    def _socket_exchange(self, payload, timeout=None):
        timeout = timeout or self._timeout()
        attempts = max(1, int(self.config.get("retry_count", 3) or 3))
        retry_delay = max(0.05, float(self.config.get("retry_delay_ms", 350) or 350) / 1000.0)
        last_exc = None
        for attempt in range(attempts):
            try:
                sock = self._open_socket(timeout)
                sock.sendall(payload)
                response = self._recv_response(sock, timeout)
                if response:
                    return response
                time.sleep(retry_delay)
            except Exception as exc:
                last_exc = exc
                self._close_socket()
                time.sleep(retry_delay)
        if last_exc:
            raise last_exc
        return b""

    def _rtu_frame(self, function_code, body):
        frame = bytes([self._slave_id(), int(function_code) & 0xFF]) + bytes(body)
        return frame + _crc16_modbus(frame)

    def _tcp_frame(self, function_code, body):
        tx_id = int(time.time() * 1000) & 0xFFFF
        pdu = bytes([self._slave_id(), int(function_code) & 0xFF]) + bytes(body)
        return tx_id.to_bytes(2, "big") + b"\x00\x00" + len(pdu).to_bytes(2, "big") + pdu

    def _looks_complete(self, data):
        if not data:
            return False
        if len(data) >= 6 and data[2:4] == b"\x00\x00":
            length = int.from_bytes(data[4:6], "big")
            return length > 0 and len(data) >= 6 + length
        return _check_crc(data)

    def _exchange_modbus(self, function_code, body, protocol=None, expect_response=True):
        protocol = (protocol or self._protocol()).lower()
        variants = ["rtu_over_tcp", "modbus_tcp"] if protocol == "auto" else [protocol]
        last_exc = None
        for variant in variants:
            try:
                payload = self._tcp_frame(function_code, body) if variant == "modbus_tcp" else self._rtu_frame(function_code, body)
                response = self._socket_exchange(payload)
                if not response and not expect_response:
                    self.last_protocol = variant
                    return b""
                if self._valid_response(response, function_code, variant):
                    self.last_protocol = variant
                    return response[6:] if variant == "modbus_tcp" else response[:-2]
            except Exception as exc:
                last_exc = exc
        if last_exc:
            raise last_exc
        raise TimeoutError("no valid relay response")

    def _valid_response(self, response, function_code, variant):
        if not response:
            return False
        if variant == "modbus_tcp":
            if len(response) < 8 or response[2:4] != b"\x00\x00":
                return False
            pdu = response[6:]
            return len(pdu) >= 2 and pdu[1] in (function_code, function_code | 0x80)
        return _check_crc(response) and len(response) >= 4 and response[1] in (function_code, function_code | 0x80)

    def _read_coils_modbus(self):
        count = self._channel_count()
        start = int(self.config.get("status_start_address", 0) or 0)
        return self._read_bool_bits_modbus(0x01, start, count, "relay")

    def _read_inputs_modbus(self):
        count = self._input_count()
        if count <= 0:
            return []
        start = int(self.config.get("input_start_address", 0) or 0)
        return self._normalize_inputs(self._read_bool_bits_modbus(0x02, start, count, "input"))

    def _read_bool_bits_modbus(self, function_code, start, count, label):
        body = int(start).to_bytes(2, "big") + int(count).to_bytes(2, "big")
        pdu = self._exchange_modbus(function_code, body)
        if len(pdu) < 4 or pdu[1] & 0x80:
            raise RuntimeError(f"{label} read exception: {pdu.hex(' ')}")
        byte_count = int(pdu[2])
        data = pdu[3:3 + byte_count]
        states = []
        for byte in data:
            for bit in range(8):
                states.append(bool(byte & (1 << bit)))
        return states[:count]

    def _send_at(self, command):
        text = str(command or "").strip()
        if not text:
            raise ValueError("empty AT command")
        response = self._socket_exchange((text + "\r\n").encode("ascii", errors="ignore"))
        return response.decode("utf-8", errors="replace").strip()

    def _at_value(self, raw, prefix):
        prefix = str(prefix or "").upper()
        lines = [
            line.strip()
            for line in str(raw or "").replace("\r", "\n").split("\n")
            if line.strip()
        ]
        for line in lines:
            if not line.upper().startswith(prefix):
                continue
            value = line.split(":", 1)[-1].split(",", 1)[0].strip()
            if value in {"0", "1"}:
                return value == "1"
            raise RuntimeError(raw or f"invalid {prefix} response")
        raise RuntimeError(raw or f"missing {prefix} response")

    def _read_coils_at(self):
        count = self._channel_count()
        channels = []
        for ch in range(1, count + 1):
            raw = self._send_at(f"AT+STACH{ch}=?")
            channels.append(self._at_value(raw, f"+STACH{ch}"))
        return channels

    def _read_inputs_at(self):
        count = self._input_count()
        inputs = []
        for ch in range(1, count + 1):
            raw = self._send_at(f"AT+OCCH{ch}=?")
            inputs.append(self._at_value(raw, f"+OCCH{ch}"))
        return self._normalize_inputs(inputs)

    def _input_active_level(self):
        value = str(self.config.get("input_active_level", "high") or "high").strip().lower()
        return "low" if value in {"low", "0", "false", "closed_low", "低", "低电平"} else "high"

    def _normalize_inputs(self, inputs):
        if self._input_active_level() != "low":
            return inputs
        return [None if item is None else not bool(item) for item in inputs]

    def read_status(self):
        with self.dev_lock:
            try:
                if self._protocol() == "at":
                    channels = self._read_coils_at()
                    inputs = self._read_inputs_at()
                else:
                    channels = self._read_coils_modbus()
                    inputs = self._read_inputs_modbus()
                self.is_online = True
                self.last_error = ""
                return {
                    "online": True,
                    "channels": channels,
                    "inputs": inputs,
                    "status_text": self.last_protocol or self._protocol(),
                    "raw_status": {"protocol": self.last_protocol or self._protocol(), "inputs": inputs},
                }
            except Exception as exc:
                self.is_online = False
                self.last_error = str(exc)
                return {
                    "online": False,
                    "channels": [None] * self._channel_count(),
                    "inputs": [None] * self._input_count(),
                    "status_text": "offline",
                    "error": str(exc),
                }

    def _write_modbus(self, channel, is_open):
        start = int(self.config.get("write_start_address", 0) or 0)
        addr = start + int(channel) - 1
        value = b"\xFF\x00" if is_open else b"\x00\x00"
        body = addr.to_bytes(2, "big") + value
        try:
            self._exchange_modbus(0x05, body)
            return True
        except Exception:
            delay = self._post_command_delay()
            if delay > 0:
                time.sleep(delay)
            status = self.read_status()
            channels = list(status.get("channels", []) or [])
            idx = int(channel) - 1
            return bool(status.get("online")) and 0 <= idx < len(channels) and channels[idx] is bool(is_open)

    def _write_at(self, channel, is_open):
        raw = self._send_at(f"AT+STACH{int(channel)}={1 if is_open else 0}")
        if "OK" in raw.upper():
            return True
        raise RuntimeError(raw or "empty AT response")

    def pulse_channel(self, channel, seconds=1):
        with self.dev_lock:
            try:
                seconds = max(1, int(float(seconds or 1)))
                if self._protocol() != "at":
                    raise RuntimeError("pulse is only implemented for AT protocol")
                raw = self._send_at(f"AT+STACH{int(channel)}=3,{seconds}")
                ok = "OK" in raw.upper()
                self.is_online = bool(ok)
                return bool(ok)
            except Exception as exc:
                self.is_online = False
                self.last_error = str(exc)
                return False

    def execute_action(self, action_name):
        action = str(action_name or "").strip().lower()
        if action in {"pulse", "pulse1", "jog", "momentary"}:
            channel = int(self.config.get("pulse_channel", 1) or 1)
            seconds = self.config.get("pulse_seconds", 1)
        elif action.startswith("pulse_ch"):
            channel = int(action.replace("pulse_ch", "", 1) or 1)
            seconds = self.config.get("pulse_seconds", 1)
        else:
            return {"success": False, "msg": f"unsupported action: {action_name}"}
        ok = self.pulse_channel(channel, seconds)
        return {"success": ok, "verified": False, "status_text": self.last_protocol or self._protocol()}

    def control_channel(self, channel, is_open):
        with self.dev_lock:
            try:
                if self._protocol() == "at":
                    ok = self._write_at(channel, is_open)
                else:
                    ok = self._write_modbus(channel, is_open)
                self.is_online = bool(ok)
                return bool(ok)
            except Exception as exc:
                self.is_online = False
                self.last_error = str(exc)
                return False
