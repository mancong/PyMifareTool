# -*- coding: utf-8 -*-
"""
PyMifareTool - 内存虚拟卡读写器适配器 (VirtualDumpReaderAdapter)
脱离物理硬件，直接将 MifareDump 映射为虚拟 RF 射频卡进行寻卡、密码验证与读写模拟
可用于无硬件离线仿真、自动化逻辑测试与算法验证
"""

from typing import Optional, Dict, Any, Tuple
from core.adapters.base_adapter import BaseReaderAdapter
from core.models.dump import MifareDump
from core.transport.base import TransportLike
from core.models.card_converter import CardConverter
from core.models.access_bits import AccessBitsDecoder


class VirtualDumpReaderAdapter(BaseReaderAdapter):
    """
    基于内存 Dump 的纯软件虚拟卡读写器适配器
    无需插拔任何 USB 硬件，即可仿真物理卡的贴卡、认证与读写
    """

    def __init__(self, dump: Optional[MifareDump] = None):
        super().__init__()
        self.device_name = "💻 软件虚拟卡仿真读写器 (Offline Virtual Card)"
        self.is_bidirectional = True
        self.default_baudrate = 0
        self.supported_baudrates = [0]
        self.firmware_info = "Virtual Mifare RF Simulator v1.0"
        self.dump = dump if dump is not None else MifareDump()
        self._authenticated_sectors = set()
        self._auth_key_types: Dict[int, str] = {}

    def set_virtual_dump(self, dump: MifareDump):
        """挂载新的虚拟卡数据实体"""
        self.dump = dump
        self._authenticated_sectors.clear()
        self._auth_key_types.clear()

    def init_device(self, ser: Optional[TransportLike] = None) -> bool:
        self._authenticated_sectors.clear()
        self._auth_key_types.clear()
        return True

    def parse_incoming(self, rx_buffer: bytearray) -> Tuple[Optional[Dict[str, Any]], bytes]:
        return None, bytes(rx_buffer)

    def poll_card(self, ser: Optional[TransportLike] = None, timeout: float = 0.5) -> Optional[Dict[str, Any]]:
        """从挂载的虚拟 Dump 中提取 Block 0 UID 进行卡片呈现"""
        b0 = self.dump.get_block(0)
        uid_bytes = b0[:4]
        if uid_bytes == b"\x00\x00\x00\x00":
            uid_bytes = bytes([0xAA, 0xBB, 0xCC, 0xDD])

        return {
            "uid_bytes": uid_bytes,
            "atqa": b0[6:8] if len(b0) >= 8 else b"\x04\x00",
            "sak": b0[5] if len(b0) > 5 else 0x08,
            "conversions": CardConverter.convert_uid(uid_bytes),
            "device_model": "VirtualReader",
        }

    def authenticate(self, ser: Optional[TransportLike], block: int, key_type: str, key: bytes, uid: bytes = b"", timeout: float = 0.35) -> bool:
        """
        验证提供的密钥是否与虚拟卡对应扇区尾块的密钥相符
        """
        sector = self.dump.get_block_sector(block)
        trailer_blk = self.dump.get_sector_trailer_block(sector)
        trailer = self.dump.get_block(trailer_blk)

        ka = trailer[0:6]
        kb = trailer[10:16]

        provided_key = key[:6]
        is_key_a = (key_type.upper() == "A")

        if is_key_a and provided_key == ka:
            self._authenticated_sectors.add(sector)
            self._auth_key_types[sector] = "A"
            return True
        elif not is_key_a and provided_key == kb:
            self._authenticated_sectors.add(sector)
            self._auth_key_types[sector] = "B"
            return True

        return False

    @staticmethod
    def _permission_allows(permission: str, key_type: str) -> bool:
        if permission == "KeyA|B":
            return True
        if permission == "KeyA":
            return key_type == "A"
        if permission == "KeyB":
            return key_type == "B"
        return False

    def _check_access(self, block: int, action: str) -> bool:
        """按扇区尾块 Access Bits 校验读/写权限"""
        sector = self.dump.get_block_sector(block)
        if sector not in self._authenticated_sectors:
            return False
        key_type = self._auth_key_types.get(sector, "A")
        first = self.dump.get_sector_first_block(sector)
        trailer_block = self.dump.get_sector_trailer_block(sector)
        trailer = self.dump.get_block(trailer_block)
        access_bytes = trailer[6:10]
        decoded = AccessBitsDecoder.decode(access_bytes)
        blocks = decoded.get("blocks", {})

        if block == trailer_block:
            info = blocks.get("trailer", {})
            perm_key = "access_read" if action == "read" else "access_write"
            permission = info.get(perm_key, "KeyA|B")
        else:
            offset = block - first
            if offset < 0 or offset > 2:
                return False
            info = blocks.get(f"block_{offset}", {})
            permission = info.get(action, "KeyA|B")

        if not decoded.get("valid", False):
            # 控制字异常时仅要求已认证，避免虚拟仿真完全不可用
            return True
        return self._permission_allows(permission, key_type)

    def read_block(self, ser: Optional[TransportLike], block: int, timeout: float = 0.35) -> Optional[bytes]:
        """读取虚拟卡指定块 (需先认证且 Access Bits 允许读取)"""
        if 0 <= block < self.dump.block_count and self._check_access(block, "read"):
            return self.dump.get_block(block)
        return None

    def write_block(self, ser: Optional[TransportLike], block: int, data: bytes, timeout: float = 0.35) -> bool:
        """写入虚拟卡指定块 (需先认证且 Access Bits 允许写入)"""
        if 0 <= block < self.dump.block_count and len(data) == 16 and self._check_access(block, "write"):
            self.dump.set_block(block, data)
            return True
        return False

    def get_capabilities(self) -> Dict[str, Any]:
        features = [
            {"name": "内存虚拟卡仿真", "status": "supported", "detail": "无需硬件，直接挂载 MifareDump 模拟贴卡"},
            {"name": "UID / ATQA / SAK 呈现", "status": "supported", "detail": "从虚拟 Dump 的 Block 0 提取"},
            {"name": "Key A/B 认证", "status": "supported", "detail": "按虚拟扇区尾块密钥校验"},
            {"name": "Access Bits 读写权限", "status": "supported", "detail": "读/写均校验认证状态与 Access Bits"},
            {"name": "真实射频 / 破解 / 身份证", "status": "unsupported", "detail": "纯软件仿真，不包含真实射频与 ISO14443-B 能力"},
        ]
        payload = self._capability_payload(features)
        payload["notes"] = ["虚拟卡用于离线逻辑验证，不能替代真机读写测试。"]
        return payload
