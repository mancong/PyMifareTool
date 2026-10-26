# -*- coding: utf-8 -*-
"""
PyMifareTool - 异步串口监听与多硬件驱动调度后台工作线程 (基于 PyQt6 QThread)
支持 PCR532 / PN532 双向全功能读写器、经典广播发卡器与虚拟离线卡
提供自动寻卡轮询、双向数据透传与任务独占控制
"""

import time
import logging
import threading
from typing import Optional, Dict, Any
from PyQt6.QtCore import QThread, pyqtSignal
from core.protocols.aabb import ReaderProtocol
from core.adapters import BaseReaderAdapter, PN532Adapter, BroadcasterAdapter, ReaderAdapterFactory
from core.transport.base import TransportLike
from core.transport.factory import TransportFactory
from core.services.capability_probe import build_device_capabilities

logger = logging.getLogger("pymifare.services.serial_worker")


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
    sig_device_capabilities = pyqtSignal(dict)    # 设备能力与工具链汇总

    def __init__(self, port: str = "COM3", baudrate: int = 115200, device_type: str = "auto"):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.device_type = device_type
        self.adapter: BaseReaderAdapter = ReaderAdapterFactory.create_adapter(device_type)

        # 连接通道类型 (serial / ble)
        self.conn_type: str = "serial"
        self.ble_address: str = ""

        self._running = False
        self._serial: Optional[TransportLike] = None
        self._tx_lock = threading.Lock()
        self._cmd_lock = threading.Lock()

        # 请求-响应与独占锁机制 (防止批量读写时与后台主动轮询冲突)
        self._exclusive_lock = threading.Lock()
        self._exclusive_operation = False
        self._pending_cmd: Optional[int] = None
        self._response_event = threading.Event()
        self._last_response: Optional[Dict[str, Any]] = None
        self._last_polled_uid: Optional[bytes] = None

        # 自动寻卡轮询开关与周期 (默认开启，间隔 300ms)
        self._auto_poll = True
        self._poll_interval = 0.3

        # 详细原始报文日志开关 (DEBUG 级别，默认关闭以保障高频操作性能)
        self._debug_logging = False

    def set_auto_poll(self, enabled: bool):
        """启用/停用后台自动寻卡轮询 (默认开启)"""
        self._auto_poll = bool(enabled)

    def set_poll_interval(self, interval_ms: int):
        """设置后台自动寻卡轮询周期 (毫秒，最小 50ms)"""
        try:
            ms = int(interval_ms)
        except (TypeError, ValueError):
            return
        self._poll_interval = max(0.05, ms / 1000.0)

    def set_debug_logging(self, enabled: bool):
        """启用/停用最详细的 TX/RX 原始报文日志 (DEBUG 级别，默认关闭以保障性能)"""
        self._debug_logging = bool(enabled)
        # 仅在 DEBUG 级别挂载底层日志回调，彻底避免非调试期的格式化与信号开销
        if getattr(self, "adapter", None) is not None:
            self.adapter.log_cb = self._emit_adapter_log if self._debug_logging else None

    def _emit_adapter_log(self, direction: str, text: str):
        """适配器底层同步收发日志回调 -> 桥接至 UI 原始报文日志"""
        if self._debug_logging:
            self.sig_raw_log.emit(direction, text)

    def set_connection(self, port: str, baudrate: int, device_type: str = "auto"):
        self.conn_type = "serial"
        self.port = port
        self.baudrate = baudrate
        self.device_type = device_type
        self.adapter = ReaderAdapterFactory.create_adapter(device_type)
        self.adapter.log_cb = self._emit_adapter_log if self._debug_logging else None

    def set_ble_connection(self, address: str, device_type: str = "auto"):
        self.conn_type = "ble"
        self.ble_address = address
        self.device_type = device_type
        self.adapter = ReaderAdapterFactory.create_adapter(device_type)
        self.adapter.log_cb = self._emit_adapter_log if self._debug_logging else None

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
            if self._debug_logging:
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

    def lock_ufuid_card(self, timeout: float = 0.5) -> bool:
        """锁死 UFUID 可变卡使其永久固化为普通 M1 卡"""
        if not self.is_connected() or not self._serial:
            return False
        with self._tx_lock:
            if hasattr(self.adapter, "lock_ufuid_card"):
                return self.adapter.lock_ufuid_card(self._serial, timeout=timeout)
        return False

    def poll_card_once(self, timeout: float = 0.4) -> Optional[Dict[str, Any]]:
        """执行一次单次寻卡 (自适应 Type A 与 二代证 Type B)"""
        if not self.is_connected() or not self._serial:
            return None
        with self._tx_lock:
            return self.adapter.poll_card(self._serial, timeout=timeout)

    def reactivate_target(self, timeout: float = 0.25) -> bool:
        """重新激活当前射频目标卡片 (解除 Mifare Classic HALT 挂起状态或恢复 Type A 射频信道)"""
        if not self.is_connected() or not self._serial:
            return False
        with self._tx_lock:
            if hasattr(self.adapter, "reactivate_target"):
                return self.adapter.reactivate_target(self._serial, timeout=timeout)
            elif hasattr(self.adapter, "poll_card"):
                card = self.adapter.poll_card(self._serial, timeout=timeout)
                return card is not None
        return False

    def read_id_card_once(self, timeout: float = 0.4) -> Optional[Dict[str, Any]]:
        """执行一次单次二代身份证 UID 读取 (ISO14443-B)"""
        if not self.is_connected() or not self._serial:
            return None
        with self._tx_lock:
            if hasattr(self.adapter, "read_id_card_uid"):
                return self.adapter.read_id_card_uid(self._serial, timeout=timeout)
        return None

    def is_card_present(self) -> bool:
        """检查当前目标卡片是否仍在射频场中"""
        if hasattr(self.adapter, "is_card_present"):
            try:
                return bool(self.adapter.is_card_present(self._serial))
            except TypeError:
                return bool(self.adapter.is_card_present())
        return True

    def log_operation(self, msg: str):
        """向串口原生数据流日志窗口上报操作记录 (OP 级别)"""
        self.sig_raw_log.emit("OP", msg)

    def send_apdu_once(self, apdu: bytes, timeout: float = 0.5) -> Dict[str, Any]:
        """向 CPU 卡发送一次原生 APDU 指令 (受 _tx_lock 线程保护，并同步发射操作与数据流日志)"""
        if not self.is_connected() or not self._serial:
            self.sig_raw_log.emit("OP", "[CPU卡] ❌ 发送失败: 读写器尚未连接")
            return {"ok": False, "error": "读写器未连接", "sw_desc": "读写器未连接", "data": b""}

        apdu_hex = " ".join(f"{b:02X}" for b in apdu)
        self.sig_raw_log.emit("OP", f"[CPU卡] 📤 TX APDU >> {apdu_hex}")

        with self._tx_lock:
            if hasattr(self.adapter, "send_apdu"):
                res = self.adapter.send_apdu(self._serial, apdu=apdu, timeout=timeout)
                if res.get("ok"):
                    sw = res.get("sw_hex", "")
                    sw_desc = res.get("sw_desc", "")
                    d_hex = res.get("data_hex", "")
                    rx_str = f"{d_hex} {sw}".strip()
                    self.sig_raw_log.emit("OP", f"[CPU卡] 📥 RX APDU << {rx_str} [状态: 0x{sw} {sw_desc}]")
                else:
                    self.sig_raw_log.emit("OP", f"[CPU卡] ❌ RX 异常: {res.get('error', '未知错误')}")
                return res

        self.sig_raw_log.emit("OP", "[CPU卡] ❌ 当前硬件驱动不支持 APDU 指令交换")
        return {"ok": False, "error": "当前硬件适配器不支持 APDU", "sw_desc": "硬件不支持", "data": b""}

    def read_cpu_card_once(self, timeout: float = 0.6) -> Dict[str, Any]:
        """执行一次 CPU 卡公开信息与交易流水读取 (受 _tx_lock 线程保护，并同步发射操作日志)"""
        if not self.is_connected() or not self._serial:
            self.sig_raw_log.emit("OP", "[CPU卡] ❌ 读取失败: 读写器尚未连接")
            return {"error": "读写器未连接"}

        self.sig_raw_log.emit("OP", "[CPU卡] 🔍 开始一键读取 CPU 卡公开数据 (PPSE/交通部/PBOC)...")
        with self._tx_lock:
            if hasattr(self.adapter, "read_cpu_card_public_info"):
                res = self.adapter.read_cpu_card_public_info(self._serial, timeout=timeout)
                if res.get("error"):
                    self.sig_raw_log.emit("OP", f"[CPU卡] ❌ 一键读取失败: {res.get('error')}")
                else:
                    c_num = res.get("card_number", "-")
                    bal = res.get("balance_str", "-")
                    tx_count = len(res.get("transactions", []))
                    app = res.get("app_name", "-")
                    self.sig_raw_log.emit(
                        "OP",
                        f"[CPU卡] ✨ 读取成功: 应用=[{app}] | 卡号=[{c_num}] | 余额=[{bal}] | 流水=[{tx_count}条]"
                    )
                return res

        self.sig_raw_log.emit("OP", "[CPU卡] ❌ 当前硬件驱动不支持 CPU 卡读取")
        return {"error": "当前硬件适配器不支持 CPU 卡读取"}

    def scan_cpu_card_tree_once(self, timeout: float = 0.35, progress_cb=None, abort_check=None) -> Dict[str, Any]:
        """执行一次 CPU 智能卡全文件系统深度树状扫描 (受 _tx_lock 保护，同步发射操作流)"""
        if not self.is_connected() or not self._serial:
            self.sig_raw_log.emit("OP", "[CPU卡] ❌ 树状扫描失败: 读写器尚未连接")
            return {"error": "读写器未连接"}

        self.sig_raw_log.emit("OP", "[CPU卡] 🌲 开始深度扫描 CPU 卡 COS 全文件系统 (SFI/FID 全目录)...")
        with self._tx_lock:
            if hasattr(self.adapter, "scan_cpu_card_tree"):
                res = self.adapter.scan_cpu_card_tree(
                    self._serial, timeout=timeout, progress_cb=progress_cb, abort_check=abort_check
                )
                stats = res.get("stats", {})
                if res.get("aborted"):
                    self.sig_raw_log.emit("OP", "[CPU卡] ⏹ 深度扫描已由用户中断或卡片已移开")
                else:
                    self.sig_raw_log.emit(
                        "OP",
                        f"[CPU卡] ✨ 文件树遍历完成! 发现 {stats.get('total_files', 0)} 个文件，"
                        f"可读 {stats.get('readable_bytes', 0)} 字节，流水记录 {stats.get('total_records', 0)} 条"
                    )
                return res

        self.sig_raw_log.emit("OP", "[CPU卡] ❌ 当前硬件驱动不支持全文件树扫描")
        return {"error": "当前硬件适配器不支持全文件树扫描"}

    # ═════════════════════════════════════════════════════════════
    # 线程主循环
    # ═════════════════════════════════════════════════════════════
    def run(self):
        self._running = True

        if getattr(self, "conn_type", "serial") == "ble":
            self.sig_status.emit(f"正在尝试建立蓝牙 BLE 连接: {self.ble_address} ...")
            try:
                self._serial = TransportFactory.create_transport("ble", address=self.ble_address, timeout=0.15)
                if not self._serial.open():
                    self._running = False
                    self.sig_disconnected.emit(f"无法建立蓝牙连接: {self.ble_address}")
                    return
            except Exception as e:
                self._running = False
                self.sig_disconnected.emit(f"无法建立蓝牙连接 {self.ble_address}: {e}")
                return
            conn_display_name = f"BLE:{self.ble_address}"
            conn_display_speed = 0
        else:
            self.sig_status.emit(f"正在尝试连接端口 {self.port} @ {self.baudrate} ...")
            try:
                self._serial = TransportFactory.create_transport(
                    "serial", port=self.port, baudrate=self.baudrate, timeout=0.1
                )
                # SerialTransport 内部严格执行硬件红线 1 (DTR/RTS=False) 并清空缓冲区
                if not self._serial.open():
                    self._running = False
                    self.sig_disconnected.emit(f"无法打开端口 {self.port}")
                    return
            except Exception as e:
                self._running = False
                self.sig_disconnected.emit(f"无法打开端口 {self.port}: {e}")
                return
            conn_display_name = self.port
            conn_display_speed = self.baudrate

        # 硬件自适应探测识别
        self.adapter = ReaderAdapterFactory.probe_device(self._serial, self.device_type)
        self.adapter.log_cb = self._emit_adapter_log if self._debug_logging else None
        self.sig_connected.emit(conn_display_name, conn_display_speed)
        self.sig_device_identified.emit(self.adapter.device_name, self.adapter.firmware_info)
        self.sig_status.emit(f"已就绪: {self.adapter.device_name} ({self.adapter.firmware_info})")
        self.sig_raw_log.emit("SYS", f"硬件就绪: {self.adapter.device_name} | {self.adapter.firmware_info}")

        try:
            capabilities = build_device_capabilities(
                self.adapter,
                connection=self.conn_type,
                port=conn_display_name,
                baudrate=conn_display_speed,
            )
            self.sig_device_capabilities.emit(capabilities)
        except Exception as exc:
            self.sig_raw_log.emit("SYS", f"设备能力汇总失败: {exc}")

        initial_rx = getattr(self.adapter, "initial_rx_data", b"") if self.adapter else b""
        rx_buffer = bytearray(initial_rx or b"")
        last_poll_time = 0.0

        while self._running:
            try:
                if not self._serial or not self._serial.is_open:
                    break

                now = time.time()

                # 1. 双向读写器模式下：执行周期性主动寻卡轮询 (250ms 周期，独占模式下挂起)
                is_exclusive = False
                if self.adapter.is_bidirectional:
                    with self._exclusive_lock:
                        is_exclusive = self._exclusive_operation

                    if self._auto_poll and not is_exclusive and (now - last_poll_time >= self._poll_interval):
                        last_poll_time = now
                        with self._tx_lock:
                            poll_timeout = 0.25  # 统一 250ms 超时，确保 CPU 卡 / 银行卡 RATS/ATS 协商充足
                            card_info = self.adapter.poll_card(self._serial, timeout=poll_timeout)

                        if card_info and "uid_bytes" in card_info:
                            curr_uid = card_info["uid_bytes"]
                            if curr_uid != self._last_polled_uid:
                                self._last_polled_uid = curr_uid
                                self.sig_card_swiped.emit(card_info)
                        else:
                            if self._last_polled_uid is not None:
                                self._last_polled_uid = None
                                self.sig_card_removed.emit()

                # 2. 独占长任务期间挂起后台接收循环，避免与上层同步收发争抢串口字节流
                if self.adapter.is_bidirectional and is_exclusive:
                    time.sleep(0.01)
                    continue

                # 3. 接收串口流数据并分发
                in_waiting = self._serial.in_waiting
                if in_waiting > 0:
                    chunk = self._serial.read(in_waiting)
                    rx_buffer.extend(chunk)
                    if self._debug_logging:
                        hex_chunk = " ".join(f"{b:02X}" for b in chunk)
                        self.sig_raw_log.emit("RX", hex_chunk)

                    while len(rx_buffer) >= 4:
                        frame_info, remaining = self.adapter.parse_incoming(rx_buffer)
                        if frame_info:
                            rx_buffer = bytearray(remaining)
                            if self._debug_logging:
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
                logger.debug("SerialWorker 轮询循环捕获异常: %s (running=%s)", e, self._running)
                if self._running:
                    self.sig_disconnected.emit(f"通信异常断开: {e}")
                break

        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception as e:
                logger.debug("SerialWorker 关闭底层传输失败: %s", e)
        self._running = False
