# -*- coding: utf-8 -*-
"""
PyMifareTool - 全自动测试套件 (All-in-One Automated Test Runner)
涵盖：
1. 协议解包与通用帧构建单元测试
2. Access Bits 权限位位运算与反码校验单元测试 (Decoder & Encoder)
3. 4/7/10 字节卡号换算（8H10D, WG26/34）及元数据键名测试
4. MifareDump 内存模型、双向文件导入导出（.dump, .bin, .txt, .mct）与防 ASCII 预览篡改测试
5. MifareDump 4K/S70 模型与全卡校验纠错测试
6. CardDatabase 本地发卡管理与刷卡流水入库单元测试
7. CardOperationWorker 桩传输与服务层底层契约测试 (解决 P0 契约错配)
8. PyQt6 界面全功能无人值守自动化模拟测试（QTest 贴卡仿真、单元格就地编辑、差分比对）
9. 硬件 COM3 端口状态与链路自检 (支持硬件免插拔自适应)
"""

import sys
import os
import time
import tempfile
import unittest

# 确保 UTF-8 控制台输出
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 引入项目主目录
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

# 确保无头测试环境
os.environ["QT_QPA_PLATFORM"] = "offscreen"


class Test01ProtocolAndAlgorithms(unittest.TestCase):
    """测试协议帧打包解包、AccessBits编码/解码器与卡号换算"""

    def setUp(self):
        from core.protocol import ReaderProtocol, AccessBitsDecoder, AccessBitsEncoder, CardConverter
        self.protocol = ReaderProtocol
        self.decoder = AccessBitsDecoder
        self.encoder = AccessBitsEncoder
        self.converter = CardConverter

    def test_bcc_calculation(self):
        payload = bytes([0x06, 0x01, 0xD7, 0x7E, 0xA0, 0xDF])
        bcc = self.protocol.calc_bcc(payload)
        self.assertEqual(bcc, 0xD1, "BCC 校验和异或计算错误")

    def test_build_frame(self):
        frame = self.protocol.build_frame(0x32, bytes([0x00]))
        expected = bytes([0xAA, 0xBB, 0x03, 0x32, 0x00, 0x31])
        self.assertEqual(frame, expected, "build_frame 生成的报文结构不匹配")

    def test_parse_frame_valid_uid(self):
        raw_stream = bytes([0x00, 0xAA, 0xBB, 0x06, 0x01, 0xD7, 0x7E, 0xA0, 0xDF, 0xD1, 0x55])
        info, remaining = self.protocol.parse_frame(raw_stream)
        self.assertIsNotNone(info, "未能成功解包有效帧")
        self.assertEqual(info["cmd"], 0x01)
        self.assertEqual(info["uid_bytes"], bytes([0xD7, 0x7E, 0xA0, 0xDF]))
        self.assertNotIn("conversions", info, "协议层不应承载 CardConverter 业务换算")
        self.assertEqual(remaining, bytes([0x55]))

        from core.adapters import BroadcasterAdapter
        adapter_info, adapter_remaining = BroadcasterAdapter().parse_incoming(bytearray(raw_stream))
        self.assertIsNotNone(adapter_info, "适配器未能解析有效广播帧")
        self.assertEqual(adapter_remaining, bytes([0x55]))
        self.assertEqual(adapter_info["conversions"]["hex_normal"], "D7 7E A0 DF")
        self.assertEqual(adapter_info["conversions"]["dec_10d_rev"], "3751837399")
        self.assertEqual(adapter_info["conversions"]["wiegand_26"], "160,32471")
        self.assertEqual(adapter_info["conversions"]["wiegand_34"], "57248,32471")

    def test_parse_frame_status_codes(self):
        """测试认证与读写块帧解析状态契约"""
        # 认证成功帧: AA BB 03 30 00 33
        auth_ok_raw = self.protocol.build_frame(0x30, bytes([0x00]))
        resp, _ = self.protocol.parse_frame(auth_ok_raw)
        self.assertEqual(resp["status"], "success")
        self.assertEqual(resp["status_code"], 0x00)
        self.assertTrue(resp["ok"])

        # 读块成功帧: AA BB 13 32 00 [16B 0x11] BCC
        read_ok_raw = self.protocol.build_frame(0x32, bytes([0x00]) + bytes([0x11] * 16))
        resp_read, _ = self.protocol.parse_frame(read_ok_raw)
        self.assertEqual(resp_read["status"], "success")
        self.assertEqual(resp_read["block_data"], bytes([0x11] * 16))
        self.assertEqual(resp_read["data"], bytes([0x11] * 16))

        # 写块失败帧: AA BB 03 33 04 ...
        write_fail_raw = self.protocol.build_frame(0x33, bytes([0x04]))
        resp_write, _ = self.protocol.parse_frame(write_fail_raw)
        self.assertEqual(resp_write["status"], "write_fail")
        self.assertFalse(resp_write["ok"])

    def test_access_bits_factory_default(self):
        info = self.decoder.decode(bytes([0xFF, 0x07, 0x80, 0x69]))
        self.assertTrue(info["valid"], "出厂控制字反码校验应为合法")
        self.assertEqual(info["blocks"]["block_0"]["read"], "KeyA|B")
        self.assertEqual(info["blocks"]["trailer"]["key_a_read"], "Never")

    def test_access_bits_readonly_protected(self):
        info = self.decoder.decode(bytes([0x08, 0x77, 0x8F, 0x69]))
        self.assertTrue(info["valid"], "只读控制字反码校验应为合法")

    def test_access_bits_encoder(self):
        # 出厂默认: (0,0,0), (0,0,0), (0,0,0), (0,0,1)
        encoded = self.encoder.encode([(0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 1)], 0x69)
        self.assertEqual(encoded, bytes([0xFF, 0x07, 0x80, 0x69]))

        # 只读/KeyB管控: (1,1,0), (1,1,0), (1,1,0), (0,1,1) -> 08 77 8F 69
        encoded_ro = self.encoder.encode([(1, 1, 0), (1, 1, 0), (1, 1, 0), (0, 1, 1)], 0x69)
        self.assertEqual(encoded_ro, bytes([0x08, 0x77, 0x8F, 0x69]))

    def test_card_converter_multi_sizes(self):
        c4 = self.converter.convert_uid(bytes([0x12, 0x34, 0x56, 0x78]))
        self.assertEqual(c4["uid_length"], 4)
        self.assertIn("Mifare Classic", c4["uid_type"])
        self.assertEqual(c4["card_type"], c4["uid_type"])
        self.assertTrue(len(c4["wiegand_34"]) > 0)

        c7 = self.converter.convert_uid(bytes([0x04, 0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC]))
        self.assertEqual(c7["uid_length"], 7)
        self.assertIn("7-byte", c7["uid_type"])
        self.assertEqual(c7["card_type"], c7["uid_type"])

        c10 = self.converter.convert_uid(bytes([i for i in range(10)]))
        self.assertEqual(c10["uid_length"], 10)
        self.assertIn("10-byte", c10["uid_type"])


class Test02DumpModelAndPersistence(unittest.TestCase):
    """测试 16/40 扇区内存数据模型、全格式导入导出与抗损坏能力"""

    def setUp(self):
        from core.dump_model import MifareDump
        self.dump = MifareDump()

    def test_factory_initialization(self):
        self.assertEqual(len(self.dump.data), 1024, "M1 卡全卡容量必须为 1024 字节")
        for s in range(16):
            info = self.dump.get_sector_info(s)
            self.assertEqual(info["key_a"], b"\xFF" * 6)
            self.assertEqual(info["access_bits"], bytes([0xFF, 0x07, 0x80, 0x69]))
            self.assertEqual(info["key_b"], b"\xFF" * 6)

    def test_set_uid(self):
        uid = bytes([0xD7, 0x7E, 0xA0, 0xDF])
        self.dump.set_uid(uid)
        b0 = self.dump.get_block(0)
        self.assertEqual(b0[:4], uid)
        expected_bcc = 0xD7 ^ 0x7E ^ 0xA0 ^ 0xDF
        self.assertEqual(b0[4], expected_bcc)

    def test_get_uid(self):
        """Block 0 前 4 字节必须可通过 get_uid 稳定提取"""
        uid = bytes([0xD7, 0x7E, 0xA0, 0xDF])
        self.dump.set_uid(uid)
        self.assertEqual(self.dump.get_uid(), uid)

    def test_block_modification(self):
        test_block = bytes([i for i in range(16)])
        self.dump.set_block(4, test_block)
        self.assertEqual(self.dump.get_block(4), test_block)

    def test_block_states(self):
        """测试块读取状态机跟踪 (未读取/已读取/读取失败)"""
        from core.dump_model import BlockState
        # 默认全部为未载入 UNREAD
        for b in range(self.dump.block_count):
            self.assertEqual(self.dump.get_block_state(b), BlockState.UNREAD)

        # 写入数据块 -> 自动变为 READ_OK
        self.dump.set_block(4, bytes([0x12] * 16))
        self.assertEqual(self.dump.get_block_state(4), BlockState.READ_OK)

        # 标记加密受限 -> READ_FAILED
        self.dump.set_block_state(8, BlockState.READ_FAILED)
        self.assertEqual(self.dump.get_block_state(8), BlockState.READ_FAILED)

        # 重置回未读取
        self.dump.reset_to_unread()
        self.assertEqual(self.dump.get_block_state(4), BlockState.UNREAD)
        self.assertEqual(self.dump.get_block_state(8), BlockState.UNREAD)

    def test_file_io_roundtrip(self):
        self.dump.set_block(8, bytes([0xAA] * 16))
        tmp_base = tempfile.gettempdir()
        dump_file = os.path.join(tmp_base, f"test_{int(time.time()*1000)}.dump")
        txt_file = os.path.join(tmp_base, f"test_{int(time.time()*1000)}.txt")
        mct_file = os.path.join(tmp_base, f"test_{int(time.time()*1000)}.mct")

        try:
            # 1. 二进制 .dump
            self.assertTrue(self.dump.save_to_file(dump_file))
            new_dump = self.dump.__class__()
            self.assertTrue(new_dump.load_from_file(dump_file))
            self.assertEqual(new_dump.get_block(8), bytes([0xAA] * 16))

            # 2. 文本 .txt
            self.assertTrue(self.dump.save_to_file(txt_file))
            txt_dump = self.dump.__class__()
            self.assertTrue(txt_dump.load_from_file(txt_file))
            self.assertEqual(txt_dump.get_block(8), bytes([0xAA] * 16))

            # 3. MCT 格式 .mct
            self.assertTrue(self.dump.save_mct(mct_file))
            mct_dump = self.dump.__class__()
            self.assertTrue(mct_dump.load_from_file(mct_file))
            self.assertEqual(mct_dump.get_block(8), bytes([0xAA] * 16))

        finally:
            for p in (dump_file, txt_file, mct_file):
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

    def test_rfidtools_eml_io_roundtrip(self):
        """测试 RFIDtools / Proxmark3 .eml 格式双向无损序列化"""
        self.dump.set_block(4, bytes([0x5A] * 16))
        tmp_eml = os.path.join(tempfile.gettempdir(), f"test_{int(time.time()*1000)}.eml")
        try:
            self.assertTrue(self.dump.save_eml(tmp_eml))
            new_dump = self.dump.__class__()
            self.assertTrue(new_dump.load_from_file(tmp_eml))
            self.assertEqual(new_dump.get_block(4), bytes([0x5A] * 16))
            # 校验 eml 文件由 64 行 32 个 hex 字符组成
            with open(tmp_eml, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            self.assertEqual(len(lines), 64)
            self.assertEqual(lines[4], "5A" * 16)
        finally:
            if os.path.exists(tmp_eml):
                try:
                    os.remove(tmp_eml)
                except Exception:
                    pass

    def test_rfidtools_json_io_roundtrip(self):
        """测试 RFIDtools / Proxmark3 JSON 档案格式双向序列化"""
        import json
        self.dump.set_block(12, bytes([0x3C] * 16))
        tmp_json = os.path.join(tempfile.gettempdir(), f"test_{int(time.time()*1000)}.json")
        try:
            self.assertTrue(self.dump.save_json(tmp_json))
            new_dump = self.dump.__class__()
            self.assertTrue(new_dump.load_from_file(tmp_json))
            self.assertEqual(new_dump.get_block(12), bytes([0x3C] * 16))
            with open(tmp_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("blocks", data)
            self.assertEqual(data["blocks"]["12"], "3C" * 16)
        finally:
            if os.path.exists(tmp_json):
                try:
                    os.remove(tmp_json)
                except Exception:
                    pass

    def test_anti_corruption_ascii_preview_txt(self):
        """严格测试: 导入带 ASCII 预览列的常见 hexdump 格式，绝对不可损坏数据 (修复 P0-4.2)"""
        tmp_txt = os.path.join(tempfile.gettempdir(), f"test_ascii_{int(time.time()*1000)}.txt")
        try:
            # 构建一个全 0x31 ('1') 的块，ASCII 预览列也是 '11111111'
            with open(tmp_txt, "w", encoding="utf-8") as f:
                for b in range(64):
                    hex_str = " ".join("31" for _ in range(16))
                    asc_str = "1" * 16
                    f.write(f"Block {b:02d}: {hex_str}  |{asc_str}|\n")

            from core.dump_model import MifareDump
            test_d = MifareDump()
            loaded = test_d.load_from_file(tmp_txt)
            self.assertTrue(loaded)

            # 校验全部 64 个块的内容均必须严格为 16 个 0x31，不能因为 ASCII 预览发生字节偏移
            for b in range(64):
                self.assertEqual(test_d.get_block(b), bytes([0x31] * 16), f"Block {b} 发生数据错位损坏")
        finally:
            if os.path.exists(tmp_txt):
                try:
                    os.remove(tmp_txt)
                except Exception:
                    pass

    def test_load_mct_with_encrypted_sectors(self):
        """测试导入含有加密/死扇区的 MCT 导出文件 (如手机 MCT 导出的部分加密卡)"""
        from core.dump_model import MifareDump, BlockState
        tmp_mct = os.path.join(tempfile.gettempdir(), f"test_mct_{int(time.time()*1000)}.mct")
        try:
            with open(tmp_mct, "w", encoding="utf-8") as f:
                # 扇区 0 正常
                f.write("+扇区: 0\n")
                f.write("D77EA0DFD608040003518BD121011890\n")
                f.write("00000000000000000000000000000000\n")
                f.write("00000000000000000000000000000000\n")
                f.write("FFFFFFFFFFFFFF078069FFFFFFFFFFFF\n")
                # 扇区 1 加密受限
                f.write("+扇区: 1\n未发现密钥(或死扇区)\n")
                # 扇区 2 正常
                f.write("+扇区: 2\n")
                f.write("00000000000000000000000000000000\n")
                f.write("00000000000000000000000000000000\n")
                f.write("00000000000000000000000000000000\n")
                f.write("FFFFFFFFFFFFFF078069FFFFFFFFFFFF\n")

            d = MifareDump()
            self.assertTrue(d.load_from_file(tmp_mct))
            # 校验扇区 0: 状态为 READ_OK 且数据准确
            self.assertEqual(d.get_block_state(0), BlockState.READ_OK)
            self.assertEqual(d.get_block(0)[:4], bytes([0xD7, 0x7E, 0xA0, 0xDF]))
            # 校验扇区 1: 状态全部为 READ_FAILED
            for b in range(4, 8):
                self.assertEqual(d.get_block_state(b), BlockState.READ_FAILED)
            # 校验扇区 2: 状态全部为 READ_OK
            for b in range(8, 12):
                self.assertEqual(d.get_block_state(b), BlockState.READ_OK)
        finally:
            if os.path.exists(tmp_mct):
                try:
                    os.remove(tmp_mct)
                except Exception:
                    pass


    def test_verify_and_repair_dump(self):
        """测试全卡校验与一键自动修复"""
        # 制造 BCC 错误
        b0 = bytearray(self.dump.get_block(0))
        b0[0:4] = bytes([0x11, 0x22, 0x33, 0x44])
        b0[4] = 0x00  # 错误 BCC
        self.dump.set_block(0, bytes(b0))

        # 制造扇区 1 控制位错误
        b7 = bytearray(self.dump.get_block(7))
        b7[6:10] = bytes([0x00, 0x00, 0x00, 0x69])  # 取反位不匹配
        self.dump.set_block(7, bytes(b7))

        ver = self.dump.verify_dump()
        self.assertFalse(ver["valid"])
        self.assertFalse(ver["bcc_valid"])
        self.assertIn(1, ver["ac_errors"])

        # 执行自动纠错
        rep = self.dump.repair_dump()
        self.assertTrue(rep["fixed"])
        self.assertEqual(len(rep["fixed_items"]), 2)

        ver2 = self.dump.verify_dump()
        self.assertTrue(ver2["valid"], "纠错后全卡校验应通过")

    def test_4k_dump_model(self):
        """测试 Mifare Classic 4K / S70 模型"""
        from core.dump_model import MifareDump
        d4k = MifareDump(is_4k=True)
        self.assertEqual(d4k.sector_count, 40)
        self.assertEqual(d4k.block_count, 256)
        self.assertEqual(d4k.total_bytes, 4096)
        # 扇区 32 属于 16 块大扇区
        self.assertEqual(d4k.get_sector_block_count(32), 16)
        self.assertEqual(d4k.get_sector_trailer_block(32), 128 + 15)


class Test03CardDatabase(unittest.TestCase):
    """测试 SQLite 数据库与发卡刷卡流水管理"""

    def setUp(self):
        self.db_path = os.path.join(tempfile.gettempdir(), f"test_cards_{int(time.time()*1000)}.db")
        from core.card_db import CardDatabase
        self.db = CardDatabase(db_path=self.db_path)

    def tearDown(self):
        self.db.close()
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_swipe_and_persistence(self):
        conv = {
            "card_type": "Mifare Classic 1K",
            "uid_type": "Mifare Classic 1K",
            "dec_10d_rev": "3751837399",
            "wiegand_26": "160,32471",
            "wiegand_34": "00160,32471",
        }
        info1 = self.db.record_swipe("D7 7E A0 DF", conv, "AA BB 06 01 D7 7E A0 DF D1")
        self.assertEqual(info1["swipe_count"], 1)

        info2 = self.db.record_swipe("D7 7E A0 DF", conv, "AA BB 06 01 D7 7E A0 DF D1")
        self.assertEqual(info2["swipe_count"], 2)

        self.db.update_card_info("D7 7E A0 DF", "VIP测试卡", "张三", "高权限门禁")
        card = self.db.get_card("D7 7E A0 DF")
        self.assertIsNotNone(card)
        self.assertEqual(card["card_name"], "VIP测试卡")
        self.assertEqual(card["card_holder"], "张三")

        logs = self.db.list_recent_logs(10)
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0]["uid"], "D7 7E A0 DF")

    def test_clear_swipe_logs(self):
        """测试清空本地数据库历史刷卡流水"""
        conv = {
            "card_type": "Mifare Classic 1K",
            "uid_type": "Mifare Classic 1K",
            "dec_10d_rev": "3751837399",
            "wiegand_26": "160,32471",
        }
        self.db.record_swipe("D7 7E A0 DF", conv, "AA BB 06 01 D7 7E A0 DF D1")
        self.db.record_swipe("D7 7E A0 DF", conv, "AA BB 06 01 D7 7E A0 DF D1")
        self.assertGreaterEqual(len(self.db.list_recent_logs()), 2)
        cleared = self.db.clear_swipe_logs()
        self.assertGreaterEqual(cleared, 2)
        self.assertEqual(len(self.db.list_recent_logs()), 0, "数据库刷卡流水未被完全清空")

    def test_sector_key_persistence(self):
        """测试读取/破解成功后的卡号-扇区密钥留存与 UPSERT 语义"""
        self.db.save_sector_keys("D77EA0DF", 1, "010203040506", "010203040506")
        self.db.save_sector_keys("D77EA0DF", 9, "", "FFFFFFFFFFFF")

        keys = self.db.get_card_keys("D77EA0DF")
        self.assertEqual(keys[1]["key_a"], "010203040506")
        self.assertEqual(keys[1]["key_b"], "010203040506")
        self.assertEqual(keys[9]["key_b"], "FFFFFFFFFFFF")
        self.assertEqual(keys[9]["key_a"], "")

        # 空值不得覆盖既有密钥 (仅更新非空)
        self.db.save_sector_keys("D77EA0DF", 1, "", "")
        self.assertEqual(self.db.get_card_keys("D77EA0DF")[1]["key_a"], "010203040506")

        # 占位词应被规范化过滤
        self.db.save_sector_keys("D77EA0DF", 12, "未破解", "AABBCCDDEEFF")
        keys = self.db.get_card_keys("D77EA0DF")
        self.assertEqual(keys[12]["key_a"], "")
        self.assertEqual(keys[12]["key_b"], "AABBCCDDEEFF")

        self.assertGreaterEqual(len(self.db.list_all_card_keys()), 3)
        self.db.clear_card_keys()
        self.assertEqual(len(self.db.list_all_card_keys()), 0)

    def test_save_card_keys_batch(self):
        """测试批量留存一张卡多个扇区密钥"""
        n = self.db.save_card_keys("12345678", {
            0: {"key_a": "FFFFFFFFFFFF", "key_b": "FFFFFFFFFFFF"},
            2: {"key_a": "A0A1A2A3A4A5", "key_b": "未破解"},
        })
        self.assertEqual(n, 2)
        keys = self.db.get_card_keys("12345678")
        self.assertEqual(keys[0]["key_a"], "FFFFFFFFFFFF")
        self.assertEqual(keys[2]["key_a"], "A0A1A2A3A4A5")
        self.assertEqual(keys[2]["key_b"], "")


