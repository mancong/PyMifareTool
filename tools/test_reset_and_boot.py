# -*- coding: utf-8 -*-
import sys
import time
import serial

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def format_hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)

def test_dtr_rts():
    print("=== 测试 DTR / RTS 复位线状态与单片机启动日志 ===")
    
    # 测试不同的 DTR / RTS 组合 (可能高电平复位或低电平复位)
    combos = [
        ("DTR=False, RTS=False (高电平释放)", False, False),
        ("DTR=True,  RTS=False", True, False),
        ("DTR=False, RTS=True", False, True),
        ("DTR=True,  RTS=True", True, True),
    ]

    bauds = [115200, 9600, 57600, 38400, 19200]

    for b in bauds:
        for desc, dtr_val, rts_val in combos:
            try:
                ser = serial.Serial("COM3", baudrate=b, timeout=0.3)
                ser.dtr = dtr_val
                ser.rts = rts_val
                ser.reset_input_buffer()
                
                # 给予 MCU 启动时间
                time.sleep(0.3)
                boot_rx = ser.read(ser.in_waiting or 64)
                if boot_rx:
                    print(f"\n[★ 捕获到开机/释放复位数据! ★]")
                    print(f"  Baud: {b} | {desc}")
                    print(f"  HEX: {format_hex(boot_rx)}")
                    print(f"  ASC: {boot_rx.decode('latin1', errors='replace')}")

                # 发送通用探测（AT 或 寻卡）
                ser.reset_input_buffer()
                ser.write(b"AT\r\n")
                ser.flush()
                time.sleep(0.05)
                at_rx = ser.read(ser.in_waiting or 64)
                if at_rx:
                    print(f"  [AT响应] Baud: {b} | {desc} -> {format_hex(at_rx)}")

                ser.close()
            except Exception as e:
                pass

if __name__ == "__main__":
    test_dtr_rts()
