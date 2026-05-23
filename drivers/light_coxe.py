# drivers/light_coxe.py

import threading
import modbus_tk.modbus_tcp as modbus_tcp
import modbus_tk.defines as cst
from .base import BaseDriver

class CoxeLightDriver(BaseDriver):
    def __init__(self, config):
        super().__init__(config)
        self.client = None
        self.dev_lock = threading.Lock()
        self.connect()

    def connect(self):
        try:
            if self.client:
                self.client.close()
            self.client = modbus_tcp.TcpMaster(
                host=self.config["ip"],
                port=self.config["port"],
                timeout_in_sec=2.0
            )
            self.is_online = True
            return True
        except Exception:
            self.is_online = False
            self.client = None
            return False

    def disconnect(self):
        if self.client:
            try:
                self.client.close()
            except:
                pass
            self.client = None
        self.is_online = False

    def read_status(self):
        with self.dev_lock:
            channels_count = self.config.get("channels", 4)
            read_mode = self.config.get("status_read_mode", "coil")
            start_addr = int(self.config.get("status_start_address", 0))
            if not self.client and not self.connect():
                return {"online": False, "channels": [None] * channels_count}
            
            try:
                if read_mode == "holding":
                    status = self.client.execute(
                        slave=self.config.get("slave_id", 1),
                        function_code=cst.READ_HOLDING_REGISTERS,
                        starting_address=start_addr,
                        quantity_of_x=channels_count
                    )
                    status = [bool(v) for v in list(status)]
                elif read_mode == "discrete":
                    status = self.client.execute(
                        slave=self.config.get("slave_id", 1),
                        function_code=cst.READ_DISCRETE_INPUTS,
                        starting_address=start_addr,
                        quantity_of_x=channels_count
                    )
                    status = list(status)
                elif read_mode == "input":
                    status = self.client.execute(
                        slave=self.config.get("slave_id", 1),
                        function_code=cst.READ_INPUT_REGISTERS,
                        starting_address=start_addr,
                        quantity_of_x=channels_count
                    )
                    status = [bool(v) for v in list(status)]
                else:
                    status = self.client.execute(
                        slave=self.config.get("slave_id", 1),
                        function_code=cst.READ_COILS,
                        starting_address=start_addr,
                        quantity_of_x=channels_count
                    )
                    status = list(status)
                self.is_online = True
                return {"online": True, "channels": list(status)}
            except Exception:
                self.is_online = False
                self.client = None
                return {"online": False, "channels": [None] * channels_count}

    def control_channel(self, channel, is_open):
        with self.dev_lock:
            write_start_addr = int(self.config.get("write_start_address", 0))
            if not self.client and not self.connect():
                return False
            
            try:
                # 寄存器地址通常是通道号减1
                reg_addr = write_start_addr + channel - 1
                self.client.execute(
                    slave=self.config.get("slave_id", 1),
                    function_code=cst.WRITE_SINGLE_COIL,
                    starting_address=reg_addr,
                    output_value=is_open
                )
                return True
            except Exception:
                self.client = None
                return False
