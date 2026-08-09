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
        if self._log_regio:
            logging.debug('0x%x <-- %s',addr ,data)
        if self._pre_write_callback_func is not None:
            self._pre_write_callback_func(addr, data)
        if not self._error_on_write:
            await self.dev_write(addr, data)

    async def read(self, addr : int, size : int) -> bytes:
        data = await self.dev_read(addr, size)
        if self._log_regio:
            logging.debug(f'0x%x --> %s', addr, data)
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

