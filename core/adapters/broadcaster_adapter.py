# -*- coding: utf-8 -*-
"""
PyMifareTool - 简易单向 UID 广播发卡器驱动适配器 (Legacy Hardware)
适用于基于 NXP CV627 + 8051 MCU + WCH CH340E 架构的旧款只读发卡器
出厂波特率 38400 bps，被动监听 AA BB 06 01 [UID] [BCC] 广播报文
本适配器将报文解析解耦委托给 core.protocols.aabb
"""

from typing import Optional, Dict, Any, Tuple
from .base_adapter import BaseReaderAdapter
from core.transport.base import TransportLike
from core.protocols.aabb import AABBProtocol, ReaderProtocol
from core.models.card_converter import CardConverter


class BroadcasterAdapter(BaseReaderAdapter):
    """简易广播发卡器驱动适配器 (单向只读)"""

    def __init__(self):
        super().__init__()
        self.device_name = "简易广播发卡器 (单向只读)"
        self.is_bidirectional = False
        self.default_baudrate = 38400
        self.supported_baudrates = [38400, 9600, 115200]
        self.firmware_info = "单向广播发卡器固件 (自动上报 UID)"

    def init_device(self, ser: TransportLike) -> bool:
        """保持 DTR/RTS 释放，清空缓冲区"""
        try:
            # 🚨 硬件红线 1: 物理复位保护，释放 DTR/RTS
            ser.dtr = False
            ser.rts = False
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            return True
        except Exception:
            return False

    def parse_incoming(self, rx_buffer: bytearray) -> Tuple[Optional[Dict[str, Any]], bytes]:
        """流式解析 AA BB 协议帧 (委托给 AABBProtocol)"""
        if len(rx_buffer) < 4:
            return None, bytes(rx_buffer)

        frame_info, remaining = AABBProtocol.parse_frame(bytes(rx_buffer))
        if frame_info:
            frame_info["device_model"] = "Broadcaster"
            uid_bytes = frame_info.get("uid_bytes")
            if uid_bytes:
                frame_info["conversions"] = CardConverter.convert_uid(uid_bytes)
            return frame_info, remaining
        return None, remaining

    def poll_card(self, ser: TransportLike, timeout: float = 0.5) -> Optional[Dict[str, Any]]:
        """单向硬件不支持下行寻卡指令，依靠被动监听流"""
        return None

    def authenticate(self, ser: TransportLike, block: int, key_type: str, key: bytes, uid: bytes = b"", timeout: float = 0.35) -> bool:
        """单向硬件不支持下行扇区认证"""
        return False

    def read_block(self, ser: TransportLike, block: int, timeout: float = 0.35) -> Optional[bytes]:
        """单向硬件不支持下行读块"""
        return None

    def write_block(self, ser: TransportLike, block: int, data: bytes, timeout: float = 0.35) -> bool:
        """单向硬件不支持下行写块"""
        return False
