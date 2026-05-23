#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
视美乐投影机 - 新指令格式测试
测试带感叹号的指令格式和 ID 替换
"""

def decode_hex(hex_str):
    """解码 16 进制为字符串"""
    return bytes.fromhex(hex_str.replace(' ', '')).decode('utf-8', errors='ignore')

def test_new_format():
    """测试新指令格式"""
    print("\n" + "="*70)
    print("🔍 视美乐新指令格式测试 (带感叹号)")
    print("="*70)
    
    # 测试数据
    test_cases = [
        {"cmd": "开机", "hex": "23 50 57 52 30 2C 31 21", "expected": "#PWR0,1!"},
        {"cmd": "关机", "hex": "23 50 57 52 30 2C 30 21", "expected": "#PWR0,0!"},
    ]
    
    for case in test_cases:
        hex_payload = case["hex"]
        str_result = decode_hex(hex_payload)
        
        print(f"\n[测试] {case['cmd']}")
        print(f"16 进制：{hex_payload}")
        print(f"字符串：{str_result}")
        print(f"期望：{case['expected']}")
        
        if str_result == case['expected']:
            print("✅ 格式正确")
        else:
            print("❌ 格式错误")
    
    print(f"\n{'='*70}")
    print("ID 替换测试")
    print("="*70)
    
    # ID 替换测试
    base_hex = "23 50 57 52 30 2C 31 21"  # #PWR0,1!
    test_ids = [1, 30, 99]
    
    for device_id in test_ids:
        print(f"\n[设备 ID={device_id}]")
        print(f"原始：{base_hex} -> {decode_hex(base_hex)}")
        
        # 模拟 ID 替换
        try:
            payload_bytes = bytes.fromhex(base_hex.replace(" ", ""))
            id_str = str(device_id)
            new_payload = bytearray(payload_bytes)
            
            # 找到逗号前的数字位置并替换
            for i in range(len(new_payload)):
                if new_payload[i:i+1] == b',':
                    if i > 0:
                        new_payload[i-1:i] = id_str.encode('utf-8')
                    break
            
            result_hex = new_payload.hex(' ').upper()
            result_str = new_payload.decode('utf-8', errors='ignore')
            
            print(f"替换后：{result_hex} -> {result_str}")
            print(f"✅ ID 替换成功")
            
        except Exception as e:
            print(f"❌ ID 替换失败：{str(e)}")
    
    print(f"\n{'='*70}")
    print("💡 说明:")
    print("   1. 指令格式：#PWR{ID},{命令}!")
    print("   2. 感叹号 (!) 表示立即执行")
    print("   3. 开机：#PWR0,1! (16 进制：23 50 57 52 30 2C 31 21)")
    print("   4. 关机：#PWR0,0! (16 进制：23 50 57 52 30 2C 30 21)")
    print("   5. 设备 ID 可配置，自动替换")
    print()

if __name__ == "__main__":
    test_new_format()
