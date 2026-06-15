# AI_MODULE: light_driver_rf_tcp
# AI_PURPOSE: RF TCP 灯光驱动 — 通过 TCP 转 RF 控制无线灯光模块。
# AI_BOUNDARY: 仅 RF TCP 转接设备；不直接操作 RF。
# AI_DATA_FLOW: CONFIG -> TCP relay -> RF transmitter -> 灯光接收器。
# AI_SEARCH_KEYWORDS: RF, TCP, wireless, light, driver.
import json
import socket
import threading
import time

from .base import BaseDriver


class RfTcpLightDriver(BaseDriver):
    def __init__(self, config):
        super().__init__(config)
        self.dev_lock = threading.Lock()
        self.last_status_payload = {}
        self.last_command_ack = {}
        self.last_status_ts = 0.0

    def connect(self):
        # TCP 文本协议按次连接，不维持长连接。
        self.is_online = True
        return True

    def disconnect(self):
        self.is_online = False

    def _timeout(self):
        try:
            return max(float(self.config.get("timeout_sec", 2.0) or 2.0), 0.3)
        except Exception:
            return 2.0

    def _post_command_delay(self):
        try:
            return max(float(self.config.get("post_command_delay_ms", 500) or 500) / 1000.0, 0.0)
        except Exception:
            return 0.5

    def _status_cache_ttl(self):
        try:
            return max(float(self.config.get("status_cache_ttl_ms", 250) or 250) / 1000.0, 0.0)
        except Exception:
            return 0.25

    def _make_socket(self):
        sock = socket.create_connection(
            (str(self.config.get("ip") or "").strip(), int(self.config.get("port") or 1881)),
            timeout=self._timeout(),
        )
        sock.settimeout(self._timeout())
        return sock

    def _send_line(self, command):
        text = str(command or "").strip()
        if not text:
            raise ValueError("empty command")

        with self._make_socket() as sock:
            sock.sendall((text + "\n").encode("utf-8"))
            chunks = []
            while True:
                part = sock.recv(4096)
                if not part:
                    break
                chunks.append(part)
                if b"\n" in part:
                    break

        raw = b"".join(chunks).decode("utf-8", errors="replace").strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            return {"success": False, "raw": raw, "error": "invalid_json"}

    def _normalize_status(self, payload):
        payload = payload or {}
        state = str(
            payload.get("display_state")
            or payload.get("inferred_state")
            or payload.get("state")
            or payload.get("status")
            or payload.get("ui_state")
            or ""
        ).strip().lower()
        on_states = {"on", "on_likely", "open", "opened", "true", "1", "enabled"}
        off_states = {"off", "off_likely", "close", "closed", "false", "0", "disabled"}
        if state in on_states:
            channels = [True]
        elif state in off_states:
            channels = [False]
        else:
            channels = [None]
        return {
            "online": bool(payload.get("success", True)),
            "channels": channels,
            "status_text": state or "unknown",
            "raw_status": payload,
        }

    def read_status(self, force=False):
        with self.dev_lock:
            now = time.monotonic()
            if (
                not force
                and self.last_status_payload
                and (now - self.last_status_ts) <= self._status_cache_ttl()
            ):
                normalized = self._normalize_status(self.last_status_payload)
                self.is_online = normalized["online"]
                return normalized

            try:
                payload = self._send_line(self.config.get("status_command", "status"))
                normalized = self._normalize_status(payload)
                self.last_status_payload = payload
                self.last_status_ts = now
                self.is_online = normalized["online"]
                return normalized
            except Exception:
                self.is_online = False
                return {"online": False, "channels": [None], "status_text": "offline", "raw_status": {}}

    def execute_action(self, action_name):
        action = str(action_name or "").strip().lower()
        command_map = {
            "on": str(self.config.get("command_on") or "on"),
            "off": str(self.config.get("command_off") or "off"),
            "off3": str(self.config.get("command_off3") or "off3"),
            "status": str(self.config.get("status_command") or "status"),
            "ping": str(self.config.get("ping_command") or "ping"),
        }
        command = command_map.get(action)
        if not command:
            return {"success": False, "msg": f"unsupported action: {action}"}

        with self.dev_lock:
            try:
                ack = self._send_line(command)
                self.last_command_ack = ack
                success = bool(ack.get("success", False))
                queued = bool(ack.get("queued", False))
                if action in {"on", "off", "off3"}:
                    delay = self._post_command_delay()
                    if delay > 0:
                        time.sleep(delay)
                    status = self.read_status(force=True)
                    result = {
                        "success": success,
                        "queued": queued,
                        "ack": ack,
                        "channels": list(status.get("channels", []) or []),
                        "verified": action != "off3",
                        "status_text": status.get("status_text", "unknown"),
                        "raw_status": status.get("raw_status", {}),
                    }
                    if action in {"on", "off"}:
                        expected = action == "on"
                        current = result["channels"][0] if result["channels"] else None
                        result["verified"] = current is expected
                    return result
                if action == "status":
                    status = self.read_status(force=True)
                    return {
                        "success": bool(status.get("online", False)),
                        "channels": list(status.get("channels", []) or []),
                        "verified": True,
                        "status_text": status.get("status_text", "unknown"),
                        "raw_status": status.get("raw_status", {}),
                    }
                return {"success": success, "queued": queued, "ack": ack}
            except Exception as exc:
                self.is_online = False
                return {"success": False, "msg": str(exc)}

    def control_channel(self, channel, is_open):
        # RF 控制器当前按整机开关工作，通道号保留给统一灯控接口。
        result = self.execute_action("on" if is_open else "off")
        return bool(result.get("success", False))
