import os
import socket
import struct
import threading
import time

CONNECT_RETRIES = max(int(os.getenv("METER_CONNECT_RETRIES", "5") or 5), 1)
IO_RETRIES = max(int(os.getenv("METER_IO_RETRIES", "5") or 5), 1)
CONNECT_RETRY_DELAY = max(float(os.getenv("METER_CONNECT_RETRY_DELAY", "0.4") or 0.4), 0.05)
READ_WINDOW_SECONDS = max(float(os.getenv("METER_READ_WINDOW_SECONDS", "3.2") or 3.2), 0.5)
READ_TIMEOUT_SECONDS = max(float(os.getenv("METER_READ_TIMEOUT_SECONDS", "1.8") or 1.8), 0.3)


def calc_crc(data):
    crc = 0xFFFF
    for pos in data:
        crc ^= pos
        for _ in range(8):
            if (crc & 1) != 0:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc.to_bytes(2, byteorder="little")


class ModbusClient:
    def __init__(self, ip, port, slave=1, timeout=1.5, protocol="AV-100"):
        self.ip = ip
        self.port = port
        self.slave = slave
        self.timeout = timeout
        self.protocol = protocol
        self.sock = None
        self._lock = threading.Lock()

    def connect(self):
        if self.sock is None:
            for attempt in range(CONNECT_RETRIES):
                try:
                    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    self.sock.settimeout(max(float(self.timeout or 0), 0.5))
                    self.sock.connect((self.ip, self.port))
                    return True
                except Exception:
                    self.close()
                    if attempt < CONNECT_RETRIES - 1:
                        time.sleep(CONNECT_RETRY_DELAY)
            return False
        return True

    def close(self):
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def _flush_input(self):
        try:
            self.sock.setblocking(False)
            while self.sock.recv(4096):
                pass
        except Exception:
            pass
        finally:
            self.sock.settimeout(self.timeout)

    def _safe_communicate(self, payload, is_rtu=False):
        with self._lock:
            for attempt in range(IO_RETRIES):
                if not self.connect():
                    if attempt < IO_RETRIES - 1:
                        time.sleep(CONNECT_RETRY_DELAY)
                    continue
                try:
                    self._flush_input()
                    self.sock.sendall(payload)
                    self.sock.settimeout(READ_TIMEOUT_SECONDS)
                    res = b""
                    start = time.time()
                    while time.time() - start < READ_WINDOW_SECONDS:
                        try:
                            chunk = self.sock.recv(1024)
                            if chunk:
                                res += chunk
                                if is_rtu and len(res) >= 5:
                                    for i in range(len(res) - 4):
                                        sub = res[i:]
                                        if len(sub) >= 5 and calc_crc(sub[:-2]) == sub[-2:]:
                                            return sub
                                if not is_rtu and len(res) >= 9:
                                    for j in range(len(res) - 5):
                                        if res[j + 2:j + 4] == b"\x00\x00":
                                            length = int.from_bytes(res[j + 4:j + 6], "big")
                                            if 0 < length <= 260 and j + 6 + length <= len(res):
                                                return res[j:j + 6 + length]
                        except socket.timeout:
                            break
                    raise ConnectionError("read timeout")
                except Exception:
                    self.close()
                    if attempt < IO_RETRIES - 1:
                        time.sleep(CONNECT_RETRY_DELAY)
            return None

    def send(self, function_code, data):
        if "RTU" in self.protocol or self.protocol == "PRSense":
            payload = bytes([self.slave, function_code]) + data
            payload += calc_crc(payload)
            res = self._safe_communicate(payload, is_rtu=True)
            return res[:-2] if res else None
        self.tx_id = int(time.time() * 1000) % 65535
        header = (
            self.tx_id.to_bytes(2, "big")
            + b"\x00\x00"
            + (len(data) + 2).to_bytes(2, "big")
            + self.slave.to_bytes(1, "big")
            + function_code.to_bytes(1, "big")
        )
        res = self._safe_communicate(header + data, is_rtu=False)
        return res[6:] if res else None


def parse_pdu_relay(pdu, count):
    try:
        if pdu[1] == 0x01:
            bits = []
            for b in pdu[3:]:
                for i in range(8):
                    bits.append((b & (1 << i)) > 0)
            return bits[:count]
        bits = []
        for i in range(count):
            bits.append(pdu[3 + i * 2 + 1] == 1)
        return bits
    except Exception:
        return None


def parse_av100_env(p_env):
    try:
        d = p_env[3:]
        hum = int.from_bytes(d[0:2], "big") * 0.1
        temp = int.from_bytes(d[2:4], "big") * 0.1
        return hum, temp
    except Exception:
        return 0.0, 0.0


