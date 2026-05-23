#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
光峰 DH 系列品牌和连接类型验证
验证品牌、型号和连接类型的区分
"""

import json

def verify_brand_structure():
    """验证品牌配置结构"""
    print("\n" + "="*80)
    print("🔍 光峰 DH 系列品牌结构验证")
    print("="*80)
    
    with open('projector_brands.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    dh_brand = None
    for brand in data['brands']:
        if brand['id'] == 'appotronics_dh':
            dh_brand = brand
            break
    
    if not dh_brand:
        print("\n❌ 未找到光峰 DH 系列配置")
        return
    
    print(f"\n✅ 品牌信息:")
    print(f"   品牌 ID: {dh_brand['id']}")
    print(f"   品牌名称：{dh_brand['name']}")
    print(f"   品牌标识：{dh_brand.get('brand', 'N/A')}")
    print(f"   系列标识：{dh_brand.get('series', 'N/A')}")
    print(f"   显示名称：{dh_brand.get('display_name', 'N/A')}")
    
    print(f"\n✅ 连接类型:")
    conn_types = dh_brand.get('connection_types', {})
    
    for conn_key, conn_info in conn_types.items():
        icon = conn_info.get('icon', '📡')
        name = conn_info.get('name', conn_key)
        port = conn_info.get('default_port', 'N/A')
        type_id = conn_info.get('id', 'N/A')
        
        print(f"\n   {icon} {name}")
        print(f"      类型 ID: {type_id}")
        print(f"      默认端口：{port}")
    
    print("\n" + "-"*80)
    print("📋 配置说明:")
    print("-"*80)
    print("""
1. 品牌区分:
   - brand: 品牌标识 (appotronics = 光峰)
   - series: 系列标识 (dh = DH 系列)
   - display_name: 显示名称 (光峰 DH 系列)

2. 连接类型区分:
   - tcp: 网络接入 (TCP) - 使用端口 9761
   - udp: 网络接入 (UDP) - 使用端口 9761
   - com: 串口接入 (RS232) - 使用波特率 9600

3. 使用方式:
   - 选择品牌：光峰 DH 系列
   - 选择连接类型：网络接入 (TCP) / 网络接入 (UDP) / 串口接入 (RS232)
   - 系统自动配置默认端口
   - 支持自定义端口覆盖
""")
    
    print("-"*80)
    print("✅ 验证项目:")
    print("-"*80)
    
    checks = {
        "品牌字段存在": 'brand' in dh_brand,
        "系列字段存在": 'series' in dh_brand,
        "显示名称存在": 'display_name' in dh_brand,
        "连接类型配置": 'connection_types' in dh_brand,
        "TCP 连接类型": 'tcp' in conn_types,
        "UDP 连接类型": 'udp' in conn_types,
        "串口连接类型": 'com' in conn_types,
        "TCP 端口正确": conn_types.get('tcp', {}).get('default_port') == 9761,
        "串口端口正确": conn_types.get('com', {}).get('default_port') == 9600,
    }
    
    all_pass = True
    for name, result in checks.items():
        status = "✅" if result else "❌"
        print(f"   {status} {name}")
        if not result:
            all_pass = False
    
    print("-"*80)
    if all_pass:
        print("✅ 所有验证通过 - 品牌和连接类型已正确区分")
    else:
        print("⚠️  部分验证未通过")
    
    print("="*80 + "\n")

def test_api_response():
    """测试 API 响应格式"""
    print("="*80)
    print("🌐 API 响应测试")
    print("="*80)
    
    try:
        from projector_core import get_brand_info, get_connection_types, get_connection_type_name
        
        brand_id = "appotronics_dh"
        
        print(f"\n测试品牌：{brand_id}")
        
        brand_info = get_brand_info(brand_id)
        print(f"\n品牌信息:")
        print(f"  名称：{brand_info.get('name', 'N/A')}")
        print(f"  显示名称：{brand_info.get('display_name', 'N/A')}")
        print(f"  品牌：{brand_info.get('brand', 'N/A')}")
        print(f"  系列：{brand_info.get('series', 'N/A')}")
        
        print(f"\n连接类型:")
        conn_types = get_connection_types(brand_id)
        for key, info in conn_types.items():
            print(f"  {info.get('icon', '📡')} {info.get('name', key)} ({info.get('id', 'N/A')})")
        
        print(f"\n连接类型名称测试:")
        for conn_type_id in ["appotronics_dh_tcp", "appotronics_dh_com"]:
            name = get_connection_type_name(brand_id, conn_type_id)
            print(f"  {conn_type_id} -> {name}")
        
        print("\n✅ API 函数测试通过")
        
    except Exception as e:
        print(f"\n❌ API 测试失败：{str(e)}")
    
    print("="*80 + "\n")

if __name__ == '__main__':
    verify_brand_structure()
    test_api_response()
    print("\n✅ 所有测试完成!\n")
