import socket
import serial
import threading
import time

# 全局串口锁字典，防止多个设备共用一个串口或并发冲突
_serial_locks = {}

def get_serial_lock(com_port):
    if com_port not in _serial_locks:
        _serial_locks[com_port] = threading.Lock()
    return _serial_locks[com_port]

class UniversalDriver:
    def __init__(self, config):
        """
        config 示例:
        {
            "id": "matrix_1",
            "interface": "tcp", # 可选: tcp, udp, com
            "ip": "192.168.50.80", "port": 4000,
            "com_port": "COM4", "baudrate": 115200
        }
        """
        self.cfg = config

    def execute_command(self, cmd_config):
        """
        cmd_config 示例:
        {
            "payload": "AA BB 01", 
            "format": "hex", # 或 "str"
            "wait_ms": 500, # 等待反馈的毫秒数
            "expect_return": "AA BB 00" # 预期收到的反馈 (可选)
        }
        """
        interface = self.cfg.get("interface", "tcp").lower()
        payload_raw = cmd_config.get("payload", "")
        fmt = cmd_config.get("format", "str")
        wait_ms = cmd_config.get("wait_ms", 0)
        
        # 1. 转换 Payload
        try:
            if fmt == "hex":
                payload = bytes.fromhex(payload_raw.replace(" ", ""))
            else:
                # 支持在字符串中写入转义字符，比如发给 Hirender 的指令可能包含 \r\n
                payload = payload_raw.encode('utf-8').decode('unicode_escape').encode('utf-8')
        except Exception as e:
            return False, f"命令格式解析失败: {str(e)}"

        # 2. 路由到具体接口
        if interface == "tcp":
            return self._send_tcp(payload, wait_ms)
        elif interface == "udp":
            return self._send_udp(payload, wait_ms)
        elif interface == "com":
            return self._send_com(payload, wait_ms)
        else:
            return False, f"不支持的接口类型: {interface}"

    def _send_tcp(self, payload, wait_ms):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((self.cfg["ip"], int(self.cfg["port"])))
                s.sendall(payload)
                
                if wait_ms > 0:
                    s.settimeout(wait_ms / 1000.0)
                    try:
                        res = s.recv(1024)
                        return True, res
                    except socket.timeout:
                        return True, b"" # 超时没收到也算发送成功
                return True, b"TCP Sent"
        except Exception as e:
            return False, f"TCP 失败: {str(e)}"

    def _send_udp(self, payload, wait_ms):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(2.0)
                s.sendto(payload, (self.cfg["ip"], int(self.cfg["port"])))
                
                if wait_ms > 0:
                    s.settimeout(wait_ms / 1000.0)
                    try:
                        res, _ = s.recvfrom(1024)
                        return True, res
                    except socket.timeout:
                        return True, b""
                return True, b"UDP Sent"
        except Exception as e:
            return False, f"UDP 失败: {str(e)}"

    def _send_com(self, payload, wait_ms):
        com_port = self.cfg.get("com_port")
        lock = get_serial_lock(com_port)
        
        with lock:
            try:
                with serial.Serial(com_port, int(self.cfg.get("baudrate", 9600)), timeout=1.0) as ser:
                    ser.flushInput()
                    ser.write(payload)
                    
                    if wait_ms > 0:
                        # 串口的等待逻辑：睡一会儿再读缓冲区
                        time.sleep(wait_ms / 1000.0)
                        res = ser.read_all()
                        return True, res
                    return True, b"COM Sent"
            except Exception as e:
                return False, f"COM 失败: {str(e)}"