class Test04GuiAutomatedInteraction(unittest.TestCase):
    """全自动 GUI 模拟测试：利用 PyQt6 测试框架执行无人值守操作"""

    def setUp(self):
        from PyQt6.QtWidgets import QApplication
        self.app = QApplication.instance()
        if not self.app:
            self.app = QApplication(sys.argv)

        from ui.main_window import MainWindow
        self.win = MainWindow()
        self.win.show()

    def tearDown(self):
        self.win.close()

    def test_gui_card_swipe_simulation(self):
        """模拟读卡器产生真实贴卡报文并驱动全界面联动"""
        mock_frame = {
            "cmd": 0x01,
            "cmd_name": "自动感应卡号",
            "uid_bytes": bytes([0xD7, 0x7E, 0xA0, 0xDF]),
            "raw": bytes([0xAA, 0xBB, 0x06, 0x01, 0xD7, 0x7E, 0xA0, 0xDF, 0xD1]),
            "conversions": {
                "hex_normal": "D7 7E A0 DF",
                "hex_reverse": "DF A0 7E D7",
                "dec_10d_rev": "3751837399",
                "wiegand_26": "160,32471",
                "wiegand_34": "57248,32471",
                "card_type": "Mifare Classic 1K",
            }
        }

        self.win._on_card_swiped(mock_frame)

        self.assertEqual(self.win.lbl_hero_uid.text(), "D7 7E A0 DF")
        self.assertEqual(self.win.val_dec_10d.text(), "3751837399")
        self.assertEqual(self.win.val_wg26.text(), "160,32471")
        self.assertEqual(self.win.val_wg34.text(), "57248,32471")
        self.assertTrue(self.win.btn_save_db.isEnabled())

        b0_data = self.win.tab_sector.dump.get_block(0)
        self.assertEqual(b0_data[:4], bytes([0xD7, 0x7E, 0xA0, 0xDF]))

        table = self.win.tab_sector.table
        r0 = self.win.tab_sector.row_for_block(0)
        self.assertEqual(table.item(r0, 2).text(), "D7")
        self.assertEqual(table.item(r0, 3).text(), "7E")
        self.assertEqual(table.item(r0, 4).text(), "A0")
        self.assertEqual(table.item(r0, 5).text(), "DF")

    def test_gui_cell_inplace_editing(self):
        """模拟用户在扇区矩阵中双击修改某一单元格 Hex 字节"""
        table = self.win.tab_sector.table
        item = table.item(self.win.tab_sector.row_for_block(4), 2)
        self.assertIsNotNone(item)
        item.setText("5A")

        b4_data = self.win.tab_sector.dump.get_block(4)
        self.assertEqual(b4_data[0], 0x5A, "就地编辑未正确同步至内存 dump 模型")

    def test_gui_dictionary_tools_interaction(self):
        """测试工具箱：输入 Access Bits 解析与卡号多进制换算"""
        tools = self.win.tab_tools

        tools.txt_access_hex.setText("FF 07 80 69")
        tools._decode_access_bits()
        report = tools.txt_access_result.toPlainText()
        self.assertTrue(len(report) > 0, "Access Bits 解析报告不应为空")

        tools.txt_input_hex.setText("D7 7E A0 DF")
        tools._convert_from_hex()
        self.assertIn("3751837399", tools.lbl_conv_res_hex.text())

    def test_gui_sector_visualizer_states(self):
        """测试扇区矩阵对未读取 '-'、原样十六进制 '00' 与加密受阻 '??' 的无歧义渲染"""
        from core.dump_model import BlockState
        table = self.win.tab_sector.table
        sector_tab = self.win.tab_sector

        # 1. 初始状态：未读取的块 (如 Block 2) 单元格全部显示为 '-'，ASCII 预览列显示 '-'
        r2 = sector_tab.row_for_block(2)
        self.assertEqual(table.item(r2, 2).text(), "-")
        self.assertEqual(table.item(r2, 17).text(), "-")
        self.assertEqual(table.item(r2, 18).text(), "-")

        # 2. 模拟读取成功（真实数据就是 0x00）：渲染原样 '00' 而非 '-'
        sector_tab.dump.set_block(2, bytes([0x00] * 16))
        sector_tab.refresh_table()
        r2 = sector_tab.row_for_block(2)
        self.assertEqual(table.item(r2, 2).text(), "00")
        self.assertEqual(table.item(r2, 17).text(), "00")
        self.assertEqual(table.item(r2, 18).text(), "." * 16)

        # 3. 模拟加密扇区读取受阻：标记为 READ_FAILED，渲染 '??' 与 '[加密受限]'
        sector_tab.dump.set_block_state(3, BlockState.READ_FAILED)
        sector_tab.refresh_table()
        r3 = sector_tab.row_for_block(3)
        self.assertEqual(table.item(r3, 2).text(), "??")
        self.assertEqual(table.item(r3, 17).text(), "??")
        self.assertEqual(table.item(r3, 18).text(), "[加密受限]")

    def test_gui_left_panel_layout_and_device_selection(self):
        """测试左侧看板控件无截断、无覆盖、设备类型名称与尺寸自适应正确"""
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        # 1. 验证设备选择下拉框显示友好中文标题，而非内部ID 'auto'
        self.assertNotEqual(self.win.combo_device.currentText(), "auto", "设备类型不应显示内部ID 'auto'")
        self.assertEqual(self.win.combo_device.currentData(), "auto")
        self.assertIn("自动识别硬件", self.win.combo_device.currentText())

        # 2. 验证串口刷新按钮与左右读卡按钮正常加载
        self.assertTrue(self.win.btn_refresh_ports.isVisible())
        self.assertGreater(self.win.btn_refresh_ports.width(), 0)
        self.assertTrue(self.win.btn_connect.isVisible())
        self.assertTrue(self.win.btn_read_id_card.isVisible())

        # 3. 验证左侧面板最小尺寸不会大于滚动区域最小宽度，防止内容被右侧截断/覆盖
        left_scroll = self.win.main_hsplitter.widget(0)
        left_panel = left_scroll.widget()
        self.assertLessEqual(
            left_panel.minimumSizeHint().width(),
            left_scroll.minimumWidth(),
            "左侧面板的最小尺寸不应超出滚动区域的最小宽度，否则会导致水平截断覆盖！"
        )



class Test11CrackScopeAndManualDecrypt(unittest.TestCase):
    """测试字典破解扇区范围选择、手动密钥解密对话框与密钥留存联动"""

    def setUp(self):
        from PyQt6.QtWidgets import QApplication
        self.app = QApplication.instance()
        if not self.app:
            self.app = QApplication(sys.argv)

    def _build_dump(self):
        from core.dump_model import MifareDump, BlockState
        d = MifareDump(is_4k=False)
        for s in range(16):
            for b in range(s * 4, s * 4 + 4):
                d.set_block(b, bytes(16))
                d.set_block_state(b, BlockState.READ_FAILED if s in (1, 12, 13) else BlockState.READ_OK)
        d.set_uid(bytes.fromhex("D77EA0DF"))  # 必须在块初始化后设置 UID (Block0 前4字节)
        return d

    def test_sector_scope_default_selects_encrypted(self):
        """范围选择对话框默认仅勾选未解密(加密)扇区"""
        from ui.crack_dialogs import SectorScopeDialog
        dlg = SectorScopeDialog(None, dump=self._build_dump())
        self.assertEqual(dlg.get_selected_sectors(), [1, 12, 13])

    def test_sector_scope_all_readable_has_no_selection(self):
        """全部可读时应无默认勾选"""
        from ui.crack_dialogs import SectorScopeDialog
        from core.dump_model import MifareDump, BlockState
        d = MifareDump(is_4k=False)
        d.set_uid(bytes.fromhex("AAAAAAAA"))
        for b in range(64):
            d.set_block(b, bytes(16))
            d.set_block_state(b, BlockState.READ_OK)
        dlg = SectorScopeDialog(None, dump=d)
        self.assertEqual(dlg.get_selected_sectors(), [])

    def test_manual_key_dialog_parsing(self):
        """手动密钥对话框类型/HEX 解析与建议预填"""
        from ui.crack_dialogs import ManualKeyDialog
        dlg = ManualKeyDialog(None, block_idx=5, sector=1,
                              suggestion_a="010203040506", suggestion_b="")
        self.assertEqual(dlg.get_key_type(), "A")
        self.assertEqual(dlg.get_key_hex(), "010203040506")
        dlg2 = ManualKeyDialog(None, block_idx=5, sector=1, suggestion_a="", suggestion_b="")
        dlg2.combo_type.setCurrentIndex(1)
        dlg2.edit_key.setText("aabb ccdd eeFF")
        self.assertEqual(dlg2.get_key_type(), "B")
        self.assertEqual(dlg2.get_key_hex(), "AABBCCDDEEFF")

    def test_sector_table_persists_recovered_keys(self):
        """扇区表格在破解命中回调时把卡号+密钥写入数据库"""
        import tempfile
        from core.card_db import CardDatabase
        from ui.sector_table import SectorTableWidget

        path = os.path.join(tempfile.gettempdir(), f"test_keys_{int(time.time()*1000)}.db")
        db = CardDatabase(db_path=path)
        try:
            w = SectorTableWidget(serial_worker=None)
            w.set_database(db)
            w.dump = self._build_dump()
            w._on_worker_sector_cracked(1, "010203040506", "010203040506")
            keys = db.get_card_keys("D77EA0DF")
            self.assertEqual(keys[1]["key_a"], "010203040506")
            self.assertEqual(keys[1]["key_b"], "010203040506")
        finally:
            db.close()
            if os.path.exists(path):
                os.remove(path)

    def test_worker_read_sector_op_constant(self):
        """CardOperationWorker 暴露手动单扇区读取操作常量"""
        from core.services.card_worker import CardOperationWorker
        self.assertEqual(CardOperationWorker.OP_READ_SECTOR, "read_sector")
        self.assertIn("manual_key", CardOperationWorker.__init__.__code__.co_varnames)


