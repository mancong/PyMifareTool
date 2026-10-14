# -*- coding: utf-8 -*-
import sys
import time
import serial

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def test_all():
    bauds = [9600, 14400, 19200, 28800, 38400, 57600, 115200, 230400, 460800]
    ack = bytes([0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00])
    fw = bytes([0x00, 0x00, 0xFF, 0x02, 0xFE, 0xD4, 0x02, 0x2A, 0x00])

    print("=== 全波特率测试 PN532 ACK 与 GetFirmware ===")
    for b in bauds:
        try:
            ser = serial.Serial("COM3", baudrate=b, timeout=0.2)
            ser.reset_input_buffer()
            ser.reset_output_buffer()

            # 先发 ACK
            ser.write(ack)
            ser.flush()
            time.sleep(0.06)
            rx_ack = ser.read(ser.in_waiting or 30)

            # 再发 GetFirmware
            ser.reset_input_buffer()
            ser.write(fw)
            ser.flush()
            time.sleep(0.06)
            rx_fw = ser.read(ser.in_waiting or 30)

            ser.close()

            if rx_ack or rx_fw:
                print(f"[响应!] Baud {b:7d}:")
                if rx_ack:
                    print(f"       ACK 响应 ({len(rx_ack)}B): {' '.join(f'{x:02X}' for x in rx_ack)}")
                if rx_fw:
                    print(f"       FW  响应 ({len(rx_fw)}B): {' '.join(f'{x:02X}' for x in rx_fw)}")
            else:
                print(f"       Baud {b:7d}: (无响应)")
        except Exception as e:
            print(f"       Baud {b:7d}: 错误 {e}")

if __name__ == "__main__":
    test_all()
