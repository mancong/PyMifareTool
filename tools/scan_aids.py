# -*- coding: utf-8 -*-
"""
探测用户卡片 (卡号 3104...) 的具体应用 AID 与文件系统
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
    ser.write(tx)
    ser.flush()
    start = time.time()
    rx_buf = bytearray()
    while time.time() - start < timeout:
        if ser.in_waiting > 0:
            c = ser.read(ser.in_waiting)
            rx_buf.extend(c)
            frames = parse_frames(bytes(rx_buf))
            data_frames = [f for f in frames if f[0] == "DATA"]
            if data_frames:
                return data_frames[0]
        time.sleep(0.005)
    return None

def apdu_exchange(apdu_hex, timeout=0.6):
    apdu = bytes.fromhex(apdu_hex.replace(" ", ""))
    payload = bytes([0x01]) + apdu
    res = execute(0x40, payload, timeout=timeout)
    if res and len(res) >= 3:
        data = res[2]
        if len(data) >= 3 and data[0] == 0x00:
            card_resp = data[1:]
            sw = card_resp[-2:].hex().upper()
            d = card_resp[:-2].hex().upper()
            return sw, d
    return "ERR", ""

# 初始化并寻卡
ser.write(bytes([0x55] * 16 + [0x00, 0x00, 0x00]))
ser.flush()
time.sleep(0.05)
execute(0x14, bytes([0x01, 0x14, 0x01]))
execute(0x4A, bytes([0x01, 0x00]))

print("开始多 AID 与目录深度扫描...")

# 常见的各种城市公交与交通卡 AID 列表
candidate_aids = [
    # 上海交通卡 / 申通地铁 / 城市一卡通
    ("上海公共交通卡 (SPTC DF01)", "00 A4 04 00 09 A0 00 00 00 03 86 98 07 01"),
    ("上海交通卡 地方应用 (A00000000386980701)", "00 A4 04 00 08 A0 00 00 00 03 86 98 07"),
    ("交通部交通联合 T-Union", "00 A4 04 00 08 A0 00 00 03 33 01 01 01"),
    ("交通联合 标准 AID 2", "00 A4 04 00 07 A0 00 00 03 33 01 01"),
    ("交通联合 标准 AID 3", "00 A4 04 00 09 A0 00 00 03 33 01 01 01 01"),
    ("住建部 9156 (DF01)", "00 A4 04 00 08 91 56 00 00 14 01 00 01"),
    ("住建部 9156 (DF02)", "00 A4 04 00 08 91 56 00 00 14 01 00 02"),
    ("住建部 D156", "00 A4 04 00 08 D1 56 00 00 14 01 00 01"),
    ("1PAY.SYS.DDF01 (PBOC PSE)", "00 A4 04 00 0E 31 50 41 59 2E 53 59 53 2E 44 44 46 30 31"),
    ("2PAY.SYS.DDF01 (PPSE)", "00 A4 04 00 0E 32 50 41 59 2E 53 59 53 2E 44 44 46 30 31"),
    ("PBOC 电子钱包 A000000333", "00 A4 04 00 05 A0 00 00 03 33"),
    ("PBOC 借记卡 (A0000000031010)", "00 A4 04 00 07 A0 00 00 00 03 10 10"),
    ("PBOC 贷记卡 (A0000000032010)", "00 A4 04 00 07 A0 00 00 00 03 20 10"),
    ("PBOC 准贷记卡 (A0000000033010)", "00 A4 04 00 07 A0 00 00 00 03 30 10"),
    ("深圳通 / 岭南通 (SZT)", "00 A4 04 00 03 53 5A 54"),
    ("武汉通 (WHT)", "00 A4 04 00 03 57 48 54"),
    ("羊城通 (YCT)", "00 A4 04 00 03 59 43 54"),
    ("北京一卡通", "00 A4 04 00 09 A0 00 00 00 03 86 98 07 01"),
    ("八达通", "00 A4 04 00 08 80 00 00 00 00 00 00 01"),
    # 按照 FID 选择文件
    ("选择主控 MF 3F00 (P1=00)", "00 A4 00 00 02 3F 00"),
    ("选择主控 MF 3F00 (P1=00, P2=00, Lc=0)", "00 A4 00 00 00"),
    ("选择 DF 1001 (P1=00)", "00 A4 00 00 02 10 01"),
    ("选择 DF 2001 (P1=00)", "00 A4 00 00 02 20 01"),
    ("选择 DF 0001 (P1=00)", "00 A4 00 00 02 00 01"),
    ("选择 DF DDF1 (P1=00)", "00 A4 00 00 02 DD F1"),
]

matched = []
for title, apdu in candidate_aids:
    sw, data = apdu_exchange(apdu)
    print(f"[{title}] -> SW: {sw}, Data: {data}")
    if sw in ("9000", "6100") or sw.startswith("61") or sw == "6283":
        print(f"   ⭐⭐⭐ 命中! SW={sw}, Data={data}")
        matched.append((title, apdu, sw, data))

# 如果命中了，继续探测数据
print("\n命中列表汇总:")
for m in matched:
    print(f"  * {m[0]} (SW={m[2]})")

ser.close()
