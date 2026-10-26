# -*- coding: utf-8 -*-
"""
PyMifareTool - 读卡器设备能力提示对话框
连接成功后展示设备固件、可用功能、外部 Crypto1 工具链与硬件限制。
"""

from typing import Any, Dict

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

DIALOG_STYLESHEET = """
QDialog {
    background-color: #0F172A;
    color: #F8FAFC;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
}
QLabel {
    color: #E2E8F0;
}
QTableWidget {
    background-color: #0B1120;
    alternate-background-color: #111C30;
    color: #F8FAFC;
    border: 1px solid #334155;
    border-radius: 6px;
    gridline-color: #1E293B;
    selection-background-color: #1E293B;
}
QHeaderView::section {
    background-color: #1E293B;
    color: #38BDF8;
    border: none;
    border-right: 1px solid #334155;
    border-bottom: 1px solid #334155;
    padding: 5px;
    font-weight: bold;
}
QCheckBox {
    color: #94A3B8;
    font-size: 11px;
}
QPushButton {
    background-color: #0284C7;
    border: 1px solid #38BDF8;
    border-radius: 6px;
    color: #FFFFFF;
    font-weight: bold;
    padding: 6px 18px;
}
QPushButton:hover {
    background-color: #0EA5E9;
}
"""

STATUS_STYLE = {
    "supported": ("✅ 支持", "#10B981"),
    "needs_card": ("⚠️ 需贴卡", "#F59E0B"),
    "external": ("🧪 需外部工具", "#38BDF8"),
    "experimental": ("🧪 实验性", "#A78BFA"),
    "unsupported": ("❌ 不支持", "#EF4444"),
}

TOOL_LABELS = [
    ("mfoc", "mfoc nested"),
    ("mfcuk", "mfcuk darkside"),
    ("libnfc_hardnested", "libnfc_hardnested"),
    ("mfdetect", "mfdetect"),
    ("nfc_list", "nfc-list"),
    ("libnfc_dll", "libnfc.dll"),
]


class DeviceCapabilitiesDialog(QDialog):
    def __init__(self, capabilities: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.capabilities = capabilities or {}
        self.setWindowTitle("读卡器设备能力与功能特性")
        self.setStyleSheet(DIALOG_STYLESHEET)
        self.setMinimumSize(720, 560)
        self.resize(780, 620)
        self._init_ui()

    def _init_ui(self):
        caps = self.capabilities
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(8)

        title = QLabel("🧪 读卡器能力与功能特性")
        title_font = QFont()
        title_font.setPointSize(15)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #38BDF8;")
        layout.addWidget(title)

        device_name = caps.get("device_name", "未知设备")
        firmware = caps.get("firmware_info", "未知固件")
        device_label = QLabel(f"{device_name}")
        device_font = QFont()
        device_font.setPointSize(11)
        device_font.setBold(True)
        device_label.setFont(device_font)
        device_label.setStyleSheet("color: #F8FAFC;")
        layout.addWidget(device_label)

        connection = caps.get("connection", "serial")
        port = caps.get("port", "") or "未知端口"
        baudrate = int(caps.get("baudrate", 0) or 0)
        conn_text = "BLE 蓝牙" if connection == "ble" else "USB 串口"
        speed_text = f" @ {baudrate} bps" if baudrate else ""
        info_label = QLabel(f"🔌 {conn_text}: {port}{speed_text}    |    🏷️ 固件/协议: {firmware}")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #94A3B8; font-size: 11px;")
        layout.addWidget(info_label)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #334155;")
        layout.addWidget(line)

        feature_title = QLabel("功能特性")
        feature_title.setStyleSheet("color: #38BDF8; font-weight: bold; font-size: 12px;")
        layout.addWidget(feature_title)

        features = caps.get("features", [])
        table = QTableWidget(len(features), 3)
        table.setHorizontalHeaderLabels(["功能", "状态", "说明"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setAlternatingRowColors(True)
        table.setWordWrap(True)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        for row, feature in enumerate(features):
            name_item = QTableWidgetItem(str(feature.get("name", "")))
            name_item.setForeground(QColor("#F8FAFC"))
            status_key = str(feature.get("status", "unsupported"))
            status_text, status_color = STATUS_STYLE.get(status_key, ("❓ 未知", "#94A3B8"))
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(QColor(status_color))
            status_font = QFont()
            status_font.setBold(True)
            status_item.setFont(status_font)
            detail_item = QTableWidgetItem(str(feature.get("detail", "")))
            detail_item.setForeground(QColor("#CBD5E1"))
            table.setItem(row, 0, name_item)
            table.setItem(row, 1, status_item)
            table.setItem(row, 2, detail_item)

        table.resizeRowsToContents()
        table.setMinimumHeight(min(320, max(150, len(features) * 32 + 36)))
        layout.addWidget(table, 1)

        tools_title = QLabel("🧰 外部 Crypto1 工具链 (tools/m1t/nfc-bin)")
        tools_title.setStyleSheet("color: #38BDF8; font-weight: bold; font-size: 12px;")
        layout.addWidget(tools_title)

        tools = caps.get("tools", {})
        tools_frame = QFrame()
        tools_frame.setStyleSheet("QFrame { background-color: #0B1120; border: 1px solid #334155; border-radius: 6px; }")
        tools_layout = QGridLayout(tools_frame)
        tools_layout.setContentsMargins(10, 8, 10, 8)
        tools_layout.setHorizontalSpacing(18)
        tools_layout.setVerticalSpacing(4)
        for index, (key, label) in enumerate(TOOL_LABELS):
            available = bool(tools.get(key, False))
            text = f"{'✅' if available else '❌'} {label}"
            tool_label = QLabel(text)
            tool_label.setStyleSheet(f"color: {'#10B981' if available else '#94A3B8'}; font-size: 11px;")
            tools_layout.addWidget(tool_label, index // 3, index % 3)
        layout.addWidget(tools_frame)

        notes = caps.get("notes", [])
        if notes:
            notes_label = QLabel("\n".join(f"• {note}" for note in notes))
            notes_label.setWordWrap(True)
            notes_label.setStyleSheet(
                "color: #FBBF24; background-color: #1C1917; border: 1px solid #78350F; "
                "border-radius: 6px; padding: 7px; font-size: 11px;"
            )
            layout.addWidget(notes_label)

        footer = QHBoxLayout()
        self.chk_dont_show = QCheckBox("下次连接不再自动显示此提示")
        footer.addWidget(self.chk_dont_show)
        footer.addStretch(1)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)
        layout.addLayout(footer)

    def should_show_next_time(self) -> bool:
        return not self.chk_dont_show.isChecked()
