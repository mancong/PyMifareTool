# -*- coding: utf-8 -*-
"""
PyMifareTool - 简易读卡器/广播发卡器 AA BB 二进制协议编解码器
对应旧款 8051 MCU + CV627 架构硬件的 AA BB 帧规范
"""

from typing import Optional, Tuple, Dict, Any, List
from .base import BaseProtocolCodec


class AABBProtocol(BaseProtocolCodec):
    """AA BB 协议帧编解码器 (无状态)"""

    HEADER = bytes([0xAA, 0xBB])

    # ═════════════════════════════════════════════════
    # 读卡器指令集 (CMD 字节定义)
    # ═════════════════════════════════════════════════
    CMD_AUTO_UID        = 0x01  # 自动上报 UID (读卡器主动推送, 无需发送)
    CMD_REQUEST_A       = 0x20  # ISO14443-3A 寻卡 (Request A / REQA)
    CMD_ANTICOLLISION   = 0x21  # 防冲突 (Anticollision) - 获取完整 UID
    CMD_SELECT          = 0x22  # 选卡 (Select)
    CMD_AUTO_READ       = 0x25  # 开启/关闭自动读卡模式
    CMD_AUTH_KEY_A      = 0x30  # 密钥 A 认证 (Authentication with Key A)
    CMD_AUTH_KEY_B      = 0x31  # 密钥 B 认证 (Authentication with Key B)
    CMD_READ_BLOCK      = 0x32  # 读取单个数据块 (Read Block, 16 bytes)
    CMD_WRITE_BLOCK     = 0x33  # 写入单个数据块 (Write Block, 16 bytes)
    CMD_INCREMENT       = 0x34  # 增值操作 (Value Block)
    CMD_DECREMENT       = 0x35  # 减值操作 (Value Block)
    CMD_RESTORE         = 0x36  # 恢复 (Restore)
    CMD_TRANSFER        = 0x37  # 转存 (Transfer)
    CMD_HALT            = 0x40  # 停止通信 (Halt)
    CMD_SET_BAUDRATE    = 0x50  # 设置波特率
    CMD_LED_CONTROL     = 0x60  # LED 控制
    CMD_BUZZER_CONTROL  = 0x61  # 蜂鸣器控制
    CMD_GET_VERSION     = 0xF0  # 获取固件版本

    # 响应状态码
    STATUS_SUCCESS      = 0x00
    STATUS_NO_CARD      = 0x01
    STATUS_AUTH_FAIL    = 0x02
    STATUS_READ_FAIL    = 0x03
    STATUS_WRITE_FAIL   = 0x04
    STATUS_ERROR        = 0xFF

    @staticmethod
    def calc_bcc(data: bytes) -> int:
        """计算异或校验和 (从 Length 字节开始至 Data 结束)"""
        res = 0
        for b in data:
            res ^= b
        return res

    @classmethod
    def build_frame(cls, cmd: int, data: bytes = b"") -> bytes:
        """
        构建一个完整的 AA BB 帧
        帧结构: [AA BB] [LEN] [CMD] [DATA...] [BCC]
        LEN = 1(CMD) + len(DATA) + 1(BCC)
        """
        length = 1 + len(data) + 1  # CMD + DATA + BCC
        payload = bytes([length, cmd]) + data
        bcc = cls.calc_bcc(payload)
        return cls.HEADER + payload + bytes([bcc])

    @classmethod
    def build_request_a(cls) -> bytes:
        """构建寻卡指令帧 (Request A)"""
        return cls.build_frame(cls.CMD_REQUEST_A, bytes([0x26]))

    @classmethod
    def build_anticollision(cls) -> bytes:
        """构建防冲突指令帧 (Anticollision)"""
        return cls.build_frame(cls.CMD_ANTICOLLISION)

    @classmethod
    def build_select(cls, uid: bytes) -> bytes:
        """构建选卡指令帧 (Select)"""
        return cls.build_frame(cls.CMD_SELECT, uid)

    @classmethod
    def build_auth(cls, block: int, key_type: str, key: bytes, uid: bytes = b"") -> bytes:
        """构建密钥认证指令帧"""
        cmd = cls.CMD_AUTH_KEY_A if key_type.upper() == 'A' else cls.CMD_AUTH_KEY_B
        data = bytes([block]) + key
        if uid:
            data += uid
        return cls.build_frame(cmd, data)

    @classmethod
    def build_read_block(cls, block: int) -> bytes:
        """构建读取数据块指令帧"""
        return cls.build_frame(cls.CMD_READ_BLOCK, bytes([block]))

    @classmethod
    def build_write_block(cls, block: int, block_data: bytes) -> bytes:
        """构建写入数据块指令帧"""
        if len(block_data) != 16:
            raise ValueError("写入数据必须为 16 字节")
        return cls.build_frame(cls.CMD_WRITE_BLOCK, bytes([block]) + block_data)

    @classmethod
    def build_halt(cls) -> bytes:
        """构建停止通信指令帧"""
        return cls.build_frame(cls.CMD_HALT)

    @classmethod
    def build_get_version(cls) -> bytes:
        """构建获取固件版本指令帧"""
        return cls.build_frame(cls.CMD_GET_VERSION)

    @classmethod
    def build_led_control(cls, state: int) -> bytes:
        """构建 LED 控制指令 (0=关, 1=开, 2=闪烁)"""
        return cls.build_frame(cls.CMD_LED_CONTROL, bytes([state]))

    @classmethod
    def build_buzzer_control(cls, duration_ms: int = 100) -> bytes:
        """构建蜂鸣器控制指令"""
        hi = (duration_ms >> 8) & 0xFF
        lo = duration_ms & 0xFF
        return cls.build_frame(cls.CMD_BUZZER_CONTROL, bytes([hi, lo]))

    @classmethod
    def parse_frame(cls, buffer: bytes) -> Tuple[Optional[Dict[str, Any]], bytes]:
        """
        从接收缓冲区中解析完整帧
        帧结构: [AA BB] [LEN] [CMD] [DATA...] [BCC]
        返回: (解析字典, 剩余未消费缓冲区)
        """
        idx = buffer.find(cls.HEADER)
        if idx == -1:
            return None, buffer[-1:] if len(buffer) > 0 else b""

        buffer = buffer[idx:]
        if len(buffer) < 4:
            return None, buffer

        length = buffer[2]
        total_len = 3 + length
        if len(buffer) < total_len:
            return None, buffer

        frame = buffer[:total_len]
        remaining = buffer[total_len:]

        cmd = frame[3]
        payload = frame[4:-1]
        received_bcc = frame[-1]

        calculated_bcc = cls.calc_bcc(frame[2:-1])
        if calculated_bcc != received_bcc:
            return None, buffer[2:]

        result: Dict[str, Any] = {
            "cmd": cmd,
            "length": length,
            "payload": payload,
            "raw": frame,
            "status": None
        }

        # CMD 0x01: 自动读卡 UID 上报
        if cmd == cls.CMD_AUTO_UID and len(payload) >= 4:
            if len(payload) in (7, 10):
                uid_bytes = payload
            else:
                uid_bytes = payload[:4]
            result["uid_bytes"] = uid_bytes
            result["uid_len"] = len(payload)

        # 寻卡响应
        elif cmd == cls.CMD_REQUEST_A and len(payload) >= 1:
            result["status_code"] = payload[0]
            if payload[0] == cls.STATUS_SUCCESS:
                result["status"] = "success"
                result["ok"] = True
                if len(payload) >= 3:
                    result["atqa"] = payload[1:3]
            else:
                result["status"] = "no_card"
                result["ok"] = False

        # 防冲突响应
        elif cmd == cls.CMD_ANTICOLLISION and len(payload) >= 1:
            result["status_code"] = payload[0]
            if payload[0] == cls.STATUS_SUCCESS and len(payload) >= 5:
                result["status"] = "success"
                result["ok"] = True
                uid_bytes = payload[1:5]
                result["uid_bytes"] = uid_bytes
            else:
                result["status"] = "fail"
                result["ok"] = False

        # 认证响应
        elif cmd in (cls.CMD_AUTH_KEY_A, cls.CMD_AUTH_KEY_B) and len(payload) >= 1:
            result["status_code"] = payload[0]
            result["ok"] = (payload[0] == cls.STATUS_SUCCESS)
            result["status"] = "success" if payload[0] == cls.STATUS_SUCCESS else "auth_fail"

        # 读块响应
        elif cmd == cls.CMD_READ_BLOCK and len(payload) >= 1:
            result["status_code"] = payload[0]
            result["ok"] = (payload[0] == cls.STATUS_SUCCESS)
            if payload[0] == cls.STATUS_SUCCESS and len(payload) >= 17:
                result["status"] = "success"
                result["block_data"] = payload[1:17]
                result["data"] = payload[1:17]  # 兼容旧代码 resp.get("data")
            else:
                result["status"] = "read_fail"

        # 写块响应
        elif cmd == cls.CMD_WRITE_BLOCK and len(payload) >= 1:
            result["status_code"] = payload[0]
            result["ok"] = (payload[0] == cls.STATUS_SUCCESS)
            result["status"] = "success" if payload[0] == cls.STATUS_SUCCESS else "write_fail"

        # 固件版本响应
        elif cmd == cls.CMD_GET_VERSION and len(payload) > 0:
            result["status_code"] = cls.STATUS_SUCCESS
            result["ok"] = True
            result["status"] = "success"
            result["version"] = payload.decode("ascii", errors="replace")

        return result, remaining


# 向后兼容别名
ReaderProtocol = AABBProtocol
