# -*- coding: utf-8 -*-
"""
PyMifareTool - Sector table visualization sub-widgets.
Contains Mifare Value Block helpers, card stats header, sector radar and live inspector.
"""

from typing import Optional, List, Dict, Any
import struct

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QInputDialog, QApplication, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal

from core.dump_model import MifareDump, BlockState
from core.models.access_bits import AccessBitsDecoder


# ==============================================================================

def parse_value_block(data: bytes) -> Optional[Dict[str, Any]]:
    """
    判断并解析 Mifare Classic 官方规范的 16 字节电子钱包 Value Block:
    Byte 0..3:   Value (4B, little-endian signed 32-bit int)
    Byte 4..7:   ~Value (4B, bitwise inverse of Value)
    Byte 8..11:  Value (4B, same as 0..3)
    Byte 12:     Addr (1B, block address)
    Byte 13:     ~Addr (1B, bitwise inverse of Addr)
    Byte 14:     Addr (1B, same as 12)
    Byte 15:     ~Addr (1B, same as 13)
    """
    if len(data) != 16:
        return None
    try:
        v1 = struct.unpack("<i", data[0:4])[0]
        v2 = struct.unpack("<I", data[4:8])[0]
        v3 = struct.unpack("<i", data[8:12])[0]
        v1_u = struct.unpack("<I", data[0:4])[0]

        if v1 != v3 or (v1_u ^ 0xFFFFFFFF) != v2:
            return None

        a1, a2, a3, a4 = data[12], data[13], data[14], data[15]
        if a1 != a3 or a2 != a4 or (a1 ^ 0xFF) != a2:
            return None

        amount_str = f"¥{v1 / 100:.2f}" if abs(v1) < 100_000_000 else f"{v1:,} 点"

        return {
            "value": v1,
            "backup_addr": a1,
            "amount_str": amount_str,
            "is_valid": True
        }
    except Exception:
        return None


def encode_value_block(val: int, backup_addr: int = 0) -> bytes:
    """生成 16 字节标准 Mifare Classic 电子钱包 Value Block"""
    v_signed = struct.pack("<i", val)
    v_unsigned = struct.unpack("<I", v_signed)[0]
    v_inv = struct.pack("<I", v_unsigned ^ 0xFFFFFFFF)
    addr = backup_addr & 0xFF
    addr_inv = (addr ^ 0xFF) & 0xFF
    return v_signed + v_inv + v_signed + bytes([addr, addr_inv, addr, addr_inv])


def calculate_dump_statistics(dump: MifareDump) -> Dict[str, Any]:
    """汇总分析卡片内存模型的全局统计指标"""
    total_blocks = dump.block_count
    total_sectors = dump.sector_count

    read_ok_blocks = 0
    unread_blocks = 0
    failed_blocks = 0
    non_zero_blocks = 0
    value_blocks_info: List[Dict[str, Any]] = []

    sector_states: List[str] = []
    key_a_known = 0
    key_b_known = 0

    for s in range(total_sectors):
        b_count = dump.get_sector_block_count(s)
        first_b = dump.get_sector_first_block(s)
        trailer_b = dump.get_sector_trailer_block(s)

        s_read_ok = 0
        s_failed = 0
        s_unread = 0

        for k in range(b_count):
            b_idx = first_b + k
            st = dump.get_block_state(b_idx)
            data = dump.get_block(b_idx)

            if st == BlockState.READ_OK:
                read_ok_blocks += 1
                s_read_ok += 1
                if any(x != 0 for x in data):
                    non_zero_blocks += 1
                if b_idx != trailer_b and b_idx != 0:
                    vb = parse_value_block(data)
                    if vb:
                        vb["block_idx"] = b_idx
                        vb["sector_idx"] = s
                        value_blocks_info.append(vb)
            elif st == BlockState.READ_FAILED:
                failed_blocks += 1
                s_failed += 1
            else:
                unread_blocks += 1
                s_unread += 1

        # 扇区尾块密钥探测
        trailer_data = dump.get_block(trailer_b)
        trailer_st = dump.get_block_state(trailer_b)
        if trailer_st == BlockState.READ_OK:
            if any(x != 0 for x in trailer_data[0:6]):
                key_a_known += 1
            if any(x != 0 for x in trailer_data[10:16]):
                key_b_known += 1

        # 评定扇区综合状态
        if s_failed == b_count:
            sec_state = "failed"
        elif s_read_ok == b_count:
            sec_state = "ok"
        elif s_unread == b_count:
            sec_state = "unread"
        elif s_read_ok > 0:
            sec_state = "partial"
        else:
            sec_state = "failed"
        sector_states.append(sec_state)

    ok_sectors = sum(1 for st in sector_states if st == "ok")
    failed_sectors = sum(1 for st in sector_states if st == "failed")
    partial_sectors = sum(1 for st in sector_states if st == "partial")

    coverage_pct = (read_ok_blocks / total_blocks * 100) if total_blocks > 0 else 0.0

    return {
        "card_type": "Mifare Classic 4K (S70)" if dump.is_4k else "Mifare Classic 1K (S50)",
        "capacity_bytes": dump.total_bytes,
        "total_sectors": total_sectors,
        "total_blocks": total_blocks,
        "read_ok_blocks": read_ok_blocks,
        "unread_blocks": unread_blocks,
        "failed_blocks": failed_blocks,
        "non_zero_blocks": non_zero_blocks,
        "ok_sectors": ok_sectors,
        "failed_sectors": failed_sectors,
        "partial_sectors": partial_sectors,
        "coverage_pct": coverage_pct,
        "sector_states": sector_states,
        "key_a_known": key_a_known,
        "key_b_known": key_b_known,
        "value_blocks": value_blocks_info
    }


