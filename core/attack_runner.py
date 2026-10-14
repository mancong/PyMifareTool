# -*- coding: utf-8 -*-
"""
PyMifareTool - 外部攻击工具链异步执行器 (AttackRunner)
对标 MifareOneTool:
- mfoc.exe (Nested 攻击，支持字典模式 -f 与已知密钥 -k)
- mfcuk.exe (Darkside 全加密爆破)
- cropto1_bs.exe / collect.exe (HardNested 采集与计算)
- mfdetect.exe (卡片加密探测)
"""

import os
from typing import Optional, List
from PyQt6.QtCore import QObject, pyqtSignal, QProcess


class AttackRunner(QObject):
    sig_output = pyqtSignal(str)          # 单行标准输出日志
    sig_progress = pyqtSignal(int, str)   # 进度百分比与描述
    sig_finished = pyqtSignal(bool, str)  # 成功标志与结束信息

    def __init__(self, bin_dir: str = "nfc-bin", parent=None):
        super().__init__(parent)
        self.bin_dir = bin_dir
        self.process: Optional[QProcess] = None

    def is_tool_available(self, exe_name: str) -> bool:
        return os.path.exists(os.path.join(self.bin_dir, exe_name))

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

        # 对标上游参数: mfcuk -v 3 -C -R -1 -s 250 -S 250
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
                # 简单解析百分比
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
            if line.strip():
                self.sig_output.emit(f"[ERR] {line.strip()}")

    def _on_process_finished(self, exit_code: int, exit_status, desc: str):
        success = (exit_code == 0)
        status_msg = f"{desc} 执行完毕 (退出码: {exit_code})" if success else f"{desc} 执行失败 (退出码: {exit_code})"
        self.sig_finished.emit(success, status_msg)

    def stop(self):
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            self.process.kill()
            self.sig_output.emit("🛑 用户已强制停止当前外部任务。")
