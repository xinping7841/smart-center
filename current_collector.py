#!/usr/bin/env python3
"""CX-IXXXS/CX-I716SX current collector protocol helpers.

The device speaks standard Modbus-RTU function 0x03.  The protocol module is
transport-agnostic so the same reader can be used with a local RS485 adapter,
a transparent serial server, or native Modbus-TCP.
"""

from __future__ import annotations

import json
import socket
import struct
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional


DEFAULT_SLAVE_ADDRESS = 1
DEFAULT_REGISTER_BASE_100X = 0x0000
DEFAULT_REGISTER_BASE_10X = 0x1000
DEFAULT_CHANNEL_COUNT = 16
DEFAULT_SCALE_100X = 100.0
DEFAULT_SCALE_10X = 10.0


class CurrentCollectorError(RuntimeError):
    """Base exception for collector protocol or transport failures."""


class ModbusCrcError(CurrentCollectorError):
    """Raised when a Modbus-RTU frame CRC is invalid."""


def crc16_modbus(data: bytes) -> int:
    """Return Modbus CRC16 as an integer, low byte first on the wire."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def append_crc(frame_without_crc: bytes) -> bytes:
    crc = crc16_modbus(frame_without_crc)
    return frame_without_crc + bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def verify_crc(frame: bytes) -> None:
    if len(frame) < 4:
        raise ModbusCrcError(f"frame too short: {frame_to_hex(frame)}")
    expected = crc16_modbus(frame[:-2])
    actual = frame[-2] | (frame[-1] << 8)
    if expected != actual:
        raise ModbusCrcError(
            f"bad crc: expected 0x{expected:04X}, got 0x{actual:04X}, frame={frame_to_hex(frame)}"
        )


def frame_to_hex(frame: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in frame)


def parse_hex_frame(text: str) -> bytes:
    compact = "".join(ch for ch in str(text or "") if ch in "0123456789abcdefABCDEF")
    if len(compact) % 2:
        raise ValueError("hex text has odd length")
    return bytes.fromhex(compact)


def build_read_holding_registers_request(slave: int, start_register: int, count: int) -> bytes:
    if not 1 <= int(slave) <= 247:
        raise ValueError("slave address must be 1..247")
    if not 0 <= int(start_register) <= 0xFFFF:
        raise ValueError("start register must be 0..65535")
    if not 1 <= int(count) <= 125:
        raise ValueError("register count must be 1..125")
    pdu = bytes((int(slave), 0x03)) + struct.pack(">HH", int(start_register), int(count))
    return append_crc(pdu)


def parse_read_holding_registers_response(frame: bytes, slave: int, count: int) -> List[int]:
    verify_crc(frame)
    if len(frame) >= 5 and frame[1] & 0x80:
        raise CurrentCollectorError(f"modbus exception code 0x{frame[2]:02X}: {frame_to_hex(frame)}")
    expected_len = 5 + int(count) * 2
    if len(frame) != expected_len:
        raise CurrentCollectorError(f"unexpected response length {len(frame)}, expected {expected_len}: {frame_to_hex(frame)}")
    if frame[0] != int(slave):
        raise CurrentCollectorError(f"unexpected slave address {frame[0]}, expected {slave}: {frame_to_hex(frame)}")
    if frame[1] != 0x03:
        raise CurrentCollectorError(f"unexpected function 0x{frame[1]:02X}: {frame_to_hex(frame)}")
    byte_count = frame[2]
    if byte_count != int(count) * 2:
        raise CurrentCollectorError(f"unexpected byte count {byte_count}, expected {int(count) * 2}: {frame_to_hex(frame)}")
    payload = frame[3:-2]
    return [int.from_bytes(payload[index:index + 2], "big", signed=False) for index in range(0, len(payload), 2)]


def registers_to_currents(registers: Iterable[int], scale: float = DEFAULT_SCALE_100X, multiplier: float = 1.0) -> List[float]:
    factor = float(scale or DEFAULT_SCALE_100X)
    mult = float(multiplier or 1.0)
    if factor == 0:
        raise ValueError("scale cannot be zero")
    return [round((int(value) / factor) * mult, 3) for value in registers]


@dataclass
class CurrentSnapshot:
    currents: List[float]
    raw_registers: List[int]
    slave: int
    register_base: int
    scale: float
    multiplier: float
    request_hex: str
    response_hex: str
    transport: str
    collected_at: str

    def as_dict(self) -> dict:
        channel_map = {f"C{index + 1:02d}": value for index, value in enumerate(self.currents)}
        return {
            "online": True,
            "transport": self.transport,
            "slave": self.slave,
            "register_base": f"0x{self.register_base:04X}",
            "scale": self.scale,
            "multiplier": self.multiplier,
            "channel_count": len(self.currents),
            "currents": self.currents,
            "channels": channel_map,
            "raw_registers": self.raw_registers,
            "request_hex": self.request_hex,
            "response_hex": self.response_hex,
            "collected_at": self.collected_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, separators=(",", ":"))


class RtuSerialTransport:
    name = "rtu_serial"

    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: int = 1,
        timeout: float = 1.0,
    ) -> None:
        self.port = port
        self.baudrate = int(baudrate)
        self.bytesize = int(bytesize)
        self.parity = str(parity or "N").upper()
        self.stopbits = int(stopbits)
        self.timeout = float(timeout)
        self._serial = None

    def __enter__(self) -> "RtuSerialTransport":
        try:
            import serial
        except Exception as exc:  # pragma: no cover - depends on host install
            raise CurrentCollectorError("pyserial is required for serial mode: pip install pyserial") from exc
        self._serial = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=self.bytesize,
            parity=self.parity,
            stopbits=self.stopbits,
            timeout=self.timeout,
            write_timeout=self.timeout,
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def transact(self, request: bytes, expected_response_len: int) -> bytes:
        if self._serial is None:
            raise CurrentCollectorError("serial transport is not open")
        self._serial.reset_input_buffer()
        self._serial.write(request)
        self._serial.flush()
        return _read_until_len(lambda size: self._serial.read(size), expected_response_len, self.timeout)


class RtuTcpBridgeTransport:
    """Transparent TCP serial server: RTU frame with CRC goes through TCP."""

    name = "rtu_tcp"

    def __init__(self, host: str, port: int, timeout: float = 1.0) -> None:
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)
        self._sock: Optional[socket.socket] = None

    def __enter__(self) -> "RtuTcpBridgeTransport":
        self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self._sock.settimeout(self.timeout)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def transact(self, request: bytes, expected_response_len: int) -> bytes:
        if self._sock is None:
            raise CurrentCollectorError("tcp-rtu transport is not open")
        self._sock.sendall(request)
        return _read_until_len(lambda size: self._sock.recv(size), expected_response_len, self.timeout)


class ModbusTcpTransport:
    """Native Modbus-TCP: MBAP header plus PDU, no RTU CRC."""

    name = "modbus_tcp"

    def __init__(self, host: str, port: int = 502, timeout: float = 1.0, transaction_id: int = 1) -> None:
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)
        self.transaction_id = int(transaction_id) & 0xFFFF
        self._sock: Optional[socket.socket] = None

    def __enter__(self) -> "ModbusTcpTransport":
        self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self._sock.settimeout(self.timeout)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def read_holding_registers(self, slave: int, start_register: int, count: int) -> tuple[bytes, bytes, List[int]]:
        if self._sock is None:
            raise CurrentCollectorError("modbus-tcp transport is not open")
        pdu = bytes((0x03,)) + struct.pack(">HH", int(start_register), int(count))
        mbap = struct.pack(">HHHB", self.transaction_id, 0, len(pdu) + 1, int(slave))
        request = mbap + pdu
        self._sock.sendall(request)
        header = _read_exact(lambda size: self._sock.recv(size), 7, self.timeout)
        tid, proto, length, unit = struct.unpack(">HHHB", header)
        if tid != self.transaction_id or proto != 0:
            raise CurrentCollectorError(f"unexpected modbus-tcp header: {frame_to_hex(header)}")
        body = _read_exact(lambda size: self._sock.recv(size), length - 1, self.timeout)
        response = header + body
        if unit != int(slave):
            raise CurrentCollectorError(f"unexpected unit id {unit}, expected {slave}: {frame_to_hex(response)}")
        if body and body[0] & 0x80:
            code = body[1] if len(body) > 1 else 0
            raise CurrentCollectorError(f"modbus-tcp exception code 0x{code:02X}: {frame_to_hex(response)}")
        if len(body) != 2 + int(count) * 2 or body[0] != 0x03 or body[1] != int(count) * 2:
            raise CurrentCollectorError(f"unexpected modbus-tcp response: {frame_to_hex(response)}")
        payload = body[2:]
        registers = [int.from_bytes(payload[index:index + 2], "big", signed=False) for index in range(0, len(payload), 2)]
        return request, response, registers


def _read_exact(read_func, length: int, timeout: float) -> bytes:
    deadline = time.monotonic() + float(timeout)
    chunks = bytearray()
    while len(chunks) < length and time.monotonic() < deadline:
        chunk = read_func(length - len(chunks))
        if chunk:
            chunks.extend(chunk)
        else:
            time.sleep(0.01)
    if len(chunks) != length:
        raise CurrentCollectorError(f"timeout reading response: got {len(chunks)} bytes, expected {length}")
    return bytes(chunks)


def _read_until_len(read_func, expected_len: int, timeout: float) -> bytes:
    response = _read_exact(read_func, min(5, expected_len), timeout)
    if len(response) >= 2 and response[1] & 0x80:
        return response
    if expected_len <= len(response):
        return response[:expected_len]
    return response + _read_exact(read_func, expected_len - len(response), timeout)


class CurrentCollector:
    def __init__(
        self,
        transport,
        slave: int = DEFAULT_SLAVE_ADDRESS,
        register_base: int = DEFAULT_REGISTER_BASE_100X,
        channel_count: int = DEFAULT_CHANNEL_COUNT,
        scale: float = DEFAULT_SCALE_100X,
        multiplier: float = 1.0,
    ) -> None:
        self.transport = transport
        self.slave = int(slave)
        self.register_base = int(register_base)
        self.channel_count = int(channel_count)
        self.scale = float(scale)
        self.multiplier = float(multiplier)

    def read_once(self) -> CurrentSnapshot:
        if isinstance(self.transport, ModbusTcpTransport):
            request, response, registers = self.transport.read_holding_registers(
                self.slave,
                self.register_base,
                self.channel_count,
            )
        else:
            request = build_read_holding_registers_request(self.slave, self.register_base, self.channel_count)
            expected_len = 5 + self.channel_count * 2
            response = self.transport.transact(request, expected_len)
            registers = parse_read_holding_registers_response(response, self.slave, self.channel_count)
        currents = registers_to_currents(registers, self.scale, self.multiplier)
        return CurrentSnapshot(
            currents=currents,
            raw_registers=registers,
            slave=self.slave,
            register_base=self.register_base,
            scale=self.scale,
            multiplier=self.multiplier,
            request_hex=frame_to_hex(request),
            response_hex=frame_to_hex(response),
            transport=getattr(self.transport, "name", self.transport.__class__.__name__),
            collected_at=datetime.now().isoformat(timespec="seconds"),
        )

