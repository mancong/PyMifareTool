# -*- coding: utf-8 -*-
"""
PyMifareTool - 读卡器能力汇总服务
只读取适配器初始化结果与本地工具链文件，不启动外部进程、不发送破坏性指令。
"""

import os
from typing import Any, Dict, Optional

from core.services.attack_runner import AttackRunner


def default_nfc_bin_dir() -> str:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(project_root, "tools", "m1t", "nfc-bin")


def check_external_tools(bin_dir: Optional[str] = None) -> Dict[str, bool]:
    return AttackRunner(bin_dir=bin_dir or default_nfc_bin_dir()).check_available_tools()


def _annotate_external_features(caps: Dict[str, Any], tools: Dict[str, bool]) -> None:
    requirements = {
        "darkside": ("mfcuk", "mfcuk / mfcuk2"),
        "nested": ("mfoc", "mfoc / mfoc2"),
        "hardnested": ("libnfc_hardnested", "libnfc_hardnested"),
    }
    for feature in caps.get("features", []):
        name = str(feature.get("name", ""))
        lowered = name.lower()
        if feature.get("status") not in ("external", "experimental"):
            continue
        if "crypto1" not in lowered and "hardnested" not in lowered and "nested" not in lowered:
            continue
        required_key = None
        required_label = None
        if "hardnested" in lowered:
            required_key, required_label = requirements["hardnested"]
        elif "darkside" in lowered:
            required_key, required_label = requirements["darkside"]
        elif "nested" in lowered:
            required_key, required_label = requirements["nested"]
        if not required_key:
            continue
        if not tools.get(required_key, False):
            feature["status"] = "unsupported"
            detail = feature.get("detail", "")
            feature["detail"] = f"{detail}；未找到 {required_label}"


def build_device_capabilities(
    adapter: Any,
    connection: str = "serial",
    port: str = "",
    baudrate: int = 0,
    bin_dir: Optional[str] = None,
    tool_status: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    """合并适配器能力与本地工具链状态，生成供 UI 展示的统一字典"""
    caps = {}
    if adapter is not None and hasattr(adapter, "get_capabilities"):
        try:
            caps = dict(adapter.get_capabilities() or {})
        except Exception as exc:
            caps = {
                "device_name": getattr(adapter, "device_name", "未知设备"),
                "firmware_info": getattr(adapter, "firmware_info", "未知固件"),
                "is_bidirectional": bool(getattr(adapter, "is_bidirectional", False)),
                "adapter_type": adapter.__class__.__name__,
                "features": [],
                "notes": [f"能力汇总失败: {exc}"],
            }

    resolved_bin_dir = bin_dir or default_nfc_bin_dir()
    tools = tool_status if tool_status is not None else check_external_tools(resolved_bin_dir)
    _annotate_external_features(caps, tools)

    caps["connection"] = connection
    caps["port"] = port
    caps["baudrate"] = baudrate
    caps["bin_dir"] = resolved_bin_dir
    caps["tools"] = dict(tools)
    caps.setdefault("features", [])
    caps.setdefault("notes", [])
    return caps
