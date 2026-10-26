# -*- coding: utf-8 -*-
"""
PyMifareTool - 硬件读写器抽象适配器基类
定义多硬件统一接入标准接口规范
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple, List
from core.transport.base import TransportLike


class BaseReaderAdapter(ABC):
    """读卡器硬件抽象适配器基类"""

    def __init__(self):
        self.device_name: str = "通用读卡器"
        self.is_bidirectional: bool = False
        self.default_baudrate: int = 115200
        self.supported_baudrates: List[int] = [115200, 38400, 9600]
        self.firmware_info: str = "未知固件"
        self.last_detected_uid: Optional[bytes] = None
        # 原始收发日志回调: callable(direction: str, text: str)；由 SerialWorker 注入桥接至 UI
        self.log_cb = None

    def get_firmware_version(self, ser: Optional[TransportLike] = None, timeout: float = 0.5) -> str:
        """获取固件版本信息"""
        return self.firmware_info

    def _capability_payload(self, features: List[Dict[str, str]]) -> Dict[str, Any]:
        return {
            "device_name": self.device_name,
            "firmware_info": self.firmware_info,
            "is_bidirectional": self.is_bidirectional,
            "adapter_type": self.__class__.__name__,
            "features": features,
        }

    def get_capabilities(self) -> Dict[str, Any]:
        """返回基础设备能力描述，具体适配器可覆盖以提供更精确的探测结果"""
        features = [
            {"name": "设备通信", "status": "supported", "detail": "适配器已加载"},
            {
                "name": "下行卡片操作",
                "status": "supported" if self.is_bidirectional else "unsupported",
                "detail": "支持双向串口指令" if self.is_bidirectional else "仅接收上行广播，不发送下行指令",
            },
        ]
        return self._capability_payload(features)

    @abstractmethod
    def init_device(self, ser: TransportLike) -> bool:
        """初始化设备与握手 (配置波特率、唤醒、SAM配置等)"""
        pass

    @abstractmethod
    def parse_incoming(self, rx_buffer: bytearray) -> Tuple[Optional[Dict[str, Any]], bytes]:
        """
        从接收缓冲区解析一帧数据
        返回: (解析结果字典 或 None, 剩余未消费字节)
        """
        pass

    @abstractmethod
    def poll_card(self, ser: TransportLike, timeout: float = 0.5) -> Optional[Dict[str, Any]]:
        """主动寻卡，检测卡片物理 UID 与射频参数"""
        pass

    @abstractmethod
    def authenticate(self, ser: TransportLike, block: int, key_type: str, key: bytes, uid: bytes = b"", timeout: float = 0.35) -> bool:
        """执行扇区密钥认证 (Key A / Key B)"""
        pass

    @abstractmethod
    def read_block(self, ser: TransportLike, block: int, timeout: float = 0.35) -> Optional[bytes]:
        """读取指定物理块 (16 字节)"""
        pass

    @abstractmethod
    def write_block(self, ser: TransportLike, block: int, data: bytes, timeout: float = 0.35) -> bool:
        """写入指定物理块 (16 字节)"""
        pass

    def write_magic_block0(self, ser: TransportLike, block0_data: bytes, magic_type: str = "CUID", timeout: float = 0.5) -> bool:
        """魔术卡/UID 卡后门写入 (支持 Gen1a 后门解锁与 Gen2/CUID/FUID/UFUID 直接写)"""
        if magic_type.upper() in ["CUID", "GEN2", "FUID"]:
            return self.write_block(ser, 0, block0_data, timeout=timeout)
        return False

    def lock_ufuid_card(self, ser: TransportLike, timeout: float = 0.5) -> bool:
        """锁定 UFUID 卡片 (0 块锁死固化变为只读普通卡)"""
        return False
