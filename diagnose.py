import socket
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from config import CONFIG

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

def test_modbus(ip, port, station_id=50):
    # Read holding registers: FC03, addr=0x04B0, count=4
    payload = bytes([station_id, 0x03, 0x04, 0xB0, 0x00, 0x04])
    payload += calc_crc(payload)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect((ip, port))
        s.sendall(payload)
        s.settimeout(1.5)
        res = s.recv(256)
        s.close()
        return True, res.hex(" ").upper()
    except Exception as e:
        return False, str(e)

print("=" * 60)
print("电柜通讯诊断")
print("=" * 60)

for i, cab in enumerate(CONFIG.get("cabinets", [])):
    ip = cab["ip"]
    port = int(cab["port"])
    sid = int(cab.get("station_id", 50))
    name = cab.get("cabinet_name", f"电柜{i}")
    print(f"\n[{i}] {name}  {ip}:{port}  station_id={sid}")

    # TCP test
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect((ip, port))
        s.close()
        print(f"    TCP:    ✅ 连通")
    except Exception as e:
        print(f"    TCP:    ❌ 失败 -> {e}")
        continue

    # Modbus test
    ok, detail = test_modbus(ip, port, sid)
    if ok:
        print(f"    Modbus: ✅ 响应 -> {detail}")
    else:
        print(f"    Modbus: ❌ 失败 -> {detail}")

print("\n" + "=" * 60)
