# -*- coding: utf-8 -*-
"""
PyMifareTool - 外部安全攻击与算法工具链执行引擎 (Attack Services Layer)
抽象攻击引擎接口，封装 mfoc, mfcuk, hardnested, mfdetect 外部工具
为未来挂载原生 Python 算法插件或 Proxmark3 联动预留抽象插槽
"""

import hashlib
import locale
import os
import re
from typing import Optional, List, Dict
from PyQt6.QtCore import QObject, pyqtSignal, QProcess, QProcessEnvironment


class BaseAttackEngine:
    """攻击引擎抽象接口规范 (未来算法插件扩展插槽)"""

    def is_available(self) -> bool:
        """检查引擎或算法依赖是否就绪"""
        raise NotImplementedError

    def start_attack(self, **kwargs) -> bool:
        """启动攻击任务"""
        raise NotImplementedError

    def cancel(self) -> None:
        """取消攻击任务"""
        raise NotImplementedError


class AttackRunner(QObject, BaseAttackEngine):
    """外部 CLI 二进制攻击工具链进程包装器 (支持 MFOC, MFCUK, Hardnested, MFDetect)"""

    sig_output = pyqtSignal(str)          # 单行标准输出日志
    sig_progress = pyqtSignal(int, str)   # 进度百分比与描述
    sig_finished = pyqtSignal(bool, str)  # 成功标志与结束信息
    sig_key_found = pyqtSignal(int, str, str)  # 捕获恢复出的密码 (sector, key_type 'A'/'B', key_hex)

    def __init__(self, bin_dir: str = "nfc-bin", parent=None):
        super().__init__(parent)
        self.bin_dir = bin_dir
        self.process: Optional[QProcess] = None
        self.device_port = ""
        self.device_baudrate = 115200
        self.device_connection = "serial"
        self._stdout_buffer = b""
        self._stderr_buffer = b""

    def set_bin_dir(self, bin_dir: str):
        """设置外部工具集所在路径"""
        self.bin_dir = bin_dir

    def set_device_context(self, port: str = "", baudrate: int = 115200, connection: str = "serial"):
        """记录主程序当前串口上下文，供外部 libnfc 工具构造设备连接串"""
        self.device_port = (port or "").strip()
        try:
            self.device_baudrate = int(baudrate or 115200)
        except (TypeError, ValueError):
            self.device_baudrate = 115200
        self.device_connection = (connection or "serial").lower()

    def get_nfc_device_string(self) -> str:
        """返回 libnfc 的 NFC_DEVICE 连接串；BLE/无效端口返回空"""
        if self.device_connection != "serial" or not self.device_port:
            return ""
        if "BLE" in self.device_port.upper():
            return ""
        return f"pn532_uart:{self.device_port}:{self.device_baudrate}"

    @staticmethod
    def _file_sha256(path: str) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def check_libnfc_driver(self) -> Dict[str, object]:
        """检查当前 libnfc.dll 是否为 PN532 UART 版本，并给出提示"""
        default_dll = os.path.join(self.bin_dir, "libnfc.dll")
        pn532_dll = os.path.join(self.bin_dir, "libnfc(532).dll")
        info: Dict[str, object] = {
            "default_present": os.path.exists(default_dll),
            "pn532_present": os.path.exists(pn532_dll),
            "is_pn532": False,
            "hint": "",
        }
        if not info["default_present"]:
            info["hint"] = "未找到 libnfc.dll，外部工具无法加载 libnfc"
        elif not info["pn532_present"]:
            info["hint"] = "未找到 libnfc(532).dll，无法确认是否为 PN532 UART 驱动"
        else:
            try:
                is_pn532 = self._file_sha256(default_dll) == self._file_sha256(pn532_dll)
            except OSError:
                is_pn532 = False
            info["is_pn532"] = is_pn532
            if is_pn532:
                info["hint"] = "当前 libnfc.dll 已匹配 PN532 UART 版本"
            else:
                info["hint"] = (
                    "当前 libnfc.dll 与 libnfc(532).dll 不一致；若提示“未找到NFC设备”，"
                    "请备份 libnfc.dll 后，把 libnfc(532).dll 重命名为 libnfc.dll"
                )
        return info

    def is_available(self) -> bool:
        return os.path.exists(self.bin_dir)

    def is_tool_available(self, exe_name: str) -> bool:
        for candidate in [exe_name, f"{exe_name}.exe"]:
            p = os.path.join(self.bin_dir, candidate)
            if os.path.exists(p):
                return True
        return False

    def check_available_tools(self) -> Dict[str, bool]:
        """检查常见外部工具链就绪状态"""
        libnfc_hardnested = (
            self.is_tool_available("libnfc_hardnested")
            or self.is_tool_available("libnfc_hardnestedlc")
        )
        return {
            "mfoc": self.is_tool_available("mfoc") or self.is_tool_available("mfoc2"),
            "mfcuk": self.is_tool_available("mfcuk") or self.is_tool_available("mfcuk2"),
            "crypto1_bs": (
                self.is_tool_available("crypto1_bs")
                or self.is_tool_available("hardnested")
                or libnfc_hardnested
            ),
            "libnfc_hardnested": libnfc_hardnested,
            "mfdetect": self.is_tool_available("mfdetect"),
            "nfc_list": self.is_tool_available("nfc-list"),
            "libnfc_dll": (
                self.is_tool_available("libnfc.dll")
                or self.is_tool_available("libnfc(532).dll")
                or self.is_tool_available("libnfc(ACR122Uslow).dll")
            ),
            "libnfc_pn532_dll": self.is_tool_available("libnfc(532).dll"),
        }

    def start_attack(self, attack_type: str = "mfoc", **kwargs) -> bool:
        if attack_type == "mfoc":
            self.run_mfoc(kwargs.get("output_dump", "dump.mfd"), kwargs.get("dict_file"), kwargs.get("known_keys"))
            return True
        elif attack_type == "mfcuk":
            self.run_mfcuk(kwargs.get("output_dump", "dump.mfd"), kwargs.get("sector", 0), kwargs.get("key_type", "A"))
            return True
        elif attack_type == "hardnested":
            self.run_hardnested(
                kwargs.get("known_key", "FFFFFFFFFFFF"),
                kwargs.get("known_sector", 0),
                kwargs.get("target_sector", 1),
                kwargs.get("output_dump", "dump.mfd"),
            )
            return True
        elif attack_type == "mfdetect":
            self.run_mfdetect()
            return True
        return False

    def cancel(self):
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            self.process.kill()

    def run_mfoc(self, output_dump: str, dict_file: Optional[str] = None, known_keys: Optional[List[str]] = None):
        """执行 MFOC Nested 攻击 (从已知密码扇区推导未知扇区)"""
        output_dump = os.path.abspath(output_dump)
        exe = self._resolve_exe("mfoc")
        if not exe:
            self.sig_finished.emit(False, f"未在 {self.bin_dir} 中找到 mfoc.exe，请确认工具链安装。")
            return

        args = ["-O", output_dump]
        if dict_file and os.path.exists(dict_file):
            args.extend(["-f", dict_file])
        if known_keys:
            for k in known_keys:
                clean_k = k.strip()
                if clean_k:
                    args.extend(["-k", clean_k])

        self._start_process(exe, args, "MFOC Nested 密码推导攻击")

    def run_mfcuk(self, output_dump: str = "dump.mfd", sector: int = 0, key_type: str = "A"):
        """执行 MFCUK Darkside 全加密卡片盲破 (利用 PRNG 漏洞恢复第一把钥匙)"""
        output_dump = os.path.abspath(output_dump)
        exe = self._resolve_exe("mfcuk")
        if not exe:
            self.sig_finished.emit(False, f"未在 {self.bin_dir} 中找到 mfcuk.exe，请确认工具链安装。")
            return

        # -v 3 详细日志, -C 连贯性, -R 尝试, -s 250, -S 250
        # -s 扇区 -w 钥匙类型 (0=A, 1=B)
        w_type = "0" if key_type.upper() == "A" else "1"
        args = ["-v", "3", "-C", "-R", "-1", "-s", "250", "-S", "250", "-d", str(sector), "-w", w_type, "-O", output_dump]
        self._start_process(exe, args, f"MFCUK Darkside 盲破 (扇区 {sector} 密钥 {key_type})")

    def run_hardnested(self, known_key: str, known_sector: int = 0, target_sector: int = 1, output_dump: str = "dump.mfd"):
        """执行 Hardnested 攻击 (针对修复 PRNG 漏洞的硬防卡/强随机数卡)"""
        output_dump = os.path.abspath(output_dump)
        exe = (
            self._resolve_exe("libnfc_hardnested")
            or self._resolve_exe("libnfc_hardnestedlc")
            or self._resolve_exe("crypto1_bs")
            or self._resolve_exe("hardnested")
        )
        if not exe:
            self.sig_finished.emit(
                False,
                f"未在 {self.bin_dir} 中找到 libnfc_hardnested / crypto1_bs / hardnested，请确认工具链安装。",
            )
            return

        known_block = known_sector * 4
        target_block = target_sector * 4
        exe_name = os.path.basename(exe).lower()
        if exe_name.startswith("libnfc_hardnested"):
            # M1T 随附版本用法:
            # libnfc_hardnested <known_key> <known_block> <A|B> <target_block> <A|B>
            args = [known_key, str(known_block), "A", str(target_block), "A"]
            desc = (
                f"Hardnested libnfc 实验性破解 (扇区 {known_sector} 块 {known_block} -> "
                f"扇区 {target_sector} 块 {target_block})"
            )
        else:
            # 标准 crypto1_bs/hardnested 参数: <known_key> <known_block> <target_block> -o <output>
            args = [known_key, str(known_block), str(target_block), "-o", output_dump]
            desc = f"Hardnested 强加密破解 (已知扇区 {known_sector} -> 目标扇区 {target_sector})"
        self._start_process(exe, args, desc)

    def run_mfdetect(self):
        """执行 mfdetect 加密探测"""
        exe = self._resolve_exe("mfdetect")
        if not exe:
            self.sig_finished.emit(False, f"未在 {self.bin_dir} 中找到 mfdetect.exe，请确认工具链安装。")
            return

        self._start_process(exe, [], "卡片加密情况探测")

    def _resolve_exe(self, name: str) -> Optional[str]:
        for candidate in [f"{name}.exe", name]:
            p = os.path.join(self.bin_dir, candidate)
            if os.path.exists(p):
                return os.path.abspath(p)
        return None

    def _start_process(self, exe: str, args: List[str], desc: str):
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            self.sig_finished.emit(False, "已有外部任务在运行中。")
            return

        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(lambda code, status: self._on_process_finished(code, status, desc))

        self.sig_output.emit(f"🚀 开始执行: {desc}")
        self.sig_output.emit(f"命令: {exe} {' '.join(args)}\n" + "-"*50)
        nfc_device = self._apply_process_context(self.process)
        if nfc_device:
            self.sig_output.emit(f"设备环境: NFC_DEVICE={nfc_device}")
        else:
            self.sig_output.emit("设备环境: 未设置 NFC_DEVICE（BLE 或未选择串口，外部工具可能无法发现读卡器）")
        driver_hint = str(self.check_libnfc_driver().get("hint", ""))
        if driver_hint:
            self.sig_output.emit(f"驱动提示: {driver_hint}")
        self.process.start(exe, args)

    def _apply_process_context(self, process: QProcess) -> str:
        """设置外部工具工作目录与 NFC_DEVICE，返回实际使用的设备串"""
        process.setWorkingDirectory(os.path.abspath(self.bin_dir))
        env = QProcessEnvironment.systemEnvironment()
        nfc_device = self.get_nfc_device_string()
        if nfc_device:
            env.insert("NFC_DEVICE", nfc_device)
        process.setProcessEnvironment(env)
        return nfc_device

    @staticmethod
    def _decode_output(data: bytes) -> str:
        """将外部工具输出统一解码为 Unicode；兼容 UTF-8 与 Windows GBK 工具。"""
        if not data:
            return ""
        for encoding in ("utf-8-sig", "utf-8", "gbk", "cp936"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        try:
            preferred = locale.getpreferredencoding(False) or "utf-8"
            return data.decode(preferred)
        except (LookupError, UnicodeDecodeError):
            return data.decode("utf-8", errors="replace")

    @staticmethod
    def _split_output_buffer(buffer: bytes):
        """按 CR/LF/CRLF 切分，保留最后一段未完成行。"""
        parts = re.split(rb"\r\n|\r|\n", buffer)
        return parts[:-1], parts[-1]

    def _consume_output(self, data: bytes, channel: str):
        attr = "_stdout_buffer" if channel == "stdout" else "_stderr_buffer"
        buffer = getattr(self, attr) + data
        lines, remainder = self._split_output_buffer(buffer)
        setattr(self, attr, remainder)
        for raw_line in lines:
            self._emit_output_line(raw_line, channel)

    def _flush_output(self, channel: str):
        attr = "_stdout_buffer" if channel == "stdout" else "_stderr_buffer"
        raw_line = getattr(self, attr)
        if raw_line:
            setattr(self, attr, b"")
            self._emit_output_line(raw_line, channel)

    def _emit_output_line(self, raw_line: bytes, channel: str):
        line_str = self._decode_output(raw_line).strip()
        if not line_str:
            return
        if channel == "stderr":
            self.sig_output.emit(f"[ERR] {line_str}")
            return
        self.sig_output.emit(line_str)
        self._parse_stdout_line(line_str)

    def _parse_stdout_line(self, line_str: str):
        # 尝试解析进度百分比
        if "%" in line_str:
            for part in line_str.split():
                if part.endswith("%"):
                    try:
                        pct = int(part.replace("%", ""))
                        self.sig_progress.emit(pct, line_str)
                    except Exception:
                        pass

        # 尝试匹配已知推导出的密码行
        # 例如: Sector 00 - Key A: a0a1a2a3a4a5 或 [Sector 00, Key A: FFFFFFFFFFFF]
        # 或 recovered key: FFFFFFFFFFFF
        m = re.search(r"Sector\s*(\d+).*?Key\s*([AB])[:\s=]+([0-9a-fA-F]{12})", line_str, re.IGNORECASE)
        if not m:
            m = re.search(r"Sector\s*(\d+)\s*\)\s*Key\s*([AB])\s*=\s*([0-9a-fA-F]{12})", line_str, re.IGNORECASE)
        if m:
            sec = int(m.group(1))
            k_type = m.group(2).upper()
            k_hex = m.group(3).upper()
            self.sig_key_found.emit(sec, k_type, k_hex)

    def _on_stdout(self):
        if not self.process:
            return
        self._consume_output(self.process.readAllStandardOutput().data(), "stdout")

    def _on_stderr(self):
        if not self.process:
            return
        self._consume_output(self.process.readAllStandardError().data(), "stderr")

    def _on_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus, desc: str):
        if self.process:
            self._consume_output(self.process.readAllStandardOutput().data(), "stdout")
            self._consume_output(self.process.readAllStandardError().data(), "stderr")
        self._flush_output("stdout")
        self._flush_output("stderr")
        success = (exit_code == 0)
        msg = f"任务 [{desc}] 运行完毕 (退出代码: {exit_code})" if success else f"任务 [{desc}] 异常终止 (代码: {exit_code})"
        self.sig_output.emit("\n" + "="*50 + f"\n{msg}\n")
        self.sig_finished.emit(success, msg)
