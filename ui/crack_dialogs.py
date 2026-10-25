# -*- coding: utf-8 -*-
"""
PyMifareTool - 字典破解范围选择 & 手动密钥解密对话框
- SectorScopeDialog: 选择参与字典破解的扇区 (默认勾选全部被加密/未解密的扇区)
- ManualKeyDialog:   在数据解析器中手动输入密钥对指定块/扇区进行测试解密
"""

from typing import List, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QLineEdit,
    QMessageBox, QAbstractItemView
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from core.dump_model import MifareDump, BlockState


_TABLE_QSS = (
    "QTableWidget { background-color: #0B1120; gridline-color: #1E293B; "
    "border: 1px solid #334155; color: #E2E8F0; } "
    "QHeaderView::section { background-color: #1E293B; color: #94A3B8; "
    "font-weight: bold; padding: 4px; border: none; }"
)


class SectorScopeDialog(QDialog):
    """字典破解范围选择对话框 (默认选中全部被加密扇区)"""

    def __init__(self, parent=None, dump: Optional[MifareDump] = None):
        super().__init__(parent)
        self.dump = dump if dump is not None else MifareDump()
        self.setWindowTitle("选择待破解扇区")
        self.setMinimumSize(560, 520)
        self.resize(560, 560)
        self._row_sector: List[int] = []
        self._default_checked: List[bool] = []
        self._init_ui()
        self._populate()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        banner = QFrame()
        banner.setStyleSheet("QFrame { background-color: #1E293B; border-radius: 6px; }")
        b_lay = QVBoxLayout(banner)
        b_lay.setContentsMargins(12, 10, 12, 10)
        b_lay.setSpacing(4)
        lbl_t = QLabel("🎯 选择参与字典破解的扇区")
        lbl_t.setStyleSheet("font-size: 10pt; font-weight: bold; color: #38BDF8;")
        lbl_s = QLabel("默认仅勾选被加密/未成功解密的扇区；已可读的扇区无需重复破解。")
        lbl_s.setStyleSheet("color: #94A3B8; font-size: 11px;")
        b_lay.addWidget(lbl_t)
        b_lay.addWidget(lbl_s)
        lay.addWidget(banner)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["勾选", "扇区", "块范围", "状态", "说明"])
        self.table.setStyleSheet(_TABLE_QSS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(self._on_item_changed)
        lay.addWidget(self.table, 1)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setStyleSheet("color: #7DD3FC; font-size: 11px;")
        lay.addWidget(self.lbl_summary)

        opt_h = QHBoxLayout()
        opt_h.setSpacing(6)
        btn_all = QPushButton("全选")
        btn_none = QPushButton("全不选")
        btn_enc = QPushButton("仅选加密")
        for b in (btn_all, btn_none, btn_enc):
            b.setFixedWidth(70)
        btn_all.clicked.connect(lambda: self._set_all(True))
        btn_none.clicked.connect(lambda: self._set_all(False))
        btn_enc.clicked.connect(self._select_encrypted)
        opt_h.addWidget(btn_all)
        opt_h.addWidget(btn_none)
        opt_h.addWidget(btn_enc)
        opt_h.addStretch(1)
        lay.addLayout(opt_h)

        foot = QHBoxLayout()
        foot.addStretch(1)
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedWidth(80)
        btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QPushButton("开始破解所选扇区")
        self.btn_ok.setStyleSheet("background-color: #0284C7; font-weight: bold; color: #FFFFFF; padding: 6px 14px;")
        self.btn_ok.clicked.connect(self._on_accept)
        foot.addWidget(btn_cancel)
        foot.addWidget(self.btn_ok)
        lay.addLayout(foot)

    def _sector_status(self, sector: int):
        first = sector * 4
        states = [self.dump.get_block_state(b) for b in range(first, first + 4)]
        ok = sum(1 for s in states if s == BlockState.READ_OK)
        if ok == 4:
            return "已解密可读", "#10B981", True
        if ok == 0:
            return "加密/未读取", "#F59E0B", False
        return f"部分可读 ({ok}/4)", "#FBBF24", False

    def _populate(self):
        self.table.setRowCount(0)
        self._row_sector.clear()
        self._default_checked.clear()
        sector_count = getattr(self.dump, "sector_count", 16)
        self.table.setRowCount(sector_count)
        for sector in range(sector_count):
            text, color, readable = self._sector_status(sector)
            first = sector * 4
            block_range = f"{first}-{first + 3}"
            self._row_sector.append(sector)
            self._default_checked.append(not readable)
            self._make_item(sector, 1, f"S{sector:02d}", "#38BDF8")
            self._make_item(sector, 2, block_range, "#E2E8F0")
            self._make_item(sector, 3, text, color)
            note = "已可读，无需破解" if readable else "需要密钥，参与字典破解"
            self._make_item(sector, 4, note, "#94A3B8")
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Checked if not readable else Qt.CheckState.Unchecked)
            self.table.setItem(sector, 0, chk)
        self._update_summary()

    def _make_item(self, row: int, col: int, text: str, color: str):
        it = QTableWidgetItem(text)
        it.setForeground(QColor(color))
        self.table.setItem(row, col, it)

    def _set_all(self, checked: bool):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it:
                it.setCheckState(state)
        self.table.blockSignals(False)
        self._update_summary()

    def _select_encrypted(self):
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it:
                it.setCheckState(Qt.CheckState.Checked if self._default_checked[r] else Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self._update_summary()

    def _on_item_changed(self, _item):
        self._update_summary()

    def _update_summary(self):
        selected = self.get_selected_sectors()
        self.lbl_summary.setText(f"已勾选 {len(selected)} / {self.table.rowCount()} 个扇区参与破解")
        self.btn_ok.setEnabled(bool(selected))

    def get_selected_sectors(self) -> List[int]:
        result = []
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it and it.checkState() == Qt.CheckState.Checked:
                result.append(self._row_sector[r])
        return result

    def _on_accept(self):
        if not self.get_selected_sectors():
            QMessageBox.warning(self, "未选择扇区", "请至少勾选一个待破解的扇区！")
            return
        self.accept()


class ManualKeyDialog(QDialog):
    """手动输入密钥进行测试解密"""

    def __init__(self, parent=None, block_idx: int = 0, sector: int = 0, suggestion_a: str = "", suggestion_b: str = ""):
        super().__init__(parent)
        self.block_idx = block_idx
        self.sector = sector
        self._sugg_a = suggestion_a or ""
        self._sugg_b = suggestion_b or ""
        self.setWindowTitle("手动密钥测试解密")
        self.setMinimumWidth(420)
        self._init_ui()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        banner = QFrame()
        banner.setStyleSheet("QFrame { background-color: #1E293B; border-radius: 6px; }")
        b_lay = QVBoxLayout(banner)
        b_lay.setContentsMargins(12, 10, 12, 10)
        b_lay.setSpacing(4)
        lbl_t = QLabel("🔑 手动输入密钥解密")
        lbl_t.setStyleSheet("font-size: 10pt; font-weight: bold; color: #38BDF8;")
        lbl_s = QLabel(f"将对扇区 S{self.sector:02d} (块 {self.block_idx:02d}) 进行一次认证测试，"
                       f"成功则读取该扇区 4 个数据块。")
        lbl_s.setStyleSheet("color: #94A3B8; font-size: 11px;")
        lbl_s.setWordWrap(True)
        b_lay.addWidget(lbl_t)
        b_lay.addWidget(lbl_s)
        lay.addWidget(banner)

        form = QHBoxLayout()
        form.setSpacing(6)
        form.addWidget(QLabel("密钥类型:"))
        self.combo_type = QComboBox()
        self.combo_type.addItem("Key A", "A")
        self.combo_type.addItem("Key B", "B")
        form.addWidget(self.combo_type)
        lay.addLayout(form)

        key_h = QHBoxLayout()
        key_h.setSpacing(6)
        key_h.addWidget(QLabel("密钥 (12位HEX):"))
        self.edit_key = QLineEdit()
        self.edit_key.setPlaceholderText("例如 FFFFFFFFFFFF")
        # 允许输入带空格的 6 组字节 (如 "AA BB CC DD EE FF"), 解析时统一去空格
        self.edit_key.setMaxLength(17)
        self.edit_key.setStyleSheet(
            "QLineEdit { background-color: #0B1120; color: #38BDF8; border: 1px solid #334155; "
            "padding: 5px; font-family: Consolas; font-size: 14px; letter-spacing: 1px; }")
        key_h.addWidget(self.edit_key, 1)
        lay.addLayout(key_h)

        if self._sugg_a:
            self.combo_type.setCurrentIndex(0)
            self.edit_key.setText(self._sugg_a)
        elif self._sugg_b:
            self.combo_type.setCurrentIndex(1)
            self.edit_key.setText(self._sugg_b)

        hint = QLabel("提示: 空卡默认密钥通常为 FFFFFFFFFFFF。密钥为 12 位十六进制字符。")
        hint.setStyleSheet("color: #64748B; font-size: 10px;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        foot = QHBoxLayout()
        foot.addStretch(1)
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedWidth(80)
        btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QPushButton("测试解密")
        self.btn_ok.setStyleSheet("background-color: #0284C7; font-weight: bold; color: #FFFFFF; padding: 6px 14px;")
        self.btn_ok.clicked.connect(self._on_accept)
        foot.addWidget(btn_cancel)
        foot.addWidget(self.btn_ok)
        lay.addLayout(foot)

        self.edit_key.textChanged.connect(self._validate)
        self._validate()

    def _validate(self):
        raw = self.edit_key.text().strip().replace(" ", "")
        ok = len(raw) == 12
        if ok:
            try:
                int(raw, 16)
            except ValueError:
                ok = False
        self.btn_ok.setEnabled(ok)

    def _on_accept(self):
        raw = self.edit_key.text().strip().replace(" ", "")
        if len(raw) != 12:
            QMessageBox.warning(self, "格式错误", "密钥必须为 12 位十六进制字符！")
            return
        try:
            int(raw, 16)
        except ValueError:
            QMessageBox.warning(self, "格式错误", "密钥包含非法的十六进制字符！")
            return
        self.accept()

    def get_key_type(self) -> str:
        return self.combo_type.currentData() or "A"

    def get_key_hex(self) -> str:
        return self.edit_key.text().strip().replace(" ", "").upper()
