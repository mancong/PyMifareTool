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
        # 自动探测阶段可能已从串口读出数据，交由 SerialWorker 作为初始接收缓存
        self.initial_rx_data = b""

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

    def get_capabilities(self) -> Dict[str, Any]:
        features = [
            {
                "name": "AA BB UID 自动上报接收",
                "status": "needs_card",
                "detail": "38400bps 被动监听；贴卡后由发卡器主动广播 AA BB 06 01 + UID + BCC",
            },
            {
                "name": "MIFARE Classic 认证 / 读写",
                "status": "unsupported",
                "detail": "硬件物理上不响应任何下行指令，适配器刻意不实现认证与读写",
            },
            {
                "name": "ISO14443-B / CPU 卡 APDU",
                "status": "unsupported",
                "detail": "仅支持 UID 广播，不支持 Type B 或 ISO7816 APDU",
            },
            {
                "name": "密钥破解 / 外部工具",
                "status": "unsupported",
                "detail": "无射频收发控制能力，不能用于 Crypto1 或字典破解",
            },
        ]
        payload = self._capability_payload(features)
        payload["notes"] = [
            "硬件红线：广播器只能接收，不能发送任何下行帧；固件探测也已改为纯被动模式。",
            "请勿用本软件向广播器发送认证、读写或寄存器配置指令。",
        ]
        return payload
