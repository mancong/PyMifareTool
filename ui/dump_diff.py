# -*- coding: utf-8 -*-
"""
PyMifareTool - Dump 数据差分对比工具 (Diff Tool)
字节级差分比对器：对比两张卡或同一张卡消费前后的数据变动
"""

import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QPushButton, QFileDialog, QMessageBox, QGroupBox,
    QAbstractItemView
)
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtCore import Qt
from core.dump_model import MifareDump

class DumpDiffWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.dump_a = MifareDump()
        self.dump_b = MifareDump()
        self.path_a = ""
        self.path_b = ""
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 顶部两个文件选择卡片
        file_box = QHBoxLayout()
        
        # 文件 A 卡片
        grp_a = QGroupBox("源卡数据 (卡 A / 例如消费前)")
        grp_a.setStyleSheet("QGroupBox { font-weight: bold; color: #60A5FA; }")
        lay_a = QHBoxLayout(grp_a)
        self.lbl_file_a = QLabel("未载入文件")
        self.lbl_file_a.setStyleSheet("color: #94A3B8;")
        btn_load_a = QPushButton("📂 选择文件 A")
        btn_load_a.clicked.connect(self._on_load_a)
        lay_a.addWidget(self.lbl_file_a, stretch=1)
        lay_a.addWidget(btn_load_a)

        # 文件 B 卡片
        grp_b = QGroupBox("对比卡数据 (卡 B / 例如消费后)")
        grp_b.setStyleSheet("QGroupBox { font-weight: bold; color: #F59E0B; }")
        lay_b = QHBoxLayout(grp_b)
        self.lbl_file_b = QLabel("未载入文件")
        self.lbl_file_b.setStyleSheet("color: #94A3B8;")
        btn_load_b = QPushButton("📂 选择文件 B")
        btn_load_b.clicked.connect(self._on_load_b)
        lay_b.addWidget(self.lbl_file_b, stretch=1)
        lay_b.addWidget(btn_load_b)

        file_box.addWidget(grp_a)
        file_box.addWidget(grp_b)
        layout.addLayout(file_box)

        # 对比操作与统计卡片
        stats_layout = QHBoxLayout()
        self.btn_compare = QPushButton("⚡ 执行差分对比")
        self.btn_compare.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; padding: 6px 16px;")
        self.btn_compare.clicked.connect(self.compare_dumps)

        self.lbl_stats = QLabel("状态: 待载入数据")
        self.lbl_stats.setStyleSheet("font-size: 10pt; color: #38BDF8; font-weight: bold;")

        stats_layout.addWidget(self.btn_compare)
        stats_layout.addWidget(self.lbl_stats)
        stats_layout.addStretch()
        layout.addLayout(stats_layout)

        # 差异结果表格
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["扇区", "块号", "偏移", "卡 A 数据 (Hex)", "卡 B 数据 (Hex)", "差值分析 (B - A)"])
        self.table.setFont(QFont("Consolas", 10))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        diff_hdr = self.table.horizontalHeader()
        diff_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        diff_hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        diff_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        diff_hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        diff_hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        diff_hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

        layout.addWidget(self.table)

    def _on_load_a(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Dump 文件 A", "", "Mifare Dump (*.dump *.mfd *.bin *.txt *.mct *.eml *.json);;所有文件 (*.*)"
        )
        if path:
            if self.dump_a.load_from_file(path):
                self.path_a = path
                self.lbl_file_a.setText(os.path.basename(path))
                self.lbl_file_a.setToolTip(path)
                self.compare_dumps()

    def _on_load_b(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Dump 文件 B", "", "Mifare Dump (*.dump *.mfd *.bin *.txt *.mct *.eml *.json);;所有文件 (*.*)"
        )
        if path:
            if self.dump_b.load_from_file(path):
                self.path_b = path
                self.lbl_file_b.setText(os.path.basename(path))
                self.lbl_file_b.setToolTip(path)
                self.compare_dumps()

    def compare_dumps(self):
        """对比全卡数据并输出差异列表 (支持 1K 与 4K 自适应对比)"""
        diff_count = 0
        diff_sectors = set()
        diff_blocks = set()

        self.table.setRowCount(0)
        row = 0

        total_blocks = max(self.dump_a.block_count, self.dump_b.block_count)

        for block_idx in range(total_blocks):
            data_a = self.dump_a.get_block(block_idx) if block_idx < self.dump_a.block_count else bytes(16)
            data_b = self.dump_b.get_block(block_idx) if block_idx < self.dump_b.block_count else bytes(16)

            if data_a != data_b:
                if block_idx < self.dump_a.block_count:
                    sector_idx = self.dump_a.get_block_sector(block_idx)
                else:
                    sector_idx = self.dump_b.get_block_sector(block_idx)
                diff_sectors.add(sector_idx)
                diff_blocks.add(block_idx)

                for byte_idx in range(16):
                    val_a = data_a[byte_idx]
                    val_b = data_b[byte_idx]

                    if val_a != val_b:
                        diff_count += 1
                        self.table.insertRow(row)

                        item_sec = QTableWidgetItem(f"扇区 {sector_idx:02d}")
                        item_blk = QTableWidgetItem(f"块 {block_idx:02d}")
                        item_off = QTableWidgetItem(f"字节 [{byte_idx:02d}]")
                        
                        item_val_a = QTableWidgetItem(f"{val_a:02X} ({val_a})")
                        item_val_a.setForeground(QColor("#60A5FA"))
                        
                        item_val_b = QTableWidgetItem(f"{val_b:02X} ({val_b})")
                        item_val_b.setForeground(QColor("#F59E0B"))

                        delta = val_b - val_a
                        delta_str = f"+{delta}" if delta > 0 else f"{delta}"
                        item_delta = QTableWidgetItem(delta_str)
                        item_delta.setForeground(QColor("#EF4444") if delta < 0 else QColor("#10B981"))

                        for col, item in enumerate([item_sec, item_blk, item_off, item_val_a, item_val_b, item_delta]):
                            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                            self.table.setItem(row, col, item)

                        row += 1

        if diff_count == 0:
            self.lbl_stats.setText("✅ 对比结果: 两张卡数据 100% 完全一致！")
            self.lbl_stats.setStyleSheet("color: #10B981; font-weight: bold; font-size: 10pt;")
        else:
            sec_str = ", ".join(f"S{s:02d}" for s in sorted(diff_sectors))
            self.lbl_stats.setText(f"⚠️ 发现差异: 共 {diff_count} 处字节不同 | 受影响扇区: {sec_str} (共 {len(diff_blocks)} 个数据块)")
            self.lbl_stats.setStyleSheet("color: #F87171; font-weight: bold; font-size: 10pt;")
