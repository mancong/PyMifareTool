# -*- coding: utf-8 -*-
import sys
import time
import serial

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def test_open():
    print("Testing if opening the port triggers anything...")
    ser = serial.Serial("COM3", baudrate=38400, timeout=0.1)
    time.sleep(0.1)
    n = ser.in_waiting
    if n > 0:
        data = ser.read(n)
        print(f"Immediately upon open: Received {len(data)} bytes: {' '.join(f'{x:02X}' for x in data)}")
    else:
        print("Immediately upon open: No data.")

    # 保持打开，连续发送不同指令
    cmds = [
        ("空操作(什么都不发，等待0.2s)", None),
        ("发送单字节 0x00", b"\x00"),
        ("发送单字节 0xFF", b"\xFF"),
        ("发送 00 00 FF", b"\x00\x00\xFF"),
        ("发送 PN532 ACK", bytes([0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00])),
        ("发送 PN532 GetFW", bytes([0x00, 0x00, 0xFF, 0x02, 0xFE, 0xD4, 0x02, 0x2A, 0x00])),
        ("发送 国产 AA BB 寻卡", bytes([0xAA, 0xBB, 0x03, 0x20, 0x01, 0x26, 0x4A])),
    ]

    for name, cmd in cmds:
        ser.reset_input_buffer()
        if cmd:
            ser.write(cmd)
            ser.flush()
        time.sleep(0.1)
        res = ser.read(ser.in_waiting or 32)
        print(f"{name:30s} -> 收到 ({len(res)}B): {' '.join(f'{x:02X}' for x in res)}")

    ser.close()

if __name__ == "__main__":
    test_open()
