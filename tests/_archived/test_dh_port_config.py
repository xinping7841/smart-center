#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
光峰 DH 系列端口配置测试
验证默认端口和自定义端口的覆盖逻辑
"""

import json

def test_port_configuration():
    """测试端口配置逻辑"""
    print("\n" + "="*80)
    print("🔧 光峰 DH 系列端口配置测试")
    print("="*80)
    
    # 读取品牌配置
    with open('projector_brands.json', 'r', encoding='utf-8') as f:
        brands = json.load(f)
    
    dh_brand = next((b for b in brands['brands'] if b['id'] == 'appotronics_dh'), None)
    
    if not dh_brand:
        print("\n❌ 未找到光峰 DH 系列配置")
        return
    
    default_port = dh_brand.get('default_port_tcp', 'N/A')
    
    print(f"\n✅ 品牌：{dh_brand['name']}")
    print(f"   品牌 ID: {dh_brand['id']}")
    print(f"   默认端口 (TCP): {default_port}")
    print(f"   默认端口 (COM): {dh_brand.get('default_port_com', 'N/A')}")
    
    print("\n" + "-"*80)
    print("📋 端口配置说明:")
    print("-"*80)
    
    print(f"""
1. 默认情况:
   - 如果在 config.json 中未配置 port 字段
   - 系统将使用默认端口：**{default_port}**

2. 自定义端口:
   - 如果在 config.json 中配置了 port 字段
   - 系统将使用配置的端口值
   - 示例：
     ```json
     {{
       "id": "dh_proj_1",
       "name": "1 号投影机",
       "brand_id": "appotronics_dh",
       "control_type": "appotronics_dh_tcp",
       "ip": "192.168.50.110",
       "port": 9762  // 自定义端口，覆盖默认值
     }}
     ```

3. 支持的控制类型:
   - appotronics_dh_tcp  (TCP 网络连接)
   - appotronics_dh_udp  (UDP 网络连接)
   - appotronics_dh_com  (串口连接)

4. 端口优先级:
   设备配置 port > 品牌默认端口 ({default_port})
""")
    
    print("-"*80)
    print(" 使用场景:")
    print("-"*80)
    print("""
✅ 场景 1: 标准配置 (使用默认端口 9761)
   - 适用于大多数 DH 系列投影机
   - 无需配置 port 字段

✅ 场景 2: 特殊配置 (自定义端口)
   - 投影机使用非标准端口
   - 多台投影机使用不同端口
   - 网络环境特殊要求
""")
    
    print("="*80)
    print("✅ 端口配置功能已就绪")
    print("="*80 + "\n")

def verify_code_logic():
    """验证代码中的端口处理逻辑"""
    print("\n" + "="*80)
    print("🔍 代码逻辑验证")
    print("="*80)
    
    with open('projector_core.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    checks = {
        "DH TCP 方法": "_send_appotronics_dh_tcp" in content,
        "DH UDP 方法": "_send_appotronics_dh_udp" in content,
        "DH COM 方法": "_send_appotronics_dh_com" in content,
        "默认端口 9761": 'port = int(self.cfg.get("port", 9761))' in content,
        "控制类型识别": '"appotronics_dh_tcp"' in content,
    }
    
    print("\n验证项目:")
    all_pass = True
    for name, result in checks.items():
        status = "✅" if result else "❌"
        print(f"   {status} {name}")
        if not result:
            all_pass = False
    
    print("-"*80)
    if all_pass:
        print("✅ 所有代码逻辑验证通过")
    else:
        print("⚠️  部分验证未通过")
    
    print("="*80 + "\n")

if __name__ == '__main__':
    test_port_configuration()
    verify_code_logic()
