# -*- coding: utf-8 -*-
"""
PyMifareTool - MCP (Model Context Protocol) 服务端配置中心
支持通过 JSON 配置文件、环境变量或命令行参数对 MCP 服务端进行动态定制
支持配置运行模式 (stdio/sse)、监听 IP/端口、启用的功能模块子集与安全限制
"""

import os
import json
from enum import Enum
from typing import List, Dict, Any, Optional

DEFAULT_CONFIG_FILENAME = "mcp_server_config.json"


class McpFeatureCategory(str, Enum):
    """MCP 服务功能大类定义"""
    HARDWARE = "hardware"             # 硬件串口连接与设备状态管理
    CARD = "card"                     # 射频寻卡、在位检测与 UID 多格式转换
    M1 = "m1"                         # Mifare Classic 扇区认证、块读写与魔术卡操作
    CRACKING = "cracking"             # 智能字典破解与密钥库管理
    ID_CARD = "id_card"               # ISO14443-B 二代居民身份证专用握手
    CPU_CARD = "cpu_card"             # ISO14443-4 CPU 智能卡、APDU 与交通联合/PBOC 数据
    DUMP = "dump"                     # Dump 导出导入、完整性校验、纠错与差分对比
    DATABASE = "database"             # 卡片档案管理与刷卡流水审计
    EXTERNAL_TOOLS = "external_tools" # 外部安全工具链状态 (mfoc, mfcuk, hardnested)


ALL_CATEGORIES: List[str] = [cat.value for cat in McpFeatureCategory]


class McpServerConfig:
    """MCP 服务端运行与安全配置模型"""

    def __init__(
        self,
        transport: str = "stdio",
        host: str = "127.0.0.1",
        port: int = 8000,
        server_name: str = "PyMifareTool-MCP",
        enabled_categories: Optional[List[str]] = None,
        disabled_tools: Optional[List[str]] = None,
        allow_block0_write: bool = False,
        default_port: str = "COM3",
        default_baudrate: int = 115200,
        default_device_type: str = "auto",
        db_path: Optional[str] = None,
    ):
        self.server_name = server_name
        self.transport = transport.lower()
        self.host = host
        self.port = port
        self.enabled_categories = list(enabled_categories) if enabled_categories is not None else list(ALL_CATEGORIES)
        self.disabled_tools = list(disabled_tools) if disabled_tools is not None else []
        self.allow_block0_write = bool(allow_block0_write)
        self.default_port = default_port
        self.default_baudrate = default_baudrate
        self.default_device_type = default_device_type
        self.db_path = db_path

    @property
    def transport_mode(self) -> str:
        return self.transport

    @transport_mode.setter
    def transport_mode(self, val: str):
        self.transport = val.lower()

    def is_category_enabled(self, category: Any) -> bool:
        """检查特定功能类别是否已配置启用"""
        cat_str = category.value if isinstance(category, Enum) else str(category)
        return cat_str in self.enabled_categories

    def is_tool_enabled(self, tool_name: str) -> bool:
        """检查特定工具是否未被显式禁用"""
        return tool_name not in self.disabled_tools

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典对象"""
        return {
            "server_name": self.server_name,
            "transport_mode": self.transport,
            "host": self.host,
            "port": self.port,
            "enabled_categories": self.enabled_categories,
            "disabled_tools": self.disabled_tools,
            "allow_block0_write": self.allow_block0_write,
            "default_port": self.default_port,
            "default_baudrate": self.default_baudrate,
            "default_device_type": self.default_device_type,
            "db_path": self.db_path,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "McpServerConfig":
        """从字典载入配置"""
        t = data.get("transport_mode") or data.get("transport", "stdio")
        return cls(
            server_name=data.get("server_name", "PyMifareTool-MCP"),
            transport=t,
            host=data.get("host", "127.0.0.1"),
            port=int(data.get("port", 8000)),
            enabled_categories=data.get("enabled_categories", ALL_CATEGORIES),
            disabled_tools=data.get("disabled_tools", []),
            allow_block0_write=bool(data.get("allow_block0_write", False)),
            default_port=data.get("default_port", "COM3"),
            default_baudrate=int(data.get("default_baudrate", 115200)),
            default_device_type=data.get("default_device_type", "auto"),
            db_path=data.get("db_path"),
        )

    @classmethod
    def from_file(cls, filepath: str) -> "McpServerConfig":
        """从文件绝对或相对路径加载"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "McpServerConfig":
        """
        自适应载入配置文件，优先级：
        1. 指定的 config_path 路径
        2. 环境变量 PYMIFARE_MCP_CONFIG 指定路径
        3. 项目根目录下的 mcp_server_config.json
        4. 全局默认配置 (并自动落盘模板)
        """
        target_path = config_path or os.environ.get("PYMIFARE_MCP_CONFIG")
        if not target_path:
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            target_path = os.path.join(root_dir, DEFAULT_CONFIG_FILENAME)

        if os.path.exists(target_path):
            try:
                return cls.from_file(target_path)
            except Exception:
                pass

        default_cfg = cls()
        try:
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(default_cfg.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        return default_cfg
