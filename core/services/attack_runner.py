# -*- coding: utf-8 -*-
"""
PyMifareTool - 外部安全攻击与算法工具链执行引擎 (Attack Services Layer)
抽象攻击引擎接口，封装 mfoc, mfcuk, hardnested, mfdetect 外部工具
为未来挂载原生 Python 算法插件或 Proxmark3 联动预留抽象插槽
"""

import os
import re
from typing import Optional, List, Dict
from PyQt6.QtCore import QObject, pyqtSignal, QProcess


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

    def set_bin_dir(self, bin_dir: str):
        """设置外部工具集所在路径"""
        self.bin_dir = bin_dir

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
        return {
            "mfoc": self.is_tool_available("mfoc"),
            "mfcuk": self.is_tool_available("mfcuk"),
            "crypto1_bs": self.is_tool_available("crypto1_bs") or self.is_tool_available("hardnested"),
            "mfdetect": self.is_tool_available("mfdetect"),
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
        exe = self._resolve_exe("crypto1_bs") or self._resolve_exe("hardnested")
        if not exe:
            self.sig_finished.emit(False, f"未在 {self.bin_dir} 中找到 crypto1_bs.exe 或 hardnested.exe，请确认工具链安装。")
            return

        # 标准 hardnested 参数: <known_key> <known_block> <target_block> <output>
        known_block = known_sector * 4
        target_block = target_sector * 4
        args = [known_key, str(known_block), str(target_block), "-o", output_dump]
        self._start_process(exe, args, f"Hardnested 强加密破解 (已知扇区 {known_sector} -> 目标扇区 {target_sector})")

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
        self.process.start(exe, args)

    def _on_stdout(self):
        if not self.process:
            return
        data = self.process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        for line in data.splitlines():
            line_str = line.strip()
            if line_str:
                self.sig_output.emit(line_str)
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
                m = re.search(r"Sector\s*(\d+).*?Key\s*([AB])[:\s]+([0-9a-fA-F]{12})", line_str, re.IGNORECASE)
                if m:
                    sec = int(m.group(1))
                    k_type = m.group(2).upper()
                    k_hex = m.group(3).upper()
                    self.sig_key_found.emit(sec, k_type, k_hex)

    def _on_stderr(self):
        if not self.process:
            return
        data = self.process.readAllStandardError().data().decode("utf-8", errors="replace")
        for line in data.splitlines():
            line_str = line.strip()
            if line_str:
                self.sig_output.emit(f"[ERR] {line_str}")

    def _on_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus, desc: str):
        success = (exit_code == 0)
        msg = f"任务 [{desc}] 运行完毕 (退出代码: {exit_code})" if success else f"任务 [{desc}] 异常终止 (代码: {exit_code})"
        self.sig_output.emit("\n" + "="*50 + f"\n{msg}\n")
        self.sig_finished.emit(success, msg)
