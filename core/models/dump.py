# -*- coding: utf-8 -*-
"""
PyMifareTool - M1 卡数据内存模型与 Dump 导入导出
支持标准 Mifare Classic 1K (16扇区/64块) 与 4K (40扇区/256块)
兼容格式: .dump, .mfd, .bin, .txt, .mct, .eml, .json
"""

import os
import re
import json
from typing import List, Dict, Optional, Any, Tuple


class BlockState:
    UNREAD = 0        # 尚未读取 / 未载入数据 (默认显示 "-")
    READ_OK = 1       # 成功读取 / 已载入数据 / 用户就地编辑 (正常显示原样 Hex 如 "00")
    READ_FAILED = 2   # 加密扇区读不出 / 认证失败 (无歧义显示 "??")


class MifareDump:
    BLOCK_SIZE = 16
    S50_BLOCK_COUNT = 64
    S50_TOTAL_BYTES = 1024
    S70_BLOCK_COUNT = 256
    S70_TOTAL_BYTES = 4096

    def __init__(self, is_4k: bool = False):
        self.is_4k = is_4k
        self.block_count = self.S70_BLOCK_COUNT if is_4k else self.S50_BLOCK_COUNT
        self.total_bytes = self.block_count * self.BLOCK_SIZE
        self.data = bytearray(self.total_bytes)
        self.block_states: List[int] = [BlockState.UNREAD] * self.block_count
        self.load_error_message = ""
        self.reset_factory_default(keep_state_unread=True)

    @property
    def sector_count(self) -> int:
        return 40 if self.is_4k else 16

    def set_card_type(self, is_4k: bool):
        if self.is_4k == is_4k:
            return
        self.is_4k = is_4k
        self.block_count = self.S70_BLOCK_COUNT if is_4k else self.S50_BLOCK_COUNT
        self.total_bytes = self.block_count * self.BLOCK_SIZE
        if len(self.data) < self.total_bytes:
            self.data.extend(b"\x00" * (self.total_bytes - len(self.data)))
            self.block_states.extend([BlockState.UNREAD] * (self.block_count - len(self.block_states)))
        elif len(self.data) > self.total_bytes:
            self.data = self.data[:self.total_bytes]
            self.block_states = self.block_states[:self.block_count]

    def reset_factory_default(self, keep_state_unread: bool = False):
        self.data = bytearray(self.total_bytes)
        for s in range(self.sector_count):
            trailer_block = self.get_sector_trailer_block(s)
            offset = trailer_block * self.BLOCK_SIZE
            self.data[offset:offset + 6] = b"\xFF" * 6
            self.data[offset + 6:offset + 10] = bytes([0xFF, 0x07, 0x80, 0x69])
            self.data[offset + 10:offset + 16] = b"\xFF" * 6
        if keep_state_unread:
            self.block_states = [BlockState.UNREAD] * self.block_count
        else:
            self.block_states = [BlockState.READ_OK] * self.block_count

    def reset_to_unread(self):
        """将全卡数据重置为未载入/未读取状态 (UI 显示 '-')"""
        self.reset_factory_default(keep_state_unread=True)

    def get_block_state(self, block_index: int) -> int:
        if 0 <= block_index < len(self.block_states):
            return self.block_states[block_index]
        return BlockState.UNREAD

    def set_block_state(self, block_index: int, state: int):
        if 0 <= block_index < len(self.block_states):
            self.block_states[block_index] = state

    def set_byte(self, block_index: int, byte_index: int, byte_value: int):
        if 0 <= block_index < self.block_count and 0 <= byte_index < self.BLOCK_SIZE:
            self.data[block_index * self.BLOCK_SIZE + byte_index] = byte_value & 0xFF
            self.block_states[block_index] = BlockState.READ_OK

    def get_sector_block_count(self, sector: int) -> int:
        if not self.is_4k:
            return 4
        return 16 if sector >= 32 else 4

    def get_sector_first_block(self, sector: int) -> int:
        if not self.is_4k or sector < 32:
            return sector * 4
        return 128 + (sector - 32) * 16

    def get_sector_trailer_block(self, sector: int) -> int:
        return self.get_sector_first_block(sector) + self.get_sector_block_count(sector) - 1

    def get_block_sector(self, block_index: int) -> int:
        if block_index < 128:
            return block_index // 4
        return 32 + (block_index - 128) // 16

    def set_uid(self, uid_bytes: bytes, sak: int = 0x08, atqa: bytes = b"\x04\x00"):
        if len(uid_bytes) == 4:
            bcc = uid_bytes[0] ^ uid_bytes[1] ^ uid_bytes[2] ^ uid_bytes[3]
            self.data[0:4] = uid_bytes
            self.data[4] = bcc
            self.data[5] = sak
            self.data[6:8] = atqa
            self.block_states[0] = BlockState.READ_OK
        elif len(uid_bytes) == 8:
            self.data[0:8] = uid_bytes
            self.block_states[0] = BlockState.READ_OK
        elif len(uid_bytes) == 7:
            self.data[0:7] = uid_bytes
            self.block_states[0] = BlockState.READ_OK

    def get_block(self, block_index: int) -> bytes:
        if 0 <= block_index < self.block_count:
            start = block_index * self.BLOCK_SIZE
            return bytes(self.data[start:start + self.BLOCK_SIZE])
        return bytes(self.BLOCK_SIZE)

    def set_block(self, block_index: int, block_data: bytes):
        if 0 <= block_index < self.block_count and len(block_data) == self.BLOCK_SIZE:
            start = block_index * self.BLOCK_SIZE
            self.data[start:start + self.BLOCK_SIZE] = block_data
            self.block_states[block_index] = BlockState.READ_OK

    def get_sector_info(self, sector_index: int) -> Dict[str, Any]:
        if not (0 <= sector_index < self.sector_count):
            return {}

        trailer_block = self.get_sector_trailer_block(sector_index)
        first_block = self.get_sector_first_block(sector_index)
        b_count = self.get_sector_block_count(sector_index)
        trailer = self.get_block(trailer_block)

        return {
            "sector": sector_index,
            "first_block": first_block,
            "block_count": b_count,
            "trailer_block": trailer_block,
            "blocks": [self.get_block(first_block + i) for i in range(b_count)],
            "key_a": trailer[0:6],
            "access_bits": trailer[6:10],
            "key_b": trailer[10:16],
            "trailer_hex": " ".join(f"{b:02X}" for b in trailer),
        }

    def verify_dump(self) -> Dict[str, Any]:
        """全卡数据与权限完整性校验"""
        errors = []
        warnings = []
        ac_errors = {}

        # 1. 检查 Block 0 UID 与 BCC
        block0 = self.get_block(0)
        uid = block0[0:4]
        bcc_stored = block0[4]
        bcc_calc = uid[0] ^ uid[1] ^ uid[2] ^ uid[3]
        bcc_valid = (bcc_stored == bcc_calc)
        if not bcc_valid:
            errors.append(f"Block 0 UID 校验值(BCC)错误: 记录值为 0x{bcc_stored:02X}, 计算值为 0x{bcc_calc:02X}")

        # 2. 逐扇区检查 Access Bits (控制字)
        for s in range(self.sector_count):
            trailer_blk = self.get_sector_trailer_block(s)
            trailer = self.get_block(trailer_blk)
            ac_bytes = trailer[6:10]

            if len(ac_bytes) == 4:
                b6, b7, b8, _ = ac_bytes
                sector_ac_valid = True
                for i in range(4):
                    c1_inv = (b6 >> i) & 1
                    c1_raw = (b7 >> (4 + i)) & 1
                    c2_inv = (b6 >> (4 + i)) & 1
                    c2_raw = (b8 >> i) & 1
                    c3_inv = (b7 >> i) & 1
                    c3_raw = (b8 >> (4 + i)) & 1
                    if c1_inv == c1_raw or c2_inv == c2_raw or c3_inv == c3_raw:
                        sector_ac_valid = False
                        break

                if not sector_ac_valid:
                    err_msg = f"扇区 {s:02d} 控制位损坏 (取反校验失败): {ac_bytes.hex().upper()}"
                    errors.append(err_msg)
                    ac_errors[s] = err_msg

            key_a = trailer[0:6]
            key_b = trailer[10:16]
            if key_a == b"\x00" * 6:
                warnings.append(f"扇区 {s:02d} Key A 全为 00")
            if key_b == b"\x00" * 6:
                warnings.append(f"扇区 {s:02d} Key B 全为 00")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "bcc_valid": bcc_valid,
            "ac_errors": ac_errors,
            "is_4k": self.is_4k,
        }

    def repair_dump(self) -> Dict[str, Any]:
        """自动纠错全卡: 修复 BCC、重置损坏控制位为出厂默认"""
        fixed_items = []
        block0 = bytearray(self.get_block(0))
        uid = block0[0:4]
        bcc_calc = uid[0] ^ uid[1] ^ uid[2] ^ uid[3]
        if block0[4] != bcc_calc:
            block0[4] = bcc_calc
            self.set_block(0, bytes(block0))
            fixed_items.append(f"修正 Block 0 BCC 校验值为 0x{bcc_calc:02X}")

        for s in range(self.sector_count):
            trailer_blk = self.get_sector_trailer_block(s)
            trailer = bytearray(self.get_block(trailer_blk))
            ac_bytes = trailer[6:10]
            b6, b7, b8, b9 = ac_bytes
            sector_ac_valid = True
            for i in range(4):
                c1_inv = (b6 >> i) & 1
                c1_raw = (b7 >> (4 + i)) & 1
                c2_inv = (b6 >> (4 + i)) & 1
                c2_raw = (b8 >> i) & 1
                c3_inv = (b7 >> i) & 1
                c3_raw = (b8 >> (4 + i)) & 1
                if c1_inv == c1_raw or c2_inv == c2_raw or c3_inv == c3_raw:
                    sector_ac_valid = False
                    break

            if not sector_ac_valid:
                trailer[6:10] = bytes([0xFF, 0x07, 0x80, 0x69])
                self.set_block(trailer_blk, bytes(trailer))
                fixed_items.append(f"扇区 {s:02d} 控制位重置为出厂默认 FF 07 80 69")

        return {"fixed": len(fixed_items) > 0, "fixed_items": fixed_items}

    def export_key_dictionary(self, filepath: str) -> int:
        """提取全卡所有扇区的 Key A 和 Key B 并去重导出为 .dic 文件"""
        keys = set()
        for s in range(self.sector_count):
            trailer_blk = self.get_sector_trailer_block(s)
            trailer = self.get_block(trailer_blk)
            ka = trailer[0:6].hex().upper()
            kb = trailer[10:16].hex().upper()
            if ka and ka != "000000000000":
                keys.add(ka)
            if kb and kb != "000000000000":
                keys.add(kb)

        sorted_keys = sorted(list(keys))
        with open(filepath, "w", encoding="utf-8") as f:
            for k in sorted_keys:
                f.write(k + "\n")
        return len(sorted_keys)

    def load_mct(self, filepath: str) -> bool:
        if not os.path.exists(filepath):
            self.load_error_message = "文件不存在"
            return False

        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        current_sector = -1
        parsed_blocks: Dict[int, bytes] = {}
        failed_blocks = set()
        sector_block_offset = 0

        for line in lines:
            line_str = line.strip()
            if not line_str or line_str.startswith("#"):
                continue

            m_sec = re.match(r"^[+]?(?:Sector|扇区)\s*:\s*(\d+)", line_str, re.IGNORECASE)
            if m_sec:
                current_sector = int(m_sec.group(1))
                sector_block_offset = 0
                continue

            is_encrypted_hint = (
                "未发现密钥" in line_str or
                "死扇区" in line_str or
                "no keys" in line_str.lower() or
                "dead sector" in line_str.lower() or
                line_str.startswith("----") or
                line_str.startswith("????")
            )
            if is_encrypted_hint and current_sector >= 0:
                first_blk = self.get_sector_first_block(current_sector)
                blk_cnt = self.get_sector_block_count(current_sector)
                for b_i in range(blk_cnt):
                    failed_blocks.add(first_blk + b_i)
                continue

            hex_cand = "".join(c for c in line_str if c in "0123456789abcdefABCDEF")
            if len(hex_cand) == 32:
                if current_sector >= 0:
                    first_blk = self.get_sector_first_block(current_sector)
                    block_idx = first_blk + sector_block_offset
                    parsed_blocks[block_idx] = bytes.fromhex(hex_cand)
                    sector_block_offset += 1
                else:
                    idx = len(parsed_blocks)
                    parsed_blocks[idx] = bytes.fromhex(hex_cand)

        total_sectors_touched = len(set(self.get_block_sector(b) for b in list(parsed_blocks.keys()) + list(failed_blocks)))
        if total_sectors_touched > 16 or any(k >= 64 for k in list(parsed_blocks.keys()) + list(failed_blocks)):
            self.set_card_type(True)
        else:
            self.set_card_type(False)

        if len(parsed_blocks) > 0 or len(failed_blocks) > 0:
            self.reset_to_unread()
            for b_idx, b_data in parsed_blocks.items():
                if 0 <= b_idx < self.block_count:
                    self.set_block(b_idx, b_data)
                    self.set_block_state(b_idx, BlockState.READ_OK)
            for b_idx in failed_blocks:
                if 0 <= b_idx < self.block_count:
                    self.set_block_state(b_idx, BlockState.READ_FAILED)
            return True

        self.load_error_message = "MCT 解析失败 (未找到有效的扇区数据或 Hex 块)"
        return False

    def save_mct(self, filepath: str) -> bool:
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                for s in range(self.sector_count):
                    f.write(f"+Sector: {s}\n")
                    first_b = self.get_sector_first_block(s)
                    b_count = self.get_sector_block_count(s)
                    for b in range(b_count):
                        block_idx = first_b + b
                        f.write(self.get_block(block_idx).hex().upper() + "\n")
            return True
        except Exception as e:
            self.load_error_message = str(e)
            return False

    def save_eml(self, filepath: str) -> bool:
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                for b in range(self.block_count):
                    f.write(self.get_block(b).hex().upper() + "\n")
            return True
        except Exception as e:
            self.load_error_message = str(e)
            return False

    def load_eml(self, filepath: str) -> bool:
        if not os.path.exists(filepath):
            self.load_error_message = "文件不存在"
            return False
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
            hex_lines = [l for l in lines if len(l) == 32 and all(c in "0123456789abcdefABCDEF" for c in l)]
            if len(hex_lines) >= 64:
                self.set_card_type(len(hex_lines) >= 256)
                self.reset_to_unread()
                for b_idx, h_str in enumerate(hex_lines[:self.block_count]):
                    self.set_block(b_idx, bytes.fromhex(h_str))
                    self.set_block_state(b_idx, BlockState.READ_OK)
                return True
            self.load_error_message = f"EML 块数不足 (仅解析出 {len(hex_lines)} 块，标准需至少 64 块)"
            return False
        except Exception as e:
            self.load_error_message = str(e)
            return False

    def save_json(self, filepath: str) -> bool:
        try:
            b0 = self.get_block(0)
            uid_hex = b0[:4].hex().upper()
            blocks_dict = {}
            for b in range(self.block_count):
                blocks_dict[str(b)] = self.get_block(b).hex().upper()
            payload = {
                "Created": "PyMifareTool",
                "FileType": "mifare",
                "Card": {
                    "UID": uid_hex,
                    "SAK": f"{b0[5]:02X}" if len(b0) > 5 else "08",
                    "ATQA": f"{b0[6]:02X}{b0[7]:02X}" if len(b0) > 7 else "0004"
                },
                "blocks": blocks_dict
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            return True
        except Exception as e:
            self.load_error_message = str(e)
            return False

    def load_json(self, filepath: str) -> bool:
        if not os.path.exists(filepath):
            self.load_error_message = "文件不存在"
            return False
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            blocks_obj = data.get("blocks", {})
            if len(blocks_obj) >= 64:
                self.set_card_type(len(blocks_obj) >= 256)
                self.reset_to_unread()
                for b_str, h_str in blocks_obj.items():
                    try:
                        b_idx = int(b_str)
                        if 0 <= b_idx < self.block_count and len(h_str) == 32:
                            self.set_block(b_idx, bytes.fromhex(h_str))
                            self.set_block_state(b_idx, BlockState.READ_OK)
                    except Exception:
                        pass
                return True
            self.load_error_message = "JSON 缺少有效 blocks 字段或块数不足 64"
            return False
        except Exception as e:
            self.load_error_message = str(e)
            return False

    def load_from_file(self, filepath: str) -> bool:
        if not os.path.exists(filepath):
            self.load_error_message = "文件不存在"
            return False

        ext = os.path.splitext(filepath)[1].lower()

        if ext in [".dump", ".mfd", ".bin"]:
            with open(filepath, "rb") as f:
                content = f.read()

            if len(content) >= self.S70_TOTAL_BYTES:
                self.set_card_type(True)
                self.data = bytearray(content[:self.S70_TOTAL_BYTES])
                self.block_states = [BlockState.READ_OK] * self.block_count
                return True
            elif len(content) >= self.S50_TOTAL_BYTES:
                self.set_card_type(False)
                self.data = bytearray(content[:self.S50_TOTAL_BYTES])
                self.block_states = [BlockState.READ_OK] * self.block_count
                return True
            elif len(content) > 0:
                self.load_error_message = f"二进制数据尺寸异常 ({len(content)} 字节, 预期 1024 或 4096 字节)"
                return False

        elif ext == ".mct":
            return self.load_mct(filepath)

        elif ext == ".eml":
            return self.load_eml(filepath)

        elif ext == ".json":
            return self.load_json(filepath)

        elif ext == ".txt":
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            if any(re.match(r"^[+]?(?:Sector|扇区)\s*:\s*\d+", l.strip(), re.IGNORECASE) for l in lines):
                return self.load_mct(filepath)

            parsed_blocks: Dict[int, bytes] = {}
            for line in lines:
                line_str = line.strip()
                if not line_str or line_str.startswith("+") or line_str.startswith("#"):
                    continue

                if "block" in line_str.lower() and ":" in line_str:
                    try:
                        prefix, rest = line_str.split(":", 1)
                        b_digits = "".join(c for c in prefix if c.isdigit())
                        if b_digits:
                            b_idx = int(b_digits)
                            hex_part = rest.split("|")[0].strip()
                            hex_tokens = [tok for tok in hex_part.split() if len(tok) == 2 and all(c in "0123456789abcdefABCDEF" for c in tok)]
                            if len(hex_tokens) == 16:
                                parsed_blocks[b_idx] = bytes.fromhex("".join(hex_tokens))
                    except Exception:
                        pass
                else:
                    hex_part = line_str.split("|")[0].strip()
                    hex_tokens = [tok for tok in hex_part.split() if len(tok) == 2 and all(c in "0123456789abcdefABCDEF" for c in tok)]
                    if len(hex_tokens) == 16:
                        idx = len(parsed_blocks)
                        parsed_blocks[idx] = bytes.fromhex("".join(hex_tokens))
                    elif len(hex_part) == 32 and all(c in "0123456789abcdefABCDEF" for c in hex_part):
                        idx = len(parsed_blocks)
                        parsed_blocks[idx] = bytes.fromhex(hex_part)

            if len(parsed_blocks) >= 64:
                if len(parsed_blocks) >= 256 or any(k >= 64 for k in parsed_blocks.keys()):
                    self.set_card_type(True)
                else:
                    self.set_card_type(False)

                for b_idx, b_data in parsed_blocks.items():
                    if 0 <= b_idx < self.block_count:
                        self.set_block(b_idx, b_data)
                return True

            self.load_error_message = f"未能解析出合法的 64 块 M1 数据 (仅匹配出 {len(parsed_blocks)} 块)"
            return False

        self.load_error_message = f"不支持的文件后缀: {ext}"
        return False

    def save_to_file(self, filepath: str) -> bool:
        ext = os.path.splitext(filepath)[1].lower()
        try:
            if ext in [".dump", ".mfd", ".bin"]:
                with open(filepath, "wb") as f:
                    f.write(self.data)
                return True
            elif ext == ".mct":
                return self.save_mct(filepath)
            elif ext == ".eml":
                return self.save_eml(filepath)
            elif ext == ".json":
                return self.save_json(filepath)
            else:
                with open(filepath, "w", encoding="utf-8") as f:
                    for s in range(self.sector_count):
                        f.write(f"+---------------- Sector {s:02d} ----------------+\n")
                        first_b = self.get_sector_first_block(s)
                        b_count = self.get_sector_block_count(s)
                        for b in range(b_count):
                            block_idx = first_b + b
                            b_data = self.get_block(block_idx)
                            hex_line = " ".join(f"{x:02X}" for x in b_data)
                            asc_line = "".join(chr(x) if 32 <= x <= 126 else "." for x in b_data)
                            f.write(f"Block {block_idx:02d}: {hex_line}  |{asc_line}|\n")
                        f.write("\n")
                return True
        except Exception as e:
            self.load_error_message = str(e)
            return False
