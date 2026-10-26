# -*- coding: utf-8 -*-
"""
DEPRECATED: 请直接从 core.services.key_manager 导入 KeyManager, KNOWN_KEY_FILES_INFO, KEYS_DIR_NAME！
此文件仅为旧代码路径提供向后兼容门面，不包含任何业务实现。

PyMifareTool - 密钥字典管理器门面 (Key Manager Facade)
向下兼容提供原 core.key_manager 中的全部导出类与元数据字典
底层实现已解耦收敛至 core.services.key_manager
"""

from core.services.key_manager import KeyManager, KNOWN_KEY_FILES_INFO, KEYS_DIR_NAME

__all__ = ["KeyManager", "KNOWN_KEY_FILES_INFO", "KEYS_DIR_NAME"]
