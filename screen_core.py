"""
幕布升降控制核心模块。

统一读取 config.json 中的 screens 配置，避免页面保存与实际控制使用的配置源不一致。
"""

import socket
import time
from datetime import datetime

import serial

from config import CONFIG, save_config


def load_screens_config():
    return {"screens": CONFIG.get("screens", [])}


def save_screens_config(config):
    CONFIG["screens"] = config.get("screens", [])
    save_config(CONFIG)


class ScreenDriver:
    def __init__(self, cfg):
        self.cfg = cfg
        self.id = cfg.get("id", "screen")
        self.name = cfg.get("name", "幕布")
        self.control_type = cfg.get("control_type", "screen_tcp")

        screen_cfg = cfg.get("screen_config", {})
        self.total_height = float(screen_cfg.get("total_height", 3.0))
        self.total_time = float(screen_cfg.get("total_time", 30))

        self.current_position = float(cfg.get("current_position", 0))
        self.current_height = float(cfg.get("current_height", 0))
        self.last_action = cfg.get("last_action", "stop")
        self.last_action_time = cfg.get("last_action_time")
        self.is_moving = bool(cfg.get("is_moving", False))
        self.moving_direction = cfg.get("moving_direction")
        self.move_start_position = float(cfg.get("move_start_position", self.current_position))

        move_start_time = cfg.get("move_start_time")
        self.move_start_time = None
        if move_start_time:
            try:
                self.move_start_time = datetime.fromisoformat(move_start_time)
            except Exception:
                self.move_start_time = None

        self.speed = self.total_height / self.total_time if self.total_time > 0 else 0

    def execute(self, cmd_config):
        action = cmd_config.get("action")
        payload = (cmd_config.get("payload") or "").strip()
        fmt = cmd_config.get("format", "hex")

        if not payload:
            return False, "未配置幕布控制指令"

        success, res = self._send_command(payload, fmt)
        if not success:
            return False, res

        if action == "up":
            self._start_moving("up")
        elif action == "down":
            self._start_moving("down")
        elif action == "stop":
            self._stop_moving()
        else:
            self.last_action = action or "unknown"
            self.last_action_time = datetime.now().isoformat()
            self._save_config()

        return True, f"幕布控制完成: {action}"

    def _send_command(self, payload, fmt):
        try:
            if self.control_type == "screen_tcp":
                return self._send_tcp(payload, fmt)
            if self.control_type == "screen_udp":
                return self._send_udp(payload, fmt)
            if self.control_type == "screen_com":
                return self._send_com(payload, fmt)
            return False, f"不支持的幕布控制协议: {self.control_type}"
        except Exception as e:
            return False, str(e)

    def _encode_payload(self, payload, fmt):
        if fmt == "hex":
            return bytes.fromhex(payload.replace(" ", ""))
        return payload.encode("utf-8")

    def _send_tcp(self, payload, fmt):
        ip = self.cfg.get("ip", "")
        port = int(self.cfg.get("port", 1234))
        payload_bytes = self._encode_payload(payload, fmt)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(3.0)
            sock.connect((ip, port))
            sock.sendall(payload_bytes)
            time.sleep(0.15)
            try:
                res = sock.recv(1024)
                if res:
                    return True, f"已发送，响应: {res.hex(' ').upper()}"
            except socket.timeout:
                pass
        return True, "已发送"

    def _send_udp(self, payload, fmt):
        ip = self.cfg.get("ip", "")
        port = int(self.cfg.get("port", 1234))
        payload_bytes = self._encode_payload(payload, fmt)

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(1.0)
            sock.sendto(payload_bytes, (ip, port))
        return True, "已发送"

    def _send_com(self, payload, fmt):
        com_port = self.cfg.get("com_port", "COM1")
        baudrate = int(self.cfg.get("baudrate", 9600))
        payload_bytes = self._encode_payload(payload, fmt)

        with serial.Serial(com_port, baudrate, timeout=1) as ser:
            ser.write(payload_bytes)
        return True, "已发送"

    def _start_moving(self, direction):
        self._refresh_runtime_position()
        self.is_moving = True
        self.moving_direction = direction
        self.move_start_time = datetime.now()
        self.move_start_position = self.current_position
        self.last_action = direction
        self.last_action_time = self.move_start_time.isoformat()
        self._save_config()

    def _stop_moving(self):
        self._refresh_runtime_position()
        self.is_moving = False
        self.moving_direction = None
        self.move_start_time = None
        self.move_start_position = self.current_position
        self.last_action = "stop"
        self.last_action_time = datetime.now().isoformat()
        self._save_config()

    def _refresh_runtime_position(self):
        if not self.is_moving or not self.move_start_time:
            return

        elapsed = max((datetime.now() - self.move_start_time).total_seconds(), 0)
        position_change = (elapsed / self.total_time) * 100 if self.total_time > 0 else 0
        if self.moving_direction == "down":
            self.current_position = min(100, self.move_start_position + position_change)
        elif self.moving_direction == "up":
            self.current_position = max(0, self.move_start_position - position_change)
        self.current_height = (self.current_position / 100) * self.total_height

        if self.current_position in [0, 100]:
            self.is_moving = False
            self.moving_direction = None
            self.move_start_time = None
            self.move_start_position = self.current_position
            self.last_action = "stop"
            self.last_action_time = datetime.now().isoformat()

    def get_status(self):
        self._refresh_runtime_position()
        if self.is_moving and self.move_start_time:
            elapsed = max((datetime.now() - self.move_start_time).total_seconds(), 0)
            remaining_position = (100 - self.current_position) if self.moving_direction == "down" else self.current_position
            remaining_time = (remaining_position / 100.0) * self.total_time if self.total_time > 0 else 0
            return {
                "position": round(self.current_position, 1),
                "height": round(self.current_height, 2),
                "action": self.moving_direction,
                "is_moving": True,
                "remaining_time": round(max(remaining_time, 0), 1),
                "total_height": self.total_height
            }

        return {
            "position": round(self.current_position, 1),
            "height": round(self.current_height, 2),
            "action": "stop",
            "is_moving": False,
            "remaining_time": 0,
            "total_height": self.total_height
        }

    def calibrate(self, position):
        position = float(position)
        self.current_position = max(0, min(100, position))
        self.current_height = (self.current_position / 100) * self.total_height
        self.is_moving = False
        self.moving_direction = None
        self.move_start_time = None
        self.move_start_position = self.current_position
        self.last_action = "stop"
        self.last_action_time = datetime.now().isoformat()
        self._save_config()
        return True, f"标定完成: {position}%"

    def set_position(self, position):
        self._refresh_runtime_position()
        position = max(0.0, min(100.0, float(position)))
        target_height = (position / 100) * self.total_height
        current_height = self.current_height
        height_diff = abs(target_height - current_height)
        move_time = height_diff / self.speed if self.speed > 0 else 0
        return {
            "target_position": position,
            "target_height": target_height,
            "move_time": move_time,
            "direction": "down" if target_height > current_height else "up"
        }

    def _save_config(self):
        screens = CONFIG.get("screens", [])
        found = False
        for index, screen in enumerate(screens):
            if str(screen.get("id")) == str(self.id):
                updated = screen.copy()
                updated["current_position"] = self.current_position
                updated["current_height"] = self.current_height
                updated["last_action"] = self.last_action
                updated["last_action_time"] = self.last_action_time
                updated["is_moving"] = self.is_moving
                updated["moving_direction"] = self.moving_direction
                updated["move_start_position"] = self.move_start_position
                updated["move_start_time"] = self.move_start_time.isoformat() if self.move_start_time else None
                screens[index] = updated
                found = True
                break

        if not found:
            screens.append({
                "id": self.id,
                "name": self.name,
                "control_type": self.control_type,
                "ip": self.cfg.get("ip", ""),
                "port": self.cfg.get("port", 1234),
                "com_port": self.cfg.get("com_port", "COM1"),
                "baudrate": self.cfg.get("baudrate", 9600),
                "current_position": self.current_position,
                "current_height": self.current_height,
                "last_action": self.last_action,
                "last_action_time": self.last_action_time,
                "is_moving": self.is_moving,
                "moving_direction": self.moving_direction,
                "move_start_position": self.move_start_position,
                "move_start_time": self.move_start_time.isoformat() if self.move_start_time else None,
                "screen_config": self.cfg.get("screen_config", {}),
                "commands": self.cfg.get("commands", [])
            })

        CONFIG["screens"] = screens
        save_config(CONFIG)


def get_all_screens():
    return CONFIG.get("screens", [])


def get_screen_by_id(screen_id):
    for screen in CONFIG.get("screens", []):
        if str(screen.get("id")) == str(screen_id):
            return screen
    return None
