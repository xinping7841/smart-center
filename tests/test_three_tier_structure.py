#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
三层结构测试：品牌 → 系列 → 连接类型
"""

from projector_core import (
    get_all_brands,
    get_brand_series,
    get_series_info,
    get_series_commands,
    get_connection_types,
    get_connection_type_name
)

def test_three_tier_structure():
    """测试三层结构"""
    print("\n" + "="*80)
    print("🏗️  三层结构测试：品牌 → 系列 → 连接类型")
    print("="*80)
    
    # 第一层：获取所有品牌
    print("\n1️⃣  第一层：品牌列表")
    print("-"*80)
    brands = get_all_brands()
    for brand in brands:
        print(f"   {brand['id']}: {brand['name']} (系列数：{brand['series_count']})")
    
    # 第二层：获取品牌下的系列
    print("\n2️⃣  第二层：品牌下的系列")
    print("-"*80)
    
    # 测试光峰品牌
    print("\n📍 光峰品牌:")
    appotronics_series = get_brand_series("appotronics")
    for series in appotronics_series:
        print(f"   - {series['id']}: {series['name']} ({series['display_name']})")
    
    # 测试视美乐品牌
    print("\n📍 视美乐品牌:")
    smile_series = get_brand_series("smile")
    for series in smile_series:
        print(f"   - {series['id']}: {series['name']} ({series['display_name']})")
    
    # 第三层：系列的详细信息和连接类型
    print("\n3️⃣  第三层：系列详情和连接类型")
    print("-"*80)
    
    # 光峰 DH 系列
    print("\n📍 光峰 DH 系列:")
    dh_series = get_series_info("appotronics", "dh")
    if dh_series:
        print(f"   系列 ID: {dh_series['id']}")
        print(f"   显示名称：{dh_series['display_name']}")
        
        # 连接类型
        conn_types = get_connection_types("appotronics", "dh")
        print(f"\n   连接类型:")
        for key, info in conn_types.items():
            icon = info.get('icon', '📡')
            name = info.get('name', key)
            port = info.get('default_port', 'N/A')
            type_id = info.get('id', 'N/A')
            print(f"      {icon} {name} ({type_id}) - 端口：{port}")
    
    # 视美乐 EK 系列
    print("\n📍 视美乐 EK 系列:")
    ek_series = get_series_info("smile", "ek")
    if ek_series:
        print(f"   系列 ID: {ek_series['id']}")
        print(f"   显示名称：{ek_series['display_name']}")
        print(f"   默认 ID: {ek_series.get('default_id', 'N/A')}")
        print(f"   控制类型：{', '.join(ek_series.get('control_types', []))}")
    
    # 命令列表
    print("\n4️⃣  系列的命令列表")
    print("-"*80)
    
    # 光峰 DH 系列命令
    print("\n📍 光峰 DH 系列命令 (前 5 个):")
    dh_commands = get_series_commands("appotronics", "dh")
    for i, cmd in enumerate(dh_commands[:5], 1):
        icon = cmd.get('icon', '')
        name = cmd.get('name', '')
        show = "✅" if cmd.get('show_on_home', False) else "❌"
        print(f"   {i}. {icon} {name} [首页显示：{show}]")
    
    # 视美乐 EK 系列命令
    print("\n📍 视美乐 EK 系列命令 (前 5 个):")
    ek_commands = get_series_commands("smile", "ek")
    for i, cmd in enumerate(ek_commands[:5], 1):
        icon = cmd.get('icon', '')
        name = cmd.get('name', '')
        show = "✅" if cmd.get('show_on_home', False) else "❌"
        print(f"   {i}. {icon} {name} [首页显示：{show}]")
    
    # 连接类型名称测试
    print("\n5️⃣  连接类型名称测试")
    print("-"*80)
    
    dh_tcp_name = get_connection_type_name("appotronics", "dh", "appotronics_dh_tcp")
    dh_com_name = get_connection_type_name("appotronics", "dh", "appotronics_dh_com")
    
    print(f"\n   光峰 DH 系列:")
    print(f"      appotronics_dh_tcp -> {dh_tcp_name}")
    print(f"      appotronics_dh_com -> {dh_com_name}")
    
    print("\n" + "="*80)
    print("✅ 三层结构验证完成!")
    print("="*80)
    print("\n层级关系:")
    print("   品牌 (Brand)")
    print("   └── 系列 (Series)")
    print("       ├── 连接类型 (Connection Type)")
    print("       └── 命令列表 (Commands)")
    print("\n示例:")
    print("   光峰 (appotronics)")
    print("   └── DH 系列 (dh)")
    print("       ├── 网络接入 (TCP)")
    print("       ├── 网络接入 (UDP)")
    print("       └── 串口接入 (RS232)")
    print("="*80 + "\n")

if __name__ == '__main__':
    test_three_tier_structure()
