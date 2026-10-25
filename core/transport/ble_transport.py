# -*- coding: utf-8 -*-
"""
PyMifareTool - 蓝牙无线传输实现 (BleTransport)
实现 ITransport 统一抽象接口，封装 bleak 异步低功耗蓝牙通信库
专为 Minicopy (WCH CH591F + NXP PN532) 及通用 BLE NFC 读写器设计
支持跨线程安全同步调用，与 pyserial 鸭子类型 100% 兼容
"""

import time
import queue
import asyncio
import threading
from typing import Optional, List, Dict, Any, Tuple
from .base import CallableBool, CallableInt, ITransport, TransportError

# 候选透明传输 GATT UUID 组合 (按优先级排序)
DEFAULT_GATT_PROFILES = [
    # 1. WCH CH59x 标准透传服务 (Minicopy 硬件实测确认)
    {
        "service": "0000ff00-0000-1000-8000-00805f9b34fb",
        "rx":      "0000ff01-0000-1000-8000-00805f9b34fb",  # Notify (设备 -> 主机)
        "tx":      "0000ff02-0000-1000-8000-00805f9b34fb",  # Write  (主机 -> 设备)
    },
    # 2. Minicopy 扩展服务
    {
        "service": "0000ae00-0000-1000-8000-00805f9b34fb",
        "rx":      "0000ae02-0000-1000-8000-00805f9b34fb",
        "tx":      "0000ae01-0000-1000-8000-00805f9b34fb",
    },
]


