# -*- coding: utf-8 -*-
"""
PyMifareTool - PN532 二代居民身份证 (ISO/IEC 14443-B) 扩展适配 Mixin
封装 12 组 CIU 射频寄存器配置、REQB/ATQB 握手、ATTRIB 选卡及 GUID/UID 读取
严格执行硬件红线 5: 在 finally 中恢复 Type A 射频寄存器，保障兼容性
"""

import time
import serial
from typing import Optional, Dict, Any, List, Tuple
from core.protocols.iso14443b import (
    ISO14443BProtocol,
    CIU_REGISTERS_TYPE_B_ID,
    CIU_REGISTERS_TYPE_A_DEFAULT,
    calculate_crc_b,
)
from core.models.card_converter import CardConverter


class PN532IdCardMixin:
    """PN532 二代居民身份证 (ISO14443-B) 专用功能 Mixin"""

    # 二代居民身份证非标寄存器与 CRC 算法桥接 (向后兼容)
    CIU_REGISTERS_TYPE_B_ID = CIU_REGISTERS_TYPE_B_ID
    calculate_crc_b = staticmethod(calculate_crc_b)

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
