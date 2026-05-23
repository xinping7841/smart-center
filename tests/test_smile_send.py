#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
视美乐投影机测试工具 - 发送真实指令
"""
import socket
import time

# 配置
IP = "192.168.50.72"
PORT = 502

def send_hex_command(hex_payload, description):
    """发送 16 进制指令"""
    print(f"\n{'='*60}")
    print(f"📤 发送：{description}")
    print(f"16 进制：{hex_payload}")
    print(f"字符串：{bytes.fromhex(hex_payload.replace(' ', '')).decode('utf-8', errors='ignore')}")
    print(f"目标：{IP}:{PORT}")
    print(f"{'='*60}")
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5.0)
            print(f"[{time.strftime('%H:%M:%S')}] 正在连接...")
            s.connect((IP, PORT))
            
            # 发送 16 进制数据
            payload = bytes.fromhex(hex_payload.replace(' ', ''))
            s.sendall(payload)
            print(f"[{time.strftime('%H:%M:%S')}] ✅ 数据已发送 (16 进制)")
            
            # 等待响应
            time.sleep(0.3)
            s.settimeout(2.0)
            
            try:
                res = s.recv(1024)
                if res:
                    print(f"[{time.strftime('%H:%M:%S')}] 📥 收到：{res.hex(' ').upper()}")
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] ⚠️  连接关闭")
            except socket.timeout:
                print(f"[{time.strftime('%H:%M:%S')}] ⚠️  读取超时 (正常)")
                
            return True
            
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] ❌ 错误：{str(e)}")
        return False

def main():
    print("\n" + "="*60)
    print("🎯 视美乐投影机 - 16 进制指令测试")
    print("="*60)
    print(f"\n请选择要测试的指令:")
    print(f"1. 开机 (23 50 57 52 30 2C 31 21)")
    print(f"2. 关机 (23 50 57 52 30 2C 30 21)")
    print(f"3. 两个都测试")
    print(f"0. 退出")
    
    choice = input(f"\n请输入选项 (0-3): ").strip()
    
    if choice == "1":
        send_hex_command("23 50 57 52 30 2C 31 21", "开机指令")
    elif choice == "2":
        send_hex_command("23 50 57 52 30 2C 30 21", "关机指令")
    elif choice == "3":
        print(f"\n>>> 测试开机...")
        send_hex_command("23 50 57 52 30 2C 31 21", "开机指令")
        time.sleep(1)
        print(f"\n>>> 测试关机...")
        send_hex_command("23 50 57 52 30 2C 30 21", "关机指令")
    else:
        print("退出")
        return
    
    print(f"\n{'='*60}")
    print(f"✅ 测试完成！请检查投影机是否执行了相应操作")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
