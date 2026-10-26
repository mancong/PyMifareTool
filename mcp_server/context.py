# -*- coding: utf-8 -*-
"""
PyMifareTool - MCP 异步上下文与硬件状态管理器
管理读写器硬件连接单例、内存 Dump 会话与线程/协程安全调度
严格执行硬件交互红线：
1. DTR/RTS 恒为 False
2. 广播器只收不发
3. 射频半双工物理链路独占互斥 (通过 asyncio.Lock 与底层线程锁双重保护)
4. Block 0 默认防写入破坏
"""

import asyncio
import logging
from typing import Optional, Dict, Any, Callable
from core.transport.serial_transport import SerialTransport
from core.adapters.base_adapter import BaseReaderAdapter
from core.adapters.factory import ReaderAdapterFactory
from core.models.dump import MifareDump
from core.card_db import CardDatabase
from .config import McpServerConfig

logger = logging.getLogger("pymifare.mcp.context")


class McpContext:
    """MCP 服务全局运行上下文与硬件单例生命周期管理"""

    def __init__(self, config: Optional[McpServerConfig] = None):
        self.config = config or McpServerConfig()
        self._lock = asyncio.Lock()  # 异步独占硬件锁，防止并发下发指令引发射频冲突
        self.transport: Optional[SerialTransport] = None
        self.adapter: Optional[BaseReaderAdapter] = None
        self.port: str = self.config.default_port
        self.baudrate: int = self.config.default_baudrate
        self.device_type: str = self.config.default_device_type

        # 内存中当前激活的卡片 Dump 模型 (用于连续读卡、分析、改写和存盘)
        self.active_dump: MifareDump = MifareDump()
        # 数据库实例
        self.db: CardDatabase = CardDatabase(self.config.db_path)
        # 临时破解/命中密钥缓存: {sector: {"key_a": hex_str, "key_b": hex_str}}
        self.recovered_keys: Dict[int, Dict[str, str]] = {}
        # 当前感应区内检测到的活跃卡片信息
        self.current_card_info: Optional[Dict[str, Any]] = None

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock

    @property
    def current_dump(self) -> MifareDump:
        return self.active_dump

    @current_dump.setter
    def current_dump(self, val: MifareDump):
        self.active_dump = val

    @property
    def known_keys(self) -> Dict[int, Dict[str, str]]:
        return self.recovered_keys

    @known_keys.setter
    def known_keys(self, val: Dict[int, Dict[str, str]]):
        self.recovered_keys = val

    def is_connected(self) -> bool:
        """检查硬件链路是否处于开启可用状态"""
        return bool(self.transport is not None and self.transport.is_open and self.adapter is not None)

    @property
    def connected(self) -> bool:
        return self.is_connected()

    async def run_io(self, fn: Callable, *args, **kwargs) -> Any:
        """
        在全局异步事件循环中，安全互斥调度执行底层同步物理 I/O 操作
        通过 asyncio.Lock 保证半双工射频独占，并通过 asyncio.to_thread 移至工作线程避免阻塞事件循环
        """
        async with self._lock:
            return await asyncio.to_thread(fn, *args, **kwargs)

    async def call_adapter(self, method_name: str, *args, **kwargs) -> Any:
        """
        安全在后台工作线程中调用适配器方法，自动注入当前已打开的 transport
        """
        if not self.is_connected():
            raise RuntimeError("当前未连接任何读写器设备，请先调用 connect_reader 连接硬件")
        adapter = self.get_adapter()
        method = getattr(adapter, method_name, None)
        if not method or not callable(method):
            raise AttributeError(f"适配器 {adapter.device_name} 不支持功能 '{method_name}'")
        return await self.run_io(method, self.transport, *args, **kwargs)

    async def connect_reader(
        self,
        port: Optional[str] = None,
        baudrate: Optional[int] = None,
        device_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """连接并初始化读写器设备"""
        target_port = port or self.port or self.config.default_port
        target_baud = baudrate or self.baudrate or self.config.default_baudrate
        target_dev = device_type or self.device_type or self.config.default_device_type

        def _do_connect():
            # 1. 若已有连接，先断开
            if self.transport and self.transport.is_open:
                try:
                    self.transport.close()
                except Exception:
                    pass
                self.transport = None
                self.adapter = None

            # 2. 创建物理串口传输并打开
            transport = SerialTransport(port=target_port, baudrate=target_baud)
            if not transport.open():
                return {"ok": False, "error": f"无法打开物理串口 {target_port} (波特率 {target_baud})"}

            # 3. 自动探测或创建指定驱动适配器
            try:
                adapter = ReaderAdapterFactory.probe_device(transport, preferred=target_dev)
                init_ok = adapter.init_device(transport)
                self.transport = transport
                self.adapter = adapter
                self.port = target_port
                self.baudrate = target_baud
                self.device_type = target_dev

                caps = adapter.get_capabilities() if hasattr(adapter, "get_capabilities") else {}
                return {
                    "ok": True,
                    "init_ok": init_ok,
                    "device_name": adapter.device_name,
                    "port": target_port,
                    "baudrate": target_baud,
                    "is_bidirectional": adapter.is_bidirectional,
                    "firmware_info": getattr(adapter, "firmware_info", "未知固件"),
                    "capabilities": caps,
                }
            except Exception as e:
                transport.close()
                return {"ok": False, "error": f"读写器设备初始化或探测失败: {e}"}

        return await self.run_io(_do_connect)

    async def disconnect_reader(self) -> Dict[str, Any]:
        """断开当前读写器硬件连接"""
        def _do_disconnect():
            if not self.transport or not self.transport.is_open:
                return {"ok": True, "message": "当前未连接任何读写器设备"}
            old_port = self.port
            try:
                self.transport.close()
            except Exception as e:
                logger.debug("断开串口异常: %s", e)
            self.transport = None
            self.adapter = None
            return {"ok": True, "message": f"读写器已安全断开 (端口: {old_port})"}

        return await self.run_io(_do_disconnect)

    def close(self):
        """释放所有上下文资源与数据库连接"""
        if self.transport and self.transport.is_open:
            try:
                self.transport.close()
            except Exception:
                pass
        if self.db:
            try:
                self.db.close()
            except Exception:
                pass
