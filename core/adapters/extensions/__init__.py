# -*- coding: utf-8 -*-
"""
PyMifareTool - 硬件适配器未来扩展插槽库 (Hardware Adapter Extensions)
预留 PC/SC (ACR122U)、虚拟离线卡片仿真等插件化适配器
"""

from .pcsc_adapter import PCSCReaderAdapter
from .virtual_adapter import VirtualDumpReaderAdapter

__all__ = [
    "PCSCReaderAdapter",
    "VirtualDumpReaderAdapter",
]
