# -*- coding: utf-8 -*-
"""
PyMifareTool - 传输层工厂服务 (TransportFactory)
支持平滑接入 USB-COM 物理串口、BLE 蓝牙低功耗透传以及未来 TCP / Modbus 工业网关
"""

from typing import Dict, Any, Type, Optional
from .base import ITransport, TransportError
from .serial_transport import SerialTransport
from .tcp_transport import ModbusTcpTransport, TcpTransport


class TransportFactory:
    """传输层通道统一创建工厂"""

    TRANSPORT_SERIAL = "serial"
    TRANSPORT_BLE    = "ble"
    TRANSPORT_TCP    = "tcp"
    TRANSPORT_MODBUS = "modbus"

    _registry: Dict[str, Type[ITransport]] = {
        TRANSPORT_SERIAL: SerialTransport,
        TRANSPORT_TCP: TcpTransport,
        TRANSPORT_MODBUS: ModbusTcpTransport,
    }

    @classmethod
    def register_transport(cls, transport_type: str, transport_cls: Type[ITransport]):
        """动态注册新型传输协议驱动 (用于扩展 TCP/Modbus 等)"""
        cls._registry[transport_type.lower()] = transport_cls

    @classmethod
    def list_transports(cls) -> list:
        """获取所有已支持/注册的传输类型列表"""
        types = list(cls._registry.keys())
        if cls.TRANSPORT_BLE not in types:
            types.append(cls.TRANSPORT_BLE)
        return types

    @classmethod
    def create_transport(cls, transport_type: str = TRANSPORT_SERIAL, **kwargs) -> ITransport:
        """
        创建传输通道实例
        - serial: port, baudrate, timeout
        - ble: address, timeout
        """
        key = transport_type.lower()
        if key == cls.TRANSPORT_BLE:
            from .ble_transport import BleTransport
            return BleTransport(
                address=kwargs.get("address", ""),
                timeout=kwargs.get("timeout", 0.5)
            )
        elif key in cls._registry:
            return cls._registry[key](**kwargs)
        else:
            raise TransportError(f"未知的传输层协议类型: {transport_type}")