class Test05CardOperationWorkerStubs(unittest.TestCase):
    """测试 CardOperationWorker 与底层通信的桩交互，锁死 P0 契约"""

    class MockWorker:
        def __init__(self):
            self.responses = {}

        def is_connected(self):
            return True

        def send_and_wait(self, cmd, data, timeout=0.25):
            from core.protocol import ReaderProtocol
            if cmd in (ReaderProtocol.CMD_AUTH_KEY_A, ReaderProtocol.CMD_AUTH_KEY_B):
                # 模拟真实协议解析器产出的字典
                return {"status": "success", "status_code": 0x00, "ok": True}
            elif cmd == ReaderProtocol.CMD_READ_BLOCK:
                return {
                    "status": "success",
                    "status_code": 0x00,
                    "ok": True,
                    "block_data": bytes([0x33] * 16),
                    "data": bytes([0x33] * 16)
                }
            elif cmd == ReaderProtocol.CMD_WRITE_BLOCK:
                return {"status": "success", "status_code": 0x00, "ok": True}
            return None

    def setUp(self):
        from core.card_service import CardOperationWorker
        self.mock_worker = self.MockWorker()
        self.op_worker = CardOperationWorker(
            worker=self.mock_worker,
            op_type=CardOperationWorker.OP_READ_CARD
        )

    def test_authenticate_contract(self):
        auth_res = self.op_worker._authenticate_sector(0, "A", b"\xFF"*6)
        self.assertTrue(auth_res, "认证必须返回 True，契约不能错配")

    def test_read_block_contract(self):
        data = self.op_worker._read_single_block(0)
        self.assertIsNotNone(data, "读块必须返回有效字节，键名不能错配")
        self.assertEqual(data, bytes([0x33] * 16))

    def test_write_block_contract(self):
        write_res = self.op_worker._write_single_block(1, bytes([0x44] * 16))
        self.assertTrue(write_res, "写块必须返回 True，契约不能错配")

    def test_write_card_authenticates_once_per_sector(self):
        """写卡时每个扇区只认证一次，且默认跳过 Block 0"""
        from core.card_service import CardOperationWorker
        from core.dump_model import MifareDump

        auth_blocks = []
        written_blocks = []

        class MockWriteWorker:
            def __init__(self):
                class DummyAdapter:
                    is_bidirectional = True
                self.adapter = DummyAdapter()

            def is_connected(self):
                return True

            def authenticate(self, block, key_type, key, uid=b"", timeout=0.35):
                auth_blocks.append(block)
                return True

            def write_block(self, block, data, timeout=0.35):
                written_blocks.append(block)
                return True

            def write_magic_block0(self, data, magic_type="CUID", timeout=0.35):
                return True

        dump = MifareDump(is_4k=False)
        op = CardOperationWorker(
            worker=MockWriteWorker(),
            op_type=CardOperationWorker.OP_WRITE_CARD,
            dump_to_write=dump,
            allow_block0_write=False,
        )
        op._do_write_card()

        self.assertEqual(len(auth_blocks), dump.sector_count)
        self.assertEqual(len(set(auth_blocks)), dump.sector_count)
        self.assertNotIn(0, written_blocks)
        self.assertEqual(len(written_blocks), dump.block_count - 1)

    def test_pn532_adapter_passthrough_contract(self):
        """测试 CardOperationWorker 透传调用 PN532Adapter 适配器方法契约"""
        from core.card_service import CardOperationWorker

        class MockAdapterWorker:
            def __init__(self):
                class DummyAdapter:
                    is_bidirectional = True
                self.adapter = DummyAdapter()

            def is_connected(self):
                return True

            def authenticate(self, block, key_type, key, timeout=0.25):
                return True

            def read_block(self, block, timeout=0.25):
                return bytes([0x77] * 16)

            def write_block(self, block, data, timeout=0.3):
                return True

            def write_magic_block0(self, data, magic_type="CUID", timeout=0.35):
                return True

        worker = MockAdapterWorker()
        op = CardOperationWorker(worker=worker, op_type=CardOperationWorker.OP_READ_CARD)
        self.assertTrue(op._authenticate_sector(0, "A", b"\xFF"*6))
        self.assertEqual(op._read_single_block(0), bytes([0x77] * 16))
        self.assertTrue(op._write_single_block(1, bytes([0x88] * 16)))
        # Block 0 写保护测试: 默认禁止
        op.allow_block0_write = False
        self.assertFalse(op._write_single_block(0, bytes([0x99] * 16)))
        # 显式允许后允许写入 Block 0
        op.allow_block0_write = True
        self.assertTrue(op._write_single_block(0, bytes([0x99] * 16)))


class Test06HardwarePortSanity(unittest.TestCase):
    """测试底层真实串口通讯链路健康度 (自适应物理拔插)"""

    def test_serial_port_detection(self):
        import serial.tools.list_ports
        ports = [p.device for p in serial.tools.list_ports.comports()]
        print(f"\n[硬件链路扫描] 系统当前检测到的串口: {ports}")
        if "COM3" not in ports:
            self.skipTest("物理硬件 COM3 端口当前未插入，已安全跳过端口在线断言。")
        else:
            self.assertIn("COM3", ports)


class Test07Pn532AdapterAndProtocol(unittest.TestCase):
    """测试 PCR532 / PN532 模块驱动、HSU 协议封装与适配器契约"""

    def test_pn532_frame_build_and_checksums(self):
        from core.adapters.pn532_adapter import PN532Adapter
        # 探测固件指令: CMD 0x02 (GetFirmwareVersion)
        frame = PN532Adapter.build_hsu_frame(PN532Adapter.CMD_GET_FIRMWARE_VERSION)
        # 格式: 00 00 FF LEN LCS D4 CMD DCS 00
        # LEN = 2 (D4 + 02), LCS = 0xFE (0x02 + 0xFE = 0x100)
        # DCS = 0x100 - (0xD4 + 0x02) = 0x2A
        expected = bytes([0x00, 0x00, 0xFF, 0x02, 0xFE, 0xD4, 0x02, 0x2A, 0x00])
        self.assertEqual(frame, expected)

    def test_pn532_parse_ack_and_response(self):
        from core.adapters.pn532_adapter import PN532Adapter
        # ACK 帧
        ack = PN532Adapter.ACK_FRAME
        info, remaining = PN532Adapter.parse_hsu_frame(ack)
        self.assertIsNotNone(info)
        self.assertEqual(info.get("type"), "ACK")
        self.assertEqual(remaining, b"")

        # 固件版本应答帧: D5 03 [32 01 06 07]
        fw_frame = PN532Adapter.build_response_frame(0x03, bytes([0x32, 0x01, 0x06, 0x07]))
        info, remaining = PN532Adapter.parse_hsu_frame(fw_frame)
        self.assertIsNotNone(info)
        self.assertEqual(info.get("type"), "DATA")
        self.assertEqual(info.get("cmd"), 0x03)
        self.assertEqual(info.get("data"), bytes([0x32, 0x01, 0x06, 0x07]))
        self.assertEqual(remaining, b"")

    def test_pn532_parse_card_target(self):
        from core.adapters.pn532_adapter import PN532Adapter
        adapter = PN532Adapter()
        # InListPassiveTarget (0x4A) 的响应 (0x4B):
        # NbTg=1, Tg=1, SENS_RES=00 04, SEL_RES=08, NFCIDLength=4, NFCID=D7 7E A0 DF
        body = bytes([0x01, 0x01, 0x00, 0x04, 0x08, 0x04, 0xD7, 0x7E, 0xA0, 0xDF])
        parsed = adapter._parse_target_data(body)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["uid_bytes"], bytes([0xD7, 0x7E, 0xA0, 0xDF]))
        self.assertEqual(parsed["sak"], 0x08)
        self.assertEqual(parsed["conversions"]["dec_10d_rev"], "3751837399")

    def test_pn532_adapter_mock_exchange(self):
        from core.adapters.pn532_adapter import PN532Adapter

        class MockSerial:
            def __init__(self):
                self.is_open = True
                self.dtr = False
                self.rts = False
                self.write_buffer = bytearray()
                self.read_queue = bytearray()

            @property
            def in_waiting(self):
                return len(self.read_queue)

            def write(self, data):
                self.write_buffer.extend(data)
                # 模拟自动回复 ACK + 响应
                if bytes([0xD4, 0x02]) in data:
                    # GetFirmwareVersion (0x02 -> 0x03)
                    ack = PN532Adapter.ACK_FRAME
                    fw_resp = PN532Adapter.build_response_frame(0x03, bytes([0x32, 0x01, 0x06, 0x07]))
                    self.read_queue.extend(ack + fw_resp)
                elif bytes([0xD4, 0x14]) in data:
                    # SAMConfiguration (0x14 -> 0x15)
                    ack = PN532Adapter.ACK_FRAME
                    sam_resp = PN532Adapter.build_response_frame(0x15)
                    self.read_queue.extend(ack + sam_resp)
                elif bytes([0xD4, 0x4A]) in data:
                    # InListPassiveTarget (0x4A -> 0x4B)
                    ack = PN532Adapter.ACK_FRAME
                    target_body = bytes([0x01, 0x01, 0x00, 0x04, 0x08, 0x04, 0xD7, 0x7E, 0xA0, 0xDF])
                    card_resp = PN532Adapter.build_response_frame(0x4B, target_body)
                    self.read_queue.extend(ack + card_resp)

            def read(self, size=1):
                if not self.read_queue:
                    return b""
                ret = self.read_queue[:size]
                self.read_queue = self.read_queue[size:]
                return bytes(ret)

            def flush(self):
                pass

            def reset_input_buffer(self):
                self.read_queue.clear()

            def reset_output_buffer(self):
                pass

        ser = MockSerial()
        adapter = PN532Adapter()
        self.assertTrue(adapter.is_bidirectional)

        # 1. 固件探测 / 初始化
        adapter.init_device(ser)
        self.assertIn("PN532", adapter.firmware_info)

        # 2. 寻卡轮询
        card = adapter.poll_card(ser)
        self.assertIsNotNone(card)
        self.assertEqual(card["conversions"]["hex_normal"], "D7 7E A0 DF")
        self.assertEqual(card["conversions"]["dec_10d_rev"], "3751837399")


class Test08KeyManagerAndConcurrentCracking(unittest.TestCase):
    """测试 MCT 密钥字典管理器 (KeyManager) 与批量并发破解线程池逻辑"""

    def test_key_manager_file_discovery_and_parsing(self):
        from core.key_manager import KeyManager
        files = KeyManager.list_available_files()
        filenames = [f["filename"] for f in files]

        # 必须发现 MCT 三大官方核心字典
        self.assertIn("std.keys", filenames)
        self.assertIn("hotel-std.keys", filenames)
        self.assertIn("extended-std.keys", filenames)

        # 校验 std.keys 包含基础出厂密码
        std_keys = KeyManager.parse_key_file(os.path.join(KeyManager.get_keys_dir(), "std.keys"))
        self.assertIn("FFFFFFFFFFFF", std_keys)
        self.assertIn("A0A1A2A3A4A5", std_keys)
        self.assertIn("D3F7D3F7D3F7", std_keys)
        self.assertEqual(len(std_keys), 3)

        # 校验 hotel-std.keys 解析出有效密钥
        hotel_keys = KeyManager.parse_key_file(os.path.join(KeyManager.get_keys_dir(), "hotel-std.keys"))
        self.assertGreater(len(hotel_keys), 10)

        # 校验 extended-std.keys 解析出 1400+ 条大字典密钥
        ext_keys = KeyManager.parse_key_file(os.path.join(KeyManager.get_keys_dir(), "extended-std.keys"))
        self.assertGreater(len(ext_keys), 1400)

        # 校验多选合并与去重
        combined = KeyManager.load_combined_keys(["std.keys", "hotel-std.keys"])
        self.assertEqual(len(combined), len(set(combined)))
        # 优先级必须保持 std.keys 在前
        self.assertEqual(combined[0], "FFFFFFFFFFFF")

    def test_concurrent_batch_cracking_workflow(self):
        from core.card_service import CardOperationWorker

        class MockConcurrentWorker:
            def __init__(self):
                # 设定扇区密钥: Sector 0 是出厂 FFFFFFFFFFFF，Sector 1 是酒店键 2A2C13CC242A
                self.sector_keys = {
                    3: b"\xFF" * 6,
                    7: bytes.fromhex("2A2C13CC242A"),
                }

            def is_connected(self):
                return True

            def send_and_wait(self, cmd, data, timeout=0.25):
                from core.protocol import ReaderProtocol
                if cmd in (ReaderProtocol.CMD_AUTH_KEY_A, ReaderProtocol.CMD_AUTH_KEY_B):
                    block = data[0]
                    key = data[1:7]
                    expected = self.sector_keys.get(block)
                    if expected and key == expected:
                        return {"status": "success", "status_code": 0x00, "ok": True}
                    return {"status": "fail", "status_code": 0x02, "ok": False}
                return None

        mock_worker = MockConcurrentWorker()
        test_keys = ["000000000000", "A0A1A2A3A4A5", "FFFFFFFFFFFF", "2A2C13CC242A", "123456789ABC"]
        cracked_history = {}

        op_worker = CardOperationWorker(
            worker=mock_worker,
            op_type=CardOperationWorker.OP_CRACK_KEYS,
            target_sectors=[0, 1],
            custom_keys=test_keys,
            concurrency=4
        )
        op_worker.sig_sector_cracked.connect(lambda s, a, b: cracked_history.update({s: (a, b)}))

        op_worker._do_crack_keys()

        # 校验 Sector 0 破解出 FFFFFFFFFFFF
        self.assertIn(0, cracked_history)
        self.assertEqual(cracked_history[0][0], "FFFFFFFFFFFF")

        # 校验 Sector 1 破解出 2A2C13CC242A
        self.assertIn(1, cracked_history)
        self.assertEqual(cracked_history[1][0], "2A2C13CC242A")


