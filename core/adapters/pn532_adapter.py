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
        try:
            ser.reset_input_buffer()
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
                return {
                    "uid_bytes": uid_bytes,
                    "atqa": atqa,
                    "sak": sak,
                    "conversions": conversions,
                    "device_model": "PN532",
                }
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

    def read_id_card_uid(self, ser: serial.Serial, timeout: float = 0.35) -> Optional[Dict[str, Any]]:
        """
        读取二代身份证 8 字节 UID (ISO/IEC 14443-B 非标协议握手)
        实现流程:
        1. 写入 12 个 CIU 射频寄存器配置
        2. 发送 REQB 指令 (05 00 00 71 FF) -> 接收 ATQB 并提取 4 字节 PUPI
        3. 发送 ATTRIB 选卡指令 (1D [PUPI 4B] 00 08 01 08 + CRC-B)
        4. 发送读取 GUID / UID 指令 (00 36 00 00 08 57 44) -> 接收 8 字节 UID
        """
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

        auth_cmd = self.MIFARE_CMD_AUTH_A if key_type.upper() == "A" else self.MIFARE_CMD_AUTH_B
        payload = bytes([0x01, auth_cmd, block & 0xFF]) + key[:6] + uid[:4]

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
            return self.write_block(ser, 0, block0_data, timeout=timeout)

        return self.write_block(ser, 0, block0_data, timeout=timeout)
