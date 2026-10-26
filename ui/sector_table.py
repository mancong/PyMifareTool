# -*- coding: utf-8 -*-
"""
PyMifareTool - 16/40 扇区可视化数据矩阵与实时数据分析中枢 (Pro 现代化重构版)
核心特性：
1. 实时数据指标看板 (Card Live Stats)：卡片规格、解密覆盖率、密钥库覆盖、数据资产与钱包特征
2. 扇区全景雷达与图例一体化栏 (Sector Radar & Legend Strip)：0~15 扇区数字雷达芯片与平滑滚动导航
3. 实时数据智能解析器 (Live Block Inspector)：
   - 块定位与语义识别 (Block 0 / 扇区尾块 / 电子钱包 / 普通数据)
   - 连续 Hex 流、ASCII 解码、大小端数值转换
   - UID / BCC 校验比对、Access Bits 权限矩阵深度透视
   - Mifare 电子钱包 (Value Block) 自动探测、余额折算与一键格式化生成
4. 现代化暗黑科技美学：
   - 水平横向与垂直双向自由滚动，绝不截断 ASCII
   - 扇区之间采用 2px 精致微细分界线，彻底消除突兀大空白
   - 0~15 纯数字高亮胶囊雷达芯片，杜绝 DPI 缩放文字变形
5. 双向就地编辑与完全兼容既有测试契约
"""

from typing import Optional, List, Dict, Any, Tuple
import struct

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QPushButton, QFileDialog, QMessageBox, QAbstractItemView,
    QProgressBar, QFrame, QCheckBox, QToolButton, QMenu, QSplitter, QComboBox
)
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtCore import Qt, pyqtSignal

from core.dump_model import MifareDump, BlockState
from core.card_service import CardOperationWorker
from ui.sector_widgets import (
    parse_value_block, encode_value_block, calculate_dump_statistics,
    CardStatsHeader, SectorRadarBar, LiveBlockInspector,
)


# ==============================================================================
# 算法与语义解析辅助函数 (Mifare Value Block & Dump Statistics)
# 核心主组件: 扇区可视化数据矩阵与操作中枢 (SectorTableWidget)
# ==============================================================================

