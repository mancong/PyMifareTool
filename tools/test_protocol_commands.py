# -*- coding: utf-8 -*-
"""
PyMifareTool - 协议指令集探针
验证基于 AA BB 帧结构的读卡器指令响应 (波特率 38400)
"""

import sys
import time
import serial

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def make_frame(cmd: int, data: bytes = b"") -> bytes:
    # 长度 = CMD(1) + DATA(N) + BCC(1)
    length = len(data) + 2
    # 校验和 BCC = LEN ^ CMD ^ DATA...
    bcc = length ^ cmd
    for b in data:
        bcc ^= b
    return bytes([0xAA, 0xBB, length, cmd]) + data + bytes([bcc])

def test_commands():
    ser = serial.Serial("COM3", baudrate=38400, timeout=0.2)
    ser.dtr = False
    ser.rts = False
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    print("=== 测试读卡器常用指令 (AA BB 格式) ===")
    
    # 候选指令测试列表
    candidates = [
        # 1. 蜂鸣器测试
        ("蜂鸣器鸣响 0x06", make_frame(0x06, bytes([0x01]))),
        ("蜂鸣器鸣响 0x04", make_frame(0x04, bytes([0x01]))),
        ("蜂鸣器鸣响 0x13", make_frame(0x13, bytes([0x01, 0x01]))),
        # 2. 读版本 / 设备信息
        ("获取设备版本 0x10", make_frame(0x10)),
        ("获取设备版本 0x01", make_frame(0x01)),
        # 3. 主动寻卡 / 选卡 (Request/Anticoll)
        ("主动寻卡指令 0x02", make_frame(0x02, bytes([0x26]))),
        ("主动寻卡指令 0x20", make_frame(0x20, bytes([0x01, 0x26]))),
        # 4. 读块0 (带默认Key FFFFFFFFFFFF)
        ("一键读块0 (CMD 0x03)", make_frame(0x03, bytes([0x00, 0x60]) + b"\xFF"*6)),
        ("一键读块0 (CMD 0x21)", make_frame(0x21, bytes([0x00, 0x60]) + b"\xFF"*6)),
    ]

    for name, frame in candidates:
        ser.reset_input_buffer()
        ser.write(frame)
        ser.flush()
        time.sleep(0.06)
        
        rx = ser.read(ser.in_waiting or 64)
        if rx:
            print(f"[★ 响应!] {name}:")
            print(f"       发送: {' '.join(f'{b:02X}' for b in frame)}")
            print(f"       返回: {' '.join(f'{b:02X}' for b in rx)}")
        else:
            print(f"[无响应] {name}")

    ser.close()

if __name__ == "__main__":
    test_commands()
