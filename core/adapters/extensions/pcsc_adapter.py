# -*- coding: utf-8 -*-
"""
PyMifareTool - PC/SC 智能卡读写器驱动 (ACR122U / CCID USB Reader)
通过 pyscard 访问标准 PC/SC 免驱读卡器，遵循 ISO 7816-4 APDU 与 PC/SC 2.0。
pyscard 为可选依赖；未安装时适配器自动降级为不可用状态。
"""

from typing import Optional, Dict, Any, Tuple
from core.adapters.base_adapter import BaseReaderAdapter
from core.transport.base import TransportLike
from core.models.card_converter import CardConverter


class PCSCReaderAdapter(BaseReaderAdapter):
    """PC/SC 标准读写器驱动适配器 (ACR122U / Identiv / Omnikey)"""

    def __init__(self, reader_name: str = ""):
        super().__init__()
        self.reader_name = reader_name
        self.device_name = f"PC/SC 读写器: {reader_name or '自动选择'}"
        self.is_bidirectional = True
        self.default_baudrate = 0
        self.firmware_info = "PC/SC CCID Driver"
        self._connection = None
        self._active_reader = None

    def _load_pyscard(self):
        try:
            from smartcard.System import readers
            return readers
        except Exception:
            return None

    def init_device(self, ser: Optional[TransportLike] = None) -> bool:
        readers = self._load_pyscard()
        if readers is None:
            self.firmware_info = "pyscard 未安装"
            return False
        try:
            available = readers()
            if not available:
                self.firmware_info = "未发现 PC/SC 读卡器"
                return False
            target = available[0]
            if self.reader_name:
                for reader in available:
                    if self.reader_name.lower() in str(reader).lower():
                        target = reader
                        break
            self._active_reader = target
            self._connection = target.createConnection()
            self._connection.connect()
            self.device_name = f"PC/SC 读写器: {target}"
            self.firmware_info = f"PC/SC CCID ({target})"
            return True
        except Exception as e:
            self._connection = None
            self.firmware_info = f"PC/SC 初始化失败: {e}"
            return False

    def parse_incoming(self, rx_buffer: bytearray) -> Tuple[Optional[Dict[str, Any]], bytes]:
        return None, bytes(rx_buffer)

    def _transmit(self, apdu: bytes) -> Optional[Tuple[bytes, int, int]]:
        if self._connection is None:
            return None
        try:
            data, sw1, sw2 = self._connection.transmit(list(apdu))
            return bytes(data), sw1, sw2
        except Exception:
            return None

    def poll_card(self, ser: Optional[TransportLike] = None, timeout: float = 0.5) -> Optional[Dict[str, Any]]:
        res = self._transmit(bytes([0xFF, 0xCA, 0x00, 0x00, 0x00]))
        if not res:
            return None
        data, sw1, sw2 = res
        if sw1 != 0x90 or sw2 != 0x00 or not data:
            return None
        self.last_detected_uid = data
        return {
            "uid_bytes": data,
            "conversions": CardConverter.convert_uid(data),
            "device_model": "PCSCReader",
            "raw": data,
        }

    def authenticate(self, ser: Optional[TransportLike], block: int, key_type: str, key: bytes, uid: bytes = b"", timeout: float = 0.35) -> bool:
        if len(key) != 6:
            return False
        load_key = bytes([0xFF, 0x82, 0x00, 0x00, 0x06]) + key
        res = self._transmit(load_key)
        if not res or (res[1], res[2]) != (0x90, 0x00):
            return False
        key_code = 0x60 if key_type.upper() == "A" else 0x61
        auth = bytes([0xFF, 0x86, 0x00, 0x00, 0x05, 0x01, 0x00, block & 0xFF, key_code, 0x00])
        res = self._transmit(auth)
        return bool(res and res[1] == 0x90 and res[2] == 0x00)

    def read_block(self, ser: Optional[TransportLike], block: int, timeout: float = 0.35) -> Optional[bytes]:
        res = self._transmit(bytes([0xFF, 0xB0, 0x00, block & 0xFF, 0x10]))
        if not res:
            return None
        data, sw1, sw2 = res
        if sw1 == 0x90 and sw2 == 0x00 and len(data) == 16:
            return data
        return None

    def write_block(self, ser: Optional[TransportLike], block: int, data: bytes, timeout: float = 0.35) -> bool:
        if len(data) != 16:
            return False
        apdu = bytes([0xFF, 0xD6, 0x00, block & 0xFF, 0x10]) + data
        res = self._transmit(apdu)
        return bool(res and res[1] == 0x90 and res[2] == 0x00)

    def get_capabilities(self) -> Dict[str, Any]:
        connected = self._connection is not None
        features = [
            {"name": "PC/SC CCID 驱动", "status": "supported" if connected else "unsupported", "detail": self.firmware_info},
            {"name": "ISO14443-A UID 读取", "status": "needs_card" if connected else "unsupported", "detail": "通过 FF CA 00 00 00 获取 UID"},
            {"name": "MIFARE Classic 认证 / 读写", "status": "needs_card" if connected else "unsupported", "detail": "通过 FF 82/86/B0/D6 伪 APDU 操作"},
            {"name": "ISO7816 APDU / CPU 卡", "status": "needs_card" if connected else "unsupported", "detail": "ACR122U 等 CCID 读卡器支持标准 APDU 透传"},
            {"name": "魔术卡后门 / UFUID 锁死", "status": "unsupported", "detail": "标准 PC/SC 指令不提供 Gen1a 后门或 UFUID 锁死"},
            {"name": "Crypto1 破解", "status": "unsupported", "detail": "PC/SC 不暴露 nonce，需 libnfc/Proxmark3 等其他工具链"},
        ]
        payload = self._capability_payload(features)
        payload["notes"] = [
            "需要安装可选依赖 pyscard；未安装时适配器会安全降级为不可用。",
            "如需使用 ACR122U 进行 mfoc/mfcuk 破解，请改用 tools/m1t/nfc-bin 的 libnfc(ACR122Uslow).dll。",
        ]
        return payload
