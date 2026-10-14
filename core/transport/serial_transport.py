# -*- coding: utf-8 -*-
"""
PyMifareTool - 物理串口传输实现 (SerialTransport)
实现 ITransport 接口，封装 pyserial
严格执行硬件交互红线 1: 物理复位保护 (DTR=False, RTS=False)
"""

import time
import threading
import serial
from typing import Optional
from .base import ITransport, TransportError


class SerialTransport(ITransport):
    """线程安全的物理串口传输层"""

    def __init__(self, port: str = "COM3", baudrate: int = 115200, timeout: float = 0.5):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: Optional[serial.Serial] = None
        self._lock = threading.Lock()

    def open(self) -> bool:
        with self._lock:
            try:
                if self._serial and self._serial.is_open:
                    self._serial.close()

                # 打开串口并严格遵循硬件红线 1
                self._serial = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=self.timeout,
                    write_timeout=self.timeout,
                )

                # 🚨 硬件红线 1：强制保持 DTR / RTS 为 False，防止拉高复位脚锁死 MCU
                self._serial.dtr = False
                self._serial.rts = False

                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()
                return True
            except Exception as e:
                self._serial = None
                return False

    def close(self) -> None:
        with self._lock:
            if self._serial and self._serial.is_open:
                try:
                    self._serial.close()
                except Exception:
                    pass
            self._serial = None

    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def write(self, data: bytes) -> int:
        if not self.is_open():
            raise TransportError("串口未连接或已关闭")
        with self._lock:
            try:
                n = self._serial.write(data)
                self._serial.flush()
                return n
            except Exception as e:
                raise TransportError(f"串口写失败: {e}")

    def read(self, size: int = 1, timeout: Optional[float] = None) -> bytes:
        if not self.is_open():
            raise TransportError("串口未连接或已关闭")
        with self._lock:
            try:
                if timeout is not None:
                    old_to = self._serial.timeout
                    self._serial.timeout = timeout
                    data = self._serial.read(size)
                    self._serial.timeout = old_to
                    return data
                return self._serial.read(size)
            except Exception as e:
                raise TransportError(f"串口读失败: {e}")

    def flush(self) -> None:
        if self.is_open():
            with self._lock:
                try:
                    self._serial.reset_input_buffer()
                    self._serial.reset_output_buffer()
                except Exception:
                    pass

    def in_waiting(self) -> int:
        if not self.is_open():
            return 0
        try:
            return self._serial.in_waiting
        except Exception:
            return 0

    @property
    def raw_serial(self) -> Optional[serial.Serial]:
        """向下兼容提供原始 serial.Serial 句柄 (供既有适配器代码直接使用)"""
        return self._serial
