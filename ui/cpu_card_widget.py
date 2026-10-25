# -*- coding: utf-8 -*-
"""
PyMifareTool - CPU 智能卡全功能交互中枢 (CpuCardWidget Pro)
支持：
1. 物理卡号 (UID) 与 ATS 硬件特征实时获取与呈现
2. 一键智能读取全国交通联合卡 (T-Union) / PBOC 金融卡 / 公交卡应用信息、卡号、余额与消费流水
3. 🗂️ 全卡文件系统深度全景遍历与字节级 Hex / ASCII 结构矩阵检查器 (类似 M1 卡全卡内容展示)
4. 交互式原生 APDU 指令收发控制台 (含常见指令预设、SW1/SW2 状态字智能解析、深度语义推导与报文历史)
5. 支持将卡内全量公开文件与流水结构导出为标准 JSON 格式文件
"""

import time
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QLineEdit, QPlainTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QGridLayout, QFrame, QSplitter, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QProgressBar, QFileDialog, QMessageBox
)
from core.protocols.iso7816 import APDUProtocol, AID_T_UNION, AID_PBOC_CASH


class CpuCardReadWorker(QThread):
    """后台异步执行 CPU 卡信息全量读取 (独占半双工射频通道，避免阻塞主 GUI)"""
    sig_finished = pyqtSignal(dict)
    sig_error = pyqtSignal(str)

    def __init__(self, serial_worker, timeout: float = 0.6):
        super().__init__()
        self.serial_worker = serial_worker
        self.timeout = timeout

    def run(self):
        worker = self.serial_worker
        try:
            worker.set_exclusive(True)
            try:
                res = worker.read_cpu_card_once(timeout=self.timeout)
            finally:
                worker.set_exclusive(False)
            self.sig_finished.emit(res)
        except Exception as e:
            self.sig_error.emit(str(e))


class CpuCardTreeScanWorker(QThread):
    """后台异步执行 CPU 智能卡全文件系统深度树状遍历扫描 (支持中途安全取消)"""
    sig_finished = pyqtSignal(dict)
    sig_progress = pyqtSignal(int, int, str)
    sig_error = pyqtSignal(str)

    def __init__(self, serial_worker, timeout: float = 0.35):
        super().__init__()
        self.serial_worker = serial_worker
        self.timeout = timeout
        self._is_aborted = False

    def abort(self):
        """外部请求中断深度扫描"""
        self._is_aborted = True

    def run(self):
        worker = self.serial_worker
        try:
            worker.set_exclusive(True)
            try:
                res = worker.scan_cpu_card_tree_once(
                    timeout=self.timeout,
                    progress_cb=lambda c, t, m: self.sig_progress.emit(c, t, m),
                    abort_check=lambda: self._is_aborted,
                )
            finally:
                worker.set_exclusive(False)
            self.sig_finished.emit(res)
        except Exception as e:
            self.sig_error.emit(str(e))


class ApduSendWorker(QThread):
    """后台异步执行单条原生 APDU 发送"""
    sig_result = pyqtSignal(dict, float)
    sig_error = pyqtSignal(str)

    def __init__(self, serial_worker, apdu_bytes: bytes, timeout: float = 0.6):
        super().__init__()
        self.serial_worker = serial_worker
        self.apdu_bytes = apdu_bytes
        self.timeout = timeout

    def run(self):
        worker = self.serial_worker
        start_t = time.time()
        try:
            worker.set_exclusive(True)
            try:
                res = worker.send_apdu_once(self.apdu_bytes, timeout=self.timeout)
            finally:
                worker.set_exclusive(False)
            elapsed_ms = (time.time() - start_t) * 1000.0
            self.sig_result.emit(res, elapsed_ms)
        except Exception as e:
            self.sig_error.emit(str(e))