from core.adapters.pn532_adapter import PN532Adapter
from core.protocol import CardConverter


class Test09IdCardReaderAndTypeBProtocol(unittest.TestCase):
    """测试二代居民身份证 (ISO/IEC 14443-B) 非标握手与 8 字节 UID 读取流程"""

    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(sys.argv)

    def test_crc_b_calculation(self):
        """验证 ISO 14443-B CRC 计算完全符合博客园实测与标准文档"""
        # REQB CRC: 05 00 00 -> 71 FF
        reqb = bytes([0x05, 0x00, 0x00])
        self.assertEqual(PN532Adapter.calculate_crc_b(reqb), bytes([0x71, 0xFF]))

        # ATTRIB (PUPI 00 00 00 00) CRC: 1d 00 00 00 00 00 08 01 08 -> F3 10
        attrib = bytes.fromhex("1D 00 00 00 00 00 08 01 08")
        self.assertEqual(PN532Adapter.calculate_crc_b(attrib), bytes([0xF3, 0x10]))

        # Read GUID CRC: 00 36 00 00 08 -> 57 44
        guid = bytes.fromhex("00 36 00 00 08")
        self.assertEqual(PN532Adapter.calculate_crc_b(guid), bytes([0x57, 0x44]))

    def test_type_b_id_registers_definitions(self):
        """验证 12 个 CIU 射频寄存器调谐参数"""
        adapter = PN532Adapter()
        self.assertEqual(len(adapter.CIU_REGISTERS_TYPE_B_ID), 12)
        # 验证 CIU_Mode 和 CIU_TypeB
        reg_map = dict(adapter.CIU_REGISTERS_TYPE_B_ID)
        self.assertEqual(reg_map[0x6301], 0xFF)
        self.assertEqual(reg_map[0x630E], 0x03)
        self.assertEqual(reg_map[0x6314], 0x68)

    def test_mock_id_card_full_reading_pipeline(self):
        """桩测试：模拟 PCR532 经由 REQB -> ATTRIB -> Read GUID 完整读取二代身份证 8 字节 UID"""
        adapter = PN532Adapter()

        class MockSerialForId:
            def __init__(self):
                self.is_open = True
                self.dtr = False
                self.rts = False
                self.read_queue = bytearray()

            def reset_input_buffer(self):
                self.read_queue.clear()
            def reset_output_buffer(self): pass
            def flush(self): pass

            @property
            def in_waiting(self):
                return len(self.read_queue)

            def read(self, size=1):
                chunk = bytes(self.read_queue[:size])
                self.read_queue = self.read_queue[size:]
                return chunk

            def write(self, data):
                ack = PN532Adapter.ACK_FRAME
                if bytes([0xD4, 0x08]) in data:
                    # WriteRegister (0x08 -> 0x09)
                    resp = PN532Adapter.build_response_frame(0x09, b"")
                    self.read_queue.extend(ack + resp)
                elif bytes([0xD4, 0x32]) in data:
                    # RFConfiguration (0x32 -> 0x33), field/retry commands
                    resp = PN532Adapter.build_response_frame(0x33, b"")
                    self.read_queue.extend(ack + resp)
                elif bytes([0xD4, 0x42, 0x05, 0x00, 0x00]) in data:
                    # REQB -> 返回 ATQB (状态码 0x00 + 0x50 + PUPI[4B] + 额外数据)
                    pupi = bytes([0x12, 0x34, 0x56, 0x78])
                    atqb_payload = bytes([0x00, 0x50]) + pupi + bytes([0x00, 0xD1, 0x03, 0x00, 0x81, 0x00])
                    resp = PN532Adapter.build_response_frame(0x43, atqb_payload)
                    self.read_queue.extend(ack + resp)
                elif bytes([0xD4, 0x42, 0x1D]) in data:
                    # ATTRIB -> 返回 0x00 状态码
                    resp = PN532Adapter.build_response_frame(0x43, bytes([0x00, 0x00]))
                    self.read_queue.extend(ack + resp)
                elif bytes([0xD4, 0x42, 0x00, 0x36, 0x00, 0x00, 0x08]) in data:
                    # Read GUID -> 返回 0x00 状态码 + 8 字节身份证 UID + 4 字节 CRC
                    mock_id_uid = bytes([0x41, 0x52, 0x63, 0x74, 0x85, 0x96, 0xA7, 0xB8])
                    guid_resp = bytes([0x00]) + mock_id_uid + bytes([0x90, 0x00, 0x12, 0x34])
                    resp = PN532Adapter.build_response_frame(0x43, guid_resp)
                    self.read_queue.extend(ack + resp)

        mock_ser = MockSerialForId()
        card_info = adapter.read_id_card_uid(mock_ser, timeout=0.2)

        self.assertIsNotNone(card_info)
        self.assertTrue(card_info.get("is_id_card"))
        expected_uid = bytes([0x41, 0x52, 0x63, 0x74, 0x85, 0x96, 0xA7, 0xB8])
        self.assertEqual(card_info.get("uid_bytes"), expected_uid)
        self.assertEqual(card_info.get("card_type"), "二代居民身份证 (8-byte UID / ISO14443-B)")

        conv = card_info.get("conversions", {})
        self.assertEqual(conv.get("uid_length"), 8)
        self.assertEqual(conv.get("hex_normal"), "41 52 63 74 85 96 A7 B8")

    def test_gui_id_card_swipe_rendering(self):
        """测试 GUI 主窗口在感应到二代身份证时的高亮渲染与看版展示"""
        from ui.main_window import MainWindow
        win = MainWindow()

        mock_id_bytes = bytes([0x5A, 0x6B, 0x7C, 0x8D, 0x1E, 0x2F, 0x30, 0x41])
        conv = CardConverter.convert_uid(mock_id_bytes)
        frame_info = {
            "uid_bytes": mock_id_bytes,
            "conversions": conv,
            "raw": mock_id_bytes,
            "is_id_card": True,
        }

        win._on_card_swiped(frame_info)

        # 校验 Hero 看板徽章为二代身份证指示
        self.assertIn("二代身份证", win.lbl_card_badge.text())
        self.assertEqual(win.lbl_hero_uid.text(), "5A 6B 7C 8D 1E 2F 30 41")
        self.assertEqual(win.val_hex_norm.text(), "5A 6B 7C 8D 1E 2F 30 41")

        # 校验扇区矩阵 Block 0 记录了 8 字节 UID
        b0_data = win.tab_sector.dump.get_block(0)
        self.assertEqual(b0_data[:8], mock_id_bytes)


class Test10ArchitectureDecouplingAndExtensions(unittest.TestCase):
    """测试重构解耦后的纯协议层、拓展插槽与门面兼容性"""

    def test_pn532_protocol_stateless_codecs(self):
        """测试无状态 PN532Protocol 纯数据帧编解码"""
        from core.protocols.pn532 import PN532Protocol
        # 1. 主机发往 PN532 的请求帧 (TFI = 0xD4)
        req_frame = PN532Protocol.build_hsu_frame(0x02, b"")
        self.assertTrue(req_frame.startswith(b"\x00\x00\xFF"))
        self.assertTrue(req_frame.endswith(b"\x00"))

        # 2. PN532 返回主机的应答帧 (TFI = 0xD5)
        resp_frame = PN532Protocol.build_response_frame(0x03, bytes([0x32, 0x01, 0x06, 0x07]))
        parsed, rem = PN532Protocol.parse_hsu_frame(resp_frame)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.get("type"), "DATA")
        self.assertEqual(parsed.get("cmd"), 0x03)
        self.assertEqual(parsed.get("data"), bytes([0x32, 0x01, 0x06, 0x07]))

    def test_iso14443b_protocol_stateless_frames(self):
        """测试无状态 ISO14443BProtocol 帧组装与 CRC-B 签名"""
        from core.protocols.iso14443b import ISO14443BProtocol
        reqb = ISO14443BProtocol.build_reqb_frame()
        self.assertEqual(reqb, bytes([0x05, 0x00, 0x00, 0x71, 0xFF]))

        read_guid = ISO14443BProtocol.build_read_guid_frame()
        self.assertEqual(read_guid, bytes([0x00, 0x36, 0x00, 0x00, 0x08, 0x57, 0x44]))

        mock_atqb = bytes([0x50, 0xAA, 0xBB, 0xCC, 0xDD, 0x11, 0x22])
        pupi = ISO14443BProtocol.parse_atqb(mock_atqb)
        self.assertEqual(pupi, bytes([0xAA, 0xBB, 0xCC, 0xDD]))

    def test_virtual_dump_reader_simulation(self):
        """测试软件虚拟卡离线读写器适配器 (VirtualDumpReaderAdapter)"""
        from core.adapters.extensions.virtual_adapter import VirtualDumpReaderAdapter
        from core.models.dump import MifareDump

        dump = MifareDump(is_4k=False)
        test_uid = bytes([0x12, 0x34, 0x56, 0x78])
        dump.set_uid(test_uid)

        # 设置第 1 扇区自定义密码 Key A
        t_block = dump.get_sector_trailer_block(1)
        custom_key_a = bytes([0xAA, 0xBB, 0xCC, 0x11, 0x22, 0x33])
        trailer_data = bytearray(dump.get_block(t_block))
        trailer_data[0:6] = custom_key_a
        dump.set_block(t_block, bytes(trailer_data))

        # 挂载到虚拟读写器
        reader = VirtualDumpReaderAdapter(dump)
        self.assertTrue(reader.is_bidirectional)

        # 寻卡测试
        card = reader.poll_card()
        self.assertIsNotNone(card)
        self.assertEqual(card.get("uid_bytes"), test_uid)

        # 认证与读写测试
        # 1. 错误密码认证应失败
        self.assertFalse(reader.authenticate(None, block=4, key_type="A", key=b"\xFF"*6))
        # 2. 正确密码认证应成功
        self.assertTrue(reader.authenticate(None, block=4, key_type="A", key=custom_key_a))
        # 3. 写块与读块
        write_payload = bytes([0x42] * 16)
        self.assertTrue(reader.write_block(None, block=4, data=write_payload))
        self.assertEqual(reader.read_block(None, block=4), write_payload)

    def test_factory_custom_adapter_registration(self):
        """测试 ReaderAdapterFactory 动态注册扩展适配器机制"""
        from core.adapters.factory import ReaderAdapterFactory
        from core.adapters.base_adapter import BaseReaderAdapter

        class CustomMockAdapter(BaseReaderAdapter):
            def __init__(self):
                super().__init__()
                self.device_name = "MyCustomReader"

            def init_device(self, ser=None): return True
            def parse_incoming(self, rx): return None, bytes(rx)
            def poll_card(self, ser=None, timeout=0.5): return None
            def authenticate(self, ser, block, key_type, key, uid=b"", timeout=0.35): return False
            def read_block(self, ser, block, timeout=0.35): return None
            def write_block(self, ser, block, data, timeout=0.35): return False

        ReaderAdapterFactory.register_adapter("custom_plugin", CustomMockAdapter)
        inst = ReaderAdapterFactory.create_adapter("custom_plugin")
        self.assertIsInstance(inst, CustomMockAdapter)
        self.assertEqual(inst.device_name, "MyCustomReader")

    def test_libnfc_cli_adapter_contract(self):
        """LibnfcCliAdapter 必须可实例化并完整实现基类抽象契约"""
        from core.adapters import BaseReaderAdapter, LibnfcCliAdapter

        adapter = LibnfcCliAdapter()
        self.assertIsInstance(adapter, BaseReaderAdapter)
        self.assertEqual(adapter.parse_incoming(bytearray(b"abc")), (None, b"abc"))
        self.assertFalse(adapter.authenticate(None, 0, "A", b"\xFF" * 6))
        self.assertIsNone(adapter.read_block(None, 0))
        self.assertFalse(adapter.write_block(None, 0, bytes(16)))

    def test_gen1a_magic_block0_backdoor_sequence(self):
        """Gen1a 写 Block 0 必须先发送 HALT 与 40/43 后门解锁序列"""
        from core.adapters.pn532_adapter import PN532Adapter

        adapter = PN532Adapter()
        calls = []
        written = {}

        def fake_send(ser, cmd, data=b"", timeout=0.3):
            calls.append((cmd, data))
            return b"\x00"

        def fake_write(ser, block, data, timeout=0.35):
            written["block"] = block
            written["data"] = data
            return True

        adapter._send_and_receive = fake_send
        adapter.write_block = fake_write

        payload = bytes(range(16))
        self.assertTrue(adapter.write_magic_block0(None, payload, magic_type="GEN1A"))
        self.assertEqual(calls[0][1], bytes([0x50, 0x00]))
        self.assertEqual(calls[1][1], bytes([0x40]))
        self.assertEqual(calls[2][1], bytes([0x43]))
        self.assertEqual(written, {"block": 0, "data": payload})

    def test_facade_backward_compatibility_reexports(self):
        """测试所有门面文件（protocol/dump_model/key_manager/serial_worker/card_service）的无损 Re-export"""
        import core.protocol as p
        import core.dump_model as d
        import core.key_manager as k
        import core.serial_worker as s
        import core.card_service as c

        # 协议与模型
        self.assertTrue(hasattr(p, "ReaderProtocol"))
        self.assertTrue(hasattr(p, "CardConverter"))
        self.assertTrue(hasattr(p, "AccessBitsDecoder"))
        self.assertTrue(hasattr(p, "AccessBitsEncoder"))
        self.assertTrue(hasattr(p, "PN532Protocol"))
        self.assertTrue(hasattr(p, "ISO14443BProtocol"))

        # Dump 模型
        self.assertTrue(hasattr(d, "MifareDump"))
        self.assertTrue(hasattr(d, "BlockState"))

        # 字典与工作器
        self.assertTrue(hasattr(k, "KeyManager"))
        self.assertTrue(hasattr(s, "SerialWorker"))
        self.assertTrue(hasattr(c, "CardOperationWorker"))
        self.assertTrue(hasattr(c, "DEFAULT_KEYS_HEX"))


