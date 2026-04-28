import socket
import struct
import threading
import time
from copy import deepcopy
from datetime import datetime

from config import CONFIG


def _pad_osc_string(value):
    raw = str(value).encode("utf-8") + b"\x00"
    while len(raw) % 4:
        raw += b"\x00"
    return raw


def _build_osc_message(address, args=None):
    args = args or []
    payload = bytearray()
    payload.extend(_pad_osc_string(address))
    tags = ","
    encoded_args = bytearray()

    for arg in args:
        if isinstance(arg, bool):
            tags += "i"
            encoded_args.extend(struct.pack(">i", 1 if arg else 0))
        elif isinstance(arg, int):
            tags += "i"
            encoded_args.extend(struct.pack(">i", arg))
        elif isinstance(arg, float):
            tags += "f"
            encoded_args.extend(struct.pack(">f", arg))
        else:
            tags += "s"
            encoded_args.extend(_pad_osc_string(arg))

    payload.extend(_pad_osc_string(tags))
    payload.extend(encoded_args)
    return bytes(payload)


def _read_osc_string(data, offset):
    end = data.find(b"\x00", offset)
    if end == -1:
        end = len(data)
    value = data[offset:end].decode("utf-8", errors="ignore")
    next_offset = end + 1
    while next_offset % 4:
        next_offset += 1
    return value, next_offset


def _parse_osc_message(data):
    if not data:
        return "", []

    address, offset = _read_osc_string(data, 0)
    tags, offset = _read_osc_string(data, offset)
    args = []
    if not tags.startswith(","):
        return address, args

    for tag in tags[1:]:
        if tag == "i":
            if offset + 4 > len(data):
                break
            args.append(struct.unpack(">i", data[offset:offset + 4])[0])
            offset += 4
        elif tag == "f":
            if offset + 4 > len(data):
                break
            args.append(struct.unpack(">f", data[offset:offset + 4])[0])
            offset += 4
        elif tag == "s":
            value, offset = _read_osc_string(data, offset)
            args.append(value)
        elif tag == "b":
            if offset + 4 > len(data):
                break
            blob_len = struct.unpack(">i", data[offset:offset + 4])[0]
            offset += 4
            args.append(data[offset:offset + blob_len])
            offset += blob_len
            while offset % 4:
                offset += 1
        else:
            break

    return address, args


def _clamp(value, low, high):
    return max(low, min(high, value))


def _safe_int(value, default):
    try:
        return int(value)
    except Exception:
        return int(default)


