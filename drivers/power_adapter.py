# AI_MODULE: power_adapter
# AI_PURPOSE: 强电适配层 — 统一不同品牌电柜的 Modbus 通道映射。
# AI_BOUNDARY: 不直接通信；为 modbus_core 提供设备适配。
# AI_DATA_FLOW: CONFIG cabinet config -> channel map -> modbus_core relay control。
# AI_SEARCH_KEYWORDS: power, adapter, channel, relay, modbus.
# drivers/power_adapter.py

from .base import BaseDriver
import modbus_core as mc
from config import channel_map

class PowerCabinetDriver(BaseDriver):
    def __init__(self, config):
        super().__init__(config)
        # 对于配电柜，我们暂时通过配置里的 cab_idx 映射到现有的 mc.clients
        self.cab_idx = config.get("cab_idx")
        self.plc_type = config.get("plc_type", "AV-100")
        
    def connect(self):
        # 连接管理已由 modbus_core 内部接管
        return True
        
    def disconnect(self):
        pass

    def read_status(self):
        # 第一阶段，读状态的轮询暂时还留在 background.py
        # 统一读取接口将在第二阶段重构
        pass

    def control_channel(self, channel, is_open):
        # 复用 modbus_core 里久经考验的控制函数
        return mc.set_channel(self.cab_idx, channel, is_open)