# AI_MODULE: driver_base
# AI_PURPOSE: 设备驱动基类 — 定义所有设备驱动的统一接口。
# AI_BOUNDARY: 不实现具体协议；子类实现 connect/send/close。
# AI_DATA_FLOW: background pollers -> driver instance -> physical device。
# AI_SEARCH_KEYWORDS: driver, base, interface, abstract, device.
# drivers/base.py

class BaseDriver:
    def __init__(self, config):
        """
        初始化设备驱动
        :param config: 字典格式的设备配置 (包含 ip, port, slave_id, channels 等)
        """
        self.config = config
        self.is_online = False

    def connect(self):
        """建立连接"""
        raise NotImplementedError

    def disconnect(self):
        """断开连接"""
        raise NotImplementedError

    def read_status(self):
        """
        读取设备状态
        :return: dict 包含在线状态和通道数据，例如 {"online": True, "channels": [True, False, ...]}
        """
        raise NotImplementedError

    def control_channel(self, channel, is_open):
        """
        控制单个通道
        :param channel: 通道号 (1-N)
        :param is_open: True为开，False为关
        :return: bool 是否控制成功
        """
        raise NotImplementedError