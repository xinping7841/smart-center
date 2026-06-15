import socket
import threading
import time
import struct
import os

MODBUS_DEBUG = str(os.environ.get("SMART_CENTER_MODBUS_DEBUG", "")).strip().lower() in {"1", "true", "yes", "on"}
MODBUS_DEBUG_THROTTLE_SEC = max(1.0, float(os.environ.get("SMART_CENTER_MODBUS_DEBUG_THROTTLE_SEC", "30") or 30))
_MODBUS_DEBUG_LOCK = threading.Lock()
_MODBUS_DEBUG_LAST = {}


from log_config import get_logger as _get_logger
_modbus_log = _get_logger("modbus_core")

def _debug_log(key, message):
    if not MODBUS_DEBUG:
        return
    now = time.monotonic()
    with _MODBUS_DEBUG_LOCK:
        last = float(_MODBUS_DEBUG_LAST.get(key, 0.0) or 0.0)
        if now - last < MODBUS_DEBUG_THROTTLE_SEC:
            return
        _MODBUS_DEBUG_LAST[key] = now
    _modbus_log.debug("%s", message)

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
    return crc.to_bytes(2, byteorder='little')

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
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(self.timeout)
                self.sock.connect((self.ip, self.port))
                return True
            except Exception as e:
                _debug_log(
                    f"connect:{self.ip}:{self.port}:{self.protocol}",
                    f"[Modbus DEBUG] 连接失败 -> IP: {self.ip}:{self.port} 协议: {self.protocol} | 错误: {e}",
                )
                self.close()
                return False
        return True

    def close(self):
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()
            except Exception: _log.debug("non-critical error suppressed", exc_info=True); pass
            self.sock = None

    def _flush_input(self):
        try:
            self.sock.setblocking(False)
            while self.sock.recv(4096): pass
        except Exception: _log.debug("non-critical error suppressed", exc_info=True); pass
        finally: self.sock.settimeout(self.timeout)

    def _safe_communicate(self, payload, is_rtu=False):
        with self._lock:
            for attempt in range(2):
                if not self.connect(): continue
                try:
                    self._flush_input()
                    self.sock.sendall(payload)
                    self.sock.settimeout(0.8)
                    res = b""
                    start = time.time()
                    while time.time() - start < 1.2:
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
                                        if res[j+2:j+4] == b'\x00\x00':  # Modbus TCP Protocol ID
                                            length = int.from_bytes(res[j+4:j+6], "big")
                                            if 0 < length <= 260 and j + 6 + length <= len(res):
                                                return res[j:j+6+length]
                        except socket.timeout: break
                    raise ConnectionError("读取响应超时")
                except Exception as e:
                    _debug_log(
                        f"rw:{self.ip}:{self.port}:{self.protocol}",
                        f"[Modbus DEBUG] 读写异常，准备重试 -> IP: {self.ip} 错误: {e}",
                    )
                    self.close()
            return None

    def send(self, function_code, data):
        if "RTU" in self.protocol or self.protocol == "PRSense":
            payload = bytes([self.slave, function_code]) + data
            payload += calc_crc(payload)
            res = self._safe_communicate(payload, is_rtu=True)
            return res[:-2] if res else None
        else:
            self.tx_id = (int(time.time() * 1000) % 65535)
            header = self.tx_id.to_bytes(2, "big") + b"\x00\x00" + (len(data) + 2).to_bytes(2, "big") + self.slave.to_bytes(1, "big") + function_code.to_bytes(1, "big")
            res = self._safe_communicate(header + data, is_rtu=False)
            return res[6:] if res else None

def parse_pdu_relay(pdu, count):
    try:
        if pdu[1] == 0x01:
            bits = []
            for b in pdu[3:]:
                for i in range(8): bits.append((b & (1 << i)) > 0)
            return bits[:count]
        else:
            bits = []
            for i in range(count): bits.append(pdu[3 + i*2 + 1] == 1)
            return bits
    except Exception: _log.debug("error in fallback path", exc_info=True); return None

