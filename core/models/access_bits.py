# -*- coding: utf-8 -*-
"""
PyMifareTool - M1 扇区控制字 (Access Bits) 权限位运算编解码模型
遵循 NXP 官方 AN1305 / MF1S50 标准规范
"""

from typing import List, Tuple, Dict, Any


class AccessBitsEncoder:
    """
    M1 扇区控制字 (Access Bits) 编码器
    根据 Block 0~2 和 Trailer (Block 3) 的 (C1, C2, C3) 状态生成合法的 4 字节控制字
    """

    @classmethod
    def encode(cls, configs: List[Tuple[int, int, int]], user_byte: int = 0x69) -> bytes:
        """
        configs: 长度为 4 的列表，每项为 (C1, C2, C3) 元组 (0 或 1)
        user_byte: Byte 9 厂商备用/通用字节，默认 0x69
        """
        if len(configs) != 4:
            raise ValueError("必须提供 4 个块的 (C1, C2, C3) 配置")

        b6 = 0
        b7 = 0
        b8 = 0

        for i in range(4):
            c1, c2, c3 = configs[i]
            c1 = 1 if c1 else 0
            c2 = 1 if c2 else 0
            c3 = 1 if c3 else 0

            c1_inv = 1 - c1
            c2_inv = 1 - c2
            c3_inv = 1 - c3

            # b6: 低4位为 c1_inv, 高4位为 c2_inv
            b6 |= (c1_inv << i)
            b6 |= (c2_inv << (4 + i))

            # b7: 低4位为 c3_inv, 高4位为 c1_raw
            b7 |= (c3_inv << i)
            b7 |= (c1 << (4 + i))

            # b8: 低4位为 c2_raw, 高4位为 c3_raw
            b8 |= (c2 << i)
            b8 |= (c3 << (4 + i))

        return bytes([b6, b7, b8, user_byte & 0xFF])


