# -*- coding: utf-8 -*-
"""
PyMifareTool MCP 快捷启动入口
将实际执行代理至独立目录 mcp_server.mcp_server
"""

import sys
from mcp_server.mcp_server import main

if __name__ == "__main__":
    sys.exit(main())
