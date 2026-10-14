# -*- coding: utf-8 -*-
"""
PyMifareTool - 密钥字典管理服务 (KeyManager Service)
支持 MCT (ikarus23/MifareClassicTool) 密钥生态 (std.keys, hotel-std.keys, extended-std.keys)
以及自定义 *.keys / *.dic / *.txt 密钥文件载入、多选过滤、去重与并发批次分发
"""

import os
import re
from typing import List, Dict, Any, Optional, Set

KEYS_DIR_NAME = "keys"

# MCT 核心标准字典描述映射
KNOWN_KEY_FILES_INFO = {
    "std.keys": {
        "title": "MCT 官方标准密钥 (std.keys)",
        "desc": "出厂默认空卡密钥 (FFFFFFFFFFFF)、MAD 目录密钥 (A0A1A2A3A4A5)、NFC Forum 密钥 (D3F7D3F7D3F7)",
        "default": True,
        "priority": 10,
    },
    "hotel-std.keys": {
        "title": "MCT 酒店门禁密钥 (hotel-std.keys)",
        "desc": "常见主流酒店客房门锁、梯控与公共区域 Mifare 卡高频默认弱口令集",
        "default": True,
        "priority": 20,
    },
    "extended-std.keys": {
        "title": "MCT 扩展大字典 (extended-std.keys)",
        "desc": "汇聚开源社区 (mfoc/crapto1/pastebin/国内外门禁梯控) 超过 1,400+ 条高命中率经典弱密钥",
        "default": False,
        "priority": 30,
    },
}


class KeyManager:
    """M1 密钥字典加载、去重与批次组织管理中心"""

    HEX_KEY_PATTERN = re.compile(r"^[0-9A-Fa-f]{12}$")

    @classmethod
    def get_keys_dir(cls) -> str:
        """自适应向上查找项目根目录下的 keys 存放路径"""
        curr = os.path.abspath(os.path.dirname(__file__))
        for _ in range(4):
            candidate = os.path.join(curr, KEYS_DIR_NAME)
            if os.path.exists(candidate):
                return candidate
            parent = os.path.dirname(curr)
            if parent == curr:
                break
            curr = parent

        # 默认回退
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        keys_dir = os.path.join(base_dir, KEYS_DIR_NAME)
        os.makedirs(keys_dir, exist_ok=True)
        return keys_dir

    @classmethod
    def list_available_files(cls) -> List[Dict[str, Any]]:
        """列出当前 keys 目录下的所有可用密钥文件元数据"""
        keys_dir = cls.get_keys_dir()
        result = []

        if not os.path.exists(keys_dir):
            return result

        for fname in os.listdir(keys_dir):
            if fname.lower().endswith((".keys", ".dic", ".txt")):
                full_path = os.path.join(keys_dir, fname)
                keys = cls.parse_key_file(full_path)
                meta = KNOWN_KEY_FILES_INFO.get(fname, {
                    "title": f"自定义字典: {fname}",
                    "desc": f"用户载入字典文件 ({fname})",
                    "default": False,
                    "priority": 50,
                })

                result.append({
                    "filename": fname,
                    "filepath": full_path,
                    "title": meta["title"],
                    "desc": meta["desc"],
                    "is_default": meta.get("default", False),
                    "priority": meta.get("priority", 50),
                    "key_count": len(keys),
                    "keys": keys,
                })

        result.sort(key=lambda x: (x["priority"], x["filename"]))
        return result

    @classmethod
    def parse_key_file(cls, filepath: str) -> List[str]:
        """从单文件中读取、提取有效 12 字符十六进制密钥"""
        if not os.path.exists(filepath):
            return []

        keys = []
        seen = set()

        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or line.startswith("//"):
                        continue
                    parts = line.split("#")[0].split("//")[0].strip()
                    parts = parts.replace(" ", "")
                    if cls.HEX_KEY_PATTERN.match(parts):
                        k_upper = parts.upper()
                        if k_upper not in seen:
                            seen.add(k_upper)
                            keys.append(k_upper)
        except Exception:
            pass

        return keys

    @classmethod
    def load_combined_keys(
        cls,
        selected_files: Optional[List[str]] = None,
        include_defaults_fallback: bool = True
    ) -> List[str]:
        """加载并合并指定的文件列表，去重并保持高命中率优先级顺序"""
        keys_dir = cls.get_keys_dir()
        combined_keys: List[str] = []
        seen: Set[str] = set()

        if not selected_files:
            avail = cls.list_available_files()
            selected_paths = [item["filepath"] for item in avail if item["is_default"]]
            if not selected_paths and avail:
                selected_paths = [avail[0]["filepath"]]
        else:
            selected_paths = []
            for item in selected_files:
                if os.path.isabs(item) and os.path.exists(item):
                    selected_paths.append(item)
                else:
                    target = os.path.join(keys_dir, item)
                    if os.path.exists(target):
                        selected_paths.append(target)

        for path in selected_paths:
            file_keys = cls.parse_key_file(path)
            for k in file_keys:
                if k not in seen:
                    seen.add(k)
                    combined_keys.append(k)

        if not combined_keys and include_defaults_fallback:
            fallback = ["FFFFFFFFFFFF", "A0A1A2A3A4A5", "D3F7D3F7D3F7", "000000000000"]
            for k in fallback:
                if k not in seen:
                    seen.add(k)
                    combined_keys.append(k)

        return combined_keys
