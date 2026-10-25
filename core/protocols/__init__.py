# -*- coding: utf-8 -*-
"""
PyMifareTool - 核心通信协议编解码库 (Stateless Protocols Layer)
统一导出无状态、高内聚协议编解码器
"""

from .base import BaseProtocolCodec, ProtocolError, FrameChecksumError, FrameIncompleteError
from .aabb import AABBProtocol, ReaderProtocol
from .pn532 import PN532Protocol
from .iso14443b import ISO14443BProtocol, calculate_crc_b, CIU_REGISTERS_TYPE_B_ID
from .iso7816 import APDUProtocol, SW_DESCRIPTIONS, AID_T_UNION, AID_PBOC_CASH

__all__ = [
    "BaseProtocolCodec",
    "ProtocolError",
    "FrameChecksumError",
    "FrameIncompleteError",
    "AABBProtocol",
    "ReaderProtocol",
    "PN532Protocol",
    "ISO14443BProtocol",
    "calculate_crc_b",
    "CIU_REGISTERS_TYPE_B_ID",
    "APDUProtocol",
    "SW_DESCRIPTIONS",
    "AID_T_UNION",
    "AID_PBOC_CASH",
]
