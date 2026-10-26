# -*- coding: utf-8 -*-
"""
PyMifareTool MCP 快捷启动入口
将实际执行代理至独立目录 mcp_server.mcp_server
"""

import os
import sys
import tempfile

# 避免 Matplotlib 在受限 Windows 主目录下创建缓存报 [WinError 5] 拒绝访问
if "MPLCONFIGDIR" not in os.environ:
    os.environ["MPLCONFIGDIR"] = os.path.join(tempfile.gettempdir(), "matplotlib")

from mcp_server.mcp_server import main

if __name__ == "__main__":
    sys.exit(main())
