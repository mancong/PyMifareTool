# -*- coding: utf-8 -*-
"""
PyMifareTool - PN532 ISO/IEC 14443-4 CPU 智能卡与 APDU/PBOC/交通联合 扩展适配 Mixin
实现原生 APDU 收发、61xx (GET RESPONSE) 与 6Cxx (修正 Le) 自动状态协商、
全国交通联合/城市一卡通/银联金融卡公共信息读取、电子钱包余额及文件系统全景遍历
"""

import serial
from typing import Optional, Dict, Any, List


class PN532CpuCardMixin:
    """PN532 CPU 卡 (ISO14443-4) 与 APDU 交互扩展 Mixin"""

    @staticmethod
    def _fix_apdu_le(apdu: bytes, le: int) -> bytes:
        """按 ISO/IEC 7816-4 的 case 1~4 结构替换/追加 Le，避免覆盖数据字节"""
        data = bytearray(apdu)
        le &= 0xFF
        if len(data) < 4:
            return bytes(data + bytes([le]))
        if len(data) == 4:
            data.append(le)
            return bytes(data)
        if len(data) == 5:
            data[-1] = le
            return bytes(data)

        if data[4] == 0x00 and len(data) >= 7:
            lc_ext = int.from_bytes(data[5:7], "big")
            if lc_ext == 0 and len(data) == 7:
                # 扩展 case 2: header + 00 00 + Le
                data[-1] = le
            elif len(data) == 7 + lc_ext:
                # 扩展 case 3: 有数据无 Le
                data.append(le)
            else:
                # 扩展 case 4 或异常长度: 替换末尾 Le
                data[-1] = le
            return bytes(data)

        lc = data[4]
        if len(data) == 5 + lc:
            # 短 case 3: 有数据无 Le
            data.append(le)
        else:
            # 短 case 2/4: 末尾为 Le
            data[-1] = le
        return bytes(data)

    def send_apdu(self, ser: serial.Serial, apdu: bytes, timeout: float = 0.5, auto_get_response: bool = True) -> Dict[str, Any]:
        """
        向当前激活的 ISO/IEC 14443-4 CPU 卡发送原生 APDU 并接收应答 (遵循 ISO 7816-4 与 NXP UM0701-04 InDataExchange)
        支持状态字自动协商:
        - 遇到 61xx (有额外数据待取回): 自动下发 00 C0 00 00 [xx] (GET RESPONSE) 取回完整载荷
        - 遇到 6Cxx (期望长度 Le 不匹配): 自动提取 xx 作为正确 Le 并重发 APDU
        """
        from core.protocols.iso7816 import APDUProtocol

        payload = bytes([0x01]) + apdu
        res = self._send_and_receive(ser, self.CMD_IN_DATA_EXCHANGE, payload, timeout=timeout)
        if res is None:
            return {"ok": False, "error": "通信超时或无应答", "sw_desc": "超时", "data": b"", "data_hex": "", "sw_hex": ""}

        if len(res) == 0 or res[0] != 0x00:
            err_code = res[0] if len(res) > 0 else 0xFF
            return {"ok": False, "error": f"PN532 射频通信异常 (0x{err_code:02X})", "sw_desc": "硬件通信异常", "data": b"", "data_hex": "", "sw_hex": ""}

        card_res = res[1:]
        if len(card_res) < 2:
            return {"ok": False, "error": "卡片应答长度不足 2 字节", "sw_desc": "异常状态字", "data": b"", "data_hex": "", "sw_hex": ""}

        sw1 = card_res[-2]
        sw2 = card_res[-1]
        sw_hex = f"{sw1:02X}{sw2:02X}"
        rx_data = card_res[:-2]
        sw_desc = APDUProtocol.get_sw_description(sw1, sw2)

        # 61xx 自动处理: 循环 GET RESPONSE 直到取回完整数据或达到上限
        if sw1 == 0x61 and auto_get_response:
            original_sw_hex = sw_hex
            full_data = rx_data
            cur_sw1, cur_sw2 = sw1, sw2
            got_response = False
            for _ in range(8):
                if cur_sw1 != 0x61:
                    break
                get_resp_apdu = bytes([0x00, 0xC0, 0x00, 0x00, cur_sw2])
                res2 = self._send_and_receive(
                    ser, self.CMD_IN_DATA_EXCHANGE, bytes([0x01]) + get_resp_apdu, timeout=timeout
                )
                if not (res2 and len(res2) >= 3 and res2[0] == 0x00):
                    break
                card_res2 = res2[1:]
                cur_sw1, cur_sw2 = card_res2[-2], card_res2[-1]
                full_data += card_res2[:-2]
                got_response = True

            if got_response:
                sw_hex2 = f"{cur_sw1:02X}{cur_sw2:02X}"
                return {
                    "ok": (sw_hex2 == "9000"),
                    "sw1": cur_sw1, "sw2": cur_sw2,
                    "sw_hex": sw_hex2,
                    "original_sw_hex": original_sw_hex,
                    "auto_resolved": True,
                    "sw_desc": f"{APDUProtocol.get_sw_description(cur_sw1, cur_sw2)} (经 GET RESPONSE 自动取回)",
                    "data": full_data,
                    "data_hex": full_data.hex().upper(),
                }

        # 6Cxx 自动处理: 按 ISO 7816-4 用例结构修正 Le 后重发
        if sw1 == 0x6C and auto_get_response:
            fixed_apdu = self._fix_apdu_le(apdu, sw2)
            res2 = self._send_and_receive(ser, self.CMD_IN_DATA_EXCHANGE, bytes([0x01]) + fixed_apdu, timeout=timeout)
            if res2 and len(res2) >= 3 and res2[0] == 0x00:
                card_res2 = res2[1:]
                sw1_2 = card_res2[-2]
                sw2_2 = card_res2[-1]
                sw_hex2 = f"{sw1_2:02X}{sw2_2:02X}"
                full_data = card_res2[:-2]
                return {
                    "ok": (sw_hex2 == "9000"),
                    "sw1": sw1_2, "sw2": sw2_2,
                    "sw_hex": sw_hex2,
                    "original_sw_hex": sw_hex,
                    "auto_resolved": True,
                    "sw_desc": f"{APDUProtocol.get_sw_description(sw1_2, sw2_2)} (经 6Cxx 自动修正期望长度 Le)",
                    "data": full_data,
                    "data_hex": full_data.hex().upper(),
                }

        return {
            "ok": (sw_hex == "9000"),
            "sw1": sw1, "sw2": sw2,
            "sw_hex": sw_hex,
            "sw_desc": sw_desc,
            "data": rx_data,
            "data_hex": rx_data.hex().upper(),
        }

    def read_cpu_card_public_info(self, ser: serial.Serial, timeout: float = 0.6) -> Dict[str, Any]:
        """
        一键全量读取 CPU 智能卡 (全国交通联合/城市交通卡/银联PBOC借贷记卡) 公开信息与最近流水
        实现自适应 AID 选择、0015 公开信息解析、SFI 2 银行卡记录读取、电子钱包余额与双格式循环记录解析
        """
        from core.protocols.iso7816 import (
            APDUProtocol, AID_T_UNION, AID_PBOC_CASH, AID_PPSE
        )

        logs = []
        def _exec_apdu(apdu_bytes: bytes, desc: str = ""):
            r = self.send_apdu(ser, apdu_bytes, timeout=timeout)
            logs.append({"cmd": apdu_bytes.hex().upper(), "desc": desc, "resp": r})
            return r

        # 步骤 0: 激活并复位射频信道，建立 ISO 14443-4 T=CL 上下文
        self.restore_type_a_registers(ser)
        target_payload = bytes([0x01, 0x00])  # MaxTg=1, BrTy=0 (Type A 106 kbps)
        target_res = self._send_and_receive(ser, self.CMD_IN_LIST_PASSIVE_TARGET, target_payload, timeout=0.35)
        if target_res is None or (len(target_res) == 1 and target_res[0] == 0x00):
            return {
                "error": "未检测到 CPU 智能卡，请将卡片贴紧读卡器！",
                "app_name": "未检测到卡片",
                "card_number": "-",
                "balance_str": "--",
                "transactions": [],
                "logs": logs,
            }

        app_name = "CPU 智能卡应用"
        selected_aid = None
        issuer_code = "-"
        card_number = "-"
        start_date = ""
        end_date = ""
        balance_val = None
        balance_str = "--"
        transactions = []

        # 步骤 1: 优先探测 PPSE (2PAY.SYS.DDF01) 识别银联芯片卡
        ppse_apdu = APDUProtocol.build_select_apdu(AID_PPSE, by_name=True)
        ppse_res = _exec_apdu(ppse_apdu, "选择非接支付系统目录 (PPSE)")
        if ppse_res.get("ok") and ppse_res.get("data"):
            ppse_info = APDUProtocol.parse_ppse_response(ppse_res["data"])
            if ppse_info and ppse_info.get("aid"):
                selected_aid = ppse_info["aid"]
                app_name = ppse_info.get("app_name", "银联 PBOC 金融卡")
                # 选定主 AID
                _exec_apdu(APDUProtocol.build_select_apdu(selected_aid, by_name=True), f"选择主应用 AID: {selected_aid.hex().upper()}")

        # 步骤 2: 若非 PPSE，按顺序尝试常见借贷记与交通联合 AID
        if not selected_aid:
            candidate_aids = [
                ("中国金融借记应用 (PBOC Debit)", bytes.fromhex("A0000000031010")),
                ("中国金融贷记应用 (PBOC Credit)", bytes.fromhex("A0000000032010")),
                ("中国金融集成电路卡 (PBOC Cash)", AID_PBOC_CASH),
                ("全国交通联合卡 (T-Union)", AID_T_UNION),
                ("上海公共交通卡 (SPTC)", bytes.fromhex("A00000000386980701")),
                ("岭南通/粤港澳交通卡", bytes.fromhex("5943542E55534552")),
                ("深圳通公交应用", bytes.fromhex("535A542E57414C4C4554")),
                ("北京市政一卡通", bytes.fromhex("9156000014010001")),
            ]
            for name, aid in candidate_aids:
                sel_res = _exec_apdu(APDUProtocol.build_select_apdu(aid, by_name=True), f"尝试选择应用: {name}")
                if sel_res.get("ok"):
                    selected_aid = aid
                    app_name = name
                    break

        # 步骤 3: 读取 0015 公开信息文件 (交通部 SFI=0x15，30 字节)
        read_0015_apdu = APDUProtocol.build_read_binary_apdu(sfi=0x15, length=30)
        res_0015 = _exec_apdu(read_0015_apdu, "读取 0015 文件 (交通部卡片信息)")
        if res_0015.get("ok") and len(res_0015.get("data", b"")) >= 20:
            parsed_0015 = APDUProtocol.parse_t_union_card_info(res_0015["data"])
            card_number = parsed_0015.get("card_number") or card_number
            issuer_code = parsed_0015.get("issuer_code") or issuer_code
            start_date = parsed_0015.get("start_date") or start_date
            end_date = parsed_0015.get("end_date") or end_date
        else:
            # 回退读取 PBOC 银行卡公共应用记录 (优先 SFI=2 与 SFI=1)
            found_pan = False
            for pboc_sfi in [2, 1]:
                for rec_i in [1, 2]:
                    read_rec_apdu = APDUProtocol.build_read_record_apdu(record_num=rec_i, sfi=pboc_sfi)
                    res_rec = _exec_apdu(read_rec_apdu, f"读取 PBOC SFI 0x{pboc_sfi:02X} 记录 {rec_i}")
                    if res_rec.get("ok") and res_rec.get("data"):
                        parsed_pboc = APDUProtocol.parse_pboc_card_info(res_rec["data"])
                        if parsed_pboc.get("card_number"):
                            card_number = parsed_pboc["card_number"]
                            issuer_code = parsed_pboc.get("issuer_name") or parsed_pboc.get("issuer_code") or issuer_code
                            end_date = parsed_pboc.get("end_date") or end_date
                            start_date = parsed_pboc.get("start_date") or start_date
                            found_pan = True
                            break
                if found_pan:
                    break

        # 步骤 4: 查询电子钱包余额 (80 5C 00 02 04)
        bal_apdu = APDUProtocol.build_get_balance_apdu(cash_type=0x00)
        bal_res = _exec_apdu(bal_apdu, "查询电子现金/钱包余额")
        if bal_res.get("ok") and len(bal_res.get("data", b"")) >= 4:
            balance_val = APDUProtocol.parse_balance(bal_res["data"])
            if balance_val is not None:
                balance_str = f"{balance_val:.2f} 元"
        else:
            balance_str = "联机/借贷记卡 (需联机验证)"

        # 步骤 5: 读取循环记录交易流水 (优先交通部 SFI=0x18，失败自动回退 PBOC SFI=0x0B)
        sfi_to_try = [0x18, 0x0B]
        for sfi in sfi_to_try:
            records_found = []
            file_not_found = False
            for rec_no in range(1, 11):
                read_rec_apdu = APDUProtocol.build_read_record_apdu(record_num=rec_no, sfi=sfi)
                rec_res = _exec_apdu(read_rec_apdu, f"读取 SFI 0x{sfi:02X} 流水记录 {rec_no}")
                sw = rec_res.get("sw_hex", "")
                if sw == "6A82":  # 文件未找到，退出尝试下一 SFI
                    file_not_found = True
                    break
                if sw in ("6A83", "6B00"):  # 记录号不存在或越界，结束循环
                    break
                if rec_res.get("ok") and len(rec_res.get("data", b"")) >= 16:
                    rec_item = APDUProtocol.parse_transaction_record(rec_res["data"], index=rec_no)
                    if rec_item:
                        records_found.append(rec_item)
            if records_found:
                transactions = records_found
                break
            if not file_not_found and len(transactions) > 0:
                break

        return {
            "app_name": app_name,
            "aid_hex": selected_aid.hex().upper() if selected_aid else "",
            "card_number": card_number,
            "issuer_code": issuer_code,
            "start_date": start_date,
            "end_date": end_date,
            "balance": balance_val,
            "balance_str": balance_str,
            "transactions": transactions,
            "logs": logs,
        }

    def scan_cpu_card_tree(self, ser: serial.Serial, timeout: float = 0.35, progress_cb=None, abort_check=None) -> Dict[str, Any]:
        """
        深度全景遍历 CPU 智能卡 COS 全文件系统与常见 SFI/FID 目录树
        支持 progress_cb 回调与 abort_check 安全快速中断
        """
        from core.protocols.iso7816 import APDUProtocol, AID_T_UNION, AID_PPSE

        tree = {
            "app_name": "CPU 智能卡全文件系统",
            "aid_hex": "",
            "aborted": False,
            "stats": {"total_files": 0, "readable_bytes": 0, "total_records": 0},
            "children": [],
            "flat_files": {},
        }

        # 激活并复位射频信道，建立 ISO 14443-4 T=CL 上下文
        self.restore_type_a_registers(ser)
        target_payload = bytes([0x01, 0x00])
        target_res = self._send_and_receive(ser, self.CMD_IN_LIST_PASSIVE_TARGET, target_payload, timeout=0.35)
        if target_res is None or (len(target_res) == 1 and target_res[0] == 0x00):
            tree["error"] = "未检测到 CPU 智能卡"
            return tree

        probes = [
            ("MF_3F00", "3F00 主控目录", bytes([0x3F, 0x00]), False),
            ("PPSE_2PAY", "2PAY.SYS.DDF01", AID_PPSE, True),
            ("PBOC_DEBIT", "中国金融借记应用 (PBOC Debit)", bytes.fromhex("A0000000031010"), True),
            ("PBOC_CREDIT", "中国金融贷记应用 (PBOC Credit)", bytes.fromhex("A0000000032010"), True),
            ("T_UNION", "交通部全国交通联合应用", AID_T_UNION, True),
            ("PBOC_CASH", "PBOC 电子现金应用", bytes.fromhex("A000000333010101"), True),
            ("DIR_1PAY", "1PAY.SYS.DDF01", bytes.fromhex("315041592E5359532E4444463031"), True),
        ]
        sfi_list = [0x15, 0x16, 0x17, 0x18, 0x19, 0x02, 0x0B]

        total_steps = len(probes) + len(sfi_list)
        cur_step = 0

        for fid_id, name, aid_bytes, by_name in probes:
            if abort_check and abort_check():
                tree["aborted"] = True
                return tree

            cur_step += 1
            if progress_cb:
                progress_cb(cur_step, total_steps, f"正在探测应用/目录: {name}...")

            sel_apdu = APDUProtocol.build_select_apdu(aid_bytes, by_name=by_name)
            res = self.send_apdu(ser, sel_apdu, timeout=timeout)
            if res.get("ok"):
                f_data = res.get("data", b"")
                tree["stats"]["total_files"] += 1
                tree["stats"]["readable_bytes"] += len(f_data)
                dir_node = {
                    "id": fid_id,
                    "name": name,
                    "type": "directory",
                    "data": f_data,
                    "size": len(f_data),
                    "children": []
                }
                tree["children"].append(dir_node)
                tree["flat_files"][fid_id] = dir_node

        for sfi in sfi_list:
            if abort_check and abort_check():
                tree["aborted"] = True
                return tree

            cur_step += 1
            if progress_cb:
                progress_cb(cur_step, total_steps, f"正在扫描文件 SFI=0x{sfi:02X}...")

            read_bin = APDUProtocol.build_read_binary_apdu(sfi=sfi, length=30)
            res_bin = self.send_apdu(ser, read_bin, timeout=timeout)
            if res_bin.get("ok") and res_bin.get("data"):
                d = res_bin["data"]
                node_id = f"EF_SFI_{sfi:02X}"
                f_node = {
                    "id": node_id,
                    "name": f"SFI 0x{sfi:02X} 二进制文件",
                    "type": "binary",
                    "data": d,
                    "size": len(d),
                }
                tree["stats"]["total_files"] += 1
                tree["stats"]["readable_bytes"] += len(d)
                tree["children"].append(f_node)
                tree["flat_files"][node_id] = f_node
            else:
                rec1_apdu = APDUProtocol.build_read_record_apdu(record_num=1, sfi=sfi)
                res_rec = self.send_apdu(ser, rec1_apdu, timeout=timeout)
                if res_rec.get("ok") and res_rec.get("data"):
                    d = res_rec["data"]
                    node_id = f"EF_REC_{sfi:02X}"
                    rec_node = {
                        "id": node_id,
                        "name": f"SFI 0x{sfi:02X} 循环记录文件",
                        "type": "record",
                        "data": d,
                        "size": len(d),
                    }
                    tree["stats"]["total_files"] += 1
                    tree["stats"]["readable_bytes"] += len(d)
                    tree["stats"]["total_records"] += 1
                    tree["children"].append(rec_node)
                    tree["flat_files"][node_id] = rec_node

        return tree
