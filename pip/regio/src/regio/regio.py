import logging
from abc import ABC, abstractmethod
from typing import Optional, Callable

CallbackFunc = Callable[[int, bytes], int]

class Regio(ABC):

    def __init__(self):
        self._log_regio = False
        self._error_on_write = False
        self._pre_write_callback_func : Optional[CallbackFunc] = None
        self._post_read_callback_func : Optional[CallbackFunc] = None
        self._mtu : Optional[int] = None

    @property
    def mtu(self) -> Optional[int]:
        return self._mtu

    @mtu.setter
    def mtu(self, value: Optional[int]):
        self._mtu = value

    @property
    def log_regio(self) -> bool:
        return self._log_regio

    @log_regio.setter
    def log_regio(self, log_regio):
        self._log_regio = log_regio

    @abstractmethod
    async def dev_write(self, addr : int, data : bytes) -> None:
        pass

    @abstractmethod
    async def dev_read(self, addr : int, size : int) -> bytes:
        pass

    async def write(self, addr : int, data : bytes) -> None:
        if self._mtu is not None and len(data) > self._mtu:
            for offset in range(0, len(data), self._mtu):
                chunk = data[offset:offset + self._mtu]
                if self.log_regio:
                    logging.debug('0x%x <-- %s', addr + offset, chunk)
                if self._pre_write_callback_func is not None:
                    self._pre_write_callback_func(addr + offset, chunk)
                if not self._error_on_write:
                    await self.dev_write(addr + offset, chunk)
        else:
            if self.log_regio:
                logging.debug('0x%x <-- %s', addr, data)
            if self._pre_write_callback_func is not None:
                self._pre_write_callback_func(addr, data)
            if not self._error_on_write:
                await self.dev_write(addr, data)

    async def read(self, addr : int, size : int) -> bytes:
        if self._mtu is not None and size > self._mtu:
            collected = bytearray()
            for offset in range(0, size, self._mtu):
                chunk_size = min(self._mtu, size - offset)
                chunk = await self.dev_read(addr + offset, chunk_size)
                collected.extend(chunk)
                if self.log_regio:
                    logging.debug('0x%x --> %s', addr + offset, chunk)
                if self._post_read_callback_func is not None:
                    self._post_read_callback_func(addr + offset, chunk)
            data = bytes(collected)
        else:
            data = await self.dev_read(addr, size)
            if self.log_regio:
                logging.debug('0x%x --> %s', addr, data)
            if self._post_read_callback_func is not None:
                self._post_read_callback_func(addr, data)
        return data

    def add_pre_write_callback_func(self, func : CallbackFunc):
        self._pre_write_callback_func = func

    def add_post_read_callback_func(self, func : CallbackFunc):
        self._post_read_callback_func = func

    def clear_pre_write_callback_func(self):
        self._pre_write_callback_func = None

    def clear_post_read_callback_func(self):
        self._post_read_callback_func = None

# class CachedRegio(Regio):
#     def __init__( self, regio : Regio, size_bytes : int, base_addr = 0):
#         Regio.__init__(self)
#         self.cache = bytearray(size_bytes)

