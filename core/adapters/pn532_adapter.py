# -*- coding: utf-8 -*-
"""
PyMifareTool - PCR532 / PN532 HSU (High-Speed UART) 硬件驱动适配器
全面兼容 PCR532 Pro / NFC PRO (基于 NXP PN532 方案) 与开源生态 (touzi/PCR532, libnfc)
支持自动唤醒、SAM配置、寻卡、双向扇区认证、数据读写与二代居民身份证 (ISO/IEC 14443-B) 穿透读取
本适配器为硬件时序状态协调者，所有底层报文编解码均解耦委托给 core.protocols 层
"""

import time
import serial
from typing import Optional, Dict, Any, Tuple, List
from .base_adapter import BaseReaderAdapter
from core.protocols.pn532 import PN532Protocol
from core.protocols.iso14443b import ISO14443BProtocol, calculate_crc_b, CIU_REGISTERS_TYPE_B_ID
from core.models.card_converter import CardConverter


class PN532Adapter(BaseReaderAdapter):
    """
    NXP PN532 / PCR532 读写器驱动适配器
    遵循 NXP UM0701-04 HSU 协议规范
    """

    # 协议常量桥接 (向后兼容)
    PREAMBLE = PN532Protocol.PREAMBLE
    START_CODE = PN532Protocol.START_CODE
    POSTAMBLE = PN532Protocol.POSTAMBLE

    HOST_TO_PN532 = PN532Protocol.HOST_TO_PN532
    PN532_TO_HOST = PN532Protocol.PN532_TO_HOST

    ACK_FRAME = PN532Protocol.ACK_FRAME

    # 常用命令字
    CMD_GET_FIRMWARE_VERSION   = PN532Protocol.CMD_GET_FIRMWARE_VERSION
    CMD_WRITE_REGISTER         = PN532Protocol.CMD_WRITE_REGISTER
    CMD_READ_REGISTER          = PN532Protocol.CMD_READ_REGISTER
    CMD_SAM_CONFIGURATION      = PN532Protocol.CMD_SAM_CONFIGURATION
    CMD_IN_LIST_PASSIVE_TARGET = PN532Protocol.CMD_IN_LIST_PASSIVE_TARGET
    CMD_IN_DATA_EXCHANGE       = PN532Protocol.CMD_IN_DATA_EXCHANGE
    CMD_IN_COMMUNICATE_THRU    = PN532Protocol.CMD_IN_COMMUNICATE_THRU
    CMD_RF_CONFIGURATION       = PN532Protocol.CMD_RF_CONFIGURATION

    # MIFARE Classic 内部指令
    MIFARE_CMD_AUTH_A = PN532Protocol.MIFARE_CMD_AUTH_A
    MIFARE_CMD_AUTH_B = PN532Protocol.MIFARE_CMD_AUTH_B
    MIFARE_CMD_READ   = PN532Protocol.MIFARE_CMD_READ
    MIFARE_CMD_WRITE  = PN532Protocol.MIFARE_CMD_WRITE

    # 二代居民身份证非标寄存器与 CRC 算法桥接 (向后兼容)
    CIU_REGISTERS_TYPE_B_ID = CIU_REGISTERS_TYPE_B_ID
    calculate_crc_b = staticmethod(calculate_crc_b)

    def __init__(self):
        super().__init__()
        self.device_name = "PCR532 / PN532 (双向全功能)"
        self.is_bidirectional = True
        self.default_baudrate = 115200
        self.supported_baudrates = [115200, 38400, 9600, 57600, 230400, 460800]
        self.firmware_info = "PN532 NFC Controller"
        self.cached_uid: Optional[bytes] = None
        self._last_poll_time = 0.0

    @classmethod
    def build_hsu_frame(cls, cmd: int, data: bytes = b"") -> bytes:
        return PN532Protocol.build_hsu_frame(cmd, data)

    @classmethod
    def build_response_frame(cls, cmd: int, data: bytes = b"") -> bytes:
        return PN532Protocol.build_response_frame(cmd, data)

    @classmethod
    def parse_hsu_frame(cls, raw: bytes) -> Tuple[Optional[Dict[str, Any]], bytes]:
        return PN532Protocol.parse_hsu_frame(raw)

    def _send_and_receive(self, ser: serial.Serial, cmd: int, data: bytes = b"", timeout: float = 0.45) -> Optional[bytes]:
        """发送 HSU 命令帧并同步等待有效应答数据载荷"""
        if not ser or not ser.is_open:
            return None

        frame = self.build_hsu_frame(cmd, data)
        if hasattr(ser, "reset_input_buffer"):
            try:
                ser.reset_input_buffer()
            except Exception:
                pass
        try:
            ser.write(frame)
            ser.flush()
        except Exception:
            return None

        start = time.time()
        rx_buf = bytearray()
        got_ack = False

        while time.time() - start < timeout:
            if ser.in_waiting > 0:
                chunk = ser.read(ser.in_waiting)
                rx_buf.extend(chunk)

                # 循环解析缓冲区
                while len(rx_buf) >= 6:
                    info, remaining = self.parse_hsu_frame(bytes(rx_buf))
                    if info is None:
                        rx_buf = bytearray(remaining)
                        break

                    rx_buf = bytearray(remaining)
                    if info.get("type") == "ACK":
                        got_ack = True
                    elif info.get("type") == "DATA":
                        # 检查应答命令字是否匹配
                        resp_cmd = info.get("cmd")
                        if resp_cmd == (cmd + 1):
                            return info.get("data", b"")
                        elif resp_cmd == cmd:
                            return info.get("data", b"")
            else:
                time.sleep(0.005)

        return None

    def wakeup(self, ser: serial.Serial) -> bool:
        """
        HSU 唤醒序列 (UM0701-04 Section 5.1):
        发送长引导前导码 0x55 0x55 0x00 0x00 0x00... 唤醒 HSU 接口
        """
        if not ser or not ser.is_open:
            return False
        try:
            # 唤醒序报: 0x55 + SAMConfiguration (或者连续 0x55 引导)
            wakeup_preamble = bytes([0x55] * 16 + [0x00, 0x00, 0x00])
            ser.write(wakeup_preamble)
            ser.flush()
            time.sleep(0.02)
            ser.reset_input_buffer()
            return True
        except Exception:
            return False

    def init_device(self, ser: serial.Serial) -> bool:
        """初始化 PCR532 / PN532 设备与 SAM 射频配置"""
        try:
            # 🚨 硬件红线 1: 物理复位保护，释放 DTR/RTS
            ser.dtr = False
            ser.rts = False
            ser.reset_input_buffer()
            ser.reset_output_buffer()

            # 步骤 1: 唤醒芯片
            self.wakeup(ser)

            # 步骤 2: 获取固件版本验证芯片存活
            fw_data = self._send_and_receive(ser, self.CMD_GET_FIRMWARE_VERSION, timeout=0.25)
            if fw_data and len(fw_data) >= 4:
                ic = fw_data[0]
                ver = fw_data[1]
                rev = fw_data[2]
                support = fw_data[3]
                self.firmware_info = f"PN532 v{ver}.{rev} (IC=0x{ic:02X}, Support=0x{support:02X})"
            else:
                self.firmware_info = "PN532 兼容设备 (快速模式)"

            # 步骤 3: SAMConfiguration 激活射频正常模式
            # 0x01: Normal mode, 0x14: 1秒超时, 0x01: 使用 IRQ
            sam_res = self._send_and_receive(ser, self.CMD_SAM_CONFIGURATION, bytes([0x01, 0x14, 0x01]), timeout=0.3)
            return True
        except Exception:
            return False

    def parse_incoming(self, rx_buffer: bytearray) -> Tuple[Optional[Dict[str, Any]], bytes]:
        """流式解析串口收到的数据"""
        info, remaining = self.parse_hsu_frame(bytes(rx_buffer))
        if info:
            if info.get("type") == "DATA" and info.get("cmd") == (self.CMD_IN_LIST_PASSIVE_TARGET + 1):
                # 收到寻卡应答包，提取 UID
                data = info.get("data", b"")
                parsed_card = self._parse_target_data(data)
                if parsed_card:
                    info.update(parsed_card)
            return info, remaining
        return None, remaining

    def _parse_target_data(self, data: bytes) -> Optional[Dict[str, Any]]:
        """解析 InListPassiveTarget (0x4B) 返回的卡片信息"""
        if len(data) >= 7 and data[0] >= 1:
            atqa = data[2:4]
            sak = data[4]
            uid_len = data[5]
            if len(data) >= 6 + uid_len:
                uid_bytes = data[6: 6 + uid_len]
                self.cached_uid = uid_bytes
                conversions = CardConverter.convert_uid(uid_bytes)

                # ATS 与 CPU 卡特征探测 (SAK Bit 5=1 即 SAK=0x20/0x28/0x38 遵循 ISO14443-4)
                is_cpu_card = bool((sak & 0x20 != 0) or sak in (0x20, 0x28, 0x38))
                ats_bytes = b""
                ats_hex = ""
                if len(data) > 6 + uid_len:
                    ats_bytes = data[6 + uid_len:]
                    ats_hex = " ".join(f"{b:02X}" for b in ats_bytes)

                card_type = conversions.get("card_type", "Type A 智能卡")
                if is_cpu_card:
                    if sak == 0x20:
                        card_type = "ISO14443-4 CPU 卡 (标准智能卡)"
                    elif sak in (0x28, 0x38):
                        card_type = f"双界面复合卡 (CPU+M1 SAK=0x{sak:02X})"
                    else:
                        card_type = f"ISO14443-4 CPU 卡 (SAK=0x{sak:02X})"

                res = {
                    "uid_bytes": uid_bytes,
                    "atqa": atqa,
                    "sak": sak,
                    "conversions": conversions,
                    "device_model": "PN532",
                    "is_cpu_card": is_cpu_card,
                    "card_type": card_type,
                }
                if ats_hex:
                    res["ats_hex"] = ats_hex
                    res["ats_bytes"] = ats_bytes
                return res
        return None

    def write_registers(self, ser: serial.Serial, reg_value_pairs: List[Tuple[int, int]], timeout: float = 0.25) -> bool:
        """向 PN532 写入 CIU 寄存器配置 (WriteRegister, 0x08)"""
        payload = bytearray()
        for addr, val in reg_value_pairs:
            payload.append((addr >> 8) & 0xFF)
            payload.append(addr & 0xFF)
            payload.append(val & 0xFF)
        resp = self._send_and_receive(ser, self.CMD_WRITE_REGISTER, bytes(payload), timeout=timeout)
        return resp is not None

    def config_type_b_id_registers(self, ser: serial.Serial) -> bool:
        """配置二代身份证专用的非标 Type B CIU 射频寄存器"""
        return self.write_registers(ser, self.CIU_REGISTERS_TYPE_B_ID)

    def restore_type_a_registers(self, ser: serial.Serial, timeout: float = 0.25) -> bool:
        """将 PN532 CIU 射频寄存器恢复为 Type A 出厂默认值 (用于二代证读取后恢复标准射频场)"""
        from core.protocols.iso14443b import CIU_REGISTERS_TYPE_A_DEFAULT
        return self.write_registers(ser, CIU_REGISTERS_TYPE_A_DEFAULT, timeout=timeout)

    def read_id_card_uid(self, ser: serial.Serial, timeout: float = 0.35) -> Optional[Dict[str, Any]]:
        """
        读取二代身份证 8 字节 UID (ISO/IEC 14443-B 非标协议握手)
        实现流程:
        1. 写入 12 个 CIU 射频寄存器配置
        2. 发送 REQB 指令 (05 00 00 71 FF) -> 接收 ATQB 并提取 4 字节 PUPI
        3. 发送 ATTRIB 选卡指令 (1D [PUPI 4B] 00 08 01 08 + CRC-B)
        4. 发送读取 GUID / UID 指令 (00 36 00 00 08 57 44) -> 接收 8 字节 UID
        5. finally 严格复位 CIU 寄存器回 Type A 出厂标准值，保障 M1/CPU 卡射频兼容
        """
        try:
            # 1. 写入 CIU 寄存器配置
            if not self.config_type_b_id_registers(ser):
                return None

            # 2. 发送 REQB 指令
            reqb_frame = ISO14443BProtocol.build_reqb_frame()
            resp = self._send_and_receive(ser, self.CMD_IN_COMMUNICATE_THRU, reqb_frame, timeout=0.12)
            if not resp or len(resp) < 6:
                return None

            if resp[0] != 0x00:
                return None

            atqb = resp[1:]
            pupi = ISO14443BProtocol.parse_atqb(atqb)
            if not pupi:
                return None

            # 3. 发送 ATTRIB 指令
            attrib_frame = ISO14443BProtocol.build_attrib_frame(pupi)
            resp_attrib = self._send_and_receive(ser, self.CMD_IN_COMMUNICATE_THRU, attrib_frame, timeout=0.15)
            if not resp_attrib or len(resp_attrib) < 1 or resp_attrib[0] != 0x00:
                return None

            # 4. 发送读取 GUID 指令
            read_guid_frame = ISO14443BProtocol.build_read_guid_frame()
            resp_guid = self._send_and_receive(ser, self.CMD_IN_COMMUNICATE_THRU, read_guid_frame, timeout=0.15)
            if not resp_guid or len(resp_guid) < 9 or resp_guid[0] != 0x00:
                return None

            # 提取 8 字节 GUID
            id_guid = ISO14443BProtocol.parse_guid_response(resp_guid[1:])
            if not id_guid:
                return None

            self.cached_uid = id_guid
            conversions = CardConverter.convert_uid(id_guid)

            return {
                "uid_bytes": id_guid,
                "atqa": b"\x00\x00",
                "sak": 0x00,
                "conversions": conversions,
                "card_type": "二代居民身份证 (8-byte UID / ISO14443-B)",
                "device_model": "PN532 (二代身份证 ISO14443-B)",
                "pupi": pupi,
                "is_id_card": True,
            }
        finally:
            # 无论读卡成功或未感应到身份证，均无条件将 CIU 寄存器恢复为 Type A 标准配置
            self.restore_type_a_registers(ser)

    def poll_card(self, ser: serial.Serial, timeout: float = 0.5) -> Optional[Dict[str, Any]]:
        """
        主动寻卡:
        1. 优先寻 Type A 卡片 (M1 / CUID / UID)
        2. 若未探测到 Type A 卡片，自适应探测二代居民身份证 (ISO14443-B)
        """
        # 1. 尝试 Type A
        payload = bytes([0x01, 0x00])  # MaxTg=1, BrTy=0 (106 kbps Type A)
        res = self._send_and_receive(ser, self.CMD_IN_LIST_PASSIVE_TARGET, payload, timeout=timeout)
        if res:
            parsed = self._parse_target_data(res)
            if parsed:
                return parsed

        # 2. 尝试二代身份证 (Type B)
        try:
            id_card = self.read_id_card_uid(ser, timeout=0.25)
            if id_card:
                return id_card
        except Exception:
            pass

        return None

    def authenticate(self, ser: serial.Serial, block: int, key_type: str, key: bytes, uid: bytes = b"", timeout: float = 0.35) -> bool:
        """Mifare Classic 密钥认证"""
        if not uid:
            uid = self.cached_uid if self.cached_uid else b"\x00\x00\x00\x00"

        # 遵循 ISO14443-3 / NXP UM0701-04: 7 字节 UID 取 Cascade Level 2 后 4 字节参与认证
        auth_uid = uid[-4:] if len(uid) >= 4 else (uid + b"\x00" * 4)[:4]

        auth_cmd = self.MIFARE_CMD_AUTH_A if key_type.upper() == "A" else self.MIFARE_CMD_AUTH_B
        payload = bytes([0x01, auth_cmd, block & 0xFF]) + key[:6] + auth_uid

        res = self._send_and_receive(ser, self.CMD_IN_DATA_EXCHANGE, payload, timeout=timeout)
        if res and len(res) >= 1:
            return res[0] == 0x00
        return False

    def read_block(self, ser: serial.Serial, block: int, timeout: float = 0.35) -> Optional[bytes]:
        """读取单个数据块 (16 字节)"""
        payload = bytes([0x01, self.MIFARE_CMD_READ, block & 0xFF])
        res = self._send_and_receive(ser, self.CMD_IN_DATA_EXCHANGE, payload, timeout=timeout)
        if res and len(res) >= 17:
            if res[0] == 0x00:
                return res[1:17]
        return None

    def write_block(self, ser: serial.Serial, block: int, data: bytes, timeout: float = 0.35) -> bool:
        """写入单个数据块 (16 字节)"""
        if len(data) != 16:
            return False
        payload = bytes([0x01, self.MIFARE_CMD_WRITE, block & 0xFF]) + data[:16]
        res = self._send_and_receive(ser, self.CMD_IN_DATA_EXCHANGE, payload, timeout=timeout)
        if res and len(res) >= 1:
            return res[0] == 0x00
        return False

    def write_magic_block0(self, ser: serial.Serial, block0_data: bytes, magic_type: str = "CUID", timeout: float = 0.5) -> bool:
        """写入 Block 0 厂商/卡号块"""
        if len(block0_data) != 16:
            return False

        if magic_type.upper() in ["CUID", "GEN2", "FUID"]:
            return self.write_block(ser, 0, block0_data, timeout=timeout)
        elif magic_type.upper() == "GEN1A":
            # Gen1a 后门解锁时序: HALT (0x50 00) -> Unlock 1 (0x40) -> Unlock 2 (0x43)
            self._send_and_receive(ser, self.CMD_IN_COMMUNICATE_THRU, bytes([0x50, 0x00]), timeout=timeout)
            self._send_and_receive(ser, self.CMD_IN_COMMUNICATE_THRU, bytes([0x40]), timeout=timeout)
            self._send_and_receive(ser, self.CMD_IN_COMMUNICATE_THRU, bytes([0x43]), timeout=timeout)
            return self.write_block(ser, 0, block0_data, timeout=timeout)

        return self.write_block(ser, 0, block0_data, timeout=timeout)

    def reactivate_target(self, ser: serial.Serial, timeout: float = 0.25) -> bool:
        """
        重新激活当前射频目标卡片 (解除 Mifare Classic HALT 挂起状态或恢复 Type A 射频信道)
        下发 InListPassiveTarget (0x4A) 重新寻卡并建立活跃通信上下文
        """
        if not ser:
            return False
        payload = bytes([0x01, 0x00])  # MaxTg=1, BrTy=0 (106 kbps Type A)
        res = self._send_and_receive(ser, self.CMD_IN_LIST_PASSIVE_TARGET, payload, timeout=timeout)
        if res:
            parsed = self._parse_target_data(res)
            if parsed and "uid_bytes" in parsed:
                self.cached_uid = parsed["uid_bytes"]
                return True
        return False

    _reactivate_target = reactivate_target

    def lock_ufuid_card(self, ser: serial.Serial, timeout: float = 0.5) -> bool:
        """锁死 UFUID 可变卡 (使其 0 块永久固化为普通只读 M1 卡)"""
        if not ser:
            return False
        lock_frame = bytes([0xE0, 0x00, 0x00, 0x00])
        res = self._send_and_receive(ser, self.CMD_IN_COMMUNICATE_THRU, lock_frame, timeout=timeout)
        if res is not None:
            return True
        res2 = self._send_and_receive(ser, self.CMD_IN_COMMUNICATE_THRU, bytes([0x43]), timeout=timeout)
        return res2 is not None

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

        # 61xx 自动处理: GET RESPONSE
        if sw1 == 0x61 and auto_get_response:
            get_resp_apdu = bytes([0x00, 0xC0, 0x00, 0x00, sw2])
            res2 = self._send_and_receive(ser, self.CMD_IN_DATA_EXCHANGE, bytes([0x01]) + get_resp_apdu, timeout=timeout)
            if res2 and len(res2) >= 3 and res2[0] == 0x00:
                card_res2 = res2[1:]
                sw1_2 = card_res2[-2]
                sw2_2 = card_res2[-1]
                sw_hex2 = f"{sw1_2:02X}{sw2_2:02X}"
                full_data = rx_data + card_res2[:-2]
                return {
                    "ok": (sw_hex2 == "9000"),
                    "sw1": sw1_2, "sw2": sw2_2,
                    "sw_hex": sw_hex2,
                    "original_sw_hex": sw_hex,
                    "auto_resolved": True,
                    "sw_desc": f"{APDUProtocol.get_sw_description(sw1_2, sw2_2)} (经 GET RESPONSE 自动取回)",
                    "data": full_data,
                    "data_hex": full_data.hex().upper(),
                }

        # 6Cxx 自动处理: 修正 Le 重发
        if sw1 == 0x6C and auto_get_response:
            fixed_apdu = apdu[:-1] + bytes([sw2]) if len(apdu) >= 5 else apdu + bytes([sw2])
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
