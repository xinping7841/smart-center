#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
视美乐投影机 - 完整指令验证工具
验证所有指令的 16 进制和字符串格式
"""
import json

def decode_hex(hex_str):
    """解码 16 进制为字符串"""
    return bytes.fromhex(hex_str.replace(' ', '')).decode('utf-8', errors='ignore')

def main():
    print("\n" + "="*80)
    print("📋 视美乐 EK 系列指令验证")
    print("="*80)
    
    # 读取配置文件
    with open('projector_brands.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 找到视美乐品牌
    smile_brand = None
    for brand in data['brands']:
        if brand['id'] == 'smile_ek':
            smile_brand = brand
            break
    
    if not smile_brand:
        print("❌ 未找到视美乐 EK 系列配置")
        return
    
    print(f"\n品牌：{smile_brand['name']}")
    print(f"默认 ID: {smile_brand.get('default_id', 30)}")
    print(f"指令数量：{len(smile_brand['commands'])}")
    
    # 验证每个指令
    print(f"\n{'='*80}")
    print("指令列表验证:")
    print(f"{'='*80}")
    
    commands = sorted(smile_brand['commands'], key=lambda x: x.get('sort', 99))
    
    for cmd in commands:
        cmd_id = cmd['id']
        cmd_name = cmd['name']
        icon = cmd.get('icon', '')
        payload_str = cmd.get('payload_str', '')
        payload_hex = cmd.get('payload_hex', '')
        show_on_home = cmd.get('show_on_home', False)
        sort = cmd.get('sort', 99)
        
        # 验证字符串和 16 进制是否匹配
        decoded = decode_hex(payload_hex) if payload_hex else ""
        
        # 检查是否以 ! 或 ? 结尾
        ends_with = ""
        if payload_str.endswith('!'):
            ends_with = "✅ 控制指令 (!)"
        elif payload_str.endswith('?'):
            ends_with = "📊 查询指令 (?)"
        else:
            ends_with = "⚠️  格式异常"
        
        # 验证匹配
        match_status = ""
        if decoded == payload_str:
            match_status = "✅ 匹配"
        else:
            match_status = f"❌ 不匹配 (解码:{decoded})"
        
        # 显示主页状态
        home_status = "🏠 主页" if show_on_home else ""
        
        print(f"\n{icon} {cmd_name} ({cmd_id}) - 排序:{sort} {home_status}")
        print(f"   字符串：{payload_str}")
        print(f"   16 进制：{payload_hex}")
        print(f"   格式：{ends_with}")
        print(f"   验证：{match_status}")
    
    print(f"\n{'='*80}")
    print("💡 指令格式说明:")
    print(f"{'='*80}")
    print("   1. 控制指令格式：#CMD{ID},{param}!  (以 ! 结尾)")
    print("   2. 查询指令格式：#CMD{ID},?      (以 ? 结尾)")
    print("   3. 设备 ID 可配置，默认 30")
    print("   4. 所有指令都支持 ID 自动替换")
    print()
    
    # 统计
    control_cmds = [c for c in commands if c.get('payload_str', '').endswith('!')]
    query_cmds = [c for c in commands if c.get('payload_str', '').endswith('?')]
    home_cmds = [c for c in commands if c.get('show_on_home', False)]
    
    print(f"{'='*80}")
    print("📊 统计信息:")
    print(f"{'='*80}")
    print(f"   总指令数：{len(commands)}")
    print(f"   控制指令：{len(control_cmds)} 个 (带 !)")
    print(f"   查询指令：{len(query_cmds)} 个 (带 ?)")
    print(f"   主页显示：{len(home_cmds)} 个")
    print()

if __name__ == "__main__":
    main()