class M32RService:
    def __init__(self):
        self.lock = threading.Lock()
        self.sock = None
        self.remote_addr = None
        self.running = False
        self.listener_thread = None
        self.last_keepalive = 0.0
        self.last_name_poll = 0.0
        self.last_rx = 0.0
        self.state = self._default_state()

    def _default_state(self):
        return {
            "connected": False,
            "online": False,
            "mode": "offline",
            "host": str(CONFIG.get("m32r", {}).get("host", "") or ""),
            "port": int(CONFIG.get("m32r", {}).get("port", 10023) or 10023),
            "name": str(CONFIG.get("m32r", {}).get("name", "Midas M32R") or "Midas M32R"),
            "model": "",
            "firmware": "",
            "show_position": None,
            "last_error": "",
            "updated_at": "",
            "last_rx_at": "",
            "auto_connect": bool(CONFIG.get("m32r", {}).get("auto_connect", False)),
            "auto_sync": bool(CONFIG.get("m32r", {}).get("auto_sync", False)),
            "sync_direction": str(CONFIG.get("m32r", {}).get("sync_direction", "mixer_to_pc") or "mixer_to_pc"),
            "known_mixers": [],
            "discovered_mixers": [],
            "local_ips": [],
            "channel_cache": {},
            "channels": [],
            "main": {"fader": 0.0, "on": True, "level_db": -90.0, "meter_db": -90.0},
        }

    @staticmethod
    def feedback_sources():
        return {
            "channel_name": "live",
            "channel_on": "live",
            "channel_fader": "live",
            "channel_pan": "live",
            "main_on": "live",
            "main_fader": "live",
            "channel_meter": "estimated",
            "main_meter": "estimated",
            "channel_scribble": "local",
            "channel_gate": "local",
            "channel_eq": "local",
            "channel_dyn": "local",
            "channel_sends": "local",
        }

    def _channel_snapshot(self, channel_no):
        return {
            "channel": channel_no,
            "name": f"CH {channel_no:02d}",
            "on": True,
            "fader": 0.0,
            "level_db": -90.0,
            "pan": 0.0,
            "meter_db": -90.0,
            "scribble": "",
            "gate": {
                "enabled": False,
                "threshold_db": -42.0,
                "range_db": -18.0,
                "attack_ms": 10,
                "hold_ms": 120,
                "release_ms": 250,
            },
            "eq": {
                "enabled": True,
                "hpf_hz": 100,
                "low_gain_db": -2.0,
                "mid_freq_hz": 3200,
                "mid_gain_db": 2.0,
                "high_gain_db": 1.5,
            },
            "dyn": {
                "enabled": True,
                "threshold_db": -18.0,
                "ratio": 3.0,
                "attack_ms": 20,
                "release_ms": 120,
            },
            "sends": {
                "bus_1": 0.55,
                "bus_2": 0.45,
                "bus_3": 0.40,
                "bus_4": 0.35,
            },
        }

    def _config(self):
        return CONFIG.get("m32r", {}) or {}

    @staticmethod
    def local_ip_addresses():
        results = ["127.0.0.1"]
        seen = set(results)
        try:
            hostname = socket.gethostname()
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_DGRAM):
                ip = str(info[4][0] or "").strip()
                if ip and ip not in seen:
                    results.append(ip)
                    seen.add(ip)
        except Exception:
            pass
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            sock.close()
            if ip and ip not in seen:
                results.insert(0, ip)
                seen.add(ip)
        except Exception:
            pass
        return results

    def _known_mixers_from_config(self):
        cfg = self._config()
        items = cfg.get("known_mixers", [])
        if not isinstance(items, list):
            items = []
        normalized = []
        seen = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            host = str(item.get("host", "") or "").strip()
            if not host or host in seen:
                continue
            seen.add(host)
            normalized.append(
                {
                    "host": host,
                    "name": str(item.get("name", "") or "").strip(),
                    "model": str(item.get("model", "") or "").strip(),
                    "firmware": str(item.get("firmware", "") or "").strip(),
                    "last_seen_at": str(item.get("last_seen_at", "") or "").strip(),
                }
            )
        return normalized

    def _update_known_mixer(self):
        cfg = self._config()
        items = self._known_mixers_from_config()
        current = {
            "host": str(self.state.get("host", "") or "").strip(),
            "name": str(self.state.get("name", "") or "").strip(),
            "model": str(self.state.get("model", "") or "").strip(),
            "firmware": str(self.state.get("firmware", "") or "").strip(),
            "last_seen_at": str(self.state.get("last_rx_at", "") or datetime.now().isoformat()),
        }
        if not current["host"]:
            return
        replaced = False
        for idx, item in enumerate(items):
            if item["host"] == current["host"]:
                merged = item.copy()
                merged.update({k: v for k, v in current.items() if v})
                items[idx] = merged
                replaced = True
                break
        if not replaced:
            items.append(current)
        cfg["known_mixers"] = items
        CONFIG["m32r"] = cfg

    def _channel_count(self):
        cfg = self._config()
        return max(1, min(_safe_int(cfg.get("channel_count", 8) or 8, 8), 32))

    def _bank_start(self):
        cfg = self._config()
        count = self._channel_count()
        max_start = max(1, 33 - count)
        return max(1, min(_safe_int(cfg.get("bank_start", 1) or 1, 1), max_start))

    def _visible_channel_numbers(self):
        bank_start = self._bank_start()
        count = self._channel_count()
        upper = min(32, bank_start + count - 1)
        return list(range(bank_start, upper + 1))

    def _ensure_channels(self):
        expected = self._visible_channel_numbers()
        self.state["channels"] = [self._merge_channel(channel_no) for channel_no in expected]

    def _merge_channel(self, channel_no):
        channel_no = int(channel_no)
        cached = self.state.get("channel_cache", {}).get(channel_no)
        if isinstance(cached, dict):
            return cached
        for item in self.state.get("channels", []):
            if int(item.get("channel", 0)) == channel_no:
                self.state.setdefault("channel_cache", {})[channel_no] = item
                return item
        snap = self._channel_snapshot(channel_no)
        self.state.setdefault("channel_cache", {})[channel_no] = snap
        return snap

    def _replace_channel(self, channel):
        channel_no = int(channel.get("channel", 0) or 0)
        if channel_no > 0:
            self.state.setdefault("channel_cache", {})[channel_no] = channel
        channels = self.state.get("channels", [])
        for idx, item in enumerate(channels):
            if int(item.get("channel", 0)) == channel_no:
                channels[idx] = channel
                return
        channels.append(channel)

    def _reset_levels_locked(self):
        for channel in self.state.get("channel_cache", {}).values():
            if not isinstance(channel, dict):
                continue
            channel["fader"] = 0.0
            channel["level_db"] = -90.0
            channel["meter_db"] = -90.0
            channel["on"] = False
        for channel in self.state.get("channels", []):
            if not isinstance(channel, dict):
                continue
            channel["fader"] = 0.0
            channel["level_db"] = -90.0
            channel["meter_db"] = -90.0
            channel["on"] = False
            channel_no = int(channel.get("channel", 0) or 0)
            if channel_no > 0:
                self.state.setdefault("channel_cache", {})[channel_no] = channel
        main = self.state.setdefault("main", {})
        main["fader"] = 0.0
        main["level_db"] = -90.0
        main["meter_db"] = -90.0
        main["on"] = False

    def configure(self, cfg=None):
        cfg = cfg or self._config()
        with self.lock:
            self.state["host"] = str(cfg.get("host", "") or "")
            self.state["port"] = _safe_int(cfg.get("port", 10023) or 10023, 10023)
            self.state["name"] = str(cfg.get("name", "Midas M32R") or "Midas M32R")
            self.state["auto_connect"] = bool(cfg.get("auto_connect", False))
            self.state["auto_sync"] = bool(cfg.get("auto_sync", False))
            self.state["sync_direction"] = str(cfg.get("sync_direction", "mixer_to_pc") or "mixer_to_pc")
            self.state["known_mixers"] = self._known_mixers_from_config()
            self.state["local_ips"] = self.local_ip_addresses()
            if not isinstance(self.state.get("channel_cache"), dict):
                self.state["channel_cache"] = {}
            self._ensure_channels()

    def connect(self, demo_mode=False):
        self.configure()
        if demo_mode:
            with self.lock:
                self.close_socket()
                self.running = False
                self.state["connected"] = True
                self.state["online"] = True
                self.state["mode"] = "demo"
                self.state["last_error"] = ""
                self.state["updated_at"] = datetime.now().isoformat()
                self.state["last_rx_at"] = "demo"
            return self.snapshot()

        with self.lock:
            self.close_socket()
            host = self.state["host"]
            port = int(self.state["port"])
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.settimeout(0.2)
            self.remote_addr = (host, port)
            self.running = True
            self.state["connected"] = True
            self.state["online"] = False
            self.state["mode"] = "live"
            self.state["last_error"] = ""
            self.state["updated_at"] = datetime.now().isoformat()
            self._reset_levels_locked()
            if not self.listener_thread or not self.listener_thread.is_alive():
                self.listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
                self.listener_thread.start()

        self._safe_send("/xinfo")
        self._safe_send("/status")
        self._safe_send("/xremote")
        self.refresh_channels()
        return self.snapshot()

    def disconnect(self):
        with self.lock:
            self.running = False
            self.state["connected"] = False
            self.state["online"] = False
            self.state["mode"] = "offline"
            self.state["updated_at"] = datetime.now().isoformat()
            self.close_socket()
            self._reset_levels_locked()
        return self.snapshot()

    def close_socket(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None
        self.remote_addr = None

    def _listen_loop(self):
        while self.running:
            sock = self.sock
            if not sock:
                time.sleep(0.1)
                continue
            try:
                data, _ = sock.recvfrom(8192)
                self._handle_packet(data)
            except socket.timeout:
                continue
            except OSError:
                time.sleep(0.1)
            except Exception as exc:
                with self.lock:
                    self.state["last_error"] = str(exc)
                    self.state["updated_at"] = datetime.now().isoformat()
                time.sleep(0.2)

    def _handle_packet(self, data):
        address, args = _parse_osc_message(data)
        now_text = datetime.now().isoformat()
        with self.lock:
            self.last_rx = time.monotonic()
            self.state["online"] = True
            self.state["updated_at"] = now_text
            self.state["last_rx_at"] = now_text
            if address == "/xinfo":
                if len(args) >= 2:
                    self.state["model"] = str(args[1])
                if len(args) >= 3:
                    self.state["firmware"] = str(args[2])
            elif address == "/-show/prepos/current":
                self.state["show_position"] = args[0] if args else None
            elif address == "/main/st/mix/fader" and args:
                value = float(args[0])
                self.state["main"]["fader"] = value
                self.state["main"]["level_db"] = self.normalized_to_db(value)
            elif address == "/main/st/mix/on" and args:
                self.state["main"]["on"] = bool(int(args[0]))
            elif address.startswith("/ch/"):
                self._apply_channel_update(address, args)
            self._update_known_mixer()

    def _apply_channel_update(self, address, args):
        parts = address.strip("/").split("/")
        if len(parts) < 4 or parts[0] != "ch":
            return
        try:
            channel_no = int(parts[1])
        except Exception:
            return

        channel = self._merge_channel(channel_no)
        tail = "/".join(parts[2:])
        if tail == "mix/fader" and args:
            value = float(args[0])
            channel["fader"] = value
            channel["level_db"] = self.normalized_to_db(value)
        elif tail == "mix/on" and args:
            channel["on"] = bool(int(args[0]))
        elif tail == "mix/pan" and args:
            channel["pan"] = float(args[0])
        elif tail == "config/name" and args:
            channel["name"] = str(args[0]) or channel["name"]
        self._replace_channel(channel)

    def _send(self, address, args=None):
        if self.state.get("mode") == "demo":
            return
        with self.lock:
            sock = self.sock
            remote_addr = self.remote_addr
        if not sock or not remote_addr:
            raise RuntimeError("M32R not connected")
        payload = _build_osc_message(address, args)
        sock.sendto(payload, remote_addr)

    def _safe_send(self, address, args=None):
        try:
            self._send(address, args)
        except Exception as exc:
            with self.lock:
                self.state["last_error"] = str(exc)
                self.state["updated_at"] = datetime.now().isoformat()

    def keepalive(self):
        if self.state.get("mode") == "demo":
            return
        cfg = self._config()
        interval = max(2, min(int(cfg.get("keepalive_sec", 5) or 5), 9))
        now = time.monotonic()
        if now - self.last_keepalive >= interval:
            try:
                self._send("/xremote")
                self.last_keepalive = now
            except Exception as exc:
                with self.lock:
                    self.state["last_error"] = str(exc)
                    self.state["online"] = False

    def refresh_channels(self):
        self.configure()
        numbers = sorted(
            {
                int(item.get("channel", 0) or 0)
                for item in self.state.get("channel_cache", {}).values()
                if int(item.get("channel", 0) or 0) > 0
            }
            | set(self._visible_channel_numbers())
        )
        for number in numbers:
            prefix = f"/ch/{number:02d}"
            self._safe_send(f"{prefix}/config/name")
            self._safe_send(f"{prefix}/mix/on")
            self._safe_send(f"{prefix}/mix/fader")
            self._safe_send(f"{prefix}/mix/pan")
        self._safe_send("/main/st/mix/fader")
        self._safe_send("/main/st/mix/on")

    def discover_mixers(self):
        self.configure()
        discovered = []
        current_host = str(self.state.get("host", "") or "").strip()
        if current_host:
            discovered.append(
                {
                    "no": 1,
                    "model": self.state.get("model", "") or "M32R",
                    "host": current_host,
                    "name": self.state.get("name", "") or "Midas M32R",
                    "firmware": self.state.get("firmware", "") or "",
                    "online": bool(self.state.get("online")),
                    "source": "current",
                }
            )
        for item in self._known_mixers_from_config():
            if any(existing["host"] == item["host"] for existing in discovered):
                continue
            discovered.append(
                {
                    "no": len(discovered) + 1,
                    "model": item.get("model") or "M32R",
                    "host": item.get("host", ""),
                    "name": item.get("name") or "Midas M32R",
                    "firmware": item.get("firmware", ""),
                    "online": item.get("host", "") == current_host and bool(self.state.get("online")),
                    "source": "known",
                }
            )
        with self.lock:
            self.state["discovered_mixers"] = discovered
            self.state["updated_at"] = datetime.now().isoformat()
        return self.snapshot()

    def set_channel_on(self, channel_no, on):
        channel_no = int(channel_no)
        self._safe_send(f"/ch/{channel_no:02d}/mix/on", [1 if bool(on) else 0])
        with self.lock:
            channel = self._merge_channel(channel_no)
            channel["on"] = bool(on)
            self._replace_channel(channel)
            self.state["updated_at"] = datetime.now().isoformat()
        return self.snapshot()

    def set_channel_fader(self, channel_no, normalized):
        channel_no = int(channel_no)
        normalized = _clamp(float(normalized), 0.0, 1.0)
        self._safe_send(f"/ch/{channel_no:02d}/mix/fader", [normalized])
        with self.lock:
            channel = self._merge_channel(channel_no)
            channel["fader"] = normalized
            channel["level_db"] = self.normalized_to_db(normalized)
            self._replace_channel(channel)
            self.state["updated_at"] = datetime.now().isoformat()
        return self.snapshot()

    def set_channel_pan(self, channel_no, normalized):
        channel_no = int(channel_no)
        normalized = _clamp(float(normalized), 0.0, 1.0)
        self._safe_send(f"/ch/{channel_no:02d}/mix/pan", [normalized])
        with self.lock:
            channel = self._merge_channel(channel_no)
            channel["pan"] = normalized
            self._replace_channel(channel)
            self.state["updated_at"] = datetime.now().isoformat()
        return self.snapshot()

    def set_channel_detail(self, channel_no, section, key, value):
        channel_no = int(channel_no)
        with self.lock:
            channel = self._merge_channel(channel_no)
            section_data = channel.get(section)
            if not isinstance(section_data, dict):
                raise ValueError("unsupported section")
            if key not in section_data:
                raise ValueError("unsupported key")
            current = section_data[key]
            if isinstance(current, bool):
                section_data[key] = bool(value)
            elif isinstance(current, int):
                section_data[key] = int(float(value))
            elif isinstance(current, float):
                section_data[key] = float(value)
            else:
                section_data[key] = value
            self._replace_channel(channel)
            self.state["updated_at"] = datetime.now().isoformat()
        return self.snapshot()

    def set_channel_label(self, channel_no, name=None, scribble=None):
        channel_no = int(channel_no)
        with self.lock:
            channel = self._merge_channel(channel_no)
            if name is not None:
                channel["name"] = str(name or "").strip() or f"CH {channel_no:02d}"
            if scribble is not None:
                channel["scribble"] = str(scribble or "").strip()
            self._replace_channel(channel)
            self.state["updated_at"] = datetime.now().isoformat()
        if name is not None:
            self._safe_send(f"/ch/{channel_no:02d}/config/name", [str(name or "").strip()])
        return self.snapshot()

    def set_main_on(self, on):
        self._safe_send("/main/st/mix/on", [1 if bool(on) else 0])
        with self.lock:
            self.state["main"]["on"] = bool(on)
            self.state["updated_at"] = datetime.now().isoformat()
        return self.snapshot()

    def set_main_fader(self, normalized):
        normalized = _clamp(float(normalized), 0.0, 1.0)
        self._safe_send("/main/st/mix/fader", [normalized])
        with self.lock:
            self.state["main"]["fader"] = normalized
            self.state["main"]["level_db"] = self.normalized_to_db(normalized)
            self.state["updated_at"] = datetime.now().isoformat()
        return self.snapshot()

    def apply_scene(self, scene_name):
        scene_name = str(scene_name or "").strip().lower()
        presets = {
            "speech": {"fader": 0.72, "main": 0.78},
            "vocal": {"fader": 0.76, "main": 0.80},
            "band": {"fader": 0.70, "main": 0.74},
        }
        preset = presets.get(scene_name)
        if not preset:
            raise ValueError("unsupported scene")
        for channel in self.snapshot().get("channels", []):
            self.set_channel_on(channel["channel"], True)
            self.set_channel_fader(channel["channel"], preset["fader"])
        self.set_main_on(True)
        self.set_main_fader(preset["main"])
        return self.snapshot()

    def capture_template(self, name):
        snap = self.snapshot()
        return {
            "name": str(name or "").strip() or "unnamed_template",
            "captured_at": datetime.now().isoformat(),
            "bank_start": self._bank_start(),
            "channel_count": len(snap.get("channels", [])),
            "main": deepcopy(snap.get("main", {})),
            "channels": [deepcopy(item) for item in snap.get("channels", [])],
        }

    def apply_template(self, template_data):
        template_data = template_data or {}
        for channel in template_data.get("channels", []):
            channel_no = int(channel.get("channel", 0) or 0)
            if channel_no <= 0:
                continue
            self.set_channel_label(channel_no, channel.get("name"), channel.get("scribble"))
            self.set_channel_on(channel_no, bool(channel.get("on", True)))
            self.set_channel_fader(channel_no, float(channel.get("fader", 0.75)))
            self.set_channel_pan(channel_no, float(channel.get("pan", 0.5)))
            for section in ["gate", "eq", "dyn", "sends"]:
                section_data = channel.get(section, {})
                if isinstance(section_data, dict):
                    for key, value in section_data.items():
                        self.set_channel_detail(channel_no, section, key, value)
        main = template_data.get("main", {})
        if isinstance(main, dict):
            self.set_main_on(bool(main.get("on", True)))
            self.set_main_fader(float(main.get("fader", 0.75)))
        return self.snapshot()

    def tick(self):
        self.keepalive()
        with self.lock:
            if not self.state.get("connected") or not self.state.get("online"):
                self._reset_levels_locked()
                self.state["updated_at"] = datetime.now().isoformat()
                return
            now = time.monotonic()
            stale = self.last_rx and (now - self.last_rx) > 12
            if stale and self.state.get("mode") == "live":
                self.state["online"] = False
                self._reset_levels_locked()
                self.state["updated_at"] = datetime.now().isoformat()
                return
            if self.state.get("mode") == "live" and (now - self.last_name_poll) >= 2.0:
                self.last_name_poll = now
                numbers = list(range(1, 33))
                for number in numbers:
                    self._safe_send(f"/ch/{number:02d}/config/name")
            for channel in self.state.get("channels", []):
                base = float(channel.get("fader", 0.0) or 0.0)
                meter = -60.0 + base * 54.0
                if not channel.get("on", True):
                    meter = -90.0
                channel["meter_db"] = round(meter, 1)
            main_base = float(self.state["main"].get("fader", 0.0) or 0.0)
            main_meter = -60.0 + main_base * 56.0
            if not self.state["main"].get("on", True):
                main_meter = -90.0
            self.state["main"]["meter_db"] = round(main_meter, 1)
            self.state["updated_at"] = datetime.now().isoformat()

    def snapshot(self):
        with self.lock:
            self._ensure_channels()
            return {
                "connected": bool(self.state.get("connected")),
                "online": bool(self.state.get("online")),
                "mode": self.state.get("mode", "offline"),
                "host": self.state.get("host", ""),
                "port": self.state.get("port", 10023),
                "name": self.state.get("name", "Midas M32R"),
                "model": self.state.get("model", ""),
                "firmware": self.state.get("firmware", ""),
                "show_position": self.state.get("show_position"),
                "last_error": self.state.get("last_error", ""),
                "updated_at": self.state.get("updated_at", ""),
                "last_rx_at": self.state.get("last_rx_at", ""),
                "auto_connect": bool(self.state.get("auto_connect")),
                "auto_sync": bool(self.state.get("auto_sync")),
                "sync_direction": self.state.get("sync_direction", "mixer_to_pc"),
                "known_mixers": deepcopy(self.state.get("known_mixers", [])),
                "discovered_mixers": deepcopy(self.state.get("discovered_mixers", [])),
                "local_ips": deepcopy(self.state.get("local_ips", [])),
                "feedback_sources": self.feedback_sources(),
                "channels": [deepcopy(item) for item in self.state.get("channels", [])],
                "main": deepcopy(self.state.get("main", {})),
            }

    @staticmethod
    def normalized_to_db(value):
        value = _clamp(float(value), 0.0, 1.0)
        return round(-90.0 + value * 100.0, 1)


m32r_service = M32RService()
