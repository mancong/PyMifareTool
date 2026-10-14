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
project_dir = r"D:\Workspace\Works\Other\PyMifareTool"
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
        self.assertEqual(info["conversions"]["hex_normal"], "D7 7E A0 DF")
        self.assertEqual(info["conversions"]["dec_10d_rev"], "3751837399")
        self.assertEqual(info["conversions"]["wiegand_26"], "160,32471")
        self.assertEqual(info["conversions"]["wiegand_34"], "57248,32471")
        self.assertEqual(remaining, bytes([0x55]))

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
        self.assertEqual(table.item(0, 2).text(), "D7")
        self.assertEqual(table.item(0, 3).text(), "7E")
        self.assertEqual(table.item(0, 4).text(), "A0")
        self.assertEqual(table.item(0, 5).text(), "DF")

    def test_gui_cell_inplace_editing(self):
        """模拟用户在扇区矩阵中双击修改某一单元格 Hex 字节"""
        table = self.win.tab_sector.table
        item = table.item(4, 2)
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
        self.assertEqual(table.item(2, 2).text(), "-")
        self.assertEqual(table.item(2, 17).text(), "-")
        self.assertEqual(table.item(2, 18).text(), "-")

        # 2. 模拟读取成功（真实数据就是 0x00）：渲染原样 '00' 而非 '-'
        sector_tab.dump.set_block(2, bytes([0x00] * 16))
        sector_tab.refresh_table()
        self.assertEqual(table.item(2, 2).text(), "00")
        self.assertEqual(table.item(2, 17).text(), "00")
        self.assertEqual(table.item(2, 18).text(), "." * 16)

        # 3. 模拟加密扇区读取受阻：标记为 READ_FAILED，渲染 '??' 与 '[加密受限]'
        sector_tab.dump.set_block_state(3, BlockState.READ_FAILED)
        sector_tab.refresh_table()
        self.assertEqual(table.item(3, 2).text(), "??")
        self.assertEqual(table.item(3, 17).text(), "??")
        self.assertEqual(table.item(3, 18).text(), "[加密受限]")

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

