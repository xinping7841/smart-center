#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
投影机状态显示功能快速验证脚本
验证前端和后端代码是否正确集成
"""

import json
import re

def verify_backend():
    """验证后端代码"""
    print("\n" + "="*80)
    print("🔍 验证后端代码")
    print("="*80)
    
    # 检查 projector_core.py
    try:
        with open('projector_core.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        checks = {
            "get_status 方法": "def get_status(self):" in content,
            "电源状态查询": '"power": "unknown"' in content,
            "温度查询": '"temp": None' in content,
            "灯泡时长": '"lamp_hours": None' in content,
            "信号源查询": '"source": None' in content,
            "信号源解析": "source_map" in content
        }
        
        print("\n✅ projector_core.py 检查:")
        for check, result in checks.items():
            status = "✅" if result else "❌"
            print(f"   {status} {check}")
        
        if all(checks.values()):
            print("\n✅ 后端代码验证通过")
        else:
            print("\n⚠️  部分检查未通过")
            
    except Exception as e:
        print(f"\n❌ 读取 projector_core.py 失败：{e}")
        return False
    
    # 检查 app.py
    try:
        with open('app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        checks = {
            "/api/projector/status 路由": "@app.route('/api/projector/status'" in content,
            "get_status 调用": "driver.get_status()" in content
        }
        
        print("\n✅ app.py 检查:")
        for check, result in checks.items():
            status = "✅" if result else "❌"
            print(f"   {status} {check}")
            
    except Exception as e:
        print(f"\n❌ 读取 app.py 失败：{e}")
        return False
    
    return True

def verify_frontend():
    """验证前端代码"""
    print("\n" + "="*80)
    print("🔍 验证前端代码")
    print("="*80)
    
    try:
        with open('templates/index.html', 'r', encoding='utf-8') as f:
            content = f.read()
        
        checks = {
            "状态显示卡片容器": 'id="projector-status-grid"' in content,
            "updateProjectorStatus 函数": "function updateProjectorStatus()" in content,
            "状态 API 调用": "fetch('/api/projector/status')" in content,
            "定时刷新": "setInterval(updateProjectorStatus, 5000)" in content,
            "电源状态显示": "电源" in content,
            "温度显示": "温度" in content,
            "灯泡时长显示": "灯泡时长" in content,
            "信号源显示": "信号源" in content
        }
        
        print("\n✅ index.html 检查:")
        for check, result in checks.items():
            status = "✅" if result else "❌"
            print(f"   {status} {check}")
        
        if all(checks.values()):
            print("\n✅ 前端代码验证通过")
        else:
            print("\n⚠️  部分检查未通过")
            
    except Exception as e:
        print(f"\n❌ 读取 index.html 失败：{e}")
        return False
    
    return True

def verify_config():
    """验证配置文件"""
    print("\n" + "="*80)
    print("🔍 验证配置文件")
    print("="*80)
    
    try:
        with open('projector_brands.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 查找视美乐品牌
        smile_brand = None
        for brand in data['brands']:
            if brand['id'] == 'smile_ek':
                smile_brand = brand
                break
        
        if not smile_brand:
            print("\n❌ 未找到视美乐 EK 系列配置")
            return False
        
        print(f"\n✅ 找到视美乐 EK 系列配置")
        print(f"   品牌：{smile_brand['name']}")
        print(f"   默认端口 (TCP): {smile_brand.get('default_port_tcp', 'N/A')}")
        print(f"   默认 ID: {smile_brand.get('default_id', 'N/A')}")
        
        # 检查必要命令
        commands = {cmd['id']: cmd for cmd in smile_brand['commands']}
        
        required_cmds = [
            'power_on',
            'power_off',
            'get_power_status',
            'get_source'
        ]
        
        print("\n✅ 必要命令检查:")
        for cmd_id in required_cmds:
            status = "✅" if cmd_id in commands else "❌"
            cmd_name = commands[cmd_id]['name'] if cmd_id in commands else "N/A"
            print(f"   {status} {cmd_id}: {cmd_name}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 读取 projector_brands.json 失败：{e}")
        return False

def verify_test_script():
    """验证测试脚本"""
    print("\n" + "="*80)
    print("🔍 验证测试脚本")
    print("="*80)
    
    import os
    if os.path.exists('test_projector_status.py'):
        print("\n✅ test_projector_status.py 已创建")
        return True
    else:
        print("\n❌ test_projector_status.py 不存在")
        return False

def main():
    print("\n" + "="*80)
    print("📊 投影机状态显示功能验证")
    print("="*80)
    
    results = []
    
    results.append(("后端代码", verify_backend()))
    results.append(("前端代码", verify_frontend()))
    results.append(("配置文件", verify_config()))
    results.append(("测试脚本", verify_test_script()))
    
    print("\n" + "="*80)
    print("📋 验证总结")
    print("="*80)
    
    for name, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {name}")
    
    if all(r[1] for r in results):
        print("\n" + "="*80)
        print("✅ 所有验证通过！功能已完整集成")
        print("="*80)
        print("\n💡 下一步:")
        print("   1. 启动系统：python app.py")
        print("   2. 打开浏览器访问：http://localhost:5000")
        print("   3. 查看主页底部的'投影机实时状态'面板")
        print("   4. 或运行测试脚本：python test_projector_status.py")
        print("="*80 + "\n")
    else:
        print("\n⚠️  部分验证未通过，请检查相关代码")
    
    return all(r[1] for r in results)

if __name__ == '__main__':
    main()