# ==============================================================================
# UI 子组件 1: 紧凑型卡片实时数据指标栏 (CardStatsHeader)
# ==============================================================================

class CardStatsHeader(QFrame):
    """
    4 张紧凑型科技感微指标卡片：
    - 垂直高度仅 46px，为下方数据表格腾出充裕视野
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statsHeaderFrame")
        self.setFixedHeight(46)
        self.setStyleSheet("""
            QFrame#statsHeaderFrame {
                background-color: #111827;
                border: 1px solid #1E293B;
                border-radius: 6px;
            }
        """)
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        # 卡片 1: 规格
        self.box_spec = self._create_card("💳 卡片规格", "Mifare Classic 1K", "1024B · 16扇区", "#38BDF8")
        # 卡片 2: 覆盖率
        self.box_cov = self._create_card("🔓 解密覆盖率", "0 / 16 (0.0%)", "已读 0 块", "#10B981")
        # 卡片 3: 密钥
        self.box_keys = self._create_card("🔑 扇区密钥库", "Key A: 0 | Key B: 0", "未载入", "#A855F7")
        # 卡片 4: 数据与资产
        self.box_data = self._create_card("📊 资产与特征", "非空数据: 0 块", "无钱包块", "#F59E0B")

        layout.addWidget(self.box_spec, 1)
        layout.addWidget(self.box_cov, 1)
        layout.addWidget(self.box_keys, 1)
        layout.addWidget(self.box_data, 1)

    def _create_card(self, title: str, main_val: str, sub_val: str, accent_color: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #1E293B;
                border: 1px solid #334155;
                border-left: 3px solid {accent_color};
                border-radius: 4px;
            }}
        """)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(8, 2, 8, 2)
        lay.setSpacing(6)

        v_lay = QVBoxLayout()
        v_lay.setContentsMargins(0, 0, 0, 0)
        v_lay.setSpacing(1)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("font-size: 10px; color: #94A3B8; font-weight: bold;")
        lbl_s = QLabel(sub_val)
        lbl_s.setStyleSheet("font-size: 10px; color: #64748B;")

        v_lay.addWidget(lbl_t)
        v_lay.addWidget(lbl_s)
        lay.addLayout(v_lay, 1)

        lbl_m = QLabel(main_val)
        lbl_m.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_m.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {accent_color}; font-family: Consolas, -apple-system, sans-serif;")
        lay.addWidget(lbl_m, 1)

        card.lbl_t = lbl_t
        card.lbl_m = lbl_m
        card.lbl_s = lbl_s
        return card

    def update_stats(self, stats: Dict[str, Any]):
        # 卡片 1
        self.box_spec.lbl_m.setText(stats["card_type"])
        self.box_spec.lbl_s.setText(f"{stats['capacity_bytes']}B · {stats['total_sectors']}扇区/{stats['total_blocks']}块")

        # 卡片 2
        cov_text = f"{stats['ok_sectors']}/{stats['total_sectors']} ({stats['coverage_pct']:.0f}%)"
        self.box_cov.lbl_m.setText(cov_text)
        sub_cov = f"已读 {stats['read_ok_blocks']} | 受阻 {stats['failed_blocks']} | 未读 {stats['unread_blocks']}"
        self.box_cov.lbl_s.setText(sub_cov)

        # 卡片 3
        self.box_keys.lbl_m.setText(f"A:{stats['key_a_known']} | B:{stats['key_b_known']}")
        if stats["read_ok_blocks"] == 0 and stats["unread_blocks"] > 0:
            self.box_keys.lbl_s.setText("等待读取/载入")
        else:
            self.box_keys.lbl_s.setText(f"已知覆盖 {stats['key_a_known'] + stats['key_b_known']} 密钥")

        # 卡片 4 (钱包识别)
        self.box_data.lbl_m.setText(f"非空 {stats['non_zero_blocks']} 块")
        vb_list = stats["value_blocks"]
        if vb_list:
            first_vb = vb_list[0]
            val_text = f"💰钱包: {first_vb['amount_str']}(B{first_vb['block_idx']:02d})"
            self.box_data.lbl_s.setText(val_text)
            self.box_data.lbl_s.setStyleSheet("font-size: 10px; color: #34D399; font-weight: bold;")
        else:
            self.box_data.lbl_s.setText("未探测到钱包块")
            self.box_data.lbl_s.setStyleSheet("font-size: 10px; color: #64748B;")