class BleTransport(ITransport):
    """
    线程安全的蓝牙低功耗 (BLE) 传输层实现
    通过专用后台 asyncio 事件循环线程，向外部提供与串口一致的同步 I/O 接口
    """

    def __init__(
        self,
        address: str = "",
        service_uuid: Optional[str] = None,
        tx_char_uuid: Optional[str] = None,
        rx_char_uuid: Optional[str] = None,
        timeout: float = 0.5,
        connect_timeout: float = 10.0
    ):
        self.address = address
        self.service_uuid = service_uuid
        self.tx_char_uuid = tx_char_uuid
        self.rx_char_uuid = rx_char_uuid
        self.timeout = timeout
        self.connect_timeout = connect_timeout

        # 接收缓冲区与条件锁
        self._rx_lock = threading.Lock()
        self._rx_cond = threading.Condition(self._rx_lock)
        self._rx_buffer = bytearray()

        # 后台事件循环与线程
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._client = None
        self._is_connected = False
        self._connect_error: Optional[str] = None
        self._tx_requires_response = False

        # 串口兼容性属性 (Duck-typing)
        self.dtr = False
        self.rts = False
        self.baudrate = 115200

    @property
    def port(self) -> str:
        return f"BLE:{self.address}"

    # ═════════════════════════════════════════════════════════
    # ITransport 核心接口实现
    # ═════════════════════════════════════════════════════════

    def open(self) -> bool:
        """打开 BLE 通信链路并开启通知订阅 (同步阻塞直到连接完成或超时)"""
        if self.is_open():
            self.close()

        with self._rx_lock:
            self._rx_buffer.clear()

        ready_event = threading.Event()
        self._connect_error = None

        def _thread_target():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self._async_connect(ready_event))
                self._loop.run_forever()
            except Exception as e:
                self._connect_error = str(e)
                ready_event.set()
            finally:
                try:
                    # 清理未完成的异步任务
                    pending = asyncio.all_tasks(self._loop)
                    for task in pending:
                        task.cancel()
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except Exception:
                    pass
                self._loop.close()

        self._loop_thread = threading.Thread(target=_thread_target, name=f"BleTransportLoop-{self.address}", daemon=True)
        self._loop_thread.start()

        # 等待后台连接就绪
        is_ready = ready_event.wait(timeout=self.connect_timeout)
        if not is_ready or not self._is_connected:
            self.close()
            return False
        return True

    async def _async_connect(self, ready_event: threading.Event):
        """后台异步连接与 GATT 特征自适应协商"""
        from bleak import BleakClient

        try:
            self._client = BleakClient(self.address, timeout=self.connect_timeout)
            await self._client.connect()

            if not self._client.is_connected:
                self._is_connected = False
                ready_event.set()
                return

            # 自适应特征值探测
            tx_uuid = self.tx_char_uuid
            rx_uuid = self.rx_char_uuid

            if not tx_uuid or not rx_uuid:
                # 遍历服务探测
                for s in self._client.services:
                    for c in s.characteristics:
                        props = c.properties
                        c_uuid = str(c.uuid).lower()
                        if "notify" in props and not rx_uuid:
                            if "ff01" in c_uuid or "ae02" in c_uuid or "ff0" in c_uuid:
                                rx_uuid = str(c.uuid)
                        if ("write" in props or "write-without-response" in props) and not tx_uuid:
                            if "ff02" in c_uuid or "ae01" in c_uuid or "ff0" in c_uuid:
                                tx_uuid = str(c.uuid)

            # 若仍未命中，取预置的默认值
            if not tx_uuid or not rx_uuid:
                for prof in DEFAULT_GATT_PROFILES:
                    rx_uuid = rx_uuid or prof["rx"]
                    tx_uuid = tx_uuid or prof["tx"]

            self.tx_char_uuid = tx_uuid
            self.rx_char_uuid = rx_uuid

            # 开启通知
            await self._client.start_notify(self.rx_char_uuid, self._on_ble_notification)
            self._is_connected = True
        except Exception as e:
            self._is_connected = False
            self._connect_error = str(e)
        finally:
            ready_event.set()

    def _on_ble_notification(self, sender, data: bytearray):
        """处理来自 BLE RX 特征的底层字节流"""
        with self._rx_lock:
            self._rx_buffer.extend(data)
            self._rx_cond.notify_all()

    def _on_rx_data(self, data: bytearray):
        """测试/直接注入底层字节流桩接口"""
        self._on_ble_notification(None, data)

    def close(self) -> None:
        """安全关闭通信链路"""
        self._is_connected = False
        if self._loop and self._loop.is_running():
            async def _cleanup():
                if self._client and self._client.is_connected:
                    try:
                        if self.rx_char_uuid:
                            await self._client.stop_notify(self.rx_char_uuid)
                    except Exception:
                        pass
                    try:
                        await self._client.disconnect()
                    except Exception:
                        pass

            try:
                future = asyncio.run_coroutine_threadsafe(_cleanup(), self._loop)
                future.result(timeout=2.0)
            except Exception:
                pass

            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._loop_thread and self._loop_thread.is_alive():
            self._loop_thread.join(timeout=2.5)

        self._loop_thread = None
        self._loop = None
        self._client = None

        with self._rx_lock:
            self._rx_buffer.clear()
            self._rx_cond.notify_all()

    @property
    def is_open(self) -> CallableBool:
        """链路是否处于可用开启状态 (支持属性访问与方法调用)"""
        try:
            client_connected = bool(self._client.is_connected) if self._client is not None else True
        except Exception:
            client_connected = False
        return CallableBool(bool(self._is_connected and client_connected))

    def write(self, data: bytes) -> int:
        """发送字节数据，返回已发送字节数。

        BLE 默认 ATT MTU 仅 23 字节，PN532 的 WriteRegister 帧可达 40+ 字节。
        若不分片，Windows 会直接抛出写入异常，导致二代证 CIU 调谐失败。
        这里按协商后的 MTU 自动分片，并在分片之间留出极短间隔保证透传模块有序处理。
        """
        if not self.is_open:
            raise TransportError("BLE 未连接或已关闭")
        if not self.tx_char_uuid:
            raise TransportError("BLE TX 写入特征值未初始化")

        async def _async_write():
            try:
                mtu = int(getattr(self._client, "mtu_size", 23) or 23)
            except Exception:
                mtu = 23
            # ATT 头占 3 字节；兼容未协商 MTU 的平台，最小按 20 字节分片
            chunk_size = max(20, mtu - 3)
            chunk_size = min(chunk_size, 244)

            for offset in range(0, len(data), chunk_size):
                chunk = data[offset:offset + chunk_size]
                try:
                    await self._client.write_gatt_char(
                        self.tx_char_uuid, chunk, response=self._tx_requires_response
                    )
                except Exception:
                    if self._tx_requires_response:
                        raise
                    # 部分固件只声明 Write(With Response)，自动降级重试
                    self._tx_requires_response = True
                    await self._client.write_gatt_char(
                        self.tx_char_uuid, chunk, response=True
                    )
                if offset + chunk_size < len(data):
                    await asyncio.sleep(0.005)

        try:
            future = asyncio.run_coroutine_threadsafe(_async_write(), self._loop)
            future.result(timeout=max(2.0, self.timeout * 4))
            return len(data)
        except Exception as e:
            raise TransportError(f"BLE 发送失败: {e}")

    def read(self, size: int = 1, timeout: Optional[float] = None) -> bytes:
        """读取指定长度字节"""
        if not self.is_open:
            raise TransportError("BLE 未连接或已关闭")

        to = timeout if timeout is not None else self.timeout
        deadline = time.time() + to

        with self._rx_lock:
            while len(self._rx_buffer) < size:
                remain = deadline - time.time()
                if remain <= 0:
                    break
                self._rx_cond.wait(timeout=remain)

            # 读取尽可能多的可用数据 (最多 size 字节)
            read_len = min(size, len(self._rx_buffer))
            ret = bytes(self._rx_buffer[:read_len])
            del self._rx_buffer[:read_len]
            return ret

    def flush(self) -> None:
        """刷新输入/输出缓冲区"""
        with self._rx_lock:
            self._rx_buffer.clear()
            self._rx_cond.notify_all()

    @property
    def in_waiting(self) -> CallableInt:
        """当前可读字节数 (支持方法调用与属性访问双向兼容)"""
        with self._rx_lock:
            return CallableInt(len(self._rx_buffer))

    # ═════════════════════════════════════════════════════════
    # 串口向下兼容接口 (Duck-typing with serial.Serial)
    # ═════════════════════════════════════════════════════════

    def reset_input_buffer(self) -> None:
        self.flush()

    def reset_output_buffer(self) -> None:
        pass

    # ═════════════════════════════════════════════════════════
    # 静态工具方法: 设备发现与扫描
    # ═════════════════════════════════════════════════════════

    @staticmethod
    def scan_devices(
        timeout: float = 2.5,
        callback: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        同步扫描周围的 BLE 读卡器与外设设备 (支持流式实时增量发现与智能分类)
        可在任意 GUI/工作线程中安全调用。
        返回: [{"name": str, "address": str, "rssi": int, "category_name": str, ...}, ...]
        """
        try:
            from bleak import BleakScanner
        except ImportError:
            return []

        from .ble_classifier import BleClassifier

        devices_map: Dict[str, Dict[str, Any]] = {}

        def _handle_detection(d, adv):
            addr = str(d.address).upper()
            raw_name = adv.local_name or d.name or ""
            classified = BleClassifier.classify(
                name=raw_name,
                address=addr,
                rssi=adv.rssi,
                service_uuids=adv.service_uuids,
                manufacturer_data=adv.manufacturer_data,
                details=d.details
            )

            dev_info = {
                "name": classified["friendly_name"],
                "raw_name": classified["raw_name"],
                "address": addr,
                "rssi": adv.rssi,
                "details": d.details,
                "service_uuids": adv.service_uuids or [],
                "manufacturer_data": adv.manufacturer_data or {},
                # 增强展示与分类字段
                "category_id": classified["category_id"],
                "category_name": classified["category_name"],
                "icon": classified["icon"],
                "tag": classified["tag"],
                "display_text": classified["display_text"],
                "tooltip": classified["tooltip"],
                "priority": classified["priority"],
                "is_reader": classified["is_reader"],
                "signal_quality": classified["signal_quality"],
            }

            # 若该设备已存在且新包未携带更丰富名称，保留旧的更有价值名称与分类
            if addr in devices_map:
                old = devices_map[addr]
                if not raw_name and old.get("raw_name"):
                    dev_info["raw_name"] = old["raw_name"]
                    dev_info["name"] = old["name"]
                    dev_info["display_text"] = old["display_text"]
                    dev_info["tooltip"] = old["tooltip"]
                    dev_info["category_id"] = old["category_id"]
                    dev_info["category_name"] = old["category_name"]
                    dev_info["icon"] = old["icon"]
                    dev_info["tag"] = old["tag"]
                    dev_info["priority"] = old["priority"]
                    dev_info["is_reader"] = old["is_reader"]

            devices_map[addr] = dev_info

            if callback:
                try:
                    callback(dev_info)
                except Exception:
                    pass

        async def _do_scan():
            scanner = BleakScanner(detection_callback=_handle_detection)
            await scanner.start()
            await asyncio.sleep(timeout)
            await scanner.stop()

            res = list(devices_map.values())
            # 排序规则: 读写器优先 (priority 小在前)，同级按信号强度降序 (-rssi)
            res.sort(key=lambda x: (x.get("priority", 99), -x.get("rssi", -100)))
            return res

        try:
            # 兼容当前已有 event loop 的情况
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                container = []
                def _runner():
                    sub_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(sub_loop)
                    try:
                        container.append(sub_loop.run_until_complete(_do_scan()))
                    finally:
                        sub_loop.close()
                t = threading.Thread(target=_runner)
                t.start()
                t.join(timeout=timeout + 2.0)
                return container[0] if container else []
            else:
                return asyncio.run(_do_scan())
        except Exception:
            return []

