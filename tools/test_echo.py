# -*- coding: utf-8 -*-
import sys
import time
import serial

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def test_pattern():
    ser = serial.Serial("COM3", baudrate=38400, timeout=0.2)
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    
    # 1. 测单字节 0x55
    ser.write(b"\x55")
    ser.flush()
    time.sleep(0.05)
    rx1 = ser.read(ser.in_waiting or 10)
    print(f"Send 55 -> Received: {' '.join(f'{x:02X}' for x in rx1)}")

    # 2. 测单字节 0x00
    ser.write(b"\x00")
    ser.flush()
    time.sleep(0.05)
    rx2 = ser.read(ser.in_waiting or 10)
    print(f"Send 00 -> Received: {' '.join(f'{x:02X}' for x in rx2)}")

    # 3. 测单字节 0xFF
    ser.write(b"\xFF")
    ser.flush()
    time.sleep(0.05)
    rx3 = ser.read(ser.in_waiting or 10)
    print(f"Send FF -> Received: {' '.join(f'{x:02X}' for x in rx3)}")

    # 4. 测 00 00 FF 00 FF 00 (ACK)
    ack = bytes([0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00])
    ser.write(ack)
    ser.flush()
    time.sleep(0.05)
    rx4 = ser.read(ser.in_waiting or 20)
    print(f"Send ACK -> Received: {' '.join(f'{x:02X}' for x in rx4)}")

    # 5. 测 PN532 GetFirmwareVersion
    fw = bytes([0x00, 0x00, 0xFF, 0x02, 0xFE, 0xD4, 0x02, 0x2A, 0x00])
    ser.write(fw)
    ser.flush()
    time.sleep(0.1)
    rx5 = ser.read(ser.in_waiting or 30)
    print(f"Send GetFirmware -> Received: {' '.join(f'{x:02X}' for x in rx5)}")

    ser.close()

if __name__ == "__main__":
    test_pattern()
