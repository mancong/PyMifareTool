# -*- coding: utf-8 -*-
import sys
import time
import serial

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def test_idle():
    print("Testing idle listening on COM3...")
    for b in [38400, 9600, 115200, 19200]:
        try:
            ser = serial.Serial("COM3", baudrate=b, timeout=0.1)
            ser.reset_input_buffer()
            time.sleep(1.0)
            n = ser.in_waiting
            if n > 0:
                data = ser.read(n)
                print(f"Baud {b}: Received {len(data)} bytes while IDLE: {' '.join(f'{x:02X}' for x in data)}")
            else:
                print(f"Baud {b}: Clean idle (no unsolicited data)")
            ser.close()
        except Exception as e:
            print(f"Baud {b}: Error {e}")

if __name__ == "__main__":
    test_idle()
