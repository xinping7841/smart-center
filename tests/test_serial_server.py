#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
串口服务器连接测试工具
用于测试与串口服务器的 TCP 连接
"""

import socket
import time

def test_tcp_connection(ip, port, timeout=5):
    """测试 TCP 连接"""
    print(f"\n{'='*60}")
    print(f"🔍 测试连接：{ip}:{port}")
    print(f"{'='*60}")
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        
        print(f"[{time.strftime('%H:%M:%S')}] 正在连接...")
        start_time = time.time()
        sock.connect((ip, port))
        connect_time = (time.time() - start_time) * 1000
        
        print(f"✅ 连接成功！耗时：{connect_time:.0f}ms")
        print(f"✅ 本地地址：{sock.getsockname()}")
        
        # 尝试发送一个简单的测试指令 (视美乐开机指令)
        test_cmd = bytes.fromhex("2331504F575220310D")  # #1POWR 1
        print(f"\n[测试] 发送开机指令：{test_cmd.hex(' ').upper()}")
        sock.sendall(test_cmd)
        
        # 等待响应
        time.sleep(0.3)
        sock.settimeout(2.0)
        
        try:
            response = sock.recv(1024)
            if response:
                print(f"✅ 收到响应 ({len(response)} 字节): {response.hex(' ').upper()}")
                try:
                    print(f"   文本内容：{response.decode('utf-8', errors='ignore')}")
                except:
                    pass
            else:
                print(f"⚠️  连接已关闭，设备没有返回数据")
        except socket.timeout:
            print(f"⚠️  读取超时 (2 秒)，设备没有返回数据")
            print(f"💡 提示：某些串口服务器只转发数据，不返回确认")
        
        sock.close()
        print(f"\n✅ 测试完成！连接已关闭")
        return True
        
    except socket.timeout:
        print(f"❌ 连接超时 ({timeout}秒)")
        print(f"💡 可能原因:")
        print(f"   1. IP 地址不正确")
        print(f"   2. 端口未开放")
        print(f"   3. 防火墙阻止连接")
        print(f"   4. 设备未开机")
        return False
        
    except ConnectionRefusedError:
        print(f"❌ 连接被拒绝")
        print(f"💡 可能原因:")
        print(f"   1. 端口号不正确")
        print(f"   2. 设备未运行在指定端口")
        print(f"   3. 防火墙阻止")
        return False
        
    except Exception as e:
        print(f"❌ 发生错误：{str(e)}")
        return False

def scan_ports(ip, port_range=(1, 65535)):
    """扫描开放的端口"""
    print(f"\n{'='*60}")
    print(f"🔍 扫描 {ip} 的开放端口...")
    print(f"{'='*60}")
    
    open_ports = []
    common_ports = [23, 80, 443, 502, 808, 888, 889, 900, 2000, 4001, 4002, 5000, 8080, 8899, 9999]
    
    # 先扫描常用端口
    print(f"\n[第 1 阶段] 扫描常用端口...")
    for port in common_ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex((ip, port))
            if result == 0:
                print(f"  ✅ 端口 {port} 开放")
                open_ports.append(port)
            sock.close()
        except:
            pass
    
    # 询问是否继续扫描
    if open_ports:
        print(f"\n✅ 发现 {len(open_ports)} 个开放端口：{', '.join(map(str, open_ports))}")
    else:
        print(f"\n⚠️  常用端口都未开放")
    
    return open_ports

def main():
    """主函数"""
    print("\n" + "="*60)
    print("🔧 串口服务器连接测试工具")
    print("="*60)
    
    # 默认配置
    default_ip = "192.168.50.72"
    default_port = 502
    
    print(f"\n📋 当前配置:")
    print(f"   IP 地址：{default_ip}")
    print(f"   端口：{default_port}")
    print(f"\n💡 提示：这是您投影机配置中的串口服务器地址")
    
    # 询问是否使用默认配置
    use_default = input(f"\n是否使用默认配置进行测试？(Y/n): ").strip().lower()
    
    if use_default != 'n' and use_default != 'no':
        ip = default_ip
        port = default_port
    else:
        ip = input(f"请输入 IP 地址 [{default_ip}]: ").strip() or default_ip
        port_str = input(f"请输入端口号 [{default_port}]: ").strip()
        port = int(port_str) if port_str.isdigit() else default_port
    
    # 测试连接
    success = test_tcp_connection(ip, port)
    
    if not success:
        print(f"\n{'='*60}")
        print("❌ 连接失败，是否扫描开放端口？")
        print("="*60)
        scan_choice = input(f"是否扫描 {ip} 的开放端口？(y/N): ").strip().lower()
        
        if scan_choice == 'y' or scan_choice == 'yes':
            open_ports = scan_ports(ip)
            
            if open_ports:
                print(f"\n💡 建议:")
                print(f"   请使用以下端口重试:")
                for p in open_ports:
                    print(f"   - {ip}:{p}")
                
                # 询问是否测试第一个开放端口
                if open_ports:
                    test_choice = input(f"\n是否测试第一个开放端口 ({open_ports[0]})? (y/N): ").strip().lower()
                    if test_choice == 'y' or test_choice == 'yes':
                        test_tcp_connection(ip, open_ports[0])
    
    print(f"\n{'='*60}")
    print("✅ 测试结束")
    print("="*60)
    print(f"\n📋 配置建议:")
    print(f"   在投影机配置页面:")
    print(f"   - IP 地址：{ip}")
    print(f"   - 端口：请使用串口服务器实际监听的端口")
    print(f"   - 协议：视美乐 EK 系列 (TCP 网口 / 串口服务器透传)")
    print(f"\n💡 如何查找串口服务器端口:")
    print(f"   1. 登录串口服务器 Web 管理界面")
    print(f"   2. 查看'服务器配置'或'监听端口'")
    print(f"   3. 常见端口：4001, 8899, 5000, 8080 等")
    print()

if __name__ == "__main__":
    main()
