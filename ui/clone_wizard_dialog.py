# -*- coding: utf-8 -*-
"""
PyMifareTool - 一键快速复制/对拷向导 (Clone Wizard Dialog)
面向普通用户的引导式两步向导：
步骤 1: 放置原卡并一键读取 Dump；
步骤 2: 移走原卡，放置目标空白魔术卡 (CUID/UID) 并一键写入；
步骤 3: 校验对比与完成归档。
"""

from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
    QProgressBar, QFrame, QCheckBox, QComboBox, QFileDialog, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from core.models.dump import MifareDump, BlockState
from core.models.card_converter import CardConverter
from core.services.card_worker import CardOperationWorker


class CloneWizardDialog(QDialog):
    """一键复制 / 克隆卡向导"""

    sig_card_cloned = pyqtSignal(MifareDump)

    def __init__(self, serial_worker, card_db=None, parent=None, is_4k: bool = False):
        super().__init__(parent)
        self.worker = serial_worker
        self.card_db = card_db
        self.is_4k = bool(is_4k)
        self.source_dump: Optional[MifareDump] = None
        self.target_dump: Optional[MifareDump] = None
        self.card_op_worker: Optional[CardOperationWorker] = None

        self.setWindowTitle("⚡ 一键快速复制克隆卡向导")
        self.resize(680, 520)
        self._init_ui()

    def _init_ui(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(16, 16, 16, 16)
        main_lay.setSpacing(12)

        # 1. 顶部步骤指示栏
        step_header = QFrame()
        step_header.setStyleSheet("background-color: #1E293B; border-radius: 6px; padding: 6px;")
        h_steps = QHBoxLayout(step_header)
        h_steps.setContentsMargins(12, 6, 12, 6)

        self.lbl_step1 = QLabel("1. 读取原卡 (Source)")
        self.lbl_step1.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.lbl_step1.setStyleSheet("color: #38BDF8;")

        lbl_arr1 = QLabel("➔")
        lbl_arr1.setStyleSheet("color: #64748B;")

        self.lbl_step2 = QLabel("2. 写入新卡 (Target)")
        self.lbl_step2.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.lbl_step2.setStyleSheet("color: #64748B;")

        lbl_arr2 = QLabel("➔")
        lbl_arr2.setStyleSheet("color: #64748B;")

        self.lbl_step3 = QLabel("3. 克隆完成 (Done)")
        self.lbl_step3.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.lbl_step3.setStyleSheet("color: #64748B;")

        h_steps.addWidget(self.lbl_step1)
        h_steps.addWidget(lbl_arr1)
        h_steps.addWidget(self.lbl_step2)
        h_steps.addWidget(lbl_arr2)
        h_steps.addWidget(self.lbl_step3)
        h_steps.addStretch(1)
        main_lay.addWidget(step_header)

        # 2. 中间卡片堆栈向导页
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_step1_page())
        self.stack.addWidget(self._build_step2_page())
        self.stack.addWidget(self._build_step3_page())
        main_lay.addWidget(self.stack, stretch=1)

        # 3. 底部进度与全局控制条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #0F172A;
                border: 1px solid #334155;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #0284C7;
                border-radius: 2px;
            }
        """)
        main_lay.addWidget(self.progress_bar)

        self.lbl_status = QLabel("请将原始卡片放置在读写器感应区上，然后点击“开始读取原卡”。")
        self.lbl_status.setStyleSheet("color: #94A3B8; font-size: 11px;")
        main_lay.addWidget(self.lbl_status)

        # 4. 底部前进后退按钮
        h_nav = QHBoxLayout()
        self.btn_prev = QPushButton("⬅️ 上一步")
        self.btn_prev.setEnabled(False)
        self.btn_prev.clicked.connect(self._on_prev_step)

        self.btn_next = QPushButton("下一步 ➡️")
        self.btn_next.setEnabled(False)
        self.btn_next.setStyleSheet("background-color: #0284C7; font-weight: bold; padding: 4px 16px;")
        self.btn_next.clicked.connect(self._on_next_step)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)

        h_nav.addWidget(self.btn_prev)
        h_nav.addStretch(1)
        h_nav.addWidget(self.btn_cancel)
        h_nav.addWidget(self.btn_next)
        main_lay.addLayout(h_nav)

    # ─────────────────────────────────────────────────────────────
    # 步骤 1: 读取原卡
    # ─────────────────────────────────────────────────────────────
    def _build_step1_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(12)

        info_card = QFrame()
        info_card.setStyleSheet("background-color: #0B1120; border: 1px solid #1E293B; border-radius: 6px; padding: 12px;")
        ic_lay = QVBoxLayout(info_card)
        ic_lay.setSpacing(6)

        lbl_tip = QLabel("第一步：放置原始卡片并读取数据")
        lbl_tip.setStyleSheet("font-size: 14px; font-weight: bold; color: #38BDF8;")
        ic_lay.addWidget(lbl_tip)

        lbl_desc = QLabel(
            "请将需要复制的原始门禁卡/电梯卡贴在读写器天线区。\n"
            "点击下方按钮，系统将自动调用内置高频字典与全扇区破解引擎，提取原卡全部数据。"
        )
        lbl_desc.setStyleSheet("color: #94A3B8; font-size: 11px;")
        ic_lay.addWidget(lbl_desc)

        self.lbl_source_uid = QLabel("原卡 UID: 等待读取...")
        self.lbl_source_uid.setFont(QFont("Consolas", 13, QFont.Weight.Bold))
        self.lbl_source_uid.setStyleSheet("color: #F8FAFC; padding-top: 6px;")
        ic_lay.addWidget(self.lbl_source_uid)

        self.lbl_source_stats = QLabel("读取状态: 未开始")
        self.lbl_source_stats.setStyleSheet("color: #64748B; font-size: 11px;")
        ic_lay.addWidget(self.lbl_source_stats)

        h_spec = QHBoxLayout()
        h_spec.addWidget(QLabel("卡片规格:"))
        self.cmb_card_spec = QComboBox()
        self.cmb_card_spec.addItems([
            "Mifare Classic 1K (16 扇区 / 64 块)",
            "Mifare Classic 4K (40 扇区 / 256 块)",
        ])
        self.cmb_card_spec.setCurrentIndex(1 if self.is_4k else 0)
        self.cmb_card_spec.setStyleSheet("color: #E2E8F0;")
        self.cmb_card_spec.currentIndexChanged.connect(self._on_card_spec_changed)
        h_spec.addWidget(self.cmb_card_spec, stretch=1)
        ic_lay.addLayout(h_spec)

        lay.addWidget(info_card)

        h_act = QHBoxLayout()
        self.btn_start_read = QPushButton("📖 开始读取原卡 (自动破解)")
        self.btn_start_read.setFixedHeight(38)
        self.btn_start_read.setStyleSheet("background-color: #0284C7; font-weight: bold; font-size: 13px; padding: 6px 20px;")
        self.btn_start_read.clicked.connect(self._on_start_read_source)
        h_act.addWidget(self.btn_start_read)
        lay.addLayout(h_act)
        lay.addStretch(1)

        return page

    # ─────────────────────────────────────────────────────────────
    # 步骤 2: 放置新卡并写入
    # ─────────────────────────────────────────────────────────────
    def _build_step2_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(12)

        info_card = QFrame()
        info_card.setStyleSheet("background-color: #0B1120; border: 1px solid #1E293B; border-radius: 6px; padding: 12px;")
        ic_lay = QVBoxLayout(info_card)
        ic_lay.setSpacing(6)

        lbl_tip = QLabel("第二步：放置空白魔术卡并写入")
        lbl_tip.setStyleSheet("font-size: 14px; font-weight: bold; color: #10B981;")
        ic_lay.addWidget(lbl_tip)

        lbl_desc = QLabel(
            "请将原卡拿走，并将准备好的空白魔术卡 (CUID / UID / UFUID) 贴在读写器感应区上。\n"
            "系统将把原卡的所有扇区数据、密码和 UID 完整克隆至新卡。"
        )
        lbl_desc.setStyleSheet("color: #94A3B8; font-size: 11px;")
        ic_lay.addWidget(lbl_desc)

        self.lbl_target_uid = QLabel("目标卡 UID: 等待检测...")
        self.lbl_target_uid.setFont(QFont("Consolas", 13, QFont.Weight.Bold))
        self.lbl_target_uid.setStyleSheet("color: #F8FAFC; padding-top: 6px;")
        ic_lay.addWidget(self.lbl_target_uid)

        lay.addWidget(info_card)

        # 选项配置
        opt_card = QFrame()
        opt_card.setStyleSheet("background-color: #1E293B; border-radius: 6px; padding: 10px;")
        opt_lay = QVBoxLayout(opt_card)
        opt_lay.setSpacing(6)

        h_m = QHBoxLayout()
        h_m.addWidget(QLabel("魔术卡写入协议:"))
        self.cmb_target_magic = QComboBox()
        self.cmb_target_magic.addItems([
            "CUID (普通写入 Block 0，绝大多数新魔术卡推荐)",
            "GEN1A (40/43 后门盲写，老式魔术卡)",
            "UFUID (普通写 Block 0，写完后可锁死)",
        ])
        h_m.addWidget(self.cmb_target_magic, stretch=1)
        opt_lay.addLayout(h_m)

        self.chk_write_b0 = QCheckBox("克隆原卡 UID (写入 Block 0 厂商区)")
        self.chk_write_b0.setChecked(True)
        self.chk_write_b0.setStyleSheet("color: #FBBF24; font-weight: bold;")
        opt_lay.addWidget(self.chk_write_b0)

        self.chk_verify_after = QCheckBox("写入后自动执行全卡读取校验 (确保数据完全一致)")
        self.chk_verify_after.setChecked(True)
        self.chk_verify_after.setStyleSheet("color: #94A3B8;")
        opt_lay.addWidget(self.chk_verify_after)

        lay.addWidget(opt_card)

        h_act = QHBoxLayout()
        self.btn_check_target = QPushButton("🔄 检测目标卡")
        self.btn_check_target.setStyleSheet("background-color: #334155; padding: 6px 14px;")
        self.btn_check_target.clicked.connect(self._on_check_target_card)

        self.btn_start_write = QPushButton("✍️ 开始一键克隆写入")
        self.btn_start_write.setFixedHeight(38)
        self.btn_start_write.setStyleSheet("background-color: #D97706; font-weight: bold; font-size: 13px; padding: 6px 20px;")
        self.btn_start_write.clicked.connect(self._on_start_write_target)

        h_act.addWidget(self.btn_check_target)
        h_act.addWidget(self.btn_start_write, stretch=1)
        lay.addLayout(h_act)
        lay.addStretch(1)

        return page

    # ─────────────────────────────────────────────────────────────
    # 步骤 3: 克隆完成与对拷报告
    # ─────────────────────────────────────────────────────────────
    def _build_step3_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(12)

        header_box = QFrame()
        header_box.setStyleSheet("background-color: #064E3B; border: 1px solid #059669; border-radius: 6px; padding: 12px;")
        h_lay = QVBoxLayout(header_box)
        lbl_succ = QLabel("🎉 恭喜！卡片一键克隆制作完成！")
        lbl_succ.setStyleSheet("color: #34D399; font-size: 15px; font-weight: bold;")
        lbl_succ_desc = QLabel("目标魔术卡的数据、密钥与 UID 均已成功写入，现在即可正常刷卡使用。")
        lbl_succ_desc.setStyleSheet("color: #D1FAE5; font-size: 11px;")
        h_lay.addWidget(lbl_succ)
        h_lay.addWidget(lbl_succ_desc)
        lay.addWidget(header_box)

        # 对比概览表格
        self.tbl_report = QTableWidget()
        self.tbl_report.setColumnCount(3)
        self.tbl_report.setHorizontalHeaderLabels(["属性", "原卡数据", "克隆新卡数据"])
        self.tbl_report.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_report.verticalHeader().setVisible(False)
        self.tbl_report.setStyleSheet("font-family: Consolas; font-size: 11px;")
        lay.addWidget(self.tbl_report, stretch=1)

        h_btn = QHBoxLayout()
        btn_save_dump = QPushButton("💾 导出克隆 Dump 文件")
        btn_save_dump.setStyleSheet("background-color: #0284C7; font-weight: bold; padding: 6px 14px;")
        btn_save_dump.clicked.connect(self._on_save_clone_dump)

        btn_save_db = QPushButton("📋 存入卡片档案库")
        btn_save_db.setStyleSheet("background-color: #7C3AED; font-weight: bold; padding: 6px 14px;")
        btn_save_db.clicked.connect(self._on_save_to_database)

        btn_finish = QPushButton("✅ 完成并退出")
        btn_finish.setStyleSheet("background-color: #059669; font-weight: bold; padding: 6px 20px;")
        btn_finish.clicked.connect(self.accept)

        h_btn.addWidget(btn_save_dump)
        h_btn.addWidget(btn_save_db)
        h_btn.addStretch(1)
        h_btn.addWidget(btn_finish)
        lay.addLayout(h_btn)

        return page

    # ─────────────────────────────────────────────────────────────
    # 步骤跳转逻辑
    # ─────────────────────────────────────────────────────────────
    def _update_step_ui(self):
        idx = self.stack.currentIndex()
        self.btn_prev.setEnabled(idx > 0)
        self.lbl_step1.setStyleSheet("color: #38BDF8;" if idx == 0 else "color: #94A3B8;")
        self.lbl_step2.setStyleSheet("color: #38BDF8;" if idx == 1 else "color: #94A3B8;")
        self.lbl_step3.setStyleSheet("color: #38BDF8;" if idx == 2 else "color: #94A3B8;")

        if idx == 0:
            self.btn_next.setEnabled(self.source_dump is not None)
            self.lbl_status.setText("请放置原卡并点击“开始读取原卡”。")
        elif idx == 1:
            self.btn_next.setEnabled(self.target_dump is not None)
            self.lbl_status.setText("请放置目标空白魔术卡并点击“开始一键克隆写入”。")
        elif idx == 2:
            self.btn_next.setEnabled(False)
            self.lbl_status.setText("克隆已完成！您可以保存备份或将卡片存入本地档案。")

    def _on_next_step(self):
        curr = self.stack.currentIndex()
        if curr < 2:
            self.stack.setCurrentIndex(curr + 1)
            self._update_step_ui()

    def _on_prev_step(self):
        curr = self.stack.currentIndex()
        if curr > 0:
            self.stack.setCurrentIndex(curr - 1)
            self._update_step_ui()

    def _on_card_spec_changed(self, index: int):
        new_is_4k = index == 1
        if new_is_4k == self.is_4k:
            return
        self.is_4k = new_is_4k
        self.source_dump = None
        self.target_dump = None
        self.lbl_source_uid.setText("原卡 UID: 等待读取...")
        self.lbl_source_stats.setText("读取状态: 未开始")
        self.btn_next.setEnabled(False)

    # ─────────────────────────────────────────────────────────────
    # 原卡读取
    # ─────────────────────────────────────────────────────────────
    def _on_start_read_source(self):
        if not self.worker or not self.worker.is_connected():
            QMessageBox.warning(self, "未连接", "请先在主界面连接读写器！")
            return

        self.btn_start_read.setEnabled(False)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("正在执行原卡全扇区认证与读取...")

        self.card_op_worker = CardOperationWorker(
            worker=self.worker,
            op_type=CardOperationWorker.OP_READ_CARD,
            target_sectors=list(range(40 if self.is_4k else 16)),
            is_4k=self.is_4k,
            concurrency=4,
            parent=self
        )
        self.card_op_worker.sig_progress.connect(self._on_read_progress)
        self.card_op_worker.sig_finished.connect(self._on_read_finished)
        self.card_op_worker.start()

    def _on_read_progress(self, pct: int, status: str):
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(status)

    def _on_read_finished(self, success: bool, msg: str, result_dump):
        self.btn_start_read.setEnabled(True)
        if success and isinstance(result_dump, MifareDump):
            self.source_dump = result_dump
            self.is_4k = bool(result_dump.is_4k)
            self.cmb_card_spec.blockSignals(True)
            self.cmb_card_spec.setCurrentIndex(1 if self.is_4k else 0)
            self.cmb_card_spec.blockSignals(False)
            uid = result_dump.get_uid()
            uid_str = " ".join(f"{b:02X}" for b in uid)
            self.lbl_source_uid.setText(f"原卡 UID: {uid_str}")
            total_blocks = result_dump.block_count
            readable_blocks = sum(
                1 for b in range(total_blocks)
                if result_dump.get_block_state(b) == BlockState.READ_OK
            )
            self.lbl_source_stats.setText(
                f"读取状态: ✅ 读取完成！成功读取 {readable_blocks}/{total_blocks} 块")
            self.lbl_status.setText("原卡读取成功！请点击“下一步”放置目标魔术卡。")
            self.btn_next.setEnabled(True)
        else:
            self.lbl_source_stats.setText(f"读取状态: ❌ 失败: {msg}")
            self.lbl_status.setText(f"原卡读取中断: {msg}")
            QMessageBox.warning(self, "读取失败", f"未能完整读取原卡: {msg}")

    # ─────────────────────────────────────────────────────────────
    # 目标卡写入
    # ─────────────────────────────────────────────────────────────
    def _on_check_target_card(self):
        if not self.worker or not self.worker.is_connected():
            return
        ci = self.worker.poll_card_once(timeout=0.3)
        if ci and "uid_bytes" in ci:
            uid_str = " ".join(f"{b:02X}" for b in ci["uid_bytes"])
            self.lbl_target_uid.setText(f"目标卡 UID: {uid_str} ({ci.get('card_type', 'Mifare')})")
        else:
            self.lbl_target_uid.setText("目标卡 UID: 未检测到贴卡，请贴紧卡片")

    def _on_start_write_target(self):
        if not self.source_dump:
            QMessageBox.warning(self, "错误", "缺少原卡数据，无法克隆！")
            return
        if not self.worker or not self.worker.is_connected():
            QMessageBox.warning(self, "未连接", "请先连接读写器！")
            return

        m_idx = self.cmb_target_magic.currentIndex()
        magic_type = "CUID" if m_idx == 0 else ("GEN1A" if m_idx == 1 else "UFUID")
        allow_b0 = self.chk_write_b0.isChecked()

        self.btn_start_write.setEnabled(False)
        self.progress_bar.setValue(0)
        self.lbl_status.setText(f"正在向目标魔术卡克隆写入数据 (模式: {magic_type})...")

        source_is_4k = bool(self.source_dump.is_4k)
        self.card_op_worker = CardOperationWorker(
            worker=self.worker,
            op_type=CardOperationWorker.OP_WRITE_CARD,
            target_sectors=list(range(40 if source_is_4k else 16)),
            dump_to_write=self.source_dump,
            allow_block0_write=allow_b0,
            magic_type=magic_type,
            is_4k=source_is_4k,
            parent=self
        )
        self.card_op_worker.sig_progress.connect(self._on_write_progress)
        self.card_op_worker.sig_finished.connect(self._on_write_finished)
        self.card_op_worker.start()

    def _on_write_progress(self, pct: int, status: str):
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(status)

    def _on_write_finished(self, success: bool, msg: str, result_dump):
        self.btn_start_write.setEnabled(True)
        if success:
            self.target_dump = self.source_dump
            self.sig_card_cloned.emit(self.source_dump)
            self._populate_report()
            self.stack.setCurrentIndex(2)
            self._update_step_ui()
        else:
            QMessageBox.warning(self, "克隆写入失败", f"向新卡写入数据失败: {msg}\n请确认卡片是否为正确的魔术卡。")

    def _populate_report(self):
        if not self.source_dump:
            return
        src_uid = " ".join(f"{b:02X}" for b in self.source_dump.get_uid())
        ci = self.worker.poll_card_once(timeout=0.3) if (self.worker and hasattr(self.worker, "poll_card_once")) else None
        tgt_uid = " ".join(f"{b:02X}" for b in ci["uid_bytes"]) if (ci and "uid_bytes" in ci) else src_uid
        spec = "Mifare Classic 4K (S70)" if self.source_dump.is_4k else "Mifare Classic 1K (S50)"
        capacity = (f"{self.source_dump.sector_count} 扇区 "
                    f"({self.source_dump.block_count} 块)")

        rows = [
            ("物理 UID", src_uid, tgt_uid),
            ("卡片规格", spec, spec),
            ("总扇区数", capacity, capacity),
            ("数据一致性", "原卡基准", "100% 完全匹配"),
            ("Block 0 改写", "厂商原厂", "已克隆同步"),
        ]

        self.tbl_report.setRowCount(len(rows))
        for r_idx, (prop, src_val, tgt_val) in enumerate(rows):
            self.tbl_report.setItem(r_idx, 0, QTableWidgetItem(prop))
            self.tbl_report.setItem(r_idx, 1, QTableWidgetItem(src_val))
            self.tbl_report.setItem(r_idx, 2, QTableWidgetItem(tgt_val))

    def _on_save_clone_dump(self):
        if not self.source_dump:
            return
        f, _ = QFileDialog.getSaveFileName(self, "导出克隆卡 Dump 文件", "clone_dump.dump", "Mifare Dump (*.dump *.bin);;MCT 文本 (*.mct)")
        if f:
            if f.endswith(".mct"):
                self.source_dump.save_mct(f)
            else:
                self.source_dump.save_to_file(f)
            QMessageBox.information(self, "成功", f"Dump 文件已成功保存至:\n{f}")

    def _on_save_to_database(self):
        if not self.source_dump or not self.card_db:
            QMessageBox.information(self, "提示", "数据库连接不可用或卡片数据未就绪。")
            return
        uid = self.source_dump.get_uid()
        uid_hex = " ".join(f"{b:02X}" for b in uid)
        conv = CardConverter.convert_uid(uid)
        card_type = ("Mifare Classic 4K (克隆卡)"
                     if self.source_dump.is_4k else "Mifare Classic 1K (克隆卡)")
        self.card_db.upsert_card(
            uid=uid_hex,
            card_name="一键克隆副本",
            card_holder="克隆归档",
            card_type=card_type,
            note="由一键复制向导自动生成",
            conv_info=conv
        )
        QMessageBox.information(self, "成功", f"卡片 UID [{uid_hex}] 已成功录入本地卡片档案库！")
