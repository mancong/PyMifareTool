# -*- coding: utf-8 -*-
"""
PyMifareTool MCP 独立服务运行入口
支持以标准 stdio 模式或 HTTP/SSE 模式启动对外 MCP 服务。
"""

import os
import sys
import argparse
import asyncio
import tempfile
import logging

# 避免 Matplotlib 在受限 Windows 主目录下创建缓存报 [WinError 5] 拒绝访问
if "MPLCONFIGDIR" not in os.environ:
    os.environ["MPLCONFIGDIR"] = os.path.join(tempfile.gettempdir(), "matplotlib")

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

    # 1. 智能定位配置文件
    candidate_paths = [
        os.path.abspath(args.config),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), args.config),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), args.config),
    ]
    config_path = None
    for p in candidate_paths:
        if os.path.exists(p):
            config_path = p
            break

    if config_path:
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

    if config.transport_mode == "sse":
        sse_url = f"http://{config.host}:{config.port}/sse"
        msg_url = f"http://{config.host}:{config.port}/messages/"
        banner = f"""
======================================================================
🚀 PyMifareTool MCP 服务已就绪 [网络 HTTP/SSE 模式]
======================================================================
服务名称: {config.server_name}
服务监听: http://{config.host}:{config.port}
🔗 SSE 订阅端点:   {sse_url}
✉️  消息交互端点:  {msg_url}
💡 第三方客户端配置指引:
   在支持 SSE 模式的 MCP 客户端（如 Cursor、远程 Agent）中添加:
   URL: {sse_url}
======================================================================
"""
        print(banner, file=sys.stdout)
        logger.info("SSE 服务监听中，按 Ctrl+C 可停止服务...")
        mcp.settings.host = config.host
        mcp.settings.port = config.port
        mcp.run(transport="sse")
    else:
        banner = f"""
======================================================================
🚀 PyMifareTool MCP 服务已就绪 [标准输入输出 stdio 模式]
======================================================================
服务名称: {config.server_name}
工作机制: 进程内标准输入输出流 (stdin / stdout) 通信
使用场景: 本地客户端（Claude Desktop, Cursor, Cline, Antigravity 等）
提示说明: stdio 模式专供本地 Agent 进程管道交互，不开放网络端口。
        若需要网络/HTTP/SSE 访问，请运行:
        python mcp_server.py --transport sse --host 0.0.0.0 --port 8000
======================================================================
"""
        # stdio 模式下普通信息输出到 stderr，防止污染 stdout 的 JSON-RPC 报文
        print(banner, file=sys.stderr)
        logger.info("stdio 模式等待来自客户端的 JSON-RPC 管道调用...")
        mcp.run(transport="stdio")


if __name__ == "__main__":
    sys.exit(main())
