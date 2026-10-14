# -*- coding: utf-8 -*-
"""
PyMifareTool - libnfc 工具链适配器 (对标 MifareOneTool 核心底层架构)
基于 nfc-bin 系列 CLI 工具驱动 PN532 与 ACR122U 硬件
"""

import os
import shutil
import subprocess
from typing import Optional, Dict, Any, List
from core.adapters.base_adapter import BaseReaderAdapter


class LibnfcCliAdapter(BaseReaderAdapter):
    """
    通过调用 nfc-bin 下的 libnfc 二进制程序实现完整的读写卡、破解与魔术卡操作
    对标 MifareOneTool 的 Form1.cs 调用方式
    """

    def __init__(self, bin_dir: str = "nfc-bin"):
        self.bin_dir = bin_dir

    @property
    def adapter_name(self) -> str:
        return "libnfc 硬件驱动 (支持 PN532 / ACR122U)"

    def is_available(self) -> bool:
        """检查 nfc-bin 工具链是否存在"""
        return os.path.exists(self.bin_dir) and os.path.isdir(self.bin_dir)

    def is_connected(self) -> bool:
        if not self.is_available():
            return False
        # 执行 nfc-scan-device 探测是否有连接的硬件
        scan_bin = os.path.join(self.bin_dir, "nfc-scan-device.exe")
        if not os.path.exists(scan_bin):
            return False
        try:
            res = subprocess.run([scan_bin], capture_output=True, text=True, timeout=2.0)
            return "NFC device" in res.stdout or "found" in res.stdout
        except Exception:
            return False

    def supports_read_write(self) -> bool:
        return True

    def supports_magic_cards(self) -> bool:
        return True

    def supports_attacks(self) -> bool:
        return True

    def scan_card(self) -> Optional[Dict[str, Any]]:
        list_bin = os.path.join(self.bin_dir, "nfc-list.exe")
        if not os.path.exists(list_bin):
            return None
        try:
            res = subprocess.run([list_bin], capture_output=True, text=True, timeout=3.0)
            output = res.stdout
            # 解析 UID (NFCID1)
            for line in output.splitlines():
                if "UID" in line or "NFCID1" in line:
                    tokens = [tok for tok in line.replace(":", " ").split() if len(tok) == 2 and all(c in "0123456789abcdefABCDEF" for c in tok)]
                    if len(tokens) >= 4:
                        uid_bytes = bytes.fromhex("".join(tokens[:4]))
                        return {"uid_bytes": uid_bytes, "raw_output": output}
        except Exception:
            pass
        return None

    def authenticate(self, block: int, key_type: str, key: bytes) -> bool:
        # libnfc 典型为批量读写或通过 nfc-mfclassic 进行
        return True

    def read_block(self, block: int) -> Optional[bytes]:
        return None

    def write_block(self, block: int, data: bytes) -> bool:
        return False

    def dump_card(self, output_file: str, key_file: Optional[str] = None) -> bool:
        """调用 nfc-mfclassic 读取整张 M1 卡"""
        bin_path = os.path.join(self.bin_dir, "nfc-mfclassic.exe")
        if not os.path.exists(bin_path):
            return False
        cmd = [bin_path, "r", "A", "u", output_file]
        if key_file:
            cmd.extend([key_file, "f"])
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30.0)
            return res.returncode == 0 and os.path.exists(output_file)
        except Exception:
            return False

    def write_card(self, dump_file: str, key_file: Optional[str] = None) -> bool:
        """调用 nfc-mfclassic 写入整张 M1 卡"""
        bin_path = os.path.join(self.bin_dir, "nfc-mfclassic.exe")
        if not os.path.exists(bin_path):
            return False
        cmd = [bin_path, "w", "A", "u", dump_file]
        if key_file:
            cmd.extend([key_file, "f"])
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30.0)
            return res.returncode == 0
        except Exception:
            return False

    def set_magic_uid(self, new_uid: bytes) -> bool:
        """调用 nfc-mfsetuid.exe 修改 Gen1a 魔术卡 UID"""
        bin_path = os.path.join(self.bin_dir, "nfc-mfsetuid.exe")
        if not os.path.exists(bin_path):
            return False
        uid_hex = new_uid.hex().upper()
        try:
            res = subprocess.run([bin_path, uid_hex], capture_output=True, text=True, timeout=5.0)
            return res.returncode == 0
        except Exception:
            return False

    def lock_ufuid(self) -> bool:
        """调用 nfc-mfsetuid.exe -q -l 锁死 UFUID"""
        bin_path = os.path.join(self.bin_dir, "nfc-mfsetuid.exe")
        if not os.path.exists(bin_path):
            return False
        try:
            res = subprocess.run([bin_path, "-q", "-l"], capture_output=True, text=True, timeout=5.0)
            return res.returncode == 0
        except Exception:
            return False
