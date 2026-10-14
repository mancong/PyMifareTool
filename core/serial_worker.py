# -*- coding: utf-8 -*-
"""
PyMifareTool - 异步串口监听工作线程门面 (Serial Worker Facade)
向下兼容提供原 core.serial_worker 中的 SerialWorker 类
底层实现已解耦收敛至 core.services.serial_worker
"""

from core.services.serial_worker import SerialWorker

__all__ = ["SerialWorker"]
