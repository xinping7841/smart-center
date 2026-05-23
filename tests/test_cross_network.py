#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
跨网段串口服务器测试工具
测试从 192.168.30.12 到 192.168.50.72:502 的连接
"""

import socket
import time
import sys

def test_connection():
    """测试连接"""
    # 配置
    SERVER_IP = "192.168.50.72"
    SERVER_PORT = 502
    LOCAL_IP = "192.168.30.12"
    
    print("\n" + "="*70)
    print("🔍 跨网段串口服务器连接测试")
    print("="*70)
    print(f"\n📋 网络配置:")
    print(f"   本地地址：{LOCAL_IP} (运行测试的机器)")
    print(f"   目标地址：{SERVER_IP}:{SERVER_PORT} (串口服务器)")
    print(f"\n💡 提示：这是跨网段通信 (30.x -> 50.x)")
    
    # 测试 1: TCP 连接
    print(f"\n{'='*70}")
    print("[测试 1] TCP 连接测试")
    print(f"{'='*70}")
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        
        print(f"\n[{time.strftime('%H:%M:%S')}] 正在连接 {SERVER_IP}:{SERVER_PORT}...")
        start_time = time.time()
        sock.connect((SERVER_IP, SERVER_PORT))
        connect_time = (time.time() - start_time) * 1000
        
        print(f"✅ 连接成功！耗时：{connect_time:.0f}ms")
        print(f"✅ 本地套接字地址：{sock.getsockname()}")
        
        # 测试 2: 发送开机指令
        print(f"\n{'='*70}")
        print("[测试 2] 发送投影机开机指令")
        print(f"{'='*70}")
        
        # 视美乐开机指令：#1POWR 1
        test_cmd_hex = "23 31 50 4F 57 52 20 31 0D"
        test_cmd = bytes.fromhex(test_cmd_hex.replace(" ", ""))
        
        print(f"\n[发送] 16 进制：{test_cmd_hex}")
        print(f"[发送] 字符串：#1POWR 1")
        print(f"[发送] 字节数：{len(test_cmd)} bytes")
        
        sock.sendall(test_cmd)
        print(f"✅ 指令已发送")
        
        # 等待响应
        print(f"\n[等待] 等待设备响应 (2 秒)...")
        time.sleep(0.3)
        sock.settimeout(2.0)
        
        try:
            response = sock.recv(1024)
            if response:
                print(f"\n✅ 收到响应!")
                print(f"   字节数：{len(response)} bytes")
                print(f"   16 进制：{response.hex(' ').upper()}")
                try:
                    text = response.decode('utf-8', errors='ignore')
                    print(f"   字符串：{text}")
                except:
                    pass
            else:
                print(f"\n⚠️  连接已关闭，设备没有返回数据")
        except socket.timeout:
            print(f"\n⚠️  读取超时 (2 秒)")
            print(f"💡 这可能是正常的，因为:")
            print(f"   1. 串口服务器只转发数据，不返回确认")
            print(f"   2. 投影机可能未开机或串口未连接")
            print(f"   3. 波特率配置不匹配")
        
        sock.close()
        print(f"\n✅ 测试完成！连接已关闭")
        
        # 总结
        print(f"\n{'='*70}")
        print("📊 测试结果总结")
        print(f"{'='*70}")
        print(f"✅ TCP 连接：成功 (网络通信正常)")
        print(f"✅ 指令发送：成功 (数据已发送到串口服务器)")
        print(f"⚠️  设备响应：无 (可能是正常的)")
        print(f"\n💡 建议:")
        print(f"   1. 检查投影机是否开机")
        print(f"   2. 检查串口线是否连接正确")
        print(f"   3. 检查串口服务器波特率配置 (视美乐 EK 默认 19200)")
        print(f"   4. 查看投影机是否有反应 (如果开机指令成功，投影机会启动)")
        
        return True
        
    except socket.timeout:
        print(f"\n❌ 连接超时 (5 秒)")
        print(f"\n💡 可能原因:")
        print(f"   1. 网络不通 (检查路由/防火墙)")
        print(f"   2. 串口服务器未开机")
        print(f"   3. 端口 502 未开放")
        print(f"   4. 串口服务器配置了 IP 白名单，未包含 192.168.30.12")
        return False
        
    except ConnectionRefusedError:
        print(f"\n❌ 连接被拒绝")
        print(f"\n💡 可能原因:")
        print(f"   1. 端口 502 未监听")
        print(f"   2. 串口服务器配置了 TCP Client 模式而非 Server 模式")
        print(f"   3. 防火墙阻止")
        return False
        
    except Exception as e:
        print(f"\n❌ 发生错误：{str(e)}")
        import traceback
        traceback.print_exc()
        return False

def check_network_route():
    """检查网络路由"""
    print(f"\n{'='*70}")
    print("🔍 网络路由检查")
    print(f"{'='*70}")
    
    import subprocess
    try:
        # Windows 使用 route print
        result = subprocess.run(['route', 'print'], capture_output=True, text=True, timeout=5)
        routes = result.stdout
        
        # 查找 192.168.50.x 的路由
        print(f"\n查找 192.168.50.x 网段的路由...")
        for line in routes.split('\n'):
            if '192.168.50' in line:
                print(f"  {line.strip()}")
        
        # 检查默认网关
        print(f"\n本地网络配置:")
        result = subprocess.run(['ipconfig', '/all'], capture_output=True, text=True, timeout=5)
        for line in result.stdout.split('\n'):
            if 'IPv4' in line or 'Default Gateway' in line or '子网掩码' in line or '默认网关' in line:
                print(f"  {line.strip()}")
                
    except Exception as e:
        print(f"⚠️  无法检查路由：{str(e)}")

if __name__ == "__main__":
    # 检查网络路由
    check_network_route()
    
    # 测试连接
    success = test_connection()
    
    print(f"\n{'='*70}")
    print("✅ 所有测试完成")
    print(f"{'='*70}")
    
    sys.exit(0 if success else 1)