class CpuCardWidget(QWidget):
    """CPU 智能卡全功能交互与调试面板"""

    # 经典常用 APDU 指令预设
    PRESET_APDUS = [
        ("00 84 00 00 08", "取 8 字节随机数 (Get Challenge)"),
        ("00 A4 04 00 0E 32 50 41 59 2E 53 59 53 2E 44 44 46 30 31", "选择 PPSE 目录 (2PAY.SYS.DDF01 动态寻址)"),
        ("00 A4 04 00 10 A0 00 00 06 32 01 01 05 53 5A 4B 57 00 00 05 31", "选择交通联合互通电子钱包应用 (MOT_T_EP)"),
        ("00 A4 04 00 08 A0 00 00 03 33 01 01 01", "选择全国交通联合标准应用 (T-Union)"),
        ("00 A4 04 00 09 A0 00 00 00 03 86 98 07 01", "选择 PBOC 金融电子现金应用"),
        ("00 A4 00 00 02 3F 00", "选择主文件目录 (MF - 3F00)"),
        ("00 B0 95 00 1E", "读取 0015 公共信息文件 (30 字节 - 卡号/有效期)"),
        ("80 5C 00 02 04", "查询电子现金/电子钱包卡内余额 (Get Balance)"),
        ("00 B2 01 C4 00", "读取交易记录第 1 条 (交通部标准 SFI=0x18)"),
        ("00 B2 01 5C 00", "读取交易记录第 1 条 (PBOC标准 P2=5C)"),
        ("00 B2 02 C4 00", "读取交易记录第 2 条 (交通部标准 SFI=0x18)"),
        ("00 B0 85 00 00", "读取 0005 持卡人基础信息文件"),
    ]

    def __init__(self, serial_worker=None, parent=None):
        super().__init__(parent)
        self.serial_worker = serial_worker
        self._current_card_info: Dict[str, Any] = {}
        self._tree_data: Dict[str, Any] = {}
        self._read_worker: Optional[CpuCardReadWorker] = None
        self._tree_worker: Optional[CpuCardTreeScanWorker] = None
        self._apdu_worker: Optional[ApduSendWorker] = None

        self._init_ui()

    def set_serial_worker(self, worker):
        self.serial_worker = worker

    def update_card_badge(self, card_info: Dict[str, Any]):
        """当读写器感应到新卡时同步基本硬件特征与卡号"""
        self._current_card_info = card_info or {}
        uid = card_info.get("uid_bytes", b"")
        if uid:
            uid_hex = " ".join(f"{b:02X}" for b in uid)
            self.lbl_uid_val.setText(uid_hex)
        else:
            self.lbl_uid_val.setText("-")

        sak = card_info.get("sak", None)
        sak_str = f"0x{sak:02X}" if sak is not None else "-"
        self.lbl_sak_val.setText(sak_str)

        card_type = card_info.get("card_type", "未知卡片")
        self.lbl_type_val.setText(card_type)

        ats_hex = card_info.get("ats_hex", "")
        self.lbl_ats_val.setText(ats_hex if ats_hex else "无 (未返回 ATS)")

        if card_info.get("is_cpu_card"):
            self.lbl_status_hint.setText("🟢 已感知到 ISO14443-4 CPU 卡，可执行公开信息读取、全卡文件遍历或原生 APDU 交互")
            self.lbl_status_hint.setStyleSheet("color: #4ADE80; font-size: 11px;")
            self.btn_auto_read.setEnabled(True)
            self.btn_scan_tree.setEnabled(True)
            self.btn_send_apdu.setEnabled(True)
        else:
            self.lbl_status_hint.setText("ℹ️ 当前卡片可能为普通 M1 卡；若为双界面 CPU 卡可继续尝试遍历或 APDU 交互")
            self.lbl_status_hint.setStyleSheet("color: #94A3B8; font-size: 11px;")

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # ═════════════════════════════════════════════════════════
        # 1. 顶部硬件感应与卡片特征看板
        # ═════════════════════════════════════════════════════════
        grp_hw = QGroupBox("💳 CPU 卡物理感知与基本特征")
        lay_hw = QGridLayout(grp_hw)
        lay_hw.setContentsMargins(10, 8, 10, 8)
        lay_hw.setSpacing(6)

        lay_hw.addWidget(QLabel("物理 UID:"), 0, 0)
        self.lbl_uid_val = QLabel("-")
        self.lbl_uid_val.setStyleSheet("color: #38BDF8; font-weight: bold; font-family: monospace;")
        lay_hw.addWidget(self.lbl_uid_val, 0, 1)

        lay_hw.addWidget(QLabel("协议类型:"), 0, 2)
        self.lbl_type_val = QLabel("等待贴卡...")
        self.lbl_type_val.setStyleSheet("color: #F8FAFC;")
        lay_hw.addWidget(self.lbl_type_val, 0, 3)

        lay_hw.addWidget(QLabel("SEL_RES (SAK):"), 1, 0)
        self.lbl_sak_val = QLabel("-")
        self.lbl_sak_val.setStyleSheet("color: #F8FAFC; font-family: monospace;")
        lay_hw.addWidget(self.lbl_sak_val, 1, 1)

        lay_hw.addWidget(QLabel("ATS 历史字节:"), 1, 2)
        self.lbl_ats_val = QLabel("-")
        self.lbl_ats_val.setStyleSheet("color: #CBD5E1; font-family: monospace;")
        lay_hw.addWidget(self.lbl_ats_val, 1, 3)

        self.lbl_status_hint = QLabel("请将 CPU 卡 / 交通卡 / 金融卡放置于读写器天线上")
        self.lbl_status_hint.setStyleSheet("color: #94A3B8; font-size: 11px;")
        lay_hw.addWidget(self.lbl_status_hint, 2, 0, 1, 4)

        main_layout.addWidget(grp_hw)

        # ═════════════════════════════════════════════════════════
        # 2. 功能选项卡中枢 (公开信息 / 🗂️ 全卡文件全景 / 💻 原生 APDU)
        # ═════════════════════════════════════════════════════════
        self.sub_tabs = QTabWidget()
        self.sub_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #334155; border-radius: 6px; background-color: #0F172A; }
            QTabBar::tab { background-color: #1E293B; color: #94A3B8; padding: 6px 14px; font-weight: bold; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background-color: #0284C7; color: #FFFFFF; }
            QTabBar::tab:hover:!selected { background-color: #334155; color: #F8FAFC; }
        """)

        # ── 选项卡 1: 公开信息与流水看板 ──
        w_overview = self._build_overview_tab()
        self.sub_tabs.addTab(w_overview, "📋 公开信息与消费流水")

        # ── 选项卡 2: 全卡文件系统全景遍历与 Hex 检查器 ──
        w_tree = self._build_file_tree_tab()
        self.sub_tabs.addTab(w_tree, "🗂️ 全卡文件全景遍历 (File Tree & Hex)")

        # ── 选项卡 3: 原生 APDU 指令控制台 ──
        w_apdu = self._build_apdu_console_tab()
        self.sub_tabs.addTab(w_apdu, "💻 原生 APDU 交互控制台")

        main_layout.addWidget(self.sub_tabs, 1)

    # ═════════════════════════════════════════════════════════════
    # 子页面 1: 公开信息与流水
    # ═════════════════════════════════════════════════════════════
    def _build_overview_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # 顶部操作条
        bar_act = QHBoxLayout()
        self.btn_auto_read = QPushButton("🔍 一键读取卡片内容 (交通卡/金融卡/公共数据)")
        self.btn_auto_read.setStyleSheet("background-color: #0284C7; color: #FFFFFF; font-weight: bold; padding: 6px 14px;")
        self.btn_auto_read.clicked.connect(self._start_auto_read)
        bar_act.addWidget(self.btn_auto_read)
        bar_act.addStretch()
        lay.addLayout(bar_act)

        # 核心指标看板卡片 (应用名称、卡号、大字余额、有效期)
        card_box = QFrame()
        card_box.setStyleSheet("background-color: #1E293B; border: 1px solid #334155; border-radius: 6px; padding: 6px;")
        lay_cb = QGridLayout(card_box)
        lay_cb.setSpacing(8)

        lay_cb.addWidget(QLabel("应用名称:"), 0, 0)
        self.val_app_name = QLabel("-")
        self.val_app_name.setStyleSheet("color: #38BDF8; font-weight: bold;")
        lay_cb.addWidget(self.val_app_name, 0, 1)

        lay_cb.addWidget(QLabel("电子现金余额:"), 0, 2)
        self.val_balance = QLabel("--")
        self.val_balance.setStyleSheet("color: #4ADE80; font-size: 16px; font-weight: bold;")
        lay_cb.addWidget(self.val_balance, 0, 3)

        lay_cb.addWidget(QLabel("应用卡号:"), 1, 0)
        self.val_card_no = QLabel("-")
        self.val_card_no.setStyleSheet("color: #F8FAFC; font-family: monospace; font-weight: bold;")
        lay_cb.addWidget(self.val_card_no, 1, 1)

        lay_cb.addWidget(QLabel("发卡机构代码:"), 1, 2)
        self.val_issuer = QLabel("-")
        self.val_issuer.setStyleSheet("color: #CBD5E1; font-family: monospace;")
        lay_cb.addWidget(self.val_issuer, 1, 3)

        lay_cb.addWidget(QLabel("卡片有效期:"), 2, 0)
        self.val_validity = QLabel("-")
        self.val_validity.setStyleSheet("color: #CBD5E1;")
        lay_cb.addWidget(self.val_validity, 2, 1)

        lay.addWidget(card_box)

        # 交易流水表格
        lbl_trans = QLabel("📜 历史交易记录流水 (循环记录文件 0x18):")
        lbl_trans.setStyleSheet("font-size: 11px; color: #94A3B8; font-weight: bold;")
        lay.addWidget(lbl_trans)

        self.table_trans = QTableWidget(0, 5)
        self.table_trans.setHorizontalHeaderLabels(["序号", "交易时间", "业务类型", "交易金额", "终端机号"])
        self.table_trans.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_trans.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_trans.setStyleSheet("font-size: 11px;")
        lay.addWidget(self.table_trans, 1)

        return w

    # ═════════════════════════════════════════════════════════════
    # 子页面 2: 全卡文件全景遍历与 Hex 检查器 (新增核心特性)
    # ═════════════════════════════════════════════════════════════
    def _build_file_tree_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # 顶部操作工具条
        row_tool = QHBoxLayout()
        self.btn_scan_tree = QPushButton("🌲 深度扫描卡片文件系统 (SFI/FID 全目录)")
        self.btn_scan_tree.setStyleSheet("background-color: #059669; color: #FFFFFF; font-weight: bold; padding: 6px 14px;")
        self.btn_scan_tree.clicked.connect(self._start_tree_scan)
        row_tool.addWidget(self.btn_scan_tree)

        self.btn_export_tree = QPushButton("💾 导出卡片公开数据 (JSON)")
        self.btn_export_tree.setEnabled(False)
        self.btn_export_tree.setStyleSheet("font-size: 11px; padding: 6px 12px;")
        self.btn_export_tree.clicked.connect(self._export_tree_json)
        row_tool.addWidget(self.btn_export_tree)

        self.lbl_tree_stats = QLabel("已探测文件: 0 | 可读数据: 0 字节 | 流水记录: 0 条")
        self.lbl_tree_stats.setStyleSheet("color: #94A3B8; font-size: 11px; margin-left: 10px;")
        row_tool.addWidget(self.lbl_tree_stats)
        row_tool.addStretch()

        lay.addLayout(row_tool)

        # 扫描进度指示条 (默认隐藏)
        self.pbar_scan = QProgressBar()
        self.pbar_scan.setFixedHeight(14)
        self.pbar_scan.setTextVisible(True)
        self.pbar_scan.setVisible(False)
        self.pbar_scan.setStyleSheet("""
            QProgressBar { border: 1px solid #334155; border-radius: 4px; text-align: center; font-size: 10px; background-color: #1E293B; color: #FFFFFF; }
            QProgressBar::chunk { background-color: #10B981; }
        """)
        lay.addWidget(self.pbar_scan)

        # 主体左右分割器 (左: 目录树，右: 结构化 Hex / ASCII 矩阵与属性面板)
        splitter_tree = QSplitter(Qt.Orientation.Horizontal)

        # 左栏: 树状目录树
        self.tree_files = QTreeWidget()
        self.tree_files.setHeaderLabels(["卡内文件系统结构 (目录/文件/记录)", "大小"])
        self.tree_files.setColumnWidth(0, 260)
        self.tree_files.setStyleSheet("""
            QTreeWidget { background-color: #0B1120; border: 1px solid #334155; border-radius: 6px; color: #F8FAFC; font-size: 11px; }
            QTreeWidget::item { padding: 3px 0; }
            QTreeWidget::item:selected { background-color: #0284C7; color: #FFFFFF; }
            QHeaderView::section { background-color: #1E293B; color: #94A3B8; font-weight: bold; border: none; padding: 4px; }
        """)
        self.tree_files.itemClicked.connect(self._on_tree_item_clicked)
        splitter_tree.addWidget(self.tree_files)

        # 右栏: 文件 Hex 检查器与属性
        w_hex = QWidget()
        lay_hex = QVBoxLayout(w_hex)
        lay_hex.setContentsMargins(0, 0, 0, 0)
        lay_hex.setSpacing(6)

        # 文件属性看板
        f_meta_box = QFrame()
        f_meta_box.setStyleSheet("background-color: #1E293B; border: 1px solid #334155; border-radius: 6px; padding: 6px;")
        lay_meta = QGridLayout(f_meta_box)
        lay_meta.setSpacing(6)

        lay_meta.addWidget(QLabel("选中对象:"), 0, 0)
        self.lbl_hex_name = QLabel("请在左侧树中点击选中文件或记录节点")
        self.lbl_hex_name.setStyleSheet("color: #38BDF8; font-weight: bold;")
        lay_meta.addWidget(self.lbl_hex_name, 0, 1)

        lay_meta.addWidget(QLabel("文件类型:"), 0, 2)
        self.lbl_hex_type = QLabel("-")
        self.lbl_hex_type.setStyleSheet("color: #F8FAFC;")
        lay_meta.addWidget(self.lbl_hex_type, 0, 3)

        lay_meta.addWidget(QLabel("数据容量:"), 1, 0)
        self.lbl_hex_size = QLabel("-")
        self.lbl_hex_size.setStyleSheet("color: #4ADE80; font-family: monospace;")
        lay_meta.addWidget(self.lbl_hex_size, 1, 1)

        lay_meta.addWidget(QLabel("权限状态:"), 1, 2)
        self.lbl_hex_status = QLabel("-")
        self.lbl_hex_status.setStyleSheet("color: #CBD5E1;")
        lay_meta.addWidget(self.lbl_hex_status, 1, 3)

        lay_meta.addWidget(QLabel("解析描述:"), 2, 0)
        self.lbl_hex_desc = QLabel("-")
        self.lbl_hex_desc.setStyleSheet("color: #CBD5E1; font-size: 11px;")
        lay_meta.addWidget(self.lbl_hex_desc, 2, 1, 1, 3)

        lay_hex.addWidget(f_meta_box)

        # 经典 Hex / ASCII 双栏等宽检查视图
        lbl_hex_t = QLabel("🔍 字节级 Hex / ASCII 数据结构矩阵 (类似 M1 卡扇区查看器):")
        lbl_hex_t.setStyleSheet("font-size: 11px; color: #94A3B8; font-weight: bold;")
        lay_hex.addWidget(lbl_hex_t)

        self.txt_hex_view = QPlainTextEdit()
        self.txt_hex_view.setReadOnly(True)
        self.txt_hex_view.setStyleSheet("""
            background-color: #0B1120;
            color: #38BDF8;
            font-family: Consolas, "Courier New", monospace;
            font-size: 11px;
            padding: 8px;
            border: 1px solid #334155;
            border-radius: 6px;
        """)
        lay_hex.addWidget(self.txt_hex_view, 1)

        splitter_tree.addWidget(w_hex)
        splitter_tree.setStretchFactor(0, 2)
        splitter_tree.setStretchFactor(1, 3)
        splitter_tree.setSizes([340, 540])

        lay.addWidget(splitter_tree, 1)
        return w

    # ═════════════════════════════════════════════════════════════
    # 子页面 3: 原生 APDU 指令控制台
    # ═════════════════════════════════════════════════════════════
    def _build_apdu_console_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # 预设指令选择行
        row_preset = QHBoxLayout()
        row_preset.addWidget(QLabel("常用快捷指令:"))
        self.cmb_preset = QComboBox()
        self.cmb_preset.addItem("── 请选择常用预设 APDU 指令 ──", "")
        for cmd_hex, desc in self.PRESET_APDUS:
            self.cmb_preset.addItem(f"{cmd_hex} ({desc})", cmd_hex)
        self.cmb_preset.currentIndexChanged.connect(self._on_preset_selected)
        row_preset.addWidget(self.cmb_preset, 1)
        lay.addLayout(row_preset)

        # APDU 输入与发送行
        row_input = QHBoxLayout()
        row_input.addWidget(QLabel("APDU (Hex):"))
        self.txt_apdu = QLineEdit()
        self.txt_apdu.setPlaceholderText("例如: 00 84 00 00 08 (取随机数) 或 00 A4 04 00 08 ...")
        self.txt_apdu.returnPressed.connect(self._send_custom_apdu)
        row_input.addWidget(self.txt_apdu, 1)

        self.btn_send_apdu = QPushButton("🚀 发送指令")
        self.btn_send_apdu.setStyleSheet("background-color: #38BDF8; color: #0F172A; font-weight: bold; padding: 4px 12px;")
        self.btn_send_apdu.clicked.connect(self._send_custom_apdu)
        row_input.addWidget(self.btn_send_apdu)

        btn_clear_log = QPushButton("清空交互")
        btn_clear_log.clicked.connect(self._clear_apdu_log)
        row_input.addWidget(btn_clear_log)

        lay.addLayout(row_input)

        # APDU 交互日志展示
        self.txt_apdu_log = QPlainTextEdit()
        self.txt_apdu_log.setReadOnly(True)
        self.txt_apdu_log.setStyleSheet(
            "background-color: #0B1120; color: #F8FAFC; font-family: monospace; font-size: 11px; padding: 6px;"
        )
        lay.addWidget(self.txt_apdu_log, 1)
        return w

    # ═════════════════════════════════════════════════════════════
    # 业务逻辑与事件交互
    # ═════════════════════════════════════════════════════════════
    def _clear_apdu_log(self):
        """清空 APDU 终端日志并同步上报原生日志"""
        self.txt_apdu_log.clear()
        if self.serial_worker and hasattr(self.serial_worker, "log_operation"):
            self.serial_worker.log_operation("[CPU卡] 🗑️ 用户清空了 APDU 控制台交互日志")

    def _on_preset_selected(self, idx: int):
        cmd = self.cmb_preset.currentData()
        if cmd:
            self.txt_apdu.setText(cmd)
            desc = self.cmb_preset.currentText()
            if self.serial_worker and hasattr(self.serial_worker, "log_operation"):
                self.serial_worker.log_operation(f"[CPU卡] 📌 选中快捷指令预设: {desc}")

    def _start_auto_read(self):
        """启动后台线程一键读取 CPU 卡公开数据"""
        if not self.serial_worker or not self.serial_worker.is_connected():
            self._log_apdu_text("⚠️ 读写器尚未连接，请先在左侧面板连接读写器！")
            return

        if self.serial_worker and hasattr(self.serial_worker, "log_operation"):
            self.serial_worker.log_operation("[CPU卡] 🔍 用户点击触发【一键读取卡片内容】")

        self.btn_auto_read.setEnabled(False)
        self.btn_auto_read.setText("⏳ 正在读取 CPU 卡信息...")
        self.val_app_name.setText("正在选卡...")
        self.val_balance.setText("--")
        self.val_card_no.setText("-")
        self.val_validity.setText("-")
        self.table_trans.setRowCount(0)

        self._read_worker = CpuCardReadWorker(self.serial_worker)
        self._read_worker.sig_finished.connect(self._on_auto_read_finished)
        self._read_worker.sig_error.connect(self._on_auto_read_error)
        self._read_worker.start()

    def _on_auto_read_finished(self, res: dict):
        self.btn_auto_read.setEnabled(True)
        self.btn_auto_read.setText("🔍 一键读取卡片内容 (交通卡/金融卡/公共数据)")

        if res.get("error"):
            self.val_app_name.setText(f"读取失败: {res['error']}")
            self._log_apdu_text(f"❌ 读取错误: {res['error']}")
            if self.serial_worker and hasattr(self.serial_worker, "log_operation"):
                self.serial_worker.log_operation(f"[CPU卡] ❌ 一键读取异常结束: {res['error']}")
            if self.serial_worker and hasattr(self.serial_worker, "reactivate_target"):
                self.serial_worker.reactivate_target()
            return

        self.val_app_name.setText(res.get("app_name", "未知应用"))
        bal_str = res.get("balance_str", "--")
        self.val_balance.setText(bal_str)
        if "联机" in bal_str:
            self.val_balance.setStyleSheet("color: #38BDF8; font-size: 13px; font-weight: bold;")
        else:
            self.val_balance.setStyleSheet("color: #4ADE80; font-size: 16px; font-weight: bold;")

        self.val_card_no.setText(res.get("card_number") or "-")
        self.val_issuer.setText(res.get("issuer_code") or "-")

        start_d = res.get("start_date", "")
        end_d = res.get("end_date", "")
        if start_d and end_d:
            self.val_validity.setText(f"{start_d} ~ {end_d}")
        elif end_d:
            self.val_validity.setText(f"有效期至: {end_d}")
        else:
            self.val_validity.setText("-")

        # 填充交易流水
        trans_list = res.get("transactions", [])
        self.table_trans.setRowCount(len(trans_list))
        for r_idx, t_item in enumerate(trans_list):
            item_seq = QTableWidgetItem(str(t_item.get("seq", r_idx + 1)))
            item_seq.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_time = QTableWidgetItem(t_item.get("datetime", "-"))
            item_type = QTableWidgetItem(t_item.get("type_desc", "-"))
            item_amt = QTableWidgetItem(f"¥ {t_item.get('amount', 0.0):.2f}")
            item_amt.setForeground(Qt.GlobalColor.green if "充值" in t_item.get("type_desc", "") else Qt.GlobalColor.white)
            item_amt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item_term = QTableWidgetItem(t_item.get("terminal", "-"))

            self.table_trans.setItem(r_idx, 0, item_seq)
            self.table_trans.setItem(r_idx, 1, item_time)
            self.table_trans.setItem(r_idx, 2, item_type)
            self.table_trans.setItem(r_idx, 3, item_amt)
            self.table_trans.setItem(r_idx, 4, item_term)

        # 输出日志
        for log_item in res.get("logs", []):
            cmd = log_item.get("cmd", "")
            r = log_item.get("resp", {})
            self._append_apdu_exchange_log(cmd, r, 0)
            if self.serial_worker and hasattr(self.serial_worker, "log_operation"):
                sw = r.get("sw_hex", "")
                d_hex = r.get("data_hex", "")
                self.serial_worker.log_operation(f"[CPU卡] 交互 >> TX: {cmd} | RX: {d_hex} 0x{sw}")

        self._log_apdu_text(f"✨ CPU 卡公开信息读取完毕！共获取 {len(trans_list)} 条历史交易记录")
        if self.serial_worker and hasattr(self.serial_worker, "log_operation"):
            self.serial_worker.log_operation(f"[CPU卡] ✨ 一键读取完毕，共解析获取 {len(trans_list)} 条交易记录流水")
        if self.serial_worker and hasattr(self.serial_worker, "reactivate_target"):
            self.serial_worker.reactivate_target()

    def _on_auto_read_error(self, err: str):
        self.btn_auto_read.setEnabled(True)
        self.btn_auto_read.setText("🔍 一键读取卡片内容 (交通卡/金融卡/公共数据)")
        self.val_app_name.setText(f"读取异常: {err}")
        self._log_apdu_text(f"❌ 异常错误: {err}")
        if self.serial_worker and hasattr(self.serial_worker, "log_operation"):
            self.serial_worker.log_operation(f"[CPU卡] ❌ 后台读取线程抛出异常: {err}")
        if self.serial_worker and hasattr(self.serial_worker, "reactivate_target"):
            self.serial_worker.reactivate_target()

    # ═════════════════════════════════════════════════════════════
    # 全卡文件系统深度树状扫描处理 (核心新增)
    # ═════════════════════════════════════════════════════════════
    def _start_tree_scan(self):
        """启动后台线程全量深度扫描卡片文件系统 (若正在扫描中则触发取消)"""
        if self._tree_worker and self._tree_worker.isRunning():
            self._tree_worker.abort()
            self.btn_scan_tree.setText("⏳ 正在中断扫描...")
            self.btn_scan_tree.setEnabled(False)
            if self.serial_worker and hasattr(self.serial_worker, "log_operation"):
                self.serial_worker.log_operation("[CPU卡] ⏹ 用户点击了【取消扫描】")
            return

        if not self.serial_worker or not self.serial_worker.is_connected():
            QMessageBox.warning(self, "设备未连接", "请先在左侧面板连接读卡器！")
            return

        self.btn_scan_tree.setEnabled(True)
        self.btn_scan_tree.setText("⏹ 取消扫描")
        self.btn_scan_tree.setStyleSheet("background-color: #DC2626; color: #FFFFFF; font-weight: bold; padding: 6px 14px;")
        self.btn_export_tree.setEnabled(False)
        self.pbar_scan.setVisible(True)
        self.pbar_scan.setValue(0)
        self.tree_files.clear()
        self.txt_hex_view.clear()
        self.lbl_hex_name.setText("正在扫描卡内结构...")
        self.lbl_hex_type.setText("-")
        self.lbl_hex_size.setText("-")
        self.lbl_hex_status.setText("-")
        self.lbl_hex_desc.setText("-")

        if self.serial_worker and hasattr(self.serial_worker, "log_operation"):
            self.serial_worker.log_operation("[CPU卡] 🌲 用户触发【深度扫描卡片文件系统】...")

        self._tree_worker = CpuCardTreeScanWorker(self.serial_worker)
        self._tree_worker.sig_progress.connect(self._on_tree_scan_progress)
        self._tree_worker.sig_finished.connect(self._on_tree_scan_finished)
        self._tree_worker.sig_error.connect(self._on_tree_scan_error)
        self._tree_worker.start()

    def _on_tree_scan_progress(self, current: int, total: int, msg: str):
        pct = int(current / max(1, total) * 100)
        self.pbar_scan.setValue(pct)
        self.pbar_scan.setFormat(f"{pct}% - {msg}")

    def _on_tree_scan_finished(self, tree: dict):
        self.btn_scan_tree.setEnabled(True)
        self.btn_scan_tree.setText("🌲 深度扫描卡片文件系统 (SFI/FID 全目录)")
        self.btn_scan_tree.setStyleSheet("background-color: #059669; color: #FFFFFF; font-weight: bold; padding: 6px 14px;")
        self.pbar_scan.setVisible(False)
        self._tree_data = tree or {}

        if tree.get("error"):
            QMessageBox.warning(self, "扫描错误", f"扫描卡片文件系统时发生错误：\n{tree['error']}")
            return

        self.btn_export_tree.setEnabled(True)
        stats = tree.get("stats", {})
        total_files = stats.get("total_files", 0)
        read_bytes = stats.get("readable_bytes", 0)
        total_recs = stats.get("total_records", 0)
        prot_files = stats.get("protected_files", 0)

        if tree.get("aborted"):
            self.lbl_tree_stats.setText(
                f"⚠️ 扫描已中断: 捕获 {total_files} 个文件 | 可读数据: {read_bytes} 字节 | 记录: {total_recs} 条"
            )
        else:
            self.lbl_tree_stats.setText(
                f"✅ 扫描完成: 捕获 {total_files} 个文件节点 | 可读明文数据: {read_bytes} 字节 | 交易记录: {total_recs} 条 | 加密受保护文件: {prot_files} 个"
            )

        # 构建展示树
        self.tree_files.clear()
        root_children = tree.get("children", [])
        for node in root_children:
            self._add_tree_node(self.tree_files.invisibleRootItem(), node)

        self.tree_files.expandAll()
        self.lbl_hex_name.setText("扫描完毕，请点击左侧节点查看 Hex 数据矩阵")
        self.lbl_hex_desc.setText(f"主应用: {tree.get('app_name', '未知')} (AID: {tree.get('aid_hex', '')})")

    def _add_tree_node(self, parent_item, node_data: dict):
        name = node_data.get("name", "未命名")
        size_str = f"{node_data.get('size', 0)} 字节" if node_data.get("type") in ("binary", "record") else ""
        item = QTreeWidgetItem([name, size_str])
        item.setData(0, Qt.ItemDataRole.UserRole, node_data.get("id"))

        # 设置不同类型节点的颜色高亮
        n_type = node_data.get("type")
        if n_type == "directory":
            item.setForeground(0, Qt.GlobalColor.cyan)
        elif "💰" in name:
            item.setForeground(0, Qt.GlobalColor.green)
        elif n_type == "record_file":
            item.setForeground(0, Qt.GlobalColor.yellow)

        parent_item.addChild(item)
        for child in node_data.get("children", []):
            self._add_tree_node(item, child)

    def _on_tree_scan_error(self, err: str):
        self.btn_scan_tree.setEnabled(True)
        self.btn_scan_tree.setText("🌲 深度扫描卡片文件系统 (SFI/FID 全目录)")
        self.btn_scan_tree.setStyleSheet("background-color: #059669; color: #FFFFFF; font-weight: bold; padding: 6px 14px;")
        self.pbar_scan.setVisible(False)
        QMessageBox.critical(self, "扫描异常", f"扫描卡片文件系统时抛出异常：\n{err}")

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, col: int):
        node_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not node_id or not self._tree_data:
            return

        node = self._tree_data.get("flat_files", {}).get(node_id)
        if not node:
            return

        name = node.get("name", "-")
        n_type = node.get("type", "-")
        size = node.get("size", 0)
        desc = node.get("desc", "-")
        status = node.get("status", "-")
        dump_lines = node.get("dump_lines", [])
        semantics = node.get("semantics", [])

        self.lbl_hex_name.setText(name)
        self.lbl_hex_type.setText(n_type)
        self.lbl_hex_size.setText(f"{size} 字节 (0x{size:04X})")
        self.lbl_hex_status.setText("公开可读 (READ_FREE)" if status == "READ_OK" else status)
        self.lbl_hex_desc.setText(desc)

        # 组织 Hex / ASCII 对照视图
        lines = [
            f"// ==================================================================",
            f"// 文件名称: {name}",
            f"// 文件类型: {n_type} | 大小: {size} 字节 (0x{size:04X})",
            f"// 功能描述: {desc}",
        ]
        if semantics:
            lines.append("// ────────────────────── 智能语义解析项 ──────────────────────")
            for sem in semantics:
                lines.append(f"//  ★ {sem}")

        lines.append("// ────────────────────── 字节级 Hex / ASCII 对照矩阵 ────────────────")
        lines.append("// Offset  00 01 02 03 04 05 06 07  08 09 0A 0B 0C 0D 0E 0F  | ASCII 文本")
        lines.append("// ------------------------------------------------------------------")

        if dump_lines:
            lines.extend(dump_lines)
        else:
            lines.append("(该节点无二进制数据载荷)")

        lines.append("// ==================================================================")
        self.txt_hex_view.setPlainText("\n".join(lines))

    def _export_tree_json(self):
        """将全卡扫描到的文件系统数据导出为 JSON 文件 (安全处理 bytes 类型，避免 TypeError)"""
        if not self._tree_data:
            return

        default_name = f"CPU_Card_Dump_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 CPU 卡全量公开文件系统数据", default_name, "JSON Files (*.json);;All Files (*)"
        )
        if not path:
            return

        try:
            def _clean_node(node):
                if isinstance(node, dict):
                    cleaned = {}
                    for k, v in node.items():
                        if k == "data" and isinstance(v, (bytes, bytearray)):
                            cleaned["data_hex"] = v.hex().upper()
                        elif isinstance(v, (bytes, bytearray)):
                            cleaned[k] = v.hex().upper()
                        elif isinstance(v, (dict, list)):
                            cleaned[k] = _clean_node(v)
                        else:
                            cleaned[k] = v
                    return cleaned
                elif isinstance(node, list):
                    return [_clean_node(x) for x in node]
                elif isinstance(node, (bytes, bytearray)):
                    return node.hex().upper()
                return node

            export_dict = {
                "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "card_uid": self.lbl_uid_val.text(),
                "sak": self.lbl_sak_val.text(),
                "ats": self.lbl_ats_val.text(),
                "app_name": self._tree_data.get("app_name", ""),
                "aid_hex": self._tree_data.get("aid_hex", ""),
                "stats": self._tree_data.get("stats", {}),
                "structure_tree": _clean_node(self._tree_data.get("children", [])),
                "files": _clean_node(self._tree_data.get("flat_files", {})),
            }

            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    export_dict,
                    f,
                    ensure_ascii=False,
                    indent=2,
                    default=lambda o: o.hex().upper() if isinstance(o, (bytes, bytearray)) else str(o)
                )

            QMessageBox.information(self, "导出成功", f"全卡文件系统数据已成功导出至：\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出文件发生错误：\n{e}")

    # ═════════════════════════════════════════════════════════════
    # APDU 自定义交互发送与排版呈现
    # ═════════════════════════════════════════════════════════════
    def _send_custom_apdu(self):
        """发送自定义 APDU 指令"""
        raw_text = self.txt_apdu.text().strip()
        if not raw_text:
            return

        cleaned_hex = raw_text.replace(" ", "").replace("0x", "").replace("0X", "").replace(",", "")
        if len(cleaned_hex) % 2 != 0:
            self._log_apdu_text(f"❌ 十六进制格式错误: 字符数必须为偶数 (当前为 {len(cleaned_hex)} 位，请检查是否有如 '8' 应写为 '08')")
            return

        try:
            apdu_bytes = bytes.fromhex(cleaned_hex)
        except ValueError:
            self._log_apdu_text(f"❌ 十六进制格式错误: 包含非法字符 '{raw_text}'")
            return

        if len(apdu_bytes) < 4:
            self._log_apdu_text(f"❌ APDU 指令过短: 标准 APDU 至少需 4 字节 Header (CLA INS P1 P2)，当前仅 {len(apdu_bytes)} 字节")
            return

        if not self.serial_worker or not self.serial_worker.is_connected():
            self._log_apdu_text("⚠️ 读写器尚未连接，请先连接读写器！")
            return

        self.btn_send_apdu.setEnabled(False)
        self._apdu_worker = ApduSendWorker(self.serial_worker, apdu_bytes)
        self._apdu_worker.sig_result.connect(self._on_apdu_result)
        self._apdu_worker.sig_error.connect(self._on_apdu_error)
        self._apdu_worker.start()

    def _on_apdu_result(self, res: dict, elapsed_ms: float):
        self.btn_send_apdu.setEnabled(True)
        raw_text = self.txt_apdu.text().strip()
        cleaned_hex = raw_text.replace(" ", "").upper()
        self._append_apdu_exchange_log(cleaned_hex, res, elapsed_ms)

    def _on_apdu_error(self, err: str):
        self.btn_send_apdu.setEnabled(True)
        self._log_apdu_text(f"❌ APDU 发送异常: {err}")

    def _append_apdu_exchange_log(self, cmd_hex: str, resp: dict, elapsed_ms: float):
        """采用层级树状结构与深度语义解析排版 APDU 交互过程"""
        t_str = time.strftime("%H:%M:%S")
        ok = resp.get("ok", False)
        sw_hex = resp.get("sw_hex", "")
        sw_desc = resp.get("sw_desc", "")
        data_hex = resp.get("data_hex", "")
        rx_data = resp.get("data", b"")
        error_msg = resp.get("error", "")

        try:
            cmd_bytes = bytes.fromhex(cmd_hex.replace(" ", ""))
        except Exception:
            cmd_bytes = b""

        # 1. 深度解析发送的 APDU 指令头与含义
        cmd_info = APDUProtocol.explain_apdu_command(cmd_bytes)
        mnemonic = cmd_info.get("mnemonic", "APDU")
        cmd_desc = cmd_info.get("desc", "")
        cmd_details = cmd_info.get("details", [])

        formatted_tx = " ".join(f"{b:02X}" for b in cmd_bytes) if cmd_bytes else cmd_hex

        lines = [
            f"┌── [{t_str}] APDU 指令交互 ({mnemonic}) ─────────────────────────",
            f"│ 📤 TX >> {formatted_tx}",
            f"│    ├─ 指令助记: {mnemonic} ({cmd_desc})",
        ]
        for d in cmd_details:
            lines.append(f"│    ├─ {d}")

        if ok:
            sw1 = int(sw_hex[:2], 16) if len(sw_hex) >= 2 else 0x90
            sw2 = int(sw_hex[2:4], 16) if len(sw_hex) >= 4 else 0x00
            time_str = f" [耗时: {elapsed_ms:.1f} ms]" if elapsed_ms > 0 else ""
            rx_summary = f"{data_hex} {sw_hex}".strip() if data_hex else sw_hex

            lines.append(f"│ 📥 RX << {rx_summary}{time_str}")
            lines.append(f"│    ├─ 状态码: [0x{sw_hex}] {sw_desc}")

            # 2. 深度推导返回数据语义 (余额/卡号/流水/AID/随机数)
            analysis = APDUProtocol.dissect_apdu_response(cmd_bytes, rx_data, sw1, sw2)
            semantics = analysis.get("semantics", [])
            if semantics:
                lines.append("│    ├─ 智能语义解析:")
                for sem in semantics:
                    lines.append(f"│    │  {sem}")

            dump_lines = analysis.get("dump_lines", [])
            if dump_lines:
                lines.append(f"│    └─ 数据 Hex / ASCII 结构矩阵 (共 {len(rx_data)} 字节):")
                for dl in dump_lines:
                    lines.append(f"│       {dl}")
            else:
                lines.append(f"│    └─ 数据载荷: {'(空数据域)' if not rx_data else data_hex}")
        else:
            lines.append(f"│ ❌ ERR << {error_msg} (状态字: 0x{sw_hex} {sw_desc})")
            lines.append("│    └─ 通信异常或卡片返回非预期的错误状态码")

        lines.append("└──────────────────────────────────────────────────────────")
        self._log_apdu_text("\n".join(lines))

    def _log_apdu_text(self, text: str):
        self.txt_apdu_log.appendPlainText(text)
        sb = self.txt_apdu_log.verticalScrollBar()
        sb.setValue(sb.maximum())
