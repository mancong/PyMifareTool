# -*- coding: utf-8 -*-
"""
PyMifareTool - 密码字典库 / Access Bits 完整解析器 / 卡号换算器 / 指令调试终端
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTextEdit, QGroupBox, QGridLayout, QComboBox, QTabWidget, QPlainTextEdit,
    QScrollArea, QFrame, QCheckBox, QFileDialog, QMessageBox
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal
from core.protocol import AccessBitsDecoder, AccessBitsEncoder
from core.key_manager import KeyManager

# 经典行业高频默认密钥字典 (门禁、梯控、一卡通、水控机)
COMMON_KEYS = [
    ("FFFFFFFFFFFF", "标准出厂默认空卡密码 (工厂缺省)"),
    ("A0A1A2A3A4A5", "NXP 官方标准传输密码 (MAD 目录块)"),
    ("D3F7D3F7D3F7", "NXP 官方 NFC Forum 标准 Key"),
    ("000000000000", "全零密码 (常见于清空卡或特殊测试)"),
    ("A0B0C0D0E0F0", "通用测试密码 A"),
    ("A1B2C3D4E5F6", "通用测试密码 B"),
    ("1A2B3C4D5E6F", "通用梯控高频默认密码"),
    ("B0B1B2B3B4B5", "某品牌门禁系统默认密钥"),
    ("4D3A99C351DD", "常见校园一卡通默认扇区密钥"),
    ("123456789ABC", "简易序列密钥"),
    ("010203040506", "顺序密钥"),
    ("AABBCCDDEEFF", "对称密钥"),
    ("714C5C886E97", "某品牌水控机默认密钥"),
    ("587EE5F9350F", "常见梯控系统密钥"),
    ("A0478CC39091", "某品牌门禁密钥"),
    ("FC00018778F7", "某品牌一卡通密钥"),
]

DATA_BLOCK_MODES = [
    ((0, 0, 0), "模式0 (000): KeyAB读写/增减值 (出厂默认)"),
    ((0, 1, 0), "模式1 (010): [只读] KeyAB读及减值/不可写"),
    ((1, 0, 0), "模式2 (100): KeyAB读 / 仅KeyB可写"),
    ((1, 1, 0), "模式3 (110): KeyAB读 / KeyB写及增值 / 任意Key减值"),
    ((0, 0, 1), "模式4 (001): KeyAB读及减值 / 永不可写"),
    ((0, 1, 1), "模式5 (011): 仅KeyB读写 / 不可增减值"),
    ((1, 0, 1), "模式6 (101): [只读] 仅KeyB可读 / 永不可写"),
    ((1, 1, 1), "模式7 (111): 完全锁死 (无任何读写权限)"),
]

TRAILER_MODES = [
    ((0, 0, 0), "模式0 (000): 出厂默认 (KeyA写KeyA/KeyB, 可读控制字/KeyB)"),
    ((0, 1, 0), "模式1 (010): 只读保护 (所有Key和控制字不可写)"),
    ((1, 0, 0), "模式2 (100): KeyB写KeyA/KeyB, 控制字只读"),
    ((1, 1, 0), "模式3 (110): 全锁 (控制字可读, 均不可改)"),
    ((0, 0, 1), "模式4 (001): KeyA可修改一切 (含控制字)"),
    ((0, 1, 1), "模式5 (011): KeyB可修改一切 (含控制字)"),
    ((1, 0, 1), "模式6 (101): KeyB可改控制字, KeyA/B均不可改"),
    ((1, 1, 1), "模式7 (111): 完全锁死 (一切均不可改)"),
]


class DictionaryToolsWidget(QWidget):
    # 发送原始 Hex 指令信号 (供主窗口连接)
    sig_send_hex = pyqtSignal(bytes)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 使用内嵌 Tab 分区 (紧凑自适应排版)
        tabs = QTabWidget()

        # Tab 1: Access Bits 解析器
        tabs.addTab(self._build_access_bits_tab(), "🛡️ 权限解析器")
        # Tab 2: 卡号换算器
        tabs.addTab(self._build_converter_tab(), "🔢 卡号换算器")
        # Tab 3: 密码字典库
        tabs.addTab(self._build_dictionary_tab(), "📖 密码字典库")
        # Tab 4: 指令调试终端
        tabs.addTab(self._build_debug_terminal_tab(), "📟 指令终端")

        tabs.setTabToolTip(0, "Access Bits 控制字权限解析与可视化生成")
        tabs.setTabToolTip(1, "正序/倒序/8H10D/WG26/WG34 卡号多标准换算")
        tabs.setTabToolTip(2, "M1 卡常见默认行业高频密钥库")
        tabs.setTabToolTip(3, "底盘原生 Hex 指令收发与调试")

        layout.addWidget(tabs)

    # ─────────────────────────────────────────────────
    # Tab 1: Access Bits 完整解析器
    # ─────────────────────────────────────────────────
    def _build_access_bits_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # 输入区
        input_box = QHBoxLayout()
        input_box.addWidget(QLabel("控制字 Hex (4 字节, 例 FF 07 80 69):"))
        self.txt_access_hex = QLineEdit("FF 07 80 69")
        self.txt_access_hex.setFont(QFont("Consolas", 11))
        self.txt_access_hex.setFixedWidth(180)
        btn_decode = QPushButton("🔍 解析权限")
        btn_decode.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; padding: 6px 14px;")
        btn_decode.clicked.connect(self._decode_access_bits)
        input_box.addWidget(self.txt_access_hex)
        input_box.addWidget(btn_decode)
        input_box.addStretch()

        # 常用预设快捷按钮
        presets = QHBoxLayout()
        presets.addWidget(QLabel("快捷预设:"))
        for name, val in [("出厂默认", "FF 07 80 69"), ("只读保护", "08 77 8F 69"),
                          ("KeyB管控", "78 77 88 69"), ("全锁", "88 00 FF 69")]:
            btn = QPushButton(name)
            btn.setFixedWidth(80)
            btn.clicked.connect(lambda _, v=val: (self.txt_access_hex.setText(v), self._decode_access_bits()))
            presets.addWidget(btn)
        presets.addStretch()

        # 交互式选择器 (对标 MifareOneTool S50HTool)
        grp_builder = QGroupBox("⚙️ 交互式权限选择器 (可视化生成合法控制字，自动计算反码校验)")
        grp_builder.setStyleSheet("QGroupBox { font-weight: bold; color: #38BDF8; }")
        grid_b = QGridLayout(grp_builder)

        grid_b.addWidget(QLabel("Block 0 权限:"), 0, 0)
        self.cmb_b0 = QComboBox()
        for mode, text in DATA_BLOCK_MODES:
            self.cmb_b0.addItem(text, mode)
        grid_b.addWidget(self.cmb_b0, 0, 1)

        grid_b.addWidget(QLabel("Block 1 权限:"), 1, 0)
        self.cmb_b1 = QComboBox()
        for mode, text in DATA_BLOCK_MODES:
            self.cmb_b1.addItem(text, mode)
        grid_b.addWidget(self.cmb_b1, 1, 1)

        grid_b.addWidget(QLabel("Block 2 权限:"), 2, 0)
        self.cmb_b2 = QComboBox()
        for mode, text in DATA_BLOCK_MODES:
            self.cmb_b2.addItem(text, mode)
        grid_b.addWidget(self.cmb_b2, 2, 1)

        grid_b.addWidget(QLabel("尾块/Key权限:"), 3, 0)
        self.cmb_b3 = QComboBox()
        for mode, text in TRAILER_MODES:
            self.cmb_b3.addItem(text, mode)
        grid_b.addWidget(self.cmb_b3, 3, 1)

        self.cmb_b0.currentIndexChanged.connect(self._on_combo_mode_changed)
        self.cmb_b1.currentIndexChanged.connect(self._on_combo_mode_changed)
        self.cmb_b2.currentIndexChanged.connect(self._on_combo_mode_changed)
        self.cmb_b3.currentIndexChanged.connect(self._on_combo_mode_changed)

        # 解析结果
        self.txt_access_result = QTextEdit()
        self.txt_access_result.setReadOnly(True)
        self.txt_access_result.setFont(QFont("Consolas", 10))
        self.txt_access_result.setStyleSheet("background-color: #0B1120; color: #E2E8F0; border: 1px solid #334155;")

        layout.addLayout(input_box)
        layout.addLayout(presets)
        layout.addWidget(grp_builder)
        layout.addWidget(self.txt_access_result)

        # 初始调用
        self._decode_access_bits()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(tab)
        return scroll

    def _on_combo_mode_changed(self):
        c0 = self.cmb_b0.currentData()
        c1 = self.cmb_b1.currentData()
        c2 = self.cmb_b2.currentData()
        c3 = self.cmb_b3.currentData()
        if c0 and c1 and c2 and c3:
            encoded = AccessBitsEncoder.encode([c0, c1, c2, c3], 0x69)
            hex_str = " ".join(f"{b:02X}" for b in encoded)
            self.txt_access_hex.setText(hex_str)
            self._decode_access_bits()

    def _decode_access_bits(self):
        raw = self.txt_access_hex.text().strip().replace(" ", "")
        if len(raw) != 8:
            self.txt_access_result.setText("❌ 格式错误: 控制字必须为 4 字节 (8 位十六进制字符)")
            return
        try:
            b = bytes.fromhex(raw)
            result = AccessBitsDecoder.decode(b)

            if "error" in result:
                self.txt_access_result.setText(f"❌ {result['error']}")
                return

            lines = []
            valid_str = "✅ 校验通过" if result["valid"] else "⚠️ 校验失败 (取反位不匹配, 可能已损坏)"
            lines.append(f"┌─ Access Bits 解析结果 [{result['raw_hex']}] {valid_str}")
            lines.append(f"│  GPB (General Purpose Byte): 0x{result['gpb']:02X}")
            lines.append(f"│")

            blocks = result["blocks"]
            for i in range(3):
                key = f"block_{i}"
                if key in blocks:
                    blk = blocks[key]
                    lines.append(f"├─ 数据块 Block {i} (C1={blk['c1']} C2={blk['c2']} C3={blk['c3']})")
                    lines.append(f"│   权限: {blk.get('desc', '')}")
                    lines.append(f"│   读取={blk.get('read','-')}  写入={blk.get('write','-')}  增值={blk.get('increment','-')}  减值/转存={blk.get('dec_transfer_restore','-')}")
                    lines.append(f"│")

            if "trailer" in blocks:
                t = blocks["trailer"]
                lines.append(f"└─ 扇区尾块 Trailer (C1={t['c1']} C2={t['c2']} C3={t['c3']})")
                lines.append(f"    权限: {t.get('desc', '')}")
                lines.append(f"    KeyA读={t.get('key_a_read','-')}  KeyA写={t.get('key_a_write','-')}")
                lines.append(f"    控制字读={t.get('access_read','-')}  控制字写={t.get('access_write','-')}")
                lines.append(f"    KeyB读={t.get('key_b_read','-')}  KeyB写={t.get('key_b_write','-')}")

            self.txt_access_result.setText("\n".join(lines))
        except Exception as e:
            self.txt_access_result.setText(f"❌ 解析异常: {e}")

    # ─────────────────────────────────────────────────
    # Tab 2: 卡号换算器
    # ─────────────────────────────────────────────────
    def _build_converter_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # 十进制 -> Hex
        grp1 = QGroupBox("🔢 十进制卡号 → Hex UID")
        grp1.setStyleSheet("QGroupBox { font-weight: bold; color: #34D399; }")
        lay1 = QGridLayout(grp1)
        lay1.addWidget(QLabel("输入 10 进制卡号:"), 0, 0)
        self.txt_input_dec = QLineEdit()
        self.txt_input_dec.setPlaceholderText("例如: 3751706327")
        btn_calc_dec = QPushButton("换算为 Hex UID")
        btn_calc_dec.clicked.connect(self._convert_from_dec)
        lay1.addWidget(self.txt_input_dec, 0, 1)
        lay1.addWidget(btn_calc_dec, 0, 2)
        self.lbl_conv_res_dec = QLabel("换算结果: 待输入")
        self.lbl_conv_res_dec.setStyleSheet("color: #E2E8F0; font-family: Consolas;")
        self.lbl_conv_res_dec.setWordWrap(True)
        lay1.addWidget(self.lbl_conv_res_dec, 1, 0, 1, 3)
        layout.addWidget(grp1)

        # Hex -> 十进制
        grp2 = QGroupBox("🔢 Hex UID → 十进制卡号")
        grp2.setStyleSheet("QGroupBox { font-weight: bold; color: #38BDF8; }")
        lay2 = QGridLayout(grp2)
        lay2.addWidget(QLabel("输入 Hex UID:"), 0, 0)
        self.txt_input_hex = QLineEdit()
        self.txt_input_hex.setPlaceholderText("例如: D7 7E A0 DF")
        btn_calc_hex = QPushButton("换算为十进制")
        btn_calc_hex.clicked.connect(self._convert_from_hex)
        lay2.addWidget(self.txt_input_hex, 0, 1)
        lay2.addWidget(btn_calc_hex, 0, 2)
        self.lbl_conv_res_hex = QLabel("换算结果: 待输入")
        self.lbl_conv_res_hex.setStyleSheet("color: #E2E8F0; font-family: Consolas;")
        self.lbl_conv_res_hex.setWordWrap(True)
        lay2.addWidget(self.lbl_conv_res_hex, 1, 0, 1, 3)
        layout.addWidget(grp2)
        layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(tab)
        return scroll

    def _convert_from_dec(self):
        text = self.txt_input_dec.text().strip()
        try:
            num = int(text)
            if num > 0xFFFFFFFF:
                self.lbl_conv_res_dec.setText("❌ 超出 4 字节范围 (0 ~ 4294967295)")
                return
            raw_bytes = num.to_bytes(4, "big")
            rev_bytes = num.to_bytes(4, "little")
            hex_norm = " ".join(f"{b:02X}" for b in raw_bytes)
            hex_rev = " ".join(f"{b:02X}" for b in rev_bytes)
            # 韦根
            wg26_fac = rev_bytes[1]
            wg26_card = int.from_bytes(rev_bytes[2:4], "big")
            self.lbl_conv_res_dec.setText(
                f"正序 UID (Big-Endian): {hex_norm}\n"
                f"倒序 UID (发卡常用):  {hex_rev}\n"
                f"韦根 WG26: {wg26_fac:03d},{wg26_card:05d}"
            )
        except Exception:
            self.lbl_conv_res_dec.setText("❌ 请输入有效的十进制正整数")

    def _convert_from_hex(self):
        text = self.txt_input_hex.text().strip().replace(" ", "")
        try:
            if len(text) not in (8, 14, 20):
                self.lbl_conv_res_hex.setText("❌ 请输入 4/7/10 字节 Hex (8/14/20 位十六进制)")
                return
            uid = bytes.fromhex(text)
            uid4 = uid[:4]
            dec_normal = int.from_bytes(uid4, byteorder="big")
            dec_rev = int.from_bytes(uid4[::-1], byteorder="big")
            uid4_rev = uid4[::-1]
            wg26_fac = uid4_rev[1]
            wg26_card = int.from_bytes(uid4_rev[2:4], "big")
            self.lbl_conv_res_hex.setText(
                f"正序 10 进制: {dec_normal:010d}\n"
                f"倒序 10 进制: {dec_rev:010d}\n"
                f"韦根 WG26: {wg26_fac:03d},{wg26_card:05d}\n"
                f"UID 长度: {len(uid)} 字节"
            )
        except Exception:
            self.lbl_conv_res_hex.setText("❌ 请输入有效的十六进制 UID")

    # ─────────────────────────────────────────────────
    # Tab 3: 密码字典库 (MCT 生态多字典管理器)
    # ─────────────────────────────────────────────────
    def _build_dictionary_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 头部操作栏
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #1E293B; border-radius: 6px; padding: 6px 10px;")
        h_lay = QVBoxLayout(header_frame)
        h_lay.setContentsMargins(4, 4, 4, 4)
        h_lay.setSpacing(6)

        t_row = QHBoxLayout()
        lbl_t = QLabel("📖 Mifare Classic 密钥字典库管理器 (集成 MCT 生态)")
        lbl_t.setStyleSheet("color: #38BDF8; font-weight: bold; font-size: 13px;")
        t_row.addWidget(lbl_t)
        t_row.addStretch()

        btn_add = QPushButton("➕ 导入外部字典")
        btn_add.clicked.connect(self._dict_import_external)
        btn_refresh = QPushButton("🔄 刷新")
        btn_refresh.clicked.connect(self._dict_refresh_files)
        btn_export = QPushButton("💾 导出合并字典")
        btn_export.clicked.connect(self._dict_export_merged)
        t_row.addWidget(btn_add)
        t_row.addWidget(btn_refresh)
        t_row.addWidget(btn_export)
        h_lay.addLayout(t_row)

        layout.addWidget(header_frame)

        # 多选 Checkbox 区域
        self.dict_file_checks_box = QFrame()
        self.dict_file_checks_lay = QHBoxLayout(self.dict_file_checks_box)
        self.dict_file_checks_lay.setContentsMargins(4, 2, 4, 2)
        self.dict_file_checks_lay.setSpacing(16)
        self.dict_checkboxes = {}
        layout.addWidget(self.dict_file_checks_box)

        # 统计提示
        self.lbl_dict_summary = QLabel("📊 统计: 正在加载字典...")
        self.lbl_dict_summary.setStyleSheet("color: #34D399; font-size: 11px; font-weight: bold;")
        layout.addWidget(self.lbl_dict_summary)

        # 字典密钥文本展示与编辑区
        self.txt_dict = QTextEdit()
        self.txt_dict.setFont(QFont("Consolas", 10))
        self.txt_dict.setStyleSheet("background-color: #0B1120; color: #FBBF24; border: 1px solid #334155;")
        layout.addWidget(self.txt_dict)

        self._dict_refresh_files()
        return tab

    def _dict_refresh_files(self):
        """刷新并重新渲染字典文件 Checkbox 列表"""
        # 清空既有 CheckBox
        while self.dict_file_checks_lay.count():
            item = self.dict_file_checks_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.dict_checkboxes.clear()
        files = KeyManager.list_available_files()

        for f in files:
            fname = f["filename"]
            cnt = f["key_count"]
            chk = QCheckBox(f"{fname} ({cnt:,} 键)")
            chk.setChecked(f.get("is_default", False))
            chk.setStyleSheet("color: #E2E8F0; font-size: 12px; font-weight: bold;")
            chk.setToolTip(f["desc"])
            chk.stateChanged.connect(self._dict_update_preview)
            self.dict_checkboxes[fname] = chk
            self.dict_file_checks_lay.addWidget(chk)

        self.dict_file_checks_lay.addStretch()
        self._dict_update_preview()

    def _dict_update_preview(self):
        """根据当前勾选的字典文件动态合并并展示预览"""
        selected_files = [fname for fname, chk in self.dict_checkboxes.items() if chk.isChecked()]
        combined_keys = KeyManager.load_combined_keys(selected_files, include_defaults_fallback=False)

        self.lbl_dict_summary.setText(
            f"📊 当前勾选 {len(selected_files)} 个字典文件 | 合并去重有效密钥: {len(combined_keys):,} 条"
        )
        if len(combined_keys) > 500:
            self.lbl_dict_summary.setStyleSheet("color: #F59E0B; font-size: 11px; font-weight: bold;")
        else:
            self.lbl_dict_summary.setStyleSheet("color: #34D399; font-size: 11px; font-weight: bold;")

        # 格式化预览 (前 200 条完整显示，超过 200 条截断提示，防止极端卡顿)
        lines = []
        preview_limit = 300
        for idx, k in enumerate(combined_keys[:preview_limit]):
            lines.append(f"{idx+1:04d}. {k}")

        if len(combined_keys) > preview_limit:
            lines.append(f"\n... (已省略剩余 {len(combined_keys) - preview_limit} 条密钥，全部密钥均会在读卡/破解时参与运算)")

        self.txt_dict.setText("\n".join(lines))

    def _dict_import_external(self):
        """导入外部字典文件"""
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
            self._dict_refresh_files()

    def _dict_export_merged(self):
        """将当前勾选的合并密钥导出到文件"""
        selected_files = [fname for fname, chk in self.dict_checkboxes.items() if chk.isChecked()]
        combined_keys = KeyManager.load_combined_keys(selected_files, include_defaults_fallback=True)

        if not combined_keys:
            QMessageBox.warning(self, "无数据", "当前未勾选任何有效密钥！")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "导出合并字典文件", "combined_keys.dic", "字典文件 (*.dic *.keys *.txt);;所有文件 (*.*)"
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("# PyMifareTool Combined Keys Dictionary\n")
                    f.write(f"# Total deduplicated keys: {len(combined_keys)}\n\n")
                    for k in combined_keys:
                        f.write(f"{k}\n")
                QMessageBox.information(self, "导出成功", f"成功导出 {len(combined_keys)} 条去重密钥至:\n{path}")
            except Exception as e:
                QMessageBox.warning(self, "导出失败", f"写入文件失败: {e}")

    # ─────────────────────────────────────────────────
    # Tab 4: 指令调试终端
    # ─────────────────────────────────────────────────
    def _build_debug_terminal_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        info = QLabel(
            "ℹ️ 输入原始 Hex 字节或使用快捷指令发送至读卡器, "
            "用于探测固件支持的指令集。"
        )
        info.setStyleSheet("color: #94A3B8; font-size: 12px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        # 快捷指令按钮组
        quick_box = QGroupBox("⚡ 快捷指令")
        quick_box.setStyleSheet("QGroupBox { font-weight: bold; color: #38BDF8; }")
        quick_lay = QGridLayout(quick_box)

        quick_cmds = [
            ("寻卡 (Request A)", "AA BB 03 20 26 05"),
            ("防冲突 (Anticoll)", "AA BB 02 21 00 23"),
            ("自动读卡 (0x25)", "AA BB 02 25 00 27"),
            ("停止通信 (Halt)", "AA BB 02 40 00 42"),
            ("获取固件版本", "AA BB 02 F0 00 F2"),
            ("LED 开启", "AA BB 03 60 01 62"),
            ("LED 关闭", "AA BB 03 60 00 63"),
            ("蜂鸣器响", "AA BB 04 61 00 64 01"),
        ]

        for idx, (name, hex_cmd) in enumerate(quick_cmds):
            btn = QPushButton(name)
            btn.setFixedHeight(28)
            btn.setStyleSheet("font-size: 11px; padding: 2px 8px;")
            btn.clicked.connect(lambda _, h=hex_cmd: self._send_quick_cmd(h))
            quick_lay.addWidget(btn, idx // 4, idx % 4)

        layout.addWidget(quick_box)

        # 手动输入
        manual_box = QHBoxLayout()
        manual_box.addWidget(QLabel("Hex 指令:"))
        self.txt_manual_hex = QLineEdit()
        self.txt_manual_hex.setPlaceholderText("例如: AA BB 02 21 00 23")
        self.txt_manual_hex.setFont(QFont("Consolas", 10))
        self.txt_manual_hex.returnPressed.connect(self._on_send_manual)
        btn_send = QPushButton("📤 发送")
        btn_send.setStyleSheet("background-color: #059669; color: white; font-weight: bold; padding: 6px 16px;")
        btn_send.clicked.connect(self._on_send_manual)
        manual_box.addWidget(self.txt_manual_hex, stretch=1)
        manual_box.addWidget(btn_send)
        layout.addLayout(manual_box)

        # 终端日志
        self.txt_terminal = QPlainTextEdit()
        self.txt_terminal.setReadOnly(True)
        self.txt_terminal.setFont(QFont("Consolas", 10))
        self.txt_terminal.setStyleSheet(
            "background-color: #050B14; color: #38BDF8; border: 1px solid #1E293B;"
        )
        self.txt_terminal.setPlaceholderText("指令响应将显示在此处...")
        layout.addWidget(self.txt_terminal)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(tab)
        return scroll

    def _send_quick_cmd(self, hex_str: str):
        self.txt_manual_hex.setText(hex_str)
        self._on_send_manual()

    def _on_send_manual(self):
        hex_text = self.txt_manual_hex.text().strip().replace(" ", "")
        if not hex_text:
            return
        try:
            data = bytes.fromhex(hex_text)
            display = " ".join(f"{b:02X}" for b in data)
            self.txt_terminal.appendPlainText(f"[↑ TX] {display}")
            self.sig_send_hex.emit(data)
        except ValueError:
            self.txt_terminal.appendPlainText("❌ 无效的十六进制格式")

    def append_terminal_log(self, direction: str, msg: str):
        """外部调用: 向终端追加日志"""
        self.txt_terminal.appendPlainText(f"[{direction}] {msg}")
