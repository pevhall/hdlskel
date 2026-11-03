import asyncio
import io
import threading
from abc import ABC, abstractmethod
from typing import Optional, Callable

CallbackFunc = Callable[[int, bytes], int]

REGIO_MTU_DEFAULT : int = 4096

class Regio(ABC):

    def __init__(self):
        self._log_regio = False
        self._error_on_write = False
        self._pre_write_callback_func : Optional[CallbackFunc] = None
        self._post_read_callback_func : Optional[CallbackFunc] = None
        self._mtu : int = REGIO_MTU_DEFAULT

    @property
    def mtu(self) -> int:
        return self._mtu

    @mtu.setter
    def mtu(self, value: int):
        assert value > 0
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

    def first_chunk_size_to_align(self, addr : int) -> int:
        chunk_size = self.mtu
        mtu_addr_off = (addr % self.mtu)
        if mtu_addr_off != 0: #Align eof of op with MTU
            chunk_size -= mtu_addr_off
        return chunk_size

    async def write(self, addr : int, data : bytes) -> None:
        chunk_size = self.first_chunk_size_to_align(addr)
        done_size = 0
        size = len(data)
        while done_size < size:
            chunk_size = min(chunk_size, size - done_size)
            chunk = data[done_size:done_size + chunk_size]
            await self._write(addr+done_size, chunk)
            done_size += chunk_size
            chunk_size = self.mtu

    async def read(self, addr : int, size : int) -> bytes:
        collected = bytearray()
        chunk_size = self.first_chunk_size_to_align(addr)
        done_size = 0
        while done_size < size:
            chunk_size = min(chunk_size, size - done_size)
            chunk = await self._read(addr+done_size, chunk_size)
            collected.extend(chunk)
            done_size += chunk_size
            chunk_size = self.mtu

        data = bytes(collected)
        return data

    async def _write(self, addr : int, data : bytes) -> None:
        if self.log_regio:
            print('0x%x <-- %s' % (addr, data) )
        if self._pre_write_callback_func is not None:
            self._pre_write_callback_func(addr, data)
        if not self._error_on_write:
            await self.dev_write(addr, data)

    async def _read(self, addr : int, size:int) -> bytes:
        data = await self.dev_read(addr, size)
        if self.log_regio:
            print('0x%x --> %s' % (addr, data) )
        assert( len(data) == size )
        if self._post_read_callback_func is not None:
            self._post_read_callback_func(addr, data)
        return data

    async def write_from_read_file(self, addr : int, f : io.IOBase, size : Optional[int] = None) -> None:
        done_size = 0
        chunk_size : int = self.first_chunk_size_to_align(addr)
        while size is None or done_size < size:
            if size is not None:
                size_left = size - done_size
                if chunk_size > size_left:
                    chunk_size = size_left
            chunk = f.read(chunk_size)
            if not chunk:
                break # reached EOF
            await self._write(addr, chunk)
            addr += len(chunk)
            done_size += len(chunk)
            if chunk_size != len(chunk): # reached EOF
                break
            chunk_size = self.mtu
        if size is not None:
            assert done_size == size

    async def read_to_write_file(self, addr : int, f : io.IOBase, size : int) -> None:
        done_size = 0
        chunk_size = self.first_chunk_size_to_align(addr)
        while done_size < size:
            size_left = size - done_size
            if chunk_size > size_left:
                chunk_size = size_left
            chunk = await self._read(addr, chunk_size)
            assert chunk_size == len(chunk)
            f.write(chunk)
            addr += chunk_size
            done_size += chunk_size
            chunk_size = self.mtu


    def add_pre_write_callback_func(self, func : CallbackFunc):
        self._pre_write_callback_func = func

    def add_post_read_callback_func(self, func : CallbackFunc):
        self._post_read_callback_func = func

    def clear_pre_write_callback_func(self):
        self._pre_write_callback_func = None

    def clear_post_read_callback_func(self):
        self._post_read_callback_func = None

