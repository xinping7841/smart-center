"""
温控设备驱动核心模块
支持常见温控协议 (Modbus TCP, 自定义TCP等)
"""
import socket
import struct

class HVACDriver:
    """温控设备驱动基类"""

    def __init__(self, config):
        """
        初始化温控驱动

        Args:
            config: 设备配置字典
                {
                    "id": "hvac_1",
                    "name": "一号厅空调",
                    "ip": "192.168.50.100",
                    "port": 502,
                    "protocol": "modbus_tcp",  # 或 "custom_tcp"
                    "station_id": 1
                }
        """
        self.config = config
        self.ip = config.get("ip")
        self.port = int(config.get("port", 502))
        self.protocol = config.get("protocol", "modbus_tcp")
        self.station_id = int(config.get("station_id", 1))

    def connect(self):
        """建立连接"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(3)
            self.sock.connect((self.ip, self.port))
            return True
        except Exception as e:
            return False

    def disconnect(self):
        """断开连接"""
        try:
            if hasattr(self, 'sock'):
                self.sock.close()
        except:
            pass

    def read_status(self):
        """
        读取设备状态

        Returns:
            dict: {
                "online": True/False,
                "temperature": 25.5,  # 当前温度
                "target_temp": 26.0,  # 目标温度
                "mode": "cool",       # cool/heat/auto/fan/off
                "fan_speed": "auto",  # auto/low/mid/high
                "power": True         # 开关状态
            }
        """
        if not self.connect():
            return {"online": False}

        try:
            if self.protocol == "modbus_tcp":
                # Modbus TCP 读取保持寄存器
                # 假设：寄存器 0=当前温度*10, 1=目标温度*10, 2=模式, 3=风速, 4=电源
                data = self._modbus_read_holding_registers(0, 5)
                if data:
                    return {
                        "online": True,
                        "temperature": data[0] / 10.0,
                        "target_temp": data[1] / 10.0,
                        "mode": self._decode_mode(data[2]),
                        "fan_speed": self._decode_fan_speed(data[3]),
                        "power": bool(data[4])
                    }

            return {"online": False}

        except Exception as e:
            return {"online": False, "error": str(e)}

        finally:
            self.disconnect()

    def set_temperature(self, temperature):
        """设置目标温度"""
        if not self.connect():
            return False, "设备连接失败"

        try:
            if self.protocol == "modbus_tcp":
                # 写入目标温度到寄存器 1
                value = int(temperature * 10)
                success = self._modbus_write_single_register(1, value)
                return success, "目标温度已更新" if success else "目标温度更新失败"

            return False, "不支持的协议"

        except Exception as e:
            return False, str(e)

        finally:
            self.disconnect()

    def set_mode(self, mode):
        """设置运行模式 (cool/heat/auto/fan/off)"""
        if not self.connect():
            return False, "设备连接失败"

        try:
            if self.protocol == "modbus_tcp":
                mode_value = self._encode_mode(mode)
                success = self._modbus_write_single_register(2, mode_value)
                return success, "运行模式已更新" if success else "运行模式更新失败"

            return False, "不支持的协议"

        except Exception as e:
            return False, str(e)

        finally:
            self.disconnect()

    def power_on(self):
        """开机"""
        return self._set_power(True)

    def power_off(self):
        """关机"""
        return self._set_power(False)

    def _set_power(self, on):
        """设置电源状态"""
        if not self.connect():
            return False, "设备连接失败"

        try:
            if self.protocol == "modbus_tcp":
                success = self._modbus_write_single_register(4, 1 if on else 0)
                return success, "电源状态已更新" if success else "电源状态更新失败"

            return False, "不支持的协议"

        except Exception as e:
            return False, str(e)

        finally:
            self.disconnect()

    # ==================== Modbus TCP 协议实现 ====================

    def _modbus_read_holding_registers(self, start_addr, count):
        """Modbus TCP 读保持寄存器 (功能码 0x03)"""
        # 构造 Modbus TCP 请求
        transaction_id = 1
        protocol_id = 0
        unit_id = self.station_id
        function_code = 0x03

        # MBAP Header (7 bytes) + PDU
        request = struct.pack('>HHHBB', transaction_id, protocol_id, 6, unit_id, function_code)
        request += struct.pack('>HH', start_addr, count)

        self.sock.sendall(request)
        response = self.sock.recv(1024)

        if len(response) < 9:
            return None

        # 解析响应
        byte_count = response[8]
        data = []
        for i in range(count):
            value = struct.unpack('>H', response[9 + i*2:11 + i*2])[0]
            data.append(value)

        return data

    def _modbus_write_single_register(self, addr, value):
        """Modbus TCP 写单个寄存器 (功能码 0x06)"""
        transaction_id = 1
        protocol_id = 0
        unit_id = self.station_id
        function_code = 0x06

        request = struct.pack('>HHHBB', transaction_id, protocol_id, 6, unit_id, function_code)
        request += struct.pack('>HH', addr, value)

        self.sock.sendall(request)
        response = self.sock.recv(1024)

        return len(response) >= 12

    # ==================== 辅助方法 ====================

    def _decode_mode(self, value):
        """解码运行模式"""
        modes = {0: "off", 1: "cool", 2: "heat", 3: "auto", 4: "fan"}
        return modes.get(value, "unknown")

    def _encode_mode(self, mode):
        """编码运行模式"""
        modes = {"off": 0, "cool": 1, "heat": 2, "auto": 3, "fan": 4}
        return modes.get(mode, 0)

    def _decode_fan_speed(self, value):
        """解码风速"""
        speeds = {0: "auto", 1: "low", 2: "mid", 3: "high"}
        return speeds.get(value, "auto")
