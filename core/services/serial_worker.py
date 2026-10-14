# -*- coding: utf-8 -*-
"""
PyMifareTool - 异步串口监听与多硬件驱动调度后台工作线程 (基于 PyQt6 QThread)
支持 PCR532 / PN532 双向全功能读写器、经典广播发卡器与虚拟离线卡
提供自动寻卡轮询、双向数据透传与任务独占控制
"""

import time
import threading
import serial
from typing import Optional, Dict, Any
from PyQt6.QtCore import QThread, pyqtSignal
from core.protocols.aabb import ReaderProtocol
from core.adapters import BaseReaderAdapter, PN532Adapter, BroadcasterAdapter, ReaderAdapterFactory


class SerialWorker(QThread):
    # 信号定义
    sig_connected = pyqtSignal(str, int)          # 端口, 波特率
    sig_disconnected = pyqtSignal(str)            # 错误原因
    sig_card_swiped = pyqtSignal(dict)            # 捕获卡片 (包含 uid, 换算字典, raw 等)
    sig_card_removed = pyqtSignal()               # 卡片移开射频天线
    sig_raw_log = pyqtSignal(str, str)            # 方向 (RX/TX/SYS/FRAME), Hex 或文本信息
    sig_status = pyqtSignal(str)                  # 状态栏提示
    sig_response = pyqtSignal(dict)               # 命令响应帧 (用于主动指令的异步响应)
    sig_device_identified = pyqtSignal(str, str)  # 设备名称, 固件信息

    def __init__(self, port: str = "COM3", baudrate: int = 115200, device_type: str = "auto"):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.device_type = device_type
        self.adapter: BaseReaderAdapter = ReaderAdapterFactory.create_adapter(device_type)

        self._running = False
        self._serial: Optional[serial.Serial] = None
        self._tx_lock = threading.Lock()
        self._cmd_lock = threading.Lock()

        # 请求-响应与独占锁机制 (防止批量读写时与后台主动轮询冲突)
        self._exclusive_lock = threading.Lock()
        self._exclusive_operation = False
        self._pending_cmd: Optional[int] = None
        self._response_event = threading.Event()
        self._last_response: Optional[Dict[str, Any]] = None
        self._last_polled_uid: Optional[bytes] = None

    def set_connection(self, port: str, baudrate: int, device_type: str = "auto"):
        self.port = port
        self.baudrate = baudrate
        self.device_type = device_type
        self.adapter = ReaderAdapterFactory.create_adapter(device_type)

    def is_connected(self) -> bool:
        """检查串口是否已连接且线程正在运行"""
        return self._running and self._serial is not None and self._serial.is_open

    def set_exclusive(self, enabled: bool):
        """进入/退出长任务独占模式 (独占时暂停后台自动寻卡轮询)"""
        with self._exclusive_lock:
            self._exclusive_operation = enabled

    def stop(self):
        self._running = False
        self._response_event.set()
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                pass
        self.wait(3000)

    def send_raw(self, data: bytes) -> bool:
        """线程安全地发送原始字节序列"""
        if not self.is_connected():
            return False
        try:
            with self._tx_lock:
                self._serial.write(data)
                self._serial.flush()
            hex_str = " ".join(f"{b:02X}" for b in data)
            self.sig_raw_log.emit("TX", hex_str)
            return True
        except Exception as e:
            self.sig_raw_log.emit("SYS", f"发送失败: {e}")
            return False

    def send_command(self, cmd: int, data: bytes = b"") -> bool:
        """向读卡器发送指令帧"""
        frame = ReaderProtocol.build_frame(cmd, data)
        return self.send_raw(frame)

    def send_and_wait(self, cmd: int, data: bytes = b"",
                      timeout: float = 2.0) -> Optional[Dict[str, Any]]:
        """发送指令并同步等待对应的响应帧 (向下兼容)"""
        if not self.is_connected():
            return None

        with self._cmd_lock:
            self._pending_cmd = cmd
            self._last_response = None
            self._response_event.clear()

        frame = ReaderProtocol.build_frame(cmd, data)
        if not self.send_raw(frame):
            with self._cmd_lock:
                self._pending_cmd = None
            return None

        got_response = self._response_event.wait(timeout)
        with self._cmd_lock:
            self._pending_cmd = None
            if got_response and self._last_response is not None:
                return self._last_response
        return None

    # ═════════════════════════════════════════════════════════════
    # 统一驱动透传接口 (供 CardOperationWorker 等上层业务直接调用)
    # ═════════════════════════════════════════════════════════════
    def authenticate(self, block: int, key_type: str, key: bytes, uid: bytes = b"", timeout: float = 0.35) -> bool:
        """执行扇区认证"""
        if not self.is_connected() or not self._serial:
            return False
        with self._tx_lock:
            return self.adapter.authenticate(self._serial, block, key_type, key, uid, timeout=timeout)

    def read_block(self, block: int, timeout: float = 0.35) -> Optional[bytes]:
        """读取物理块数据 (16 字节)"""
        if not self.is_connected() or not self._serial:
            return None
        with self._tx_lock:
            return self.adapter.read_block(self._serial, block, timeout=timeout)

    def write_block(self, block: int, data: bytes, timeout: float = 0.35) -> bool:
        """写入物理块数据 (16 字节)"""
        if not self.is_connected() or not self._serial:
            return False
        with self._tx_lock:
            return self.adapter.write_block(self._serial, block, data, timeout=timeout)

    def write_magic_block0(self, block0_data: bytes, magic_type: str = "CUID", timeout: float = 0.5) -> bool:
        """写入 Block 0 (魔术卡/UID 卡)"""
        if not self.is_connected() or not self._serial:
            return False
        with self._tx_lock:
            return self.adapter.write_magic_block0(self._serial, block0_data, magic_type=magic_type, timeout=timeout)

    def poll_card_once(self, timeout: float = 0.4) -> Optional[Dict[str, Any]]:
        """执行一次单次寻卡 (自适应 Type A 与 二代证 Type B)"""
        if not self.is_connected() or not self._serial:
            return None
        with self._tx_lock:
            return self.adapter.poll_card(self._serial, timeout=timeout)

    def read_id_card_once(self, timeout: float = 0.4) -> Optional[Dict[str, Any]]:
        """执行一次单次二代身份证 UID 读取 (ISO14443-B)"""
        if not self.is_connected() or not self._serial:
            return None
        with self._tx_lock:
            if hasattr(self.adapter, "read_id_card_uid"):
                return self.adapter.read_id_card_uid(self._serial, timeout=timeout)
        return None

    # ═════════════════════════════════════════════════════════════
    # 线程主循环
    # ═════════════════════════════════════════════════════════════
    def run(self):
        self._running = True
        self.sig_status.emit(f"正在尝试连接端口 {self.port} @ {self.baudrate} ...")

        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1
            )
            # 🚨 硬件红线 1: 物理复位保护，释放 DTR/RTS
            self._serial.dtr = False
            self._serial.rts = False
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
        except Exception as e:
            self._running = False
            self.sig_disconnected.emit(f"无法打开端口 {self.port}: {e}")
            return

        # 硬件自适应探测识别
        self.adapter = ReaderAdapterFactory.probe_device(self._serial, self.device_type)
        self.sig_connected.emit(self.port, self.baudrate)
        self.sig_device_identified.emit(self.adapter.device_name, self.adapter.firmware_info)
        self.sig_status.emit(f"已就绪: {self.adapter.device_name} ({self.adapter.firmware_info})")
        self.sig_raw_log.emit("SYS", f"硬件就绪: {self.adapter.device_name} | {self.adapter.firmware_info}")

        rx_buffer = bytearray()
        last_poll_time = 0.0

        while self._running:
            try:
                if not self._serial or not self._serial.is_open:
                    break

                now = time.time()

                # 1. 双向读写器模式下：执行周期性主动寻卡轮询 (250ms 周期，独占模式下挂起)
                if self.adapter.is_bidirectional:
                    with self._exclusive_lock:
                        is_exclusive = self._exclusive_operation

                    if not is_exclusive and (now - last_poll_time >= 0.25):
                        last_poll_time = now
                        with self._tx_lock:
                            card_info = self.adapter.poll_card(self._serial, timeout=0.15)

                        if card_info and "uid_bytes" in card_info:
                            curr_uid = card_info["uid_bytes"]
                            if curr_uid != self._last_polled_uid:
                                self._last_polled_uid = curr_uid
                                self.sig_card_swiped.emit(card_info)
                        else:
                            if self._last_polled_uid is not None:
                                self._last_polled_uid = None
                                self.sig_card_removed.emit()

                # 2. 接收串口流数据并分发
                in_waiting = self._serial.in_waiting
                if in_waiting > 0:
                    chunk = self._serial.read(in_waiting)
                    rx_buffer.extend(chunk)
                    hex_chunk = " ".join(f"{b:02X}" for b in chunk)
                    self.sig_raw_log.emit("RX", hex_chunk)

                    while len(rx_buffer) >= 4:
                        frame_info, remaining = self.adapter.parse_incoming(rx_buffer)
                        if frame_info:
                            rx_buffer = bytearray(remaining)
                            raw_bytes = frame_info.get("raw", b"")
                            if raw_bytes:
                                raw_hex = " ".join(f"{b:02X}" for b in raw_bytes)
                                self.sig_raw_log.emit("FRAME", f"解析到有效帧: {raw_hex}")

                            with self._cmd_lock:
                                if self._pending_cmd is not None and frame_info.get("cmd") == self._pending_cmd:
                                    self._last_response = frame_info
                                    self._response_event.set()

                            if "uid_bytes" in frame_info and not self.adapter.is_bidirectional:
                                self.sig_card_swiped.emit(frame_info)

                            self.sig_response.emit(frame_info)
                        else:
                            rx_buffer = bytearray(remaining)
                            break
                else:
                    time.sleep(0.02)
            except Exception as e:
                if self._running:
                    self.sig_disconnected.emit(f"通信异常断开: {e}")
                break

        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                pass
        self._running = False
