import asyncio
import io
import threading
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
                    print('0x%x <-- %s'%(addr + offset, chunk))
                if self._pre_write_callback_func is not None:
                    self._pre_write_callback_func(addr + offset, chunk)
                if not self._error_on_write:
                    await self.dev_write(addr + offset, chunk)
        else:
            if self.log_regio:
                print('0x%x <-- %s' % (addr, data) )
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
                    print('0x%x --> %s' % (addr + offset, chunk) )
                if self._post_read_callback_func is not None:
                    self._post_read_callback_func(addr + offset, chunk)
            data = bytes(collected)
        else:
            data = await self.dev_read(addr, size)
            if self.log_regio:
                print('0x%x --> %s', (addr, data) )
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


class RegioFile(io.RawIOBase):
    """File-like (io.RawIOBase) view over a contiguous region of a Regio device.

    Streams a large file starting at `base_addr`, breaking every transfer into
    operations of at most `regio.mtu` bytes. Only one MTU-sized chunk is held
    in memory at a time, so files much larger than RAM can be read/written.

    The underlying Regio API is async, while io.RawIOBase is synchronous. This
    class bridges the two by running a dedicated asyncio event loop on a
    background thread, so RegioFile is safe to use from plain synchronous code
    as well as from code already running inside an event loop. Purely async
    callers can use `aread()` / `awrite()` instead.

    Example (upload a large file into a device region):
        with open('firmware.bin', 'rb') as fh, \
             RegioFile(regio, base_addr=0x1000_0000, mode='wb',
                       size=os.path.getsize('firmware.bin')) as rf:
            while chunk := fh.read(1 << 20):
                rf.write(chunk)

    Example (dump a device region to a file):
        with RegioFile(regio, base_addr=0x1000_0000, size=0x100000) as rf, \
             open('dump.bin', 'wb') as fh:
            while chunk := rf.read(1 << 20):
                fh.write(chunk)
    """

    def __init__(self, regio: Regio, base_addr: int = 0, mode: str = 'rb',
                 size: Optional[int] = None):
        super().__init__()
        if not any(c in mode for c in 'rwax'):
            raise ValueError(f'invalid mode: {mode!r}')
        self._regio = regio
        self._base_addr = base_addr
        self._mode = mode.replace('b', '')
        # Logical length of the region; None means unbounded (no EOF).
        self._size = size
        self._pos = 0
        # Dedicated background event loop to drive the async Regio API.
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever,
                                        name='RegioFile-loop', daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _check_open(self):
        if self.closed:
            raise ValueError('I/O operation on closed file')

    def _run(self, coro):
        """Run an async Regio coroutine to completion from sync code."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def _chunk_limit(self, want: int) -> int:
        """Max bytes per single device operation (MTU-bounded)."""
        mtu = self._regio.mtu
        return want if mtu is None else min(want, mtu)

    def _remaining(self) -> int:
        """Bytes left in the logical file, or -1 if size is unbounded."""
        if self._size is None:
            return -1
        return max(0, self._size - self._pos)

    # ------------------------------------------------------------------
    # io.RawIOBase interface
    # ------------------------------------------------------------------
    def readable(self) -> bool:
        return 'r' in self._mode or '+' in self._mode

    def writable(self) -> bool:
        return any(c in self._mode for c in 'wax+')

    def seekable(self) -> bool:
        return True

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def base_addr(self) -> int:
        return self._base_addr

    def tell(self) -> int:
        self._check_open()
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        self._check_open()
        if whence == io.SEEK_SET:
            pos = offset
        elif whence == io.SEEK_CUR:
            pos = self._pos + offset
        elif whence == io.SEEK_END:
            if self._size is None:
                raise OSError('cannot seek relative to end of an unbounded region')
            pos = self._size + offset
        else:
            raise ValueError(f'invalid whence: {whence!r}')
        if pos < 0:
            raise OSError('negative seek position')
        self._pos = pos
        return pos

    def truncate(self, size: Optional[int] = None) -> int:
        self._check_open()
        if not self.writable():
            raise io.UnsupportedOperation('not writable')
        new_size = self._pos if size is None else size
        if new_size < 0:
            raise ValueError('negative truncate size')
        self._size = new_size
        return new_size

    def flush(self):
        self._check_open()
        # Device writes are performed immediately; nothing to buffer.

    def readinto(self, b) -> int:
        self._check_open()
        if not self.readable():
            raise io.UnsupportedOperation('not readable')
        want = len(b)
        if want == 0:
            return 0
        remaining = self._remaining()
        if remaining == 0:
            return 0  # EOF
        if remaining > 0:
            want = min(want, remaining)
        total = 0
        while total < want:
            n = self._chunk_limit(want - total)
            chunk = self._run(self._regio.dev_read(self._base_addr + self._pos + total, n))
            b[total:total + len(chunk)] = chunk
            total += len(chunk)
            if self._regio._post_read_callback_func is not None:
                self._regio._post_read_callback_func(self._base_addr + self._pos + total - len(chunk), chunk)
            if self._regio.log_regio:
                print('0x%x --> %s' % (self._base_addr + self._pos + total - len(chunk), chunk))
            if len(chunk) < n:
                break  # short read: treat as EOF for this region
        self._pos += total
        return total

    def write(self, b) -> int:
        self._check_open()
        if not self.writable():
            raise io.UnsupportedOperation('not writable')
        want = len(b)
        if want == 0:
            return 0
        remaining = self._remaining()
        if remaining == 0:
            raise OSError('no space left in region')
        if remaining > 0:
            want = min(want, remaining)
        total = 0
        while total < want:
            n = self._chunk_limit(want - total)
            chunk = bytes(b[total:total + n])
            addr = self._base_addr + self._pos + total
            if self._regio.log_regio:
                print('0x%x <-- %s' % (addr, chunk))
            if self._regio._pre_write_callback_func is not None:
                self._regio._pre_write_callback_func(addr, chunk)
            if not self._regio._error_on_write:
                self._run(self._regio.dev_write(addr, chunk))
            total += n
        self._pos += total
        return total

    # ------------------------------------------------------------------
    # Async-friendly variants (use these from inside an event loop)
    # ------------------------------------------------------------------
    async def aread(self, size: int = -1) -> bytes:
        """Async read of up to `size` bytes (-1 = to end of bounded region)."""
        self._check_open()
        if not self.readable():
            raise io.UnsupportedOperation('not readable')
        remaining = self._remaining()
        if remaining == 0:
            return b''
        if size < 0:
            if remaining < 0:
                raise ValueError('size must be given for an unbounded region')
            size = remaining
        if remaining > 0:
            size = min(size, remaining)
        data = await self._regio.read(self._base_addr + self._pos, size)
        self._pos += len(data)
        return data

    async def awrite(self, data: bytes) -> int:
        """Async write of `data` at the current position."""
        self._check_open()
        if not self.writable():
            raise io.UnsupportedOperation('not writable')
        remaining = self._remaining()
        if remaining >= 0:
            data = data[:remaining]
        if not data:
            return 0
        await self._regio.write(self._base_addr + self._pos, data)
        self._pos += len(data)
        return len(data)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def close(self):
        if not self.closed:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=2.0)
            self._loop.close()
        super().close()

