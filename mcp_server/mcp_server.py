# -*- coding: utf-8 -*-
"""
PyMifareTool MCP 独立服务运行入口
支持以标准 stdio 模式或 HTTP/SSE 模式启动对外 MCP 服务。
"""

import os
import sys
import argparse
import asyncio
import logging

# 确保 UTF-8 编码
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from mcp_server.config import McpServerConfig
from mcp_server.server import create_mcp_server


def setup_logging(is_stdio: bool):
    """配置日志格式与输出流：stdio 模式必须输出到 stderr 防止污染 JSON-RPC 协议帧"""
    handler = logging.StreamHandler(sys.stderr if is_stdio else sys.stdout)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [MCP] %(message)s",
        datefmt="%H:%M:%S"
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)


def parse_args():
    parser = argparse.ArgumentParser(description="PyMifareTool Model Context Protocol (MCP) 服务")
    parser.add_argument(
        "--config", "-c",
        default="mcp_server_config.json",
        help="MCP 配置文件路径 (默认: mcp_server_config.json)"
    )
    parser.add_argument(
        "--transport", "-t",
        choices=["stdio", "sse"],
        help="传输模式: stdio 或 sse (覆盖配置文件)"
    )
    parser.add_argument(
        "--host",
        help="SSE 模式绑定的 IP 地址 (例如 127.0.0.1 或 0.0.0.0)"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        help="SSE 模式监听的端口号 (例如 8000)"
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="打印当前已激活注册的所有 MCP 工具清单及其说明"
    )
    return parser.parse_args()


async def list_tools_cli(mcp):
    """展示当前注册的全部 MCP 工具"""
    tools = await mcp.list_tools()
    print("=" * 70)
    print(f"📦 PyMifareTool MCP 已就绪工具列表 (共 {len(tools)} 个):")
    print("=" * 70)
    for idx, t in enumerate(tools, 1):
        desc = (t.description or "无描述").strip().split("\n")[0]
        print(f"[{idx:02d}] 🔧 {t.name}")
        print(f"     说明: {desc}")
    print("=" * 70)


def main():
    args = parse_args()

    # 1. 加载或新建配置
    config_path = os.path.abspath(args.config)
    if os.path.exists(config_path):
        config = McpServerConfig.from_file(config_path)
    else:
        config = McpServerConfig()
        if args.config != "mcp_server_config.json":
            print(f"[警告] 指定的配置文件 {args.config} 不存在，已使用默认配置。", file=sys.stderr)

    # 2. 命令行参数优先覆盖配置
    if args.transport:
        config.transport_mode = args.transport
    if args.host:
        config.host = args.host
    if args.port:
        config.port = args.port

    is_stdio = (config.transport_mode == "stdio")
    setup_logging(is_stdio)
    logger = logging.getLogger("PyMifareTool.MCP")

    # 3. 构造服务
    mcp, ctx = create_mcp_server(config)

    # 如果仅列出工具
    if args.list_tools:
        asyncio.run(list_tools_cli(mcp))
        return 0

    logger.info("PyMifareTool MCP 服务启动中... [服务名: %s, 传输协议: %s]", config.server_name, config.transport_mode)

    try:
        if config.transport_mode == "sse":
            logger.info("正在以 SSE 模式监听 http://%s:%d/ ...", config.host, config.port)
            mcp.settings.host = config.host
            mcp.settings.port = config.port
            mcp.run(transport="sse")
        else:
            logger.info("正在以标准 stdio 模式运行...")
            mcp.run(transport="stdio")
    except (KeyboardInterrupt, SystemExit):
        logger.info("PyMifareTool MCP 服务正常关闭。")
    finally:
        ctx.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
