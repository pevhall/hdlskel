import logging
from abc import ABC, abstractmethod
from typing import Optional, Callable

CallbackFunc = Callable[[int, bytes], int]

class Regio(ABC):

    def __init__(self):
        self.log_ops = False
        self.prevent_dev_writes = False
        self.pre_write_callback_func : Optional[CallbackFunc] = None
        self.post_read_callback_func : Optional[CallbackFunc] = None
    
    @abstractmethod
    async def dev_write(self, addr : int, data : bytes) -> None:
        pass

    @abstractmethod
    async def dev_read(self, addr : int, size : int) -> bytes:
        pass

    async def write(self, addr : int, data : bytes) -> None:
        if self.log_ops:
            logging.debug('0x%x <-- %s',addr ,data)
        if self.pre_write_callback_func is not None:
            self.pre_write_callback_func(addr, data)
        if not self.prevent_dev_writes:
            await self.dev_write(addr, data)

    async def read(self, addr : int, size : int) -> bytes:
        data = await self.dev_read(addr, size)
        if self.log_ops:
            print()
            logging.debug(f'0x%x --> %s', addr, data)
        if self.post_read_callback_func is not None:
            self.post_read_callback_func(addr, data)
        return data

    def add_pre_write_callback_func(self, func : CallbackFunc):
        self.pre_write_callback_func = func

    def add_post_read_callback_func(self, func : CallbackFunc):
        self.post_read_callback_func = func

    def clear_pre_write_callback_func(self):
        self.pre_write_callback_func = None

    def clear_post_read_callback_func(self):
        self.post_read_callback_func = None
