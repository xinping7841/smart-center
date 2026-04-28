#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
视美乐 ID 替换测试工具
"""

def test_id_replacement():
    """测试 ID 替换逻辑"""
    print("\n" + "="*70)
    print("🔍 视美乐设备 ID 替换测试")
    print("="*70)
    
    # 测试数据
    test_cases = [
        {"device_id": 30, "cmd": "开机", "hex": "23 50 57 52 30 2C 30 31", "expected": "#PWR30,01"},
        {"device_id": 1, "cmd": "开机", "hex": "23 50 57 52 30 2C 30 31", "expected": "#PWR1,01"},
        {"device_id": 99, "cmd": "开机", "hex": "23 50 57 52 30 2C 30 31", "expected": "#PWR99,01"},
        {"device_id": 30, "cmd": "关机", "hex": "23 50 57 52 30 2C 30 30", "expected": "#PWR30,00"},
        {"device_id": 30, "cmd": "HDMI1", "hex": "23 53 4F 55 52 30 2C 31 37", "expected": "#SOUR30,17"},
    ]
    
    for case in test_cases:
        device_id = case["device_id"]
        hex_payload = case["hex"]
        
        print(f"\n[测试] {case['cmd']} (设备 ID={device_id})")
        print(f"原始 16 进制：{hex_payload}")
        
        # 模拟 ID 替换逻辑
        try:
            payload_bytes = bytes.fromhex(hex_payload.replace(" ", ""))
            id_str = str(device_id)
            new_payload = bytearray(payload_bytes)
            
            # 找到逗号前的数字位置并替换
            for i in range(len(new_payload)):
                if new_payload[i:i+1] == b',':
                    # 逗号前的字节是 ID，替换
                    if i > 0:
                        new_payload[i-1:i] = id_str.encode('utf-8')
                    break
            
            result_hex = new_payload.hex(' ').upper()
            result_str = new_payload.decode('utf-8', errors='ignore')
            
            print(f"替换后 16 进制：{result_hex}")
            print(f"替换后字符串：{result_str}")
            print(f"期望结果：{case['expected']}")
            
            if result_str == case['expected']:
                print("✅ 测试通过")
            else:
                print("❌ 测试失败")
                
        except Exception as e:
            print(f"❌ 发生错误：{str(e)}")
    
    print(f"\n{'='*70}")
    print("测试完成")
    print("="*70)
    print(f"\n💡 说明:")
    print(f"   1. 设备 ID 可以在配置页面设置 (默认 30)")
    print(f"   2. 指令中的 ID 会自动替换为配置的值")
    print(f"   3. 例如：设备 ID=1 时，开机指令变为 #PWR1,01")
    print()

if __name__ == "__main__":
    test_id_replacement()
