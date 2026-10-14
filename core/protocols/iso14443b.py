# -*- coding: utf-8 -*-
"""
PyMifareTool - ISO/IEC 14443 Type B 与中国二代居民身份证专用协议编解码器
实现 CRC-B 算法、12 组 CIU 射频寄存器配置参数及 4 步非标穿透握手报文封装
"""

from typing import Optional, List, Tuple, Dict, Any


def calculate_crc_b(data: bytes) -> bytes:
    """
    计算 ISO/IEC 14443 Type B CRC (CRC-B)
    多项式: 0x8408 (反转 0x1021), 初值: 0xFFFF, 取反, 结果低字节在前
    """
    crc = 0xFFFF
    for b in data:
        b ^= (crc & 0xFF)
        b ^= (b << 4) & 0xFF
        crc = (crc >> 8) ^ ((b << 8) & 0xFFFF) ^ ((b << 3) & 0xFFFF) ^ (b >> 4)
    crc = (~crc) & 0xFFFF
    return bytes([crc & 0xFF, (crc >> 8) & 0xFF])


# 12 个 CIU 射频寄存器调谐参数 (二代居民身份证非标 ISO14443-B 物理层配置)
CIU_REGISTERS_TYPE_B_ID: List[Tuple[int, int]] = [
    (0x6301, 0xFF),  # CIU_Mode: 0xFF
    (0x6305, 0x00),  # CIU_TxAuto: 0x00
    (0x6302, 0x03),  # CIU_TxMode: 0x03 (106kbps Type B, 裸CRC由软件计算)
    (0x6303, 0x03),  # CIU_RxMode: 0x03 (106kbps Type B, 裸CRC由软件计算)
    (0x630E, 0x03),  # CIU_TypeB: 0x03
    (0x6309, 0x4D),  # CIU_Demod: 0x4D
    (0x6317, 0xFF),  # CIU_GsNOn: 0xFF
    (0x6318, 0x3F),  # CIU_CWGsP: 0x3F
    (0x6319, 0x18),  # CIU_ModGsP: 0x18
    (0x6308, 0x4D),  # CIU_RxThreshold: 0x4D
    (0x6314, 0x68),  # CIU_ModWidth: 0x68
    (0x630D, 0x10),  # CIU_ManualRCV: 0x10
]


class ISO14443BProtocol:
    """ISO/IEC 14443-B 二代居民身份证协议编解码器"""

    @staticmethod
    def calculate_crc_b(data: bytes) -> bytes:
        return calculate_crc_b(data)

    @classmethod
    def build_reqb_frame(cls) -> bytes:
        """构建 REQB 广播寻卡指令 (带 CRC-B: 05 00 00 71 FF)"""
        reqb_raw = bytes([0x05, 0x00, 0x00])
        return reqb_raw + cls.calculate_crc_b(reqb_raw)

    @classmethod
    def parse_atqb(cls, atqb_data: bytes) -> Optional[bytes]:
        """
        从卡片返回的 ATQB 响应中提取 4 字节 PUPI (Pseudo-Unique PICC Identifier)
        ATQB 结构: [0x50] [PUPI 4B] [ApplicationData 4B] [ProtocolInfo 3B]
        """
        if len(atqb_data) >= 5 and atqb_data[0] == 0x50:
            return atqb_data[1:5]
        return None

    @classmethod
    def build_attrib_frame(cls, pupi: bytes) -> bytes:
        """
        构建 ATTRIB 选卡激活指令 (带 CRC-B)
        格式: 1D [PUPI 4B] 00 08 01 08 + CRC-B
        """
        attrib_raw = bytes([0x1D]) + pupi[:4] + bytes([0x00, 0x08, 0x01, 0x08])
        return attrib_raw + cls.calculate_crc_b(attrib_raw)

    @classmethod
    def build_read_guid_frame(cls) -> bytes:
        """
        构建读取二代身份证 8 字节硬件物理 GUID 的 APDU 报文
        格式: 00 36 00 00 08 + CRC-B (即 00 36 00 00 08 57 44)
        """
        cmd_raw = bytes([0x00, 0x36, 0x00, 0x00, 0x08])
        return cmd_raw + cls.calculate_crc_b(cmd_raw)

    @classmethod
    def parse_guid_response(cls, resp_data: bytes) -> Optional[bytes]:
        """
        解析读取 GUID 返回的响应
        返回: 8 字节物理卡号 GUID，失败返回 None
        """
        if len(resp_data) >= 8:
            return resp_data[:8]
        return None