def parse_av100_mode(p_mode, cab_conf):
    try: 
        mode_val = p_mode[-1]
        if mode_val == 0: return cab_conf["ui_text"]["label_mode_manual"]
        elif mode_val == 1: return cab_conf["ui_text"]["label_mode_remote"]
        elif mode_val in [2, 3]: return cab_conf["ui_text"].get("label_mode_external", "卡控模式")
        return cab_conf["ui_text"]["label_mode_unknown"]
    except Exception: _log.debug("error in fallback path", exc_info=True); return cab_conf["ui_text"]["label_mode_unknown"]

def parse_av100_env(p_env):
    try:
        d = p_env[3:]
        hum = int.from_bytes(d[0:2], "big") * 0.1
        temp = int.from_bytes(d[2:4], "big") * 0.1
        return hum, temp
    except Exception: _log.debug("error in fallback path", exc_info=True); return 0.0, 0.0

def parse_av100_meter(p_env, p_curr, mode="type1", ct_ratio=1.0):
    va, vb, vc, ia, ib, ic, energy = 0, 0, 0, 0, 0, 0, 0
    ct = float(ct_ratio) if ct_ratio else 1.0
    if ct <= 0: ct = 1.0
    if mode == "debug": return 0,0,0,0,0,0,0
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
    except Exception as e:
        _debug_log("parse_av100_meter", f"[Modbus DEBUG] 阵列解算报错: {e}")
    return round(va,1), round(vb,1), round(vc,1), round(ia,1), round(ib,1), round(ic,1), round(energy,2)

def parse_pdu_smart_env(pdu):
    try: return int.from_bytes(pdu[3:5], "big")*0.1, int.from_bytes(pdu[5:7], "big")*0.1
    except Exception: _log.debug("error in fallback path", exc_info=True); return None
def parse_pdu_smart_pwr(pdu):
    try:
        d = pdu[3:]
        return (int.from_bytes(d[0:2], "big")*0.1, int.from_bytes(d[2:4], "big")*0.1, int.from_bytes(d[4:6], "big")*0.1,
                int.from_bytes(d[6:8], "big")*0.1, int.from_bytes(d[8:10], "big")*0.1, int.from_bytes(d[10:12], "big")*0.1)
    except Exception: _log.debug("error in fallback path", exc_info=True); return None
def parse_prsense_env(pdu):
    try:
        # RTU 响应格式: 地址(1) 功能码(1) 字节数(1) 数据区(N)
        # 寄存器定义:
        # 500=湿度(10倍), 501=温度(10倍, 负数补码), ..., 506/507=Lux 高/低 16 位
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
            "illuminance": lux
        }
    except Exception: _log.debug("error in fallback path", exc_info=True); return None

try:
    from config import CONFIG
except Exception:
    CONFIG = {"cabinets": []}

clients = {}


def init_modbus_clients():
    global clients
    for c in list(clients.values()):
        try:
            c.close()
        except Exception:
            _log.debug("non-critical error suppressed", exc_info=True)
            pass
    cabinets = list((CONFIG or {}).get("cabinets", []))
    clients = {
        i: ModbusClient(
            cab["ip"],
            int(cab["port"]),
            int(cab.get("station_id", 50)),
            protocol=cab.get("plc_type", "AV-100"),
        )
        for i, cab in enumerate(cabinets)
        if isinstance(cab, dict) and cab.get("ip")
    }


init_modbus_clients()

def read_coils(cab_idx, start, count):
    if cab_idx not in clients: return None
    return clients[cab_idx].send(0x01, start.to_bytes(2, "big") + count.to_bytes(2, "big"))

def read_regs(cab_idx, start, count):
    if cab_idx not in clients: return None
    return clients[cab_idx].send(0x03, start.to_bytes(2, "big") + count.to_bytes(2, "big"))

def set_channel(cab_idx, ch, on):
    if cab_idx not in clients: return False
    client = clients[cab_idx]
    if "Smart" in client.protocol:
        reg = 0x05 + ch - 1
        return client.send(0x06, reg.to_bytes(2, "big") + (b"\x00\x01" if on else b"\x00\x00")) is not None
    else:
        reg = 0x03EB + (ch - 1) * 2 if on else 0x03EC + (ch - 1) * 2
        return client.send(0x05, reg.to_bytes(2, "big") + b"\xFF\x00") is not None

def reload_modbus_client():
    init_modbus_clients()


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