class AccessBitsDecoder:
    """
    M1 扇区控制字 (Access Bits) 完整解析器
    按照 NXP 官方 AN1305 标准, 从 4 字节控制位中提取 C1/C2/C3 并映射权限
    """

    DATA_BLOCK_ACCESS = {
        (0, 0, 0): {"read": "KeyA|B", "write": "KeyA|B", "increment": "KeyA|B", "dec_transfer_restore": "KeyA|B",
                     "desc": "可用KeyA/B自由读写、增减值 (出厂默认)"},
        (0, 1, 0): {"read": "KeyA|B", "write": "Never",  "increment": "Never",  "dec_transfer_restore": "Never",
                     "desc": "KeyA/B可读, 永不可写 (只读保护)"},
        (1, 0, 0): {"read": "KeyA|B", "write": "KeyB",   "increment": "Never",  "dec_transfer_restore": "Never",
                     "desc": "KeyA/B可读, 仅KeyB可写"},
        (1, 1, 0): {"read": "KeyA|B", "write": "KeyB",   "increment": "KeyB",   "dec_transfer_restore": "KeyA|B",
                     "desc": "KeyA/B可读, KeyB可写/增值, 任意Key可减值"},
        (0, 0, 1): {"read": "KeyA|B", "write": "Never",  "increment": "Never",  "dec_transfer_restore": "KeyA|B",
                     "desc": "KeyA/B可读, 任意Key可减值/转存/恢复"},
        (0, 1, 1): {"read": "KeyB",   "write": "KeyB",   "increment": "Never",  "dec_transfer_restore": "Never",
                     "desc": "仅KeyB可读写"},
        (1, 0, 1): {"read": "KeyB",   "write": "Never",  "increment": "Never",  "dec_transfer_restore": "Never",
                     "desc": "仅KeyB可读, 永不可写"},
        (1, 1, 1): {"read": "Never",  "write": "Never",  "increment": "Never",  "dec_transfer_restore": "Never",
                     "desc": "完全锁死 (任何Key均无权限)"},
    }

    TRAILER_ACCESS = {
        (0, 0, 0): {"key_a_read": "Never",  "key_a_write": "KeyA",  "access_read": "KeyA",
                     "access_write": "Never", "key_b_read": "KeyA",  "key_b_write": "KeyA",
                     "desc": "出厂默认: KeyA可修改KeyA/KeyB, 可读控制字/KeyB"},
        (0, 1, 0): {"key_a_read": "Never",  "key_a_write": "Never", "access_read": "KeyA",
                     "access_write": "Never", "key_b_read": "KeyA",  "key_b_write": "Never",
                     "desc": "只读保护: 所有Key和控制字不可改"},
        (1, 0, 0): {"key_a_read": "Never",  "key_a_write": "KeyB",  "access_read": "KeyA|B",
                     "access_write": "Never", "key_b_read": "Never", "key_b_write": "KeyB",
                     "desc": "KeyB可修改KeyA/KeyB"},
        (1, 1, 0): {"key_a_read": "Never",  "key_a_write": "Never", "access_read": "KeyA|B",
                     "access_write": "Never", "key_b_read": "Never", "key_b_write": "Never",
                     "desc": "全锁: 控制字可读但均不可改"},
        (0, 0, 1): {"key_a_read": "Never",  "key_a_write": "KeyA",  "access_read": "KeyA",
                     "access_write": "KeyA",  "key_b_read": "KeyA",  "key_b_write": "KeyA",
                     "desc": "KeyA可修改一切 (含控制字)"},
        (0, 1, 1): {"key_a_read": "Never",  "key_a_write": "KeyB",  "access_read": "KeyA|B",
                     "access_write": "KeyB",  "key_b_read": "Never", "key_b_write": "KeyB",
                     "desc": "KeyB可修改一切 (含控制字)"},
        (1, 0, 1): {"key_a_read": "Never",  "key_a_write": "Never", "access_read": "KeyA|B",
                     "access_write": "KeyB",  "key_b_read": "Never", "key_b_write": "Never",
                     "desc": "KeyB可改控制字, KeyA/B均不可改"},
        (1, 1, 1): {"key_a_read": "Never",  "key_a_write": "Never", "access_read": "KeyA|B",
                     "access_write": "Never", "key_b_read": "Never", "key_b_write": "Never",
                     "desc": "完全锁死: 一切不可改"},
    }

    @classmethod
    def decode(cls, access_bytes: bytes) -> Dict[str, Any]:
        """
        解析 4 字节控制字 (Byte6~Byte9)
        返回每个块 (Block 0/1/2 + Trailer) 的权限描述
        """
        if len(access_bytes) != 4:
            return {"error": "控制字必须为 4 字节"}

        b6, b7, b8, b9 = access_bytes

        blocks = {}
        valid = True

        for i in range(4):
            c1_inv = (b6 >> i) & 1
            c1_raw = (b7 >> (4 + i)) & 1
            c2_inv = (b6 >> (4 + i)) & 1
            c2_raw = (b8 >> i) & 1
            c3_inv = (b7 >> i) & 1
            c3_raw = (b8 >> (4 + i)) & 1

            if c1_inv == c1_raw or c2_inv == c2_raw or c3_inv == c3_raw:
                valid = False

            c1, c2, c3 = c1_raw, c2_raw, c3_raw
            key = (c1, c2, c3)

            if i < 3:
                perm = cls.DATA_BLOCK_ACCESS.get(key, {"desc": f"未知组合 C1={c1} C2={c2} C3={c3}"})
                blocks[f"block_{i}"] = {"c1": c1, "c2": c2, "c3": c3, **perm}
            else:
                perm = cls.TRAILER_ACCESS.get(key, {"desc": f"未知组合 C1={c1} C2={c2} C3={c3}"})
                blocks["trailer"] = {"c1": c1, "c2": c2, "c3": c3, **perm}

        return {
            "blocks": blocks,
            "valid": valid,
            "gpb": b9,
            "raw_hex": " ".join(f"{b:02X}" for b in access_bytes),
        }
