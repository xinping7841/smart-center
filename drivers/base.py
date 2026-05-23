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