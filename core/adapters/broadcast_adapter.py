# -*- coding: utf-8 -*-
"""
PyMifareTool - 板载串口单向 UID 广播发卡器适配器 (兼容别名)
已统一重构至 core.adapters.broadcaster_adapter.BroadcasterAdapter
"""

from .broadcaster_adapter import BroadcasterAdapter

# 向后兼容别名
BroadcastSerialAdapter = BroadcasterAdapter

__all__ = ["BroadcastSerialAdapter", "BroadcasterAdapter"]
