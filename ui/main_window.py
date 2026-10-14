# -*- coding: utf-8 -*-
"""
PyMifareTool - 主窗口界面与现代化暗黑科技风格仪表盘 (Pro 增强版)
基于 PyQt6 打造，完整集成 M1T 核心特性与本地读卡器驱动
支持：
- 线程安全连接与延迟优雅自启
- 实时卡片监测、大号 UID 显示、8H10D/WG26/WG34 卡号换算
- 扇区矩阵、差分对比器、发卡流水管理、密码字典与指令终端
- 报文日志双向联动与底层指令发送
"""

import sys
import datetime
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTabWidget, QGroupBox, QGridLayout, QPlainTextEdit,
    QStatusBar, QMessageBox, QFrame, QSplitter, QScrollArea, QApplication
)
from PyQt6.QtGui import QFont, QColor, QIcon
from PyQt6.QtCore import Qt, pyqtSlot, QTimer
import serial.tools.list_ports

from core.serial_worker import SerialWorker
from core.adapters import ReaderAdapterFactory
from core.card_db import CardDatabase
from ui.sector_table import SectorTableWidget
from ui.dump_diff import DumpDiffWidget
from ui.card_manage import CardManageWidget
from ui.dictionary_tools import DictionaryToolsWidget

DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #0F172A;
    color: #F8FAFC;
    font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    font-size: 13px;
}
QGroupBox {
    border: 1px solid #334155;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QPushButton, QToolButton {
    background-color: #1E293B;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 5px 10px;
    color: #F8FAFC;
    font-weight: 500;
    font-size: 12px;
}
QPushButton:hover, QToolButton:hover {
    background-color: #334155;
    border-color: #64748B;
}
QPushButton:pressed, QToolButton:pressed {
    background-color: #0F172A;
}
QToolButton::menu-button {
    border-left: 1px solid #475569;
    width: 16px;
}
QMenu {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    background: transparent;
    padding: 6px 18px;
    color: #F8FAFC;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #0284C7;
    color: #FFFFFF;
}
QMenu::separator {
    height: 1px;
    background: #334155;
    margin: 4px 6px;
}
QComboBox {
    background-color: #1E293B;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 4px 22px 4px 6px;
    color: #F8FAFC;
    font-size: 12px;
}
QComboBox:hover {
    border-color: #38BDF8;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: none;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #94A3B8;
    width: 0;
    height: 0;
    margin-right: 6px;
}
QComboBox::down-arrow:hover {
    border-top: 5px solid #38BDF8;
}
QComboBox QAbstractItemView {
    background-color: #1E293B;
    border: 1px solid #334155;
    selection-background-color: #0284C7;
    selection-color: #FFFFFF;
    color: #F8FAFC;
    padding: 4px;
    outline: none;
}
QLineEdit {
    background-color: #1E293B;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 4px 8px;
    color: #F8FAFC;
    font-size: 12px;
}
QLineEdit:focus {
    border-color: #38BDF8;
}
QTabWidget::pane {
    border: 1px solid #334155;
    border-radius: 8px;
    background-color: #111827;
}
QTabBar::tab {
    background-color: #1E293B;
    color: #94A3B8;
    padding: 6px 14px;
    margin-right: 3px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: bold;
    font-size: 12px;
}
QTabBar::tab:selected {
    background-color: #0284C7;
    color: #FFFFFF;
}
QTableWidget {
    background-color: #0B1120;
    gridline-color: #1E293B;
    border: none;
    selection-background-color: #0369A1;
    selection-color: #FFFFFF;
}
QHeaderView::section {
    background-color: #1E293B;
    color: #94A3B8;
    padding: 4px;
    border: none;
    font-weight: bold;
}
QPlainTextEdit {
    background-color: #050B14;
    border: 1px solid #1E293B;
    font-family: Consolas, monospace;
    font-size: 11px;
    color: #38BDF8;
}
QScrollBar:vertical {
    border: none;
    background: #0F172A;
    width: 8px;
}
QScrollBar::handle:vertical {
    background: #334155;
    border-radius: 4px;
}
QScrollBar:horizontal {
    border: none;
    background: #0F172A;
    height: 8px;
}
QScrollBar::handle:horizontal {
    background: #334155;
    border-radius: 4px;
}
QScrollArea {
    background: transparent;
    border: none;
}
QSplitter::handle {
    background-color: #1E293B;
}
QSplitter::handle:horizontal {
    width: 5px;
}
QSplitter::handle:vertical {
    height: 5px;
}
QSplitter::handle:hover {
    background-color: #38BDF8;
}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyMifareTool - 智能 Mifare Classic 管理套件 (Pro)")
        self.setStyleSheet(DARK_STYLESHEET)

        # 屏幕分辨率自适应初始尺寸与安全最小尺寸 (防止小屏幕展示不全)
        self.setMinimumSize(880, 520)
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            init_w = max(880, min(1220, int(avail.width() * 0.86)))
            init_h = max(540, min(780, int(avail.height() * 0.86)))
            self.resize(init_w, init_h)
            # 居中对齐
            self.move(
                avail.x() + (avail.width() - init_w) // 2,
                avail.y() + (avail.height() - init_h) // 2
            )
        else:
            self.resize(1120, 680)

        # 核心引擎
        self.db = CardDatabase()
        self.worker = SerialWorker()
        self.current_uid = ""

        self._init_ui()
        self._init_signals()

        # 延迟优雅自动连接 (避免窗口加载阻塞)
        QTimer.singleShot(600, self._auto_connect_default)

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(0)

        # 水平主分割器 (实现左侧看板与右侧工作区的自适应拖拽与布局)
        self.main_hsplitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_hsplitter.setChildrenCollapsible(False)

        # 左侧看板面板内容部件 (紧凑自适应排版，避免垂直溢出)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(6, 4, 6, 6)
        left_layout.setSpacing(6)

        # 标题 Badge (紧凑设计)
        title_box = QFrame()
        title_box.setObjectName("titleBox")
        title_box.setStyleSheet("#titleBox { background-color: #1E293B; border-radius: 6px; }")
        t_lay = QVBoxLayout(title_box)
        t_lay.setContentsMargins(8, 6, 8, 6)
        t_lay.setSpacing(2)
        lbl_title = QLabel("PyMifareTool")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #38BDF8;")
        lbl_sub = QLabel("NFC / M1 卡全功能上位机套件")
        lbl_sub.setStyleSheet("font-size: 10px; color: #94A3B8;")
        t_lay.addWidget(lbl_title)
        t_lay.addWidget(lbl_sub)
        left_layout.addWidget(title_box)

        # 1. 设备串口连接卡片
        grp_conn = QGroupBox("🔌 硬件连接管理")
        grp_conn.setStyleSheet("QGroupBox { color: #38BDF8; font-size: 12px; }")
        lay_conn = QGridLayout(grp_conn)
        lay_conn.setContentsMargins(6, 6, 6, 6)
        lay_conn.setSpacing(4)

        lay_conn.addWidget(QLabel("设备类型:"), 0, 0)
        self.combo_device = QComboBox()
        self.combo_device.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_device.setMinimumContentsLength(6)
        for title, dev_id in ReaderAdapterFactory.DEVICE_CHOICES:
            self.combo_device.addItem(title, dev_id)
        self.combo_device.currentIndexChanged.connect(self._on_device_type_changed)
        lay_conn.addWidget(self.combo_device, 0, 1)

        lay_conn.addWidget(QLabel("串口号:"), 1, 0)
        self.combo_port = QComboBox()
        self.combo_port.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_port.setMinimumContentsLength(6)
        self.btn_refresh_ports = QPushButton("🔄")
        self.btn_refresh_ports.setToolTip("刷新可用串口列表")
        self.btn_refresh_ports.setFixedWidth(28)
        self.btn_refresh_ports.clicked.connect(self._refresh_ports)
        port_h = QHBoxLayout()
        port_h.setContentsMargins(0, 0, 0, 0)
        port_h.setSpacing(4)
        port_h.addWidget(self.combo_port, 1)
        port_h.addWidget(self.btn_refresh_ports, 0)
        lay_conn.addLayout(port_h, 1, 1)

        lay_conn.addWidget(QLabel("波特率:"), 2, 0)
        self.combo_baud = QComboBox()
        self.combo_baud.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_baud.setMinimumContentsLength(6)
        self.combo_baud.addItems([
            "115200 (PCR532推荐)",
            "38400 (发卡器推荐)",
            "9600",
            "19200",
            "57600",
            "230400"
        ])
        lay_conn.addWidget(self.combo_baud, 2, 1)

        btn_h = QHBoxLayout()
        btn_h.setContentsMargins(0, 0, 0, 0)
        btn_h.setSpacing(4)

        self.btn_connect = QPushButton("连接读卡器")
        self.btn_connect.setStyleSheet("background-color: #0284C7; font-weight: bold; padding: 5px 4px;")
        self.btn_connect.clicked.connect(self._toggle_connection)
        btn_h.addWidget(self.btn_connect, 1)

        self.btn_read_id_card = QPushButton("🪪 读身份证")
        self.btn_read_id_card.setStyleSheet("background-color: #4338CA; font-weight: bold; padding: 5px 4px;")
        self.btn_read_id_card.setToolTip("手动单次读取二代身份证 8 字节物理 UID (ISO14443-B)")
        self.btn_read_id_card.clicked.connect(self._on_read_id_card_clicked)
        btn_h.addWidget(self.btn_read_id_card, 1)

        lay_conn.addLayout(btn_h, 3, 0, 1, 2)

        self.lbl_status_led = QLabel("● 状态: 未连接")
        self.lbl_status_led.setStyleSheet("color: #EF4444; font-weight: bold; font-size: 11px;")
        lay_conn.addWidget(self.lbl_status_led, 4, 0, 1, 2)

        left_layout.addWidget(grp_conn)

        # 2. 实时感应卡片看板 (核心视觉焦点，高度紧凑)
        grp_card = QGroupBox("💳 实时卡片监测")
        grp_card.setStyleSheet("QGroupBox { color: #10B981; font-size: 12px; }")
        lay_card = QVBoxLayout(grp_card)
        lay_card.setContentsMargins(6, 6, 6, 6)
        lay_card.setSpacing(4)

        # 卡片状态标签
        self.lbl_card_badge = QLabel("等待贴卡感应...")
        self.lbl_card_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_card_badge.setStyleSheet(
            "background-color: #1E293B; color: #94A3B8; border-radius: 4px; padding: 4px; font-weight: bold; font-size: 11px;"
        )
        lay_card.addWidget(self.lbl_card_badge)

        # 大号 UID 呈现 (自适应 18px，保证任何尺寸下美观居中)
        self.lbl_hero_uid = QLabel("-- -- -- --")
        self.lbl_hero_uid.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_hero_uid.setStyleSheet(
            "font-size: 18px; font-family: Consolas; font-weight: bold; color: #38BDF8; padding: 6px;"
            "background-color: #0B1120; border: 1px dashed #334155; border-radius: 6px;"
        )
        lay_card.addWidget(self.lbl_hero_uid)

        # 换算信息列表 (紧凑栅格)
        info_grid = QGridLayout()
        info_grid.setContentsMargins(0, 2, 0, 2)
        info_grid.setSpacing(3)

        info_grid.addWidget(QLabel("正序 Hex:"), 0, 0)
        self.val_hex_norm = QLabel("-")
        info_grid.addWidget(self.val_hex_norm, 0, 1)

        info_grid.addWidget(QLabel("倒序 Hex:"), 1, 0)
        self.val_hex_rev = QLabel("-")
        info_grid.addWidget(self.val_hex_rev, 1, 1)

        info_grid.addWidget(QLabel("10进制(8H10D):"), 2, 0)
        self.val_dec_10d = QLabel("-")
        self.val_dec_10d.setStyleSheet("color: #34D399; font-weight: bold;")
        info_grid.addWidget(self.val_dec_10d, 2, 1)

        info_grid.addWidget(QLabel("门禁韦根 WG26:"), 3, 0)
        self.val_wg26 = QLabel("-")
        info_grid.addWidget(self.val_wg26, 3, 1)

        info_grid.addWidget(QLabel("门禁韦根 WG34:"), 4, 0)
        self.val_wg34 = QLabel("-")
        info_grid.addWidget(self.val_wg34, 4, 1)

        info_grid.addWidget(QLabel("最近刷卡时间:"), 5, 0)
        self.val_time = QLabel("-")
        info_grid.addWidget(self.val_time, 5, 1)

        lay_card.addLayout(info_grid)

        # 动作按钮
        self.btn_save_db = QPushButton("📥 快速建档 / 登记此卡")
        self.btn_save_db.setEnabled(False)
        self.btn_save_db.setStyleSheet("padding: 5px; font-weight: bold;")
        self.btn_save_db.clicked.connect(self._on_register_card)
        lay_card.addWidget(self.btn_save_db)

        left_layout.addWidget(grp_card)

        # 底部通信监视折叠按钮
        self.btn_toggle_log = QPushButton("📜 通信报文监视器 [收起/展开]")
        self.btn_toggle_log.setStyleSheet("padding: 5px; font-size: 11px;")
        self.btn_toggle_log.clicked.connect(self._toggle_log_box)
        left_layout.addWidget(self.btn_toggle_log)
        left_layout.addStretch()

        # 放入自适应滚动区域中 (保证小屏幕或高 DPI 缩放时左侧所有看板内容均可滑动浏览，绝不截断)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setWidget(left_panel)
        left_scroll.setMinimumWidth(280)
        left_scroll.setMaximumWidth(400)

        self.main_hsplitter.addWidget(left_scroll)

        # 右侧核心工作区 (使用 QSplitter 支持上下折叠)
        splitter = QSplitter(Qt.Orientation.Vertical)

        # 顶部 Tab 分页 (紧凑标签与完整 ToolTip，确保各种屏幕尺寸绝不溢出截断)
        self.tabs = QTabWidget()

        self.tab_sector = SectorTableWidget(serial_worker=self.worker)
        self.tab_diff = DumpDiffWidget()
        self.tab_manage = CardManageWidget(self.db)
        self.tab_tools = DictionaryToolsWidget()

        self.tabs.addTab(self.tab_sector, "📑 扇区矩阵")
        self.tabs.addTab(self.tab_diff, "🔍 Dump 对比")
        self.tabs.addTab(self.tab_manage, "📋 发卡管理")
        self.tabs.addTab(self.tab_tools, "🛠️ 字典工具")

        self.tabs.setTabToolTip(0, "Mifare Classic 16 扇区 / 64 块可视化数据矩阵与操作")
        self.tabs.setTabToolTip(1, "Dump 差分对比器 (消费前后/双卡数据比对)")
        self.tabs.setTabToolTip(2, "发卡档案管理与实时刷卡流水审计")
        self.tabs.setTabToolTip(3, "密码字典库、Access Bits 权限解析器与调试终端")

        splitter.addWidget(self.tabs)

        # 底部报文日志窗口
        self.log_box = QWidget()
        log_lay = QVBoxLayout(self.log_box)
        log_lay.setContentsMargins(0, 4, 0, 0)
        log_head = QHBoxLayout()
        lbl_log_t = QLabel("📡 串口原生数据流日志 (Hex Stream Monitor)")
        lbl_log_t.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: bold;")
        btn_clear_log = QPushButton("清空日志")
        btn_clear_log.setFixedSize(65, 22)
        btn_clear_log.setStyleSheet("font-size: 11px; padding: 2px;")
        btn_clear_log.clicked.connect(lambda: self.txt_log.clear())
        log_head.addWidget(lbl_log_t)
        log_head.addStretch()
        log_head.addWidget(btn_clear_log)
        log_lay.addLayout(log_head)

        self.txt_log = QPlainTextEdit()
        self.txt_log.setMinimumHeight(60)
        self.txt_log.setMaximumHeight(130)
        log_lay.addWidget(self.txt_log)

        splitter.addWidget(self.log_box)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([480, 140])

        self.main_hsplitter.addWidget(splitter)
        self.main_hsplitter.setStretchFactor(0, 0)
        self.main_hsplitter.setStretchFactor(1, 1)
        self.main_hsplitter.setSizes([300, 920])

        main_layout.addWidget(self.main_hsplitter)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪 - 支持 PCR532/PN532 全功能双向读写与经典广播发卡器自适应")

    def _init_signals(self):
        self._bind_worker_signals()

        # 绑定工具箱终端发送指令至串口
        self.tab_tools.sig_send_hex.connect(self._on_send_hex_from_tools)

        # 绑定扇区表格通知至状态栏与日志
        self.tab_sector.sig_notify.connect(self._on_sector_table_notify)

    def _bind_worker_signals(self):
        self.worker.sig_connected.connect(self._on_connected)
        self.worker.sig_disconnected.connect(self._on_disconnected)
        self.worker.sig_card_swiped.connect(self._on_card_swiped)
        self.worker.sig_card_removed.connect(self._on_card_removed)
        self.worker.sig_device_identified.connect(self._on_device_identified)
        self.worker.sig_raw_log.connect(self._on_raw_log)
        self.worker.sig_status.connect(lambda msg: self.status_bar.showMessage(msg))

    def _on_device_type_changed(self, idx: int):
        dev_id = self.combo_device.currentData()
        if dev_id == ReaderAdapterFactory.DEVICE_PN532:
            self.combo_baud.setCurrentIndex(0)  # 115200
        elif dev_id == ReaderAdapterFactory.DEVICE_BROADCASTER:
            self.combo_baud.setCurrentIndex(1)  # 38400

    def _refresh_ports(self):
        self.combo_port.clear()
        ports = serial.tools.list_ports.comports()
        for p in ports:
            self.combo_port.addItem(f"{p.device} ({p.description})", p.device)
        # 默认选中 COM3
        for i in range(self.combo_port.count()):
            if "COM3" in self.combo_port.itemText(i):
                self.combo_port.setCurrentIndex(i)
                break

    def _auto_connect_default(self):
        self._refresh_ports()
        if self.combo_port.count() > 0:
            self._toggle_connection()

    def _toggle_connection(self):
        if self.worker.isRunning():
            self.worker.stop()
            self.btn_connect.setText("连接读卡器")
            self.btn_connect.setStyleSheet("background-color: #0284C7; font-weight: bold; padding: 7px;")
            self.lbl_status_led.setText("● 状态: 已断开")
            self.lbl_status_led.setStyleSheet("color: #EF4444; font-weight: bold;")
        else:
            port = self.combo_port.currentData() or "COM3"
            baud_text = self.combo_baud.currentText()
            baud = int(baud_text.split()[0])
            device_type = self.combo_device.currentData() or ReaderAdapterFactory.DEVICE_AUTO

            self.worker.set_connection(port, baud, device_type=device_type)
            self.tab_sector.set_serial_worker(self.worker)
            self.worker.start()

    @pyqtSlot(str, int)
    def _on_connected(self, port, baud):
        self.btn_connect.setText("断开连接")
        self.btn_connect.setStyleSheet("background-color: #DC2626; font-weight: bold; padding: 7px;")
        self.lbl_status_led.setText(f"● 已在线 ({port} @ {baud})")
        self.lbl_status_led.setStyleSheet("color: #10B981; font-weight: bold;")
        self.status_bar.showMessage(f"已连接硬件串口: {port} @ {baud} bps，正在侦听/握手...")

    @pyqtSlot(str)
    def _on_disconnected(self, reason):
        self.btn_connect.setText("连接读卡器")
        self.btn_connect.setStyleSheet("background-color: #0284C7; font-weight: bold; padding: 7px;")
        self.lbl_status_led.setText("● 状态: 未连接")
        self.lbl_status_led.setStyleSheet("color: #EF4444; font-weight: bold;")
        self.status_bar.showMessage(f"断开: {reason}")

    @pyqtSlot(str, str)
    def _on_device_identified(self, dev_name: str, fw_ver: str):
        self.lbl_status_led.setText(f"● 已识别: {dev_name}")
        self.lbl_status_led.setStyleSheet("color: #10B981; font-weight: bold;")
        self.status_bar.showMessage(f"🎯 读卡器已就绪: {dev_name} | 固件/协议: {fw_ver}")

    @pyqtSlot()
    def _on_card_removed(self):
        self.lbl_card_badge.setText("等待贴卡感应...")
        self.lbl_card_badge.setStyleSheet(
            "background-color: #1E293B; color: #94A3B8; border-radius: 4px; padding: 4px; font-weight: bold; font-size: 11px;"
        )

    @pyqtSlot(dict)
    def _on_card_swiped(self, frame_info):
        """核心业务: 处理刷卡捕获事件"""
        uid_bytes = frame_info.get("uid_bytes", b"")
        conv = frame_info.get("conversions", {})
        raw_hex = " ".join(f"{b:02X}" for b in frame_info.get("raw", b""))

        self.current_uid = conv.get("hex_normal", "")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. 更新左侧 Hero 看板
        is_id_card = frame_info.get("is_id_card", False) or conv.get("uid_type", "").startswith("8-byte")
        if is_id_card:
            self.lbl_card_badge.setText("🪪 成功识别 二代身份证 (ISO 14443-B)")
            self.lbl_card_badge.setStyleSheet(
                "background-color: #312E81; color: #818CF8; border-radius: 6px; padding: 6px; font-weight: bold;"
            )
            self.lbl_hero_uid.setText(self.current_uid)
            self.lbl_hero_uid.setStyleSheet(
                "font-size: 20px; font-family: Consolas; font-weight: bold; color: #818CF8; padding: 10px;"
                "background-color: #0B1120; border: 2px solid #6366F1; border-radius: 8px;"
            )
        else:
            self.lbl_card_badge.setText("✅ 成功识别 ISO 14443-3A 卡片")
            self.lbl_card_badge.setStyleSheet(
                "background-color: #064E3B; color: #34D399; border-radius: 6px; padding: 6px; font-weight: bold;"
            )
            self.lbl_hero_uid.setText(self.current_uid)
            self.lbl_hero_uid.setStyleSheet(
                "font-size: 24px; font-family: Consolas; font-weight: bold; color: #34D399; padding: 10px;"
                "background-color: #0B1120; border: 2px solid #10B981; border-radius: 8px;"
            )

        self.val_hex_norm.setText(conv.get("hex_normal", "-"))
        self.val_hex_rev.setText(conv.get("hex_reverse", "-"))
        self.val_dec_10d.setText(conv.get("dec_10d_rev", "-"))
        self.val_wg26.setText(conv.get("wiegand_26", "-"))
        self.val_wg34.setText(conv.get("wiegand_34", "-"))
        self.val_time.setText(now_str)
        self.btn_save_db.setEnabled(True)

        # 2. 自动同步至数据矩阵 0 块
        self.tab_sector.update_uid(uid_bytes)

        # 3. 自动记录数据库流水
        card_info = self.db.record_swipe(self.current_uid, conv, raw_hex)
        self.tab_manage.refresh_cards()
        self.tab_manage.refresh_logs()

        if is_id_card:
            self.status_bar.showMessage(f"🪪 捕获二代身份证 UID: [{self.current_uid}] (8字节 GUID)")
        else:
            self.status_bar.showMessage(
                f"🎯 捕获新卡片: UID=[{self.current_uid}] | 累计刷卡: {card_info.get('swipe_count')} 次"
            )

    def _on_read_id_card_clicked(self):
        """手动单次触发读取二代身份证 UID"""
        if not self.worker.isRunning() or not self.worker.is_connected():
            QMessageBox.warning(self, "设备未连接", "请先连接 PCR532 / PN532 读卡器！")
            return

        self.status_bar.showMessage("正在调谐 Type B CIU 射频并读取二代身份证 UID...")
        card_info = self.worker.read_id_card_once(timeout=0.45)
        if card_info and "uid_bytes" in card_info:
            self._on_card_swiped(card_info)
            uid_hex = card_info.get("conversions", {}).get("hex_normal", "")
            QMessageBox.information(
                self, "读取成功",
                f"🪪 成功读取二代居民身份证 UID！\n\n"
                f"UID (8字节 Hex): {uid_hex}\n"
                f"协议标准: ISO/IEC 14443 Type B\n\n"
                f"注: 该卡号已自动同步至左侧看板与发卡流水记录。"
            )
        else:
            QMessageBox.warning(
                self, "未感应到身份证",
                "未检测到二代身份证！\n"
                "请将二代居民身份证贴紧读卡器天线感应区后重试。"
            )

    @pyqtSlot(str, str)
    def _on_raw_log(self, direction, msg):
        now = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        if direction == "RX":
            line = f"[{now}] ⬇ RX: {msg}"
        elif direction == "TX":
            line = f"[{now}] ⬆ TX: {msg}"
        elif direction == "FRAME":
            line = f"[{now}] ★ {msg}"
        else:
            line = f"[{now}] ℹ {msg}"
        self.txt_log.appendPlainText(line)

        # 同步推送到工具箱内的交互终端
        self.tab_tools.append_terminal_log(direction, msg)

    @pyqtSlot(bytes)
    def _on_send_hex_from_tools(self, data: bytes):
        """处理来自调试终端的下发指令"""
        if not self.worker.is_connected():
            self.tab_tools.append_terminal_log("SYS", "❌ 读卡器未连接，无法发送指令")
            return
        success = self.worker.send_raw(data)
        if not success:
            self.tab_tools.append_terminal_log("SYS", "❌ 指令发送失败")

    @pyqtSlot(str)
    def _on_sector_table_notify(self, msg: str):
        self.status_bar.showMessage(msg)
        self._on_raw_log("OP", msg)

    def _on_register_card(self):
        if not self.current_uid:
            return
        from ui.card_manage import EditCardDialog
        dialog = EditCardDialog(self.current_uid, "新发卡片", "持卡人", "通过上位机即时录入", self)
        if dialog.exec():
            name, holder, note = dialog.get_data()
            self.db.update_card_info(self.current_uid, name, holder, note)
            self.tab_manage.refresh_cards()
            QMessageBox.information(self, "登记成功", f"卡片 [{self.current_uid}] 已成功存档！")

    def _toggle_log_box(self):
        self.log_box.setVisible(not self.log_box.isVisible())

    def closeEvent(self, event):
        if hasattr(self, "tab_sector") and self.tab_sector.card_op_worker:
            if self.tab_sector.card_op_worker.isRunning():
                self.tab_sector.card_op_worker.abort()
                self.tab_sector.card_op_worker.wait(1000)
        self.worker.stop()
        event.accept()
