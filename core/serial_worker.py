# -*- coding: utf-8 -*-
"""
DEPRECATED: 请直接从 core.services.serial_worker 导入 SerialWorker！
此文件仅为旧代码路径提供向后兼容门面，不包含任何业务实现。

PyMifareTool - 异步串口监听工作线程门面 (Serial Worker Facade)
向下兼容提供原 core.serial_worker 中的 SerialWorker 类
底层实现已解耦收敛至 core.services.serial_worker
"""

from core.services.serial_worker import SerialWorker

__all__ = ["SerialWorker"]
