# -*- coding: utf-8 -*-
"""
PyMifareTool - 底层通信传输抽象层 (Transport Layer)
定义读卡器数据流物理/链路传输接口规范
支持未来平滑扩展网络透传 (TCP/UDP Transport)、虚拟传输 (Mock Transport) 及蓝牙 (BLE Transport)
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Protocol, runtime_checkable


class TransportError(Exception):
    """物理传输层基类异常"""
    pass


class CallableInt(int):
    """支持作为整数使用，也支持作为无参函数调用的特殊整数，以双向兼容 in_waiting 属性与方法"""
    def __call__(self) -> int:
        return int(self)


class CallableBool:
    """支持作为布尔值使用，也支持作为无参函数调用的特殊布尔对象，以双向兼容 is_open 属性与方法"""
    def __init__(self, val: bool):
        self._val = bool(val)

    def __bool__(self) -> bool:
        return self._val

    def __call__(self) -> bool:
        return self._val

    def __eq__(self, other) -> bool:
        return self._val == bool(other)

    def __repr__(self) -> str:
        return str(self._val)


@runtime_checkable
class TransportLike(Protocol):
    """
    适配器与业务层使用的最小传输通道契约 (pyserial / SerialTransport / BleTransport 均可满足)

    is_open / in_waiting 使用 Any 类型，以兼容属性访问与方法调用两种历史写法。
    """

    baudrate: int
    dtr: bool
    rts: bool
    is_open: Any
    in_waiting: Any

    def read(self, size: int = 1, timeout: Optional[float] = None) -> bytes:
        ...

    def write(self, data: bytes) -> int:
        ...

    def flush(self) -> None:
        ...

    def reset_input_buffer(self) -> None:
        ...

    def reset_output_buffer(self) -> None:
        ...


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
