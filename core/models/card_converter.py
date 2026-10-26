# -*- coding: utf-8 -*-
"""
PyMifareTool - 卡号格式多行业标准换算模型 (CardConverter)
针对 4 / 7 / 8 / 10 字节物理 UID 进行正序、倒序、8H10D、门禁韦根 WG26/34 换算
"""

from typing import Dict, Any, Optional


class CardConverter:
    """针对 4/7/8/10 字节 UID 进行全行业常见格式换算，并提供 Block 0 厂商块智能装配"""

    @staticmethod
    def generate_random_uid(length: int = 4) -> bytes:
        """生成随机物理卡号 UID (避免以 0x00 或 0x88 级联符开头)"""
        import os
        b = bytearray(os.urandom(length))
        while b[0] in (0x00, 0x88):
            b[0] = os.urandom(1)[0]
        return bytes(b)

    @staticmethod
    def build_block0(
        uid: bytes,
        sak: int = 0x08,
        atqa: Any = b"\x04\x00",
        manufacturer_data: Optional[bytes] = None
    ) -> bytes:
        """
        根据提供的 UID 与射频参数构建标准的 16 字节 Block 0 (厂商数据块)
        4字节UID结构: [4B UID] [1B BCC] [1B SAK] [2B ATQA] [8B 厂商数据]
        """
        if isinstance(atqa, int):
            atqa_2b = atqa.to_bytes(2, "big")
        elif isinstance(atqa, (bytes, bytearray)):
            atqa_2b = bytes(atqa[:2]) if len(atqa) >= 2 else bytes(atqa).ljust(2, b"\x00")
        else:
            atqa_2b = b"\x04\x00"

        if len(uid) == 4:
            bcc = uid[0] ^ uid[1] ^ uid[2] ^ uid[3]
            mfg = manufacturer_data if (manufacturer_data and len(manufacturer_data) == 8) else bytes.fromhex("6263646566676869")
            return uid + bytes([bcc, sak & 0xFF]) + atqa_2b + mfg
        elif len(uid) == 7:
            bcc = uid[3] ^ uid[4] ^ uid[5] ^ uid[6]
            mfg = manufacturer_data if (manufacturer_data and len(manufacturer_data) == 5) else bytes.fromhex("0804000102")
            return uid + bytes([bcc, sak & 0xFF]) + atqa_2b + mfg
        else:
            raise ValueError(f"不支持的 UID 长度: {len(uid)} 字节 (仅支持 4 或 7 字节)")

    @staticmethod
    def convert_uid(uid: bytes) -> Dict[str, Any]:
        if len(uid) < 4:
            return {}

        uid_full = uid
        uid4 = uid[:4]

        hex_normal = " ".join(f"{b:02X}" for b in uid_full)
        hex_normal_nospace = "".join(f"{b:02X}" for b in uid_full)

        uid_rev = uid_full[::-1]
        hex_rev = " ".join(f"{b:02X}" for b in uid_rev)
        hex_rev_nospace = "".join(f"{b:02X}" for b in uid_rev)

        hex_4b_normal = " ".join(f"{b:02X}" for b in uid4)

        uid4_rev = uid4[::-1]
        dec_normal = int.from_bytes(uid4, byteorder="big")
        dec_normal_10d = f"{dec_normal:010d}"

        dec_rev = int.from_bytes(uid4_rev, byteorder="big")
        dec_rev_10d = f"{dec_rev:010d}"

        wg26_fac = uid4_rev[1] if len(uid4_rev) >= 3 else 0
        wg26_card = int.from_bytes(uid4_rev[2:4], "big") if len(uid4_rev) >= 4 else 0
        wg26_str = f"{wg26_fac:03d},{wg26_card:05d}"

        wg34_fac = int.from_bytes(uid4_rev[0:2], "big")
        wg34_card = int.from_bytes(uid4_rev[2:4], "big")
        wg34_str = f"{wg34_fac:05d},{wg34_card:05d}"

        result: Dict[str, Any] = {
            "hex_normal": hex_normal,
            "hex_normal_raw": hex_normal_nospace,
            "hex_reverse": hex_rev,
            "hex_reverse_raw": hex_rev_nospace,
            "hex_4b_normal": hex_4b_normal,
            "dec_10d_normal": dec_normal_10d,
            "dec_10d_rev": dec_rev_10d,
            "wiegand_26": wg26_str,
            "wiegand_34": wg34_str,
            "uid_length": len(uid_full),
        }

        if len(uid_full) == 7:
            card_desc = "7-byte (Mifare Plus / NTAG / DESFire)"
        elif len(uid_full) == 8:
            card_desc = "8-byte (二代身份证 / ISO14443-B)"
        elif len(uid_full) == 10:
            card_desc = "10-byte (Triple-size UID)"
        else:
            card_desc = "4-byte (Mifare Classic)"

        result["uid_type"] = card_desc
        result["card_type"] = card_desc  # 兼容 card_db 键名读取
        return result

    convert = convert_uid
