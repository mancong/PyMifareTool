# -*- coding: utf-8 -*-
"""
PyMifareTool - 纯被动无干扰刷卡监听探针
绝对不向读卡器发送任何字节，只被动接收读卡器单片机在刷卡时主动吐出的数据！
"""

import sys
import time
import serial

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def format_hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)

def listen_port(port="COM3", baud=9600, duration=15):
    print(f"\n{'='*60}")
    print(f"[*] 启动纯被动监听: 端口 {port} | 波特率 {baud} bps")
    print(f"[*] 持续监听时间: {duration} 秒")
    print(f"[*] >>> 请现在将 NFC 卡片贴向读卡器（观察红灯灭一秒再亮的过程）<<<")
    print(f"{'='*60}\n")
    
    try:
        # 打开串口，超时 0.2 秒
        ser = serial.Serial(port, baudrate=baud, timeout=0.2)
        # 保持与当前上电一致，不触发硬件复位
        ser.dtr = False
        ser.rts = False
    except Exception as e:
        print(f"[-] 打开串口失败: {e}")
        return None

    ser.reset_input_buffer()
    
    start_time = time.time()
    received_bytes = bytearray()
    
    while time.time() - start_time < duration:
        n = ser.in_waiting
        if n > 0:
            chunk = ser.read(n)
            received_bytes.extend(chunk)
            print(f"[★ 成功捕获到刷卡数据! ★]")
            print(f"  HEX:    {format_hex(chunk)}")
            print(f"  ASCII:  {chunk.decode('latin1', errors='replace')}")
            # 如果是 ASCII 字符，尝试 utf-8 / gbk 解码
            try:
                print(f"  文本内容: {chunk.decode('gbk', errors='ignore')}")
            except Exception:
                pass
            print(f"  总长度:  {len(received_bytes)} 字节\n")
            # 继续监听 1 秒捕获完整后续数据
            time.sleep(1.0)
            if ser.in_waiting > 0:
                more = ser.read(ser.in_waiting)
                received_bytes.extend(more)
                print(f"  后续追加: {format_hex(more)}")
            break
        time.sleep(0.05)
        
    ser.close()
    
    if not received_bytes:
        print(f"[-] 在波特率 {baud} 下暂未捕获到数据。")
        return None
    return bytes(received_bytes)

if __name__ == "__main__":
    b = 9600
    if len(sys.argv) > 1:
        b = int(sys.argv[1])
    dur = 15
    if len(sys.argv) > 2:
        dur = int(sys.argv[2])
    listen_port("COM3", b, dur)
