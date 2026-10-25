# -*- coding: utf-8 -*-
"""
PyMifareTool - 魔术卡高级工具箱 (Magic Card Specialist Dialog)
支持 UID/CUID/UFUID/GEN1A 卡片改写 Block 0、随机重置 UID、全卡出厂化救砖、UFUID 永久锁死
"""

from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QGroupBox, QGridLayout, QComboBox, QTabWidget, QCheckBox,
    QMessageBox, QFrame, QProgressBar, QTextEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from core.models.dump import MifareDump
from core.models.card_converter import CardConverter


class MagicWorkerThread(QThread):
    """魔术卡底层长耗时操作后台工作线程 (严格遵循硬件红线 2 独占互斥)"""
    sig_log = pyqtSignal(str)
    sig_progress = pyqtSignal(int, str)
    sig_finished = pyqtSignal(bool, str)

    def __init__(self, serial_worker, action: str, params: dict, parent=None):
        super().__init__(parent)
        self.worker = serial_worker
        self.action = action
        self.params = params

    def run(self):
        if not self.worker or not self.worker.is_connected():
            self.sig_finished.emit(False, "读写器尚未连接，无法执行硬件操作。")
            return

        self.worker.set_exclusive(True)
        try:
            if self.action == "write_block0":
                self._do_write_block0()
            elif self.action == "factory_wipe":
                self._do_factory_wipe()
            elif self.action == "lock_ufuid":
                self._do_lock_ufuid()
            else:
                self.sig_finished.emit(False, f"未知的操作动作: {self.action}")
        except Exception as e:
            self.sig_log.emit(f"❌ 操作异常: {e}")
            self.sig_finished.emit(False, str(e))
        finally:
            self.worker.set_exclusive(False)

    def _do_write_block0(self):
        b0_bytes = self.params["block0_bytes"]
        magic_type = self.params["magic_type"]
        key_a = self.params.get("key_a", b"\xFF" * 6)

        self.sig_progress.emit(10, f"正在准备改写 Block 0 ({magic_type} 模式)...")
        self.sig_log.emit(f"📤 准备写入 Block 0: {' '.join(f'{b:02X}' for b in b0_bytes)}")

        # 若是 CUID / UFUID 模式，写 Block 0 通常需要先认证扇区 0
        if magic_type in ("CUID", "UFUID"):
            self.sig_progress.emit(30, "正在进行扇区 0 密钥认证...")
            auth_ok = self.worker.authenticate(0, "A", key_a, timeout=0.4)
            if not auth_ok:
                # 尝试默认出厂密钥 FFFFFFFFFFFF
                if key_a != b"\xFF" * 6:
                    auth_ok = self.worker.authenticate(0, "A", b"\xFF" * 6, timeout=0.4)
            if not auth_ok:
                self.sig_log.emit("⚠️ 扇区 0 认证未响应，将尝试直接下发写指令...")

        self.sig_progress.emit(60, f"下发 Block 0 写入指令 ({magic_type})...")
        ok = self.worker.write_magic_block0(b0_bytes, magic_type=magic_type, timeout=0.6)

        if ok:
            self.sig_progress.emit(100, "Block 0 写入成功！")
            self.sig_log.emit("✨ Block 0 改写成功！新卡号已生效。")
            self.sig_finished.emit(True, "Block 0 (UID) 改写成功！")
        else:
            self.sig_progress.emit(100, "Block 0 写入失败")
            self.sig_log.emit(f"❌ 写入 Block 0 失败，请确认卡片是否为正品 {magic_type} 魔术卡。")
            self.sig_finished.emit(False, f"改写失败: 请确认卡片是否为 {magic_type} 魔术卡或钥匙是否正确。")

    def _do_factory_wipe(self):
        total_sectors = 40 if self.params.get("is_4k", False) else 16
        magic_type = self.params.get("magic_type", "CUID")
        wipe_b0 = self.params.get("wipe_block0", False)
        b0_bytes = self.params.get("block0_bytes")
        current_keys = self.params.get("known_keys", {})

        self.sig_progress.emit(5, "开始执行全卡出厂化清空...")
        self.sig_log.emit(f"🚀 开始出厂化清空共 {total_sectors} 个扇区 (魔术模式: {magic_type})...")

        factory_dump = MifareDump(is_4k=(total_sectors == 40))
        factory_dump.initialize_factory()

        if not wipe_b0 and b0_bytes and len(b0_bytes) == 16:
            factory_dump.set_block(0, b0_bytes)

        # 遍历全扇区写入
        success_sectors = 0
        for s in range(total_sectors):
            pct = int((s / total_sectors) * 90) + 5
            self.sig_progress.emit(pct, f"正在出厂化扇区 S{s:02d} / S{total_sectors - 1:02d} ...")

            first_block = s * 4 if s < 32 else 128 + (s - 32) * 16
            blocks_in_sec = 4 if s < 32 else 16

            # 认证
            candidate_keys = [b"\xFF" * 6]
            if s in current_keys:
                candidate_keys.insert(0, current_keys[s])

            authed = False
            for k in candidate_keys:
                if self.worker.authenticate(first_block, "A", k, timeout=0.3):
                    authed = True
                    break
                if self.worker.authenticate(first_block, "B", k, timeout=0.3):
                    authed = True
                    break

            if not authed and magic_type != "GEN1A":
                self.sig_log.emit(f"⚠️ 扇区 S{s:02d} 认证失败，跳过写入")
                continue

            sec_ok = True
            for b_rel in range(blocks_in_sec):
                b_abs = first_block + b_rel
                if b_abs == 0:
                    if wipe_b0:
                        b0_data = factory_dump.get_block(0)
                        if not self.worker.write_magic_block0(b0_data, magic_type=magic_type, timeout=0.5):
                            self.sig_log.emit("⚠️ Block 0 写入失败")
                    continue

                b_data = factory_dump.get_block(b_abs)
                if not self.worker.write_block(b_abs, b_data, timeout=0.35):
                    sec_ok = False
                    self.sig_log.emit(f"❌ 块 {b_abs} (S{s:02d}) 写入失败")

            if sec_ok:
                success_sectors += 1

        self.sig_progress.emit(100, f"出厂化清空完成 ({success_sectors}/{total_sectors} 扇区)")
        self.sig_log.emit(f"✨ 全卡出厂化完成: 成功重置 {success_sectors}/{total_sectors} 个扇区。")
        self.sig_finished.emit(True, f"出厂化清空完成！成功写入 {success_sectors}/{total_sectors} 扇区。")

    def _do_lock_ufuid(self):
        self.sig_progress.emit(20, "正在下发 UFUID 永久固化锁死指令...")
        self.sig_log.emit("🔒 正在向卡片发送 UFUID 固化指令 (0xE0 / 0xE1)...")

        ok = self.worker.lock_ufuid_card(timeout=0.6)
        if ok:
            self.sig_progress.emit(100, "UFUID 锁死成功！")
            self.sig_log.emit("✨ UFUID 卡片锁死成功！该卡已永久固化为普通 M1 只读 UID 卡。")
            self.sig_finished.emit(True, "UFUID 锁死成功！该卡已固化为普通 M1 卡。")
        else:
            self.sig_progress.emit(100, "UFUID 锁死失败")
            self.sig_log.emit("❌ UFUID 锁死失败，请确认卡片是否支持 UFUID 锁死协议。")
            self.sig_finished.emit(False, "UFUID 锁死失败，卡片可能并非处于可锁死的 UFUID 状态。")


