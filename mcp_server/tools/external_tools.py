"""
PyMifareTool MCP 外部攻击工具链环境探测工具集
"""

from typing import Dict, Any
import asyncio
from mcp.server.fastmcp import FastMCP
from core.services.capability_probe import check_external_tools, default_nfc_bin_dir
from mcp_server.context import McpContext


def register_external_tools(mcp: FastMCP, ctx: McpContext) -> None:
    """注册外部密码学攻击工具链状态检测相关的 MCP 工具"""

    @mcp.tool(
        name="get_external_tools_status",
        description="""探测本地工作区中外部高级密码学攻击工具链的可用状态与路径。
检测项目包括：
- mfoc (针对默认 Key 存在的 Nested 嵌套认证攻击)
- mfcuk (针对全加密无已知 Key 卡片的 Darkside 经典暗面漏洞攻击)
- libnfc_hardnested (针对加强型防探测 Hardnested 硬件卡片的暴力离线分析)
- mfdetect (侦听读卡器与卡片通信的嗅探探测器)
- nfc-list (LibNFC 原生卡片枚举诊断工具)"""
    )
    async def get_external_tools_status() -> Dict[str, Any]:
        bin_dir = default_nfc_bin_dir()
        tools_status = await asyncio.to_thread(check_external_tools, bin_dir)
        return {
            "success": True,
            "bin_dir": bin_dir,
            "tools": tools_status,
            "message": "已完成本地外部工具链就绪状态扫描"
        }