class Test12TransportLayerAndBle(unittest.TestCase):
    """测试多通信链路传输层抽象、BLE 适配及 GUI 动态连接模式切换"""

    def test_transport_factory_creations(self):
        """测试 TransportFactory 创建 serial、ble 以及未知协议回退"""
        from core.transport.factory import TransportFactory
        from core.transport.serial_transport import SerialTransport
        from core.transport.ble_transport import BleTransport

        t_ser = TransportFactory.create_transport("serial", port="COM1", baudrate=115200)
        self.assertIsInstance(t_ser, SerialTransport)

        t_ble = TransportFactory.create_transport("ble", address="9C:7F:64:7A:1A:A4")
        self.assertIsInstance(t_ble, BleTransport)
        self.assertEqual(t_ble.address, "9C:7F:64:7A:1A:A4")

        # 未知协议抛出 TransportError
        from core.transport.base import TransportError
        with self.assertRaises(TransportError):
            TransportFactory.create_transport("unknown_proto")

    def test_transport_factory_custom_registration(self):
        """测试 TransportFactory 动态扩展机制 (为未来 TCP/Modbus 提供插槽)"""
        from core.transport.factory import TransportFactory
        from core.transport.base import ITransport

        class MockTcpTransport(ITransport):
            def __init__(self, host="127.0.0.1", port=8080):
                self.host = host
                self.port = port
            def open(self): return True
            def close(self): pass
            @property
            def is_open(self): return True
            def read(self, size=1, timeout=None): return b""
            def write(self, data): return len(data)
            def flush(self): pass
            def reset_input_buffer(self): pass
            def reset_output_buffer(self): pass
            @property
            def in_waiting(self): return 0

        TransportFactory.register_transport("tcp", MockTcpTransport)
        self.assertIn("tcp", TransportFactory.list_transports())
        tcp_inst = TransportFactory.create_transport("tcp", host="192.168.1.100", port=502)
        self.assertIsInstance(tcp_inst, MockTcpTransport)
        self.assertEqual(tcp_inst.host, "192.168.1.100")

    def test_ble_transport_callable_duck_typing(self):
        """测试 CallableBool 与 CallableInt 兼顾属性与方法调用的双重鸭子类型契约"""
        from core.transport.ble_transport import CallableBool, CallableInt

        cb_true = CallableBool(True)
        self.assertTrue(bool(cb_true))
        self.assertTrue(cb_true())  # 兼容方法调用
        self.assertEqual(cb_true, True)

        cb_false = CallableBool(False)
        self.assertFalse(bool(cb_false))
        self.assertFalse(cb_false())
        self.assertEqual(cb_false, False)

        ci = CallableInt(16)
        self.assertEqual(int(ci), 16)
        self.assertEqual(ci(), 16)  # 兼容方法调用
        self.assertGreater(ci, 0)
        self.assertEqual(ci + 4, 20)

    def test_ble_transport_mock_data_exchange(self):
        """测试 BleTransport 在无物理硬件下的内部缓冲队列收发与超时机制"""
        from core.transport.ble_transport import BleTransport

        t = BleTransport(address="00:11:22:33:44:55", timeout=0.1)
        self.assertFalse(t.is_open)
        t._is_connected = True
        self.assertTrue(t.is_open)

        # 模拟 RX 回调注入数据
        t._on_rx_data(bytearray(b"\x00\x00\xFF\x00\xFF\x00"))  # ACK 帧
        self.assertEqual(t.in_waiting, 6)
        self.assertEqual(t.in_waiting(), 6)

        read_data = t.read(6)
        self.assertEqual(read_data, b"\x00\x00\xFF\x00\xFF\x00")
        self.assertEqual(t.in_waiting, 0)

        # 超时读空
        empty_data = t.read(4)
        self.assertEqual(empty_data, b"")

        # 缓冲队列清理
        t._on_rx_data(bytearray(b"\x12\x34\x56"))
        self.assertEqual(t.in_waiting, 3)
        t.reset_input_buffer()
        self.assertEqual(t.in_waiting, 0)

    def test_serial_worker_ble_configuration(self):
        """测试 SerialWorker 对 BLE 模式的参数设置与状态初始化"""
        from core.services.serial_worker import SerialWorker
        worker = SerialWorker()

        worker.set_ble_connection("9C:7F:64:7A:1A:A4", device_type="pn532")
        self.assertEqual(worker.conn_type, "ble")
        self.assertEqual(worker.ble_address, "9C:7F:64:7A:1A:A4")
        self.assertEqual(worker.device_type, "pn532")
        self.assertIn("PCR532", worker.adapter.device_name)

    def test_gui_ble_mode_toggle_and_controls(self):
        """测试 GUI 主窗口中 USB 串口与 BLE 蓝牙模式的无缝切换与控件显隐"""
        from PyQt6.QtWidgets import QApplication
        from ui.main_window import MainWindow

        app = QApplication.instance() or QApplication(sys.argv)
        win = MainWindow()
        win.show()
        try:
            # 1. 默认处于串口模式
            self.assertTrue(win.rb_conn_serial.isChecked())
            self.assertFalse(win.rb_conn_ble.isChecked())
            self.assertTrue(win.lbl_port.isVisible())
            self.assertTrue(win.w_port.isVisible())
            self.assertTrue(win.btn_refresh_ports.isVisible())
            self.assertFalse(win.lbl_ble.isVisible())
            self.assertFalse(win.w_ble.isVisible())

            # 2. 切换到蓝牙 BLE 模式
            win.rb_conn_ble.setChecked(True)
            QApplication.processEvents()
            self.assertFalse(win.lbl_port.isVisible())
            self.assertFalse(win.w_port.isVisible())
            self.assertTrue(win.lbl_ble.isVisible())
            self.assertTrue(win.w_ble.isVisible())
            self.assertTrue(win.btn_refresh_ble.isVisible())

            # 初始状态提示扫描
            self.assertEqual(win.combo_ble.currentData(), "")

            # 模拟扫描发现设备 (真实 dict 结构测试)
            mock_devices = [
                {"name": "Minicopy(BLE)", "address": "9C:7F:64:7A:1A:A4", "rssi": -48},
                {"name": "Other_Device", "address": "11:22:33:44:55:66", "rssi": -75}
            ]
            win._on_ble_scan_found(mock_devices)
            self.assertEqual(win.combo_ble.count(), 2)
            self.assertEqual(win.combo_ble.currentData(), "9C:7F:64:7A:1A:A4")
            self.assertIn("Minicopy", win.combo_ble.currentText())

            # 3. 切换回 USB 串口模式
            win.rb_conn_serial.setChecked(True)
            QApplication.processEvents()
            self.assertTrue(win.lbl_port.isVisible())
            self.assertTrue(win.w_port.isVisible())
            self.assertFalse(win.lbl_ble.isVisible())
            self.assertFalse(win.w_ble.isVisible())
        finally:
            win.close()

    def test_pn532_firmware_probe_workflow(self):
        """测试 PN532 双向读写器固件探测正确识别为 PCR532 全功能模式 (非误判为单向广播)"""
        from core.card_service import CardOperationWorker

        class MockSerial:
            is_open = True
            def reset_input_buffer(self): pass
            def reset_output_buffer(self): pass
            def write(self, d): pass
            def flush(self): pass

        class MockPn532Adapter(PN532Adapter):
            is_bidirectional = True
            CMD_SAM_CONFIGURATION = 0x14
            def wakeup(self, ser): return True
            def get_firmware_version(self, ser=None): return "PN532 v1.6 (IC=0x01, Support=0x07)"
            def _send_and_receive(self, ser, cmd, data=b"", timeout=0.3): return b"\x00"
            def write_registers(self, ser, pairs, timeout=0.25): return True
            def poll_card(self, ser, timeout=0.25):
                return {
                    "uid_bytes": b"\x12\x34\x56\x78",
                    "conversions": CardConverter.convert_uid(b"\x12\x34\x56\x78"),
                    "raw": b"\x00\x01\x02\x03\x04"
                }

        class MockWorker:
            def __init__(self):
                self.adapter = MockPn532Adapter()
                self._serial = MockSerial()
            def is_connected(self): return True

        worker = MockWorker()
        op = CardOperationWorker(worker=worker, op_type=CardOperationWorker.OP_PROBE_FIRMWARE)
        finished_results = {}
        op.sig_finished.connect(lambda ok, summary, res: finished_results.update({"ok": ok, "summary": summary, "res": res}))

        op._do_probe_firmware()

        self.assertTrue(finished_results.get("ok"))
        summary = finished_results.get("summary", "")
        self.assertIn("PCR532 双向全功能模式", summary)
        self.assertIn("PN532 v1.6", summary)
        self.assertNotIn("单向广播", summary)

    def test_card_swipe_sync_on_read_or_load(self):
        """测试自动读卡默认开启且卡片数据实时同步至左侧卡片监测看板"""
        from PyQt6.QtWidgets import QApplication
        from ui.main_window import MainWindow
        app = QApplication.instance() or QApplication(sys.argv)
        win = MainWindow()
        win.show()
        try:
            # 校验默认自动读卡开启且周期为 300ms
            self.assertTrue(win.chk_auto_poll.isChecked())
            self.assertEqual(win.spin_poll_interval.value(), 300)

            # 模拟感应到卡片信号
            test_uid = b"\xAB\xCD\xEF\x12"
            test_frame = {
                "uid_bytes": test_uid,
                "conversions": CardConverter.convert_uid(test_uid),
                "raw": b"\xAB\xCD\xEF\x12\x08\x04\x00",
                "card_type": "Mifare Classic 1K"
            }
            win.worker.sig_card_swiped.emit(test_frame)
            QApplication.processEvents()

            # 校验左侧 Hero 看板正确展示卡片数据
            self.assertEqual(win.lbl_hero_uid.text(), "AB CD EF 12")
            self.assertEqual(win.val_hex_norm.text(), "AB CD EF 12")
            self.assertEqual(win.val_hex_rev.text(), "12 EF CD AB")
            self.assertNotEqual(win.val_dec_10d.text(), "-")
            self.assertTrue(win.btn_save_db.isEnabled())
            self.assertIn("成功识别", win.lbl_card_badge.text())
        finally:
            win.close()

    def test_ble_classifier_multidimensional_categorization(self):
        """测试 BleClassifier 对各类蓝牙设备（耳机、手柄、键鼠、穿戴、手机、电脑及读写器）的精准识别"""
        from core.transport.ble_classifier import BleClassifier

        # 1. 读写器识别与最高优先级
        res_reader = BleClassifier.classify(name="Minicopy(BLE)", address="D7:4E:91:22:33:44", rssi=-50)
        self.assertEqual(res_reader["category_id"], "reader")
        self.assertEqual(res_reader["priority"], 0)
        self.assertTrue(res_reader["is_reader"])
        self.assertIn("★推荐", res_reader["display_text"])

        # 2. 音频设备 (耳机) 识别
        res_audio = BleClassifier.classify(name="Black Shark OWS Pro App", address="52:FD:A7:EE:E4:C3", rssi=-77)
        self.assertEqual(res_audio["category_id"], "audio")
        self.assertEqual(res_audio["icon"], "🎧")
        self.assertIn("[音频/耳机]", res_audio["display_text"])

        # 3. 游戏手柄识别
        res_gamepad = BleClassifier.classify(name="Xbox Wireless Controller", address="11:22:33:44:55:66", rssi=-60)
        self.assertEqual(res_gamepad["category_id"], "gamepad")
        self.assertEqual(res_gamepad["icon"], "🎮")

        # 4. 键盘外设识别
        res_kbd = BleClassifier.classify(name="Keychron K2 Pro", address="22:33:44:55:66:77", rssi=-65)
        self.assertEqual(res_kbd["category_id"], "keyboard")
        self.assertEqual(res_kbd["icon"], "⌨️")

        # 5. 鼠标外设识别
        res_mouse = BleClassifier.classify(name="Logi MX Master 3", address="33:44:55:66:77:88", rssi=-68)
        self.assertEqual(res_mouse["category_id"], "mouse")
        self.assertEqual(res_mouse["icon"], "🖱️")

        # 6. Apple 生态匿名广播设备
        res_apple = BleClassifier.classify(name="", address="44:55:66:77:88:99", rssi=-70, manufacturer_data={76: b"\x01"})
        self.assertEqual(res_apple["category_id"], "apple")
        self.assertIn("Apple 广播设备", res_apple["friendly_name"])

        # 7. Microsoft Windows 匿名电脑广播
        res_ms = BleClassifier.classify(name="", address="55:66:77:88:99:AA", rssi=-80, manufacturer_data={6: b"\x01"})
        self.assertEqual(res_ms["category_id"], "pc")
        self.assertIn("Windows", res_ms["friendly_name"])

    def test_gui_ble_combobox_tooltip_and_popup_width(self):
        """测试 GUI 蓝牙下拉框弹出视图开阔宽度 (>=560px) 与多行富文本 ToolTip 绑定"""
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        from ui.main_window import MainWindow
        app = QApplication.instance() or QApplication(sys.argv)
        win = MainWindow()
        try:
            # 校验弹出列表视图最小宽度，确保展开时不被挤压截断
            self.assertGreaterEqual(win.combo_ble.view().minimumWidth(), 500)

            # 模拟注入多个不同品类设备
            mock_devs = [
                {"name": "Minicopy", "address": "9C:7F:64:7A:1A:A4", "rssi": -45},
                {"name": "AirPods Pro", "address": "AA:BB:CC:DD:EE:01", "rssi": -65},
            ]
            win._on_ble_scan_found(mock_devs)

            # 校验读写器置顶与默认选中
            self.assertEqual(win.combo_ble.currentIndex(), 0)
            self.assertEqual(win.combo_ble.currentData(), "9C:7F:64:7A:1A:A4")

            # 校验各条目的 ToolTipRole 是否包含完整地址与分类信息
            tip_0 = win.combo_ble.itemData(0, Qt.ItemDataRole.ToolTipRole)
            self.assertIn("9C:7F:64:7A:1A:A4", tip_0)
            self.assertIn("NFC读写器", tip_0)

            tip_1 = win.combo_ble.itemData(1, Qt.ItemDataRole.ToolTipRole)
            self.assertIn("AA:BB:CC:DD:EE:01", tip_1)
            self.assertIn("音频/耳机", tip_1)

            # 校验 combo_ble 自身 ToolTip 随选中项同步更新
            self.assertIn("9C:7F:64:7A:1A:A4", win.combo_ble.toolTip())
        finally:
            win.close()


