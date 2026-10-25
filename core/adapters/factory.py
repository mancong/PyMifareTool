# -*- coding: utf-8 -*-
"""
PyMifareTool - 读卡器适配器工厂与自动探测服务 (ReaderAdapterFactory)
支持插件式扩展注册第三方驱动与虚拟离线仿真
"""

import time
from typing import Optional, List, Dict, Type
from .base_adapter import BaseReaderAdapter
from core.transport.base import TransportLike
from .pn532_adapter import PN532Adapter
from .broadcaster_adapter import BroadcasterAdapter


class ReaderAdapterFactory:
    """读卡器驱动工厂 (支持动态扩展与自动嗅探)"""

    DEVICE_AUTO = "auto"
    DEVICE_PN532 = "pn532"
    DEVICE_BROADCASTER = "broadcaster"
    DEVICE_VIRTUAL = "virtual"
    DEVICE_PCSC = "pcsc"
    DEVICE_LIBNFC = "libnfc"

    DEVICE_CHOICES = [
        ("⚡ 自动识别硬件 (推荐)", DEVICE_AUTO),
        ("🚀 PCR532 / PN532 双向读写器", DEVICE_PN532),
        ("📻 简易广播发卡器", DEVICE_BROADCASTER),
        ("💻 软件虚拟卡离线仿真", DEVICE_VIRTUAL),
    ]

    # 动态注册表，供未来插件或扩展模块动态注入新驱动
    _custom_registry: Dict[str, Type[BaseReaderAdapter]] = {}

    @classmethod
    def register_adapter(cls, device_type: str, adapter_cls: Type[BaseReaderAdapter]):
        """注册新的硬件驱动适配器类 (扩展插槽)"""
        cls._custom_registry[device_type.lower()] = adapter_cls

    @classmethod
    def create_adapter(cls, device_type: str = DEVICE_AUTO) -> BaseReaderAdapter:
        device_type_key = device_type.lower()
        if device_type_key in cls._custom_registry:
            return cls._custom_registry[device_type_key]()

        if device_type_key == cls.DEVICE_PN532:
            return PN532Adapter()
        elif device_type_key == cls.DEVICE_BROADCASTER:
            return BroadcasterAdapter()
        elif device_type_key == cls.DEVICE_VIRTUAL:
            from .extensions.virtual_adapter import VirtualDumpReaderAdapter
            return VirtualDumpReaderAdapter()
        elif device_type_key == cls.DEVICE_PCSC:
            from .extensions.pcsc_adapter import PCSCReaderAdapter
            return PCSCReaderAdapter()
        elif device_type_key == cls.DEVICE_LIBNFC:
            from .libnfc_adapter import LibnfcCliAdapter
            return LibnfcCliAdapter()
        else:
            # 默认为 PN532 兼容优先
            return PN532Adapter()

    @classmethod
    def probe_device(cls, ser: TransportLike, preferred_type: str = DEVICE_AUTO) -> BaseReaderAdapter:
        """
        在已打开的串口上自动探测读卡器型号
        优先尝试 PN532 唤醒与固件版本握手
        若无应答则优雅降级为 Broadcaster 兼容模式
        """
        if preferred_type == cls.DEVICE_BROADCASTER:
            adapter = BroadcasterAdapter()
            adapter.init_device(ser)
            return adapter

        if preferred_type == cls.DEVICE_PN532:
            adapter = PN532Adapter()
            adapter.init_device(ser)
            return adapter

        if preferred_type == cls.DEVICE_VIRTUAL:
            from .extensions.virtual_adapter import VirtualDumpReaderAdapter
            adapter = VirtualDumpReaderAdapter()
            adapter.init_device(ser)
            return adapter

        if preferred_type == cls.DEVICE_LIBNFC:
            from .libnfc_adapter import LibnfcCliAdapter
            adapter = LibnfcCliAdapter()
            adapter.init_device(ser)
            return adapter

        # 自动识别逻辑
        # 1. 尝试初始化 PN532
        pn532 = PN532Adapter()
        if pn532.init_device(ser):
            fw = pn532.get_firmware_version(ser)
            if "PN532" in fw:
                return pn532

        # 2. 检查是否有 AA BB 广播数据流
        time.sleep(0.08)
        if ser.in_waiting > 0:
            peek_data = ser.read(ser.in_waiting)
            if b"\xAA\xBB" in peek_data:
                broadcaster = BroadcasterAdapter()
                broadcaster.init_device(ser)
                return broadcaster

        # 3. 根据波特率推断
        if ser.baudrate == 38400:
            broadcaster = BroadcasterAdapter()
            broadcaster.init_device(ser)
            return broadcaster

        return pn532
