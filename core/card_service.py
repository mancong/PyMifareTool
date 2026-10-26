# -*- coding: utf-8 -*-
"""
DEPRECATED: 请直接从 core.services.card_worker 导入 CardOperationWorker, DEFAULT_KEYS_HEX！
此文件仅为旧代码路径提供向后兼容门面，不包含任何业务实现。

PyMifareTool - 卡片核心业务服务引擎与后台操作线程门面 (Card Service Facade)
向下兼容提供原 core.card_service 中的全部导出类与常量：
- CardOperationWorker: 三阶段智能并发字典破解/读卡/写卡工作线程
- DEFAULT_KEYS_HEX: 默认高频弱密钥表
底层实现已解耦收敛至 core.services.card_worker
"""

from core.services.card_worker import CardOperationWorker, DEFAULT_KEYS_HEX

__all__ = ["CardOperationWorker", "DEFAULT_KEYS_HEX"]