class MagicCardDialog(QDialog):
    """魔术卡专用高级工具箱窗口"""

    def __init__(self, serial_worker, current_dump: Optional[MifareDump] = None, parent=None):
        super().__init__(parent)
        self.worker = serial_worker
        self.current_dump = current_dump
        self.active_thread: Optional[MagicWorkerThread] = None

        self.setWindowTitle("🪄 魔术卡高级工具箱 (UID / CUID / UFUID / GEN1A)")
        self.resize(720, 560)
        self._init_ui()
        self._update_card_info_header()

    def _init_ui(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(12, 12, 12, 12)
        main_lay.setSpacing(10)

        # 1. 顶部当前卡片物理状态卡片
        info_box = QFrame()
        info_box.setStyleSheet("background-color: #1E293B; border-radius: 6px; padding: 6px;")
        info_lay = QHBoxLayout(info_box)
        info_lay.setContentsMargins(8, 6, 8, 6)

        lbl_icon = QLabel("💳")
        lbl_icon.setFont(QFont("Segoe UI Emoji", 20))
        info_lay.addWidget(lbl_icon)

        v_info = QVBoxLayout()
        v_info.setSpacing(2)
        self.lbl_card_title = QLabel("当前卡片: 检测中...")
        self.lbl_card_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #38BDF8;")
        self.lbl_card_details = QLabel("UID: -- -- -- -- | SAK: -- | ATQA: --")
        self.lbl_card_details.setStyleSheet("font-size: 11px; color: #94A3B8; font-family: Consolas;")
        v_info.addWidget(self.lbl_card_title)
        v_info.addWidget(self.lbl_card_details)
        info_lay.addLayout(v_info, stretch=1)

        self.btn_recheck = QPushButton("🔄 重新寻卡")
        self.btn_recheck.setStyleSheet("background-color: #334155; font-size: 11px; padding: 4px 12px;")
        self.btn_recheck.clicked.connect(self._on_recheck_card)
        info_lay.addWidget(self.btn_recheck)

        main_lay.addWidget(info_box)

        # 2. 功能 Tab 分区
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_uid_write_tab(), "✍️ UID 写号与改号")
        self.tabs.addTab(self._build_factory_wipe_tab(), "🔄 全卡出厂化 (救砖)")
        self.tabs.addTab(self._build_lock_ufuid_tab(), "🔒 固化锁死 UFUID")
        main_lay.addWidget(self.tabs, stretch=1)

        # 3. 底部进度与操作日志
        prog_box = QVBoxLayout()
        prog_box.setSpacing(4)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #0F172A;
                border: 1px solid #334155;
                border-radius: 4px;
                text-align: center;
                color: #F8FAFC;
                font-size: 10px;
            }
            QProgressBar::chunk {
                background-color: #0284C7;
                border-radius: 3px;
            }
        """)
        prog_box.addWidget(self.progress_bar)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFixedHeight(90)
        self.txt_log.setFont(QFont("Consolas", 9))
        self.txt_log.setStyleSheet(
            "background-color: #050B14; color: #38BDF8; border: 1px solid #1E293B; border-radius: 4px;"
        )
        self.txt_log.setPlaceholderText("魔术卡操作交互日志将在此呈现...")
        prog_box.addWidget(self.txt_log)
        main_lay.addLayout(prog_box)

    # ─────────────────────────────────────────────────────────────
    # Tab 1: UID 写号与改号 (Block 0)
    # ─────────────────────────────────────────────────────────────
    def _build_uid_write_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(8)

        grid.addWidget(QLabel("目标 UID (4字节 Hex):"), 0, 0)
        self.txt_target_uid = QLineEdit()
        self.txt_target_uid.setFont(QFont("Consolas", 11))
        self.txt_target_uid.setPlaceholderText("例如: D7 7E A0 DF 或 12345678")
        self.txt_target_uid.textChanged.connect(self._update_b0_preview)
        grid.addWidget(self.txt_target_uid, 0, 1)

        btn_rand_uid = QPushButton("🎲 随机 UID")
        btn_rand_uid.setStyleSheet("background-color: #7C3AED; font-weight: bold; padding: 4px 10px;")
        btn_rand_uid.clicked.connect(self._on_random_uid)
        grid.addWidget(btn_rand_uid, 0, 2)

        btn_curr_uid = QPushButton("📋 读取当前卡")
        btn_curr_uid.setStyleSheet("background-color: #334155; padding: 4px 10px;")
        btn_curr_uid.clicked.connect(self._on_fill_from_current)
        grid.addWidget(btn_curr_uid, 0, 3)

        grid.addWidget(QLabel("SAK / ATQA / 厂商字节:"), 1, 0)
        h_aux = QHBoxLayout()
        h_aux.setSpacing(6)
        self.txt_sak = QLineEdit("08")
        self.txt_sak.setFixedWidth(40)
        self.txt_sak.setFont(QFont("Consolas", 10))
        self.txt_sak.setToolTip("SAK 控制字节 (默认 08 代表 S50 1K)")
        self.txt_sak.textChanged.connect(self._update_b0_preview)
        h_aux.addWidget(QLabel("SAK:"))
        h_aux.addWidget(self.txt_sak)

        self.txt_atqa = QLineEdit("04 00")
        self.txt_atqa.setFixedWidth(65)
        self.txt_atqa.setFont(QFont("Consolas", 10))
        self.txt_atqa.setToolTip("ATQA 卡片应答字节 (默认 04 00)")
        self.txt_atqa.textChanged.connect(self._update_b0_preview)
        h_aux.addWidget(QLabel("ATQA:"))
        h_aux.addWidget(self.txt_atqa)

        self.txt_manuf = QLineEdit("62 63 64 65 66 67 68 69")
        self.txt_manuf.setFont(QFont("Consolas", 10))
        self.txt_manuf.setToolTip("厂商保留数据字节 (8 字节)")
        self.txt_manuf.textChanged.connect(self._update_b0_preview)
        h_aux.addWidget(QLabel("厂商数据:"))
        h_aux.addWidget(self.txt_manuf, stretch=1)
        grid.addLayout(h_aux, 1, 1, 1, 3)

        grid.addWidget(QLabel("Block 0 预览 (含BCC):"), 2, 0)
        self.lbl_b0_preview = QLabel("00 00 00 00 00 08 04 00 62 63 64 65 66 67 68 69")
        self.lbl_b0_preview.setFont(QFont("Consolas", 10))
        self.lbl_b0_preview.setStyleSheet(
            "background-color: #0B1120; color: #10B981; padding: 6px; border: 1px dashed #334155; border-radius: 4px;"
        )
        grid.addWidget(self.lbl_b0_preview, 2, 1, 1, 3)

        grid.addWidget(QLabel("魔术卡写入协议:"), 3, 0)
        self.cmb_magic_mode = QComboBox()
        self.cmb_magic_mode.addItems([
            "CUID (普通指令写入，需扇区0密钥，现代主流魔术卡)",
            "GEN1A (40/43 后门盲写，无需密码，经典老式魔术卡)",
            "UFUID (普通指令写入，改写后可锁定固化为普通卡)",
        ])
        grid.addWidget(self.cmb_magic_mode, 3, 1, 1, 2)

        # 扇区 0 密钥 A (针对 CUID/UFUID)
        self.txt_sec0_key = QLineEdit("FFFFFFFFFFFF")
        self.txt_sec0_key.setFont(QFont("Consolas", 10))
        self.txt_sec0_key.setToolTip("扇区 0 的 Key A (默认为出厂密码 FFFFFFFFFFFF)")
        grid.addWidget(self.txt_sec0_key, 3, 3)

        lay.addLayout(grid)

        # 动作按钮
        h_btn = QHBoxLayout()
        h_btn.addStretch(1)
        btn_write_b0 = QPushButton("✍️ 立即写入 Block 0 (改号)")
        btn_write_b0.setFixedHeight(34)
        btn_write_b0.setStyleSheet("background-color: #D97706; color: white; font-weight: bold; padding: 6px 20px;")
        btn_write_b0.clicked.connect(self._on_write_block0)
        h_btn.addWidget(btn_write_b0)
        lay.addLayout(h_btn)
        lay.addStretch(1)

        return tab

    # ─────────────────────────────────────────────────────────────
    # Tab 2: 全卡出厂化救砖
    # ─────────────────────────────────────────────────────────────
    def _build_factory_wipe_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        warn_box = QFrame()
        warn_box.setStyleSheet("background-color: #451A03; border: 1px solid #B45309; border-radius: 6px; padding: 8px;")
        w_lay = QVBoxLayout(warn_box)
        lbl_w = QLabel("⚠️ 出厂化清空说明 (救砖功能):")
        lbl_w.setStyleSheet("color: #FBBF24; font-weight: bold; font-size: 12px;")
        lbl_w_desc = QLabel(
            "此操作将把卡片全部扇区恢复为出厂空卡：\n"
            "• 扇区密码 A/B 全部恢复为 FFFFFFFFFFFF\n"
            "• 扇区控制字恢复为标准出厂 FF 07 80 69\n"
            "• 所有数据块全部清零 (00 00 ...)\n"
            "• 可用于挽救误改数据或被破坏控制字导致的读写异常。"
        )
        lbl_w_desc.setStyleSheet("color: #FEF3C7; font-size: 11px;")
        w_lay.addWidget(lbl_w)
        w_lay.addWidget(lbl_w_desc)
        lay.addWidget(warn_box)

        grid = QGridLayout()
        grid.setSpacing(8)

        grid.addWidget(QLabel("卡片规格:"), 0, 0)
        self.cmb_wipe_model = QComboBox()
        self.cmb_wipe_model.addItems(["1K (S50 - 共 16 扇区)", "4K (S70 - 共 40 扇区)"])
        grid.addWidget(self.cmb_wipe_model, 0, 1)

        grid.addWidget(QLabel("魔术卡模式:"), 1, 0)
        self.cmb_wipe_magic = QComboBox()
        self.cmb_wipe_magic.addItems(["CUID / 普通卡", "GEN1A (后门盲写模式)"])
        grid.addWidget(self.cmb_wipe_magic, 1, 1)

        self.chk_wipe_b0 = QCheckBox("同时将 Block 0 恢复为出厂 UID (01 02 03 04)")
        self.chk_wipe_b0.setStyleSheet("color: #F8FAFC; font-size: 11px;")
        self.chk_wipe_b0.setChecked(False)
        grid.addWidget(self.chk_wipe_b0, 2, 0, 1, 2)

        lay.addLayout(grid)

        h_btn = QHBoxLayout()
        h_btn.addStretch(1)
        btn_wipe = QPushButton("⚠️ 开始全卡出厂化清空")
        btn_wipe.setFixedHeight(34)
        btn_wipe.setStyleSheet("background-color: #DC2626; color: white; font-weight: bold; padding: 6px 20px;")
        btn_wipe.clicked.connect(self._on_start_factory_wipe)
        h_btn.addWidget(btn_wipe)
        lay.addLayout(h_btn)
        lay.addStretch(1)

        return tab

    # ─────────────────────────────────────────────────────────────
    # Tab 3: 固化锁死 UFUID
    # ─────────────────────────────────────────────────────────────
    def _build_lock_ufuid_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        warn_box = QFrame()
        warn_box.setStyleSheet("background-color: #7F1D1D; border: 1px solid #EF4444; border-radius: 6px; padding: 10px;")
        w_lay = QVBoxLayout(warn_box)
        lbl_w = QLabel("🚨 UFUID 永久锁死警告 (绝对不可逆):")
        lbl_w.setStyleSheet("color: #FCA5A5; font-weight: bold; font-size: 13px;")
        lbl_w_desc = QLabel(
            "UFUID (Ultra Fast UID) 卡具备防探测锁定特性：\n\n"
            "1. 锁定前：卡片表现为普通魔术卡，可通过普通指令随时改写 Block 0 (UID)；\n"
            "2. 锁定后：卡内主控芯片熔丝固化或进入只读 OTP 锁死状态，Block 0 将被彻底永久锁死，"
            "转变为普通的只读 M1 IC 卡；\n"
            "3. 锁定后的卡片能够完美绕过任何门禁、梯控系统对魔术卡后门指令的防火墙探测！\n\n"
            "⚠️ 注意：此操作为硬件级单向固化，锁定后卡片将永远无法再次改号！"
        )
        lbl_w_desc.setStyleSheet("color: #FEE2E2; font-size: 11px;")
        w_lay.addWidget(lbl_w)
        w_lay.addWidget(lbl_w_desc)
        lay.addWidget(warn_box)

        self.chk_confirm_lock = QCheckBox("我已充分理解上述警告，确认要将此 UFUID 卡永久锁死为普通卡")
        self.chk_confirm_lock.setStyleSheet("color: #FBBF24; font-weight: bold; font-size: 11px;")
        lay.addWidget(self.chk_confirm_lock)

        h_btn = QHBoxLayout()
        h_btn.addStretch(1)
        self.btn_lock_ufuid = QPushButton("🔒 立即锁死 UFUID 卡")
        self.btn_lock_ufuid.setFixedHeight(36)
        self.btn_lock_ufuid.setStyleSheet("background-color: #991B1B; color: white; font-weight: bold; padding: 6px 24px;")
        self.btn_lock_ufuid.clicked.connect(self._on_lock_ufuid)
        h_btn.addWidget(self.btn_lock_ufuid)
        lay.addLayout(h_btn)
        lay.addStretch(1)

        return tab

    # ─────────────────────────────────────────────────────────────
    # 事件处理
    # ─────────────────────────────────────────────────────────────
    def _update_card_info_header(self):
        if not self.worker or not self.worker.is_connected():
            self.lbl_card_title.setText("读写器状态: 尚未连接")
            self.lbl_card_details.setText("请先在主窗口连接读写器。")
            return

        card_info = self.worker.poll_card_once(timeout=0.3)
        if card_info and "uid_bytes" in card_info:
            uid = card_info["uid_bytes"]
            sak = card_info.get("sak", 0x08)
            atqa = card_info.get("atqa", 0x0400)
            uid_hex = " ".join(f"{b:02X}" for b in uid)
            self.lbl_card_title.setText(f"当前在场卡片: {card_info.get('card_type', 'Mifare Classic')}")
            self.lbl_card_details.setText(f"UID: {uid_hex} | SAK: {sak:02X} | ATQA: {atqa:04X}")
        else:
            self.lbl_card_title.setText("当前在场卡片: 未检测到贴卡")
            self.lbl_card_details.setText("请将目标 Mifare / 魔术卡紧贴在读写器感应区上。")

    def _on_recheck_card(self):
        self._update_card_info_header()
        self.txt_log.append("🔄 刷新在场卡片状态完成。")

    def _on_random_uid(self):
        new_uid = CardConverter.generate_random_uid(4)
        self.txt_target_uid.setText(" ".join(f"{b:02X}" for b in new_uid))

    def _on_fill_from_current(self):
        if not self.worker or not self.worker.is_connected():
            return
        card_info = self.worker.poll_card_once(timeout=0.3)
        if card_info and "uid_bytes" in card_info:
            uid = card_info["uid_bytes"]
            self.txt_target_uid.setText(" ".join(f"{b:02X}" for b in uid))
            if "sak" in card_info:
                self.txt_sak.setText(f"{card_info['sak']:02X}")
            if "atqa" in card_info:
                self.txt_atqa.setText(f"{(card_info['atqa'] >> 8) & 0xFF:02X} {card_info['atqa'] & 0xFF:02X}")

    def _update_b0_preview(self):
        uid_str = self.txt_target_uid.text().strip().replace(" ", "")
        try:
            uid_bytes = bytes.fromhex(uid_str) if uid_str else b"\x00" * 4
            if len(uid_bytes) != 4:
                self.lbl_b0_preview.setText("UID 长度必须为 4 字节 (8 位十六进制)")
                return
        except ValueError:
            self.lbl_b0_preview.setText("UID 包含非法的十六进制字符")
            return

        try:
            sak = int(self.txt_sak.text().strip().replace(" ", ""), 16)
        except Exception:
            sak = 0x08

        try:
            atqa_bytes = bytes.fromhex(self.txt_atqa.text().strip().replace(" ", ""))
            atqa = int.from_bytes(atqa_bytes, "big") if atqa_bytes else 0x0400
        except Exception:
            atqa = 0x0400

        try:
            manuf = bytes.fromhex(self.txt_manuf.text().strip().replace(" ", ""))
            if len(manuf) < 8:
                manuf = manuf.ljust(8, b"\x00")
            elif len(manuf) > 8:
                manuf = manuf[:8]
        except Exception:
            manuf = bytes.fromhex("62 63 64 65 66 67 68 69")

        b0 = CardConverter.build_block0(uid_bytes, sak=sak, atqa=atqa, manufacturer_data=manuf)
        self.lbl_b0_preview.setText(" ".join(f"{b:02X}" for b in b0))

    def _on_write_block0(self):
        b0_text = self.lbl_b0_preview.text().strip().replace(" ", "")
        try:
            b0_bytes = bytes.fromhex(b0_text)
            if len(b0_bytes) != 16:
                QMessageBox.warning(self, "参数错误", "Block 0 预览数据不合法，必须为 16 字节！")
                return
        except Exception:
            QMessageBox.warning(self, "参数错误", "Block 0 数据格式无效！")
            return

        mode_idx = self.cmb_magic_mode.currentIndex()
        magic_type = "CUID" if mode_idx == 0 else ("GEN1A" if mode_idx == 1 else "UFUID")

        key_a_str = self.txt_sec0_key.text().strip().replace(" ", "")
        try:
            key_a = bytes.fromhex(key_a_str)
            if len(key_a) != 6:
                key_a = b"\xFF" * 6
        except Exception:
            key_a = b"\xFF" * 6

        self._start_worker("write_block0", {
            "block0_bytes": b0_bytes,
            "magic_type": magic_type,
            "key_a": key_a,
        })

    def _on_start_factory_wipe(self):
        res = QMessageBox.question(
            self,
            "确认全卡出厂化",
            "确定要对当前卡片执行全卡出厂化清空操作吗？\n此操作将重置所有扇区密码与数据，过程不可撤销！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if res != QMessageBox.StandardButton.Yes:
            return

        is_4k = self.cmb_wipe_model.currentIndex() == 1
        magic_type = "CUID" if self.cmb_wipe_magic.currentIndex() == 0 else "GEN1A"
        wipe_b0 = self.chk_wipe_b0.isChecked()

        known_keys = {}
        if self.current_dump:
            for s in range(40 if self.current_dump.is_4k else 16):
                ka = self.current_dump.get_key_a(s)
                if ka and ka != b"\x00" * 6:
                    known_keys[s] = ka

        b0_bytes = None
        if not wipe_b0:
            if self.current_dump:
                b0_bytes = self.current_dump.get_block(0)
            elif self.worker:
                ci = self.worker.poll_card_once()
                if ci and "uid_bytes" in ci:
                    b0_bytes = CardConverter.build_block0(ci["uid_bytes"])

        self._start_worker("factory_wipe", {
            "is_4k": is_4k,
            "magic_type": magic_type,
            "wipe_block0": wipe_b0,
            "block0_bytes": b0_bytes,
            "known_keys": known_keys,
        })

    def _on_lock_ufuid(self):
        if not self.chk_confirm_lock.isChecked():
            QMessageBox.warning(self, "确认警告", "请先勾选下方免责声明，确认知悉 UFUID 锁死为永久不可逆操作！")
            return

        res = QMessageBox.critical(
            self,
            "终极确认: 永久固化 UFUID",
            "警告：执行此操作后，卡片将永久变为只读普通 M1 卡，今后将无法再修改 UID！\n\n是否立即锁死？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if res != QMessageBox.StandardButton.Yes:
            return

        self._start_worker("lock_ufuid", {})

    def _start_worker(self, action: str, params: dict):
        if self.active_thread and self.active_thread.isRunning():
            QMessageBox.information(self, "提示", "已有操作在后台执行中，请稍候。")
            return

        self.progress_bar.setValue(0)
        self.active_thread = MagicWorkerThread(self.worker, action, params, parent=self)
        self.active_thread.sig_log.connect(lambda msg: self.txt_log.append(msg))
        self.active_thread.sig_progress.connect(self._on_worker_progress)
        self.active_thread.sig_finished.connect(self._on_worker_finished)
        self.active_thread.start()

    def _on_worker_progress(self, pct: int, status: str):
        self.progress_bar.setValue(pct)

    def _on_worker_finished(self, success: bool, msg: str):
        self.progress_bar.setValue(100 if success else 0)
        if success:
            QMessageBox.information(self, "成功", msg)
            self._update_card_info_header()
        else:
            QMessageBox.warning(self, "失败", msg)
