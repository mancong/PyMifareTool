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
    QStatusBar, QMessageBox, QFrame, QSplitter, QScrollArea, QApplication,
    QCheckBox, QSpinBox, QRadioButton, QButtonGroup, QFileDialog,
    QTabBar, QStylePainter, QStyleOptionTab, QStyle
)
from PyQt6.QtGui import QFont, QColor, QIcon
from PyQt6.QtCore import Qt, pyqtSlot, QTimer, QThread, pyqtSignal
import serial.tools.list_ports

from core.serial_worker import SerialWorker
from core.adapters import ReaderAdapterFactory
from core.card_db import CardDatabase
from ui.sector_table import SectorTableWidget
from ui.dump_diff import DumpDiffWidget
from ui.card_manage import CardManageWidget
from ui.dictionary_tools import DictionaryToolsWidget
from ui.cpu_card_widget import CpuCardWidget

DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #0F172A;
    color: #F8FAFC;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", "Microsoft YaHei", "PingFang SC", sans-serif;
    font-size: 10pt;
}
QGroupBox {
    border: 1px solid #334155;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: bold;
    background-color: #0F172A;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    background-color: #0F172A;
}
QPushButton, QToolButton {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 5px 10px;
    color: #F8FAFC;
    font-weight: 500;
    font-size: 12px;
}
QRadioButton {
    color: #F8FAFC;
    font-size: 12px;
    spacing: 5px;
}
QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border-radius: 7px;
    border: 1px solid #475569;
    background-color: #1E293B;
}
QRadioButton::indicator:hover {
    border-color: #38BDF8;
}
QRadioButton::indicator:checked {
    background-color: #0284C7;
    border: 2px solid #38BDF8;
}
QPushButton:hover, QToolButton:hover {
    background-color: #2D3D54;
    border-color: #38BDF8;
    color: #FFFFFF;
}
QPushButton:pressed, QToolButton:pressed {
    background-color: #0B1120;
    border-color: #0284C7;
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
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 4px 22px 4px 8px;
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
QComboBox QAbstractItemView::item {
    min-height: 28px;
    padding: 3px 6px;
}
QToolTip {
    background-color: #0F172A;
    color: #F8FAFC;
    border: 1px solid #38BDF8;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}
QLineEdit {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 4px 8px;
    color: #F8FAFC;
    font-size: 12px;
}
QLineEdit:focus {
    border-color: #38BDF8;
    background-color: #0B1120;
}
QTabWidget::pane {
    border: 1px solid #1E293B;
    border-radius: 8px;
    background-color: #0B1120;
}
QTabBar::tab {
    background-color: #111827;
    color: #94A3B8;
    padding: 7px 16px;
    margin-right: 3px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border: 1px solid #1E293B;
    border-bottom: none;
    font-weight: bold;
    font-size: 12px;
}
QTabBar::tab:hover {
    background-color: #1E293B;
    color: #E2E8F0;
}
QTabBar::tab:selected {
    background-color: #1E293B;
    color: #38BDF8;
    border-top: 2px solid #38BDF8;
    border-left: 1px solid #334155;
    border-right: 1px solid #334155;
}
QTableWidget {
    background-color: #0B1120;
    gridline-color: #1E293B;
    border: none;
    selection-background-color: #0284C7;
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
    border-radius: 4px;
}
QScrollBar:vertical {
    border: none;
    background: #0F172A;
    width: 6px;
}
QScrollBar::handle:vertical {
    background: #334155;
    border-radius: 3px;
}
QScrollBar::handle:vertical:hover {
    background: #38BDF8;
}
QScrollBar:horizontal {
    border: none;
    background: #0F172A;
    height: 6px;
}
QScrollBar::handle:horizontal {
    background: #334155;
    border-radius: 3px;
}
QScrollBar::handle:horizontal:hover {
    background: #38BDF8;
}
QScrollArea {
    background: transparent;
    border: none;
}
QSplitter::handle {
    background-color: #1E293B;
}
QSplitter::handle:horizontal {
    width: 4px;
}
QSplitter::handle:vertical {
    height: 4px;
}
QSplitter::handle:hover {
    background-color: #38BDF8;
}
QStatusBar {
    background-color: #0B1120;
    border-top: 1px solid #1E293B;
    color: #94A3B8;
    font-size: 11px;
}
"""


class BleScanWorker(QThread):
    """后台异步扫描 BLE 蓝牙设备工作线程 (支持实时增量流式发现与智能分类)"""
    sig_device_discovered = pyqtSignal(dict)
    sig_found = pyqtSignal(list)
    sig_failed = pyqtSignal(str)

    def __init__(self, timeout: float = 2.5):
        super().__init__()
        self.timeout = timeout

    def run(self):
        try:
            from core.transport.ble_transport import BleTransport
            devices = BleTransport.scan_devices(
                timeout=self.timeout,
                callback=self.sig_device_discovered.emit
            )
            self.sig_found.emit(devices)
        except Exception as e:
            self.sig_failed.emit(str(e))


class IdCardReadWorker(QThread):
    """后台执行二代身份证读取，独占射频通道并避免阻塞 GUI 线程"""
    sig_result = pyqtSignal(object)
    sig_failed = pyqtSignal(str)

    def __init__(self, serial_worker, timeout: float = 0.45):
        super().__init__()
        self.serial_worker = serial_worker
        self.timeout = timeout

    def run(self):
        serial_worker = self.serial_worker
        try:
            # 射频半双工独占：暂停后台自动寻卡轮询，防止后台线程抢走 BLE/串口应答字节
            serial_worker.set_exclusive(True)
            try:
                card_info = serial_worker.read_id_card_once(timeout=self.timeout)
            finally:
                serial_worker.set_exclusive(False)
            self.sig_result.emit(card_info)
        except Exception as e:
            self.sig_failed.emit(str(e))


class SelectableTabBar(QTabBar):
    """支持完全取消激活选中态的 QTabBar (用于右上角独立 Tab 分组)"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_active = True
        self.setDrawBase(False)

    def paintEvent(self, ev):
        p = QStylePainter(self)
        for i in range(self.count()):
            opt = QStyleOptionTab()
            self.initStyleOption(opt, i)
            if not self.is_active:
                opt.state &= ~QStyle.StateFlag.State_Selected
            p.drawControl(QStyle.ControlElement.CE_TabBarTab, opt)


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
        self._id_read_worker = None
        self.current_uid = ""
        self._last_selected_ble_addr = ""
        self._ble_discovered_map = {}

        self._init_ui()
        self._init_signals()

        # 启动后扫描并列出可用串口 (由用户在下拉列表中选择并点击连接)
        QTimer.singleShot(200, self._refresh_ports)

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

        # 1. 设备串口 / 蓝牙连接卡片
        grp_conn = QGroupBox("🔌 硬件连接管理")
        grp_conn.setStyleSheet("QGroupBox { color: #38BDF8; font-size: 12px; }")
        lay_conn = QGridLayout(grp_conn)
        lay_conn.setContentsMargins(6, 6, 6, 6)
        lay_conn.setSpacing(4)

        # 模式切换: USB 串口 / 蓝牙 BLE
        mode_box = QHBoxLayout()
        mode_box.setContentsMargins(0, 0, 0, 0)
        mode_box.setSpacing(12)
        self.rb_conn_serial = QRadioButton("🔌 USB 串口")
        self.rb_conn_ble = QRadioButton("📶 蓝牙 BLE")
        self.rb_conn_serial.setChecked(True)
        self.btn_group_mode = QButtonGroup(self)
        self.btn_group_mode.addButton(self.rb_conn_serial, 0)
        self.btn_group_mode.addButton(self.rb_conn_ble, 1)
        self.btn_group_mode.idToggled.connect(self._on_conn_mode_changed)
        mode_box.addWidget(self.rb_conn_serial)
        mode_box.addWidget(self.rb_conn_ble)
        mode_box.addStretch()
        lay_conn.addLayout(mode_box, 0, 0, 1, 2)

        # 设备类型
        lay_conn.addWidget(QLabel("设备类型:"), 1, 0)
        self.combo_device = QComboBox()
        self.combo_device.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_device.setMinimumContentsLength(6)
        for title, dev_id in ReaderAdapterFactory.DEVICE_CHOICES:
            self.combo_device.addItem(title, dev_id)
        self.combo_device.currentIndexChanged.connect(self._on_device_type_changed)
        lay_conn.addWidget(self.combo_device, 1, 1)

        # 串口专属行: 串口号
        self.lbl_port = QLabel("串口号:")
        self.combo_port = QComboBox()
        self.combo_port.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_port.setMinimumContentsLength(6)
        self.btn_refresh_ports = QPushButton("🔄")
        self.btn_refresh_ports.setToolTip("刷新可用串口列表")
        self.btn_refresh_ports.setFixedWidth(28)
        self.btn_refresh_ports.clicked.connect(self._refresh_ports)
        self.w_port = QWidget()
        port_h = QHBoxLayout(self.w_port)
        port_h.setContentsMargins(0, 0, 0, 0)
        port_h.setSpacing(4)
        port_h.addWidget(self.combo_port, 1)
        port_h.addWidget(self.btn_refresh_ports, 0)

        lay_conn.addWidget(self.lbl_port, 2, 0)
        lay_conn.addWidget(self.w_port, 2, 1)

        # 串口专属行: 波特率
        self.lbl_baud = QLabel("波特率:")
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
        lay_conn.addWidget(self.lbl_baud, 3, 0)
        lay_conn.addWidget(self.combo_baud, 3, 1)

        # 蓝牙专属行: 蓝牙设备
        self.lbl_ble = QLabel("蓝牙设备:")
        self.combo_ble = QComboBox()
        self.combo_ble.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_ble.setMinimumContentsLength(6)
        # 弹层开阔视图：设为 560px 宽度，避免文字被省略号截断，全称、MAC与信号一目了然
        self.combo_ble.view().setMinimumWidth(560)
        self.combo_ble.addItem("请点击右侧 🔍 扫描附近蓝牙设备...", "")
        self.combo_ble.setToolTip("选择扫描到的 BLE 读卡器。提示: 本设备采用 BLE GATT 透明传输，无需在 Windows 系统设置中配对即可直连")
        self.combo_ble.currentIndexChanged.connect(self._on_combo_ble_index_changed)
        self.btn_refresh_ble = QPushButton("🔍")
        self.btn_refresh_ble.setToolTip("扫描附近 BLE 蓝牙低功耗设备 (免系统配对)")
        self.btn_refresh_ble.setFixedWidth(28)
        self.btn_refresh_ble.clicked.connect(self._scan_ble_devices)
        self.w_ble = QWidget()
        ble_h = QHBoxLayout(self.w_ble)
        ble_h.setContentsMargins(0, 0, 0, 0)
        ble_h.setSpacing(4)
        ble_h.addWidget(self.combo_ble, 1)
        ble_h.addWidget(self.btn_refresh_ble, 0)

        lay_conn.addWidget(self.lbl_ble, 4, 0)
        lay_conn.addWidget(self.w_ble, 4, 1)

        # 默认隐藏蓝牙控件
        self.lbl_ble.setVisible(False)
        self.w_ble.setVisible(False)

        # 按钮行
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

        lay_conn.addLayout(btn_h, 5, 0, 1, 2)

        self.lbl_status_led = QLabel("● 状态: 未连接")
        self.lbl_status_led.setStyleSheet("color: #EF4444; font-weight: bold; font-size: 11px;")
        lay_conn.addWidget(self.lbl_status_led, 6, 0, 1, 2)

        # 自动读卡开关与探测间隔调整
        auto_h = QHBoxLayout()
        auto_h.setContentsMargins(0, 0, 0, 0)
        auto_h.setSpacing(4)
        self.chk_auto_poll = QCheckBox("自动读卡")
        self.chk_auto_poll.setChecked(True)
        self.chk_auto_poll.setToolTip("开启后后台按设定间隔自动寻卡感应卡片 (默认开启)")
        auto_h.addWidget(self.chk_auto_poll)
        auto_h.addStretch(1)
        self.spin_poll_interval = QSpinBox()
        self.spin_poll_interval.setRange(50, 5000)
        self.spin_poll_interval.setSingleStep(50)
        self.spin_poll_interval.setValue(300)
        self.spin_poll_interval.setSuffix(" ms")
        self.spin_poll_interval.setToolTip("自动寻卡探测间隔 (默认 300ms)")
        auto_h.addWidget(self.spin_poll_interval)
        lay_conn.addLayout(auto_h, 7, 0, 1, 2)

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

        # 顶部 Tab 分页 (左侧：辅助管理工具；右上角 CornerWidget：两大核心射频卡交互靠最右侧对齐)
        self.tabs = QTabWidget()

        self.tab_diff = DumpDiffWidget()
        self.tab_manage = CardManageWidget(self.db)
        self.tab_tools = DictionaryToolsWidget()
        self.tab_sector = SectorTableWidget(serial_worker=self.worker)
        self.tab_sector.set_database(self.db)
        self.tab_cpu = CpuCardWidget(serial_worker=self.worker)

        # 左侧通用辅助标签页
        self.tabs.addTab(self.tab_diff, "🔍 Dump 对比")
        self.tabs.addTab(self.tab_manage, "📋 发卡管理")
        self.tabs.addTab(self.tab_tools, "🛠️ 字典工具")

        # 隐藏但挂载在 QTabWidget 内的核心卡页面 (保持完整的页面栈管理与统一生命周期)
        self.tabs.addTab(self.tab_sector, "📑 M1卡 (1K/4K)")
        self.tabs.addTab(self.tab_cpu, "💳 CPU卡交互")
        self.tabs.tabBar().setTabVisible(3, False)
        self.tabs.tabBar().setTabVisible(4, False)

        self.tabs.setTabToolTip(0, "Dump 差分对比器 (消费前后/双卡数据比对)")
        self.tabs.setTabToolTip(1, "发卡档案管理与实时刷卡流水审计")
        self.tabs.setTabToolTip(2, "密码字典库、Access Bits 权限解析器与调试终端")

        # 右侧核心射频卡交互栏 (靠最右侧对齐排列)
        self.right_tab_bar = SelectableTabBar()
        self.right_tab_bar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.right_tab_bar.addTab("📑 M1卡 (1K/4K)")
        self.right_tab_bar.addTab("💳 CPU卡交互")
        self.right_tab_bar.setTabToolTip(0, "Mifare Classic (1K/4K) 扇区数据矩阵、密钥破解与读写操作")
        self.right_tab_bar.setTabToolTip(1, "ISO/IEC 14443-4 CPU 智能卡、交通联合/金融卡余额流水读取与原生 APDU 调试")

        self.tabs.setCornerWidget(self.right_tab_bar, Qt.Corner.TopRightCorner)

        def _on_right_tab_clicked(idx):
            if idx == 0:
                self.tabs.setCurrentWidget(self.tab_sector)
            elif idx == 1:
                self.tabs.setCurrentWidget(self.tab_cpu)
            self.right_tab_bar.is_active = True
            self.right_tab_bar.update()

        self.right_tab_bar.tabBarClicked.connect(_on_right_tab_clicked)

        def _on_tab_changed(idx):
            if idx == self.tabs.indexOf(self.tab_sector):
                self.right_tab_bar.is_active = True
                self.right_tab_bar.setCurrentIndex(0)
            elif idx == self.tabs.indexOf(self.tab_cpu):
                self.right_tab_bar.is_active = True
                self.right_tab_bar.setCurrentIndex(1)
            else:
                self.right_tab_bar.is_active = False
            self.right_tab_bar.update()

        self.tabs.currentChanged.connect(_on_tab_changed)

        # 默认高亮并聚焦 M1 卡核心交互矩阵
        self.tabs.setCurrentWidget(self.tab_sector)

        splitter.addWidget(self.tabs)

        # 底部报文日志窗口
        self.log_box = QWidget()
        log_lay = QVBoxLayout(self.log_box)
        log_lay.setContentsMargins(0, 4, 0, 0)
        log_head = QHBoxLayout()
        lbl_log_t = QLabel("📡 串口原生数据流日志 (Hex Stream Monitor)")
        lbl_log_t.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: bold;")
        lbl_log_lvl = QLabel("级别:")
        lbl_log_lvl.setStyleSheet("color: #94A3B8; font-size: 11px;")
        self.combo_log_level = QComboBox()
        self.combo_log_level.setFixedHeight(22)
        self.combo_log_level.setStyleSheet("font-size: 11px; padding: 1px 4px;")
        self.combo_log_level.addItem("常规 (INFO)", False)
        self.combo_log_level.addItem("调试 (DEBUG)", True)
        self.combo_log_level.setToolTip("调试级别会打印最详细的 TX/RX 原始报文交互，性能开销较高")
        btn_clear_log = QPushButton("清空日志")
        btn_clear_log.setFixedSize(65, 22)
        btn_clear_log.setStyleSheet("font-size: 11px; padding: 2px;")
        btn_clear_log.clicked.connect(lambda: self.txt_log.clear())

        btn_export_log = QPushButton("💾 导出日志")
        btn_export_log.setFixedSize(75, 22)
        btn_export_log.setStyleSheet("font-size: 11px; padding: 2px;")
        btn_export_log.setToolTip("将当前原生数据流日志导出保存为 UTF-8 编码的 TXT 文件")
        btn_export_log.clicked.connect(self._export_log_file)

        log_head.addWidget(lbl_log_t)
        log_head.addStretch()
        log_head.addWidget(lbl_log_lvl)
        log_head.addWidget(self.combo_log_level)
        log_head.addWidget(btn_clear_log)
        log_head.addWidget(btn_export_log)
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
        self.tab_tools.sig_load_dump_file.connect(self._on_load_dump_from_tools)
        self.tab_tools.sig_key_recovered.connect(self._on_key_recovered_from_tools)

        # 绑定扇区表格通知至状态栏与日志
        self.tab_sector.sig_notify.connect(self._on_sector_table_notify)

        # 绑定自动读卡开关与探测间隔调整
        self.chk_auto_poll.toggled.connect(self._on_auto_poll_toggled)
        self.spin_poll_interval.valueChanged.connect(self._on_poll_interval_changed)
        self.worker.set_auto_poll(self.chk_auto_poll.isChecked())
        self.worker.set_poll_interval(self.spin_poll_interval.value())

        # 绑定日志级别过滤 (仅 DEBUG 打印详细 TX/RX 报文)
        self.combo_log_level.currentIndexChanged.connect(self._on_log_level_changed)
        self.worker.set_debug_logging(self.combo_log_level.currentData())

    def _on_log_level_changed(self, idx: int):
        debug = bool(self.combo_log_level.currentData())
        self.worker.set_debug_logging(debug)
        self.status_bar.showMessage(f"日志级别: {'调试 (DEBUG，含原始报文)' if debug else '常规 (INFO)'}")

    def _on_auto_poll_toggled(self, checked: bool):
        self.worker.set_auto_poll(checked)
        self.status_bar.showMessage(f"自动读卡: {'已开启' if checked else '已关闭'}")

    def _on_poll_interval_changed(self, value: int):
        self.worker.set_poll_interval(value)
        self.status_bar.showMessage(f"自动读卡探测间隔: {value} ms")

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

    def _on_conn_mode_changed(self, btn_id: int, checked: bool):
        if not checked:
            return
        is_ble = (btn_id == 1)
        self.lbl_port.setVisible(not is_ble)
        self.w_port.setVisible(not is_ble)
        self.lbl_baud.setVisible(not is_ble)
        self.combo_baud.setVisible(not is_ble)

        self.lbl_ble.setVisible(is_ble)
        self.w_ble.setVisible(is_ble)

        if is_ble:
            # 蓝牙模式默认选择 PCR532/PN532 全功能
            for i in range(self.combo_device.count()):
                if self.combo_device.itemData(i) == ReaderAdapterFactory.DEVICE_PN532:
                    self.combo_device.setCurrentIndex(i)
                    break
            if not self.combo_ble.currentData():
                self.status_bar.showMessage("已切换至蓝牙 BLE 模式，请点击 🔍 扫描附近的读卡器设备（免系统配对）")
        else:
            self.status_bar.showMessage("已切换至 USB 串口模式，请在下拉框选择串口号")

    def _on_combo_ble_index_changed(self, index: int):
        if index < 0 or self.combo_ble.count() == 0:
            return
        tip = self.combo_ble.itemData(index, Qt.ItemDataRole.ToolTipRole)
        if tip:
            self.combo_ble.setToolTip(tip)

    def _scan_ble_devices(self):
        self.btn_refresh_ble.setEnabled(False)
        self.btn_refresh_ble.setText("⏳")
        self.status_bar.showMessage("正在实时流式扫描周围 BLE 蓝牙设备 (约需 2.5 秒)...")

        # 记录上一次选中的设备地址
        self._last_selected_ble_addr = self.combo_ble.currentData() or ""
        self._ble_discovered_map = {}

        self.combo_ble.clear()
        self.combo_ble.addItem("⏳ 正在实时扫描周围蓝牙设备...", "")

        self._ble_scan_worker = BleScanWorker(timeout=2.5)
        self._ble_scan_worker.sig_device_discovered.connect(self._on_ble_device_discovered)
        self._ble_scan_worker.sig_found.connect(self._on_ble_scan_found)
        self._ble_scan_worker.sig_failed.connect(self._on_ble_scan_failed)
        self._ble_scan_worker.start()

    def _on_ble_device_discovered(self, dev: dict):
        addr = dev.get("address")
        if not addr:
            return

        self._ble_discovered_map[addr] = dev

        # 首次发现有效设备时，清除占位项
        if len(self._ble_discovered_map) == 1 and self.combo_ble.count() > 0:
            if not self.combo_ble.itemData(0):
                self.combo_ble.clear()

        display = dev.get("display_text") or f"{dev.get('name')} [{addr}]"
        tooltip = dev.get("tooltip") or display

        # 检查是否已在当前下拉列表中
        existing_idx = -1
        for i in range(self.combo_ble.count()):
            if self.combo_ble.itemData(i) == addr:
                existing_idx = i
                break

        if existing_idx >= 0:
            self.combo_ble.setItemText(existing_idx, display)
            self.combo_ble.setItemData(existing_idx, tooltip, Qt.ItemDataRole.ToolTipRole)
        else:
            priority = dev.get("priority", 99)
            insert_idx = self.combo_ble.count()
            for i in range(self.combo_ble.count()):
                other_addr = self.combo_ble.itemData(i)
                other_dev = self._ble_discovered_map.get(other_addr, {})
                if priority < other_dev.get("priority", 99):
                    insert_idx = i
                    break
            self.combo_ble.insertItem(insert_idx, display, addr)
            self.combo_ble.setItemData(insert_idx, tooltip, Qt.ItemDataRole.ToolTipRole)

            # 优先自动聚焦目标读卡器或此前选中的设备
            if dev.get("is_reader"):
                self.combo_ble.setCurrentIndex(insert_idx)
                self.status_bar.showMessage(f"🎯 已发现 NFC 读卡器: {dev.get('name')}，继续流式扫描中...")
            elif self._last_selected_ble_addr and addr.upper() == self._last_selected_ble_addr.upper():
                self.combo_ble.setCurrentIndex(insert_idx)

        total_cnt = len(self._ble_discovered_map)
        if not dev.get("is_reader"):
            self.status_bar.showMessage(f"正在实时扫描中... 已捕获 {total_cnt} 个附近低功耗设备")

    def _on_ble_scan_found(self, devices: list):
        self.btn_refresh_ble.setEnabled(True)
        self.btn_refresh_ble.setText("🔍")

        if not devices:
            self.combo_ble.clear()
            self.combo_ble.addItem("未发现附近 BLE 读卡器 (请靠近后点击 🔍 重试)", "")
            self.combo_ble.setToolTip("未发现附近的低功耗蓝牙设备")
            self.status_bar.showMessage("BLE 扫描完成：未发现附近的低功耗蓝牙设备")
            return

        current_selected_addr = self.combo_ble.currentData() or self._last_selected_ble_addr
        self.combo_ble.clear()

        best_index = 0
        reader_count = 0
        from core.transport.ble_classifier import BleClassifier

        for dev in devices:
            if isinstance(dev, dict):
                addr = dev.get("address", "")
                if "display_text" not in dev:
                    classified = BleClassifier.classify(
                        name=dev.get("name", ""),
                        address=addr,
                        rssi=dev.get("rssi"),
                        service_uuids=dev.get("service_uuids", []),
                        manufacturer_data=dev.get("manufacturer_data", {}),
                    )
                    display = classified["display_text"]
                    tooltip = classified["tooltip"]
                    is_reader = classified["is_reader"]
                else:
                    display = dev.get("display_text") or f"{dev.get('name')} [{addr}]"
                    tooltip = dev.get("tooltip") or display
                    is_reader = dev.get("is_reader", False)
            elif isinstance(dev, (list, tuple)):
                addr = dev[1] if len(dev) > 1 else ""
                classified = BleClassifier.classify(
                    name=dev[0] if len(dev) > 0 else "",
                    address=addr,
                    rssi=dev[2] if len(dev) > 2 else None,
                )
                display = classified["display_text"]
                tooltip = classified["tooltip"]
                is_reader = classified["is_reader"]
            else:
                continue

            if not addr:
                continue

            idx = self.combo_ble.count()
            if is_reader:
                reader_count += 1

            self.combo_ble.addItem(display, addr)
            self.combo_ble.setItemData(idx, tooltip, Qt.ItemDataRole.ToolTipRole)

            if current_selected_addr and addr.upper() == current_selected_addr.upper():
                best_index = idx
            elif is_reader and best_index == 0:
                best_index = idx

        if self.combo_ble.count() > 0:
            self.combo_ble.setCurrentIndex(best_index)
            # 同步更新 combo_ble 自身 ToolTip
            current_tip = self.combo_ble.itemData(best_index, Qt.ItemDataRole.ToolTipRole)
            if current_tip:
                self.combo_ble.setToolTip(current_tip)

            reader_hint = f"（含 {reader_count} 台读卡器）" if reader_count > 0 else "（未发现读卡器）"
            self.status_bar.showMessage(
                f"BLE 扫描完成，共捕获 {self.combo_ble.count()} 个附近设备 {reader_hint}，免配对直连"
            )
        else:
            self.combo_ble.addItem("未发现附近 BLE 读卡器 (请靠近后点击 🔍 重试)", "")
            self.combo_ble.setToolTip("未发现有效设备")
            self.status_bar.showMessage("BLE 扫描完成：未发现有效设备")

    def _on_ble_scan_failed(self, err: str):
        self.btn_refresh_ble.setEnabled(True)
        self.btn_refresh_ble.setText("🔍")
        self.status_bar.showMessage(f"BLE 扫描失败: {err}")

    def _refresh_ports(self):
        self.combo_port.clear()
        ports = serial.tools.list_ports.comports()
        if not ports:
            self.combo_port.addItem("未检测到可用串口 (请插入后点击 🔄)", "")
            self.status_bar.showMessage("未检测到可用 USB 串口设备，请插入读卡器后点击 🔄 刷新")
            return

        for p in ports:
            desc = p.description or "未知串口设备"
            self.combo_port.addItem(f"{p.device} ({desc})", p.device)

        self.combo_port.setCurrentIndex(0)
        self.status_bar.showMessage(f"已扫描到 {len(ports)} 个可用串口，请从下拉框中选择")

    def _toggle_connection(self):
        if self.worker.isRunning():
            self.worker.stop()
            self.btn_connect.setText("连接读卡器")
            self.btn_connect.setStyleSheet("background-color: #0284C7; font-weight: bold; padding: 5px 4px;")
            self.lbl_status_led.setText("● 状态: 已断开")
            self.lbl_status_led.setStyleSheet("color: #EF4444; font-weight: bold; font-size: 11px;")
        else:
            is_ble = self.rb_conn_ble.isChecked()
            device_type = self.combo_device.currentData() or ReaderAdapterFactory.DEVICE_AUTO

            if is_ble:
                addr = self.combo_ble.currentData()
                if not addr:
                    raw_text = self.combo_ble.currentText().strip()
                    if "[" in raw_text and "]" in raw_text:
                        addr = raw_text.split("[")[1].split("]")[0].strip()
                    elif "(" in raw_text and ")" in raw_text:
                        addr = raw_text.split("(")[1].split(")")[0].strip()
                if not addr:
                    QMessageBox.warning(
                        self, "未选择蓝牙设备",
                        "未选择有效的蓝牙读卡器设备！\n\n"
                        "1. 请点击右侧 🔍 扫描按钮发现附近的 BLE 读卡器；\n"
                        "2. 从下拉框中选择扫描出来的设备（例如 Minicopy(BLE)）；\n\n"
                        "💡 说明：本读卡器使用 BLE GATT 直连协议，无需在 Windows 系统设置中手动配对即可使用。"
                    )
                    return
                if device_type == ReaderAdapterFactory.DEVICE_AUTO:
                    device_type = ReaderAdapterFactory.DEVICE_PN532
                self.worker.set_ble_connection(addr, device_type=device_type)
            else:
                port = self.combo_port.currentData()
                if not port:
                    QMessageBox.warning(
                        self, "未检测到串口",
                        "未检测到可用串口设备！\n\n"
                        "请先将读卡器 USB 数据线插入电脑，然后点击右侧 🔄 刷新按钮，并在下拉列表中选择对应的 COM 端口。"
                    )
                    return
                baud_text = self.combo_baud.currentText()
                baud = int(baud_text.split()[0])
                self.worker.set_connection(port, baud, device_type=device_type)

            self.tab_sector.set_serial_worker(self.worker)
            self.worker.start()

    @pyqtSlot(str, int)
    def _on_connected(self, port, baud):
        self.btn_connect.setText("断开连接")
        self.btn_connect.setStyleSheet("background-color: #DC2626; font-weight: bold; padding: 5px 4px;")
        if baud == 0 or "BLE:" in port or getattr(self.worker, "conn_type", "serial") == "ble":
            self.lbl_status_led.setText(f"● 已在线 ({port})")
            self.lbl_status_led.setStyleSheet("color: #10B981; font-weight: bold; font-size: 11px;")
            self.status_bar.showMessage(f"已连接低功耗蓝牙(BLE): {port}，正在侦听/握手...")
        else:
            self.lbl_status_led.setText(f"● 已在线 ({port} @ {baud})")
            self.lbl_status_led.setStyleSheet("color: #10B981; font-weight: bold; font-size: 11px;")
            self.status_bar.showMessage(f"已连接硬件串口: {port} @ {baud} bps，正在侦听/握手...")

    @pyqtSlot(str)
    def _on_disconnected(self, reason):
        self.btn_connect.setText("连接读卡器")
        self.btn_connect.setStyleSheet("background-color: #0284C7; font-weight: bold; padding: 5px 4px;")
        self.lbl_status_led.setText("● 状态: 未连接")
        self.lbl_status_led.setStyleSheet("color: #EF4444; font-weight: bold; font-size: 11px;")
        self.status_bar.showMessage(f"断开: {reason}")

    @pyqtSlot(str, str)
    def _on_device_identified(self, dev_name: str, fw_ver: str):
        self.lbl_status_led.setText(f"● 已识别: {dev_name}")
        self.lbl_status_led.setStyleSheet("color: #10B981; font-weight: bold; font-size: 11px;")
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
        is_cpu_card = frame_info.get("is_cpu_card", False)

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
        elif is_cpu_card:
            card_desc = frame_info.get("card_type", "ISO 14443-4 CPU 卡")
            self.lbl_card_badge.setText(f"💳 成功识别 {card_desc}")
            self.lbl_card_badge.setStyleSheet(
                "background-color: #0E7490; color: #67E8F9; border-radius: 6px; padding: 6px; font-weight: bold;"
            )
            self.lbl_hero_uid.setText(self.current_uid)
            self.lbl_hero_uid.setStyleSheet(
                "font-size: 24px; font-family: Consolas; font-weight: bold; color: #67E8F9; padding: 10px;"
                "background-color: #0B1120; border: 2px solid #06B6D4; border-radius: 8px;"
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

        # 2. 自动同步至数据矩阵 0 块与 CPU 卡交互面板
        self.tab_sector.update_uid(uid_bytes)
        if hasattr(self, "tab_cpu"):
            self.tab_cpu.update_card_badge(frame_info)

        # 3. 自动记录数据库流水
        card_info = self.db.record_swipe(self.current_uid, conv, raw_hex)
        self.tab_manage.refresh_cards()
        self.tab_manage.refresh_logs()

        if is_id_card:
            self.status_bar.showMessage(f"🪪 捕获二代身份证 UID: [{self.current_uid}] (8字节 GUID)")
        elif is_cpu_card:
            self.status_bar.showMessage(
                f"💳 捕获 CPU 智能卡: UID=[{self.current_uid}] (可点击【💳 CPU卡交互】标签页读取应用内容/执行APDU)"
            )
        else:
            self.status_bar.showMessage(
                f"🎯 捕获新卡片: UID=[{self.current_uid}] | 累计刷卡: {card_info.get('swipe_count')} 次"
            )

    def _on_read_id_card_clicked(self):
        """手动单次触发读取二代身份证 UID"""
        if not self.worker.isRunning() or not self.worker.is_connected():
            QMessageBox.warning(self, "设备未连接", "请先连接 PCR532 / PN532 读卡器！")
            return
        if self._id_read_worker is not None and self._id_read_worker.isRunning():
            return

        self.btn_read_id_card.setEnabled(False)
        self.btn_read_id_card.setText("读取中...")
        self.status_bar.showMessage("正在调谐 Type B CIU 射频并读取二代身份证 UID...")

        self._id_read_worker = IdCardReadWorker(self.worker, timeout=0.45)
        self._id_read_worker.sig_result.connect(self._on_id_card_read_result)
        self._id_read_worker.sig_failed.connect(self._on_id_card_read_failed)
        self._id_read_worker.finished.connect(self._on_id_card_read_finished)
        self._id_read_worker.start()

    def _restore_id_card_button(self):
        self.btn_read_id_card.setEnabled(True)
        self.btn_read_id_card.setText("🪪 读身份证")

    @pyqtSlot(object)
    def _on_id_card_read_result(self, card_info):
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
            self.status_bar.showMessage(f"🪪 身份证读取成功: {uid_hex}")
        else:
            detail = getattr(self.worker.adapter, "last_id_error", "") or "未收到卡片响应"
            self.status_bar.showMessage(f"未检测到二代身份证: {detail}")
            QMessageBox.warning(
                self, "未感应到身份证",
                "未检测到二代身份证！\n"
                "请将二代居民身份证贴紧读卡器天线感应区后重试。\n\n"
                f"诊断信息: {detail}"
            )

    @pyqtSlot(str)
    def _on_id_card_read_failed(self, err: str):
        self.status_bar.showMessage(f"身份证读取异常: {err}")
        QMessageBox.warning(
            self, "读取异常",
            f"读取二代身份证时发生通信异常：\n{err}\n\n"
            "请检查读卡器连接后重试。"
        )

    @pyqtSlot()
    def _on_id_card_read_finished(self):
        self._restore_id_card_button()

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
    def _on_load_dump_from_tools(self, path: str):
        if self.tab_sector.load_dump_from_path(path):
            self.tabs.setCurrentWidget(self.tab_sector)
            self.status_bar.showMessage(f"已从外部破解工具链载入 Dump: {path}")

    @pyqtSlot(int, str, str)
    def _on_key_recovered_from_tools(self, sector: int, key_type: str, key_hex: str):
        ka = key_hex if key_type.upper() == "A" else ""
        kb = key_hex if key_type.upper() == "B" else ""
        self.tab_sector._persist_sector_keys(sector, ka, kb)
        self.status_bar.showMessage(f"已捕获并保存扇区 S{sector:02d} Key {key_type}: {key_hex}")

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

    def _export_log_file(self):
        """将当前串口原生数据流日志导出保存为 UTF-8 编码文本文件"""
        content = self.txt_log.toPlainText().strip()
        if not content:
            QMessageBox.information(self, "提示", "当前原生数据流日志为空，无需导出。")
            return

        default_name = f"PyMifareTool_SerialLog_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出串口原生数据流日志",
            default_name,
            "文本文件 (*.txt);;所有文件 (*.*)",
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            self.status_bar.showMessage(f"✅ 日志已成功导出至: {file_path}", 6000)
            QMessageBox.information(self, "导出成功", f"日志文件已成功保存为 UTF-8 编码：\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"写入日志文件时发生异常：\n{e}")

    @staticmethod
    def _stop_thread(thread, wait_ms: int):
        if not thread or not thread.isRunning():
            return
        thread.wait(wait_ms)
        if thread.isRunning():
            thread.terminate()
            thread.wait(1000)

    def closeEvent(self, event):
        if hasattr(self, "_ble_scan_worker"):
            self._stop_thread(self._ble_scan_worker, 500)

        if getattr(self, "_id_read_worker", None):
            self._stop_thread(self._id_read_worker, 1500)

        if hasattr(self, "tab_sector") and self.tab_sector.card_op_worker:
            card_worker = self.tab_sector.card_op_worker
            if card_worker.isRunning():
                card_worker.abort()
            self._stop_thread(card_worker, 1000)

        worker = getattr(self, "worker", None)
        if worker:
            try:
                worker.stop()
            except Exception:
                pass
            self._stop_thread(worker, 1000)

        try:
            if hasattr(self, "db"):
                self.db.close()
        except Exception:
            pass

        event.accept()
