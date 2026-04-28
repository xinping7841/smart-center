from __future__ import annotations

import hashlib
import logging
import secrets
import socketserver
from dataclasses import dataclass

from .state import SimulatorState


LOGGER = logging.getLogger("pjlink-simulator.tcp")


@dataclass
class CommandResult:
    ok: bool
    body: str


class PJLinkCommandProcessor:
    def __init__(self, state: SimulatorState):
        self.state = state

    def handle(self, raw_command: str) -> str:
        command = raw_command.strip()
        if not command.startswith("%") or len(command) < 6:
            return "PJLINK ERRA"

        header, parameter = self._split_command(command)
        pj_class = header[1]
        cmd = header[2:]

        if pj_class not in {"1", "2"}:
            return "PJLINK ERRA"

        profile = self.state.get_profile()
        max_class = str(profile["pjlink_class"])
        if int(pj_class) > int(max_class):
            return f"%{pj_class}{cmd}=ERR1"

        result = self._dispatch(pj_class, cmd, parameter)
        return f"%{pj_class}{cmd}={result.body}"

    def _split_command(self, command: str) -> tuple[str, str]:
        text = command[1:]
        if " " in text:
            header, parameter = text.split(" ", 1)
            return f"%{header}", parameter.strip()
        return f"%{text}", ""

    def _dispatch(self, pj_class: str, cmd: str, parameter: str) -> CommandResult:
        profile = self.state.get_profile()
        supports = profile["supports"]

        handlers = {
            "POWR": self._power,
            "INPT": self._input,
            "AVMT": self._av_mute,
            "ERST": self._error_status,
            "LAMP": self._lamp_status,
            "INST": self._installed_inputs,
            "NAME": self._device_name,
            "INF1": self._manufacturer,
            "INF2": self._product,
            "INFO": self._other_info,
            "CLSS": self._class_info,
            "SNUM": self._serial_number,
            "SVER": self._software_version,
            "INNM": self._input_name,
            "IRES": self._input_resolution,
            "RRES": self._recommended_resolution,
            "FILT": self._filter_hours,
            "RLMP": self._lamp_model,
            "RFIL": self._filter_model,
            "FREZ": self._freeze,
            "SVOL": self._speaker_volume,
            "MVOL": self._microphone_volume,
        }

        if cmd not in handlers:
            return CommandResult(False, "ERR1")

        if cmd in {"SNUM", "SVER", "INNM", "IRES", "RRES", "FILT", "RLMP", "RFIL", "FREZ", "SVOL", "MVOL"}:
            if pj_class != "2":
                return CommandResult(False, "ERR1")

        capability_map = {
            "SNUM": supports["serial_number"],
            "SVER": supports["software_version"],
            "INNM": supports["input_name"],
            "IRES": supports["input_resolution"],
            "RRES": supports["recommended_resolution"],
            "FILT": supports["filter_hours"],
            "RLMP": supports["lamp_model"],
            "RFIL": supports["filter_model"],
            "FREZ": supports["freeze"],
            "SVOL": supports["speaker_volume"],
            "MVOL": supports["microphone_volume"],
        }
        if cmd in capability_map and not capability_map[cmd]:
            return CommandResult(False, "ERR1")

        return handlers[cmd](parameter)

    def _power(self, parameter: str) -> CommandResult:
        if parameter == "?":
            return CommandResult(True, self.state.get_power_state())
        if parameter in {"0", "1"}:
            self.state.set_power(parameter)
            return CommandResult(True, "OK")
        return CommandResult(False, "ERR2")

    def _input(self, parameter: str) -> CommandResult:
        if parameter == "?":
            return CommandResult(True, self.state.snapshot()["input_code"])
        try:
            self.state.set_input(parameter)
            return CommandResult(True, "OK")
        except ValueError:
            return CommandResult(False, "ERR2")

    def _av_mute(self, parameter: str) -> CommandResult:
        snapshot = self.state.snapshot()
        if parameter == "?":
            if snapshot["audio_muted"] and snapshot["video_muted"]:
                return CommandResult(True, "31")
            if snapshot["video_muted"]:
                return CommandResult(True, "11")
            if snapshot["audio_muted"]:
                return CommandResult(True, "21")
            return CommandResult(True, "30")

        mapping = {
            "11": {"video_muted": True},
            "10": {"video_muted": False},
            "21": {"audio_muted": True},
            "20": {"audio_muted": False},
            "31": {"audio_muted": True, "video_muted": True},
            "30": {"audio_muted": False, "video_muted": False},
        }
        if parameter not in mapping:
            return CommandResult(False, "ERR2")
        self.state.update(mapping[parameter])
        return CommandResult(True, "OK")

    def _error_status(self, parameter: str) -> CommandResult:
        if parameter != "?":
            return CommandResult(False, "ERR2")
        return CommandResult(True, self.state.snapshot()["error_status"])

    def _lamp_status(self, parameter: str) -> CommandResult:
        if parameter != "?":
            return CommandResult(False, "ERR2")
        lamp_hours = self.state.snapshot()["lamp_hours"]
        if not lamp_hours:
            return CommandResult(False, "ERR1")
        parts = []
        for hours in lamp_hours:
            parts.extend([str(hours), "1"])
        return CommandResult(True, " ".join(parts))

    def _installed_inputs(self, parameter: str) -> CommandResult:
        if parameter != "?":
            return CommandResult(False, "ERR2")
        return CommandResult(True, " ".join(self.state.get_inputs().keys()))

    def _device_name(self, parameter: str) -> CommandResult:
        if parameter != "?":
            return CommandResult(False, "ERR2")
        return CommandResult(True, self.state.snapshot()["device_name"])

    def _manufacturer(self, parameter: str) -> CommandResult:
        if parameter != "?":
            return CommandResult(False, "ERR2")
        return CommandResult(True, self.state.snapshot()["manufacturer_name"])

    def _product(self, parameter: str) -> CommandResult:
        if parameter != "?":
            return CommandResult(False, "ERR2")
        return CommandResult(True, self.state.snapshot()["product_name"])

    def _other_info(self, parameter: str) -> CommandResult:
        if parameter != "?":
            return CommandResult(False, "ERR2")
        return CommandResult(True, self.state.snapshot()["other_info"])

    def _class_info(self, parameter: str) -> CommandResult:
        if parameter != "?":
            return CommandResult(False, "ERR2")
        return CommandResult(True, str(self.state.get_profile()["pjlink_class"]))

    def _serial_number(self, parameter: str) -> CommandResult:
        if parameter != "?":
            return CommandResult(False, "ERR2")
        return CommandResult(True, self.state.snapshot()["serial_number"])

    def _software_version(self, parameter: str) -> CommandResult:
        if parameter != "?":
            return CommandResult(False, "ERR2")
        return CommandResult(True, self.state.snapshot()["software_version"])

    def _input_name(self, parameter: str) -> CommandResult:
        inputs = self.state.get_inputs()
        if parameter == "?":
            body = ";".join(f"{code}:{name}" for code, name in inputs.items())
            return CommandResult(True, body)
        if parameter in inputs:
            return CommandResult(True, inputs[parameter])
        return CommandResult(False, "ERR2")

    def _input_resolution(self, parameter: str) -> CommandResult:
        if parameter != "?":
            return CommandResult(False, "ERR2")
        return CommandResult(True, self.state.snapshot()["input_resolution"])

    def _recommended_resolution(self, parameter: str) -> CommandResult:
        if parameter != "?":
            return CommandResult(False, "ERR2")
        return CommandResult(True, self.state.snapshot()["recommended_resolution"])

    def _filter_hours(self, parameter: str) -> CommandResult:
        if parameter != "?":
            return CommandResult(False, "ERR2")
        filter_hours = self.state.snapshot()["filter_hours"]
        if not filter_hours:
            return CommandResult(False, "ERR1")
        return CommandResult(True, " ".join(str(value) for value in filter_hours))

    def _lamp_model(self, parameter: str) -> CommandResult:
        if parameter != "?":
            return CommandResult(False, "ERR2")
        models = self.state.snapshot()["lamp_models"]
        if not models:
            return CommandResult(False, "ERR1")
        return CommandResult(True, ";".join(models))

    def _filter_model(self, parameter: str) -> CommandResult:
        if parameter != "?":
            return CommandResult(False, "ERR2")
        models = self.state.snapshot()["filter_models"]
        if not models:
            return CommandResult(False, "ERR1")
        return CommandResult(True, ";".join(models))

    def _freeze(self, parameter: str) -> CommandResult:
        if parameter == "?":
            return CommandResult(True, "1" if self.state.snapshot()["freeze"] else "0")
        if parameter not in {"0", "1"}:
            return CommandResult(False, "ERR2")
        self.state.update({"freeze": parameter == "1"})
        return CommandResult(True, "OK")

    def _speaker_volume(self, parameter: str) -> CommandResult:
        if parameter not in {"0", "1"}:
            return CommandResult(False, "ERR2")
        snapshot = self.state.snapshot()
        delta = 1 if parameter == "1" else -1
        self.state.update({"speaker_volume": snapshot["speaker_volume"] + delta})
        return CommandResult(True, "OK")

    def _microphone_volume(self, parameter: str) -> CommandResult:
        if parameter not in {"0", "1"}:
            return CommandResult(False, "ERR2")
        snapshot = self.state.snapshot()
        delta = 1 if parameter == "1" else -1
        self.state.update({"microphone_volume": snapshot["microphone_volume"] + delta})
        return CommandResult(True, "OK")


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


class PJLinkTCPHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        app = self.server.app
        auth_mode = app.state.snapshot()["auth_mode"]
        nonce = secrets.token_hex(4).upper()
        handshake = "PJLINK 0\r" if auth_mode == "none" else f"PJLINK 1 {nonce}\r"

        self.wfile.write(handshake.encode("ascii"))
        self.wfile.flush()
        LOGGER.info("Client connected from %s, handshake=%s", self.client_address[0], handshake.strip())

        while True:
            raw = self._read_cr_terminated()
            if not raw:
                return
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            command = self._authenticate(line, nonce, auth_mode)
            if command is None:
                self.wfile.write(b"PJLINK ERRA\r")
                self.wfile.flush()
                return
            response = app.processor.handle(command)
            LOGGER.info("PJLink <- %s | -> %s", command, response)
            self.wfile.write((response + "\r").encode("utf-8"))
            self.wfile.flush()

    def _read_cr_terminated(self) -> bytes:
        data = bytearray()
        while True:
            chunk = self.connection.recv(1)
            if not chunk:
                break
            if chunk == b"\r":
                break
            if chunk == b"\n":
                continue
            data.extend(chunk)
        return bytes(data)

    def _authenticate(self, line: str, nonce: str, auth_mode: str) -> str | None:
        if auth_mode == "none":
            return line

        password = self.server.app.state.snapshot().get("password", "")
        md5_prefix = hashlib.md5(f"{nonce}{password}".encode("utf-8")).hexdigest()
        sha256_prefix = hashlib.sha256(f"{nonce}{password}".encode("utf-8")).hexdigest()

        if line.startswith(md5_prefix):
            return line[len(md5_prefix):]
        if auth_mode == "auto" and line.startswith(sha256_prefix):
            return line[len(sha256_prefix):]
        return None


class PJLinkServerApp:
    def __init__(self, host: str, port: int, state: SimulatorState):
        self.host = host
        self.port = port
        self.state = state
        self.processor = PJLinkCommandProcessor(state)
        self._server = ThreadedTCPServer((host, port), PJLinkTCPHandler)
        self._server.app = self

    def serve_forever(self) -> None:
        LOGGER.info("PJLink TCP server listening on %s:%s", self.host, self.port)
        self._server.serve_forever()

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()
