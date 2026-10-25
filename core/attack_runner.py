# -*- coding: utf-8 -*-
"""
PyMifareTool - 外部攻击工具链执行器门面 (Attack Runner Facade)
向下兼容提供原 core.attack_runner 中的 AttackRunner 与 BaseAttackEngine
底层实现已解耦收敛至 core.services.attack_runner
"""

from core.services.attack_runner import AttackRunner, BaseAttackEngine

__all__ = ["AttackRunner", "BaseAttackEngine"]
