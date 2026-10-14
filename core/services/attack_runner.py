# -*- coding: utf-8 -*-
"""
PyMifareTool - 外部安全攻击与算法工具链执行引擎 (Attack Services Layer)
抽象攻击引擎接口，封装 mfoc, mfcuk, hardnested, mfdetect 外部工具
为未来挂载原生 Python 算法插件或 Proxmark3 联动预留抽象插槽
"""

import os
from typing import Optional, List
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
    """外部 CLI 二进制攻击工具链进程包装器"""

    sig_output = pyqtSignal(str)          # 单行标准输出日志
    sig_progress = pyqtSignal(int, str)   # 进度百分比与描述
    sig_finished = pyqtSignal(bool, str)  # 成功标志与结束信息

    def __init__(self, bin_dir: str = "nfc-bin", parent=None):
        super().__init__(parent)
        self.bin_dir = bin_dir
        self.process: Optional[QProcess] = None

    def is_available(self) -> bool:
        return os.path.exists(self.bin_dir)

    def is_tool_available(self, exe_name: str) -> bool:
        return os.path.exists(os.path.join(self.bin_dir, exe_name))

    def start_attack(self, attack_type: str = "mfoc", **kwargs) -> bool:
        if attack_type == "mfoc":
            self.run_mfoc(kwargs.get("output_dump", "dump.mfd"), kwargs.get("dict_file"), kwargs.get("known_keys"))
            return True
        elif attack_type == "mfcuk":
            self.run_mfcuk()
            return True
        elif attack_type == "mfdetect":
            self.run_mfdetect()
            return True
        return False

    def cancel(self):
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            self.process.kill()

    def run_mfoc(self, output_dump: str, dict_file: Optional[str] = None, known_keys: Optional[List[str]] = None):
        """执行 MFOC Nested 攻击"""
        exe = os.path.join(self.bin_dir, "mfoc.exe")
        if not os.path.exists(exe):
            self.sig_finished.emit(False, f"未在 {self.bin_dir} 中找到 mfoc.exe，请确认工具链安装。")
            return

        args = ["-O", output_dump]
        if dict_file and os.path.exists(dict_file):
            args.extend(["-f", dict_file])
        if known_keys:
            for k in known_keys:
                args.extend(["-k", k])

        self._start_process(exe, args, "MFOC Nested 密码恢复攻击")

    def run_mfcuk(self):
        """执行 MFCUK Darkside 全加密卡片爆破"""
        exe = os.path.join(self.bin_dir, "mfcuk.exe")
        if not os.path.exists(exe):
            self.sig_finished.emit(False, f"未在 {self.bin_dir} 中找到 mfcuk.exe，请确认工具链安装。")
            return

        args = ["-v", "3", "-C", "-R", "-1", "-s", "250", "-S", "250"]
        self._start_process(exe, args, "MFCUK Darkside 全加密卡片爆破")

    def run_mfdetect(self):
        """执行 mfdetect 加密探测"""
        exe = os.path.join(self.bin_dir, "mfdetect.exe")
        if not os.path.exists(exe):
            self.sig_finished.emit(False, f"未在 {self.bin_dir} 中找到 mfdetect.exe，请确认工具链安装。")
            return

        self._start_process(exe, [], "卡片加密情况探测")

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
                if "%" in line_str:
                    for part in line_str.split():
                        if part.endswith("%"):
                            try:
                                pct = int(part.replace("%", ""))
                                self.sig_progress.emit(pct, line_str)
                            except Exception:
                                pass

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
