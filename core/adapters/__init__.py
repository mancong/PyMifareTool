# -*- coding: utf-8 -*-
"""
PyMifareTool - 多硬件读写器驱动适配器层 (Hardware Adapters Layer)
支持 PCR532 / PN532 双向全功能读写器、经典广播发卡器与未来 PC/SC / 虚拟离线卡扩展
"""

from .base_adapter import BaseReaderAdapter
from .pn532_adapter import PN532Adapter
from .broadcaster_adapter import BroadcasterAdapter
from .libnfc_adapter import LibnfcCliAdapter
from .factory import ReaderAdapterFactory
from .extensions import PCSCReaderAdapter, VirtualDumpReaderAdapter

__all__ = [
    "BaseReaderAdapter",
    "PN532Adapter",
    "BroadcasterAdapter",
    "LibnfcCliAdapter",
    "ReaderAdapterFactory",
    "PCSCReaderAdapter",
    "VirtualDumpReaderAdapter",
]
