# -*- coding: utf-8 -*-
"""PyMifareTool 核心包初始化与基础日志配置"""

import logging

logger = logging.getLogger("pymifare")
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
