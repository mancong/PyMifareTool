# -*- coding: utf-8 -*-
"""
PyMifareTool - 卡号格式多行业标准换算模型 (CardConverter)
针对 4 / 7 / 8 / 10 字节物理 UID 进行正序、倒序、8H10D、门禁韦根 WG26/34 换算
"""

from typing import Dict, Any


class CardConverter:
    """针对 4/7/8/10 字节 UID 进行全行业常见格式换算"""

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
