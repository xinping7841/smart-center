#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
视美乐投影机 - 直接发送关机指令
"""
import socket
import time

# 配置
IP = "192.168.50.72"
PORT = 502

print(f"\n{'='*60}")
print(f"🎯 发送关机指令")
print(f"{'='*60}")
print(f"目标：{IP}:{PORT}")
print(f"16 进制：23 50 57 52 30 2C 30 21")
print(f"字符串：#PWR0,0!")
print(f"{'='*60}\n")

try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(5.0)
        print(f"[{time.strftime('%H:%M:%S')}] 正在连接...")
        s.connect((IP, PORT))
        
        # 发送 16 进制数据
        payload = bytes.fromhex("23 50 57 52 30 2C 30 21")
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
            
        print(f"\n✅ 指令已发送！请检查投影机是否关机")
        
except Exception as e:
    print(f"❌ 错误：{str(e)}")

print(f"\n{'='*60}\n")
