# -*- coding: utf-8 -*-
import sys
import time
import serial

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def format_hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)

# 标准 PN532 指令帧
GET_FIRMWARE = bytes([0x00, 0x00, 0xFF, 0x02, 0xFE, 0xD4, 0x02, 0x2A, 0x00])
SAM_CONFIG = bytes([0x00, 0x00, 0xFF, 0x03, 0xFD, 0xD4, 0x14, 0x01, 0x17, 0x00])

def scan():
    bauds = [38400, 115200, 57600, 19200, 9600, 28800]
    parities = [
        ("None", serial.PARITY_NONE),
        ("Even", serial.PARITY_EVEN),
        ("Odd",  serial.PARITY_ODD)
    ]

    for baud in bauds:
        for p_name, parity in parities:
            try:
                ser = serial.Serial(
                    port="COM3",
                    baudrate=baud,
                    bytesize=serial.EIGHTBITS,
                    parity=parity,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.3
                )
            except Exception:
                continue

            ser.reset_input_buffer()
            ser.reset_output_buffer()

            # 发送 GetFirmwareVersion
            ser.write(GET_FIRMWARE)
            ser.flush()
            time.sleep(0.08)
            
            rx = ser.read(ser.in_waiting or 64)
            if rx:
                print(f"[命中] Baud: {baud:6d} | Parity: {p_name:4s} | RX ({len(rx)}B): {format_hex(rx)}")
                # 如果还有后续数据（比如 ACK 之后的应答帧），再多等 0.1s 读一下
                time.sleep(0.1)
                more = ser.read(ser.in_waiting or 64)
                if more:
                    print(f"       后续完整帧: {format_hex(more)}")
            ser.close()

if __name__ == "__main__":
    scan()
