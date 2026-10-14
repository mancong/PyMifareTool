# -*- coding: utf-8 -*-
"""
PyMifareTool - 底层通信传输抽象层 (Transport Layer)
定义读卡器数据流物理/链路传输接口规范
支持未来平滑扩展网络透传 (TCP/UDP Transport)、虚拟传输 (Mock Transport) 及蓝牙 (BLE Transport)
"""

from abc import ABC, abstractmethod
from typing import Optional


class TransportError(Exception):
    """物理传输层基类异常"""
    pass


class ITransport(ABC):
    """通信链路统一抽象接口"""

    @abstractmethod
    def open(self) -> bool:
        """打开通信链路"""
        pass

    @abstractmethod
    def close(self) -> None:
        """安全关闭通信链路"""
        pass

    @abstractmethod
    def is_open(self) -> bool:
        """链路是否处于可用开启状态"""
        pass

    @abstractmethod
    def write(self, data: bytes) -> int:
        """发送字节数据，返回已发送字节数"""
        pass

    @abstractmethod
    def read(self, size: int = 1, timeout: Optional[float] = None) -> bytes:
        """读取指定长度字节"""
        pass

    @abstractmethod
    def flush(self) -> None:
        """刷新输入/输出缓冲区"""
        pass

    @abstractmethod
    def in_waiting(self) -> int:
        """当前可读字节数"""
        pass
