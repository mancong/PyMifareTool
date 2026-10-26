# -*- coding: utf-8 -*-
"""
PyMifareTool - 密钥字典文件选择与扫描模式配置对话框
支持手动多选 MCT 标准字典 (std.keys, hotel-std.keys, extended-std.keys) 与导入外部字典；
射频半双工环境下密钥按优先级顺序单线程扫描。
"""

import os
from collections import Counter
from typing import List, Tuple, Dict, Any, Optional, Set
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QMessageBox, QFrame, QGroupBox, QAbstractItemView
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from core.key_manager import KeyManager


class KeySelectDialog(QDialog):
    """M1 密钥字典多选与扫描模式配置对话框"""

    def __init__(self, parent=None, initial_selected: Optional[List[str]] = None, concurrency: int = 4):
        super().__init__(parent)
        self.setWindowTitle("🔑 密钥字典选择与扫描配置 (MCT 生态)")
        self.setMinimumSize(560, 420)
        self.resize(600, 460)

        self.initial_selected = initial_selected
        self.concurrency = concurrency
        self.available_files = []
        self.checkboxes: Dict[str, QCheckBox] = {}
        self._file_key_sets: Dict[str, Set[str]] = {}
        self._selected_key_counts: Counter = Counter()

        self._init_ui()
        self._load_file_list()
        self._update_summary()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 顶部说明 Banner
        banner = QFrame()
        banner.setStyleSheet("background-color: #1E293B; border-radius: 6px; padding: 6px 10px;")
        b_lay = QVBoxLayout(banner)
        b_lay.setContentsMargins(4, 4, 4, 4)
        b_lay.setSpacing(3)
        lbl_title = QLabel("选择用于读卡或字典破解的密钥库 (对标 MifareClassicTool)")
        lbl_title.setStyleSheet("font-size: 10pt; font-weight: bold; color: #38BDF8;")
        lbl_sub = QLabel("支持勾选 MCT 官方预置字典或载入外部字典；密钥将按优先级顺序单线程扫描。")
        lbl_sub.setStyleSheet("font-size: 11px; color: #94A3B8;")
        b_lay.addWidget(lbl_title)
        b_lay.addWidget(lbl_sub)
        layout.addWidget(banner)

        # 字典文件列表表格
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["勾选", "字典文件", "有效密钥数", "说明"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #0B1120; gridline-color: #1E293B; border: 1px solid #334155; }"
            "QHeaderView::section { background-color: #1E293B; color: #94A3B8; font-weight: bold; padding: 4px; }"
        )
        layout.addWidget(self.table)

        # 中部操作组 (添加外部文件 + 扫描模式说明)
        opt_box = QGroupBox("⚙️ 字典扩展选项")
        opt_box.setStyleSheet("QGroupBox { font-weight: bold; color: #34D399; margin-top: 4px; }")
        opt_lay = QHBoxLayout(opt_box)
        opt_lay.setContentsMargins(8, 8, 8, 8)
        opt_lay.setSpacing(10)

        self.btn_add_external = QPushButton("➕ 导入外部字典文件...")
        self.btn_add_external.setStyleSheet("background-color: #1E293B; border: 1px solid #475569; padding: 4px 8px;")
        self.btn_add_external.clicked.connect(self._on_add_external_file)
        opt_lay.addWidget(self.btn_add_external)

        opt_lay.addStretch()

        lbl_mode = QLabel("ℹ️ 射频半双工：密钥按优先级顺序单线程扫描")
        lbl_mode.setStyleSheet("color: #94A3B8; font-size: 11px;")
        opt_lay.addWidget(lbl_mode)
        layout.addWidget(opt_box)

        # 统计摘要栏
        self.lbl_summary = QLabel("📊 已选 0 个字典文件 | 合计 0 条去重有效密钥")
        self.lbl_summary.setStyleSheet("font-size: 12px; font-weight: bold; color: #F59E0B;")
        layout.addWidget(self.lbl_summary)

        # 底部按钮
        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)

        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.setFixedWidth(60)
        self.btn_select_all.clicked.connect(lambda: self._set_all_checked(True))
        self.btn_select_none = QPushButton("全不选")
        self.btn_select_none.setFixedWidth(60)
        self.btn_select_none.clicked.connect(lambda: self._set_all_checked(False))
        btn_box.addWidget(self.btn_select_all)
        btn_box.addWidget(self.btn_select_none)

        btn_box.addStretch()

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_confirm = QPushButton("确认使用")
        self.btn_confirm.setStyleSheet("background-color: #0284C7; font-weight: bold; padding: 6px 16px;")
        self.btn_confirm.clicked.connect(self.accept)
        btn_box.addWidget(self.btn_cancel)
        btn_box.addWidget(self.btn_confirm)
        layout.addLayout(btn_box)

    def _load_file_list(self):
        """扫描并加载所有字典文件到列表中"""
        self.available_files = KeyManager.list_available_files()
        self.table.setRowCount(len(self.available_files))
        self.checkboxes.clear()
        self._file_key_sets.clear()
        self._selected_key_counts.clear()

        for row, item in enumerate(self.available_files):
            fname = item["filename"]

            # 确定是否默认勾选
            if self.initial_selected is not None:
                checked = fname in self.initial_selected or item["filepath"] in self.initial_selected
            else:
                checked = item.get("is_default", False)

            self._file_key_sets[fname] = set(item.get("keys", []))

            chk = QCheckBox()
            chk.setChecked(checked)
            chk.stateChanged.connect(lambda state, name=fname: self._on_file_toggled(name, state))
            self.checkboxes[fname] = chk

            # 居中放置 CheckBox
            w = QFrame()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(8, 0, 8, 0)
            lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(chk)
            self.table.setCellWidget(row, 0, w)

            # 文件名
            it_name = QTableWidgetItem(fname)
            it_name.setFlags(it_name.flags() & ~Qt.ItemFlag.ItemIsEditable)
            it_name.setForeground(QColor("#38BDF8"))
            it_name.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            self.table.setItem(row, 1, it_name)

            # 密钥数
            it_cnt = QTableWidgetItem(f"{item['key_count']:,} 键")
            it_cnt.setFlags(it_cnt.flags() & ~Qt.ItemFlag.ItemIsEditable)
            it_cnt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_cnt.setForeground(QColor("#34D399"))
            self.table.setItem(row, 2, it_cnt)

            # 说明
            it_desc = QTableWidgetItem(item["desc"])
            it_desc.setFlags(it_desc.flags() & ~Qt.ItemFlag.ItemIsEditable)
            it_desc.setToolTip(item["desc"])
            self.table.setItem(row, 3, it_desc)

        self._rebuild_selected_counts()

    def _on_file_toggled(self, fname: str, state: int):
        """增量维护密钥出现次数，避免每次勾选都全量合并大字典"""
        keys = self._file_key_sets.get(fname, set())
        if state:
            for key in keys:
                self._selected_key_counts[key] += 1
        else:
            for key in keys:
                self._selected_key_counts[key] -= 1
                if self._selected_key_counts[key] <= 0:
                    del self._selected_key_counts[key]
        self._update_summary()

    def _rebuild_selected_counts(self):
        self._selected_key_counts.clear()
        for fname, chk in self.checkboxes.items():
            if chk.isChecked():
                for key in self._file_key_sets.get(fname, set()):
                    self._selected_key_counts[key] += 1

    def _set_all_checked(self, state: bool):
        for chk in self.checkboxes.values():
            chk.setChecked(state)
        self._rebuild_selected_counts()
        self._update_summary()

    def _update_summary(self):
        """实时显示选中的去重密钥总数 (基于增量计数)"""
        selected_files = self.get_selected_files()
        total = sum(1 for count in self._selected_key_counts.values() if count > 0)
        self.lbl_summary.setText(
            f"📊 已选 {len(selected_files)} 个字典文件 | 合计去重有效密钥: {total:,} 条"
        )
        if total > 500:
            self.lbl_summary.setStyleSheet("font-size: 12px; font-weight: bold; color: #F59E0B;")
        else:
            self.lbl_summary.setStyleSheet("font-size: 12px; font-weight: bold; color: #34D399;")

    def _on_add_external_file(self):
        """用户导入外部字典文件并复制/加载"""
        path, _ = QFileDialog.getOpenFileName(
            self, "导入外部密钥字典文件", "", "密钥字典文件 (*.keys *.dic *.txt);;所有文件 (*.*)"
        )
        if path:
            keys = KeyManager.parse_key_file(path)
            if not keys:
                QMessageBox.warning(self, "解析失败", "所选文件中未解析到有效的 12 位十六进制密钥！")
                return

            fname = os.path.basename(path)
            target = os.path.join(KeyManager.get_keys_dir(), fname)
            if os.path.abspath(path) != os.path.abspath(target):
                try:
                    import shutil
                    shutil.copy2(path, target)
                except Exception as e:
                    QMessageBox.warning(self, "导入错误", f"拷贝字典失败: {e}")
                    return

            QMessageBox.information(self, "导入成功", f"成功导入字典文件 [{fname}]，包含 {len(keys)} 条有效密钥！")
            self._load_file_list()
            if fname in self.checkboxes:
                self.checkboxes[fname].setChecked(True)
            self._update_summary()

    def get_selected_files(self) -> List[str]:
        """获取所有被勾选的文件名列表"""
        selected = []
        for fname, chk in self.checkboxes.items():
            if chk.isChecked():
                selected.append(fname)
        return selected

    def get_selected_keys(self) -> List[str]:
        """获取所有选中的文件合并后的去重十六进制密钥列表"""
        selected_files = self.get_selected_files()
        return KeyManager.load_combined_keys(selected_files)

    def get_concurrency(self) -> int:
        """射频半双工下密钥扫描为单线程顺序执行。"""
        return 1
