# -*- coding: utf-8 -*-
"""
PyMifareTool - MCP (Model Context Protocol) 服务端配置中心
支持通过 JSON 配置文件、环境变量或命令行参数对 MCP 服务端进行动态定制
支持配置运行模式 (stdio/sse)、监听 IP/端口、启用的功能模块子集与工具级精细开关 (Key-Value 字典)
"""

import os
import json
from enum import Enum
from typing import List, Dict, Any, Optional, Union

# 默认配置文件指向独立目录 mcp_server/mcp_server_config.json
DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server_config.json")


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

# 35 个全量工具列表及其所属大类映射
ALL_TOOLS_MAPPING: Dict[str, str] = {
    "get_mcp_service_status": "hardware",
    "list_serial_ports": "hardware",
    "connect_reader": "hardware",
    "disconnect_reader": "hardware",
    "get_device_status": "hardware",
    "probe_capabilities": "hardware",
    "poll_card": "card",
    "is_card_present": "card",
    "convert_uid_formats": "card",
    "authenticate_sector": "m1",
    "read_block": "m1",
    "write_block": "m1",
    "read_sector": "m1",
    "write_magic_block0": "m1",
    "lock_ufuid_card": "m1",
    "list_key_dictionaries": "cracking",
    "parse_key_dictionary_file": "cracking",
    "save_custom_keys": "cracking",
    "get_card_known_keys": "cracking",
    "crack_card_keys": "cracking",
    "read_id_card": "id_card",
    "send_apdu": "cpu_card",
    "read_cpu_card_public_info": "cpu_card",
    "scan_cpu_card_filesystem": "cpu_card",
    "load_dump_file": "dump",
    "save_dump_file": "dump",
    "get_dump_summary": "dump",
    "verify_and_repair_dump": "dump",
    "compare_dumps": "dump",
    "query_card_profile": "database",
    "upsert_card_profile": "database",
    "list_registered_cards": "database",
    "get_swipe_history": "database",
    "record_swipe_log": "database",
    "get_external_tools_status": "external_tools",
}


class McpServerConfig:
    """MCP 服务端运行与安全配置模型"""

    def __init__(
        self,
        transport: str = "stdio",
        host: str = "127.0.0.1",
        port: int = 8000,
        server_name: str = "PyMifareTool-MCP",
        enabled_categories: Optional[Union[Dict[str, bool], List[str]]] = None,
        enabled_tools: Optional[Union[Dict[str, bool], List[str]]] = None,
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
        self.allow_block0_write = bool(allow_block0_write)
        self.default_port = default_port
        self.default_baudrate = default_baudrate
        self.default_device_type = default_device_type
        self.db_path = db_path
        self.disabled_tools = list(disabled_tools) if disabled_tools is not None else []

        # 1. 解析分类配置：支持字典 {"hardware": True, "m1": False} 或列表 ["hardware", "m1"]
        self.categories_dict: Dict[str, bool] = {}
        if isinstance(enabled_categories, dict):
            self.categories_dict = {str(k): bool(v) for k, v in enabled_categories.items()}
        elif isinstance(enabled_categories, list):
            self.categories_dict = {cat: (cat in enabled_categories) for cat in ALL_CATEGORIES}
        else:
            self.categories_dict = {cat: True for cat in ALL_CATEGORIES}

        # 2. 解析工具级开关配置：支持字典 {"poll_card": True, "lock_ufuid_card": False} 或列表
        self.tools_dict: Dict[str, bool] = {}
        if isinstance(enabled_tools, dict):
            self.tools_dict = {str(k): bool(v) for k, v in enabled_tools.items()}
        elif isinstance(enabled_tools, list):
            self.tools_dict = {t: (t in enabled_tools) for t in ALL_TOOLS_MAPPING.keys()}
        else:
            self.tools_dict = {t: True for t in ALL_TOOLS_MAPPING.keys()}

    @property
    def transport_mode(self) -> str:
        return self.transport

    @transport_mode.setter
    def transport_mode(self, val: str):
        self.transport = val.lower()

    @property
    def enabled_categories(self) -> List[str]:
        """向后兼容属性：返回当前启用的分类字符串列表"""
        return [k for k, v in self.categories_dict.items() if v]

    @enabled_categories.setter
    def enabled_categories(self, val: Union[Dict[str, bool], List[str]]):
        if isinstance(val, dict):
            self.categories_dict = {str(k): bool(v) for k, v in val.items()}
        elif isinstance(val, list):
            self.categories_dict = {cat: (cat in val) for cat in ALL_CATEGORIES}

    def is_category_enabled(self, category: Any) -> bool:
        """检查特定功能类别是否启用"""
        cat_str = category.value if isinstance(category, Enum) else str(category)
        return self.categories_dict.get(cat_str, True)

    def is_tool_enabled(self, tool_name: str) -> bool:
        """检查特定工具是否已配置启用（综合分类总开关与工具独立细分开关）"""
        # 1. 显式禁用列表拦截
        if tool_name in self.disabled_tools:
            return False

        # 2. 工具独立开关判定
        if tool_name in self.tools_dict and not self.tools_dict[tool_name]:
            return False

        # 3. 工具所属分类总开关判定
        cat = ALL_TOOLS_MAPPING.get(tool_name)
        if cat and not self.is_category_enabled(cat):
            return False

        return True

    def to_dict(self) -> Dict[str, Any]:
        """序列化为标准 JSON 友好字典"""
        return {
            "server_name": self.server_name,
            "transport_mode": self.transport,
            "host": self.host,
            "port": self.port,
            "default_port": self.default_port,
            "default_baudrate": self.default_baudrate,
            "default_device_type": self.default_device_type,
            "allow_block0_write": self.allow_block0_write,
            "enabled_categories": self.categories_dict,
            "enabled_tools": self.tools_dict,
            "disabled_tools": self.disabled_tools,
            "db_path": self.db_path,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "McpServerConfig":
        """从字典载入配置（智能兼容各种结构）"""
        t = data.get("transport_mode") or data.get("transport", "stdio")
        return cls(
            server_name=data.get("server_name", "PyMifareTool-MCP"),
            transport=t,
            host=data.get("host", "127.0.0.1"),
            port=int(data.get("port", 8000)),
            enabled_categories=data.get("enabled_categories"),
            enabled_tools=data.get("enabled_tools") or data.get("tools"),
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
        """自适应加载配置文件，优先使用独立目录中的配置文件"""
        target_path = config_path or os.environ.get("PYMIFARE_MCP_CONFIG") or DEFAULT_CONFIG_PATH

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
