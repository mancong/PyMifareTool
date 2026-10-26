"""
PyMifareTool MCP 二代身份证 (ISO/IEC 14443-B) 工具集
"""

from typing import Dict, Any
from mcp.server.fastmcp import FastMCP
from core.models.card_converter import CardConverter
from mcp_server.context import McpContext


def register_id_card_tools(mcp: FastMCP, ctx: McpContext) -> None:
    """注册二代居民身份证相关的 MCP 工具"""

    @mcp.tool(
        name="read_id_card",
        description="""针对放置在天线区域的中国二代居民身份证（ISO/IEC 14443-B 非标协议）执行物理底层读取。
执行完整的 Type B 射频寄存器配置 -> REQB/ATQB 握手 -> 提取 4 字节 PUPI -> ATTRIB 激活 -> 读取 8 字节 GUID 指令链路。
返回内容包含：8 字节物理 GUID/UID 十六进制、4 字节 PUPI、门禁常用 8H10D/WG26/WG34 编码格式。
执行后将自动且严格复位射频寄存器至标准 Type A，确保后续普通 M1 卡与 CPU 卡读写兼容。"""
    )
    async def read_id_card() -> Dict[str, Any]:
        try:
            res = await ctx.call_adapter("read_id_card_uid", timeout=0.6)
            if not res:
                return {
                    "success": False,
                    "message": "未检测到二代身份证或读取超时。请将身份证平放紧贴读卡器线圈后重试。"
                }

            guid_hex = res.get("uid", "")
            pupi_hex = res.get("pupi", "")
            formats = res.get("formats", {})

            if not formats and guid_hex:
                try:
                    formats = CardConverter.convert(bytes.fromhex(guid_hex))
                except Exception:
                    pass

            return {
                "success": True,
                "card_type": "中华人民共和国居民身份证 (ISO14443-B)",
                "guid": guid_hex,
                "pupi": pupi_hex,
                "formats": formats,
                "message": f"成功读取二代身份证物理 GUID: {guid_hex}"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"读取二代身份证发生异常: {e}"
            }
