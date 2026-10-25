# -*- coding: utf-8 -*-
"""
PyMifareTool - PC/SC 智能卡读写器驱动扩展骨架 (ACR122U / CCID USB Reader)
预留给未来通过 pyscard 库扩展标准 PC/SC 读写器硬件
遵循 ISO 7816-4 APDU 与 PC/SC 2.0 规范
"""

from typing import Optional, Dict, Any, Tuple
from core.adapters.base_adapter import BaseReaderAdapter
from core.transport.base import TransportLike


class PCSCReaderAdapter(BaseReaderAdapter):
    """
    PC/SC 标准读写器驱动适配器 (扩展骨架)
    支持 ACR122U, Identiv uTrust, Omnikey 等免驱 USB PC/SC 读卡器
    """

    def __init__(self, reader_name: str = "PCSC USB Smart Card Reader"):
        super().__init__()
        self.device_name = f"PC/SC 读写器: {reader_name}"
        self.is_bidirectional = True
        self.default_baudrate = 0  # PC/SC 由系统驱动层管理波特率
        self.firmware_info = "PC/SC CCID Driver"
        self._connection = None

    def init_device(self, ser: Optional[TransportLike] = None) -> bool:
        """检查 PC/SC 服务环境与读卡器上下文"""
        return True

    def parse_incoming(self, rx_buffer: bytearray) -> Tuple[Optional[Dict[str, Any]], bytes]:
        """PC/SC 为事务请求-应答模型，通常不依赖被动流解析"""
        return None, bytes(rx_buffer)

    def poll_card(self, ser: Optional[TransportLike] = None, timeout: float = 0.5) -> Optional[Dict[str, Any]]:
        """
        通过 APDU FF CA 00 00 00 获取卡片 UID (Get Card UID)
        """
        return None

    def authenticate(self, ser: Optional[TransportLike], block: int, key_type: str, key: bytes, uid: bytes = b"", timeout: float = 0.35) -> bool:
        """
        通过 APDU FF 86 00 00 05 01 00 [Block] [KeyType] 00 进行 PC/SC 扇区认证
        """
        return False

    def read_block(self, ser: Optional[TransportLike], block: int, timeout: float = 0.35) -> Optional[bytes]:
        """
        通过 APDU FF B0 00 [Block] 10 读取 16 字节物理块
        """
        return None

    def write_block(self, ser: Optional[TransportLike], block: int, data: bytes, timeout: float = 0.35) -> bool:
        """
        通过 APDU FF D6 00 [Block] 10 [16B Data] 写入 16 字节物理块
        """
        return False
