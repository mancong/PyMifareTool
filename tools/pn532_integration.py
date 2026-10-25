# -*- coding: utf-8 -*-
"""
PyMifareTool - PN532/PCR532 硬件联调脚本 (走项目自身适配器真实链路)
严格硬件红线 1: DTR=False / RTS=False
用法: python tools/pn532_integration.py [PORT] [STAGE]
  STAGE: handshake | poll | read | crack
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import serial
from core.adapters.pn532_adapter import PN532Adapter


class LoggingSerial(serial.Serial):
    """带原始 TX/RX 帧日志的串口包装，便于联调观察 HSU 帧"""

    def write(self, data):
        hexs = " ".join(f"{b:02X}" for b in data)
        print(f"  [TX] {hexs}", flush=True)
        return super().write(data)

    def read(self, size=1):
        data = super().read(size)
        if data:
            hexs = " ".join(f"{b:02X}" for b in data)
            print(f"  [RX] {hexs}", flush=True)
        return data


def open_port(port: str, baud: int = 115200) -> serial.Serial:
    ser = LoggingSerial(port=port, baudrate=baud, timeout=0.1)
    ser.dtr = False
    ser.rts = False
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    return ser


def stage_handshake(ser) -> PN532Adapter:
    print("=== STAGE: handshake (唤醒 + GetFirmwareVersion + SAMConfiguration) ===", flush=True)
    ad = PN532Adapter()
    ok = ad.init_device(ser)
    print(f"  init_device -> {ok}", flush=True)
    print(f"  firmware_info -> {ad.firmware_info}", flush=True)
    return ad


def stage_poll(ser, ad: PN532Adapter):
    print("=== STAGE: poll (Type A 优先, 回退 Type B 二代证) ===", flush=True)
    for i in range(5):
        card = ad.poll_card(ser, timeout=0.5)
        if card:
            uid = card.get("uid_bytes", b"")
            print(f"  命中卡片 #{i}: UID={uid.hex().upper()} "
                  f"SAK={card.get('sak'):#04x} ATQA={card.get('atqa', b'').hex().upper()}", flush=True)
            conv = card.get("conversions", {})
            if conv:
                print(f"  换算: {conv}", flush=True)
            return card
        print(f"  第 {i} 次寻卡: 无卡", flush=True)
        time.sleep(0.2)
    return None


def stage_read(ser, ad: PN532Adapter):
    print("=== STAGE: read (逐扇区认证 + 读块) ===", flush=True)
    from core.services.card_worker import DEFAULT_KEYS_HEX
    keys = [bytes.fromhex(k) for k in DEFAULT_KEYS_HEX]

    card = ad.poll_card(ser, timeout=0.5)
    if not card:
        print("  无卡，终止", flush=True)
        return
    uid = card["uid_bytes"]
    print(f"  卡片 UID={uid.hex().upper()} 已缓存", flush=True)

    total_ok = 0
    for sector in range(16):
        trailer = sector * 4 + 3
        key_a = key_b = None
        for k in keys:
            if ad.authenticate(ser, trailer, "A", k, uid, timeout=0.25):
                key_a = k
                break
        for k in keys:
            if ad.authenticate(ser, trailer, "B", k, uid, timeout=0.25):
                key_b = k
                break
        if not (key_a or key_b):
            print(f"  S{sector:02d}: 认证失败 (无匹配默认密钥)", flush=True)
            continue
        # 认证成功后读本扇区 4 块
        lines = []
        for bi in range(4):
            blk = sector * 4 + bi
            # 每块读前需重新认证
            auth_key = key_a or key_b
            ad.authenticate(ser, trailer, "A" if key_a else "B", auth_key, uid, timeout=0.25)
            data = ad.read_block(ser, blk, timeout=0.25)
            if data:
                lines.append(f"B{blk:02d}={data.hex().upper()}")
                total_ok += 1
        print(f"  S{sector:02d}: KeyA={key_a.hex().upper() if key_a else '----'} "
              f"KeyB={key_b.hex().upper() if key_b else '----'}", flush=True)
        for l in lines:
            print(f"      {l}", flush=True)
    print(f"  读取成功块数: {total_ok}", flush=True)


def stage_write(ser, ad: PN532Adapter):
    print("=== STAGE: write (写 Block 4/5 -> 回读校验 -> 还原) ===", flush=True)
    from core.services.card_worker import DEFAULT_KEYS_HEX
    keys = [bytes.fromhex(k) for k in DEFAULT_KEYS_HEX]

    card = ad.poll_card(ser, timeout=0.5)
    if not card:
        print("  无卡，终止", flush=True)
        return
    uid = card["uid_bytes"]
    trailer = 7  # 扇区 1 尾块
    auth_ok = False
    for k in keys:
        if ad.authenticate(ser, trailer, "A", k, uid, timeout=0.25):
            auth_ok = True
            break
    print(f"  扇区1认证: {auth_ok}", flush=True)

    pattern = bytes.fromhex("DEADBEEF0123456789ABCDEF0F1E2D3C")
    print(f"  写入 Block 4: {pattern.hex().upper()}", flush=True)
    ad.authenticate(ser, trailer, "A", keys[0], uid, timeout=0.25)
    w1 = ad.write_block(ser, 4, pattern, timeout=0.3)
    ad.authenticate(ser, trailer, "A", keys[0], uid, timeout=0.25)
    r1 = ad.read_block(ser, 4, timeout=0.3)
    print(f"  write={w1} | read_back={r1.hex().upper() if r1 else None} | "
          f"MATCH={r1 == pattern}", flush=True)

    zero = bytes(16)
    print("  还原 Block 4 -> 全 00", flush=True)
    ad.authenticate(ser, trailer, "A", keys[0], uid, timeout=0.25)
    ad.write_block(ser, 4, zero, timeout=0.3)
    ad.authenticate(ser, trailer, "A", keys[0], uid, timeout=0.25)
    r2 = ad.read_block(ser, 4, timeout=0.3)
    print(f"  还原后读回: {r2.hex().upper() if r2 else None}", flush=True)


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "COM3"
    stage = sys.argv[2] if len(sys.argv) > 2 else "handshake"
    print(f"# 联调目标: {port} @ 115200 (DTR/RTS=False)", flush=True)

    ser = open_port(port, 115200)
    try:
        ad = stage_handshake(ser)
        if stage == "poll":
            stage_poll(ser, ad)
        elif stage in ("read", "crack"):
            stage_read(ser, ad)
        elif stage == "write":
            stage_write(ser, ad)
    finally:
        ser.close()
        print("# 串口已关闭", flush=True)


if __name__ == "__main__":
    main()
