# -*- coding: utf-8 -*-
"""
PyMifareTool - 实时贴卡嗅探器
配合用户操作：请将一张 NFC / M1 卡贴在读卡器上线圈上，脚本将循环下发寻卡信号，
一旦芯片捕获到卡片或返回 UID，立刻高亮输出！
"""

import sys
import time
import serial

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def format_hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)

# 寻卡与扫卡指令集
POLL_COMMANDS = [
    ("PN532 寻卡 (InListPassiveTarget)", bytes([0x00, 0x00, 0xFF, 0x04, 0xFC, 0xD4, 0x4A, 0x01, 0x00, 0xE1, 0x00])),
    ("RC522/CV520 通用 AA BB 寻卡 (Request A)", bytes([0xAA, 0xBB, 0x03, 0x20, 0x01, 0x26, 0x4A])),
    ("通用 02 寻卡 (STX Request)", bytes([0x02, 0x00, 0x02, 0x20, 0x22, 0x03])),
    ("微朗/金木雨 02 选卡", bytes([0x02, 0x00, 0x01, 0x25, 0x24, 0x03])),
    ("简易 0x26 (ISO14443 REQA 原生码)", bytes([0x26])),
    ("简易 0x52 (ISO14443 WUPA 原生码)", bytes([0x52])),
]

def run_sniffer(port="COM3", baud=115200):
    print(f"\n[*] 启动实时嗅探器: 端口 {port} | 波特率 {baud}")
    print("[*] >>> 请将您的 NFC/M1 卡片贴在读卡器线圈上 <<<")
    print("[*] 正在持续监听并发送寻卡脉冲 (按 Ctrl+C 退出)...\n")

    try:
        ser = serial.Serial(port, baudrate=baud, timeout=0.1)
    except Exception as e:
        print(f"[-] 打开串口失败: {e}")
        return

    ser.dtr = False
    ser.rts = False
    
    count = 0
    try:
        while count < 30: # 默认运行一段时间，若在后台或终端可调节
            count += 1
            # 1. 检查是否有主动上报数据（很多读卡器一旦感应到卡会主动响一声并吐卡号）
            if ser.in_waiting > 0:
                unsolicited = ser.read(ser.in_waiting)
                print(f"[★ 读卡器感应到卡片! 主动上报数据 ★]")
                print(f"  HEX: {format_hex(unsolicited)}")
                print(f"  ASC: {unsolicited.decode('latin1', errors='replace')}")
                break

            # 2. 轮流下发寻卡指令
            for name, cmd in POLL_COMMANDS:
                ser.reset_input_buffer()
                ser.write(cmd)
                ser.flush()
                time.sleep(0.04)
                
                if ser.in_waiting > 0:
                    resp = ser.read(ser.in_waiting)
                    # 过滤纯连零噪声
                    if resp and set(resp) != {0}:
                        print(f"[★ 寻卡命令命中! ★] 触发指令: {name}")
                        print(f"  发送: {format_hex(cmd)}")
                        print(f"  返回: {format_hex(resp)}")
                        return True

            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n[*] 用户中止嗅探。")
    finally:
        ser.close()

if __name__ == "__main__":
    b = 115200
    if len(sys.argv) > 1:
        b = int(sys.argv[1])
    run_sniffer("COM3", b)
