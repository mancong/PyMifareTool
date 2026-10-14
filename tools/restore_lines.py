# -*- coding: utf-8 -*-
import time
import serial

try:
    ser = serial.Serial("COM3", baudrate=115200, timeout=0.1)
    # 释放控制线
    ser.dtr = False
    ser.rts = False
    time.sleep(0.1)
    ser.close()
    print("DTR/RTS lines reset to False successfully.")
except Exception as e:
    print(f"Error: {e}")
