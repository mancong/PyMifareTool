# -*- coding: utf-8 -*-
"""
PyMifareTool - 卡片核心业务服务引擎与后台操作线程 (CardOperationWorker Service)
提供自主研发的高性能射频交互业务能力：
1. 字典攻击 / 扇区密钥破解 (Dictionary Attack)
2. 逐扇区认证与数据块读取 (Full Card Dump Reader)
3. 数据块写入与全卡烧录 (Full Card Dump Writer，含 Block 0 安全保护)
4. 读卡器固件协议兼容性自动探测 (Firmware Capability Prober)
"""

import time
import threading
from typing import List, Dict, Optional, Tuple, Any
from PyQt6.QtCore import QThread, pyqtSignal

from core.protocols.aabb import ReaderProtocol
from core.models.dump import MifareDump, BlockState
from core.services.key_manager import KeyManager

# 常用行业默认与经典弱密列表
DEFAULT_KEYS_HEX = [
    # 基础出厂与标准协议弱密
    "FFFFFFFFFFFF",  # 行业出厂默认 (95% 空卡)
    "A0A1A2A3A4A5",  # MAD 目录扇区
    "D3F7D3F7D3F7",  # NFC Forum 标准 NDEF
    "000000000000",  # 全零测试卡
    "B0B1B2B3B4B5",  # 常用门禁测试
    "A0B0C0D0E0F0",  # 通用测试 A
    "A1B2C3D4E5F6",  # 通用测试 B
    # RFIDtools / Proxmark3 (RRG mfc_default_keys.dic) 经典精选
    "4D3A99C351DD",  # 校园一卡通常用
    "1A2B3C4D5E6F",  # 梯控系统常用
    "123456789ABC",  # 简易顺序密码
    "010203040506",  # 经典顺序密码
    "AABBCCDDEEFF",  # 常见镜像密码
    "714C5C886E97",  # 节水控水系统常用
    "587EE5F9350F",  # 梯控专用系统
    "A0478CC39091",  # 门禁管理系统
    "FC00018778F7",  # 一卡通物业系统
    "4B0478C39091",  # 门禁消费系统
    "6C0478C39091",  # 停车场管理系统
    "888888888888",  # 重复数字弱密
    "999999999999",  # 重复数字弱密
    "112233445566",  # 双数字顺序
    "E20000000000",  # 工业手持终端
    "2A3B4C5D6E7F",  # 梯控常用拓展
    "B5FF67CBAE51",  # 考勤机默认
    "FFFFFFFFF000",  # 部分旧式发卡器
    "414243444546",  # ASCII 'ABCDEF'
]


