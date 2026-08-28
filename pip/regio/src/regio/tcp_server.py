
from typing import Optional

from . import Regio

from .tcp import RQST_HEAD_SIZE, RqstHead, RplyHead, unpack_rqst_head, pack_rply_head, PORT_DEFAULT


import socket
import struct
from typing import Optional

# Keep the async Regio interface the same as you provided

class RegioTcpServer:
    def __init__(self, regio: Regio, host: str = "0.0.0.0", port: int = PORT_DEFAULT, backlog: int = 1):
        self.regio = regio
        self.host = host
        self.port = port
        self.backlog = backlog
        self._sock: Optional[socket.socket] = None

    async def start(self):
        """Start listening (blocking accept loop)."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Allow quick restart
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(self.backlog)
        print(f"RegioTcpServer listening on {self.host}:{self.port}")
        try:
            while True:
                conn, addr = self._sock.accept()
                print(f"Accepted connection from {addr}")
                try:
                    await self._handle_client(conn)
                except Exception as e:
                    print(f"Error handling client {addr}: {e}")
                finally:
                    conn.close()
                    print(f"Connection from {addr} closed")
        except KeyboardInterrupt:
            print("Server shutting down (KeyboardInterrupt)")
        finally:
            if self._sock:
                self._sock.close()
                self._sock = None

    def _recv_exact(self, conn: socket.socket, n: int) -> bytes:
        """Receive exactly n bytes or raise EOFError."""
        buf = bytearray()
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                raise EOFError("connection closed while reading")
            buf.extend(chunk)
        return bytes(buf)

    async def _handle_client(self, conn: socket.socket):
        """Handle a single client connection until it disconnects."""
        while True:
            # Read request header
            try:
                rqst_head_bytes = self._recv_exact(conn, RQST_HEAD_SIZE)
            except EOFError:
                # client closed connection
                return

            try:
                rqst_head = unpack_rqst_head(rqst_head_bytes)
            except struct.error or ValueError:
                print("Malformed header; closing connection")
                return

            # If write request, read payload and call regio.write
            if rqst_head.flag_we:
                try:
                    wr_data = self._recv_exact(conn, rqst_head.payload_size)
                except EOFError:
                    print("Client closed while sending wr_data; closing connection")
                    return

                # Call async write using asyncio.run (runs a fresh event loop for the call)
                await self.regio.write(rqst_head.addr, wr_data)

            else:
                # Read request (flag_we == 0)
                rd_data = await self.regio.read(rqst_head.addr, rqst_head.size)
                if not isinstance(rd_data, (bytes, bytearray)):
                    raise TypeError("Regio.read must return bytes")
                if len(rd_data) != rqst_head.size:
                    # treat mismatch as error
                    raise TypeError(f"Regio.read returned {len(rd_data)} bytes but requested {rqst_head.size}")
                    flag_error = True
                    rd_data = b""
                else:
                    flag_error = False

                rply_head = RplyHead(
                    flag_error = flag_error,
                    size = rqst_head.size,
                    addr = rqst_head.addr
                )
                rply_head_bytes = pack_rply_head(rply_head)
                conn.sendall(rply_head_bytes)
                conn.sendall(rd_data)
                # continue to next request from same client

# # Example Regio implementation (user should implement these)
# class ExampleRegio(Regio):
#     def __init__(self):
#         # simple in-memory storage
#         self._mem = bytearray(1024 * 1024)  # 1 MiB
#
#     async def write(self, addr: int, data: bytes) -> None:
#         # synchronous-like implementation inside async function
#         if addr < 0 or addr + len(data) > len(self._mem):
#             raise ValueError("write out of range")
#         self._mem[addr:addr+len(data)] = data
#
#     async def read(self, addr: int, size: int) -> bytes:
#         if addr < 0 or addr + size > len(self._mem):
#             raise ValueError("read out of range")
#         return bytes(self._mem[addr:addr+size])

# Example usage
# if __name__ == "__main__":
#     regio = ExampleRegio()
#     server = RegioTcpServer(regio, host="127.0.0.1", port=9999)
#     server.start()




