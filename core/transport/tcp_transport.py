# -*- coding: utf-8 -*-
"""
PyMifareTool - TCP 透传与 Modbus TCP 传输实现
用于通过串口服务器 / 工业网关远程访问读卡器
"""

import socket
import threading
import time
from typing import Optional

from .base import CallableBool, CallableInt, ITransport, TransportError


class TcpTransport(ITransport):
    """线程安全的 TCP 字节流传输层"""

    def __init__(self, host: str = "127.0.0.1", port: int = 5000,
                 timeout: float = 0.5, connect_timeout: Optional[float] = None):
        self.host = host
        self.port = int(port)
        self.timeout = timeout
        self.connect_timeout = connect_timeout if connect_timeout is not None else max(timeout, 2.0)
        self.baudrate = 0
        self._sock: Optional[socket.socket] = None
        self._lock = threading.RLock()
        self._rx_buffer = bytearray()
        self._dtr = False
        self._rts = False

    def open(self) -> bool:
        with self._lock:
            self.close()
            try:
                sock = socket.create_connection(
                    (self.host, self.port),
                    timeout=self.connect_timeout,
                )
                sock.settimeout(self.timeout)
                self._sock = sock
                self._rx_buffer.clear()
                return True
            except Exception:
                self._sock = None
                return False

    def close(self) -> None:
        with self._lock:
            sock = self._sock
            self._sock = None
            self._rx_buffer.clear()
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    sock.close()
                except Exception:
                    pass

    @property
    def is_open(self) -> CallableBool:
        return CallableBool(self._sock is not None)

    @property
    def dtr(self) -> bool:
        return self._dtr

    @dtr.setter
    def dtr(self, value: bool) -> None:
        self._dtr = bool(value)

    @property
    def rts(self) -> bool:
        return self._rts

    @rts.setter
    def rts(self, value: bool) -> None:
        self._rts = bool(value)

    def _fill_buffer(self) -> None:
        if self._sock is None:
            return
        try:
            self._sock.setblocking(False)
            try:
                chunk = self._sock.recv(4096)
            finally:
                self._sock.setblocking(True)
                self._sock.settimeout(self.timeout)
            if chunk:
                self._rx_buffer.extend(chunk)
        except (BlockingIOError, socket.timeout):
            pass
        except Exception:
            pass

    @property
    def in_waiting(self) -> CallableInt:
        self._fill_buffer()
        return CallableInt(len(self._rx_buffer))

    def write(self, data: bytes) -> int:
        if self._sock is None:
            raise TransportError("TCP 链路未连接或已关闭")
        with self._lock:
            try:
                self._sock.sendall(data)
                return len(data)
            except Exception as e:
                raise TransportError(f"TCP 写失败: {e}")

    def read(self, size: int = 1, timeout: Optional[float] = None) -> bytes:
        if self._sock is None:
            raise TransportError("TCP 链路未连接或已关闭")
        if size <= 0:
            return b""

        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        with self._lock:
            while len(self._rx_buffer) < size:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    self._sock.settimeout(remaining)
                    chunk = self._sock.recv(4096)
                except socket.timeout:
                    break
                except Exception as e:
                    raise TransportError(f"TCP 读失败: {e}")
                finally:
                    if self._sock is not None:
                        try:
                            self._sock.settimeout(self.timeout)
                        except Exception:
                            pass
                if not chunk:
                    break
                self._rx_buffer.extend(chunk)

            result = bytes(self._rx_buffer[:size])
            del self._rx_buffer[:size]
            return result

    def flush(self) -> None:
        return None

    def reset_input_buffer(self) -> None:
        with self._lock:
            self._rx_buffer.clear()

    def reset_output_buffer(self) -> None:
        return None


class ModbusTcpTransport(TcpTransport):
    """Modbus TCP 网关透传 (默认 502 端口，按原始字节流处理)"""

    def __init__(self, host: str = "127.0.0.1", port: int = 502,
                 timeout: float = 0.5, connect_timeout: Optional[float] = None):
        super().__init__(host=host, port=port, timeout=timeout,
                         connect_timeout=connect_timeout)
