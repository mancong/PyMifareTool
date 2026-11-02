# -*- coding: utf-8 -*-
"""
测试候选的主机下发指令帧格式 (COM3 @ 38400 bps)
验证读卡器主动应答 (在卡片放置在天线上时测试)
"""

import sys
import time
from typing import List, Tuple

import serial

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def calc_xor(data: bytes) -> int:
    res = 0
    for b in data:
        res ^= b
    return res


def build_candidates() -> List[Tuple[str, bytes]]:
    """构建全部候选下行帧（纯字节串，便于单元测试直接校验）"""
    # AABB 认证帧: AA BB | LEN CMD Sector KeyType Key(6) | BCC
    login_body = [0x0A, 0x02, 0x00, 0xAA] + [0xFF] * 6
    login_frame = [0xAA, 0xBB] + login_body + [calc_xor(bytes(login_body))]

    return [
        # 格式 A: 纯 AABB + 1字节Len + CMD + BCC (类似读卡器回包风格)
        ("AABB 寻卡 0x01 (单字节Len)", bytes([0xAA, 0xBB, 0x02, 0x01, 0x02 ^ 0x01])),

        # 格式 B: AABB + 2字节Len + 2字节DeviceID + CMD + BCC (SL600风格)
        ("SL600 寻卡 0x01 (带DeviceID 00 00)", bytes([0xAA, 0xBB, 0x03, 0x00, 0x00, 0x00, 0x01, 0x03 ^ 0x01])),

        # 格式 C: SL018/031 标准 BA 帧头
        ("SL018/031 BA 帧头 寻卡 0x01", bytes([0xBA, 0x02, 0x01, 0xBA ^ 0x02 ^ 0x01])),

        # 格式 D: AABB 认证扇区0 (CMD 0x02, Sector 0, KeyA FFFFFFFFFFFF)
        ("AABB 认证扇区0 (CMD 0x02)", bytes(login_frame)),

        # 格式 E: AABB 读块0 (CMD 0x03)
        ("AABB 读块0 (CMD 0x03)", bytes([0xAA, 0xBB, 0x03, 0x03, 0x00, 0x03 ^ 0x03 ^ 0x00])),

        # 格式 F: 蜂鸣器 (CMD 0x06 / 0x08)
        ("AABB 蜂鸣器", bytes([0xAA, 0xBB, 0x02, 0x06, 0x02 ^ 0x06])),
    ]


def test_candidates():
    ser = serial.Serial("COM3", baudrate=38400, timeout=0.2)
    ser.dtr = False
    ser.rts = False

    candidates = build_candidates()

    print("=== 发送候选下发帧并观察是否有即时回包 ===")
    for name, cmd in candidates:
        ser.reset_input_buffer()
        ser.write(cmd)
        ser.flush()
        time.sleep(0.08)

        rx = ser.read(ser.in_waiting or 64)
        if rx:
            print(f"[★ 响应! ★] {name}:")
            print(f"      TX: {' '.join(f'{b:02X}' for b in cmd)}")
            print(f"      RX: {' '.join(f'{b:02X}' for b in rx)}")
        else:
            print(f"[无响应] {name} (TX: {' '.join(f'{b:02X}' for b in cmd)})")

    ser.close()


if __name__ == "__main__":
    test_candidates()
