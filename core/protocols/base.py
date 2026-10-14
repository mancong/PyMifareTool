# -*- coding: utf-8 -*-
"""
PyMifareTool - 基础协议抽象与通用异常规范
定义无状态协议编解码器标准接口 (Stateless Protocol Codec)
"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict, Any


class ProtocolError(Exception):
    """协议编解码基类异常"""
    pass


class FrameChecksumError(ProtocolError):
    """帧校验和错误 (BCC / LCS / DCS / CRC 校验失败)"""
    pass


class FrameIncompleteError(ProtocolError):
    """缓冲区数据不完整，需要等待更多字节"""
    pass


class BaseProtocolCodec(ABC):
    """
    无状态通信协议编解码基类
    所有协议编解码器必须纯粹处理字节数据流，绝不直接持有物理连接或硬件串口
    """

    @abstractmethod
    def build_frame(self, cmd: int, data: bytes = b"") -> bytes:
        """封装完整的二进制协议帧"""
        pass

    @abstractmethod
    def parse_frame(self, buffer: bytes) -> Tuple[Optional[Dict[str, Any]], bytes]:
        """
        从缓冲区解析完整帧
        返回: (解析结果字典 或 None, 剩余未消费字节)
        """
        pass
