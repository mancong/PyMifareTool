"""
PyMifareTool MCP 卡片档案与刷卡审计数据库工具集
"""

from typing import Dict, Any
import asyncio
from mcp.server.fastmcp import FastMCP
from core.models.card_converter import CardConverter
from mcp_server.context import McpContext


def register_database_tools(mcp: FastMCP, ctx: McpContext) -> None:
    """注册卡片档案库与流水审计相关的 MCP 工具"""

    @mcp.tool(
        name="query_card_profile",
        description="""从本地 SQLite 数据库中查询指定卡号 (UID) 的登记档案。
包含：卡片自定义名称、持卡人姓名、卡片类型、10位十进制内码、韦根26/34编码、备注说明、登记建档时间、最近刷卡时间及累计刷卡计数。"""
    )
    async def query_card_profile(uid: str) -> Dict[str, Any]:
        cleaned_uid = uid.replace(" ", "").upper()
        db = ctx.get_db()
        card = await asyncio.to_thread(db.get_card, cleaned_uid)
        if not card:
            return {
                "found": False,
                "uid": cleaned_uid,
                "message": f"卡片档案中未查询到 UID: {cleaned_uid}"
            }

        return {
            "found": True,
            "uid": card.get("uid"),
            "card_name": card.get("card_name"),
            "card_holder": card.get("card_holder"),
            "card_type": card.get("card_type"),
            "dec_10d": card.get("dec_10d"),
            "wiegand_26": card.get("wiegand_26"),
            "wiegand_34": card.get("wiegand_34"),
            "note": card.get("note"),
            "created_at": card.get("created_at"),
            "last_swiped_at": card.get("last_swiped_at"),
            "swipe_count": card.get("swipe_count", 0)
        }

    @mcp.tool(
        name="upsert_card_profile",
        description="""在本地数据库中创建或更新指定卡片 (UID) 的管理档案。
如果档案已存在则更新属性，不存在则新建档案并自动计算门禁 8H10D、WG26、WG34 编码。"""
    )
    async def upsert_card_profile(
        uid: str,
        card_name: str = "",
        card_holder: str = "",
        card_type: str = "M1 IC卡",
        note: str = ""
    ) -> Dict[str, Any]:
        cleaned_uid = uid.replace(" ", "").upper()
        try:
            conv_info = CardConverter.convert(bytes.fromhex(cleaned_uid))
        except Exception:
            conv_info = {}

        db = ctx.get_db()
        ok = await asyncio.to_thread(
            db.upsert_card,
            uid=cleaned_uid,
            card_name=card_name,
            card_holder=card_holder,
            card_type=card_type,
            note=note,
            conv_info=conv_info
        )

        return {
            "success": bool(ok),
            "uid": cleaned_uid,
            "card_name": card_name,
            "card_holder": card_holder,
            "message": f"卡片档案 {cleaned_uid} 保存成功" if ok else "保存卡片档案失败"
        }

    @mcp.tool(
        name="list_registered_cards",
        description="""查询并列出本地数据库中已建档的所有卡片列表。"""
    )
    async def list_registered_cards() -> Dict[str, Any]:
        db = ctx.get_db()
        cards = await asyncio.to_thread(db.list_all_cards)
        return {
            "count": len(cards),
            "cards": cards
        }

    @mcp.tool(
        name="get_swipe_history",
        description="""查询卡片被读卡器感应刷卡的历史审计日志流水。
支持通过 limit 参数限制返回最近记录条数（默认 50 条）。"""
    )
    async def get_swipe_history(limit: int = 50) -> Dict[str, Any]:
        db = ctx.get_db()
        logs = await asyncio.to_thread(db.list_recent_logs, limit=limit)
        return {
            "count": len(logs),
            "logs": logs
        }

    @mcp.tool(
        name="record_swipe_log",
        description="""手动或主动向数据库流水日志中追加一条刷卡记录。
同时会自动触发对应卡片档案中的累计刷卡次数累加与最近刷卡时间刷新。"""
    )
    async def record_swipe_log(uid: str, raw_hex: str = "") -> Dict[str, Any]:
        cleaned_uid = uid.replace(" ", "").upper()
        try:
            conv_info = CardConverter.convert(bytes.fromhex(cleaned_uid))
        except Exception:
            conv_info = {}

        db = ctx.get_db()
        ok = await asyncio.to_thread(db.record_swipe, cleaned_uid, conv_info, raw_hex)
        return {
            "success": bool(ok),
            "uid": cleaned_uid,
            "message": f"已成功为卡片 {cleaned_uid} 记录刷卡流水"
        }
