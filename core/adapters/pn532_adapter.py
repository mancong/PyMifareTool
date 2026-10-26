# -*- coding: utf-8 -*-
"""
PyMifareTool - NXP PN532 / PCR532 读写器硬件驱动适配器
遵循 NXP UM0701-04 HSU 协议规范
支持 Mifare Classic 寻卡、认证、读写、魔术卡以及通过 Mixin 扩展的二代身份证与 CPU 卡 APDU
"""

import time
import serial
import logging
from typing import Optional, Dict, Any, List, Tuple
from core.protocols.pn532 import PN532Protocol
from core.protocols.iso14443b import (
    ISO14443BProtocol,
    CIU_REGISTERS_TYPE_B_ID,
    CIU_REGISTERS_TYPE_A_DEFAULT,
    calculate_crc_b,
)
from core.models.card_converter import CardConverter
from .base_adapter import BaseReaderAdapter
from .pn532_id_card import PN532IdCardMixin
from .pn532_cpu_card import PN532CpuCardMixin

logger = logging.getLogger("pymifare.adapters.pn532")


class PN532Adapter(BaseReaderAdapter, PN532IdCardMixin, PN532CpuCardMixin):
    """
    NXP PN532 / PCR532 读写器驱动适配器
    通过组合 PN532IdCardMixin (二代证) 与 PN532CpuCardMixin (CPU卡) 实现高内聚低耦合
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

    # SAMConfiguration 显式配置常量
    SAM_MODE_NORMAL = 0x01
    SAM_TIMEOUT_1S  = 0x14
    SAM_USE_IRQ     = 0x01

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
        self._last_ser: Optional[serial.Serial] = None
        self._probe_fw_ok = False
        self._probe_sam_ok = False
        self._probe_checked = False

    @classmethod
    def build_hsu_frame(cls, cmd: int, data: bytes = b"") -> bytes:
        return PN532Protocol.build_hsu_frame(cmd, data)

    @classmethod
    def build_response_frame(cls, cmd: int, data: bytes = b"") -> bytes:
        return PN532Protocol.build_response_frame(cmd, data)

    @classmethod
    def parse_hsu_frame(cls, raw: bytes) -> Tuple[Optional[Dict[str, Any]], bytes]:
        return PN532Protocol.parse_hsu_frame(raw)

    def parse_incoming(self, raw: bytes) -> Tuple[Optional[Dict[str, Any]], bytes]:
        """解析接收到的原始数据流，提取完整 HSU 帧信息"""
        return self.parse_hsu_frame(raw)

    def _send_and_receive(self, ser: serial.Serial, cmd: int, data: bytes = b"", timeout: float = 0.45) -> Optional[bytes]:
        """发送 HSU 命令帧并同步等待有效应答数据载荷 (优化轮询间隔以降低 CPU 开销)"""
        if not ser or not ser.is_open:
            return None

        frame = self.build_hsu_frame(cmd, data)
        if hasattr(ser, "reset_input_buffer"):
            try:
                ser.reset_input_buffer()
            except Exception as e:
                logger.debug("PN532 reset_input_buffer 异常: %s", e)
        try:
            ser.write(frame)
            ser.flush()
        except Exception as e:
            logger.debug("PN532 写入帧异常: %s", e)
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
                time.sleep(0.010)

        return None

    def wakeup(self, ser: serial.Serial) -> bool:
        """
        HSU 唤醒序列 (UM0701-04 Section 5.1):
        发送长引导前导码 0x55 0x55 0x00 0x00 0x00... 唤醒 HSU 接口
        """
        if not ser or not ser.is_open:
            return False
        try:
            wakeup_seq = bytes([0x55, 0x55, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
            ser.write(wakeup_seq)
            ser.flush()
            time.sleep(0.015)
            if hasattr(ser, "reset_input_buffer"):
                ser.reset_input_buffer()
            return True
        except Exception as e:
            logger.debug("PN532 wakeup 异常: %s", e)
            return False

    def init_device(self, ser: serial.Serial) -> bool:
        """
        初始化 PN532 设备:
        1. 发送唤醒帧唤醒芯片
        2. 获取固件版本验证芯片存活
        3. 发送 SAMConfiguration (0x14) 激活正常工作模式
        """
        self._last_ser = ser
        try:
            # 步骤 1: 唤醒
            self.wakeup(ser)

            # 步骤 2: 获取固件版本验证芯片存活
            fw_data = self._send_and_receive(ser, self.CMD_GET_FIRMWARE_VERSION, timeout=0.25)
            fw_ok = bool(fw_data and len(fw_data) >= 4)
            if fw_ok:
                ic = fw_data[0]
                ver = fw_data[1]
                rev = fw_data[2]
                support = fw_data[3]
                self.firmware_info = f"PN532 v{ver}.{rev} (IC=0x{ic:02X}, Support=0x{support:02X})"
            else:
                self.firmware_info = "PN532 未响应固件查询"

            # 步骤 3: SAMConfiguration 激活射频正常模式
            sam_payload = bytes([self.SAM_MODE_NORMAL, self.SAM_TIMEOUT_1S, self.SAM_USE_IRQ])
            sam_res = self._send_and_receive(ser, self.CMD_SAM_CONFIGURATION, sam_payload, timeout=0.3)
            sam_ok = sam_res is not None
            self._probe_fw_ok = fw_ok
            self._probe_sam_ok = sam_ok
            self._probe_checked = True

            if not fw_ok and sam_ok:
                self.firmware_info = "PN532 兼容设备 (快速模式)"

            # 固件与 SAM 均无应答时不应当被自动探测识别为 PN532
            return bool(fw_ok or sam_ok)
        except Exception as e:
            logger.warning("PN532 初始化流程异常: %s", e)
            self._probe_fw_ok = False
            self._probe_sam_ok = False
            self._probe_checked = True
            return False

    def get_firmware_version(self, ser: Optional[serial.Serial] = None, timeout: float = 0.5) -> str:
        """主动查询固件版本，避免仅返回初始化时缓存的信息"""
        if ser is None:
            ser = self._last_ser
        if ser is not None and getattr(ser, "is_open", False):
            try:
                fw_data = self._send_and_receive(ser, self.CMD_GET_FIRMWARE_VERSION, timeout=timeout)
                if fw_data and len(fw_data) >= 4:
                    ic, ver, rev, support = fw_data[0], fw_data[1], fw_data[2], fw_data[3]
                    self.firmware_info = f"PN532 v{ver}.{rev} (IC=0x{ic:02X}, Support=0x{support:02X})"
                    self._probe_fw_ok = True
                else:
                    self.firmware_info = "PN532 未响应固件查询"
            except Exception as e:
                logger.debug("主动查询固件版本异常: %s", e)
                self.firmware_info = "PN532 固件查询失败"
        return self.firmware_info

    def is_card_present(self, ser: Optional[serial.Serial] = None, timeout: float = 0.15) -> bool:
        """快速判断是否有卡片处于射频场内 (低延时探针)"""
        if ser is None:
            ser = self._last_ser
        if not ser or not getattr(ser, "is_open", False):
            return False
        payload = bytes([0x01, 0x00])  # MaxTg=1, BrTy=0 (Type A 106 kbps)
        res = self._send_and_receive(ser, self.CMD_IN_LIST_PASSIVE_TARGET, payload, timeout=timeout)
        if res and len(res) >= 1:
            return res[0] > 0
        return False

    def get_capabilities(self) -> Dict[str, Any]:
        """汇总初始化探测结果，供连接后能力提示窗展示"""
        fw_ok = bool(self._probe_fw_ok)
        sam_ok = bool(self._probe_sam_ok)
        core_ok = fw_ok or sam_ok
        probe_note = "已完成初始化探测" if self._probe_checked else "尚未执行初始化探测"
        features = [
            {
                "name": "PN532 HSU 协议 / 固件查询",
                "status": "supported" if fw_ok else ("external" if sam_ok else "unsupported"),
                "detail": self.firmware_info if fw_ok else f"{probe_note}，固件查询无有效应答",
            },
            {
                "name": "SAM 射频配置 (Normal Mode)",
                "status": "supported" if sam_ok else "unsupported",
                "detail": "SAMConfiguration 0x14 已应答" if sam_ok else "SAMConfiguration 未应答",
            },
            {
                "name": "ISO14443-A 寻卡 / UID 读取",
                "status": "needs_card" if core_ok else "unsupported",
                "detail": "支持 InListPassiveTarget，贴卡后自动读取 UID" if core_ok else "射频初始化未通过",
            },
            {
                "name": "MIFARE Classic 认证 / 读写",
                "status": "needs_card" if core_ok else "unsupported",
                "detail": "支持 Key A/B 认证、块读写与扇区扫描；需贴 M1 卡",
            },
            {
                "name": "魔术卡 UID 写号 / UFUID 锁死",
                "status": "needs_card" if core_ok else "unsupported",
                "detail": "支持 CUID/Gen1a/Gen2/UFUID；需使用对应魔术卡并显式允许写 Block 0",
            },
            {
                "name": "ISO14443-B 二代身份证",
                "status": "needs_card" if core_ok else "unsupported",
                "detail": "需贴身份证，读取时会临时切换 Type B 寄存器并在结束时恢复 Type A",
            },
            {
                "name": "ISO14443-4 CPU 卡 / APDU",
                "status": "needs_card" if core_ok else "unsupported",
                "detail": "支持 T=CL 激活、APDU 透传、61xx/6Cxx 自动处理；需贴 CPU 卡",
            },
            {
                "name": "CIU 寄存器读写 / Type B 切换",
                "status": "experimental" if core_ok else "unsupported",
                "detail": "支持 WriteRegister/ReadRegister；非标准固件行为可能不同",
            },
            {
                "name": "Crypto1 darkside / nested",
                "status": "external",
                "detail": "标准 PN532 HSU 固件不直接暴露 nonce；需使用 tools/m1t/nfc-bin 的 libnfc 工具并先断开本软件串口",
            },
            {
                "name": "Hardnested 攻击",
                "status": "external",
                "detail": "需已知一个扇区密钥并通过外部 libnfc_hardnested 工具执行；本软件仅提供集成调用",
            },
        ]
        return {
            "device_name": self.device_name,
            "device_model": "PN532",
            "connection": "serial",
            "summary": "NXP PN532 双向读写器已连接" if core_ok else "PN532 响应异常",
            "firmware_version": self.firmware_info,
            "features": features,
        }

    def _parse_target_data(self, data: bytes) -> Optional[Dict[str, Any]]:
        """解析 InListPassiveTarget (0x4B) 应答载荷"""
        if len(data) < 1:
            return None

        nb_tg = data[0]
        if nb_tg == 0:
            return None

        if len(data) >= 6:
            tg = data[1]
            sens_res = data[2:4]  # ATQA
            sel_res = data[4]     # SAK
            nfcid_len = data[5]

            if len(data) >= 6 + nfcid_len:
                uid_bytes = data[6:6 + nfcid_len]
                self.cached_uid = uid_bytes

                atqa = sens_res
                sak = sel_res
                conversions = CardConverter.convert_uid(uid_bytes)

                is_cpu_card = bool((sak & 0x20 != 0) or sak in (0x20, 0x28, 0x38))
                ats_bytes = b""
                ats_hex = ""
                if len(data) > 6 + nfcid_len:
                    ats_bytes = data[6 + nfcid_len:]
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
        # Type B 探测会改写 12 组 CIU 寄存器，限制为每 2 秒最多一次，避免拖慢 M1 认证失败路径
        now = time.monotonic()
        if now - self._last_poll_time >= 2.0:
            self._last_poll_time = now
            try:
                id_card = self.read_id_card_uid(ser, timeout=0.25)
                if id_card:
                    return id_card
            except Exception as e:
                logger.debug("寻二代身份证异常: %s", e)

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

        def _is_ok(resp: Optional[bytes]) -> bool:
            # InCommunicateThru 返回载荷首字节为射频状态，0x00 才表示指令被卡片接受
            return bool(resp is not None and len(resp) >= 1 and resp[0] == 0x00)

        res = self._send_and_receive(ser, self.CMD_IN_COMMUNICATE_THRU, lock_frame, timeout=timeout)
        if _is_ok(res):
            return True
        res2 = self._send_and_receive(ser, self.CMD_IN_COMMUNICATE_THRU, bytes([0x43]), timeout=timeout)
        return _is_ok(res2)
