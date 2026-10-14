# -*- coding: utf-8 -*-
"""
PyMifareTool - M1 卡数据内存模型与 Dump 导入导出门面 (Dump Model Facade)
向下兼容提供原 core.dump_model 中的 MifareDump 与 BlockState
底层实现已解耦收敛至 core.models.dump
"""

from core.models.dump import MifareDump, BlockState

__all__ = ["MifareDump", "BlockState"]