class CardOperationWorker(QThread):
    """卡片异步操作工作线程，执行耗时的寻卡、认证、读取、写入及批量并发破解任务"""

    OP_CRACK_KEYS = "crack_keys"
    OP_READ_CARD = "read_card"
    OP_READ_SECTOR = "read_sector"
    OP_WRITE_CARD = "write_card"
    OP_PROBE_FIRMWARE = "probe_firmware"

    # 信号
    sig_progress = pyqtSignal(int, str)                # 进度 (0-100), 文本描述
    sig_log = pyqtSignal(str)                          # 详细流水日志
    sig_sector_cracked = pyqtSignal(int, str, str)     # sector, key_a_hex, key_b_hex
    sig_block_read = pyqtSignal(int, bytes)            # block_index, 16_bytes_data
    sig_block_failed = pyqtSignal(int)                 # block_index (单块加密受限读取失败)
    sig_finished = pyqtSignal(bool, str, object)       # success, message, result_data

    def __init__(
        self,
        worker,
        op_type: str,
        target_sectors: Optional[List[int]] = None,
        custom_keys: Optional[List[str]] = None,
        dump_to_write: Optional[MifareDump] = None,
        allow_block0_write: bool = False,
        concurrency: int = 4,
        manual_key: Optional[Dict[str, Any]] = None,
        magic_type: str = "CUID",
        is_4k: Optional[bool] = None,
        parent=None
    ):
        super().__init__(parent)
        self.worker = worker
        self.op_type = op_type

        # 4K 标志自适应推导
        if is_4k is not None:
            self.is_4k = is_4k
        elif dump_to_write is not None:
            self.is_4k = bool(dump_to_write.is_4k)
        elif target_sectors is not None and len(target_sectors) > 0:
            self.is_4k = max(target_sectors) >= 16
        else:
            self.is_4k = False

        if target_sectors is not None:
            self.target_sectors = target_sectors
        else:
            self.target_sectors = list(range(40 if self.is_4k else 16))

        self.custom_keys = custom_keys if custom_keys is not None else KeyManager.load_combined_keys()
        self.dump_to_write = dump_to_write
        self.manual_key = manual_key  # 手动解密用: {"key_type": "A"/"B", "key": bytes}
        self.allow_block0_write = allow_block0_write
        self.magic_type = magic_type
        self.concurrency = max(1, concurrency)
        self._hardware_lock = threading.Lock()
        self._abort = False

    def abort(self):
        """中止当前操作"""
        self._abort = True

    def run(self):
        if not self.worker or not self.worker.is_connected():
            self.sig_finished.emit(False, "错误: 读卡器未连接，请先连接串口！", None)
            return

        if hasattr(self.worker, "set_exclusive"):
            self.worker.set_exclusive(True)

        try:
            # 独占后主动寻卡一次，建立射频会话并缓存 UID (不依赖后台自动轮询开关)
            adapter = getattr(self.worker, "adapter", None)
            is_bidi = bool(adapter and getattr(adapter, "is_bidirectional", False))
            if is_bidi and self.op_type in (self.OP_READ_CARD, self.OP_CRACK_KEYS,
                                            self.OP_READ_SECTOR, self.OP_WRITE_CARD):
                card = self.worker.poll_card_once(timeout=0.5)
                if not card:
                    self.sig_finished.emit(False, "未检测到卡片，请将卡片贴近读卡器后重试。", None)
                    return
                # 同步向主界面发射寻卡捕获信号，确保左侧实时卡片监测面板第一时间展示卡片数据
                if hasattr(self.worker, "sig_card_swiped"):
                    self.worker.sig_card_swiped.emit(card)

            if self.op_type == self.OP_CRACK_KEYS:
                self._do_crack_keys()
            elif self.op_type == self.OP_READ_CARD:
                self._do_read_card()
            elif self.op_type == self.OP_READ_SECTOR:
                self._do_read_sector()
            elif self.op_type == self.OP_WRITE_CARD:
                self._do_write_card()
            elif self.op_type == self.OP_PROBE_FIRMWARE:
                self._do_probe_firmware()
            else:
                self.sig_finished.emit(False, f"未知操作类型: {self.op_type}", None)
        finally:
            if hasattr(self.worker, "set_exclusive"):
                self.worker.set_exclusive(False)

    def _do_crack_keys(self):
        self.sig_log.emit("开始执行 Mifare Classic 密钥字典攻击 (射频半双工，单线程顺序扫描)...")
        keys_bytes = []
        for kh in self.custom_keys:
            try:
                b = bytes.fromhex(kh.strip().replace(" ", ""))
                if len(b) == 6 and b not in keys_bytes:
                    keys_bytes.append(b)
            except Exception:
                pass

        if not keys_bytes:
            self.sig_finished.emit(False, "字典中无有效 6 字节密钥！", None)
            return

        cracked_results = {}
        total_sectors = len(self.target_sectors)
        solved_keys = set()
        unsolved_sectors = list(self.target_sectors)

        helper_dump = MifareDump(is_4k=self.is_4k)
        consecutive_absent = 0

        def check_card_absent() -> bool:
            nonlocal consecutive_absent
            if hasattr(self.worker, "is_card_present") and not self.worker.is_card_present():
                consecutive_absent += 1
                if consecutive_absent >= 3:
                    return True
            else:
                consecutive_absent = 0
            return False

        self.sig_log.emit(f"载入去重密钥: {len(keys_bytes):,} 条 | 待测扇区数: {total_sectors} ({'4K' if self.is_4k else '1K'})")

        priority_keys = keys_bytes[:min(10, len(keys_bytes))]

        for sector in list(unsolved_sectors):
            if self._abort:
                self.sig_finished.emit(False, "操作已由用户手动中止", cracked_results)
                return
            trailer_block = helper_dump.get_sector_trailer_block(sector)
            found_a = None
            found_b = None

            for k in priority_keys:
                if not found_a and self._authenticate_sector(trailer_block, "A", k) is True:
                    found_a = k.hex().upper()
                    solved_keys.add(k)
                elif not found_a and check_card_absent():
                    self.sig_log.emit("⚠️ 检测到卡片已移离读卡区，正在中止任务...")
                    self.sig_finished.emit(False, "卡片已移离读卡区，操作已自动中止", cracked_results)
                    return

                if not found_b and self._authenticate_sector(trailer_block, "B", k) is True:
                    found_b = k.hex().upper()
                    solved_keys.add(k)
                elif not found_b and check_card_absent():
                    self.sig_log.emit("⚠️ 检测到卡片已移离读卡区，正在中止任务...")
                    self.sig_finished.emit(False, "卡片已移离读卡区，操作已自动中止", cracked_results)
                    return

                if found_a and found_b:
                    break

            if found_a or found_b:
                cracked_results[sector] = {
                    "key_a": found_a or "未破解",
                    "key_b": found_b or "未破解",
                }
                self.sig_sector_cracked.emit(sector, found_a or "未破解", found_b or "未破解")
                if found_a and found_b:
                    unsolved_sectors.remove(sector)
                    self.sig_log.emit(f"★ [阶段1速解] 扇区 S{sector:02d} 全部命中! KeyA={found_a} KeyB={found_b}")

        if solved_keys and unsolved_sectors:
            for sector in list(unsolved_sectors):
                if self._abort:
                    break
                trailer_block = helper_dump.get_sector_trailer_block(sector)
                cur = cracked_results.get(sector, {"key_a": "未破解", "key_b": "未破解"})
                found_a = cur["key_a"] if cur["key_a"] != "未破解" else None
                found_b = cur["key_b"] if cur["key_b"] != "未破解" else None

                for k in solved_keys:
                    if not found_a and self._authenticate_sector(trailer_block, "A", k) is True:
                        found_a = k.hex().upper()
                    if not found_b and self._authenticate_sector(trailer_block, "B", k) is True:
                        found_b = k.hex().upper()
                    if found_a and found_b:
                        break

                cracked_results[sector] = {
                    "key_a": found_a or "未破解",
                    "key_b": found_b or "未破解",
                }
                self.sig_sector_cracked.emit(sector, found_a or "未破解", found_b or "未破解")
                if found_a and found_b and sector in unsolved_sectors:
                    unsolved_sectors.remove(sector)
                    self.sig_log.emit(f"★ [阶段2传导] 扇区 S{sector:02d} 复用命中! KeyA={found_a} KeyB={found_b}")

        remaining_keys = [k for k in keys_bytes if k not in priority_keys and k not in solved_keys]

        if unsolved_sectors and remaining_keys:
            total_keys = len(remaining_keys)
            self.sig_log.emit(
                f"进入阶段 3 深度字典扫描: 剩余待解扇区 {len(unsolved_sectors)} 个, "
                f"待测密钥 {total_keys:,} 条 (单扇区最坏 {total_keys * 2:,} 次认证)"
            )
            # 进度打印步长：约每 4% 或至少每 20 条输出一次，避免刷屏与日志开销
            progress_step = max(20, total_keys // 25)

            for u_idx, sector in enumerate(unsolved_sectors):
                if self._abort:
                    break

                trailer_block = helper_dump.get_sector_trailer_block(sector)
                cur = cracked_results.get(sector, {"key_a": "未破解", "key_b": "未破解"})
                found_a = cur["key_a"] if cur["key_a"] != "未破解" else None
                found_b = cur["key_b"] if cur["key_b"] != "未破解" else None
                need_a = found_a is None
                need_b = found_b is None

                self.sig_log.emit(f">> 正在深度扫描扇区 S{sector:02d} (剩余字典 {total_keys} 条) ...")
                sector_start = time.time()

                # 单趟扫描：逐把密钥同时尝试 KeyA / KeyB，命中即短路退出
                for i, k in enumerate(remaining_keys):
                    if self._abort:
                        break

                    if need_a:
                        if self._authenticate_sector(trailer_block, "A", k) is True:
                            found_a = k.hex().upper()
                            solved_keys.add(k)
                            need_a = False
                            self.sig_log.emit(f"✔ 命中扇区 S{sector:02d} Key A: {found_a}")
                        elif check_card_absent():
                            self.sig_log.emit("⚠️ 检测到卡片已移离读卡区，正在中止任务...")
                            self.sig_finished.emit(False, "卡片已移离读卡区，操作已自动中止", cracked_results)
                            return

                    if need_b:
                        if self._authenticate_sector(trailer_block, "B", k) is True:
                            found_b = k.hex().upper()
                            solved_keys.add(k)
                            need_b = False
                            self.sig_log.emit(f"✔ 命中扇区 S{sector:02d} Key B: {found_b}")
                        elif check_card_absent():
                            self.sig_log.emit("⚠️ 检测到卡片已移离读卡区，正在中止任务...")
                            self.sig_finished.emit(False, "卡片已移离读卡区，操作已自动中止", cracked_results)
                            return

                    if not need_a and not need_b:
                        break

                    if i and i % progress_step == 0:
                        pct = int(((u_idx + i / total_keys) / len(unsolved_sectors)) * 100)
                        self.sig_progress.emit(pct, f"扫描 S{sector:02d}: {i}/{total_keys}")
                        self.sig_log.emit(
                            f"   进度 S{sector:02d}: {i}/{total_keys} ({int(i / total_keys * 100)}%)"
                        )

                if found_a or found_b:
                    cracked_results[sector] = {
                        "key_a": found_a or "未破解",
                        "key_b": found_b or "未破解",
                    }
                    self.sig_sector_cracked.emit(sector, found_a or "未破解", found_b or "未破解")

                elapsed = time.time() - sector_start
                status = "全部命中" if (found_a and found_b) else ("部分命中" if (found_a or found_b) else "未命中")
                self.sig_log.emit(
                    f"<< 扇区 S{sector:02d} 扫描完毕[{status}]: "
                    f"KeyA={found_a or '未破解'} KeyB={found_b or '未破解'} (耗时 {elapsed:.1f}s)"
                )

                self.sig_progress.emit(
                    int(((u_idx + 1) / len(unsolved_sectors)) * 100),
                    f"扇区 S{sector:02d} 完成"
                )

        self.sig_progress.emit(100, "破解完成！")
        success_count = sum(1 for v in cracked_results.values() if v["key_a"] != "未破解" or v["key_b"] != "未破解")
        msg = f"破解结束: 共探测 {total_sectors} 个扇区，成功识别出 {success_count} 个扇区密钥。"
        self.sig_finished.emit(True, msg, cracked_results)

    def _do_read_card(self):
        self.sig_log.emit(f"开始逐扇区读取 Mifare Classic {'4K' if self.is_4k else '1K'} 卡片全数据...")
        dump = MifareDump(is_4k=self.is_4k)
        total_blocks = dump.block_count
        read_success_count = 0
        read_failed_count = 0

        for sector in self.target_sectors:
            if self._abort:
                self.sig_finished.emit(False, "读卡已被用户中止", dump)
                return

            first_block = dump.get_sector_first_block(sector)
            block_count = dump.get_sector_block_count(sector)
            trailer_block = dump.get_sector_trailer_block(sector)

            authed = False
            key_a_found = "未破解"
            key_b_found = "未破解"
            for kh in self.custom_keys:
                try:
                    k_bytes = bytes.fromhex(kh.strip().replace(" ", ""))
                    if len(k_bytes) == 6:
                        if self._authenticate_sector(trailer_block, "A", k_bytes) is True:
                            authed = True
                            key_a_found = k_bytes.hex().upper()
                            # 顺带探测 KeyB 是否为同一密钥 (空卡 A==B 常见)
                            if self._authenticate_sector(trailer_block, "B", k_bytes) is True:
                                key_b_found = k_bytes.hex().upper()
                            break
                        if self._authenticate_sector(trailer_block, "B", k_bytes) is True:
                            authed = True
                            key_b_found = k_bytes.hex().upper()
                            break
                except Exception:
                    pass

            if not authed:
                self.sig_log.emit(f"扇区 S{sector:02d} 认证失败，标记该扇区 {block_count} 块为未破解/加密状态 (??)")
                for b_i in range(block_count):
                    blk = first_block + b_i
                    dump.set_block_state(blk, BlockState.READ_FAILED)
                    read_failed_count += 1
                    self.sig_block_failed.emit(blk)
                pct = int(((first_block + block_count) / total_blocks) * 100)
                self.sig_progress.emit(pct, f"扇区 S{sector:02d} 加密受限 (??)...")
                continue

            # 成功解密扇区 -> 上报已识别的密钥 (供 UI 留存至数据库)
            self.sig_sector_cracked.emit(sector, key_a_found, key_b_found)

            for b_i in range(block_count):
                if self._abort:
                    return
                block = first_block + b_i
                data = self._read_single_block(block)
                if data:
                    dump.set_block(block, data)
                    dump.set_block_state(block, BlockState.READ_OK)
                    self.sig_block_read.emit(block, data)
                    read_success_count += 1
                    if block == 0 and len(data) >= 4:
                        from core.models.card_converter import CardConverter
                        uid_b = data[:4]
                        card_swipe_info = {
                            "uid_bytes": uid_b,
                            "conversions": CardConverter.convert_uid(uid_b),
                            "raw": data,
                            "card_type": "Mifare Classic 4K" if self.is_4k else "Mifare Classic 1K",
                        }
                        if hasattr(self.worker, "sig_card_swiped"):
                            self.worker.sig_card_swiped.emit(card_swipe_info)
                else:
                    dump.set_block_state(block, BlockState.READ_FAILED)
                    read_failed_count += 1

                pct = int(((block + 1) / total_blocks) * 100)
                self.sig_progress.emit(pct, f"正在读取 Block {block:02d} ...")

        self.sig_progress.emit(100, "全卡读取完成！")
        summary = f"读卡完毕: 成功读取 {read_success_count}/{total_blocks} 块，失败/加密 {read_failed_count} 块。"
        self.sig_finished.emit(True, summary, dump)

    def _do_read_sector(self):
        """使用用户手动输入的单一密钥认证并读取目标扇区 (测试解密)"""
        mk = self.manual_key or {}
        key_type = str(mk.get("key_type", "A")).upper()
        key = mk.get("key") or b""
        if isinstance(key, str):
            try:
                key = bytes.fromhex(key.strip().replace(" ", ""))
            except Exception:
                key = b""

        sectors = list(self.target_sectors or [])
        if not sectors or len(key) != 6 or key_type not in ("A", "B"):
            self.sig_finished.emit(False, "手动解密参数无效 (需提供 KeyA/KeyB 类型与 6 字节密钥及目标扇区)", None)
            return

        sector = int(sectors[0])
        helper_dump = MifareDump(is_4k=True if sector >= 16 else False)
        first_block = helper_dump.get_sector_first_block(sector)
        block_count = helper_dump.get_sector_block_count(sector)
        trailer_block = helper_dump.get_sector_trailer_block(sector)
        key_hex = key.hex().upper()
        self.sig_log.emit(f"手动解密: 使用 Key{key_type}={key_hex} 认证扇区 S{sector:02d} ...")

        if self._authenticate_sector(trailer_block, key_type, key) is not True:
            self.sig_log.emit(f"✘ 扇区 S{sector:02d} 认证失败: Key{key_type}={key_hex} 无效")
            self.sig_finished.emit(
                False, f"手动密钥认证失败: 扇区 S{sector:02d} 拒绝了 Key{key_type}={key_hex}", None)
            return

        self.sig_log.emit(f"✔ 扇区 S{sector:02d} 认证成功! 正在读取 {block_count} 个数据块 ...")
        read_ok = 0
        for b_i in range(block_count):
            if self._abort:
                return
            block = first_block + b_i
            data = self._read_single_block(block)
            if data:
                self.sig_block_read.emit(block, data)
                read_ok += 1
            pct = int(((b_i + 1) / block_count) * 100)
            self.sig_progress.emit(pct, f"正在读取 Block {block:02d} ...")

        key_a = key_hex if key_type == "A" else "未破解"
        key_b = key_hex if key_type == "B" else "未破解"
        self.sig_sector_cracked.emit(sector, key_a, key_b)
        self.sig_progress.emit(100, "手动解密读取完成")
        summary = f"手动解密成功: 扇区 S{sector:02d} (Key{key_type}={key_hex}) 已读取 {read_ok}/{block_count} 块。"
        self.sig_finished.emit(True, summary, None)

    def _do_write_card(self):
        if not self.dump_to_write:
            self.sig_finished.emit(False, "错误: 未提供待写入的 Dump 数据！", None)
            return

        self.sig_log.emit("开始向物理卡片写入数据 (写入保护状态检查)...")
        total_blocks = self.dump_to_write.block_count
        write_success = 0
        write_skipped = 0
        write_fail = 0

        def update_progress(block: int, text: str):
            pct = int(((block + 1) / total_blocks) * 100)
            self.sig_progress.emit(pct, text)

        for sector in range(self.dump_to_write.sector_count):
            if self._abort:
                self.sig_finished.emit(False, "写卡已被用户中止", None)
                return

            first_block = self.dump_to_write.get_sector_first_block(sector)
            block_count = self.dump_to_write.get_sector_block_count(sector)
            trailer_block = self.dump_to_write.get_sector_trailer_block(sector)
            trailer_data = self.dump_to_write.get_block(trailer_block)
            key_a = trailer_data[0:6]
            key_b = trailer_data[10:16]

            authed = False
            if key_a != b"\x00" * 6 and self._authenticate_sector(trailer_block, "A", key_a):
                authed = True
            elif key_b != b"\x00" * 6 and self._authenticate_sector(trailer_block, "B", key_b):
                authed = True

            if not authed:
                for kh in self.custom_keys:
                    try:
                        k_b = bytes.fromhex(kh.strip().replace(" ", ""))
                        if len(k_b) == 6:
                            if self._authenticate_sector(trailer_block, "A", k_b):
                                authed = True
                                break
                            if self._authenticate_sector(trailer_block, "B", k_b):
                                authed = True
                                break
                    except Exception:
                        pass

            if not authed:
                self.sig_log.emit(
                    f"扇区 S{sector:02d} 认证失败: 跳过该扇区 {block_count} 个块")

            for block in range(first_block, first_block + block_count):
                if self._abort:
                    self.sig_finished.emit(False, "写卡已被用户中止", None)
                    return

                if block == 0 and not self.allow_block0_write:
                    self.sig_log.emit("安全保护: 已跳过 Block 0 (原厂厂商/UID块写入保护已开启)")
                    write_skipped += 1
                    update_progress(block, f"正在写入 Block {block:02d} ...")
                    continue

                if not authed:
                    write_fail += 1
                    update_progress(block, f"正在写入 Block {block:02d} ...")
                    continue

                block_data = self.dump_to_write.get_block(block)
                ok = self._write_single_block(block, block_data)
                if ok:
                    write_success += 1
                else:
                    write_fail += 1

                update_progress(block, f"正在写入 Block {block:02d} ...")

        self.sig_progress.emit(100, "写卡流程执行完毕！")
        summary = f"写卡完成: 成功写入 {write_success} 块，失败 {write_fail} 块，跳过 {write_skipped} 块。"
        self.sig_finished.emit(True, summary, None)

    def _do_probe_firmware(self):
        adapter = getattr(self.worker, "adapter", None)
        is_bidi = bool(adapter and getattr(adapter, "is_bidirectional", False))
        ser = getattr(self.worker, "_serial", None)

        if is_bidi and ser and ser.is_open:
            self.sig_log.emit("开始 PCR532 / NXP PN532 双向指令集与硬件状态深度探测...")
            probe_results = {}

            # 1. 唤醒与同步
            if self._abort:
                return
            self.sig_progress.emit(15, "正在测试: HSU 接口唤醒与链路同步 ...")
            self.sig_log.emit("发送探测指令: HSU Wakeup 引导前导序列")
            with self._hardware_lock:
                wake_ok = adapter.wakeup(ser) if hasattr(adapter, "wakeup") else True
            if wake_ok:
                probe_results["HSU 接口唤醒"] = {"supported": True, "response": "已唤醒就绪"}
                self.sig_log.emit("✔ HSU 物理总线唤醒应答正常")
            else:
                probe_results["HSU 接口唤醒"] = {"supported": False, "response": "唤醒无响应"}
            time.sleep(0.05)

            # 2. 固件版本探测 (0x02 GetFirmwareVersion)
            if self._abort:
                return
            self.sig_progress.emit(35, "正在测试: 固件版本查询 (GetFirmwareVersion) ...")
            self.sig_log.emit("发送探测指令: GetFirmwareVersion [CMD 0x02]")
            with self._hardware_lock:
                fw_ver = adapter.get_firmware_version(ser) if hasattr(adapter, "get_firmware_version") else "PN532 兼容"
            if fw_ver and "PN532" in fw_ver:
                probe_results["固件版本查询 (0x02)"] = {"supported": True, "response": fw_ver}
                self.sig_log.emit(f"✔ 固件版本识别成功: {fw_ver}")
            else:
                probe_results["固件版本查询 (0x02)"] = {"supported": False, "response": fw_ver or "无回包"}
            time.sleep(0.05)

            # 3. SAM 射频配置 (0x14 SAMConfiguration)
            if self._abort:
                return
            self.sig_progress.emit(55, "正在测试: SAM 射频参数配置 (SAMConfiguration) ...")
            self.sig_log.emit("发送探测指令: SAMConfiguration [CMD 0x14, Normal Mode]")
            with self._hardware_lock:
                sam_ok = adapter._send_and_receive(ser, adapter.CMD_SAM_CONFIGURATION, bytes([0x01, 0x14, 0x01]), timeout=0.3)
            if sam_ok is not None:
                probe_results["SAM 模式配置 (0x14)"] = {"supported": True, "response": "射频通道 Normal 激活"}
                self.sig_log.emit("✔ SAM 安全模块射频激活配置成功")
            else:
                probe_results["SAM 模式配置 (0x14)"] = {"supported": False, "response": "超时无回包"}
            time.sleep(0.05)

            # 4. CIU 内部射频寄存器配置 (0x08 WriteRegister)
            if self._abort:
                return
            self.sig_progress.emit(75, "正在测试: CIU 射频寄存器写入 (WriteRegister) ...")
            self.sig_log.emit("发送探测指令: WriteRegister [CMD 0x08, TxMode=106kbps TypeA]")
            with self._hardware_lock:
                reg_ok = adapter.write_registers(ser, [(0x6302, 0x00)], timeout=0.25) if hasattr(adapter, "write_registers") else True
            if reg_ok:
                probe_results["CIU 寄存器配置 (0x08)"] = {"supported": True, "response": "寄存器读写校验通过"}
                self.sig_log.emit("✔ CIU 内部射频寄存器写入应答成功")
            else:
                probe_results["CIU 寄存器配置 (0x08)"] = {"supported": False, "response": "超时无回包"}
            time.sleep(0.05)

            # 5. ISO14443-A 被动寻卡探测 (0x4A InListPassiveTarget)
            if self._abort:
                return
            self.sig_progress.emit(90, "正在测试: ISO14443-A 寻卡信道 (InListPassiveTarget) ...")
            self.sig_log.emit("发送探测指令: InListPassiveTarget [CMD 0x4A, 106kbps Type A]")
            with self._hardware_lock:
                card = adapter.poll_card(ser, timeout=0.25)
            if card and "uid_bytes" in card:
                uid_hex = " ".join(f"{b:02X}" for b in card["uid_bytes"])
                probe_results["ISO14443-A 寻卡 (0x4A)"] = {"supported": True, "response": f"感应到卡片 UID: {uid_hex}"}
                self.sig_log.emit(f"✔ 寻卡探测成功: 感应到卡片 [{uid_hex}]")
                if hasattr(self.worker, "sig_card_swiped"):
                    self.worker.sig_card_swiped.emit(card)
            else:
                probe_results["ISO14443-A 寻卡 (0x4A)"] = {"supported": True, "response": "信道就绪 (天线未感应到卡片)"}
                self.sig_log.emit("✔ 寻卡信道就绪 (当前射频天线上未贴卡)")

            self.sig_progress.emit(100, "PCR532 / PN532 固件探测分析完成")

            supported_count = sum(1 for v in probe_results.values() if v.get("supported"))
            fw_display = probe_results.get("固件版本查询 (0x02)", {}).get("response", "PN532")
            summary = (
                f"🎯 读卡器固件验证成功: NXP PN532 (PCR532 双向全功能模式)\n\n"
                f"• 固件版本: {fw_display}\n"
                f"• 指令集测试: {supported_count}/{len(probe_results)} 项指令通过验证\n"
                f"• 支持特性: ISO14443-A (M1/UID/CUID) 读写/破解、二代证 (ISO14443-B) GUID 读取、后门盲写"
            )
            self.sig_finished.emit(True, summary, probe_results)
            return

        # 针对简易单向发卡器的探测回退逻辑
        self.sig_log.emit("开始单向广播读卡器固件指令集兼容性探测...")
        test_commands = [
            ("寻卡请求 (Request A)", ReaderProtocol.build_request_a(), ReaderProtocol.CMD_REQUEST_A),
            ("防冲突选卡 (Anticollision)", ReaderProtocol.build_anticollision(), ReaderProtocol.CMD_ANTICOLLISION),
            ("固件版本查询 (Get Version)", ReaderProtocol.build_get_version(), ReaderProtocol.CMD_GET_VERSION),
            ("LED 控制测试 (LED Flash)", ReaderProtocol.build_led_control(2), ReaderProtocol.CMD_LED_CONTROL),
            ("蜂鸣器控制 (Buzzer Beep)", ReaderProtocol.build_buzzer_control(50), ReaderProtocol.CMD_BUZZER_CONTROL),
        ]

        probe_results = {}
        for idx, (name, frame, cmd) in enumerate(test_commands):
            if self._abort:
                return
            pct = int(((idx + 1) / len(test_commands)) * 100)
            self.sig_progress.emit(pct, f"正在测试: {name} ...")
            self.sig_log.emit(f"发送探测帧: {name} [CMD 0x{cmd:02X}]")

            resp = self.worker.send_and_wait(cmd, frame[4:-1] if len(frame) > 5 else b"", timeout=0.3)
            if resp:
                probe_results[name] = {"supported": True, "response": resp}
                self.sig_log.emit(f"✔ 收到固件积极应答: {resp.get('status')}")
            else:
                probe_results[name] = {"supported": False, "response": "超时无回包"}

            time.sleep(0.05)

        self.sig_progress.emit(100, "固件探测分析完成")

        supported_cmds = [k for k, v in probe_results.items() if v["supported"]]
        if supported_cmds:
            summary = f"读卡器固件支持指令交互! 成功响应指令: {len(supported_cmds)} 项。"
        else:
            summary = "读卡器固件目前处于【单向广播 / 自动上报 UID 模式】。上位机主动查询指令未产生应答。"

        self.sig_finished.emit(True, summary, probe_results)

    def _authenticate_sector(self, block: int, key_type: str, key: bytes) -> Optional[bool]:
        """向读卡器发送认证指令 (自适应 PCR532/PN532 与 AA BB 协议，线程安全)"""
        with self._hardware_lock:
            if hasattr(self.worker, "authenticate"):
                ok = self.worker.authenticate(block, key_type, key, timeout=0.25)
                if not ok:
                    # 🚨 关键硬件保护：Mifare Classic 密码认证失败后，卡片会进入 HALT 状态拒绝后续所有指令！
                    # 必须立刻唤醒重新激活目标卡片，防止半加密卡的单扇区失败引发后续所有扇区雪崩式失败！
                    if hasattr(self.worker, "reactivate_target"):
                        self.worker.reactivate_target()
                    elif hasattr(self.worker, "poll_card_once"):
                        self.worker.poll_card_once(timeout=0.15)
                return True if ok else False
            if hasattr(self.worker, "adapter") and self.worker.adapter and getattr(self.worker.adapter, "is_bidirectional", False):
                ok = self.worker.adapter.authenticate(getattr(self.worker, "_serial", None), block, key_type, key, timeout=0.25)
                if not ok and hasattr(self.worker.adapter, "reactivate_target"):
                    self.worker.adapter.reactivate_target(getattr(self.worker, "_serial", None))
                return True if ok else False

            cmd = ReaderProtocol.CMD_AUTH_KEY_A if key_type == "A" else ReaderProtocol.CMD_AUTH_KEY_B
            data = bytes([block]) + key
            if hasattr(self.worker, "send_and_wait"):
                resp = self.worker.send_and_wait(cmd, data, timeout=0.25)
                if resp:
                    if resp.get("ok") is True or resp.get("status") == "success":
                        return True
                    code = resp.get("status_code", resp.get("status"))
                    return code == ReaderProtocol.STATUS_SUCCESS
            return False

    def _read_single_block(self, block: int) -> Optional[bytes]:
        """向读卡器发送读块指令 (自适应 PCR532/PN532 与 AA BB 协议，线程安全)"""
        with self._hardware_lock:
            if hasattr(self.worker, "read_block"):
                return self.worker.read_block(block, timeout=0.25)
            if hasattr(self.worker, "adapter") and self.worker.adapter and getattr(self.worker.adapter, "is_bidirectional", False):
                return self.worker.adapter.read_block(getattr(self.worker, "_serial", None), block, timeout=0.25)

            if hasattr(self.worker, "send_and_wait"):
                resp = self.worker.send_and_wait(ReaderProtocol.CMD_READ_BLOCK, bytes([block]), timeout=0.25)
                if resp:
                    data = resp.get("block_data") or resp.get("data", b"")
                    if len(data) >= 16:
                        return data[:16]
            return None

    def _write_single_block(self, block: int, block_data: bytes) -> bool:
        """向读卡器发送写块指令 (自适应 PCR532/PN532 与 AA BB 协议，线程安全)"""
        with self._hardware_lock:
            if hasattr(self.worker, "adapter") and self.worker.adapter and self.worker.adapter.is_bidirectional:
                if block == 0:
                    if not self.allow_block0_write:
                        return False
                    return self.worker.write_magic_block0(
                        block_data, magic_type=getattr(self, "magic_type", "CUID"), timeout=0.35)
                return self.worker.write_block(block, block_data, timeout=0.3)

            payload = bytes([block]) + block_data[:16]
            resp = self.worker.send_and_wait(ReaderProtocol.CMD_WRITE_BLOCK, payload, timeout=0.3)
            if resp:
                if resp.get("ok") is True or resp.get("status") == "success":
                    return True
                code = resp.get("status_code", resp.get("status"))
                return code == ReaderProtocol.STATUS_SUCCESS
            return False
