#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
光峰 DH 系列投影机测试工具
测试投影机控制命令和状态查询
"""

import json
import time
from projector_core import ProjectorDriver

def test_projector_commands():
    """测试光峰 DH 系列投影机命令"""
    print("\n" + "="*80)
    print("🧪 光峰 DH 系列投影机测试工具")
    print("="*80)
    
    # 读取配置
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"\n❌ 读取配置文件失败：{e}")
        return
    
    # 查找光峰 DH 系列投影机
    dh_projectors = []
    for proj in config.get('projectors', []):
        if proj.get('brand_id') == 'appotronics_dh':
            dh_projectors.append(proj)
    
    if not dh_projectors:
        print("\n⚠️  未找到光峰 DH 系列投影机配置")
        print("\n💡 提示：请在系统配置中添加光峰 DH 系列投影机")
        return
    
    print(f"\n✅ 找到 {len(dh_projectors)} 台光峰 DH 系列投影机")
    print("-" * 80)
    
    for i, proj in enumerate(dh_projectors, 1):
        print(f"\n🎥 投影机 {i}: {proj.get('name', proj['id'])}")
        print(f"   品牌：{proj.get('brand_id')}")
        print(f"   控制类型：{proj.get('control_type')}")
        print(f"   地址：{proj.get('host', '')}:{proj.get('port', '')}")
        print("-" * 80)
        
        try:
            driver = ProjectorDriver(proj)
            
            # 测试基本命令
            print("\n📋 测试基本命令:")
            
            # 1. 测试开机命令
            print("\n   1️⃣  测试开机命令...")
            cmd_power_on = next((c for c in proj.get('commands', []) if c['id'] == 'power_on'), None)
            if cmd_power_on:
                payload = cmd_power_on.get('payload_hex', '')
                success, res = driver.execute({'payload': payload, 'format': 'hex'})
                print(f"      结果：{'✅ 成功' if success else '❌ 失败'}")
                if res:
                    print(f"      响应：{res}")
                time.sleep(0.5)
            
            # 2. 测试关机命令
            print("\n   2️⃣  测试关机命令...")
            cmd_power_off = next((c for c in proj.get('commands', []) if c['id'] == 'power_off'), None)
            if cmd_power_off:
                payload = cmd_power_off.get('payload_hex', '')
                success, res = driver.execute({'payload': payload, 'format': 'hex'})
                print(f"      结果：{'✅ 成功' if success else '❌ 失败'}")
                if res:
                    print(f"      响应：{res}")
                time.sleep(0.5)
            
            # 3. 测试信号源切换
            print("\n   3️⃣  测试 HDMI1 信号源...")
            cmd_hdmi1 = next((c for c in proj.get('commands', []) if c['id'] == 'source_hdmi1'), None)
            if cmd_hdmi1:
                payload = cmd_hdmi1.get('payload_hex', '')
                success, res = driver.execute({'payload': payload, 'format': 'hex'})
                print(f"      结果：{'✅ 成功' if success else '❌ 失败'}")
                if res:
                    print(f"      响应：{res}")
                time.sleep(0.5)
            
            # 4. 查询状态
            print("\n   4️⃣  查询投影机状态...")
            try:
                status = driver.get_status()
                print(f"      在线状态：{'✅ 在线' if status.get('online') else '❌ 离线'}")
                print(f"      电源状态：{status.get('power', 'unknown')}")
                if status.get('temp') is not None:
                    print(f"      温度：{status['temp']}℃")
                if status.get('lamp_hours') is not None:
                    print(f"      灯泡时长：{status['lamp_hours']} 小时")
                if status.get('source'):
                    print(f"      信号源：{status['source']}")
            except Exception as e:
                print(f"      ❌ 查询失败：{str(e)}")
            
        except Exception as e:
            print(f"\n❌ 连接失败：{str(e)}")
        
        print("-" * 80)
    
    print("\n" + "="*80)
    print("✅ 测试完成")
    print("="*80 + "\n")

def show_command_reference():
    """显示命令参考表"""
    print("\n" + "="*80)
    print("📖 光峰 DH 系列命令参考")
    print("="*80)
    
    commands = {
        "电源控制": [
            ("开机", "AA 01 01 01 00 00 00 03"),
            ("关机", "AA 01 01 01 00 00 00 02"),
        ],
        "信号源切换": [
            ("HDMI1", "AA 01 02 01 00 00 00 11"),
            ("HDMI2", "AA 01 02 01 00 00 00 12"),
            ("DVI", "AA 01 02 01 00 00 00 02"),
            ("VGA", "AA 01 02 01 00 00 00 01"),
            ("DP", "AA 01 02 01 00 00 00 03"),
        ],
        "状态查询": [
            ("查询电源", "AA 01 01 02 00 00 00 04"),
            ("查询温度", "AA 01 03 02 00 00 00 06"),
            ("查询灯泡时长", "AA 01 04 02 00 00 00 08"),
        ]
    }
    
    for category, cmds in commands.items():
        print(f"\n{category}:")
        print("-" * 80)
        for name, hex_cmd in cmds:
            print(f"   {name:15} : {hex_cmd}")
    
    print("\n" + "="*80)
    print("💡 提示：所有命令均为 16 进制格式，帧头为 AA")
    print("="*80 + "\n")

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--ref':
        show_command_reference()
    else:
        test_projector_commands()
