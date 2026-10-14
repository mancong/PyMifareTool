# -*- coding: utf-8 -*-
"""
PyMifareTool - 卡片核心业务服务引擎与后台操作线程 (CardOperationWorker Service)
实现对标 MifareOneTool 的核心交互特性：
1. 字典攻击 / 扇区密钥破解 (Dictionary Attack)
2. 逐扇区认证与数据块读取 (Full Card Dump Reader)
3. 数据块写入与全卡烧录 (Full Card Dump Writer，含 Block 0 安全保护)
4. 读卡器固件协议兼容性自动探测 (Firmware Capability Prober)
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    OP_WRITE_CARD = "write_card"
    OP_PROBE_FIRMWARE = "probe_firmware"

    # 信号
    sig_progress = pyqtSignal(int, str)                # 进度 (0-100), 文本描述
    sig_log = pyqtSignal(str)                          # 详细流水日志
    sig_sector_cracked = pyqtSignal(int, str, str)     # sector, key_a_hex, key_b_hex
    sig_block_read = pyqtSignal(int, bytes)            # block_index, 16_bytes_data
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
        parent=None
    ):
        super().__init__(parent)
        self.worker = worker
        self.op_type = op_type
        self.target_sectors = target_sectors if target_sectors is not None else list(range(16))
        self.custom_keys = custom_keys if custom_keys is not None else KeyManager.load_combined_keys()
        self.dump_to_write = dump_to_write
        self.allow_block0_write = allow_block0_write
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
            if self.op_type == self.OP_CRACK_KEYS:
                self._do_crack_keys()
            elif self.op_type == self.OP_READ_CARD:
                self._do_read_card()
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
        self.sig_log.emit(f"开始执行 Mifare Classic 密钥字典攻击 (并发线程数: {self.concurrency})...")
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

        self.sig_log.emit(f"载入去重密钥: {len(keys_bytes):,} 条 | 待测扇区数: {total_sectors}")

        priority_keys = keys_bytes[:min(10, len(keys_bytes))]

        for sector in list(unsolved_sectors):
            if self._abort:
                self.sig_finished.emit(False, "操作已由用户手动中止", cracked_results)
                return
            trailer_block = sector * 4 + 3
            found_a = None
            found_b = None

            for k in priority_keys:
                if not found_a and self._authenticate_sector(trailer_block, "A", k) is True:
                    found_a = k.hex().upper()
                    solved_keys.add(k)
                if not found_b and self._authenticate_sector(trailer_block, "B", k) is True:
                    found_b = k.hex().upper()
                    solved_keys.add(k)
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
                trailer_block = sector * 4 + 3
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
            self.sig_log.emit(f"进入阶段 3 并发批次字典攻击: 剩余待解扇区 {len(unsolved_sectors)} 个, 待测密钥 {len(remaining_keys)} 条...")

            for u_idx, sector in enumerate(unsolved_sectors):
                if self._abort:
                    break

                pct = int(((total_sectors - len(unsolved_sectors) + u_idx) / total_sectors) * 100)
                self.sig_progress.emit(pct, f"正在并发批量破解扇区 S{sector:02d}...")

                trailer_block = sector * 4 + 3
                cur = cracked_results.get(sector, {"key_a": "未破解", "key_b": "未破解"})
                found_a = cur["key_a"] if cur["key_a"] != "未破解" else None
                found_b = cur["key_b"] if cur["key_b"] != "未破解" else None

                target_types = []
                if not found_a:
                    target_types.append("A")
                if not found_b:
                    target_types.append("B")

                chunk_size = max(5, 20 if self.concurrency <= 8 else 10)
                key_chunks = [remaining_keys[i:i + chunk_size] for i in range(0, len(remaining_keys), chunk_size)]

                for k_type in target_types:
                    if self._abort:
                        break

                    solved_this_type = False
                    solved_key_hex = None

                    def _worker_task(chunk):
                        for k in chunk:
                            if solved_this_type or self._abort:
                                return None
                            if self._authenticate_sector(trailer_block, k_type, k) is True:
                                return k
                        return None

                    with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
                        futures = {executor.submit(_worker_task, chk): chk for chk in key_chunks}
                        for future in as_completed(futures):
                            if solved_this_type or self._abort:
                                break
                            hit_key = future.result()
                            if hit_key:
                                solved_this_type = True
                                solved_key_hex = hit_key.hex().upper()
                                solved_keys.add(hit_key)
                                break

                    if solved_key_hex:
                        if k_type == "A":
                            found_a = solved_key_hex
                        else:
                            found_b = solved_key_hex
                        self.sig_log.emit(f"✔ 并发命中扇区 S{sector:02d} Key {k_type}: {solved_key_hex}")

                cracked_results[sector] = {
                    "key_a": found_a or "未破解",
                    "key_b": found_b or "未破解",
                }
                self.sig_sector_cracked.emit(sector, found_a or "未破解", found_b or "未破解")

        self.sig_progress.emit(100, "破解完成！")
        success_count = sum(1 for v in cracked_results.values() if v["key_a"] != "未破解" or v["key_b"] != "未破解")
        msg = f"破解结束: 共探测 {total_sectors} 个扇区，成功识别出 {success_count} 个扇区密钥。"
        self.sig_finished.emit(True, msg, cracked_results)

    def _do_read_card(self):
        self.sig_log.emit("开始逐扇区读取 Mifare Classic 卡片全数据...")
        dump = MifareDump(is_4k=False)
        total_blocks = 64
        read_success_count = 0
        read_failed_count = 0

        for sector in range(16):
            if self._abort:
                self.sig_finished.emit(False, "读卡已被用户中止", dump)
                return

            trailer_block = sector * 4 + 3
            first_block = sector * 4

            authed = False
            for kh in self.custom_keys:
                try:
                    k_bytes = bytes.fromhex(kh.strip().replace(" ", ""))
                    if len(k_bytes) == 6:
                        if self._authenticate_sector(trailer_block, "A", k_bytes) is True:
                            authed = True
                            break
                        if self._authenticate_sector(trailer_block, "B", k_bytes) is True:
                            authed = True
                            break
                except Exception:
                    pass

            if not authed:
                self.sig_log.emit(f"扇区 S{sector:02d} 认证失败，标记该扇区 4 块为未破解/加密状态 (??)")
                for b_i in range(4):
                    blk = first_block + b_i
                    dump.set_block_state(blk, BlockState.READ_FAILED)
                    read_failed_count += 1
                continue

            for b_i in range(4):
                if self._abort:
                    return
                block = first_block + b_i
                data = self._read_single_block(block)
                if data:
                    dump.set_block(block, data)
                    dump.set_block_state(block, BlockState.READ_OK)
                    self.sig_block_read.emit(block, data)
                    read_success_count += 1
                else:
                    dump.set_block_state(block, BlockState.READ_FAILED)
                    read_failed_count += 1

                pct = int(((block + 1) / total_blocks) * 100)
                self.sig_progress.emit(pct, f"正在读取 Block {block:02d} ...")

        self.sig_progress.emit(100, "全卡读取完成！")
        summary = f"读卡完毕: 成功读取 {read_success_count} 块，失败/加密 {read_failed_count} 块。"
        self.sig_finished.emit(True, summary, dump)

    def _do_write_card(self):
        if not self.dump_to_write:
            self.sig_finished.emit(False, "错误: 未提供待写入的 Dump 数据！", None)
            return

        self.sig_log.emit("开始向物理卡片写入数据 (写入保护状态检查)...")
        total_blocks = self.dump_to_write.block_count
        write_success = 0
        write_skipped = 0
        write_fail = 0

        for block in range(total_blocks):
            if self._abort:
                self.sig_finished.emit(False, "写卡已被用户中止", None)
                return

            if block == 0 and not self.allow_block0_write:
                self.sig_log.emit("安全保护: 已跳过 Block 0 (原厂厂商/UID块写入保护已开启)")
                write_skipped += 1
                continue

            sector = self.dump_to_write.get_block_sector(block)
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
                self.sig_log.emit(f"写块跳过: 扇区 S{sector:02d} 认证失败，无法写入 Block {block:02d}")
                write_fail += 1
                continue

            block_data = self.dump_to_write.get_block(block)
            ok = self._write_single_block(block, block_data)
            if ok:
                write_success += 1
            else:
                write_fail += 1

            pct = int(((block + 1) / total_blocks) * 100)
            self.sig_progress.emit(pct, f"正在写入 Block {block:02d} ...")

        self.sig_progress.emit(100, "写卡流程执行完毕！")
        summary = f"写卡完成: 成功写入 {write_success} 块，失败 {write_fail} 块，跳过 {write_skipped} 块。"
        self.sig_finished.emit(True, summary, None)

    def _do_probe_firmware(self):
        self.sig_log.emit("开始读卡器固件指令集兼容性深度探测...")
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
            if hasattr(self.worker, "adapter") and self.worker.adapter and self.worker.adapter.is_bidirectional:
                ok = self.worker.authenticate(block, key_type, key, timeout=0.25)
                return True if ok else False

            cmd = ReaderProtocol.CMD_AUTH_KEY_A if key_type == "A" else ReaderProtocol.CMD_AUTH_KEY_B
            data = bytes([block]) + key
            resp = self.worker.send_and_wait(cmd, data, timeout=0.25)
            if resp:
                if resp.get("ok") is True or resp.get("status") == "success":
                    return True
                code = resp.get("status_code", resp.get("status"))
                return code == ReaderProtocol.STATUS_SUCCESS
            return None

    def _read_single_block(self, block: int) -> Optional[bytes]:
        """向读卡器发送读块指令 (自适应 PCR532/PN532 与 AA BB 协议，线程安全)"""
        with self._hardware_lock:
            if hasattr(self.worker, "adapter") and self.worker.adapter and self.worker.adapter.is_bidirectional:
                return self.worker.read_block(block, timeout=0.25)

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
                    return self.worker.write_magic_block0(block_data, magic_type="CUID", timeout=0.35)
                return self.worker.write_block(block, block_data, timeout=0.3)

            payload = bytes([block]) + block_data[:16]
            resp = self.worker.send_and_wait(ReaderProtocol.CMD_WRITE_BLOCK, payload, timeout=0.3)
            if resp:
                if resp.get("ok") is True or resp.get("status") == "success":
                    return True
                code = resp.get("status_code", resp.get("status"))
                return code == ReaderProtocol.STATUS_SUCCESS
            return False