def parse_av100_meter(p_env, p_curr, mode="type1", ct_ratio=1.0):
    va, vb, vc, ia, ib, ic, energy = 0, 0, 0, 0, 0, 0, 0
    ct = float(ct_ratio) if ct_ratio else 1.0
    if ct <= 0:
        ct = 1.0
    if mode == "debug":
        return 0, 0, 0, 0, 0, 0, 0
    try:
        if mode == "type1":
            if p_env and len(p_env) >= 17:
                d = p_env[3:]
                energy = int.from_bytes(d[4:8], "big") * 0.01 * ct
                va = int.from_bytes(d[8:10], "big") * 0.1
                vb = int.from_bytes(d[10:12], "big") * 0.1
                vc = int.from_bytes(d[12:14], "big") * 0.1
            if p_curr and len(p_curr) >= 15:
                d = p_curr[3:]
                ia = int.from_bytes(d[0:2], "big") * 0.1 * ct
                ib = int.from_bytes(d[4:6], "big") * 0.1 * ct
                ic = int.from_bytes(d[8:10], "big") * 0.1 * ct
        elif mode == "type2":
            if p_curr and len(p_curr) >= 19:
                d = p_curr[3:]
                va = int.from_bytes(d[0:2], "big") * 0.1
                vb = int.from_bytes(d[2:4], "big") * 0.1
                vc = int.from_bytes(d[4:6], "big") * 0.1
                ia = int.from_bytes(d[6:8], "big") * 0.1 * ct
                ib = int.from_bytes(d[8:10], "big") * 0.1 * ct
                ic = int.from_bytes(d[10:12], "big") * 0.1 * ct
                energy = int.from_bytes(d[12:16], "big") * 0.01 * ct
        elif mode == "type3":
            if p_env and len(p_env) >= 23:
                d = p_env[3:]
                va = int.from_bytes(d[4:6], "big") * 0.1
                vb = int.from_bytes(d[6:8], "big") * 0.1
                vc = int.from_bytes(d[8:10], "big") * 0.1
                ia = int.from_bytes(d[10:12], "big") * 0.1 * ct
                ib = int.from_bytes(d[12:14], "big") * 0.1 * ct
                ic = int.from_bytes(d[14:16], "big") * 0.1 * ct
                energy = int.from_bytes(d[16:20], "big") * 0.01 * ct
        elif mode == "type4":
            if p_env and len(p_env) >= 35:
                d = p_env[3:]
                va = int.from_bytes(d[8:12], "big") / 10000.0
                vb = int.from_bytes(d[12:16], "big") / 10000.0
                vc = int.from_bytes(d[16:20], "big") / 10000.0
                raw_energy = int.from_bytes(d[30:32] + d[28:30], "big")
                energy = raw_energy / 100.0 * ct
            if p_curr and len(p_curr) >= 15:
                d = p_curr[3:]
                ia = int.from_bytes(d[0:4], "big") / 10000.0 * ct
                ib = int.from_bytes(d[4:8], "big") / 10000.0 * ct
                ic = int.from_bytes(d[8:12], "big") / 10000.0 * ct
    except Exception:
        pass
    return round(va, 1), round(vb, 1), round(vc, 1), round(ia, 1), round(ib, 1), round(ic, 1), round(energy, 2)


def parse_prsense_env(pdu):
    try:
        if len(pdu) < 19:
            return None
        byte_count = pdu[2]
        data = pdu[3:3 + byte_count]
        if len(data) < 16:
            return None
        hum = int.from_bytes(data[0:2], "big") * 0.1
        temp_raw = int.from_bytes(data[2:4], "big")
        if temp_raw > 0x7FFF:
            temp_raw -= 0x10000
        temp = temp_raw * 0.1
        noise = int.from_bytes(data[4:6], "big") * 0.1
        pm25 = int.from_bytes(data[6:8], "big")
        pm10 = int.from_bytes(data[8:10], "big")
        pressure = int.from_bytes(data[10:12], "big") * 0.1
        lux_high = int.from_bytes(data[12:14], "big")
        lux_low = int.from_bytes(data[14:16], "big")
        lux = (lux_high << 16) | lux_low
        return {
            "humidity": round(hum, 1),
            "temperature": round(temp, 1),
            "noise": round(noise, 1),
            "pm25": pm25,
            "pm10": pm10,
            "pressure": round(pressure, 1),
            "illuminance": lux,
        }
    except Exception:
        return None


def make_client(ip, port, slave=1, timeout=1.5, protocol="AV-100"):
    return ModbusClient(ip, int(port), int(slave), timeout=timeout, protocol=protocol)


def read_registers_by_client(client, function_code, start, count):
    if not client:
        return None
    return client.send(int(function_code), int(start).to_bytes(2, "big") + int(count).to_bytes(2, "big"))


def _normalize_byte_order(data, byte_order="ABCD"):
    raw = bytes(data or b"")
    order = str(byte_order or "").upper()
    if len(raw) == 2:
        if order in ("BA", "DCBA"):
            return raw[::-1]
        return raw
    if len(raw) == 4:
        if order == "ABCD":
            return raw
        if order == "BADC":
            return bytes([raw[1], raw[0], raw[3], raw[2]])
        if order == "CDAB":
            return bytes([raw[2], raw[3], raw[0], raw[1]])
        if order == "DCBA":
            return raw[::-1]
    return raw


def decode_register_bytes(register_bytes, data_type="u16", scale=1.0, byte_order="AB"):
    data_type = str(data_type or "u16").lower()
    scale = float(scale or 1.0)
    raw = _normalize_byte_order(register_bytes, byte_order)
    if data_type == "u16":
        value = int.from_bytes(raw[:2], "big", signed=False)
    elif data_type == "s16":
        value = int.from_bytes(raw[:2], "big", signed=True)
    elif data_type == "u32":
        value = int.from_bytes(raw[:4], "big", signed=False)
    elif data_type == "s32":
        value = int.from_bytes(raw[:4], "big", signed=True)
    elif data_type == "f32":
        value = struct.unpack(">f", raw[:4])[0]
    else:
        raise ValueError(f"Unsupported data_type: {data_type}")
    return float(value) * scale


def extract_register_bytes_from_pdu(pdu):
    if not pdu or len(pdu) < 3:
        return None
    byte_count = pdu[2]
    payload = pdu[3:3 + byte_count]
    if len(payload) != byte_count:
        return None
    return payload
