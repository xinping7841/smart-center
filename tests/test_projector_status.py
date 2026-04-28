#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
投影机状态查询测试工具
测试投影机开关机状态、温度、灯泡时长、信号源等状态查询功能
"""

import json
from projector_core import ProjectorDriver

def test_projector_status():
    """测试投影机状态查询"""
    print("\n" + "="*80)
    print("📊 投影机状态查询测试")
    print("="*80)
    
    # 读取配置
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"❌ 读取配置文件失败：{e}")
        return
    
    projectors = config.get('projectors', [])
    if not projectors:
        print("❌ 未配置投影机")
        return
    
    print(f"\n✅ 找到 {len(projectors)} 台投影机")
    print("-" * 80)
    
    for proj in projectors:
        print(f"\n🎥 投影机：{proj.get('name', proj['id'])}")
        print(f"   品牌：{proj.get('brand_id', 'unknown')}")
        print(f"   通讯方式：{proj.get('control_type', 'unknown')}")
        print(f"   地址：{proj.get('host', '')}:{proj.get('port', '')}")
        print("-" * 80)
        
        try:
            driver = ProjectorDriver(proj)
            status = driver.get_status()
            
            print(f"\n📊 状态查询结果:")
            print(f"   在线状态：{'✅ 在线' if status['online'] else '❌ 离线'}")
            print(f"   电源状态：{status['power']}")
            
            if status['temp'] is not None:
                temp_status = "⚠️ 高温" if status['temp'] > 60 else "✅ 正常"
                print(f"   温度：{status['temp']}℃ {temp_status}")
            else:
                print(f"   温度：-- (不支持或查询失败)")
            
            if status['lamp_hours'] is not None:
                print(f"   灯泡时长：{status['lamp_hours']} 小时")
            else:
                print(f"   灯泡时长：-- (不支持或查询失败)")
            
            if status['source']:
                print(f"   当前信号源：{status['source']}")
            else:
                print(f"   信号源：-- (不支持或查询失败)")
            
        except Exception as e:
            print(f"\n❌ 查询失败：{str(e)}")
        
        print("-" * 80)
    
    print("\n" + "="*80)
    print("✅ 测试完成")
    print("="*80 + "\n")

if __name__ == '__main__':
    test_projector_status()
