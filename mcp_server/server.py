"""
PyMifareTool - MCP (Model Context Protocol) 核心服务构造与生命周期管理
"""

import logging
from typing import Optional, Tuple
from mcp.server.fastmcp import FastMCP

from .config import McpServerConfig, McpFeatureCategory
from .context import McpContext

from .tools.hardware import register_hardware_tools
from .tools.card import register_card_tools
from .tools.m1 import register_m1_tools
from .tools.cracking import register_cracking_tools
from .tools.id_card import register_id_card_tools
from .tools.cpu_card import register_cpu_card_tools
from .tools.dump import register_dump_tools
from .tools.database import register_database_tools
from .tools.external_tools import register_external_tools

logger = logging.getLogger("PyMifareTool.MCP")


def create_mcp_server(config: Optional[McpServerConfig] = None) -> Tuple[FastMCP, McpContext]:
    """
    根据配置实例化并装配 PyMifareTool 全局异步 MCP 服务

    Args:
        config: MCP 服务配置对象，若为 None 则使用默认配置

    Returns:
        (FastMCP 实例, McpContext 共享上下文)
    """
    cfg = config or McpServerConfig()

    mcp = FastMCP(
        name=cfg.server_name,
        instructions="""PyMifareTool RFID/NFC 智能卡综合运维 MCP 服务。
支持 Mifare Classic 1K/4K 扇区认证读写与魔术卡改写、二代居民身份证 GUID 读取、
ISO14443-4 CPU 卡原生 APDU 交互与交通联合电子钱包查询、M1 字典暴力破解、
卡片档案 SQLite 数据库查询以及 Dump 镜像文件的全套操作。
本服务所有物理 I/O 操作均受异步独占锁保护并严格遵守 DTR/RTS 禁用硬件安全红线。"""
    )

    ctx = McpContext(config=cfg)

    # 动态拦截工具注册，依据配置字典进行细粒度启用/禁用过滤
    original_tool = mcp.tool

    def filtered_tool(*args, **kwargs):
        name_hint = kwargs.get("name")
        if not name_hint and args and isinstance(args[0], str):
            name_hint = args[0]

        def decorator(fn):
            actual_name = name_hint or getattr(fn, "__name__", "")
            if cfg.is_tool_enabled(actual_name):
                return original_tool(*args, **kwargs)(fn)
            logger.debug("工具 %s 已在配置中被禁用，跳过注册", actual_name)
            return fn

        return decorator

    mcp.tool = filtered_tool

    # 1. 注册基础状态工具
    @mcp.tool(
        name="get_mcp_service_status",
        description="""获取当前 PyMifareTool MCP 服务的运行状态、当前网络配置、读卡器硬件连接情况及已激活的功能工具分类列表。"""
    )
    async def get_mcp_service_status():
        enabled_categories = [
            cat.value for cat in McpFeatureCategory if cfg.is_category_enabled(cat)
        ]
        return {
            "server_name": cfg.server_name,
            "transport_mode": cfg.transport_mode,
            "host": cfg.host,
            "port": cfg.port,
            "hardware_connected": ctx.is_connected(),
            "connected_port": ctx.port if ctx.is_connected() else None,
            "connected_device": ctx.device_type if ctx.is_connected() else None,
            "enabled_feature_categories": enabled_categories,
            "active_card_uid": ctx.current_card_info.get("uid") if ctx.current_card_info else None
        }

    # 2. 依据配置动态注册各功能分类工具
    if cfg.is_category_enabled(McpFeatureCategory.HARDWARE):
        register_hardware_tools(mcp, ctx)

    if cfg.is_category_enabled(McpFeatureCategory.CARD):
        register_card_tools(mcp, ctx)

    if cfg.is_category_enabled(McpFeatureCategory.M1):
        register_m1_tools(mcp, ctx)

    if cfg.is_category_enabled(McpFeatureCategory.CRACKING):
        register_cracking_tools(mcp, ctx)

    if cfg.is_category_enabled(McpFeatureCategory.ID_CARD):
        register_id_card_tools(mcp, ctx)

    if cfg.is_category_enabled(McpFeatureCategory.CPU_CARD):
        register_cpu_card_tools(mcp, ctx)

    if cfg.is_category_enabled(McpFeatureCategory.DUMP):
        register_dump_tools(mcp, ctx)

    if cfg.is_category_enabled(McpFeatureCategory.DATABASE):
        register_database_tools(mcp, ctx)

    if cfg.is_category_enabled(McpFeatureCategory.EXTERNAL_TOOLS):
        register_external_tools(mcp, ctx)

    return mcp, ctx
