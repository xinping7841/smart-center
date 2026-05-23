"""
光峰 DH 系列投影机测试脚本
测试目标: 192.168.50.110:9761
"""
import sys
sys.path.insert(0, 'd:/IDE/smart_power_monitor_324 _VS_1')

from projector_core import ProjectorDriver

# 光峰 DH 投影机配置
projector_config = {
    "id": "test_appotronics_dh",
    "name": "光峰DH测试机",
    "brand_id": "appotronics_dh",
    "control_type": "appotronics_dh_tcp",
    "ip": "192.168.50.110",
    "port": 9761
}

print("\n" + "="*70)
print("光峰 DH 系列投影机集成测试")
print("="*70)
print(f"测试目标: {projector_config['ip']}:{projector_config['port']}")
print(f"投影机名称: {projector_config['name']}")
print("="*70 + "\n")

# 创建驱动实例
driver = ProjectorDriver(projector_config)

# 测试命令列表
test_commands = [
    {
        "name": "关机",
        "payload": "EB 90 00 0C 00 00 08 01 00 01 00 91",
        "format": "hex"
    }
]

# 执行测试
for i, cmd in enumerate(test_commands, 1):
    print(f"\n{'#'*70}")
    print(f"测试 {i}/{len(test_commands)}: {cmd['name']}")
    print(f"{'#'*70}")

    success, result = driver.execute(cmd)

    print(f"\n执行结果:")
    print(f"  状态: {'[OK] 成功' if success else '[FAIL] 失败'}")
    print(f"  返回: {result}")

    if i < len(test_commands):
        import time
        print(f"\n等待 2 秒后执行下一条指令...")
        time.sleep(2)

print(f"\n{'='*70}")
print("测试完成")
print("="*70 + "\n")
