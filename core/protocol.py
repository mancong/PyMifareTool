# -*- coding: utf-8 -*-
"""
PyMifareTool - 核心协议与算法向后兼容门面 (Protocols & Models Facade)
向下兼容提供原 core.protocol 中的全部导出对象：
- ReaderProtocol / AABBProtocol: AA BB 协议帧解包/构建、BCC 校验
- CardConverter: UID 格式转换 (Hex 正倒序, 8H10D, 韦根 WG26/34, 二代身份证)
- AccessBitsDecoder / AccessBitsEncoder: M1 控制字权限位运算编解码
- PN532Protocol: NXP PN532 HSU 标准通信协议
- ISO14443BProtocol: 二代身份证 (ISO/IEC 14443-B) CRC-B 与非标 APDU
已遵循软件工程整洁架构，核心实现分别解耦位于 core.protocols.* 与 core.models.*
"""

from core.protocols.aabb import AABBProtocol, ReaderProtocol
from core.protocols.pn532 import PN532Protocol
from core.protocols.iso14443b import ISO14443BProtocol, calculate_crc_b, CIU_REGISTERS_TYPE_B_ID
from core.models.card_converter import CardConverter
from core.models.access_bits import AccessBitsDecoder, AccessBitsEncoder

__all__ = [
    "ReaderProtocol",
    "AABBProtocol",
    "PN532Protocol",
    "ISO14443BProtocol",
    "calculate_crc_b",
    "CIU_REGISTERS_TYPE_B_ID",
    "CardConverter",
    "AccessBitsDecoder",
    "AccessBitsEncoder",
]
