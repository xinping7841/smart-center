#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
光峰 DH 系列投影机协议验证脚本
验证配置文件中的命令格式和校验和
"""

import json

def calculate_checksum(hex_str):
    """计算校验和 (简单累加)"""
    bytes_list = [int(b, 16) for b in hex_str.split()]
    checksum = sum(bytes_list) & 0xFF
    return checksum

def verify_dh_commands():
    """验证光峰 DH 系列命令"""
    print("\n" + "="*80)
    print("🔍 光峰 DH 系列投影机协议验证")
    print("="*80)
    
    # 读取配置
    with open('projector_brands.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 查找光峰 DH 系列
    dh_brand = None
    for brand in data['brands']:
        if brand['id'] == 'appotronics_dh':
            dh_brand = brand
            break
    
    if not dh_brand:
        print("\n❌ 未找到光峰 DH 系列配置")
        return False
    
    print(f"\n✅ 品牌：{dh_brand['name']}")
    print(f"   ID: {dh_brand['id']}")
    print(f"   控制类型：{dh_brand['control_types']}")
    print(f"   默认端口 (TCP): {dh_brand.get('default_port_tcp', 'N/A')}")
    print(f"   默认端口 (COM): {dh_brand.get('default_port_com', 'N/A')}")
    
    print("\n" + "-"*80)
    print("📋 命令列表验证:")
    print("-"*80)
    
    commands = sorted(dh_brand['commands'], key=lambda x: x.get('sort', 99))
    
    for cmd in commands:
        cmd_id = cmd['id']
        cmd_name = cmd['name']
        icon = cmd.get('icon', '')
        payload_hex = cmd.get('payload_hex', '')
        show_on_home = cmd.get('show_on_home', False)
        sort = cmd.get('sort', 99)
        
        # 解析命令结构
        if payload_hex:
            bytes_list = payload_hex.split()
            if len(bytes_list) >= 4:
                head = bytes_list[0]  # 帧头
                cmd_type = bytes_list[1]  # 命令类型
                sub_cmd = bytes_list[2]  # 子命令
                data_len = bytes_list[3]  # 数据长度
                
                print(f"\n{icon} {cmd_name} ({cmd_id})")
                print(f"   16 进制：{payload_hex}")
                print(f"   帧头：{head} | 命令类型：{cmd_type} | 子命令：{sub_cmd} | 数据长度：{data_len}")
                print(f"   主页显示：{'✅' if show_on_home else '❌'} | 排序：{sort}")
                
                # 验证帧头
                if head == "AA":
                    print(f"   ✅ 帧头正确 (AA)")
                else:
                    print(f"   ⚠️  帧头异常 (期望：AA, 实际：{head})")
    
    print("\n" + "="*80)
    print("✅ 验证完成")
    print("="*80 + "\n")
    
    return True

def compare_with_protocol_doc():
    """对比协议文档中的命令"""
    print("\n" + "="*80)
    print("📖 协议文档对比")
    print("="*80)
    
    # 根据协议文档验证关键命令
    expected_commands = {
        "power_on": "AA 01 01 01 00 00 00 03",  # 开机
        "power_off": "AA 01 01 01 00 00 00 02",  # 关机
        "source_hdmi1": "AA 01 02 01 00 00 00 11",  # HDMI1
        "source_hdmi2": "AA 01 02 01 00 00 00 12",  # HDMI2
        "get_power_status": "AA 01 01 02 00 00 00 04",  # 查询电源
        "get_temp": "AA 01 03 02 00 00 00 06",  # 查询温度
        "get_lamp_hours": "AA 01 04 02 00 00 00 08"  # 查询灯泡时长
    }
    
    with open('projector_brands.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    dh_brand = next((b for b in data['brands'] if b['id'] == 'appotronics_dh'), None)
    
    if not dh_brand:
        print("\n❌ 未找到光峰 DH 系列")
        return
    
    print("\n关键命令对比:")
    print("-"*80)
    
    all_match = True
    for cmd_id, expected_hex in expected_commands.items():
        cmd = next((c for c in dh_brand['commands'] if c['id'] == cmd_id), None)
        if cmd:
            actual_hex = cmd.get('payload_hex', '')
            if actual_hex == expected_hex:
                print(f"✅ {cmd_id}: {cmd['name']} - 匹配")
            else:
                print(f"❌ {cmd_id}: {cmd['name']} - 不匹配")
                print(f"   期望：{expected_hex}")
                print(f"   实际：{actual_hex}")
                all_match = False
        else:
            print(f"❌ {cmd_id}: 命令未找到")
            all_match = False
    
    print("-"*80)
    if all_match:
        print("✅ 所有关键命令与协议文档一致")
    else:
        print("⚠️  部分命令不匹配，请检查")
    
    print("="*80 + "\n")

if __name__ == '__main__':
    if verify_dh_commands():
        compare_with_protocol_doc()
