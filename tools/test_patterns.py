# -*- coding: utf-8 -*-
import sys
import time
import serial

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def test():
    ser = serial.Serial("COM3", baudrate=38400, timeout=0.1)
    
    test_cases = [
        ("00", b"\x00"),
        ("00 00", b"\x00\x00"),
        ("00 00 00", b"\x00\x00\x00"),
        ("00 00 00 00", b"\x00\x00\x00\x00"),
        ("FF", b"\xFF"),
        ("FF FF", b"\xFF\xFF"),
        ("00 FF", b"\x00\xFF"),
        ("FF 00", b"\xFF\x00"),
        ("00 00 FF", b"\x00\x00\xFF"),
        ("00 FF 00", b"\x00\xFF\x00"),
        ("01 02 03", b"\x01\x02\x03"),
        ("55 55 55", b"\x55\x55\x55"),
        ("AA AA AA", b"\xAA\xAA\xAA"),
    ]

    for name, data in test_cases:
        ser.reset_input_buffer()
        ser.write(data)
        ser.flush()
        time.sleep(0.05)
        rx = ser.read(ser.in_waiting or 32)
        print(f"TX: {name:15s} -> RX ({len(rx):2d}B): {' '.join(f'{x:02X}' for x in rx)}")

    ser.close()

if __name__ == "__main__":
    test()
