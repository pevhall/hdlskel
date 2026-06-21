
import asyncio
from typing import Optional

from . import Regio
from .tcp import RQST_HEAD_SIZE, RqstHead, RplyHead, unpack_rply_head, pack_rqst_head, ADDR_MAX, SIZE_MAX, PORT_DEFAULT


class RegioTcpClient(Regio):
    """
    TCP client implementing Regio interface.
    Connects to a BinaryRegioServer and performs read/write operations.
    """
    def __init__(self, host: str = "127.0.0.1", port: int = PORT_DEFAULT, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if self._writer is not None and not self._writer.is_closing():
            return
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port),
            timeout=self.timeout
        )

    async def close(self) -> None:
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            finally:
                self._reader = None
                self._writer = None

    async def _send_request_and_get_response(self, req_bytes: bytes) -> bytes:
        if self._writer is None or self._writer.is_closing():
            await self.connect()
        assert self._writer is not None and self._reader is not None
        self._writer.write(req_bytes)
        await self._writer.drain()
        # Read response header
        header = await asyncio.wait_for(self._reader.readexactly(RQST_HEAD_SIZE), timeout=self.timeout)
        return header

    def check_size(self, size : int):
        if size > SIZE_MAX or size <= 0:
            raise ValueError(f"size {size}")

    def check_addr(self, addr : int):
        if addr > ADDR_MAX or addr < 0:
            raise ValueError(f"addr {addr}")

    async def write(self, addr: int, data: bytes) -> None:
        size = len(data)

        self.check_addr(addr)
        self.check_size(size)
        async with self._lock:
            # Build request header with flag_we = 1
            rqst_head = RqstHead(flag_we=True, addr=addr, size=size)

            rqst_head_bytes = pack_rqst_head(rqst_head)
            # Send header + payload
            if self._writer is None or self._writer.is_closing():
                await self.connect()
            assert self._writer is not None and self._reader is not None
            self._writer.write(rqst_head_bytes + data)
            await self._writer.drain()

            # Read response header
            # rply_head_bytes = await asyncio.wait_for(self._reader.readexactly(RQST_HEAD_SIZE), timeout=self.timeout)
            #
            # rply_head = unpack_rply_head(rply_head_bytes)
            # if rply_head.flag_error != 0:
            #     raise IOError("server reported error on write")
            # Optionally consume any trailing bytes if server sends them. Server sends no payload for write.
            return None

    async def read(self, addr: int, size: int) -> bytes:
        self.check_addr(addr)
        self.check_size(size)
        async with self._lock:
            rqst_head = RqstHead(flag_we=False, addr=addr, size=size)

            # Build request header with flag_we = 0
            rqst_head_bytes = pack_rqst_head(rqst_head)
            if self._writer is None or self._writer.is_closing():
                await self.connect()
            assert self._writer is not None and self._reader is not None
            self._writer.write(rqst_head_bytes)
            await self._writer.drain()
            # Read response header
            rply_head_bytes = await asyncio.wait_for(self._reader.readexactly(RQST_HEAD_SIZE), timeout=self.timeout)
            rply_head = unpack_rply_head(rply_head_bytes)
            # sync, flag_error, resp_size, resp_addr16 = struct.unpack(RESP_HEADER_FMT, rply_head_bytes)
            if rply_head.flag_error != 0:
                raise IOError("server reported error on read")
            if rply_head.size != size:
                # Server returned different size, treat as error
                raise IOError(f"unexpected response size {rply_head.size}, expected {size}")
            # Read payload
            rply_payload_size = rply_head.payload_size
            if rply_payload_size > 0: 
                data = await asyncio.wait_for(self._reader.readexactly(rply_payload_size), timeout=self.timeout)
            else:
                data = b""
            print(f'RegioTcpClient.read [{addr}] = {data}')
            return data

# async def example():
#     client = RegioTcpClient(host="127.0.0.1", port=9999, timeout=3.0)
#     try:
#         await client.connect()
#         # Write example
#         await client.write(0x1000, b"\x01\x02\x03\x04")
#         # Read example
#         data = await client.read(0x1000, 4)
#         print("Read data:", data)
#     finally:
#         await client.close()
#
# if __name__ == "__main__":
#     try:
#         asyncio.run(example())
#     except KeyboardInterrupt:
#         pass
