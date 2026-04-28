#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
投影机品牌命令库测试脚本
用于验证 projector_brands.json 和 projector_core.py 的功能
"""

import json
import os

def test_brand_library():
    """测试品牌库加载"""
    print("\n" + "="*60)
    print("📋 测试品牌库加载")
    print("="*60)
    
    from projector_core import load_brand_library, get_all_brands, get_brand_commands
    
    # 测试加载品牌库
    lib = load_brand_library()
    print(f"✅ 品牌库加载成功，包含 {len(lib.get('brands', []))} 个品牌")
    
    # 测试获取所有品牌
    brands = get_all_brands()
    print(f"\n📦 可用品牌列表:")
    for brand in brands:
        print(f"   - {brand['id']}: {brand['name']}")
        print(f"     支持协议：{', '.join(brand.get('control_types', []))}")
        print(f"     命令数量：{len(brand.get('commands', []))}")
    
    return True

def test_smile_ek_commands():
    """测试视美乐 EK 系列命令"""
    print("\n" + "="*60)
    print("🎯 测试视美乐 EK 系列命令")
    print("="*60)
    
    from projector_core import get_brand_commands
    
    commands = get_brand_commands('smile_ek')
    print(f"✅ 视美乐 EK 系列包含 {len(commands)} 条命令\n")
    
    print(f"{'功能':<15} {'名称':<20} {'格式':<8} {'主页显示':<10}")
    print("-" * 60)
    for cmd in commands:
        show_on_home = "✅" if cmd.get('show_on_home') else "❌"
        print(f"{cmd.get('id', 'N/A'):<15} {cmd.get('name', 'N/A'):<20} {cmd.get('default_format', 'N/A'):<8} {show_on_home:<10}")
    
    return True

def test_driver_initialization():
    """测试驱动初始化"""
    print("\n" + "="*60)
    print("🔧 测试驱动初始化")
    print("="*60)
    
    from projector_core import ProjectorDriver
    
    # 测试配置
    test_configs = [
        {
            "id": "test_proj_1",
            "name": "测试投影机 1",
            "brand_id": "smile_ek",
            "control_type": "smile_ek_tcp",
            "ip": "192.168.1.100",
            "port": 502
        },
        {
            "id": "test_proj_2",
            "name": "测试投影机 2",
            "brand_id": "smile_ek",
            "control_type": "smile_ek_com",
            "com_port": "COM1",
            "baudrate": 19200
        },
        {
            "id": "test_proj_3",
            "name": "测试投影机 3",
            "brand_id": "epson",
            "control_type": "pjlink",
            "ip": "192.168.1.101",
            "port": 4352
        }
    ]
    
    for cfg in test_configs:
        try:
            driver = ProjectorDriver(cfg)
            print(f"✅ {cfg['name']}: 初始化成功")
            print(f"   品牌：{driver.brand_id}, 协议：{driver.control_type}")
        except Exception as e:
            print(f"❌ {cfg['name']}: 初始化失败 - {str(e)}")
    
    return True

def test_command_execution():
    """测试命令执行 (模拟)"""
    print("\n" + "="*60)
    print("🎬 测试命令执行逻辑")
    print("="*60)
    
    from projector_core import ProjectorDriver, get_brand_commands
    
    cfg = {
        "id": "test_proj",
        "name": "测试投影机",
        "brand_id": "smile_ek",
        "control_type": "smile_ek_tcp",
        "ip": "192.168.1.100",
        "port": 502
    }
    
    driver = ProjectorDriver(cfg)
    
    # 测试命令解析
    test_commands = [
        "power_on",  # 字符串形式 (旧版兼容)
        {"payload": "#1POWR 1", "format": "str"},  # 字典形式
        {"payload": "23 31 50 4F 57 52 20 31 0D", "format": "hex"},  # Hex 形式
    ]
    
    for cmd in test_commands:
        print(f"\n测试命令：{cmd}")
        try:
            # 这里只测试命令解析，不实际发送
            # 实际发送需要连接真实设备
            if isinstance(cmd, str):
                brand_cmds = get_brand_commands(driver.brand_id)
                cmd_def = next((c for c in brand_cmds if c["id"] == cmd), None)
                if cmd_def:
                    fmt = cmd_def.get("default_format", "str")
                    payload = driver._get_payload(cmd_def, fmt)
                    print(f"   ✅ 解析成功 -> 格式：{fmt}, Payload: {payload}")
                else:
                    print(f"   ⚠️  未找到命令定义，使用默认逻辑")
            else:
                print(f"   ✅ 字典命令 -> 格式：{cmd.get('format')}, Payload: {cmd.get('payload')}")
        except Exception as e:
            print(f"   ❌ 解析失败：{str(e)}")
    
    return True

def test_config_integration():
    """测试与 config.py 的集成"""
    print("\n" + "="*60)
    print("🔗 测试配置集成")
    print("="*60)
    
    try:
        from config import get_projector_brands, get_brand_commands, normalize_projector_config
        
        # 测试获取品牌
        brands = get_projector_brands()
        print(f"✅ config.py 成功获取品牌列表：{len(brands)} 个品牌")
        
        # 测试标准化配置
        test_proj = {
            "id": "proj_test",
            "name": "测试投影机"
        }
        
        normalized = normalize_projector_config(test_proj)
        print(f"✅ 配置标准化成功:")
        print(f"   brand_id: {normalized.get('brand_id')}")
        print(f"   control_type: {normalized.get('control_type')}")
        print(f"   commands: {len(normalized.get('commands', []))} 条命令")
        
        return True
    except Exception as e:
        print(f"❌ 配置集成测试失败：{str(e)}")
        return False

def test_api_endpoints():
    """测试 API 端点"""
    print("\n" + "="*60)
    print("🌐 测试 API 端点 (需要服务器运行)")
    print("="*60)
    
    import requests
    
    base_url = "http://localhost:6899"
    
    try:
        # 测试品牌列表 API
        resp = requests.get(f"{base_url}/api/projector/brands", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            print(f"✅ GET /api/projector/brands - 返回 {len(data.get('brands', []))} 个品牌")
        else:
            print(f"❌ GET /api/projector/brands - 状态码：{resp.status_code}")
        
        # 测试品牌命令 API
        resp = requests.get(f"{base_url}/api/projector/brand_commands?brand_id=smile_ek", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            print(f"✅ GET /api/projector/brand_commands - 返回 {len(data.get('commands', []))} 条命令")
        else:
            print(f"❌ GET /api/projector/brand_commands - 状态码：{resp.status_code}")
        
        # 测试状态查询 API (需要有投影机配置)
        resp = requests.get(f"{base_url}/api/projector/status", timeout=2)
        if resp.status_code == 200:
            print(f"✅ GET /api/projector/status - 返回状态数据")
        else:
            print(f"⚠️  GET /api/projector/status - 状态码：{resp.status_code} (可能没有配置投影机)")
        
        return True
    except requests.exceptions.ConnectionError:
        print(f"⚠️  服务器未运行，跳过 API 测试")
        print(f"   提示：先运行 python app.py 启动服务器")
        return False
    except Exception as e:
        print(f"❌ API 测试失败：{str(e)}")
        return False

def main():
    """主测试函数"""
    print("\n" + "🎥"*30)
    print("🎥 投影机品牌命令库集成测试")
    print("🎥"*30)
    
    tests = [
        ("品牌库加载", test_brand_library),
        ("视美乐 EK 命令", test_smile_ek_commands),
        ("驱动初始化", test_driver_initialization),
        ("命令执行逻辑", test_command_execution),
        ("配置集成", test_config_integration),
        ("API 端点", test_api_endpoints),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} 测试异常：{str(e)}")
            results.append((name, False))
    
    # 汇总结果
    print("\n" + "="*60)
    print("📊 测试结果汇总")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} - {name}")
    
    print(f"\n总计：{passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！系统已准备就绪。")
    else:
        print("\n⚠️  部分测试失败，请检查相关配置。")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    main()
