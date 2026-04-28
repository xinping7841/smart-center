#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
光峰 HD500 协议测试工具
"""

import socket
import time

def calculate_checksum(data_bytes):
    """计算校验和 (所有字节相加，取低 8 位)"""
    return sum(data_bytes) & 0xFF

def build_frame(cmd_h, cmd_l, param=0):
    """
    构建光峰 HD500 协议帧
    
    帧格式:
    - Head_H: EB
    - Head_L: 90
    - Length_H: 00
    - Length_L: 08 (固定长度)
    - Flag: 01 (发送), 00 (接收)
    - Count: 00
    - From: 01 (DLP), 02 (PMU), 04 (IDU), 08 (PC)
    - To: 00 (DLP), 01 (PMU), 02 (IDU), 08 (PC)
    - CMD_H: 命令高字节
    - CMD_L: 命令低字节
    - Param: 参数 (4 字节)
    - Checksum: 校验和
    """
    head_h = 0xEB
    head_l = 0x90
    length_h = 0x00
    length_l = 0x08
    flag = 0x01  # 发送
    count = 0x00
    from_addr = 0x01  # PC
    to_addr = 0x00    # DLP
    
    # 构建不含校验和的帧
    frame = bytes([
        head_h, head_l, length_h, length_l,
        flag, count, from_addr, to_addr,
        cmd_h, cmd_l,
        (param >> 24) & 0xFF, (param >> 16) & 0xFF, (param >> 8) & 0xFF, param & 0xFF
    ])
    
    # 计算校验和
    checksum = calculate_checksum(frame)
    
    # 返回完整帧
    return frame + bytes([checksum])

def test_appotronics_hd500():
    """测试光峰 HD500 协议"""
    # 配置 - 使用您实际的串口服务器配置
    SERVER_IP = "192.168.50.72"  # 串口服务器 IP
    SERVER_PORT = 502  # 端口
    USE_UDP = False  # 使用 TCP 模式测试
    
    print("\n" + "="*70)
    print("🔍 光峰 HD500 协议测试")
    print("="*70)
    print(f"\n📋 配置:")
    print(f"   目标地址：{SERVER_IP}:{SERVER_PORT}")
    print(f"   协议：光峰 HD500 二进制协议 ({'UDP' if USE_UDP else 'TCP'})")
    
    # 测试命令列表
    test_commands = [
        {"name": "开机", "cmd_h": 0x00, "cmd_l": 0x01, "param": 0x01},
        {"name": "关机", "cmd_h": 0x00, "cmd_l": 0x01, "param": 0x00},
        {"name": "切换至 HDMI1", "cmd_h": 0x00, "cmd_l": 0x04, "param": 0x01},
        {"name": "切换至 HDMI2", "cmd_h": 0x00, "cmd_l": 0x04, "param": 0x02},
        {"name": "查询电源状态", "cmd_h": 0x80, "cmd_l": 0x58, "param": 0x00},
    ]
    
    for cmd in test_commands:
        print(f"\n{'='*70}")
        print(f"[测试] {cmd['name']}")
        print(f"{'='*70}")
        
        # 构建协议帧
        frame = build_frame(cmd['cmd_h'], cmd['cmd_l'], cmd['param'])
        
        print(f"\n[帧结构]")
        print(f"   Head: {frame[0]:02X} {frame[1]:02X}")
        print(f"   Length: {frame[2]:02X} {frame[3]:02X}")
        print(f"   Flag: {frame[4]:02X}, Count: {frame[5]:02X}")
        print(f"   From: {frame[6]:02X}, To: {frame[7]:02X}")
        print(f"   CMD: {frame[8]:02X} {frame[9]:02X}")
        print(f"   Param: {frame[10]:02X} {frame[11]:02X} {frame[12]:02X} {frame[13]:02X}")
        print(f"   Checksum: {frame[14]:02X}")
        print(f"\n[16 进制] {frame.hex(' ').upper()}")
        
        # 发送测试
        try:
            if USE_UDP:
                # UDP 模式
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(3.0)
                sock.sendto(frame, (SERVER_IP, SERVER_PORT))
                print(f"\n[发送] UDP 数据已发送到 {SERVER_IP}:{SERVER_PORT}")
                
                # 等待响应
                time.sleep(0.3)
                
                try:
                    response, addr = sock.recvfrom(1024)
                    if response:
                        print(f"✅ 收到响应 ({len(response)} 字节)")
                        print(f"   来源：{addr[0]}:{addr[1]}")
                        print(f"   16 进制：{response.hex(' ').upper()}")
                    else:
                        print(f"⚠️  收到空响应")
                except socket.timeout:
                    print(f"⚠️  读取超时 (3 秒)")
                    print(f"💡 这可能是正常的，串口服务器可能不返回数据")
                finally:
                    sock.close()
            else:
                # TCP 模式
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5.0)
                
                print(f"\n[发送] 正在连接 {SERVER_IP}:{SERVER_PORT}...")
                sock.connect((SERVER_IP, SERVER_PORT))
                sock.sendall(frame)
                print(f"✅ 数据已发送")
                
                # 等待响应
                time.sleep(0.3)
                sock.settimeout(2.0)
                
                try:
                    response = sock.recv(1024)
                    if response:
                        print(f"✅ 收到响应 ({len(response)} 字节)")
                        print(f"   16 进制：{response.hex(' ').upper()}")
                        
                        # 解析响应
                        if len(response) >= 15:
                            print(f"   Head: {response[0]:02X} {response[1]:02X}")
                            print(f"   CMD: {response[8]:02X} {response[9]:02X}")
                            print(f"   Param: {response[10]:02X} {response[11]:02X} {response[12]:02X} {response[13]:02X}")
                            print(f"   Checksum: {response[14]:02X}")
                    else:
                        print(f"⚠️  连接已关闭，无响应")
                except socket.timeout:
                    print(f"⚠️  读取超时 (2 秒)")
                    print(f"💡 这可能是正常的，串口服务器可能不返回数据")
                
                sock.close()
            
        except socket.timeout:
            print(f"❌ 连接超时")
        except ConnectionRefusedError:
            print(f"❌ 连接被拒绝")
        except Exception as e:
            print(f"❌ 发生错误：{str(e)}")
        
        time.sleep(0.5)
    
    # 总结
    print(f"\n{'='*70}")
    print("📊 测试完成")
    print(f"{'='*70}")
    print(f"\n💡 说明:")
    print(f"   1. 如果显示'数据已发送'，说明网络通讯正常")
    print(f"   2. 如果有响应，说明投影机或串口服务器正常工作")
    print(f"   3. 没有响应也可能是正常的 (UDP 模式或串口服务器配置)")
    print(f"   4. 请观察投影机是否有实际反应")
    print()

if __name__ == "__main__":
    test_appotronics_hd500()