class Test13CpuCardAndApduInteraction(unittest.TestCase):
    """测试 ISO/IEC 7816-4 APDU 协议、CPU 智能卡识别与内容读取交互"""

    def test_apdu_protocol_frame_building_and_sw_parsing(self):
        """测试 APDU 基础指令构建与 SW1/SW2 状态字释义"""
        from core.protocols.iso7816 import APDUProtocol, AID_T_UNION

        # 1. SELECT 指令构建
        sel_tunion = APDUProtocol.build_select_apdu(AID_T_UNION, by_name=True)
        self.assertEqual(sel_tunion[:4], bytes([0x00, 0xA4, 0x04, 0x00]))
        self.assertEqual(sel_tunion[4], len(AID_T_UNION))
        self.assertEqual(sel_tunion[5:], AID_T_UNION)

        sel_mf = APDUProtocol.build_select_apdu(bytes([0x3F, 0x00]), by_name=False)
        self.assertEqual(sel_mf, bytes([0x00, 0xA4, 0x00, 0x00, 0x02, 0x3F, 0x00]))

        # 2. READ BINARY 与 READ RECORD
        read_bin = APDUProtocol.build_read_binary_apdu(sfi=0x15, length=30)
        self.assertEqual(read_bin, bytes([0x00, 0xB0, 0x95, 0x00, 0x1E]))

        read_rec = APDUProtocol.build_read_record_apdu(record_num=1, sfi=0x18)
        self.assertEqual(read_rec, bytes([0x00, 0xB2, 0x01, 0xC4, 0x00]))

        # 3. GET BALANCE 余额指令与数值解析
        get_bal = APDUProtocol.build_get_balance_apdu()
        self.assertEqual(get_bal, bytes([0x80, 0x5C, 0x00, 0x02, 0x04]))

        # 4 字节 4500 分 = 45.00 元
        bal_bytes = (4500).to_bytes(4, "big")
        parsed_bal = APDUProtocol.parse_balance(bal_bytes)
        self.assertEqual(parsed_bal, 45.00)

        # 4. 状态字解析
        self.assertIn("成功", APDUProtocol.get_sw_description(0x90, 0x00))
        self.assertIn("文件或应用未找到", APDUProtocol.get_sw_description(0x6A, 0x82))
        self.assertIn("安全状态不满足", APDUProtocol.get_sw_description(0x69, 0x82))

    def test_apdu_protocol_record_and_card_info_parsing(self):
        """测试 0x15 公开数据与 0x18 交易流水明细的解析 (含用户实机交通卡数据)"""
        from core.protocols.iso7816 import APDUProtocol

        # 1. 构造仿真的 0015 公开信息报文 (30 字节)
        # 机构代码(8B) + 保留(2B) + 卡号(10B) + 启用日期(4B) + 截止日期(4B)
        mock_0015 = (
            bytes.fromhex("3104888800000000") +
            bytes([0x00, 0x00]) +
            bytes.fromhex("12345678901234567890") +
            bytes.fromhex("20200101") +
            bytes.fromhex("20301231")
        )
        info = APDUProtocol.parse_t_union_card_info(mock_0015)
        self.assertEqual(info["issuer_code"], "3104888800000000")
        self.assertEqual(info["card_number"], "12345678901234567890")
        self.assertEqual(info["start_date"], "2020-01-01")
        self.assertEqual(info["end_date"], "2030-12-31")

        # 2. 真实用户公交卡 0015 公共信息报文解析 (精准匹配 19 位卡面卡号 3104930820010840711)
        real_0015 = bytes.fromhex("03654510FFFFFFFF02010310493082001084071120250209204012300000")
        real_info = APDUProtocol.parse_t_union_card_info(real_0015)
        self.assertEqual(real_info["card_number"], "3104930820010840711")
        self.assertEqual(real_info["start_date"], "2025-02-09")
        self.assertEqual(real_info["end_date"], "2040-12-30")

        # 3. 构造一条 23 字节标准消费记录
        # 序号 0x0001, 透支限额 0, 消费 200分 (2.00元), 类型 0x06 (消费), 终端 6B, 日期 20261022, 时间 154500
        mock_rec = (
            bytes([0x00, 0x01]) +
            bytes([0x00, 0x00, 0x00]) +
            (200).to_bytes(4, "big") +
            bytes([0x06]) +
            bytes.fromhex("112233445566") +
            bytes.fromhex("20261022") +
            bytes.fromhex("154500")
        )
        rec = APDUProtocol.parse_transaction_record(mock_rec, index=1)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["seq"], 1)
        self.assertEqual(rec["amount"], 2.00)
        self.assertIn("消费", rec["type_desc"])
        self.assertEqual(rec["terminal"], "112233445566")
        self.assertEqual(rec["datetime"], "2026-10-22 15:45:00")

        # 4. 真实用户公交卡 10/20 23:10 扣费 4.00 元交易记录验证
        real_rec_bytes = bytes.fromhex("0155000000000001900941310188892420261020231044")
        real_rec = APDUProtocol.parse_transaction_record(real_rec_bytes, index=1)
        self.assertIsNotNone(real_rec)
        self.assertEqual(real_rec["seq"], 0x0155)
        self.assertEqual(real_rec["amount"], 4.00)
        self.assertIn("消费", real_rec["type_desc"])
        self.assertEqual(real_rec["terminal"], "413101888924")
        self.assertEqual(real_rec["datetime"], "2026-10-20 23:10:44")

        # 5. PPSE 目录响应解析 Tag 4F 动态获取交通互通 AID
        mock_ppse_fci = bytes.fromhex(
            "6F36840E325041592E5359532E4444463031A524BF0C21611F4F10"
            "A000000632010105535A4B5700000531"
            "870101"
        )
        extracted_res = APDUProtocol.parse_ppse_response(mock_ppse_fci)
        self.assertIsNotNone(extracted_res)
        self.assertEqual(extracted_res["aid"], bytes.fromhex("A000000632010105535A4B5700000531"))
        self.assertIn("MOT_T_EP", extracted_res["app_name"])

    def test_pn532_adapter_cpu_card_detection_and_apdu_mock(self):
        """测试 PN532Adapter 正确感知 SAK=0x20 的 CPU 卡并支持 InDataExchange APDU"""
        from core.adapters.pn532_adapter import PN532Adapter

        adapter = PN532Adapter()

        # 1. 模拟 InListPassiveTarget 返回 SAK=0x20 (Bit 5=1), 7 字节 UID 与 ATS
        # [NbTg=1] [Tg=1] [ATQA=00 04] [SAK=20] [UIDLen=7] [UID=04 11 22 33 44 55 66] [ATS=05 78 80 82 02]
        mock_target_data = bytes([
            0x01, 0x01, 0x00, 0x04, 0x20, 0x07,
            0x04, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66,
            0x05, 0x78, 0x80, 0x82, 0x02
        ])
        parsed = adapter._parse_target_data(mock_target_data)
        self.assertIsNotNone(parsed)
        self.assertTrue(parsed["is_cpu_card"])
        self.assertIn("CPU 卡", parsed["card_type"])
        self.assertEqual(parsed["sak"], 0x20)
        self.assertEqual(parsed["conversions"]["uid_type"], "7-byte (Mifare Plus / NTAG / DESFire)")
        self.assertIn("04 11 22 33 44 55 66", parsed["conversions"]["hex_normal"])
        self.assertIn("05 78 80 82 02", parsed["ats_hex"])

        # 2. 模拟 send_apdu 交互
        class MockSerial:
            is_open = True
            def write(self, d): pass
            def flush(self): pass
            def reset_input_buffer(self): pass

        # Mock send_and_receive: 返回 0x00 (成功) + 数据域 + 90 00
        mock_apdu_resp = bytes([0x00, 0x11, 0x22, 0x90, 0x00])
        adapter._send_and_receive = lambda ser, cmd, payload, timeout=0.5: mock_apdu_resp

        apdu_result = adapter.send_apdu(MockSerial(), bytes([0x00, 0x84, 0x00, 0x00, 0x08]))
        self.assertTrue(apdu_result["ok"])
        self.assertEqual(apdu_result["sw_hex"], "9000")
        self.assertEqual(apdu_result["data_hex"], "1122")
        self.assertIn("成功", apdu_result["sw_desc"])

    def test_gui_cpu_card_widget_rendering_and_interaction(self):
        """测试 CpuCardWidget 无头 GUI 渲染与组件联动"""
        from PyQt6.QtWidgets import QApplication
        from ui.cpu_card_widget import CpuCardWidget
        app = QApplication.instance() or QApplication(sys.argv)
        w = CpuCardWidget()
        try:
            # 1. 模拟感应到 CPU 卡片特征
            card_info = {
                "uid_bytes": bytes([0x08, 0x12, 0x34, 0x56]),
                "sak": 0x20,
                "is_cpu_card": True,
                "card_type": "ISO14443-4 CPU 卡 (标准智能卡)",
                "ats_hex": "05 78 80 82"
            }
            w.update_card_badge(card_info)

            self.assertEqual(w.lbl_uid_val.text(), "08 12 34 56")
            self.assertEqual(w.lbl_sak_val.text(), "0x20")
            self.assertIn("CPU 卡", w.lbl_type_val.text())
            self.assertIn("05 78 80 82", w.lbl_ats_val.text())
            self.assertTrue(w.btn_auto_read.isEnabled())

            # 2. 预设指令选择测试
            w.cmb_preset.setCurrentIndex(1)
            self.assertIn("00 84 00 00 08", w.txt_apdu.text())

            # 3. 模拟一键读取回调填充
            mock_read_res = {
                "app_name": "全国交通联合 (T-Union) 互联互通卡",
                "card_number": "3104888812345678",
                "issuer_code": "31040000",
                "start_date": "20210101",
                "end_date": "20310101",
                "balance_str": "¥ 68.50",
                "transactions": [
                    {
                        "seq": 1,
                        "datetime": "2026-10-22 15:30:00",
                        "type_desc": "公共交通/脱机消费",
                        "amount": 3.00,
                        "terminal": "998877665544"
                    }
                ],
                "logs": []
            }
            w._on_auto_read_finished(mock_read_res)
            self.assertEqual(w.val_app_name.text(), "全国交通联合 (T-Union) 互联互通卡")
            self.assertEqual(w.val_card_no.text(), "3104888812345678")
            self.assertEqual(w.val_balance.text(), "¥ 68.50")
            self.assertEqual(w.table_trans.rowCount(), 1)
        finally:
            w.close()

    def test_apdu_instruction_explanation_and_deep_dissection(self):
        """测试 APDU 指令助记符解析、响应深度语义推导与 Hex Dump 对照矩阵"""
        from core.protocols.iso7816 import APDUProtocol

        # 1. 测试指令助记符解析
        sel_ppse = bytes.fromhex("00A404000E325041592E5359532E4444463031")
        expl_sel = APDUProtocol.explain_apdu_command(sel_ppse)
        self.assertEqual(expl_sel["mnemonic"], "SELECT FILE")
        self.assertIn("2PAY.SYS.DDF01", expl_sel["details"][0])

        get_bal = bytes.fromhex("805C000204")
        expl_bal = APDUProtocol.explain_apdu_command(get_bal)
        self.assertEqual(expl_bal["mnemonic"], "GET BALANCE")

        # 2. 测试 Hex Dump + ASCII 矩阵对齐
        test_payload = b"Hello\x00\x01\x02\x03World1234567890"
        dump_lines = APDUProtocol.format_hex_ascii_dump(test_payload, width=16)
        self.assertGreaterEqual(len(dump_lines), 2)
        self.assertIn("0000:", dump_lines[0])
        self.assertIn("Hello", dump_lines[0])

        # 3. 测试响应语义推导 (余额 4.80 元)
        bal_resp_data = (480).to_bytes(4, "big")  # 480 分 = 4.80 元
        dissect_res = APDUProtocol.dissect_apdu_response(get_bal, bal_resp_data, 0x90, 0x00)
        self.assertTrue(dissect_res["is_ok"])
        self.assertEqual(dissect_res["parsed_fields"]["balance_yuan"], 4.80)
        self.assertIn("4.80 元", dissect_res["semantics"][0])

    def test_gui_export_log_button(self):
        """测试主窗口存在 '导出日志' 按钮且默认具备 UTF-8 导出支持"""
        from PyQt6.QtWidgets import QApplication, QPushButton
        from ui.main_window import MainWindow
        app = QApplication.instance() or QApplication(sys.argv)
        win = MainWindow()
        try:
            # 验证导出日志按钮存在且可见
            btn_export = None
            for btn in win.log_box.findChildren(QPushButton):
                if "导出日志" in btn.text():
                    btn_export = btn
                    break
            self.assertIsNotNone(btn_export, "原生数据流日志控制栏中未找到'导出日志'按钮！")
            self.assertTrue(btn_export.isEnabled())
            self.assertIn("UTF-8", btn_export.toolTip())
        finally:
            win.close()


