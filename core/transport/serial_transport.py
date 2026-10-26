# -*- coding: utf-8 -*-
"""
PyMifareTool - 物理串口传输实现 (SerialTransport)
实现 ITransport 接口，封装 pyserial
严格执行硬件交互红线 1: 物理复位保护 (DTR=False, RTS=False)
"""

import logging
import threading
import serial
from typing import Optional
from .base import CallableBool, CallableInt, ITransport, TransportError

logger = logging.getLogger("pymifare.transport.serial")


class SerialTransport(ITransport):
    """线程安全的物理串口传输层"""

    def __init__(self, port: str = "COM3", baudrate: int = 115200, timeout: float = 0.5):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: Optional[serial.Serial] = None
        self._lock = threading.Lock()
        self._dtr = False
        self._rts = False

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
                self._dtr = False
                self._rts = False

                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()
                return True
            except Exception:
                self._serial = None
                return False

    def close(self) -> None:
        with self._lock:
            if self._serial and self._serial.is_open:
                try:
                    self._serial.close()
                except Exception as e:
                    logger.debug("关闭底层串口对象异常: %s", e)
            self._serial = None

    @property
    def is_open(self) -> CallableBool:
        """链路是否处于可用开启状态 (支持属性访问与方法调用)"""
        return CallableBool(self._serial is not None and bool(self._serial.is_open))

    @property
    def dtr(self) -> bool:
        return self._dtr

    @dtr.setter
    def dtr(self, value: bool) -> None:
        self._dtr = bool(value)
        if self._serial is not None and self._serial.is_open:
            try:
                self._serial.dtr = self._dtr
            except Exception as e:
                logger.debug("DTR 设置失败 (硬件可能不支持): %s", e)

    @property
    def rts(self) -> bool:
        return self._rts

    @rts.setter
    def rts(self, value: bool) -> None:
        self._rts = bool(value)
        if self._serial is not None and self._serial.is_open:
            try:
                self._serial.rts = self._rts
            except Exception as e:
                logger.debug("RTS 设置失败 (硬件可能不支持): %s", e)

    def write(self, data: bytes) -> int:
        with self._lock:
            if not self._serial or not self._serial.is_open:
                raise TransportError("串口未连接或已关闭")
            try:
                n = self._serial.write(data)
                self._serial.flush()
                return n
            except Exception as e:
                raise TransportError(f"串口写失败: {e}")

    def read(self, size: int = 1, timeout: Optional[float] = None) -> bytes:
        with self._lock:
            if not self._serial or not self._serial.is_open:
                raise TransportError("串口未连接或已关闭")
            try:
                if timeout is not None:
                    old_to = self._serial.timeout
                    self._serial.timeout = timeout
                    try:
                        return self._serial.read(size)
                    finally:
                        self._serial.timeout = old_to
                return self._serial.read(size)
            except Exception as e:
                raise TransportError(f"串口读失败: {e}")

    def flush(self) -> None:
        """刷新输出缓冲区 (与 pyserial 语义一致)"""
        with self._lock:
            if self._serial and self._serial.is_open:
                try:
                    self._serial.flush()
                except Exception as e:
                    logger.debug("刷新串口输出缓冲区异常: %s", e)

    def reset_input_buffer(self) -> None:
        """清空输入缓冲区"""
        with self._lock:
            if self._serial and self._serial.is_open:
                try:
                    self._serial.reset_input_buffer()
                except Exception as e:
                    logger.debug("清空输入缓冲区异常: %s", e)

    def reset_output_buffer(self) -> None:
        """清空输出缓冲区"""
        with self._lock:
            if self._serial and self._serial.is_open:
                try:
                    self._serial.reset_output_buffer()
                except Exception as e:
                    logger.debug("清空输出缓冲区异常: %s", e)

    @property
    def in_waiting(self) -> CallableInt:
        """当前可读字节数 (支持属性访问与方法调用)"""
        if not self.is_open:
            return CallableInt(0)
        try:
            return CallableInt(self._serial.in_waiting)
        except Exception:
            return CallableInt(0)

    @property
    def raw_serial(self) -> Optional[serial.Serial]:
        """向下兼容提供原始 serial.Serial 句柄 (供既有适配器代码直接使用)"""
        return self._serial
