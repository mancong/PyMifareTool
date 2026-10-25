# -*- coding: utf-8 -*-
"""
PyMifareTool - NXP PN532 HSU (High-Speed UART) 二进制通信协议编解码器
遵循 NXP UM0701-04 User Manual HSU 帧规范与状态解析
纯无状态编解码器，不依赖任何硬件串口连接
"""

from typing import Optional, Tuple, Dict, Any
from .base import BaseProtocolCodec


class PN532Protocol(BaseProtocolCodec):
    """NXP PN532 HSU 协议编解码器"""

    PREAMBLE = 0x00
    START_CODE = bytes([0x00, 0xFF])
    POSTAMBLE = 0x00

    HOST_TO_PN532 = 0xD4
    PN532_TO_HOST = 0xD5

    ACK_FRAME = bytes([0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00])

    # 常用命令字
    CMD_GET_FIRMWARE_VERSION = 0x02
    CMD_WRITE_REGISTER       = 0x08
    CMD_READ_REGISTER        = 0x06
    CMD_SAM_CONFIGURATION    = 0x14
    CMD_IN_LIST_PASSIVE_TARGET = 0x4A
    CMD_IN_DATA_EXCHANGE     = 0x40
    CMD_IN_COMMUNICATE_THRU  = 0x42
    CMD_IN_RELEASE           = 0x52
    CMD_RF_CONFIGURATION     = 0x32

    # MIFARE Classic 内部指令
    MIFARE_CMD_AUTH_A = 0x60
    MIFARE_CMD_AUTH_B = 0x61
    MIFARE_CMD_READ   = 0x30
    MIFARE_CMD_WRITE  = 0xA0

    @classmethod
    def build_hsu_frame(cls, cmd: int, data: bytes = b"") -> bytes:
        """
        构建标准 PN532 HSU 请求数据帧 (Host -> PN532):
        [00 00 FF] [LEN] [LCS] [D4] [CMD] [DATA...] [DCS] [00]
        """
        payload = bytes([cls.HOST_TO_PN532, cmd]) + data
        length = len(payload)
        lcs = (-length) & 0xFF
        dcs = (-sum(payload)) & 0xFF
        return bytes([cls.PREAMBLE]) + cls.START_CODE + bytes([length, lcs]) + payload + bytes([dcs, cls.POSTAMBLE])

    @classmethod
    def build_response_frame(cls, cmd: int, data: bytes = b"") -> bytes:
        """
        构建标准 PN532 应答数据帧 (PN532 -> Host):
        [00 00 FF] [LEN] [LCS] [D5] [CMD] [DATA...] [DCS] [00]
        """
        payload = bytes([cls.PN532_TO_HOST, cmd]) + data
        length = len(payload)
        lcs = (-length) & 0xFF
        dcs = (-sum(payload)) & 0xFF
        return bytes([cls.PREAMBLE]) + cls.START_CODE + bytes([length, lcs]) + payload + bytes([dcs, cls.POSTAMBLE])

    @classmethod
    def parse_hsu_frame(cls, raw: bytes) -> Tuple[Optional[Dict[str, Any]], bytes]:
        """
        从字节流解析 PN532 应答帧或 ACK 确认帧
        """
        idx = raw.find(b"\x00\x00\xFF")
        if idx == -1:
            return None, raw[-2:] if len(raw) > 2 else raw

        remaining = raw[idx:]
        if len(remaining) < 6:
            return None, remaining

        # ACK 帧判断
        if remaining.startswith(cls.ACK_FRAME):
            return {"type": "ACK", "raw": cls.ACK_FRAME}, remaining[6:]

        length = remaining[3]
        lcs = remaining[4]
        if (length + lcs) & 0xFF != 0x00:
            return None, remaining[3:]

        total_frame_len = length + 7
        if len(remaining) < total_frame_len:
            return None, remaining

        frame_bytes = remaining[:total_frame_len]
        payload = frame_bytes[5: 5 + length]
        dcs = frame_bytes[5 + length]
        if (sum(payload) + dcs) & 0xFF != 0x00:
            return None, remaining[total_frame_len:]

        tfi = payload[0]
        if tfi != cls.PN532_TO_HOST:
            return None, remaining[total_frame_len:]

        cmd = payload[1] if len(payload) > 1 else 0x00
        data = payload[2:] if len(payload) > 2 else b""

        frame_info = {
            "type": "DATA",
            "cmd": cmd,
            "data": data,
            "raw": frame_bytes,
        }
        return frame_info, remaining[total_frame_len:]

    def build_frame(self, cmd: int, data: bytes = b"") -> bytes:
        return self.build_hsu_frame(cmd, data)

    def parse_frame(self, buffer: bytes) -> Tuple[Optional[Dict[str, Any]], bytes]:
        return self.parse_hsu_frame(buffer)