# ==============================================================================
# UI 子组件 2: 扇区全景雷达与图例一体化栏 (SectorRadarBar)
# ==============================================================================

class SectorRadarBar(QFrame):
    """
    0~15 数字扇区雷达微地图 + 状态图例合并单行：
    - 纯数字呈现 (0~15)，杜绝任何 DPI 缩放下的字符重叠变形
    - 高度仅 32px，左侧扇区快速跳转定位，右侧颜色状态图例
    """
    sig_sector_selected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.chips: List[QPushButton] = []
        self.setObjectName("radarFrame")
        self.setFixedHeight(32)
        self.setStyleSheet("""
            QFrame#radarFrame {
                background-color: #111827;
                border: 1px solid #1E293B;
                border-radius: 6px;
                padding: 1px 4px;
            }
        """)
        self._init_ui()

    def _init_ui(self):
        main_lay = QHBoxLayout(self)
        main_lay.setContentsMargins(6, 1, 6, 1)
        main_lay.setSpacing(3)

        lbl_t = QLabel("🛰️ 扇区雷达:")
        lbl_t.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: bold;")
        main_lay.addWidget(lbl_t)

        self.chip_container = QHBoxLayout()
        self.chip_container.setSpacing(2)
        main_lay.addLayout(self.chip_container)

        self._build_chips(16)

        main_lay.addStretch(1)

        # 合并的图例指示
        leg_lay = QHBoxLayout()
        leg_lay.setSpacing(6)
        leg_lay.addWidget(self._make_legend("Block 0", "#3D2B1F", "#FFB300"))
        leg_lay.addWidget(self._make_legend("普通数据", "#1E293B", "#E2E8F0"))
        leg_lay.addWidget(self._make_legend("扇区尾块", "#0C2B45", "#7DD3FC"))
        leg_lay.addWidget(self._make_legend("未读", "#0F172A", "#64748B"))
        leg_lay.addWidget(self._make_legend("加密受阻", "#3B1B1B", "#F87171"))
        main_lay.addLayout(leg_lay)

    def _make_legend(self, text: str, bg_color: str, text_color: str) -> QLabel:
        lbl = QLabel(f" {text} ")
        lbl.setStyleSheet(
            f"background-color: {bg_color}; color: {text_color}; border-radius: 3px; font-size: 10px; padding: 1px 4px;"
        )
        return lbl

    def _build_chips(self, count: int):
        for btn in self.chips:
            btn.deleteLater()
        self.chips.clear()

        for s in range(count):
            btn = QPushButton(str(s))
            btn.setFixedSize(26, 20)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"扇区 {s:02d}: 点击快速定位查看")
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1E293B;
                    border: 1px solid #334155;
                    border-radius: 3px;
                    color: #94A3B8;
                    font-family: Consolas, "Segoe UI", sans-serif;
                    font-size: 10px;
                    font-weight: bold;
                    padding: 0px;
                    margin: 0px;
                }
                QPushButton:hover { border-color: #38BDF8; color: #FFFFFF; }
            """)
            btn.clicked.connect(lambda checked, sec=s: self.sig_sector_selected.emit(sec))
            self.chip_container.addWidget(btn)
            self.chips.append(btn)

    def update_radar(self, sector_states: List[str]):
        if len(sector_states) != len(self.chips):
            self._build_chips(len(sector_states))

        for s, state in enumerate(sector_states):
            btn = self.chips[s]
            if state == "ok":
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #064E3B;
                        border: 1px solid #059669;
                        border-radius: 3px;
                        color: #6EE7B7;
                        font-family: Consolas, "Segoe UI", sans-serif;
                        font-size: 10px;
                        font-weight: bold;
                        padding: 0px;
                        margin: 0px;
                    }
                    QPushButton:hover { border-color: #38BDF8; }
                """)
                btn.setToolTip(f"扇区 {s:02d}: 全部数据块读取正常，密钥已知")
            elif state == "partial":
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #78350F;
                        border: 1px solid #D97706;
                        border-radius: 3px;
                        color: #FCD34D;
                        font-family: Consolas, "Segoe UI", sans-serif;
                        font-size: 10px;
                        font-weight: bold;
                        padding: 0px;
                        margin: 0px;
                    }
                    QPushButton:hover { border-color: #38BDF8; }
                """)
                btn.setToolTip(f"扇区 {s:02d}: 部分数据块读取成功")
            elif state == "failed":
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #450A0A;
                        border: 1px solid #DC2626;
                        border-radius: 3px;
                        color: #FCA5A5;
                        font-family: Consolas, "Segoe UI", sans-serif;
                        font-size: 10px;
                        font-weight: bold;
                        padding: 0px;
                        margin: 0px;
                    }
                    QPushButton:hover { border-color: #38BDF8; }
                """)
                btn.setToolTip(f"扇区 {s:02d}: 认证受限或密钥未知 (??)")
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #1E293B;
                        border: 1px solid #334155;
                        border-radius: 3px;
                        color: #64748B;
                        font-family: Consolas, "Segoe UI", sans-serif;
                        font-size: 10px;
                        padding: 0px;
                        margin: 0px;
                    }
                    QPushButton:hover { border-color: #38BDF8; }
                """)
                btn.setToolTip(f"扇区 {s:02d}: 尚未载入或读取 (-)")


# ==============================================================================
# UI 子组件 3: 实时数据智能解析器 (LiveBlockInspector)
# ==============================================================================

class LiveBlockInspector(QFrame):
    """
    实时数据智能解析器面板：
    - 联动显示当前所选块的结构化透视 (Block 0, Trailer, Value Block, Data Block)
    - 实时解析 UID, BCC, Access Bits 权限位, 钱包金额与备份地址
    - 快速块操作工具 (复制Hex/ASCII、清零、写入钱包格式、恢复默认尾块)
    """
    sig_block_modified = pyqtSignal(int, bytes)
    sig_toggle_collapse = pyqtSignal()
    sig_manual_decrypt = pyqtSignal(int)   # 请求对指定块所属扇区进行手动密钥解密

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_block_idx: int = 0
        self.current_dump: Optional[MifareDump] = None
        self.setObjectName("inspectorFrame")
        self.setStyleSheet("""
            QFrame#inspectorFrame {
                background-color: #0F172A;
                border: 1px solid #334155;
                border-radius: 6px;
            }
        """)
        self._init_ui()

    def _init_ui(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(8, 6, 8, 6)
        main_lay.setSpacing(5)

        # 1. 顶部 Header
        header_h = QHBoxLayout()
        header_h.setContentsMargins(0, 0, 0, 0)
        lbl_title = QLabel("🔍 实时数据智能解析器")
        lbl_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #38BDF8;")
        header_h.addWidget(lbl_title)
        header_h.addStretch(1)

        self.btn_collapse = QPushButton("收起 ⇥")
        self.btn_collapse.setFixedSize(52, 20)
        self.btn_collapse.setStyleSheet("font-size: 10px; padding: 1px 3px; background-color: #1E293B;")
        self.btn_collapse.clicked.connect(lambda: self.sig_toggle_collapse.emit())
        header_h.addWidget(self.btn_collapse)
        main_lay.addLayout(header_h)

        # 2. 块定位与属性徽章
        badge_frame = QFrame()
        badge_frame.setStyleSheet("background-color: #1E293B; border-radius: 4px; padding: 2px;")
        b_lay = QHBoxLayout(badge_frame)
        b_lay.setContentsMargins(6, 3, 6, 3)

        self.lbl_pos_badge = QLabel("S00 · B00")
        self.lbl_pos_badge.setStyleSheet("font-size: 10pt; font-family: Consolas; font-weight: bold; color: #F8FAFC;")
        self.lbl_role_badge = QLabel("Block 0 (UID/厂商块)")
        self.lbl_role_badge.setStyleSheet("background-color: #3D2B1F; color: #FFB300; border-radius: 3px; padding: 1px 5px; font-size: 10px; font-weight: bold;")
        self.lbl_state_badge = QLabel("● 未载入")
        self.lbl_state_badge.setStyleSheet("color: #64748B; font-size: 10px; font-weight: bold;")

        b_lay.addWidget(self.lbl_pos_badge)
        b_lay.addSpacing(4)
        b_lay.addWidget(self.lbl_role_badge)
        b_lay.addStretch(1)
        b_lay.addWidget(self.lbl_state_badge)
        main_lay.addWidget(badge_frame)

        # 3. 连续 Hex 字节流预览与一键复制
        hex_box = QFrame()
        hex_box.setStyleSheet("background-color: #0B1120; border: 1px solid #1E293B; border-radius: 4px;")
        hex_lay = QVBoxLayout(hex_box)
        hex_lay.setContentsMargins(6, 4, 6, 4)
        hex_lay.setSpacing(2)

        hex_head = QHBoxLayout()
        lbl_hex_t = QLabel("十六进制字节流 (16 Bytes):")
        lbl_hex_t.setStyleSheet("font-size: 10px; color: #94A3B8; font-weight: bold;")
        btn_copy_hex = QPushButton("📋 复制 Hex")
        btn_copy_hex.setFixedSize(65, 18)
        btn_copy_hex.setStyleSheet("font-size: 9px; padding: 0px;")
        btn_copy_hex.clicked.connect(self._copy_hex)
        hex_head.addWidget(lbl_hex_t)
        hex_head.addStretch(1)
        hex_head.addWidget(btn_copy_hex)
        hex_lay.addLayout(hex_head)

        self.lbl_hex_stream = QLabel("-- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --")
        self.lbl_hex_stream.setStyleSheet("font-family: Consolas; font-size: 11px; color: #38BDF8; font-weight: bold;")
        self.lbl_hex_stream.setWordWrap(True)
        hex_lay.addWidget(self.lbl_hex_stream)
        main_lay.addWidget(hex_box)

        # 4. 深度语义结构透视区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(2, 2, 2, 2)
        self.content_layout.setSpacing(3)
        scroll.setWidget(self.content_widget)
        main_lay.addWidget(scroll, 1)

        # 5. 块级快捷操作工具栏
        act_box = QFrame()
        act_box.setStyleSheet("background-color: #1E293B; border-radius: 4px; padding: 3px;")
        act_lay = QVBoxLayout(act_box)
        act_lay.setContentsMargins(6, 3, 6, 3)
        act_lay.setSpacing(3)

        lbl_act_t = QLabel("⚡ 快捷编辑与格式转换:")
        lbl_act_t.setStyleSheet("font-size: 10px; color: #94A3B8; font-weight: bold;")
        act_lay.addWidget(lbl_act_t)

        act_btn_row1 = QHBoxLayout()
        act_btn_row1.setSpacing(4)
        self.btn_copy_asc = QPushButton("📋 复制 ASCII")
        self.btn_copy_asc.clicked.connect(self._copy_ascii)
        self.btn_zero = QPushButton("🧹 块清零 (00)")
        self.btn_zero.clicked.connect(self._zero_block)
        act_btn_row1.addWidget(self.btn_copy_asc)
        act_btn_row1.addWidget(self.btn_zero)
        act_lay.addLayout(act_btn_row1)

        act_btn_row2 = QHBoxLayout()
        act_btn_row2.setSpacing(4)
        self.btn_wallet = QPushButton("💰 转为钱包块")
        self.btn_wallet.setToolTip("输入金额，自动编码生成标准 Mifare Value Block 电子钱包")
        self.btn_wallet.clicked.connect(self._format_wallet)
        self.btn_trailer = QPushButton("🔑 出厂默认尾块")
        self.btn_trailer.setToolTip("快速填充出厂默认 Key A (FF..FF) + 默认控制字 (FF 07 80 69) + Key B (FF..FF)")
        self.btn_trailer.clicked.connect(self._restore_default_trailer)
        act_btn_row2.addWidget(self.btn_wallet)
        act_btn_row2.addWidget(self.btn_trailer)
        act_lay.addLayout(act_btn_row2)

        main_lay.addWidget(act_box)

    def _copy_hex(self):
        txt = self.lbl_hex_stream.text().replace(" ", "").strip()
        if txt and "-" not in txt and "?" not in txt:
            QApplication.clipboard().setText(txt)
            QMessageBox.information(self, "复制成功", f"已复制 16 字节 Hex:\n{txt}")

    def _copy_ascii(self):
        if not self.current_dump:
            return
        data = self.current_dump.get_block(self.current_block_idx)
        asc = "".join(chr(x) if 32 <= x <= 126 else "." for x in data)
        QApplication.clipboard().setText(asc)
        QMessageBox.information(self, "复制成功", f"已复制 ASCII:\n{asc}")

    def _zero_block(self):
        if self.current_block_idx == 0:
            reply = QMessageBox.warning(
                self, "修改 Block 0 警告",
                "当前选中的是 Block 0 (UID/厂商块)！清零可能导致卡片变砖，确定继续吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.sig_block_modified.emit(self.current_block_idx, bytes([0x00] * 16))

    def _format_wallet(self):
        val, ok = QInputDialog.getInt(
            self, "生成电子钱包块 (Value Block)",
            "请输入钱包初始数值/金额 (例如 10000 即 ¥100.00):",
            10000, -2147483648, 2147483647, 100
        )
        if ok:
            block_data = encode_value_block(val, self.current_block_idx)
            self.sig_block_modified.emit(self.current_block_idx, block_data)

    def _restore_default_trailer(self):
        if not self.current_dump:
            return
        sec = self.current_dump.get_block_sector(self.current_block_idx)
        trailer_b = self.current_dump.get_sector_trailer_block(sec)
        if self.current_block_idx != trailer_b:
            QMessageBox.information(self, "非尾块", f"块 B{self.current_block_idx:02d} 不是扇区尾块，无需恢复默认尾块结构。")
            return
        default_trailer = b"\xFF" * 6 + bytes([0xFF, 0x07, 0x80, 0x69]) + b"\xFF" * 6
        self.sig_block_modified.emit(self.current_block_idx, default_trailer)

    def inspect_block(self, block_idx: int, dump: MifareDump):
        """核心联动：实时解析指定块数据并动态更新 Inspector UI"""
        self.current_block_idx = block_idx
        self.current_dump = dump

        sec_idx = dump.get_block_sector(block_idx)
        trailer_b = dump.get_sector_trailer_block(sec_idx)
        is_trailer = (block_idx == trailer_b)
        is_block0 = (block_idx == 0)
        state = dump.get_block_state(block_idx)
        block_data = dump.get_block(block_idx)

        # 1. 块定位与角色
        self.lbl_pos_badge.setText(f"S{sec_idx:02d} · B{block_idx:02d}")
        if is_block0:
            self.lbl_role_badge.setText("Block 0 (UID/厂商块)")
            self.lbl_role_badge.setStyleSheet("background-color: #3D2B1F; color: #FFB300; border-radius: 3px; padding: 1px 5px; font-size: 10px; font-weight: bold;")
        elif is_trailer:
            self.lbl_role_badge.setText("扇区尾块 (Key/控制位)")
            self.lbl_role_badge.setStyleSheet("background-color: #0C2B45; color: #7DD3FC; border-radius: 3px; padding: 1px 5px; font-size: 10px; font-weight: bold;")
        else:
            vb = parse_value_block(block_data) if state == BlockState.READ_OK else None
            if vb:
                self.lbl_role_badge.setText("💰 Mifare 钱包块")
                self.lbl_role_badge.setStyleSheet("background-color: #064E3B; color: #6EE7B7; border-radius: 3px; padding: 1px 5px; font-size: 10px; font-weight: bold;")
            else:
                self.lbl_role_badge.setText("普通数据块")
                self.lbl_role_badge.setStyleSheet("background-color: #1E293B; color: #E2E8F0; border-radius: 3px; padding: 1px 5px; font-size: 10px;")

        # 状态 Badge
        if state == BlockState.UNREAD:
            self.lbl_state_badge.setText("○ 尚未读取")
            self.lbl_state_badge.setStyleSheet("color: #64748B; font-size: 10px; font-weight: bold;")
            self.lbl_hex_stream.setText("-- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --")
            self.lbl_hex_stream.setStyleSheet("font-family: Consolas; font-size: 11px; color: #64748B;")
        elif state == BlockState.READ_FAILED:
            self.lbl_state_badge.setText("● 加密受阻")
            self.lbl_state_badge.setStyleSheet("color: #F87171; font-size: 10px; font-weight: bold;")
            self.lbl_hex_stream.setText("?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ??")
            self.lbl_hex_stream.setStyleSheet("font-family: Consolas; font-size: 11px; color: #F87171; font-weight: bold;")
        else:
            self.lbl_state_badge.setText("● 正常读取")
            self.lbl_state_badge.setStyleSheet("color: #34D399; font-size: 10px; font-weight: bold;")
            self.lbl_hex_stream.setText(" ".join(f"{b:02X}" for b in block_data))
            self.lbl_hex_stream.setStyleSheet("font-family: Consolas; font-size: 11px; color: #38BDF8; font-weight: bold;")

        # 2. 清除并重新构建动态透视内容
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 3. 动态渲染语义透视
        if state == BlockState.UNREAD:
            self._render_unread_info()
        elif state == BlockState.READ_FAILED:
            self._render_failed_info()
        elif is_block0:
            self._render_block0_info(block_data)
        elif is_trailer:
            self._render_trailer_info(block_data)
        else:
            vb = parse_value_block(block_data)
            if vb:
                self._render_value_block_info(vb, block_data)
            else:
                self._render_generic_data_info(block_data)

        self.btn_trailer.setEnabled(is_trailer)

    def _render_unread_info(self):
        lbl = QLabel("该块尚未载入或读取，数据暂无。\n\n• 可通过【一键读卡】从硬件读出\n• 或在表格中双击直接编辑填写数据")
        lbl.setStyleSheet("color: #64748B; font-size: 11px; padding: 6px;")
        lbl.setWordWrap(True)
        self.content_layout.addWidget(lbl)

    def _render_failed_info(self):
        lbl = QLabel("⚠️ 扇区密码受保护或未命中有效密钥。\n\n• PN532 读取该块时认证失败 (Read Block Failed)\n• 建议使用【字典破解】或加载更多字典并发解密")
        lbl.setStyleSheet("color: #F87171; font-size: 11px; padding: 6px;")
        lbl.setWordWrap(True)
        self.content_layout.addWidget(lbl)

        btn_manual = QPushButton("🔑 手动输入密钥解密")
        btn_manual.setStyleSheet(
            "background-color: #7C3AED; color: #FFFFFF; font-weight: bold; padding: 6px;"
        )
        btn_manual.setToolTip("手动输入该扇区的 KeyA/KeyB 进行测试解密并读取")
        btn_manual.clicked.connect(lambda: self.sig_manual_decrypt.emit(self.current_block_idx))
        self.content_layout.addWidget(btn_manual)

        self.content_layout.addStretch(1)

    def _render_block0_info(self, data: bytes):
        """渲染 Block 0 厂商与 UID 校验透视"""
        uid4 = data[:4]
        calc_bcc = uid4[0] ^ uid4[1] ^ uid4[2] ^ uid4[3]
        stored_bcc = data[4]
        bcc_match = (calc_bcc == stored_bcc)

        uid_hex = " ".join(f"{b:02X}" for b in uid4)
        uid_rev = " ".join(f"{b:02X}" for b in uid4[::-1])
        sak = data[5]
        atqa = f"{data[6]:02X} {data[7]:02X}"

        info_box = QFrame()
        info_box.setStyleSheet("background-color: #1E293B; border-radius: 4px; padding: 4px;")
        lay = QVBoxLayout(info_box)
        lay.setSpacing(3)

        lay.addWidget(self._row_label("卡号 (UID):", uid_hex, "#FFB300"))
        lay.addWidget(self._row_label("反序 UID:", uid_rev, "#E2E8F0"))
        bcc_status = f"{stored_bcc:02X} ({'✔ 校验通过' if bcc_match else '✘ 损坏'})"
        bcc_color = "#34D399" if bcc_match else "#EF4444"
        lay.addWidget(self._row_label("BCC 校验和:", bcc_status, bcc_color))
        lay.addWidget(self._row_label("SAK 标志位:", f"0x{sak:02X} ({'M1 S50 1K' if sak == 0x08 else '其他'})", "#38BDF8"))
        lay.addWidget(self._row_label("ATQA 响应:", f"0x{atqa}", "#94A3B8"))

        mfg_hex = " ".join(f"{b:02X}" for b in data[8:16])
        lay.addWidget(self._row_label("厂商参数:", mfg_hex, "#64748B"))

        self.content_layout.addWidget(info_box)

    def _render_trailer_info(self, data: bytes):
        """渲染扇区尾块 Key A / 控制字 / Key B 深度解析"""
        key_a_hex = " ".join(f"{b:02X}" for b in data[0:6])
        key_b_hex = " ".join(f"{b:02X}" for b in data[10:16])
        ac_hex = " ".join(f"{b:02X}" for b in data[6:10])

        ac_info = AccessBitsDecoder.decode(data[6:10])
        valid = ac_info.get("valid", False)

        box = QFrame()
        box.setStyleSheet("background-color: #1E293B; border-radius: 4px; padding: 4px;")
        lay = QVBoxLayout(box)
        lay.setSpacing(3)

        lay.addWidget(self._row_label("Key A 密钥:", key_a_hex, "#4ADE80"))
        lay.addWidget(self._row_label("Key B 密钥:", key_b_hex, "#60A5FA"))
        val_status = f"{ac_hex} ({'✔ 合法' if valid else '✘ 错误'})"
        val_color = "#FBBF24" if valid else "#EF4444"
        lay.addWidget(self._row_label("控制字 (AC):", val_status, val_color))

        if valid and "blocks" in ac_info:
            b_desc = ac_info["blocks"].get("block_0", {}).get("desc", "-")
            t_desc = ac_info["blocks"].get("trailer", {}).get("desc", "-")
            lay.addWidget(self._row_label("数据块权限:", b_desc, "#E2E8F0"))
            lay.addWidget(self._row_label("尾块权限:", t_desc, "#94A3B8"))

        self.content_layout.addWidget(box)

    def _render_value_block_info(self, vb: Dict[str, Any], raw: bytes):
        """渲染 Mifare 钱包数据块"""
        box = QFrame()
        box.setStyleSheet("background-color: #1E293B; border-radius: 4px; padding: 4px;")
        lay = QVBoxLayout(box)
        lay.setSpacing(3)

        lay.addWidget(self._row_label("钱包余额 (Dec):", f"{vb['value']:,}", "#34D399"))
        lay.addWidget(self._row_label("折算金额:", vb["amount_str"], "#F59E0B"))
        lay.addWidget(self._row_label("备份地址:", f"Block {vb['backup_addr']:02d}", "#38BDF8"))
        lay.addWidget(self._row_label("反码校验:", "✔ 标准 3 重校验有效", "#10B981"))

        self.content_layout.addWidget(box)

    def _render_generic_data_info(self, data: bytes):
        """渲染普通数据块 ASCII 与整数解码"""
        asc_str = "".join(chr(x) if 32 <= x <= 126 else "." for x in data)
        is_all_zero = all(x == 0 for x in data)
        is_all_ff = all(x == 0xFF for x in data)

        u32_le = struct.unpack("<I", data[0:4])[0]
        u32_be = struct.unpack(">I", data[0:4])[0]

        box = QFrame()
        box.setStyleSheet("background-color: #1E293B; border-radius: 4px; padding: 4px;")
        lay = QVBoxLayout(box)
        lay.setSpacing(3)

        lay.addWidget(self._row_label("ASCII 预览:", asc_str, "#F8FAFC"))
        if is_all_zero:
            lay.addWidget(self._row_label("特征标记:", "全 0x00 空数据块", "#64748B"))
        elif is_all_ff:
            lay.addWidget(self._row_label("特征标记:", "全 0xFF 填充数据块", "#FBBF24"))
        else:
            lay.addWidget(self._row_label("特征标记:", "含有效用户数据", "#38BDF8"))

        lay.addWidget(self._row_label("小端 32位:", f"{u32_le}", "#94A3B8"))
        lay.addWidget(self._row_label("大端 32位:", f"{u32_be}", "#94A3B8"))

        self.content_layout.addWidget(box)

    def _row_label(self, title: str, value: str, val_color: str) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("font-size: 10px; color: #94A3B8; font-weight: bold;")
        lbl_v = QLabel(value)
        lbl_v.setStyleSheet(f"font-size: 11px; color: {val_color}; font-family: Consolas;")
        lbl_v.setWordWrap(True)

        h.addWidget(lbl_t)
        h.addStretch(1)
        h.addWidget(lbl_v)
        return w


# ==============================================================================
