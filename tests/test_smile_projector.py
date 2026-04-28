#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
视美乐投影机测试工具 - 测试开机/关机指令
"""
import socket
import time

# 配置
IP = "192.168.50.72"
PORT = 502

def decode_hex(hex_str):
    """解码 16 进制为字符串"""
    return bytes.fromhex(hex_str.replace(' ', '')).decode('utf-8', errors='ignore')

def send_command(hex_payload, description):
    """发送指令并显示结果"""
    print(f"\n{'='*60}")
    print(f"测试：{description}")
    print(f"16 进制：{hex_payload}")
    print(f"字符串：{decode_hex(hex_payload)}")
    print(f"目标：{IP}:{PORT}")
    print(f"{'='*60}")
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5.0)
            print(f"[{time.strftime('%H:%M:%S')}] 正在连接...")
            s.connect((IP, PORT))
            
            # 发送数据
            payload = bytes.fromhex(hex_payload.replace(' ', ''))
            s.sendall(payload)
            print(f"[{time.strftime('%H:%M:%S')}] ✅ 数据已发送")
            
            # 等待响应
            time.sleep(0.3)
            s.settimeout(2.0)
            
            try:
                res = s.recv(1024)
                if res:
                    print(f"[{time.strftime('%H:%M:%S')}] 📥 收到响应：{res.hex(' ').upper()}")
                    print(f"[{time.strftime('%H:%M:%S')}] 📥 字符串：{res.decode('utf-8', errors='ignore')}")
                    return True, f"成功：{res.hex(' ').upper()}"
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] ⚠️  连接被关闭")
                    return True, "已发送 (无返回)"
            except socket.timeout:
                print(f"[{time.strftime('%H:%M:%S')}] ⚠️  读取超时 (正常)")
                return True, "已发送 (无返回)"
                
    except socket.timeout:
        print(f"[{time.strftime('%H:%M:%S')}] ❌ 连接超时")
        return False, "连接超时"
    except ConnectionRefusedError:
        print(f"[{time.strftime('%H:%M:%S')}] ❌ 连接被拒绝")
        return False, "连接被拒绝"
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] ❌ 错误：{str(e)}")
        return False, str(e)

def main():
    print("\n" + "="*60)
    print("🎯 视美乐投影机控制测试")
    print("="*60)
    
    # 测试指令列表
    test_commands = [
        # 根据用户提供的关机指令
        ("23 50 57 52 30 2C 31 21", "关机指令 (用户提供) #PWR0,1!"),
        
        # 标准格式测试
        ("23 50 57 52 30 2C 30 31", "开机指令 #PWR0,01"),
        ("23 50 57 52 30 2C 30 30", "关机指令 #PWR0,00"),
        
        # 带 ID=30 的格式
        ("23 50 57 52 33 30 2C 30 31", "开机指令 (ID=30) #PWR30,01"),
        ("23 50 57 52 33 30 2C 30 30", "关机指令 (ID=30) #PWR30,00"),
    ]
    
    results = []
    for hex_cmd, desc in test_commands:
        success, msg = send_command(hex_cmd, desc)
        results.append((desc, success, msg))
        time.sleep(1)  # 间隔 1 秒
    
    # 显示结果汇总
    print(f"\n{'='*60}")
    print("📊 测试结果汇总")
    print("="*60)
    for desc, success, msg in results:
        status = "✅" if success else "❌"
        print(f"{status} {desc}")
        print(f"   结果：{msg}")
    
    print(f"\n💡 提示:")
    print(f"   1. 如果连接成功但投影机无反应，请检查设备 ID 是否正确")
    print(f"   2. 默认设备 ID 为 30，如果投影机 ID 不同，需要修改配置")
    print(f"   3. 串口服务器可能不返回数据，只要发送成功即正常")
    print()

if __name__ == "__main__":
    main()
