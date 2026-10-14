# -*- coding: utf-8 -*-
"""
PyMifareTool - 16 扇区可视化数据矩阵组件 (Pro 增强版)
支持：
1. 0~15 扇区、64 个数据块、Key A、控制字、Key B 视觉分块渲染
2. 双击直接就地编辑 Hex 字节，自动校验并实时回写同步至 MifareDump
3. 集成一键读卡 (Read Card)、一键写卡 (Write Card)、扇区字典攻击 (Crack Keys) 与固件探测
4. 任务进度条与操作取消控制
"""

from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QPushButton, QFileDialog, QMessageBox, QAbstractItemView,
    QProgressBar, QFrame, QCheckBox, QToolButton, QMenu
)
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtCore import Qt, pyqtSignal

from core.dump_model import MifareDump, BlockState
from core.card_service import CardOperationWorker


class SectorTableWidget(QWidget):
    # 信号：请求主窗口转发日志或通知
    sig_notify = pyqtSignal(str)

    def __init__(self, serial_worker=None, parent=None):
        super().__init__(parent)
        self.serial_worker = serial_worker
        self.dump = MifareDump()
        self.card_op_worker: Optional[CardOperationWorker] = None
        self._updating_table = False  # 防止刷新表格时触发 cellChanged

        # 字典与并发配置状态
        self._selected_key_files: Optional[List[str]] = None
        self._selected_keys: Optional[List[str]] = None
        self._concurrency: int = 4

        self._init_ui()

    def set_serial_worker(self, worker):
        self.serial_worker = worker

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 1. 顶部主功能栏 (卡片式双行自适应分组，避免低分辨率屏幕按钮溢出或遮挡)
        tool_frame = QFrame()
        tool_frame.setStyleSheet(
            "QFrame#toolFrame { background-color: #1E293B; border: 1px solid #334155; border-radius: 8px; }"
        )
        tool_frame.setObjectName("toolFrame")
        tool_vbox = QVBoxLayout(tool_frame)
        tool_vbox.setContentsMargins(8, 6, 8, 6)
        tool_vbox.setSpacing(6)

        # 第 1 行：文件 Dump 与全卡纠错工具 (自适应紧凑工具按钮与下拉菜单)
        row1 = QHBoxLayout()
        row1.setSpacing(6)
        lbl_r1 = QLabel("📁 Dump 管理:")
        lbl_r1.setStyleSheet("color: #94A3B8; font-weight: bold; font-size: 11px;")
        row1.addWidget(lbl_r1)

        self.btn_load = QPushButton("📂 载入 Dump")
        self.btn_load.clicked.connect(self._on_load_file)
        self.btn_save = QPushButton("💾 导出 Dump")
        self.btn_save.clicked.connect(self._on_save_file)

        # 格式转换下拉菜单 (MCT / 文本 / 字典)
        self.btn_export_more = QToolButton()
        self.btn_export_more.setText("📄 格式转换")
        self.btn_export_more.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        menu_exp = QMenu(self)
        act_mct = menu_exp.addAction("📄 导出 MCT 格式 (*.mct)")
        act_mct.triggered.connect(self._on_export_txt)
        act_txt = menu_exp.addAction("📝 导出十六进制文本 (*.txt)")
        act_txt.triggered.connect(self._on_export_txt)
        act_dic = menu_exp.addAction("🔑 导出扇区密钥字典 (*.dic)")
        act_dic.triggered.connect(self._on_export_dict)
        self.btn_export_more.setMenu(menu_exp)
        self.btn_export_more.clicked.connect(self._on_export_txt)

        # 纠错与修复下拉菜单 (检查 / 纠正)
        self.btn_check_fix = QToolButton()
        self.btn_check_fix.setText("🛡️ 纠错与修复")
        self.btn_check_fix.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        menu_chk = QMenu(self)
        act_chk = menu_chk.addAction("🛡️ 检查全卡数据完整性 (BCC/控制字)")
        act_chk.triggered.connect(self._on_check_card)
        act_fix = menu_chk.addAction("🔧 纠正修复全卡 (自动修复损坏校验)")
        act_fix.triggered.connect(self._on_repair_card)
        self.btn_check_fix.setMenu(menu_chk)
        self.btn_check_fix.clicked.connect(self._on_check_card)

        self.btn_reset = QPushButton("🔄 重置空白")
        self.btn_reset.clicked.connect(self._on_reset)

        # 属性兼容引用
        self.btn_export_txt = self.btn_export_more
        self.btn_export_dic = self.btn_export_more
        self.btn_check = self.btn_check_fix
        self.btn_repair = self.btn_check_fix

        row1.addWidget(self.btn_load)
        row1.addWidget(self.btn_save)
        row1.addWidget(self.btn_export_more)
        row1.addWidget(self.btn_check_fix)
        row1.addWidget(self.btn_reset)
        row1.addStretch()

        # 第 2 行：卡片硬件交互与写保护
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        lbl_r2 = QLabel("⚡ 卡片操作:")
        lbl_r2.setStyleSheet("color: #94A3B8; font-weight: bold; font-size: 11px;")
        row2.addWidget(lbl_r2)

        self.btn_read_card = QPushButton("📖 一键读卡")
        self.btn_read_card.setStyleSheet("background-color: #0284C7; font-weight: bold;")
        self.btn_read_card.clicked.connect(self._on_read_card)

        self.btn_write_card = QPushButton("✍️ 一键写卡")
        self.btn_write_card.setStyleSheet("background-color: #D97706; font-weight: bold;")
        self.btn_write_card.clicked.connect(self._on_write_card)

        self.btn_crack = QPushButton("🔑 字典破解")
        self.btn_crack.setStyleSheet("background-color: #7C3AED; font-weight: bold;")
        self.btn_crack.clicked.connect(self._on_crack_keys)

        self.btn_key_config = QPushButton("⚙️ 字典并发")
        self.btn_key_config.setStyleSheet("background-color: #334155; font-size: 11px;")
        self.btn_key_config.clicked.connect(self._on_configure_keys)

        self.btn_probe = QPushButton("🔬 探测固件")
        self.btn_probe.setStyleSheet("background-color: #059669; font-weight: bold;")
        self.btn_probe.clicked.connect(self._on_probe_firmware)

        row2.addWidget(self.btn_read_card)
        row2.addWidget(self.btn_write_card)
        row2.addWidget(self.btn_crack)
        row2.addWidget(self.btn_key_config)
        row2.addWidget(self.btn_probe)
        row2.addSpacing(6)

        self.chk_protect_b0 = QCheckBox("Block 0 写保护 (防废卡)")
        self.chk_protect_b0.setChecked(True)
        self.chk_protect_b0.setStyleSheet("color: #FBBF24; font-size: 11px; font-weight: bold;")
        row2.addWidget(self.chk_protect_b0)
        row2.addStretch()

        tool_vbox.addLayout(row1)
        tool_vbox.addLayout(row2)
        layout.addWidget(tool_frame)

        # 2. 图例说明栏 (含未读取占位与加密状态提示，彻底消除歧义)
        legend_layout = QHBoxLayout()
        legend_layout.addWidget(self._make_legend("Block 0 (UID/厂商块)", "#3D2B1F", "#FFB300"))
        legend_layout.addWidget(self._make_legend("普通数据块 (已读取 Hex)", "#1E293B", "#E2E8F0"))
        legend_layout.addWidget(self._make_legend("扇区尾块 (Key A / 控制字 / Key B)", "#1A365D", "#60A5FA"))
        legend_layout.addWidget(self._make_legend("[-] 未载入/未读取", "#0F172A", "#64748B"))
        legend_layout.addWidget(self._make_legend("[??] 加密/读取受阻", "#3B1B1B", "#F87171"))
        legend_layout.addStretch()
        layout.addLayout(legend_layout)

        # 3. 核心 64 块表格主体
        self.table = QTableWidget()
        self.table.setColumnCount(19)
        headers = ["扇区", "块号"] + [f"{i:02X}" for i in range(16)] + ["ASCII 字符预览"]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(64)

        # 启用双击就地编辑
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.verticalHeader().setVisible(False)
        self.table.setFont(QFont("Consolas", 9))

        # 绑定单元格修改事件，实时回写 dump_model
        self.table.cellChanged.connect(self._on_cell_changed)

        # 列宽调整 (紧凑自适应排版，保证低分辨率小屏幕与高缩放下不重叠、不折叠)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 42)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 42)
        for i in range(2, 18):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(i, 28)
        header.setSectionResizeMode(18, QHeaderView.ResizeMode.Stretch)
        header.setMinimumSectionSize(26)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        layout.addWidget(self.table)

        # 4. 底部进度条与状态面板
        self.progress_panel = QFrame()
        self.progress_panel.setStyleSheet(
            "background-color: #1E293B; border-radius: 6px; padding: 4px;"
        )
        p_layout = QHBoxLayout(self.progress_panel)
        p_layout.setContentsMargins(6, 4, 6, 4)

        self.lbl_progress = QLabel("就绪")
        self.lbl_progress.setStyleSheet("font-size: 11px; color: #38BDF8;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setStyleSheet(
            "QProgressBar { background-color: #0F172A; border-radius: 4px; text-align: center; color: white; font-size: 10px; }"
            "QProgressBar::chunk { background-color: #0284C7; border-radius: 4px; }"
        )

        self.btn_abort = QPushButton("✖ 停止")
        self.btn_abort.setFixedSize(56, 22)
        self.btn_abort.setStyleSheet("background-color: #DC2626; font-size: 10px; padding: 1px;")
        self.btn_abort.clicked.connect(self._on_abort_operation)

        p_layout.addWidget(self.lbl_progress, stretch=2)
        p_layout.addWidget(self.progress_bar, stretch=3)
        p_layout.addWidget(self.btn_abort)
        self.progress_panel.setVisible(False)

        layout.addWidget(self.progress_panel)

        self.refresh_table()

    def _make_legend(self, text: str, bg_color: str, text_color: str) -> QLabel:
        lbl = QLabel(f" {text} ")
        lbl.setStyleSheet(
            f"background-color: {bg_color}; color: {text_color}; border-radius: 3px; font-size: 11px; padding: 2px 6px;"
        )
        return lbl

    def set_dump(self, dump: MifareDump):
        self.dump = dump
        self.refresh_table()

    def update_uid(self, uid_bytes: bytes):
        """刷卡感应捕获时同步 Block 0 UID"""
        self.dump.set_uid(uid_bytes)
        self.refresh_table()

    def refresh_table(self):
        """刷新整张表格渲染 (支持未读取 '-'、原样读取十六进制与加密受限 '??')"""
        self._updating_table = True
        self.table.setRowCount(self.dump.block_count)
        for block_idx in range(self.dump.block_count):
            sector_idx = self.dump.get_block_sector(block_idx)
            trailer_block = self.dump.get_sector_trailer_block(sector_idx)
            is_trailer = (block_idx == trailer_block)
            is_block0 = (block_idx == 0)
            state = self.dump.get_block_state(block_idx)

            if is_block0:
                bg = QColor("#2A1F10")
                fg = QColor("#FFD54F")
            elif is_trailer:
                bg = QColor("#0F172A")
                fg = QColor("#38BDF8")
            else:
                bg = QColor("#1E293B") if (sector_idx % 2 == 0) else QColor("#182234")
                fg = QColor("#E2E8F0")

            # 扇区编号 (只读)
            item_sec = QTableWidgetItem(f"S{sector_idx:02d}")
            item_sec.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_sec.setBackground(bg)
            item_sec.setForeground(fg)
            item_sec.setFlags(item_sec.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(block_idx, 0, item_sec)

            # 块编号 (只读)
            item_blk = QTableWidgetItem(f"B{block_idx:02d}")
            item_blk.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_blk.setBackground(bg)
            item_blk.setForeground(fg)
            item_blk.setFlags(item_blk.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(block_idx, 1, item_blk)

            # 16 字节数据 (根据块状态精准渲染：未读 "-" / 读出原样 Hex / 加密不可读 "??")
            block_data = self.dump.get_block(block_idx)
            for b in range(16):
                item_byte = QTableWidgetItem()
                item_byte.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_byte.setBackground(bg)

                if state == BlockState.UNREAD:
                    # 未读取 / 未载入: 呈现 "-" 占位，柔和暗灰色，绝不显示误导性的 00
                    item_byte.setText("-")
                    item_byte.setForeground(QColor("#64748B"))
                    item_byte.setToolTip(f"S{sector_idx:02d} B{block_idx:02d} 字节[{b:02X}]: 尚未读取，双击可直接就地编辑修改")
                elif state == BlockState.READ_FAILED:
                    # 加密扇区读不出 / 认证失败: 无歧义呈现 "??"，珊瑚红警示
                    item_byte.setText("??")
                    item_byte.setForeground(QColor("#F87171"))
                    item_byte.setToolTip(f"S{sector_idx:02d} B{block_idx:02d} 字节[{b:02X}]: 扇区加密受保护或未命中密钥，无法读取")
                else:
                    # 真实读取成功 / 已载入文件 / 用户已编辑: 原样展示实际 Hex 字节
                    val = block_data[b]
                    item_byte.setText(f"{val:02X}")
                    if is_trailer:
                        if b < 6:
                            item_byte.setForeground(QColor("#4ADE80"))  # Key A
                        elif b < 10:
                            item_byte.setForeground(QColor("#FBBF24"))  # 控制字
                        else:
                            item_byte.setForeground(QColor("#60A5FA"))  # Key B
                    else:
                        item_byte.setForeground(fg)
                    item_byte.setToolTip(f"S{sector_idx:02d} B{block_idx:02d} 字节[{b:02X}]: 0x{val:02X} (十进制 {val})")

                self.table.setItem(block_idx, 2 + b, item_byte)

            # ASCII 文本预览 (只读)
            if state == BlockState.UNREAD:
                asc_str = "-"
                asc_fg = QColor("#64748B")
            elif state == BlockState.READ_FAILED:
                asc_str = "[加密受限]"
                asc_fg = QColor("#F87171")
            else:
                asc_str = "".join(chr(x) if 32 <= x <= 126 else "." for x in block_data)
                asc_fg = fg

            item_asc = QTableWidgetItem(asc_str)
            item_asc.setBackground(bg)
            item_asc.setForeground(asc_fg)
            item_asc.setFlags(item_asc.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(block_idx, 18, item_asc)

        self._updating_table = False

    def _on_cell_changed(self, row: int, col: int):
        """处理单元格直接就地编辑修改"""
        if self._updating_table:
            return
        if not (2 <= col <= 17):
            return

        item = self.table.item(row, col)
        if not item:
            return

        byte_idx = col - 2
        text = item.text().strip().upper()

        # 校验合法十六进制单字节
        try:
            val = int(text, 16)
            if not (0 <= val <= 255):
                raise ValueError()
        except ValueError:
            # 还原为原值或根据状态还原
            state = self.dump.get_block_state(row)
            self._updating_table = True
            if state == BlockState.UNREAD:
                item.setText("-")
            elif state == BlockState.READ_FAILED:
                item.setText("??")
            else:
                original = self.dump.get_block(row)[byte_idx]
                item.setText(f"{original:02X}")
            self._updating_table = False
            return

        # 格式化展示为大写 2 位 Hex
        formatted = f"{val:02X}"
        self._updating_table = True
        item.setText(formatted)
        item.setForeground(QColor("#E2E8F0"))
        self._updating_table = False

        # 同步回 dump 模型并标记该块为已读取/已编辑
        block_bytes = bytearray(self.dump.get_block(row))
        block_bytes[byte_idx] = val
        self.dump.set_block(row, bytes(block_bytes))
        self.dump.set_block_state(row, BlockState.READ_OK)

        # 更新同行的 ASCII 预览
        asc_str = "".join(chr(x) if 32 <= x <= 126 else "." for x in block_bytes)
        item_asc = self.table.item(row, 18)
        if item_asc:
            item_asc.setText(asc_str)
            item_asc.setForeground(QColor("#E2E8F0"))

        # 视觉高亮标记已修改
        item.setBackground(QColor("#065F46"))

    # -------------------------------------------------------------
    # 异步卡片交互工作流
    # -------------------------------------------------------------
    def _start_worker(self, op_type: str, dump_to_write=None, allow_b0=False, custom_keys=None, concurrency=4):
        if not self.serial_worker or not self.serial_worker.is_connected():
            QMessageBox.warning(self, "未连接", "请先在左侧连接读卡器串口！")
            return

        if self.card_op_worker and self.card_op_worker.isRunning():
            QMessageBox.information(self, "正在进行", "当前已有正在执行的任务，请等待其完成。")
            return

        self.progress_panel.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_progress.setText(f"正在准备: {op_type}...")

        self.card_op_worker = CardOperationWorker(
            worker=self.serial_worker,
            op_type=op_type,
            dump_to_write=dump_to_write,
            allow_block0_write=allow_b0,
            custom_keys=custom_keys,
            concurrency=concurrency,
            parent=self
        )
        self.card_op_worker.sig_progress.connect(self._on_worker_progress)
        self.card_op_worker.sig_log.connect(lambda msg: self.sig_notify.emit(msg))
        self.card_op_worker.sig_block_read.connect(self._on_worker_block_read)
        self.card_op_worker.sig_finished.connect(self._on_worker_finished)
        self.card_op_worker.start()

    def _on_worker_progress(self, pct: int, status: str):
        self.progress_bar.setValue(pct)
        self.lbl_progress.setText(status)

    def _on_worker_block_read(self, block_idx: int, data: bytes):
        self.dump.set_block(block_idx, data)
        # 单块更新表格局部渲染
        self._updating_table = True
        for b in range(16):
            it = self.table.item(block_idx, 2 + b)
            if it:
                it.setText(f"{data[b]:02X}")
        it_asc = self.table.item(block_idx, 18)
        if it_asc:
            it_asc.setText("".join(chr(x) if 32 <= x <= 126 else "." for x in data))
        self._updating_table = False

    def _on_worker_finished(self, success: bool, msg: str, result_data):
        self.progress_panel.setVisible(False)
        if isinstance(result_data, MifareDump):
            self.dump = result_data
        self.refresh_table()

        if success:
            QMessageBox.information(self, "操作完成", msg)
        else:
            QMessageBox.warning(self, "操作结果", msg)


    def _on_abort_operation(self):
        if self.card_op_worker and self.card_op_worker.isRunning():
            self.card_op_worker.abort()
            self.lbl_progress.setText("正在中止...")

    def _on_configure_keys(self):
        """打开字典选择与并发配置对话框"""
        from ui.key_select_dialog import KeySelectDialog
        dialog = KeySelectDialog(self, initial_selected=self._selected_key_files, concurrency=self._concurrency)
        if dialog.exec():
            self._selected_key_files = dialog.get_selected_files()
            self._concurrency = dialog.get_concurrency()
            self._selected_keys = dialog.get_selected_keys()
            QMessageBox.information(
                self, "字典配置更新",
                f"已配置加载 {len(self._selected_key_files)} 个字典文件，共计 {len(self._selected_keys):,} 条去重有效密钥。\n"
                f"并发解密线程数: {self._concurrency} 线程。"
            )

    def _on_read_card(self):
        from core.key_manager import KeyManager
        keys = self._selected_keys if self._selected_keys else KeyManager.load_combined_keys()
        concurrency = self._concurrency if hasattr(self, "_concurrency") else 4
        self._start_worker(
            CardOperationWorker.OP_READ_CARD,
            custom_keys=keys,
            concurrency=concurrency
        )

    def _on_write_card(self):
        reply = QMessageBox.question(
            self,
            "写卡确认",
            "确定要将当前表格中的数据写入卡片吗？请确保卡片已放置在读卡器天线上！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            allow_b0 = not self.chk_protect_b0.isChecked()
            self._start_worker(
                CardOperationWorker.OP_WRITE_CARD,
                dump_to_write=self.dump,
                allow_b0=allow_b0
            )

    def _on_crack_keys(self):
        from ui.key_select_dialog import KeySelectDialog
        dialog = KeySelectDialog(self, initial_selected=self._selected_key_files, concurrency=self._concurrency)
        if dialog.exec():
            self._selected_key_files = dialog.get_selected_files()
            self._concurrency = dialog.get_concurrency()
            self._selected_keys = dialog.get_selected_keys()
            if not self._selected_keys:
                QMessageBox.warning(self, "未选择字典", "未找到有效密钥，请至少勾选一个包含有效密钥的字典文件！")
                return
            self._start_worker(
                CardOperationWorker.OP_CRACK_KEYS,
                custom_keys=self._selected_keys,
                concurrency=self._concurrency
            )

    def _on_probe_firmware(self):
        self._start_worker(CardOperationWorker.OP_PROBE_FIRMWARE)

    # -------------------------------------------------------------
    # 全卡校验与字典工具
    # -------------------------------------------------------------
    def _on_check_card(self):
        res = self.dump.verify_dump()
        if res["valid"]:
            QMessageBox.information(
                self, "全卡校验通过",
                "✅ 全卡数据与权限完整性检查全部通过！\n\n• Block 0 UID 与 BCC 校验值正确\n• 各扇区控制字 (Access Bits) 均合法有效"
            )
        else:
            msg = "⚠️ 发现以下异常问题:\n\n" + "\n".join(res["errors"][:10])
            if len(res["errors"]) > 10:
                msg += f"\n... 等共 {len(res['errors'])} 项错误"
            if res["warnings"]:
                msg += "\n\n提示:\n" + "\n".join(res["warnings"][:5])
            QMessageBox.warning(self, "全卡检查发现异常", msg)

    def _on_repair_card(self):
        res = self.dump.repair_dump()
        if res["fixed"]:
            self.refresh_table()
            msg = "🔧 已完成自动纠错修复:\n\n" + "\n".join(res["fixed_items"])
            QMessageBox.information(self, "自动纠错完成", msg)
        else:
            QMessageBox.information(self, "纠错结果", "全卡数据规范有效，未发现需要纠错的项目。")

    def _on_export_dict(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出密钥字典文件", "card_keys.dic", "字典文件 (*.dic *.txt);;所有文件 (*.*)"
        )
        if path:
            count = self.dump.export_key_dictionary(path)
            QMessageBox.information(self, "导出成功", f"已成功提取并导出 {count} 条去重密钥至:\n{path}")

    # -------------------------------------------------------------
    # 文件导入导出
    # -------------------------------------------------------------
    def _on_load_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Dump 文件",
            "",
            "全格式 Mifare Dump (*.dump *.mfd *.bin *.txt *.mct *.eml *.json);;"
            "MCT 文件 (*.mct *.txt);;"
            "RFIDtools / Proxmark3 EML (*.eml);;"
            "JSON 卡片档案 (*.json);;"
            "二进制 Dump (*.dump *.mfd *.bin);;"
            "所有文件 (*.*)"
        )
        if path:
            if self.dump.load_from_file(path):
                self.refresh_table()
                QMessageBox.information(self, "导入成功", "已成功载入文件:\n" + path)
            else:
                err_detail = self.dump.load_error_message or "文件格式不匹配或数据损坏"
                QMessageBox.warning(self, "导入失败", f"无法解析该文件:\n{err_detail}")

    def _on_save_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存为 Dump 文件",
            "card_dump.dump",
            "标准二进制 Dump (*.dump);;"
            "MFD 文件 (*.mfd);;"
            "MCT 文本格式 (*.mct);;"
            "RFIDtools / PM3 EML (*.eml);;"
            "JSON 格式 (*.json);;"
            "BIN 文件 (*.bin)"
        )
        if path:
            if self.dump.save_to_file(path):
                QMessageBox.information(self, "导出成功", "Dump 文件已保存至:\n" + path)
            else:
                QMessageBox.warning(self, "保存失败", "保存文件时发生错误！")

    def _on_export_txt(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存为文本文件",
            "card_dump.txt",
            "文本文件 (*.txt);;MCT 文件 (*.mct);;RFIDtools EML (*.eml);;JSON 文件 (*.json)"
        )
        if path:
            if self.dump.save_to_file(path):
                QMessageBox.information(self, "导出成功", "文本格式数据已保存至:\n" + path)

    def _on_reset(self):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("重置卡片矩阵")
        msg_box.setText("请选择重置方式：")
        msg_box.setInformativeText(
            "• 重置为未载入状态 (-)：全卡恢复为未读取/未载入占位符，消除数据真实性歧义。\n"
            "• 填充出厂空白卡 (00/FF)：填充标准空白卡模板数据并标记为已载入。"
        )
        btn_unread = msg_box.addButton("重置为未载入 (-)", QMessageBox.ButtonRole.ActionRole)
        btn_factory = msg_box.addButton("填充出厂空白卡", QMessageBox.ButtonRole.ActionRole)
        btn_cancel = msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        msg_box.setDefaultButton(btn_unread)
        msg_box.exec()

        clicked = msg_box.clickedButton()
        if clicked == btn_unread:
            self.dump.reset_to_unread()
            self.refresh_table()
        elif clicked == btn_factory:
            self.dump.reset_factory_default(keep_state_unread=False)
            self.refresh_table()

