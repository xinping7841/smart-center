# AI_MODULE: server_hardware_parsing_tests
# AI_PURPOSE: 固定服务器监控硬件解析规则，特别是 Linux DIMM 通道、CPU 核心/线程拓扑。
# AI_BOUNDARY: 单元测试只验证解析函数，不连接真实服务器、不触发任何设备或电源控制。
# AI_DATA_FLOW: mocked cpuinfo / synthetic DIMM labels -> linux_agent helpers -> expected monitor payload semantics.
# AI_SEARCH_KEYWORDS: server monitor test, DIMM_A1, quad channel, cpu cores, cpu threads.
import unittest
from unittest.mock import patch

from agent import linux_agent


class ServerHardwareParsingTest(unittest.TestCase):
    def test_linux_dimm_locator_channels_infer_quad_channel(self):
        labels = ["DIMM_A1 NODE 1", "DIMM_B1 NODE 1", "DIMM_C1 NODE 1", "DIMM_D1 NODE 1"]

        channels = []
        for label in labels:
            channel = linux_agent.infer_memory_channel_from_label(label)
            if channel and channel not in channels:
                channels.append(channel)

        self.assertEqual(channels, ["A", "B", "C", "D"])
        self.assertEqual(linux_agent.memory_channel_mode(len(channels), 4), "quad")

    def test_channel_a_across_two_controllers_remains_dual_on_windows_payloads(self):
        label_0 = "Controller0-ChannelA-DIMM0 BANK 0"
        label_1 = "Controller1-ChannelA-DIMM0 BANK 0"

        self.assertEqual(linux_agent.infer_memory_channel_from_label(label_0), "A")
        self.assertEqual(linux_agent.infer_memory_channel_from_label(label_1), "A")

    def test_linux_cpu_topology_counts_cores_and_threads(self):
        cpuinfo = """
processor   : 0
physical id : 0
core id     : 0

processor   : 1
physical id : 0
core id     : 0

processor   : 2
physical id : 0
core id     : 1

processor   : 3
physical id : 0
core id     : 1
"""
        with patch.object(linux_agent, "read_text", return_value=cpuinfo):
            topology = linux_agent.read_cpu_topology()

        self.assertEqual(topology["core_count"], 2)
        self.assertEqual(topology["thread_count"], 4)
        self.assertEqual(topology["socket_count"], 1)


if __name__ == "__main__":
    unittest.main()
