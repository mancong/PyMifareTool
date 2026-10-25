# -*- coding: utf-8 -*-
"""
精细打印每一个 TX/RX 报文，定位 APDU 交换的真实细节
"""
import sys
import time
import serial

sys.stdout.reconfigure(encoding="utf-8")

def build_hsu_frame(cmd, payload=b""):
    tfi = 0xD4
    data = bytes([tfi, cmd]) + bytes(payload)
    length = len(data)
    lcs = (-length) & 0xFF
    dcs = (-sum(data)) & 0xFF
    return bytes([0x00, 0x00, 0xFF, length, lcs]) + data + bytes([dcs, 0x00])

def parse_frames(rx_bytes):
    frames = []
    i = 0
    while i < len(rx_bytes):
        idx = rx_bytes.find(b"\x00\x00\xFF", i)
        if idx == -1:
            break
        if idx + 6 <= len(rx_bytes) and rx_bytes[idx:idx+6] == b"\x00\x00\xFF\x00\xFF\x00":
            frames.append(("ACK", b""))
            i = idx + 6
            continue
        if idx + 5 <= len(rx_bytes):
            length = rx_bytes[idx+3]
            lcs = rx_bytes[idx+4]
            if (length + lcs) & 0xFF == 0:
                total = idx + 5 + length + 2
                if len(rx_bytes) >= total:
                    body = rx_bytes[idx+5 : idx+5+length]
                    dcs = rx_bytes[idx+5+length]
                    if (sum(body) + dcs) & 0xFF == 0:
                        tfi = body[0]
                        cmd = body[1]
                        payload = body[2:]
                        frames.append(("DATA", cmd, payload))
                        i = total
                        continue
        i = idx + 1
    return frames

ser = serial.Serial("COM3", 115200, timeout=0.1)
ser.dtr = False
ser.rts = False
ser.reset_input_buffer()
ser.reset_output_buffer()

def execute(cmd, payload=b"", timeout=0.6):
    tx = build_hsu_frame(cmd, payload)
    print(f"\n[TX] cmd=0x{cmd:02X}, len={len(payload)}: {tx.hex().upper()}")
    ser.write(tx)
    ser.flush()
    start = time.time()
    rx_buf = bytearray()
    while time.time() - start < timeout:
        if ser.in_waiting > 0:
            c = ser.read(ser.in_waiting)
            rx_buf.extend(c)
            # 尝试解析
            frames = parse_frames(bytes(rx_buf))
            data_frames = [f for f in frames if f[0] == "DATA"]
            if data_frames:
                print(f"[RX] 收到完整应答: {rx_buf.hex().upper()}")
                for f in frames:
                    if f[0] == "ACK":
                        print("  -> <ACK>")
                    elif f[0] == "DATA":
                        print(f"  -> <DATA> cmd=0x{f[1]:02X}, payload={f[2].hex().upper()}")
                return data_frames[0]
        time.sleep(0.01)
    print(f"[RX 超时] 收到原始碎片: {rx_buf.hex().upper()}")
    return None

# 1. 唤醒
ser.write(bytes([0x55] * 16 + [0x00, 0x00, 0x00]))
ser.flush()
time.sleep(0.05)
ser.reset_input_buffer()

# 2. SAM
execute(0x14, bytes([0x01, 0x14, 0x01]))

# 3. 寻卡
target_frame = execute(0x4A, bytes([0x01, 0x00]))
if not target_frame:
    print("未寻到卡")
    ser.close()
    sys.exit(0)

# 4. 执行选卡应用 APDU
# 交通联合 AID: A0 00 00 03 33 01 01 01 -> APDU: 00 A4 04 00 08 A0 00 00 03 33 01 01 01
apdu_tunion = bytes.fromhex("00A4040008A000000333010101")
print("\n--- 发送 APDU: 选择全国交通联合 ---")
# 注意 InDataExchange 的参数格式: [Tg (1字节)] + [DataOut]
execute(0x40, bytes([0x01]) + apdu_tunion, timeout=0.8)

# 5. 尝试住建部城市互联互通: A0 00 00 00 03 86 98 07 01
print("\n--- 发送 APDU: 选择住建部/城市公交 ---")
apdu_city = bytes.fromhex("00A4040009A00000000386980701")
execute(0x40, bytes([0x01]) + apdu_city, timeout=0.8)

# 6. 尝试选择 3F00 (主目录)
print("\n--- 发送 APDU: 选择 MF 3F00 ---")
apdu_mf = bytes.fromhex("00A40000023F00")
execute(0x40, bytes([0x01]) + apdu_mf, timeout=0.8)

# 7. 尝试选择 1001 (公共交通应用)
print("\n--- 发送 APDU: 选择 DF 1001 ---")
apdu_1001 = bytes.fromhex("00A40000021001")
execute(0x40, bytes([0x01]) + apdu_1001, timeout=0.8)

ser.close()
