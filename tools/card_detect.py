# -*- coding: utf-8 -*-
"""
PyMifareTool - 贴卡实时协议与UID探测器
针对 ISO 14443-3A 卡片进行多协议寻卡与卡号读取测试
"""

import sys
import time
import serial

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def format_hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)

# 针对 ISO 14443-3A 卡片的常用读卡器寻卡与防冲突指令集
TEST_COMMANDS = [
    # 1. PN532 协议 (106k Type A 寻卡)
    ("PN532 寻卡 (InListPassiveTarget)", bytes([0x00, 0x00, 0xFF, 0x04, 0xFC, 0xD4, 0x4A, 0x01, 0x00, 0xE1, 0x00])),
    # 2. 国产通用 AA BB 协议 (寻卡 + 读UID)
    ("AA BB 寻卡 (Request A)", bytes([0xAA, 0xBB, 0x03, 0x20, 0x01, 0x26, 0x4A])),
    ("AA BB 防冲突读卡号 (Anticollision)", bytes([0xAA, 0xBB, 0x02, 0x21, 0x00, 0x23])),
    ("AA BB 自动读卡号 (Auto Read UID)", bytes([0xAA, 0xBB, 0x02, 0x25, 0x00, 0x27])),
    # 3. STX (0x02 ... 0x03) 工业协议
    ("STX 寻卡指令", bytes([0x02, 0x00, 0x02, 0x20, 0x22, 0x03])),
    ("STX 读卡号指令", bytes([0x02, 0x00, 0x02, 0x21, 0x23, 0x03])),
    # 4. 微朗/金木雨/德卡
    ("微朗选卡 (0x25)", bytes([0x02, 0x00, 0x01, 0x25, 0x24, 0x03])),
    # 5. 原生单字节射频唤醒 (有些简易MCU直接透传)
    ("ISO14443 REQA 原生码 0x26", bytes([0x26])),
    ("ISO14443 WUPA 原生码 0x52", bytes([0x52])),
]

def scan_card_on_port(port="COM3"):
    print(f"\n{'='*60}")
    print(f"[*] 启动读卡器贴卡探测 (端口: {port})")
    print(f"[*] 目标卡片类型: ISO 14443-3A")
    print(f"{'='*60}\n")
    
    bauds = [115200, 9600, 38400, 57600, 19200]
    
    found = False
    
    for baud in bauds:
        print(f"[+] 正在以波特率 {baud} 探测...")
        try:
            ser = serial.Serial(port, baudrate=baud, timeout=0.1)
            ser.dtr = False
            ser.rts = False
        except Exception as e:
            print(f"    打开失败: {e}")
            continue

        ser.reset_input_buffer()
        ser.reset_output_buffer()

        # 1. 检查是否有卡片感应自动上报 (监听 0.5s)
        time.sleep(0.3)
        if ser.in_waiting > 0:
            rx = ser.read(ser.in_waiting)
            if set(rx) != {0}: # 排除纯零
                print(f"\n[★ 命中! 读卡器感应到 ISO 14443-3A 卡片主动上报! ★]")
                print(f"  波特率: {baud}")
                print(f"  HEX: {format_hex(rx)}")
                print(f"  ASC: {rx.decode('latin1', errors='replace')}")
                found = True

        # 2. 依次测试命令
        for name, cmd in TEST_COMMANDS:
            ser.reset_input_buffer()
            ser.write(cmd)
            ser.flush()
            time.sleep(0.06)
            
            if ser.in_waiting > 0:
                rx = ser.read(ser.in_waiting)
                # 排除硬件相邻引脚串扰产生的连零或固定串扰字
                if rx and len(rx) > 0 and set(rx) != {0} and rx != b"\x00\x05\x03\x20\x05\x23":
                    print(f"\n[★ 命中命令响应! ★]")
                    print(f"  波特率: {baud}")
                    print(f"  触发指令: {name}")
                    print(f"  发送数据: {format_hex(cmd)}")
                    print(f"  返回数据: {format_hex(rx)} (长度: {len(rx)})")
                    print(f"  ASCII: {rx.decode('latin1', errors='replace')}")
                    found = True

        ser.close()

    print(f"\n{'='*60}")
    if found:
        print("[✔] 成功捕获到针对 ISO 14443-3A 卡片的数据回包！")
    else:
        print("[i] 本轮测试未捕获到有效回包。")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    scan_card_on_port("COM3")
