# -*- coding: utf-8 -*-
"""
PyMifareTool MCP 工具集 - 硬件连接与通信管理 (Hardware Management)
提供物理串口扫描、读写器连接握手、断开与硬件能力矩阵探测
"""

import serial.tools.list_ports
from mcp.server.fastmcp import FastMCP
from typing import Dict, Any
from mcp_server.context import McpContext
from core.services.capability_probe import build_device_capabilities


def register_hardware_tools(mcp: FastMCP, ctx: McpContext):
    """注册硬件通信管理相关 MCP 异步工具"""

    @mcp.tool()
    async def list_serial_ports() -> Dict[str, Any]:
        """
        扫描并列出当前操作系统中所有可用的物理串口与 USB 转串口设备列表。

        返回:
            包含可用串口列表的字典，每个条目包含 port(串口号), description(设备描述), hwid(硬件ID) 等信息。
        """
        ports_info = []
        for p in serial.tools.list_ports.comports():
            ports_info.append({
                "port": p.device,
                "description": p.description,
                "hwid": p.hwid,
                "manufacturer": getattr(p, "manufacturer", None),
                "product": getattr(p, "product", None),
            })
        return {
            "ok": True,
            "count": len(ports_info),
            "ports": ports_info,
            "connected_port": ctx.port if ctx.is_connected else None,
        }

    @mcp.tool()
    async def connect_reader(
        port: str = "COM3",
        baudrate: int = 115200,
        device_type: str = "auto"
    ) -> Dict[str, Any]:
        """
        连接指定的读写器硬件设备，并执行芯片唤醒与自适应驱动探测。

        参数:
            port: 物理串口号 (例如 'COM3', 'COM4' 或 Linux/macOS 下的 '/dev/ttyUSB0')
            baudrate: 串口通信波特率，PCR532/PN532 默认为 115200，简易广播器默认为 38400
            device_type: 驱动类型，支持 'auto'(自适应探测), 'pn532', 'broadcaster'(广播器), 'virtual'(虚拟卡)

        返回:
            连接状态字典，包含是否连接成功、设备型号、固件版本与基础能力信息。
        """
        return await ctx.connect_reader(port=port, baudrate=baudrate, device_type=device_type)

    @mcp.tool()
    async def disconnect_reader() -> Dict[str, Any]:
        """
        安全断开当前已连接的读写器硬件，释放串口占用与硬件锁。

        返回:
            断开结果与提示信息。
        """
        return await ctx.disconnect_reader()

    @mcp.tool()
    async def get_device_status() -> Dict[str, Any]:
        """
        获取当前硬件链路的连接状态、设备参数、固件版本与缓存 UID。

        返回:
            当前连接的读写器状态字典。
        """
        if not ctx.is_connected:
            return {
                "ok": True,
                "connected": False,
                "message": "当前未连接任何读写器设备，请先调用 connect_reader 连接。",
            }

        adapter = ctx.adapter
        return {
            "ok": True,
            "connected": True,
            "port": ctx.port,
            "baudrate": ctx.baudrate,
            "device_name": adapter.device_name,
            "is_bidirectional": adapter.is_bidirectional,
            "firmware_info": getattr(adapter, "firmware_info", "未知固件"),
            "cached_uid": adapter.cached_uid.hex().upper() if getattr(adapter, "cached_uid", None) else None,
        }

    @mcp.tool()
    async def probe_capabilities() -> Dict[str, Any]:
        """
        全面探测当前读写器硬件能力与外部攻击工具链状态。
        评估项涵盖：PN532 HSU、SAM 配置、M1 认证读写、二代身份证 Type B、CPU 卡 APDU、Crypto1 与 Hardnested 工具链可用性。

        返回:
            包含详细软硬件功能矩阵 (supported / needs_card / external / unsupported) 的字典。
        """
        if not ctx.is_connected:
            return {
                "ok": False,
                "error": "设备未连接，无法执行能力探测，请先调用 connect_reader。",
            }

        def _do_probe():
            try:
                caps = build_device_capabilities(
                    ctx.adapter,
                    connection="serial",
                    port=ctx.port,
                    baudrate=ctx.baudrate
                )
                return {"ok": True, "capabilities": caps}
            except Exception as e:
                return {"ok": False, "error": f"探测能力失败: {e}"}

        return await ctx.run_io(_do_probe)