class SectorTableWidget(QWidget):
    """
    Mifare Classic 16/40 扇区可视化数据矩阵主视图 (Pro 现代化重构版)
    完全集成：
    - 实时数据指标总览栏 (CardStatsHeader)
    - 扇区全景雷达与图例一体化栏 (SectorRadarBar)
    - 64 块三态彩色矩阵 (QTableWidget)
    - 实时数据智能解析器 (LiveBlockInspector)
    """
    sig_notify = pyqtSignal(str)

    def __init__(self, serial_worker=None, parent=None):
        super().__init__(parent)
        self.serial_worker = serial_worker
        self.dump = MifareDump()
        self.db = None  # CardDatabase (由主窗口注入，用于密钥留存)
        self.card_op_worker: Optional[CardOperationWorker] = None
        self._updating_table = False
        self._row_map: List[Optional[int]] = []
        self._block_to_row: List[int] = []

        # 字典与并发状态
        self._selected_key_files: Optional[List[str]] = None
        self._selected_keys: Optional[List[str]] = None
        self._concurrency: int = 1

        self._init_ui()

    def set_serial_worker(self, worker):
        self.serial_worker = worker

    def set_database(self, db):
        """注入卡片数据库 (用于留存读取/破解成功的卡号与密钥)"""
        self.db = db

    def _persist_sector_keys(self, sector: int, key_a: str, key_b: str):
        """将成功解密的扇区密钥留存到数据库 (以当前卡片 UID 为主键)"""
        if not self.db:
            return
        try:
            uid = self.dump.get_block(0)[:4].hex().upper()
        except Exception:
            uid = ""
        if not uid:
            return
        try:
            self.db.save_sector_keys(uid, sector, key_a, key_b)
            self.sig_notify.emit(f"🔐 已留存密钥: 卡 {uid} 扇区 S{sector:02d} (便于后续直接解密)")
        except Exception as e:
            self.sig_notify.emit(f"密钥留存失败: {e}")

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # 1. 顶部主功能栏 (卡片式双行分组)
        tool_frame = QFrame()
        tool_frame.setStyleSheet("""
            QFrame#toolFrame {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 6px;
            }
        """)
        tool_frame.setObjectName("toolFrame")
        tool_vbox = QVBoxLayout(tool_frame)
        tool_vbox.setContentsMargins(8, 4, 8, 4)
        tool_vbox.setSpacing(4)

        # 第 1 行：文件 Dump 与纠错管理
        row1 = QHBoxLayout()
        row1.setSpacing(5)
        lbl_r1 = QLabel("📁 Dump 管理:")
        lbl_r1.setStyleSheet("color: #94A3B8; font-weight: bold; font-size: 11px;")
        row1.addWidget(lbl_r1)

        self.btn_load = QPushButton("📂 载入 Dump")
        self.btn_load.clicked.connect(self._on_load_file)
        self.btn_save = QPushButton("💾 导出 Dump")
        self.btn_save.clicked.connect(self._on_save_file)

        # 格式转换
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

        # 纠错与修复
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
        row1.addStretch(1)

        # 切换 Inspector 显隐
        self.btn_toggle_inspector = QPushButton("🔍 数据解析器 [收起]")
        self.btn_toggle_inspector.setStyleSheet("background-color: #334155; font-size: 11px;")
        self.btn_toggle_inspector.clicked.connect(self._toggle_inspector_panel)
        row1.addWidget(self.btn_toggle_inspector)

        # 第 2 行：卡片硬件交互
        row2 = QHBoxLayout()
        row2.setSpacing(5)
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

        self.btn_key_config = QPushButton("⚙️ 字典配置")
        self.btn_key_config.setStyleSheet("background-color: #334155; font-size: 11px;")
        self.btn_key_config.clicked.connect(self._on_configure_keys)

        self.btn_probe = QPushButton("🔬 探测固件")
        self.btn_probe.setStyleSheet("background-color: #059669; font-weight: bold;")
        self.btn_probe.clicked.connect(self._on_probe_firmware)

        self.btn_clone_wizard = QPushButton("⚡ 克隆向导")
        self.btn_clone_wizard.setStyleSheet("background-color: #0284C7; font-weight: bold;")
        self.btn_clone_wizard.setToolTip("面向新手的两步一键复制/克隆卡向导")
        self.btn_clone_wizard.clicked.connect(self._on_open_clone_wizard)

        self.btn_magic_tools = QPushButton("🪄 魔术卡")
        self.btn_magic_tools.setStyleSheet("background-color: #7C3AED; font-weight: bold;")
        self.btn_magic_tools.setToolTip("魔术卡高级工具箱 (UID/CUID改号/出厂化/UFUID锁死)")
        self.btn_magic_tools.clicked.connect(self._on_open_magic_tools)

        row2.addWidget(self.btn_read_card)
        row2.addWidget(self.btn_write_card)
        row2.addWidget(self.btn_crack)
        row2.addWidget(self.btn_clone_wizard)
        row2.addWidget(self.btn_magic_tools)
        row2.addWidget(self.btn_key_config)
        row2.addWidget(self.btn_probe)
        row2.addSpacing(6)

        self.chk_protect_b0 = QCheckBox("Block 0 写保护 (防废卡)")
        self.chk_protect_b0.setChecked(True)
        self.chk_protect_b0.setStyleSheet("color: #FBBF24; font-size: 11px; font-weight: bold;")
        row2.addWidget(self.chk_protect_b0)

        self.cmb_magic_type = QComboBox()
        self.cmb_magic_type.addItems(["CUID (默认常规写)", "GEN1A (后门盲写)"])
        self.cmb_magic_type.setToolTip("改写 Block 0 时的魔术卡类型:\n- CUID/Gen2: 普通写指令，需扇区密钥认证\n- GEN1A: 后门 40/43 序列盲写 (需卡片支持)")
        self.cmb_magic_type.setEnabled(False)
        self.chk_protect_b0.toggled.connect(lambda checked: self.cmb_magic_type.setEnabled(not checked))
        row2.addWidget(self.cmb_magic_type)

        row2.addSpacing(6)
        lbl_card_model = QLabel("规格:")
        lbl_card_model.setStyleSheet("color: #94A3B8; font-size: 11px;")
        row2.addWidget(lbl_card_model)
        self.cmb_card_model = QComboBox()
        self.cmb_card_model.addItems(["1K (S50)", "4K (S70)"])
        self.cmb_card_model.setToolTip("选择当前处理的卡片容量规格 (1K/4K)")
        self.cmb_card_model.currentIndexChanged.connect(self._on_card_model_changed)
        row2.addWidget(self.cmb_card_model)
        row2.addStretch(1)

        tool_vbox.addLayout(row1)
        tool_vbox.addLayout(row2)
        main_layout.addWidget(tool_frame)

        # 2. 实时数据指标总览栏 (Stats Header, 46px)
        self.stats_header = CardStatsHeader(self)
        main_layout.addWidget(self.stats_header)

        # 3. 扇区全景雷达与图例一体化栏 (Radar Bar, 32px)
        self.radar_bar = SectorRadarBar(self)
        self.radar_bar.sig_sector_selected.connect(self._on_sector_radar_clicked)
        main_layout.addWidget(self.radar_bar)

        # 4. 核心工作区分割器 (左侧表格 + 右侧 Live Inspector)
        self.work_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.work_splitter.setChildrenCollapsible(False)

        # 左侧表格
        self.table = QTableWidget()
        self.table.setColumnCount(19)
        headers = ["扇区", "块号"] + [f"{i:02X}" for i in range(16)] + ["ASCII 字符预览"]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(64)

        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.verticalHeader().setVisible(False)
        self.table.setFont(QFont("Consolas", 9))
        self.table.setShowGrid(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #0B1120;
                gridline-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 6px;
                selection-background-color: #0284C7;
                selection-color: #FFFFFF;
            }
            QHeaderView::section {
                background-color: #1E293B;
                color: #94A3B8;
                padding: 3px;
                border: none;
                font-weight: bold;
                font-family: Consolas;
                font-size: 11px;
            }
        """)
        # 解除 Qt 对最小行高的强制限制 (允许 2px 的精细分界线)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.verticalHeader().setMinimumSectionSize(2)

        # 单元格改变与选择联动
        self.table.cellChanged.connect(self._on_cell_changed)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)

        # 水平列宽配置与水平滚动条启用 (绝不强行 Stretch 最后一列导致截断)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 44)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 42)
        for i in range(2, 18):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(i, 28)
        # 第 18 列 ASCII 预览列：设置交互式自适应模式，默认 140px，完整展示 16 字符
        header.setSectionResizeMode(18, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(18, 140)

        # 启用水平与垂直滚动条
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.work_splitter.addWidget(self.table)

        # 右侧实时数据智能解析器
        self.inspector = LiveBlockInspector(self)
        self.inspector.sig_block_modified.connect(self._on_inspector_block_modified)
        self.inspector.sig_toggle_collapse.connect(self._toggle_inspector_panel)
        self.inspector.sig_manual_decrypt.connect(self._on_manual_decrypt)
        self.work_splitter.addWidget(self.inspector)

        # 比例分配 (表格宽 680, Inspector 宽 280)
        self.work_splitter.setStretchFactor(0, 3)
        self.work_splitter.setStretchFactor(1, 1)
        self.work_splitter.setSizes([680, 280])
        main_layout.addWidget(self.work_splitter, 1)

        # 5. 底部操作进度面板
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

        main_layout.addWidget(self.progress_panel)

        # 初始化渲染
        self.refresh_table()

    def _toggle_inspector_panel(self):
        visible = not self.inspector.isVisible()
        self.inspector.setVisible(visible)
        self.btn_toggle_inspector.setText("🔍 数据解析器 [展开]" if not visible else "🔍 数据解析器 [收起]")

    def row_for_block(self, block_idx: int) -> int:
        if 0 <= block_idx < len(self._block_to_row):
            return self._block_to_row[block_idx]
        return block_idx

    def set_dump(self, dump: MifareDump):
        self.dump = dump
        self.refresh_table()

    def update_uid(self, uid_bytes: bytes):
        self.dump.set_uid(uid_bytes)
        self.refresh_table()

    def _on_sector_radar_clicked(self, sec: int):
        first_b = self.dump.get_sector_first_block(sec)
        row = self.row_for_block(first_b)
        item = self.table.item(row, 0)
        if item:
            self.table.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtTop)
            self.table.selectRow(row)

    def _on_table_selection_changed(self):
        items = self.table.selectedItems()
        if not items:
            return
        row = items[0].row()
        block_idx = self._row_map[row] if 0 <= row < len(self._row_map) else None
        if block_idx is not None:
            self.inspector.inspect_block(block_idx, self.dump)

    def _on_inspector_block_modified(self, block_idx: int, data: bytes):
        """Inspector 工具修改了块数据，同步回 dump 并更新视图"""
        self.dump.set_block(block_idx, data)
        self.dump.set_block_state(block_idx, BlockState.READ_OK)
        self.refresh_table()
        self.inspector.inspect_block(block_idx, self.dump)

    def refresh_table(self):
        """刷新整张表格渲染，并联动刷新 KPI 统计、扇区雷达与 Inspector"""
        self._updating_table = True
        self.table.clearSpans()

        total_blocks = self.dump.block_count
        num_sectors = max(1, total_blocks // 4 if not self.dump.is_4k else self.dump.sector_count)

        row_map = []
        block_to_row = [0] * total_blocks
        for s in range(num_sectors):
            b_cnt = self.dump.get_sector_block_count(s)
            first_b = self.dump.get_sector_first_block(s)
            for k in range(b_cnt):
                b = first_b + k
                if b >= total_blocks:
                    break
                block_to_row[b] = len(row_map)
                row_map.append(b)
            if s != num_sectors - 1:
                row_map.append(None)
        self._row_map = row_map
        self._block_to_row = block_to_row
        self.table.setRowCount(len(row_map))

        bg_b0, fg_b0 = QColor("#3D2B1F"), QColor("#FFB300")
        bg_data, fg_data = QColor("#1E293B"), QColor("#E2E8F0")
        bg_trailer, fg_trailer = QColor("#0C2B45"), QColor("#7DD3FC")
        # 扇区微细分割线：使用优雅深蓝灰色，消除突兀大空白
        bg_sep = QColor("#334155")

        for row, block_idx in enumerate(row_map):
            if block_idx is None:
                self.table.setSpan(row, 0, 1, 19)
                sep = QTableWidgetItem("")
                sep.setBackground(bg_sep)
                sep.setFlags(Qt.ItemFlag.NoItemFlags)
                self.table.setItem(row, 0, sep)
                # 精致 2 像素微细分界线
                self.table.setRowHeight(row, 2)
                continue

            self.table.setRowHeight(row, 24)
            sector_idx = self.dump.get_block_sector(block_idx)
            trailer_block = self.dump.get_sector_trailer_block(sector_idx)
            is_trailer = (block_idx == trailer_block)
            is_block0 = (block_idx == 0)
            state = self.dump.get_block_state(block_idx)

            if is_block0:
                bg, fg = bg_b0, fg_b0
            elif is_trailer:
                bg, fg = bg_trailer, fg_trailer
            else:
                bg, fg = bg_data, fg_data

            # 扇区编号 (只读)
            item_sec = QTableWidgetItem(f"S{sector_idx:02d}")
            item_sec.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_sec.setBackground(bg)
            item_sec.setForeground(fg)
            item_sec.setFlags(item_sec.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, item_sec)

            # 块编号 (只读)
            item_blk = QTableWidgetItem(f"B{block_idx:02d}")
            item_blk.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_blk.setBackground(bg)
            item_blk.setForeground(fg)
            item_blk.setFlags(item_blk.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, item_blk)

            # 16 字节数据
            block_data = self.dump.get_block(block_idx)
            for b in range(16):
                item_byte = QTableWidgetItem()
                item_byte.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_byte.setBackground(bg)

                if state == BlockState.UNREAD:
                    item_byte.setText("-")
                    item_byte.setForeground(QColor("#64748B"))
                    item_byte.setToolTip(f"S{sector_idx:02d} B{block_idx:02d} 字节[{b:02X}]: 尚未读取，双击可直接编辑修改")
                elif state == BlockState.READ_FAILED:
                    item_byte.setText("??")
                    item_byte.setForeground(QColor("#F87171"))
                    item_byte.setToolTip(f"S{sector_idx:02d} B{block_idx:02d} 字节[{b:02X}]: 扇区加密受保护或未命中密钥")
                else:
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

                self.table.setItem(row, 2 + b, item_byte)

            # ASCII 文本预览
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
            self.table.setItem(row, 18, item_asc)

        self._updating_table = False

        # 联动刷新 KPI 指标看板与扇区雷达地图
        stats = calculate_dump_statistics(self.dump)
        self.stats_header.update_stats(stats)
        self.radar_bar.update_radar(stats["sector_states"])

        # 联动刷新 Inspector 面板
        selected_block = self.inspector.current_block_idx
        if selected_block >= self.dump.block_count:
            selected_block = 0
        self.inspector.inspect_block(selected_block, self.dump)

    def _on_cell_changed(self, row: int, col: int):
        if self._updating_table:
            return
        if not (2 <= col <= 17):
            return

        block_idx = self._row_map[row] if 0 <= row < len(self._row_map) else None
        if block_idx is None:
            return

        item = self.table.item(row, col)
        if not item:
            return

        byte_idx = col - 2
        text = item.text().strip().upper()

        try:
            val = int(text, 16)
            if not (0 <= val <= 255):
                raise ValueError()
        except ValueError:
            state = self.dump.get_block_state(block_idx)
            self._updating_table = True
            if state == BlockState.UNREAD:
                item.setText("-")
            elif state == BlockState.READ_FAILED:
                item.setText("??")
            else:
                original = self.dump.get_block(block_idx)[byte_idx]
                item.setText(f"{original:02X}")
            self._updating_table = False
            return

        formatted = f"{val:02X}"
        self._updating_table = True
        item.setText(formatted)
        item.setForeground(QColor("#E2E8F0"))
        self._updating_table = False

        block_bytes = bytearray(self.dump.get_block(block_idx))
        block_bytes[byte_idx] = val
        self.dump.set_block(block_idx, bytes(block_bytes))
        self.dump.set_block_state(block_idx, BlockState.READ_OK)

        asc_str = "".join(chr(x) if 32 <= x <= 126 else "." for x in block_bytes)
        item_asc = self.table.item(row, 18)
        if item_asc:
            item_asc.setText(asc_str)
            item_asc.setForeground(QColor("#E2E8F0"))

        item.setBackground(QColor("#065F46"))

        # 联动更新 Inspector 与 Stats
        self.inspector.inspect_block(block_idx, self.dump)
        stats = calculate_dump_statistics(self.dump)
        self.stats_header.update_stats(stats)
        self.radar_bar.update_radar(stats["sector_states"])

    def _on_card_model_changed(self, index: int):
        target_4k = (index == 1)
        if self.dump.is_4k != target_4k:
            new_dump = MifareDump(is_4k=target_4k)
            copy_blocks = min(self.dump.block_count, new_dump.block_count)
            for b in range(copy_blocks):
                new_dump.set_block(b, self.dump.get_block(b))
                new_dump.set_block_state(b, self.dump.get_block_state(b))
            self.dump = new_dump
            self.refresh_table()

    # -------------------------------------------------------------
    # 异步卡片交互工作流
    # -------------------------------------------------------------
    def _start_worker(self, op_type: str, dump_to_write=None, allow_b0=False, custom_keys=None,
                      concurrency=1, target_sectors=None, manual_key=None, magic_type="CUID", is_4k=None,
                      crack_mode="fast"):
        if not self.serial_worker or not self.serial_worker.is_connected():
            QMessageBox.warning(self, "未连接", "请先在左侧连接读卡器串口！")
            return

        if self.card_op_worker and self.card_op_worker.isRunning():
            QMessageBox.information(self, "正在进行", "当前已有正在执行的任务，请等待其完成。")
            return

        self.progress_panel.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_progress.setText(f"正在准备: {op_type}...")

        is_4k_effective = is_4k if is_4k is not None else self.dump.is_4k

        self.card_op_worker = CardOperationWorker(
            worker=self.serial_worker,
            op_type=op_type,
            target_sectors=target_sectors,
            dump_to_write=dump_to_write,
            allow_block0_write=allow_b0,
            custom_keys=custom_keys,
            concurrency=concurrency,
            manual_key=manual_key,
            magic_type=magic_type,
            is_4k=is_4k_effective,
            parent=self,
            crack_mode=crack_mode
        )
        self.card_op_worker.sig_progress.connect(self._on_worker_progress)
        self.card_op_worker.sig_log.connect(lambda msg: self.sig_notify.emit(msg))
        self.card_op_worker.sig_block_read.connect(self._on_worker_block_read)
        self.card_op_worker.sig_block_failed.connect(self._on_worker_block_failed)
        self.card_op_worker.sig_sector_cracked.connect(self._on_worker_sector_cracked)
        self.card_op_worker.sig_finished.connect(self._on_worker_finished)
        self.card_op_worker.start()

    def _on_worker_progress(self, pct: int, status: str):
        self.progress_bar.setValue(pct)
        self.lbl_progress.setText(status)

    def _on_worker_block_read(self, block_idx: int, data: bytes):
        self.dump.set_block(block_idx, data)
        self.dump.set_block_state(block_idx, BlockState.READ_OK)
        row = self._block_to_row[block_idx] if block_idx < len(self._block_to_row) else block_idx
        self._updating_table = True
        for b in range(16):
            it = self.table.item(row, 2 + b)
            if it:
                it.setText(f"{data[b]:02X}")
        it_asc = self.table.item(row, 18)
        if it_asc:
            it_asc.setText("".join(chr(x) if 32 <= x <= 126 else "." for x in data))
        self._updating_table = False

    def _on_worker_block_failed(self, block_idx: int):
        """读卡/解密过程中某块认证失败，实时更新单元格为 '??' 保持实时动画流动感"""
        self.dump.set_block_state(block_idx, BlockState.READ_FAILED)
        row = self._block_to_row[block_idx] if block_idx < len(self._block_to_row) else block_idx
        self._updating_table = True
        for b in range(16):
            it = self.table.item(row, 2 + b)
            if it:
                it.setText("??")
                it.setForeground(QColor("#F87171"))
        it_asc = self.table.item(row, 18)
        if it_asc:
            it_asc.setText("[加密受限]")
            it_asc.setForeground(QColor("#F87171"))
        self._updating_table = False

    def _on_worker_sector_cracked(self, sector: int, key_a: str, key_b: str):
        """破解/读取成功某扇区密钥 -> 留存至数据库"""
        self._persist_sector_keys(sector, key_a, key_b)

    def _on_worker_finished(self, success: bool, msg: str, result_data):
        self.progress_panel.setVisible(False)
        if isinstance(result_data, MifareDump):
            self.dump = result_data
            uid = self.dump.get_uid()
            if uid and any(b != 0 for b in uid):
                from core.models.card_converter import CardConverter
                card_info = {
                    "uid_bytes": uid,
                    "conversions": CardConverter.convert_uid(uid),
                    "raw": self.dump.get_block(0),
                    "card_type": "Mifare Classic 1K" if not self.dump.is_4k else "Mifare Classic 4K",
                }
                if self.serial_worker and hasattr(self.serial_worker, "sig_card_swiped"):
                    self.serial_worker.sig_card_swiped.emit(card_info)
        self.refresh_table()
        if self.inspector.current_dump is not None:
            self.inspector.inspect_block(self.inspector.current_block_idx, self.dump)

        if success:
            QMessageBox.information(self, "操作完成", msg)
        else:
            QMessageBox.warning(self, "操作结果", msg)

    def _on_abort_operation(self):
        if self.card_op_worker and self.card_op_worker.isRunning():
            self.card_op_worker.abort()
            self.lbl_progress.setText("正在中止...")

    def _on_configure_keys(self):
        from ui.key_select_dialog import KeySelectDialog
        dialog = KeySelectDialog(self, initial_selected=self._selected_key_files, concurrency=self._concurrency)
        if dialog.exec():
            self._selected_key_files = dialog.get_selected_files()
            self._concurrency = dialog.get_concurrency()
            self._selected_keys = dialog.get_selected_keys()
            QMessageBox.information(
                self, "字典配置更新",
                f"已配置加载 {len(self._selected_key_files)} 个字典文件，共计 {len(self._selected_keys):,} 条去重有效密钥。\n"
                f"扫描模式: 单线程顺序扫描 (射频半双工)。"
            )

    def _on_read_card(self):
        from core.key_manager import KeyManager
        keys = list(self._selected_keys) if self._selected_keys else KeyManager.load_combined_keys()

        # 优先读取并合并该卡在数据库中此前已破解留存的历史已知密钥 (置顶优先命中)
        card_uid_hex = self.dump.get_uid().hex().upper() if self.dump.get_uid() else ""
        if self.db and card_uid_hex:
            saved_keys = self.db.get_card_keys(card_uid_hex)
            db_keys = []
            for s_info in saved_keys.values():
                ka = s_info.get("key_a", "")
                kb = s_info.get("key_b", "")
                if ka and len(ka) == 12 and ka not in db_keys and ka != "未破解":
                    db_keys.append(ka)
                if kb and len(kb) == 12 and kb not in db_keys and kb != "未破解":
                    db_keys.append(kb)
            if db_keys:
                keys = db_keys + [k for k in keys if k not in db_keys]

        is_4k = (self.cmb_card_model.currentIndex() == 1) or self.dump.is_4k
        target_sectors = list(range(40 if is_4k else 16))
        self._start_worker(
            CardOperationWorker.OP_READ_CARD,
            custom_keys=keys,
            concurrency=1,
            target_sectors=target_sectors,
            is_4k=is_4k
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
            magic_type = "GEN1A" if "GEN1A" in self.cmb_magic_type.currentText().upper() else "CUID"
            self._start_worker(
                CardOperationWorker.OP_WRITE_CARD,
                dump_to_write=self.dump,
                allow_b0=allow_b0,
                magic_type=magic_type,
                is_4k=self.dump.is_4k
            )

    def _on_crack_keys(self):
        from ui.key_select_dialog import KeySelectDialog
        from ui.crack_dialogs import SectorScopeDialog

        # 1. 先选择字典
        dialog = KeySelectDialog(self, initial_selected=self._selected_key_files, concurrency=self._concurrency)
        if not dialog.exec():
            return
        self._selected_key_files = dialog.get_selected_files()
        self._concurrency = dialog.get_concurrency()
        self._selected_keys = dialog.get_selected_keys()
        if not self._selected_keys:
            QMessageBox.warning(self, "未选择字典", "未找到有效密钥，请至少勾选一个包含有效密钥的字典文件！")
            return

        # 2. 再选择参与破解的扇区 (默认勾选全部被加密扇区)
        scope = SectorScopeDialog(self, dump=self.dump)
        if not scope.exec():
            return
        target_sectors = scope.get_selected_sectors()
        if not target_sectors:
            QMessageBox.warning(self, "未选择扇区", "请至少勾选一个待破解的扇区！")
            return

        is_4k = (self.cmb_card_model.currentIndex() == 1) or self.dump.is_4k or (max(target_sectors) >= 16)
        self._start_worker(
            CardOperationWorker.OP_CRACK_KEYS,
            custom_keys=self._selected_keys,
            concurrency=self._concurrency,
            target_sectors=target_sectors,
            is_4k=is_4k,
            crack_mode=scope.get_crack_mode()
        )

    def _on_manual_decrypt(self, block_idx: int):
        """数据解析器: 手动输入密钥对指定块所属扇区进行测试解密"""
        from ui.crack_dialogs import ManualKeyDialog

        if not self.serial_worker or not self.serial_worker.is_connected():
            QMessageBox.warning(self, "未连接", "请先在左侧连接读卡器串口！")
            return

        sector = self.dump.get_block_sector(block_idx)
        # 若数据库已留存该卡该扇区密钥, 作为输入建议
        sugg_a = sugg_b = ""
        if self.db:
            try:
                uid = self.dump.get_block(0)[:4].hex().upper()
                saved = self.db.get_card_keys(uid).get(sector, {})
                sugg_a = saved.get("key_a", "")
                sugg_b = saved.get("key_b", "")
            except Exception:
                pass

        dlg = ManualKeyDialog(self, block_idx=block_idx, sector=sector,
                              suggestion_a=sugg_a, suggestion_b=sugg_b)
        if not dlg.exec():
            return

        key_hex = dlg.get_key_hex()
        try:
            key_bytes = bytes.fromhex(key_hex)
        except ValueError:
            QMessageBox.warning(self, "格式错误", "密钥解析失败！")
            return

        self._start_worker(
            CardOperationWorker.OP_READ_SECTOR,
            target_sectors=[sector],
            manual_key={"key_type": dlg.get_key_type(), "key": key_bytes}
        )

    def _on_probe_firmware(self):
        self._start_worker(CardOperationWorker.OP_PROBE_FIRMWARE)

    def _on_open_clone_wizard(self):
        from ui.clone_wizard_dialog import CloneWizardDialog
        dlg = CloneWizardDialog(
            self.serial_worker,
            card_db=self.db,
            parent=self,
            is_4k=bool(getattr(self.dump, "is_4k", False)),
        )
        dlg.sig_card_cloned.connect(self._on_card_cloned)
        dlg.exec()

    def _on_card_cloned(self, dump: MifareDump):
        self.dump = dump
        self.refresh_table()
        self.sig_notify.emit("✨ 一键克隆卡片成功！已加载克隆数据到扇区表。")

    def _on_open_magic_tools(self):
        from ui.magic_card_dialog import MagicCardDialog
        dlg = MagicCardDialog(self.serial_worker, current_dump=self.dump, parent=self)
        dlg.exec()

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

    def load_dump_from_path(self, path: str) -> bool:
        """从指定路径直接载入卡片 Dump 数据并刷新界面与状态"""
        if self.dump.load_from_file(path):
            self.cmb_card_model.blockSignals(True)
            self.cmb_card_model.setCurrentIndex(1 if self.dump.is_4k else 0)
            self.cmb_card_model.blockSignals(False)
            self.refresh_table()
            uid = self.dump.get_uid()
            if uid and any(b != 0 for b in uid):
                from core.models.card_converter import CardConverter
                card_info = {
                    "uid_bytes": uid,
                    "conversions": CardConverter.convert_uid(uid),
                    "raw": self.dump.get_block(0),
                    "card_type": "Mifare Classic 1K" if not self.dump.is_4k else "Mifare Classic 4K",
                }
                if self.serial_worker and hasattr(self.serial_worker, "sig_card_swiped"):
                    self.serial_worker.sig_card_swiped.emit(card_info)
            return True
        return False

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
            if self.load_dump_from_path(path):
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
