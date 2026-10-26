"""
PyMifareTool MCP 基础寻卡与卡号转换工具集
"""

from typing import Dict, Any
from mcp.server.fastmcp import FastMCP
from core.models.card_converter import CardConverter
from mcp_server.context import McpContext


def register_card_tools(mcp: FastMCP, ctx: McpContext) -> None:
    """注册基础寻卡与卡号转换相关的 MCP 工具"""

    @mcp.tool(
        name="poll_card",
        description="""执行一次射频寻卡检测。
如果检测到 RFID/NFC 智能卡在读卡器射频区，将返回卡片的物理信息（包括 UID、ATQA、SAK、卡片预估类型、ATS 信息等）以及全套常用卡号格式换算（正逆序、8H10D、WG26、WG34）。
同时会自动将该卡设置为当前会话的目标活跃卡片，供后续读写与认证操作使用。"""
    )
    async def poll_card() -> Dict[str, Any]:
        try:
            card = await ctx.call_adapter("poll_card")
        except Exception as e:
            return {"success": False, "card_present": False, "message": f"寻卡异常: {e}"}

        if not card:
            return {
                "success": False,
                "card_present": False,
                "message": "射频区未检测到有效卡片，请将卡片贴近读卡器天线后重试"
            }

        uid_hex = card.get("uid", "")
        conv_info = {}
        if uid_hex:
            try:
                uid_bytes = bytes.fromhex(uid_hex)
                conv_info = CardConverter.convert(uid_bytes)
            except Exception:
                pass

        result = {
            "success": True,
            "card_present": True,
            "uid": uid_hex,
            "atqa": card.get("atqa", ""),
            "sak": card.get("sak", ""),
            "ats": card.get("ats", ""),
            "card_type": card.get("card_type", "未知卡类型"),
            "is_chinese_id": card.get("is_chinese_id", False),
            "formats": conv_info
        }
        ctx.current_card_info = result
        return result

    @mcp.tool(
        name="is_card_present",
        description="""快速检查目标卡片是否仍在感应区域中（原位存活探测）。
非侵入式探测，可用于在执行批量耗时任务前验证卡片是否被移开。"""
    )
    async def is_card_present() -> Dict[str, Any]:
        try:
            present = await ctx.call_adapter("is_card_present")
            return {
                "card_present": bool(present),
                "message": "卡片在位" if present else "卡片未处于感应区或已被移走"
            }
        except Exception as e:
            return {"card_present": False, "message": f"在位检测异常: {e}"}

    @mcp.tool(
        name="convert_uid_formats",
        description="""针对指定的 16 进制卡号 (UID) 执行全套卡号标准换算（无需物理连接读卡器）。
换算结果包括：大端/小端十六进制、8H10D（标准十位十进制门禁号）、WG26（韦根26）、WG34（韦根34）等门禁及一卡通标准编码。"""
    )
    async def convert_uid_formats(uid_hex: str) -> Dict[str, Any]:
        cleaned = uid_hex.replace(" ", "").replace(":", "").strip()
        try:
            uid_bytes = bytes.fromhex(cleaned)
        except ValueError:
            return {
                "success": False,
                "message": f"无效的十六进制 UID 格式: '{uid_hex}'"
            }

        conv = CardConverter.convert(uid_bytes)
        return {
            "success": True,
            "raw_hex": cleaned.upper(),
            "byte_length": len(uid_bytes),
            "formats": conv
        }