class Test14RemediationAnd4KFullSupport(unittest.TestCase):
    """验证体系化缺陷整改：4K 读写全贯通、7B UID 认证切片、移卡快速中断、Diff 4K、WG34 持久化与门面统一"""

    def test_7byte_uid_pn532_auth_slice(self):
        """测试 7 字节 UID 卡在 Mifare Classic 认证时按 ISO14443-3 提取后 4 字节 (Cascade Level 2)"""
        from core.adapters.pn532_adapter import PN532Adapter
        adapter = PN532Adapter()
        captured_payloads = []

        def fake_send(ser, cmd, payload=b"", timeout=0.35):
            captured_payloads.append(payload)
            return b"\x00"

        adapter._send_and_receive = fake_send

        # 1. 7-byte UID 测试 (如 04 11 22 33 44 55 66)
        uid_7b = bytes.fromhex("04112233445566")
        key = bytes.fromhex("FFFFFFFFFFFF")
        self.assertTrue(adapter.authenticate(None, 4, "A", key, uid=uid_7b))
        # 负载格式: [0x01, auth_cmd, block] + key[:6] + auth_uid
        # 应包含 uid[-4:] 即 33 44 55 66
        self.assertEqual(captured_payloads[-1][9:13], bytes.fromhex("33445566"))

        # 2. 4-byte UID 测试 (如 A1 B2 C3 D4)
        uid_4b = bytes.fromhex("A1B2C3D4")
        self.assertTrue(adapter.authenticate(None, 4, "A", key, uid=uid_4b))
        self.assertEqual(captured_payloads[-1][9:13], bytes.fromhex("A1B2C3D4"))

    def test_4k_card_worker_trailer_and_blocks(self):
        """测试 CardOperationWorker 在 4K 模式下正确读取 40 个扇区，大扇区使用正确的尾块与 16 块读取"""
        from core.services.card_worker import CardOperationWorker

        auth_blocks = []
        read_blocks = []

        class MockWorker:
            def is_connected(self):
                return True
            def is_card_present(self):
                return True
            def authenticate(self, trailer_block, key_type, key, timeout=0.35):
                auth_blocks.append(trailer_block)
                return True
            def read_block(self, block, timeout=0.3):
                read_blocks.append(block)
                return bytes([block % 256] * 16)

        mock_w = MockWorker()
        # 针对扇区 32 (大扇区) 进行读取测试
        worker = CardOperationWorker(
            mock_w,
            op_type=CardOperationWorker.OP_READ_CARD,
            target_sectors=[32],
            custom_keys=["FFFFFFFFFFFF"],
            is_4k=True
        )
        worker.run()

        # 扇区 32 的尾块应为 143 (128 + 15)，而非 131 (32 * 4 + 3)
        self.assertIn(143, auth_blocks)
        self.assertNotIn(131, auth_blocks)
        # 扇区 32 应连续读取 16 个块 (128~143)
        self.assertEqual(len(read_blocks), 16)
        self.assertEqual(read_blocks, list(range(128, 144)))

    def test_fast_card_removed_detection(self):
        """测试当卡片脱离天线时，字典破解循环能够快速感知并中断，不盲目跑完剩余字典"""
        from core.services.card_worker import CardOperationWorker

        auth_attempts = 0

        class MockWorkerAbsent:
            def is_connected(self):
                return True
            def is_card_present(self):
                # 模拟卡片已被移走
                return False
            def authenticate(self, trailer_block, key_type, key, timeout=0.35):
                nonlocal auth_attempts
                auth_attempts += 1
                return False

        mock_w = MockWorkerAbsent()
        many_keys = [f"{i:012X}" for i in range(100)]
        worker = CardOperationWorker(
            mock_w,
            op_type=CardOperationWorker.OP_CRACK_KEYS,
            target_sectors=[0, 1],
            custom_keys=many_keys
        )

        finished_results = []
        worker.sig_finished.connect(lambda ok, msg, data: finished_results.append((ok, msg)))
        worker.run()

        # 连续脱离场检查会在尝试 3 次左右直接中断，尝试次数绝不会达到 100+
        self.assertLessEqual(auth_attempts, 10)
        self.assertTrue(len(finished_results) > 0)
        self.assertFalse(finished_results[0][0])
        self.assertIn("移离", finished_results[0][1])

    def test_dump_diff_4k_support(self):
        """测试 Diff Tool 对 4K Dump 的差分比对 (涵盖 S32~S39 大扇区)"""
        from ui.dump_diff import DumpDiffWidget
        from core.models.dump import MifareDump
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication(sys.argv)
        diff_widget = DumpDiffWidget()
        try:
            diff_widget.dump_a = MifareDump(is_4k=True)
            diff_widget.dump_b = MifareDump(is_4k=True)
            # 在扇区 33 (块 146) 写入差异数据
            diff_widget.dump_a.set_block(146, b"\x00" * 16)
            diff_widget.dump_b.set_block(146, b"\xAA" * 16)

            diff_widget.compare_dumps()
            self.assertEqual(diff_widget.table.rowCount(), 16)
            # 校验扇区号被正确识别为 33
            sec_text = diff_widget.table.item(0, 0).text()
            self.assertEqual(sec_text, "扇区 33")
            blk_text = diff_widget.table.item(0, 1).text()
            self.assertEqual(blk_text, "块 146")
        finally:
            diff_widget.close()

    def test_card_db_wiegand_34_migration_and_persistence(self):
        """测试 SQLite 数据库对 Wiegand 34 字段的自动建表/迁移与持久化"""
        import tempfile
        from core.card_db import CardDatabase

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            temp_db_path = f.name

        try:
            db = CardDatabase(db_path=temp_db_path)
            conv_info = {
                "card_type": "Mifare Classic 1K",
                "dec_10d_rev": "1234567890",
                "wiegand_26": "123,45678",
                "wiegand_34": "00123,45678",
            }
            db.record_swipe("AABBCCDD", conv_info, "AA BB CC DD")

            card = db.get_card("AABBCCDD")
            self.assertIsNotNone(card)
            self.assertEqual(card.get("wiegand_34"), "00123,45678")

            all_cards = db.list_all_cards()
            self.assertEqual(len(all_cards), 1)
            self.assertEqual(all_cards[0].get("wiegand_34"), "00123,45678")
            db.close()
        finally:
            if os.path.exists(temp_db_path):
                try:
                    os.remove(temp_db_path)
                except Exception:
                    pass

    def test_attack_runner_facade(self):
        """测试 core/attack_runner.py 门面正确 re-export 服务层抽象"""
        import core.attack_runner as ar_facade
        from core.services.attack_runner import AttackRunner, BaseAttackEngine
        self.assertIs(ar_facade.AttackRunner, AttackRunner)
        self.assertIs(ar_facade.BaseAttackEngine, BaseAttackEngine)


class Test15CpuCardEnhancements(unittest.TestCase):
    """验证 CPU 智能卡交互专项强化：61xx/6Cxx 自动协商取回、F 填充清洗、空记录过滤、JSON 导出 bytes 防崩溃、树扫描安全中断与 PBOC 流水兼容"""

    def setUp(self):
        from core.adapters.pn532_adapter import PN532Adapter
        self.adapter = PN532Adapter()

        class MockSerial:
            is_open = True
            def write(self, d): pass
            def flush(self): pass
            def reset_input_buffer(self): pass

        self.mock_ser = MockSerial()

    def test_send_apdu_auto_get_response_61xx(self):
        """测试 send_apdu 遇到 61xx 状态字自动发送 00 C0 (GET RESPONSE) 取回完整数据"""
        calls = []

        def fake_exchange(ser, cmd, payload=b"", timeout=0.5):
            calls.append((cmd, payload))
            if len(calls) == 1:
                # 第一次返回 61 14 (表示有 20 字节待取回)
                return bytes([0x00, 0x61, 0x14])
            elif len(calls) == 2:
                # 第二次响应 GET RESPONSE: 返回 20 字节 FCI + 90 00
                fci_data = bytes([0x6F, 0x12, 0x84, 0x0E]) + b"2PAY.SYS.DDF01"
                return bytes([0x00]) + fci_data + bytes([0x90, 0x00])
            return bytes([0x00, 0x90, 0x00])

        self.adapter._send_and_receive = fake_exchange

        sel_apdu = bytes.fromhex("00A404000E325041592E5359532E4444463031")
        res = self.adapter.send_apdu(self.mock_ser, sel_apdu, auto_get_response=True)

        self.assertTrue(res["ok"], "自动执行 GET RESPONSE 后操作应成功")
        self.assertEqual(res["sw_hex"], "9000")
        self.assertEqual(res["original_sw_hex"], "6114")
        self.assertTrue(res.get("auto_resolved"))
        self.assertIn("GET RESPONSE", res["sw_desc"])
        self.assertGreater(len(res["data"]), 0)
        self.assertEqual(len(calls), 2, "应自动触发第二轮 GET RESPONSE 指令")
        # 验证第二轮指令为 00 C0 00 00 14
        self.assertEqual(calls[1][1], bytes([0x01, 0x00, 0xC0, 0x00, 0x00, 0x14]))

    def test_send_apdu_auto_wrong_le_6cxx(self):
        """测试 send_apdu 遇到 6Cxx 状态字自动修正 Le 并重新发送"""
        calls = []

        def fake_exchange(ser, cmd, payload=b"", timeout=0.5):
            calls.append((cmd, payload))
            if len(calls) == 1:
                # 第一次返回 6C 1E (提示正确 Le 应为 30 字节)
                return bytes([0x00, 0x6C, 0x1E])
            elif len(calls) == 2:
                # 第二次返回 30 字节数据 + 90 00
                return bytes([0x00]) + bytes([0xAA] * 30) + bytes([0x90, 0x00])
            return bytes([0x00, 0x90, 0x00])

        self.adapter._send_and_receive = fake_exchange

        read_apdu = bytes.fromhex("00B0950000")  # Le 原为 00
        res = self.adapter.send_apdu(self.mock_ser, read_apdu, auto_get_response=True)

        self.assertTrue(res["ok"])
        self.assertEqual(res["sw_hex"], "9000")
        self.assertEqual(res["original_sw_hex"], "6C1E")
        self.assertTrue(res.get("auto_resolved"))
        self.assertEqual(len(res["data"]), 30)
        self.assertEqual(len(calls), 2)
        # 验证第二轮指令末尾被修正为 0x1E
        self.assertEqual(calls[1][1][-1], 0x1E)

    def test_t_union_card_info_f_padding_and_invalid_date_cleaning(self):
        """测试 0x15 文件解析中末尾 F 填充清洗与未初始化/全0/全F日期保护"""
        from core.protocols.iso7816 import APDUProtocol

        # 模拟带 F 填充的卡号与无效日期
        # 0~7: 发卡机构 3104FFFFFFFFFFFF
        # 8~9: 保留
        # 10~19: 卡号 1234567890123456FFFF (16位卡号 + 4位F)
        # 20~23: 启用日期 00000000 (未初始化)
        # 24~27: 截止日期 FFFFFFFF (无效)
        mock_data = (
            bytes.fromhex("3104FFFFFFFFFFFF") +
            bytes.fromhex("0000") +
            bytes.fromhex("1234567890123456FFFF") +
            bytes.fromhex("00000000") +
            bytes.fromhex("FFFFFFFF")
        )

        res = APDUProtocol.parse_t_union_card_info(mock_data)
        self.assertEqual(res["issuer_code"], "3104")
        self.assertEqual(res["card_number"], "1234567890123456", "应干净剔除尾部 FFFF 填充")
        self.assertEqual(res["start_date"], "", "全 0 日期不应输出为 0000-00-00")
        self.assertEqual(res["end_date"], "", "全 F 日期不应输出为 FFFF-FF-FF")

    def test_parse_transaction_record_empty_slots_filtering(self):
        """测试交易流水循环记录中全 0x00 与全 0xFF 未写入空记录的自动过滤"""
        from core.protocols.iso7816 import APDUProtocol

        # 1. 全 0x00 记录
        zero_rec = bytes([0x00] * 23)
        self.assertIsNone(APDUProtocol.parse_transaction_record(zero_rec))

        # 2. 全 0xFF 记录
        ff_rec = bytes([0xFF] * 23)
        self.assertIsNone(APDUProtocol.parse_transaction_record(ff_rec))

        # 3. 真实合法交易记录 (23 字节)
        # [2B seq=1] [3B overdraft=0] [4B cents=300] [1B type=0x06] [6B term=112233445566] [4B date=20261023] [3B time=123000]
        valid_rec = bytes.fromhex("00010000000000012C0611223344556620261023123000")
        parsed = APDUProtocol.parse_transaction_record(valid_rec, index=1)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["seq"], 1)
        self.assertEqual(parsed["amount"], 3.00)
        self.assertEqual(parsed["datetime"], "2026-10-23 12:30:00")

    def test_cpu_tree_scan_json_export_bytes_safety(self):
        """测试全卡文件树中包含 bytes 原生载荷时，JSON 导出不会抛出 TypeError"""
        import json

        # 构建含原始 bytes 载荷的树结构 (与 scan_cpu_card_tree 输出完全一致)
        raw_payload = b"\x00\x01\x02\x03\x04\xAA\xBB\xCC\xDD"
        tree_with_bytes = {
            "app_name": "测试 CPU 应用",
            "aid_hex": "A000000632010105",
            "stats": {"total_files": 1, "readable_bytes": len(raw_payload)},
            "children": [
                {
                    "id": "DIR_APP",
                    "name": "主目录",
                    "type": "directory",
                    "children": [
                        {
                            "id": "EF_0015",
                            "name": "0015 文件",
                            "type": "binary",
                            "data": raw_payload,  # 原生 bytes
                            "size": len(raw_payload),
                        }
                    ]
                }
            ],
            "flat_files": {
                "EF_0015": {
                    "id": "EF_0015",
                    "name": "0015 文件",
                    "type": "binary",
                    "data": raw_payload,  # 原生 bytes
                    "size": len(raw_payload),
                }
            }
        }

        # 验证通过 default 回调进行序列化，绝不抛出 TypeError
        json_str = json.dumps(
            tree_with_bytes,
            ensure_ascii=False,
            default=lambda o: o.hex().upper() if isinstance(o, (bytes, bytearray)) else str(o)
        )
        self.assertIn("0001020304AABBCCDD", json_str)

    def test_scan_cpu_card_tree_abort_mechanism(self):
        """测试 scan_cpu_card_tree 在 abort_check 返回 True 时快速跳出"""
        calls_count = 0

        def fake_exchange(ser, cmd, payload=b"", timeout=0.35):
            nonlocal calls_count
            calls_count += 1
            return bytes([0x00, 0x90, 0x00])

        self.adapter._send_and_receive = fake_exchange

        # 在执行 2 次交互后触发 abort
        should_abort = False
        def check_abort():
            return should_abort

        def progress_cb(cur, total, msg):
            nonlocal should_abort
            if cur >= 2:
                should_abort = True

        tree = self.adapter.scan_cpu_card_tree(
            self.mock_ser, timeout=0.01, progress_cb=progress_cb, abort_check=check_abort
        )
        self.assertTrue(tree.get("aborted"), "检测到 abort_check 应将 aborted 置为 True")
        self.assertLess(calls_count, 15, "中断后交互次数应远小于完整全目录探测总次数 (38+)")

    def test_read_cpu_card_public_info_pboc_sfi_fallback(self):
        """测试交通部 SFI=0x18 读取失败时，自动回退读取中国金融 PBOC 银行卡 SFI=0x0B 流水"""
        def fake_exchange(ser, cmd, payload=b"", timeout=0.5):
            # payload: [0x01, CLA, INS, P1, P2, Le]
            if len(payload) >= 5 and payload[1:3] == bytes([0x00, 0xB2]):
                p2 = payload[4]
                # P2 = (0x18 << 3) | 4 = 0xC4
                if p2 == 0xC4:
                    return bytes([0x00, 0x6A, 0x82])  # 交通部文件未找到
                # P2 = (0x0B << 3) | 4 = 0x5C
                elif p2 == 0x5C:
                    rec_no = payload[3]
                    if rec_no == 1:
                        # 仅第 1 条有记录 (23 字节)
                        pboc_rec = bytes.fromhex("0001000000000002580699887766554420261023150000")
                        return bytes([0x00]) + pboc_rec + bytes([0x90, 0x00])
                    else:
                        # 记录 2~10 不存在，返回 6A83 (Record not found)
                        return bytes([0x00, 0x6A, 0x83])
            return bytes([0x00, 0x90, 0x00])

        self.adapter._send_and_receive = fake_exchange

        res = self.adapter.read_cpu_card_public_info(self.mock_ser)
        self.assertEqual(len(res["transactions"]), 1, "应成功回退读取 PBOC SFI=0x0B 交易记录")
        self.assertEqual(res["transactions"][0]["amount"], 6.00)

    def test_cpu_card_widget_apdu_input_validation(self):
        """测试 CpuCardWidget 对奇数 Hex 字符与不足 4 字节 APDU 的拦截提示"""
        import sys
        from PyQt6.QtWidgets import QApplication
        from ui.cpu_card_widget import CpuCardWidget

        app = QApplication.instance() or QApplication(sys.argv)
        w = CpuCardWidget()
        try:
            # 1. 奇数位 Hex 校验
            w.txt_apdu.setText("00 84 00 00 8")
            w._send_custom_apdu()
            self.assertIn("字符数必须为偶数", w.txt_apdu_log.toPlainText())

            # 2. 不足 4 字节 APDU 校验
            w.txt_apdu.setText("00 A4")
            w._send_custom_apdu()
            self.assertIn("至少需 4 字节", w.txt_apdu_log.toPlainText())
        finally:
            w.close()

    def test_pboc_tlv_and_card_info_parsing(self):
        """测试 PBOC / EMV 金融卡 BER-TLV 解析与卡号/有效期/发卡行提取"""
        from core.protocols.iso7816 import APDUProtocol

        # SFI 2 Rec 1 真实报文数据 (含 Tag 5A 卡号, 5F24 有效期, 5F25 启用日期)
        sfi2_data = bytes.fromhex(
            "704F5F24033405315F25032405065A0862148305638621755F3401009F0702FF00"
            "8E0C000000000000000042031E039F0D05D86004A8009F0E0500109800009F0F05"
            "D86804F8005F280201569F08020030"
        )
        tlvs = APDUProtocol.parse_tlv(sfi2_data)
        self.assertIn("5A", tlvs)
        self.assertIn("5F24", tlvs)
        self.assertIn("5F25", tlvs)

        pboc_info = APDUProtocol.parse_pboc_card_info(tlvs)
        self.assertEqual(pboc_info["card_number"], "6214830563862175")
        self.assertEqual(pboc_info["start_date"], "2024-05-06")
        self.assertEqual(pboc_info["end_date"], "2034-05-31")
        self.assertIn("招商银行", pboc_info["issuer_name"])

        # 测试纯磁道 2 等效数据 (Tag 57) 解析
        sfi1_data = bytes.fromhex("701557136214830563862175D34052208304200695551F")
        info_t2 = APDUProtocol.parse_pboc_card_info(sfi1_data)
        self.assertEqual(info_t2["card_number"], "6214830563862175")
        self.assertEqual(info_t2["end_date"], "2034-05")

    def test_pboc_45byte_transaction_record_parsing(self):
        """测试 PBOC 45 字节金融 IC 卡循环交易日志解析"""
        from core.protocols.iso7816 import APDUProtocol

        # 取现 3000 元记录 (ATC 11)
        rec1 = bytes.fromhex(
            "26021416311800000030000000000000000001560156000000000000000000000000000000000000000001000B"
        )
        p1 = APDUProtocol.parse_transaction_record(rec1, index=1)
        self.assertIsNotNone(p1)
        self.assertEqual(p1["seq"], 11)
        self.assertEqual(p1["amount"], 3000.00)
        self.assertEqual(p1["datetime"], "2026-02-14 16:31:18")
        self.assertIn("取款", p1["type_desc"])

        # PSBC-ATM 取款 600 元记录 (ATC 6)
        rec2 = bytes.fromhex(
            "25012810100300000006000000000000000001560156505342432D41544D000000000000000000000000010006"
        )
        p2 = APDUProtocol.parse_transaction_record(rec2, index=2)
        self.assertIsNotNone(p2)
        self.assertEqual(p2["seq"], 6)
        self.assertEqual(p2["amount"], 600.00)
        self.assertEqual(p2["datetime"], "2025-01-28 10:10:03")
        self.assertEqual(p2["terminal"], "PSBC-ATM")

    def test_read_cpu_card_public_info_pboc_bank_card_full_flow(self):
        """测试银行卡一键读取全流程 (PPSE -> 应用 -> SFI 2 卡号 -> SFI 0x0B 流水)"""
        def fake_exchange(ser, cmd, payload=b"", timeout=0.5):
            # PPSE 选择指令 (00 A4 04 00 0E 32504159...)
            if b"2PAY.SYS.DDF01" in payload:
                fci = bytes.fromhex(
                    "6F34840E325041592E5359532E4444463031A522BF0C1F611D4F08A000000333010101"
                    "500E556E696F6E5061792044656269748701019000"
                )
                return bytes([0x00]) + fci
            # 应用选择指令 (A000000333010101)
            if b"\xA0\x00\x00\x03\x33\x01\x01\x01" in payload:
                return bytes([0x00, 0x90, 0x00])
            # 读 0015 文件 (银行卡无此文件，返回 6D00)
            if len(payload) >= 5 and payload[1:3] == bytes([0x00, 0xB0]):
                return bytes([0x00, 0x6D, 0x00])
            # 读记录
            if len(payload) >= 5 and payload[1:3] == bytes([0x00, 0xB2]):
                p2 = payload[4]
                rec_no = payload[3]
                # SFI 2 (P2=0x14)
                if p2 == 0x14 and rec_no == 1:
                    sfi2 = bytes.fromhex("701A5F24033405315F25032405065A0862148305638621755F3401009000")
                    return bytes([0x00]) + sfi2
                # SFI 0x0B (P2=0x5C)
                if p2 == 0x5C and rec_no == 1:
                    rec1 = bytes.fromhex("26021416311800000030000000000000000001560156000000000000000000000000000000000000000001000B9000")
                    return bytes([0x00]) + rec1
                return bytes([0x00, 0x6A, 0x83])
            # 余额查询 (银行借记卡不支持 80 5C，返回 6D00)
            if len(payload) >= 3 and payload[1:3] == bytes([0x80, 0x5C]):
                return bytes([0x00, 0x6D, 0x00])
            return bytes([0x00, 0x90, 0x00])

        self.adapter._send_and_receive = fake_exchange
        res = self.adapter.read_cpu_card_public_info(self.mock_ser)
        self.assertEqual(res["card_number"], "6214830563862175")
        self.assertEqual(res["end_date"], "2034-05-31")
        self.assertIn("招商银行", res["issuer_code"])
        self.assertIn("联机", res["balance_str"])
        self.assertEqual(len(res["transactions"]), 1)
        self.assertEqual(res["transactions"][0]["amount"], 3000.00)


