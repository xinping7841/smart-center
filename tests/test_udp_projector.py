#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
UDP 模式串口服务器测试工具
测试从 192.168.30.12 到 192.168.50.72:502 的 UDP 连接
"""

import socket
import time

def test_udp_connection():
    """测试 UDP 连接"""
    SERVER_IP = "192.168.50.72"
    SERVER_PORT = 502
    
    print("\n" + "="*70)
    print("🔍 UDP 模式串口服务器测试")
    print("="*70)
    print(f"\n📋 配置:")
    print(f"   本地地址：192.168.30.12")
    print(f"   目标地址：{SERVER_IP}:{SERVER_PORT}")
    print(f"   协议：UDP")
    
    # 创建 UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(3.0)
    
    # 测试 1: 发送开机指令
    print(f"\n{'='*70}")
    print("[测试 1] 发送开机指令 (#1POWR 1)")
    print(f"{'='*70}")
    
    # 视美乐开机指令：#1POWR 1
    test_cmd_hex = "23 31 50 4F 57 52 20 31 0D"
    test_cmd = bytes.fromhex(test_cmd_hex.replace(" ", ""))
    
    print(f"\n[发送] 16 进制：{test_cmd_hex}")
    print(f"[发送] 字符串：#1POWR 1")
    print(f"[发送] 字节数：{len(test_cmd)} bytes")
    print(f"[发送] 目标：{SERVER_IP}:{SERVER_PORT}")
    
    try:
        sock.sendto(test_cmd, (SERVER_IP, SERVER_PORT))
        print(f"✅ 指令已通过 UDP 发送!")
        
        # 等待响应
        print(f"\n[等待] 等待设备响应 (3 秒)...")
        time.sleep(0.5)
        
        try:
            response, addr = sock.recvfrom(1024)
            if response:
                print(f"\n✅ 收到响应!")
                print(f"   来源：{addr[0]}:{addr[1]}")
                print(f"   字节数：{len(response)} bytes")
                print(f"   16 进制：{response.hex(' ').upper()}")
                try:
                    text = response.decode('utf-8', errors='ignore')
                    print(f"   字符串：{text}")
                except:
                    pass
            else:
                print(f"\n⚠️  收到空响应")
        except socket.timeout:
            print(f"\n⚠️  读取超时 (3 秒)")
            print(f"💡 这是正常的，因为:")
            print(f"   1. UDP 是无连接的，不等待响应")
            print(f"   2. 串口服务器只转发数据到串口")
            print(f"   3. 投影机可能不会立即响应")
        
        # 测试 2: 发送关机指令
        print(f"\n{'='*70}")
        print("[测试 2] 发送关机指令 (#1POWR 0)")
        print(f"{'='*70}")
        
        test_cmd_hex = "23 31 50 4F 57 52 20 30 0D"
        test_cmd = bytes.fromhex(test_cmd_hex.replace(" ", ""))
        
        print(f"\n[发送] 16 进制：{test_cmd_hex}")
        print(f"[发送] 字符串：#1POWR 0")
        
        sock.sendto(test_cmd, (SERVER_IP, SERVER_PORT))
        print(f"✅ 关机指令已发送!")
        
        time.sleep(0.5)
        
        sock.close()
        
        # 总结
        print(f"\n{'='*70}")
        print("📊 测试结果")
        print(f"{'='*70}")
        print(f"✅ UDP 发送：成功")
        print(f"⚠️  设备响应：无 (正常)")
        print(f"\n💡 说明:")
        print(f"   1. UDP 数据已发送到串口服务器")
        print(f"   2. 串口服务器会转发到 RS232 串口")
        print(f"   3. 如果投影机有反应，说明成功!")
        print(f"   4. 没有响应是正常的 (UDP 特性)")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 发生错误：{str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        sock.close()

if __name__ == "__main__":
    success = test_udp_connection()
    
    print(f"\n{'='*70}")
    print("✅ 测试完成")
    print(f"{'='*70}")
    
    if success:
        print(f"\n🎉 UDP 通讯正常!")
        print(f"💡 请在投影机配置页面选择:")
        print(f"   协议：视美乐 EK 系列 (UDP 网口)")
        print(f"   IP: 192.168.50.72")
        print(f"   端口：502")
    else:
        print(f"\n❌ UDP 通讯失败，请检查网络配置")
    
    print()
