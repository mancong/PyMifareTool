# -*- coding: utf-8 -*-
"""
PyMifareTool - 发卡管理与刷卡流水看板组件
"""

import csv
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QPushButton, QFileDialog, QMessageBox, QLineEdit,
    QDialog, QFormLayout, QDialogButtonBox, QAbstractItemView, QTabWidget,
    QToolButton, QMenu
)
from PyQt6.QtCore import Qt
from core.card_db import CardDatabase

class EditCardDialog(QDialog):
    def __init__(self, uid: str, name: str, holder: str, note: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"编辑卡片信息 [{uid}]")
        self.resize(360, 200)

        layout = QFormLayout(self)
        self.txt_name = QLineEdit(name)
        self.txt_holder = QLineEdit(holder)
        self.txt_note = QLineEdit(note)

        layout.addRow("卡片名称:", self.txt_name)
        layout.addRow("持卡人:", self.txt_holder)
        layout.addRow("备注说明:", self.txt_note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_data(self):
        return self.txt_name.text().strip(), self.txt_holder.text().strip(), self.txt_note.text().strip()

class CardManageWidget(QWidget):
    def __init__(self, db: CardDatabase, parent=None):
        super().__init__(parent)
        self.db = db
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Tab: 登记卡片库 vs 刷卡流水日志
        self.tabs = QTabWidget()

        # 1. 登记卡片库 Tab
        tab_cards = QWidget()
        lay_cards = QVBoxLayout(tab_cards)
        
        tool_cards = QHBoxLayout()
        btn_refresh = QPushButton("🔄 刷新列表")
        btn_refresh.clicked.connect(self.refresh_cards)
        btn_edit = QPushButton("✏️ 编辑选中卡片")
        btn_edit.clicked.connect(self._on_edit_card)
        btn_export = QPushButton("📤 导出为 CSV")
        btn_export.clicked.connect(self._on_export_cards)

        tool_cards.addWidget(btn_refresh)
        tool_cards.addWidget(btn_edit)
        tool_cards.addWidget(btn_export)
        tool_cards.addStretch()
        lay_cards.addLayout(tool_cards)

        self.table_cards = QTableWidget()
        self.table_cards.setColumnCount(8)
        self.table_cards.setHorizontalHeaderLabels([
            "物理卡号 (UID)", "卡片名称", "持卡人", "十进制卡号 (8H10D)",
            "韦根 (WG26)", "刷卡次数", "最后刷卡时间", "备注"
        ])
        self.table_cards.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table_cards.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_cards.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_cards.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_cards.verticalHeader().setVisible(False)
        lay_cards.addWidget(self.table_cards)

        # 2. 刷卡流水日志 Tab
        tab_logs = QWidget()
        lay_logs = QVBoxLayout(tab_logs)
        tool_logs = QHBoxLayout()
        btn_refresh_logs = QPushButton("🔄 刷新流水")
        btn_refresh_logs.clicked.connect(self.refresh_logs)
        btn_export_logs = QPushButton("📤 导出流水 CSV")
        btn_export_logs.clicked.connect(self._on_export_logs)

        # 清空流水功能 (支持下拉菜单选择 或 点击直接弹窗选择：清空页面显示 vs 永久清空数据库记录)
        self.btn_clear_logs = QToolButton()
        self.btn_clear_logs.setText("🗑️ 清空流水")
        self.btn_clear_logs.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        menu_clear = QMenu(self)
        act_clear_view = menu_clear.addAction("🧹 仅清空页面显示 (保留数据库记录)")
        act_clear_view.triggered.connect(self._on_clear_logs_view)
        act_clear_db = menu_clear.addAction("🗑️ 永久清空数据库记录 (不可逆)")
        act_clear_db.triggered.connect(self._on_clear_logs_db)
        self.btn_clear_logs.setMenu(menu_clear)
        self.btn_clear_logs.clicked.connect(self._on_clear_logs_choice)

        tool_logs.addWidget(btn_refresh_logs)
        tool_logs.addWidget(btn_export_logs)
        tool_logs.addWidget(self.btn_clear_logs)
        tool_logs.addStretch()
        lay_logs.addLayout(tool_logs)

        self.table_logs = QTableWidget()
        self.table_logs.setColumnCount(5)
        self.table_logs.setHorizontalHeaderLabels(["序号", "刷卡时间", "物理卡号 (UID)", "归属卡片/持卡人", "原始串口报文"])
        self.table_logs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table_logs.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table_logs.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table_logs.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_logs.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_logs.verticalHeader().setVisible(False)
        lay_logs.addWidget(self.table_logs)

        self.tabs.addTab(tab_cards, "💳 注册卡片库")
        self.tabs.addTab(tab_logs, "📜 实时刷卡流水")
        layout.addWidget(self.tabs)

        self.refresh_cards()
        self.refresh_logs()

    def refresh_cards(self):
        cards = self.db.list_all_cards()
        self.table_cards.setRowCount(len(cards))
        for row, c in enumerate(cards):
            items = [
                c.get("uid", ""),
                c.get("card_name", ""),
                c.get("card_holder", ""),
                c.get("dec_10d", ""),
                c.get("wiegand_26", ""),
                str(c.get("swipe_count", 0)),
                c.get("last_swiped_at", ""),
                c.get("note", "") or ""
            ]
            for col, val in enumerate(items):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if col not in [1, 7] else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table_cards.setItem(row, col, item)

    def refresh_logs(self):
        logs = self.db.list_recent_logs(100)
        self.table_logs.setRowCount(len(logs))
        for row, l in enumerate(logs):
            name = l.get("card_name") or "未登记"
            holder = l.get("card_holder") or "访客"
            items = [
                str(l.get("id", "")),
                l.get("swiped_at", ""),
                l.get("uid", ""),
                f"{name} ({holder})",
                l.get("raw_hex", "")
            ]
            for col, val in enumerate(items):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if col < 3 else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table_logs.setItem(row, col, item)

    def _on_edit_card(self):
        selected = self.table_cards.currentRow()
        if selected < 0:
            QMessageBox.information(self, "提示", "请先在表格中选中一行卡片！")
            return
        uid = self.table_cards.item(selected, 0).text()
        name = self.table_cards.item(selected, 1).text()
        holder = self.table_cards.item(selected, 2).text()
        note = self.table_cards.item(selected, 7).text()

        dialog = EditCardDialog(uid, name, holder, note, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_name, new_holder, new_note = dialog.get_data()
            self.db.update_card_info(uid, new_name, new_holder, new_note)
            self.refresh_cards()
            self.refresh_logs()

    def _on_export_cards(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出卡片列表", "cards.csv", "CSV 文件 (*.csv)")
        if path:
            cards = self.db.list_all_cards()
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["UID", "卡片名称", "持卡人", "十进制卡号", "韦根26", "刷卡次数", "最后刷卡时间", "备注"])
                for c in cards:
                    writer.writerow([
                        c.get("uid"), c.get("card_name"), c.get("card_holder"),
                        c.get("dec_10d"), c.get("wiegand_26"), c.get("swipe_count"),
                        c.get("last_swiped_at"), c.get("note")
                    ])
            QMessageBox.information(self, "导出成功", f"卡片列表已导出至:\n{path}")

    def _on_export_logs(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出刷卡流水", "swipe_logs.csv", "CSV 文件 (*.csv)")
        if path:
            logs = self.db.list_recent_logs(500)
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["序号", "刷卡时间", "UID", "卡片名称", "持卡人", "原始报文"])
                for l in logs:
                    writer.writerow([
                        l.get("id"), l.get("swiped_at"), l.get("uid"),
                        l.get("card_name"), l.get("card_holder"), l.get("raw_hex")
                    ])
            QMessageBox.information(self, "导出成功", f"刷卡流水已导出至:\n{path}")

    def _on_clear_logs_choice(self):
        """弹出选择对话框，供用户选择仅清空页面显示还是永久清空数据库记录"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("清空刷卡流水")
        msg_box.setText("请选择流水记录清空方式：")
        msg_box.setInformativeText(
            "• 🧹 【仅清空页面显示】：仅清空当前界面表格显示，数据库历史记录保留，点击【刷新流水】可重新载入。\n\n"
            "• 🗑️ 【永久清空数据库】：彻底清空 SQLite 数据库中的所有历史刷卡记录（此操作不可撤销）。"
        )
        btn_view = msg_box.addButton("🧹 仅清空页面显示", QMessageBox.ButtonRole.ActionRole)
        btn_db = msg_box.addButton("🗑️ 永久清空数据库", QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        msg_box.setDefaultButton(btn_view)
        msg_box.exec()

        if msg_box.clickedButton() == btn_view:
            self._on_clear_logs_view()
        elif msg_box.clickedButton() == btn_db:
            self._on_clear_logs_db()

    def _on_clear_logs_view(self):
        """仅清空前端表格视图"""
        self.table_logs.setRowCount(0)
        QMessageBox.information(
            self, "提示", "已清空当前页面流水显示。\n（本地数据库记录已完整保留，点击【刷新流水】可随时重新载入）"
        )

    def _on_clear_logs_db(self):
        """彻底清空数据库中的历史刷卡流水"""
        reply = QMessageBox.warning(
            self, "二次确认",
            "⚠️ 警告：此操作将永久清空本地数据库中存储的所有刷卡历史流水，操作后无法恢复！\n\n是否确认永久清空？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            count = self.db.clear_swipe_logs()
            self.table_logs.setRowCount(0)
            QMessageBox.information(self, "清空成功", f"成功从数据库中永久清空了 {count} 条历史流水记录！")
