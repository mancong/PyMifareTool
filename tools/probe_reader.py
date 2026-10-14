# -*- coding: utf-8 -*-
import sys
import time
import serial

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def format_hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)

def test_specific_baud(port="COM3", baud=38400):
    print(f"\n{'='*50}")
    print(f"[*] 深度测试串口 {port} @ {baud} bps")
    print(f"{'='*50}")
    
    try:
        ser = serial.Serial(port, baudrate=baud, timeout=0.5, write_timeout=0.5)
    except Exception as e:
        print(f"打开串口失败: {e}")
        return

    # 测试 1: 发送 PN532 唤醒序列 (长前导码 + SAMConfiguration)
    print("\n--- 步骤 1: 发送 PN532 唤醒与正常模式配置 ---")
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    # 唤醒前导序列
    wakeup = b"\x55\x55" + b"\x00" * 10
    ser.write(wakeup)
    ser.flush()
    time.sleep(0.05) # 必须等待晶振稳定
    
    # SAMConfiguration 帧
    sam_cmd = bytes([0x00, 0x00, 0xFF, 0x03, 0xFD, 0xD4, 0x14, 0x01, 0x17, 0x00])
    ser.write(sam_cmd)
    ser.flush()
    time.sleep(0.1)
    res = ser.read(ser.in_waiting or 64)
    print(f"  发送 SAMConfig: {format_hex(sam_cmd)}")
    print(f"  收到响应:       {format_hex(res)} (长度: {len(res)})")

    # 测试 2: 发送 GetFirmwareVersion
    print("\n--- 步骤 2: 发送 GetFirmwareVersion (0xD4 0x02) ---")
    ser.reset_input_buffer()
    fw_cmd = bytes([0x00, 0x00, 0xFF, 0x02, 0xFE, 0xD4, 0x02, 0x2A, 0x00])
    ser.write(fw_cmd)
    ser.flush()
    time.sleep(0.1)
    res = ser.read(ser.in_waiting or 64)
    print(f"  发送 GetFirmware: {format_hex(fw_cmd)}")
    print(f"  收到响应:         {format_hex(res)} (长度: {len(res)})")

    # 测试 3: 发送普通单字节测试 (排查是否有 Echo 或特定单字节协议)
    print("\n--- 步骤 3: 单字节与常规 RFID 指令探测 ---")
    test_frames = [
        ("寻卡 InListPassiveTarget", bytes([0x00, 0x00, 0xFF, 0x04, 0xFC, 0xD4, 0x4A, 0x01, 0x00, 0xE1, 0x00])),
        ("通用 AA BB 寻卡", bytes([0xAA, 0xBB, 0x03, 0x20, 0x01, 0x26, 0x4A])),
        ("通用 AA BB 读信息", bytes([0xAA, 0xBB, 0x02, 0x10, 0x00, 0x12])),
        ("STX 寻卡", bytes([0x02, 0x00, 0x02, 0x20, 0x22, 0x03])),
        ("单字节 0x55", bytes([0x55])),
        ("单字节 0xAA", bytes([0xAA])),
        ("单字节 0x02", bytes([0x02])),
        ("单字节 0x20 (寻卡常数)", bytes([0x20])),
        ("回车换行 CRLF", b"\r\n")
    ]
    
    for name, cmd in test_frames:
        ser.reset_input_buffer()
        ser.write(cmd)
        ser.flush()
        time.sleep(0.08)
        res = ser.read(ser.in_waiting or 64)
        if res:
            print(f"  [有响应] {name}: 发送 [{format_hex(cmd)}] -> 收到 [{format_hex(res)}]")
        else:
            print(f"  [无响应] {name}")

    ser.close()

if __name__ == "__main__":
    # 先测 38400，再测 115200，再测 9600
    for b in [38400, 115200, 9600, 19200]:
        test_specific_baud("COM3", b)
