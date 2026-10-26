# -*- coding: utf-8 -*-
"""
PyMifareTool - libnfc 外部工具链驱动适配器
基于 nfc-bin 系列 CLI 工具驱动 PN532 与 ACR122U 硬件
"""

import os
import subprocess
from typing import Optional, Dict, Any, Tuple
from core.adapters.base_adapter import BaseReaderAdapter
from core.models.card_converter import CardConverter
from core.transport.base import TransportLike


class LibnfcCliAdapter(BaseReaderAdapter):
    """
    通过调用 nfc-bin 下的 libnfc 二进制程序实现读写卡、破解与魔术卡操作
    """

    def __init__(self, bin_dir: Optional[str] = None):
        super().__init__()
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.bin_dir = os.path.abspath(bin_dir) if bin_dir else os.path.join(project_root, "tools", "m1t", "nfc-bin")
        self.device_name = "libnfc CLI (PN532 / ACR122U)"
        self.is_bidirectional = True
        self.default_baudrate = 115200
        self.firmware_info = "libnfc 命令行工具链"

    @property
    def adapter_name(self) -> str:
        return "libnfc 硬件驱动 (支持 PN532 / ACR122U)"

    def _find_binary(self, base_name: str) -> Optional[str]:
        for name in (f"{base_name}.exe", base_name):
            path = os.path.join(self.bin_dir, name)
            if os.path.exists(path):
                return path
        return None

    def is_available(self) -> bool:
        """检查 nfc-bin 工具链是否存在"""
        return os.path.isdir(self.bin_dir)

    def is_connected(self) -> bool:
        if not self.is_available():
            return False
        scan_bin = self._find_binary("nfc-scan-device")
        if not scan_bin:
            return False
        try:
            res = subprocess.run([scan_bin], capture_output=True, text=True, timeout=2.0)
            output = f"{res.stdout}\n{res.stderr}".lower()
            return "nfc device" in output or "found" in output
        except Exception:
            return False

    def supports_read_write(self) -> bool:
        return True

    def supports_magic_cards(self) -> bool:
        return True

    def supports_attacks(self) -> bool:
        return True

    def init_device(self, ser: Optional[TransportLike] = None) -> bool:
        """CLI 后端不依赖已打开的串口句柄，只校验工具链与设备可用性。"""
        return self.is_available() and self.is_connected()

    def parse_incoming(self, rx_buffer: bytearray) -> Tuple[Optional[Dict[str, Any]], bytes]:
        """CLI 后端不维护串口接收缓冲区。"""
        return None, bytes(rx_buffer)

    def scan_card(self, timeout: float = 3.0) -> Optional[Dict[str, Any]]:
        list_bin = self._find_binary("nfc-list")
        if not list_bin:
            return None
        try:
            res = subprocess.run([list_bin], capture_output=True, text=True, timeout=timeout)
            output = res.stdout
            for line in output.splitlines():
                if "UID" in line or "NFCID1" in line:
                    tokens = [
                        tok for tok in line.replace(":", " ").split()
                        if len(tok) == 2 and all(c in "0123456789abcdefABCDEF" for c in tok)
                    ]
                    if len(tokens) >= 4:
                        uid_bytes = bytes.fromhex("".join(tokens[:4]))
                        return {"uid_bytes": uid_bytes, "raw_output": output}
        except Exception:
            pass
        return None

    def poll_card(self, ser: Optional[TransportLike] = None, timeout: float = 0.5) -> Optional[Dict[str, Any]]:
        card = self.scan_card(timeout=max(1.0, timeout))
        if not card:
            return None
        uid_bytes = card["uid_bytes"]
        self.last_detected_uid = uid_bytes
        return {
            "uid_bytes": uid_bytes,
            "conversions": CardConverter.convert_uid(uid_bytes),
            "device_model": self.device_name,
            "raw": b"",
        }

    def authenticate(self, ser: Optional[TransportLike], block: int, key_type: str,
                     key: bytes, uid: bytes = b"", timeout: float = 0.35) -> bool:
        """CLI 后端不支持单块认证；整卡操作请使用 dump_card/write_card。"""
        return False

    def read_block(self, ser: Optional[TransportLike], block: int, timeout: float = 0.35) -> Optional[bytes]:
        return None

    def write_block(self, ser: Optional[TransportLike], block: int, data: bytes, timeout: float = 0.35) -> bool:
        return False

    def dump_card(self, output_file: str, key_file: Optional[str] = None) -> bool:
        """调用 nfc-mfclassic 读取整张 M1 卡"""
        bin_path = self._find_binary("nfc-mfclassic")
        if not bin_path:
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
        bin_path = self._find_binary("nfc-mfclassic")
        if not bin_path:
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
        """调用 nfc-mfsetuid 修改 Gen1a 魔术卡 UID"""
        bin_path = self._find_binary("nfc-mfsetuid")
        if not bin_path:
            return False
        uid_hex = new_uid.hex().upper()
        try:
            res = subprocess.run([bin_path, uid_hex], capture_output=True, text=True, timeout=5.0)
            return res.returncode == 0
        except Exception:
            return False

    def lock_ufuid(self) -> bool:
        """调用 nfc-mfsetuid -q -l 锁死 UFUID"""
        bin_path = self._find_binary("nfc-mfsetuid")
        if not bin_path:
            return False
        try:
            res = subprocess.run([bin_path, "-q", "-l"], capture_output=True, text=True, timeout=5.0)
            return res.returncode == 0
        except Exception:
            return False

    def get_capabilities(self) -> Dict[str, Any]:
        available = self.is_available()
        has_list = self._find_binary("nfc-list") is not None
        has_mfclassic = self._find_binary("nfc-mfclassic") is not None
        has_mfoc = self._find_binary("mfoc") is not None or self._find_binary("mfoc2") is not None
        has_mfcuk = self._find_binary("mfcuk") is not None or self._find_binary("mfcuk2") is not None
        has_hardnested = self._find_binary("libnfc_hardnested") is not None
        features = [
            {"name": "nfc-list 寻卡 / UID 读取", "status": "external" if has_list else "unsupported", "detail": "通过 libnfc CLI 调用；需先断开 PyMifareTool 串口"},
            {"name": "nfc-mfclassic 整卡读写", "status": "external" if has_mfclassic else "unsupported", "detail": "读写整卡 Dump，不支持单块交互"},
            {"name": "mfoc nested 攻击", "status": "experimental" if has_mfoc else "unsupported", "detail": "需要可用的 libnfc 驱动与 PN532/ACR122U 设备"},
            {"name": "mfcuk darkside 攻击", "status": "experimental" if has_mfcuk else "unsupported", "detail": "对部分卡片有效，耗时与卡片随机数强度相关"},
            {"name": "libnfc_hardnested", "status": "experimental" if has_hardnested else "unsupported", "detail": "需已知密钥；PCR532 需替换 libnfc(532).dll，兼容性需真机实测"},
        ]
        payload = self._capability_payload(features)
        payload["bin_dir"] = self.bin_dir
        payload["available"] = available
        payload["notes"] = [
            "libnfc CLI 后端不持有串口句柄，运行外部工具前必须先在 PyMifareTool 中断开同一 COM 口。",
            "PCR532 使用 libnfc(532).dll；ACR122U 使用 libnfc(ACR122Uslow).dll。",
        ]
        return payload