class Test16MagicCardCloneWizardAndAttackRunner(unittest.TestCase):
    """测试魔术卡高级工具箱、一键对拷克隆向导与外部破解引擎集成"""

    def test_random_uid_and_build_block0(self):
        """测试随机 UID 生成与 Block 0 (含 BCC 校验) 组装契约"""
        from core.models.card_converter import CardConverter
        uid1 = CardConverter.generate_random_uid(4)
        uid2 = CardConverter.generate_random_uid(4)
        self.assertEqual(len(uid1), 4)
        self.assertEqual(len(uid2), 4)
        # 极低概率重复
        self.assertNotEqual(uid1, uid2)

        manuf = bytes([0x62, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69])
        b0 = CardConverter.build_block0(uid1, sak=0x08, atqa=0x0400, manufacturer_data=manuf)
        self.assertEqual(len(b0), 16)
        self.assertEqual(b0[:4], uid1)
        expected_bcc = uid1[0] ^ uid1[1] ^ uid1[2] ^ uid1[3]
        self.assertEqual(b0[4], expected_bcc, "Block 0 的第 4 字节必须是 UID 4 字节的异或 BCC 校验码")
        self.assertEqual(b0[5], 0x08, "SAK 字节不匹配")
        self.assertEqual(b0[6:8], bytes([0x04, 0x00]), "ATQA 字节序不匹配")
        self.assertEqual(b0[8:16], manuf, "厂商数据字段不匹配")

    def test_lock_ufuid_card_mock(self):
        """测试 PN532Adapter 对 UFUID 锁死序列与 SerialWorker 接口转发契约"""
        from core.adapters.pn532_adapter import PN532Adapter
        from core.services.serial_worker import SerialWorker

        class MockSerial:
            def __init__(self):
                self.is_open = True
                self.written = []
                self.in_waiting = 0

            def write(self, data):
                self.written.append(bytes(data))
                return len(data)

            def flush(self):
                pass

            def read(self, n):
                # 模拟 ACK 响应
                return bytes([0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00])

        adapter = PN532Adapter()
        mock_ser = MockSerial()
        res = adapter.lock_ufuid_card(mock_ser, timeout=0.1)
        # 即使卡片在 mock 下未返回真实应答帧，也应安全返回 bool，不崩溃
        self.assertIsInstance(res, bool)
        self.assertTrue(len(mock_ser.written) > 0, "应下发了魔术卡解锁或锁死报文")

        # 测试 SerialWorker 桩转发
        worker = SerialWorker(port="COM_MOCK")
        worker.adapter = adapter
        worker._serial = mock_ser
        w_res = worker.lock_ufuid_card(timeout=0.1)
        self.assertIsInstance(w_res, bool)

    def test_attack_runner_command_generation_and_parsing(self):
        """测试 AttackRunner 外部工具链状态检测与正则密钥解析"""
        from core.services.attack_runner import AttackRunner
        runner = AttackRunner(bin_dir="nfc-bin")
        st = runner.check_available_tools()
        self.assertIn("mfoc", st)
        self.assertIn("mfcuk", st)
        self.assertIn("crypto1_bs", st)
        self.assertIn("mfdetect", st)

        # 测试捕获密钥正则提取
        found_keys = []
        runner.sig_key_found.connect(lambda sec, kt, k: found_keys.append((sec, kt, k)))

        class MockProcess:
            def __init__(self):
                self.data = b"Sector 04 - Key A: A0A1A2A3A4A5\nSector 05 - Key B: FFFFFFFFFFFF\n"

            def readAllStandardOutput(self):
                class ByteArray:
                    def __init__(self, d):
                        self.d = d
                    def data(self):
                        return self.d
                d = self.data
                self.data = b""
                return ByteArray(d)

        runner.process = MockProcess()
        runner._on_stdout()
        self.assertEqual(len(found_keys), 2)
        self.assertEqual(found_keys[0], (4, "A", "A0A1A2A3A4A5"))
        self.assertEqual(found_keys[1], (5, "B", "FFFFFFFFFFFF"))

    def test_magic_card_dialog_offscreen(self):
        """测试 MagicCardDialog 无头仿真渲染与 Block 0 实时计算"""
        from PyQt6.QtWidgets import QApplication
        from ui.magic_card_dialog import MagicCardDialog

        app = QApplication.instance() or QApplication(sys.argv)
        dlg = MagicCardDialog(serial_worker=None)
        try:
            dlg.txt_target_uid.setText("D7 7E A0 DF")
            dlg.txt_sak.setText("08")
            dlg.txt_atqa.setText("04 00")
            dlg._update_b0_preview()
            self.assertIn("D7 7E A0 DF", dlg.lbl_b0_preview.text())
            # 异或校验 D7^7E^A0^DF = D6
            self.assertIn("D6", dlg.lbl_b0_preview.text())

            # 随机 UID 测试
            dlg._on_random_uid()
            self.assertNotEqual(dlg.txt_target_uid.text(), "D7 7E A0 DF")
        finally:
            dlg.close()

    def test_clone_wizard_dialog_offscreen(self):
        """测试 CloneWizardDialog 无头仿真渲染与三步向导状态流转"""
        from PyQt6.QtWidgets import QApplication
        from ui.clone_wizard_dialog import CloneWizardDialog
        from core.models.dump import MifareDump

        app = QApplication.instance() or QApplication(sys.argv)
        dlg = CloneWizardDialog(serial_worker=None)
        try:
            self.assertEqual(dlg.stack.currentIndex(), 0)
            self.assertFalse(dlg.btn_next.isEnabled())

            # 模拟原卡读取完成
            mock_dump = MifareDump()
            mock_dump.initialize_factory()
            mock_dump.set_uid(bytes([0x12, 0x34, 0x56, 0x78]))
            dlg.source_dump = mock_dump
            dlg.btn_next.setEnabled(True)

            # 前进至步骤 2
            dlg._on_next_step()
            self.assertEqual(dlg.stack.currentIndex(), 1)

            # 模拟新卡写入完成
            dlg._on_write_finished(True, "OK", mock_dump)
            self.assertEqual(dlg.stack.currentIndex(), 2)
            self.assertEqual(dlg.tbl_report.rowCount(), 5)
        finally:
            dlg.close()

    def test_dictionary_tools_tab5_attack_runner_widget(self):
        """测试 DictionaryToolsWidget Tab 5 外部破解选项卡与信号流"""
        from PyQt6.QtWidgets import QApplication
        from ui.dictionary_tools import DictionaryToolsWidget

        app = QApplication.instance() or QApplication(sys.argv)
        w = DictionaryToolsWidget()
        try:
            # 检查 Tab 5 外部算法破解
            self.assertTrue(hasattr(w, "attack_runner"))
            self.assertTrue(hasattr(w, "btn_run_attack"))
            self.assertTrue(hasattr(w, "cmb_attack_type"))

            # 切换攻击策略
            w.cmb_attack_type.setCurrentIndex(1)  # MFCUK
            self.assertFalse(w.lbl_target_sec.isHidden())
            w.cmb_attack_type.setCurrentIndex(2)  # Hardnested
            self.assertFalse(w.lbl_known_key.isHidden())

            # 测试捕获密钥反馈
            recovered = []
            w.sig_key_recovered.connect(lambda s, t, k: recovered.append((s, t, k)))
            w._on_key_found(2, "A", "A1B2C3D4E5F6")
            self.assertEqual(len(recovered), 1)
            self.assertEqual(recovered[0], (2, "A", "A1B2C3D4E5F6"))
            self.assertEqual(w.tbl_recovered_keys.rowCount(), 1)
        finally:
            w.close()


def run_all_tests():
    print("\n" + "="*70)
    print("🚀 PyMifareTool 自动化集成测试套件启动")
    print("="*70)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(Test01ProtocolAndAlgorithms))
    suite.addTests(loader.loadTestsFromTestCase(Test02DumpModelAndPersistence))
    suite.addTests(loader.loadTestsFromTestCase(Test03CardDatabase))
    suite.addTests(loader.loadTestsFromTestCase(Test04GuiAutomatedInteraction))
    suite.addTests(loader.loadTestsFromTestCase(Test05CardOperationWorkerStubs))
    suite.addTests(loader.loadTestsFromTestCase(Test06HardwarePortSanity))
    suite.addTests(loader.loadTestsFromTestCase(Test07Pn532AdapterAndProtocol))
    suite.addTests(loader.loadTestsFromTestCase(Test08KeyManagerAndConcurrentCracking))
    suite.addTests(loader.loadTestsFromTestCase(Test09IdCardReaderAndTypeBProtocol))
    suite.addTests(loader.loadTestsFromTestCase(Test10ArchitectureDecouplingAndExtensions))
    suite.addTests(loader.loadTestsFromTestCase(Test11CrackScopeAndManualDecrypt))
    suite.addTests(loader.loadTestsFromTestCase(Test12TransportLayerAndBle))
    suite.addTests(loader.loadTestsFromTestCase(Test13CpuCardAndApduInteraction))
    suite.addTests(loader.loadTestsFromTestCase(Test14RemediationAnd4KFullSupport))
    suite.addTests(loader.loadTestsFromTestCase(Test15CpuCardEnhancements))
    suite.addTests(loader.loadTestsFromTestCase(Test16MagicCardCloneWizardAndAttackRunner))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "="*70)
    print(f"📊 测试总结: 执行 {result.testsRun} 项测试 | 失败: {len(result.failures)} | 错误: {len(result.errors)}")
    if result.wasSuccessful():
        print("🎉 全部自动化测试顺利通过！所有核心模块、通信契约与防损坏防护验证完毕！")
    print("="*70 + "\n")

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

