"""Regio TCP server that accepts **multiple clients at the same time**.

The server multiplexes all client connections in a single task using
``selectors`` on plain (blocking) sockets — no asyncio I/O primitives
are used, so the server runs both under a regular asyncio event loop
**and** under cocotb (2.x drives coroutines with its own scheduler and
has no running asyncio loop).

While one client's operation is being served, the other clients'
incoming data is buffered (in the kernel and locally) and served as
soon as the operation completes; the ``regio`` device therefore never
sees more than one operation in flight (the same request / response
semantics as with a single client).

Wire protocol (see :mod:`regio.tcp`): little-endian; a request is an
8-byte header ``u8 sync (0x9A), u8 flag_we, u16 size, u32 addr``
followed, for writes (``flag_we = 1``), by ``size`` payload bytes.  A
read (``flag_we = 0``) is answered by an 8-byte header
``u8 sync (0x9B), u8 flag_error, u16 size, u32 addr`` + payload
(a failed read has ``flag_error = 1`` and no payload).

Example::

    import regio.tcp_server_async_multi

    server = regio.tcp_server_async_multi.RegioTcpServer(
        regio, host="127.0.0.1", port=9999
    )
    await server.start()  # runs until server.stop() / KeyboardInterrupt
"""

import asyncio
import selectors
import socket
import struct
from typing import Dict, Tuple

from . import Regio

from .tcp import (
    RQST_HEAD_SIZE,
    RplyHead,
    unpack_rqst_head,
    pack_rply_head,
    PORT_DEFAULT,
)


class _Client:
    """State of one connected (client-side) connection."""

    __slots__ = ("sock", "peer", "buf")

    def __init__(self, sock: socket.socket, peer: Tuple[str, int]):
        self.sock = sock
        self.peer = peer
        #: not-yet-processed request bytes
        self.buf = bytearray()


class RegioTcpServer:
    def __init__(self, regio: Regio, host: str = "0.0.0.0", port: int = PORT_DEFAULT, backlog: int = 100):
        self.regio = regio
        self.host = host
        self.port = port
        self.backlog = backlog
        self._stopped = False

    def stop(self) -> None:
        """Ask the server to stop serving (the loop exits after the
        in-flight operation, if any, has completed)."""
        self._stopped = True

    @staticmethod
    async def _yield_once():
        """Give control back to the coroutine driver.

        Under a regular asyncio event loop this is a ``sleep(0)``;
        under cocotb (2.x has no running asyncio loop and only
        understands cocotb triggers) it is a 1 ns ``Timer``.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # no asyncio event loop is running (e.g. cocotb 2.x)
            from cocotb.triggers import Timer
            await Timer(1, unit="ns")
            return
        await asyncio.sleep(0)

    async def start(self):
        """Start listening and serve all clients concurrently (runs
        forever; closes the sockets on KeyboardInterrupt)."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Allow quick restart
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen(self.backlog)
        print(f"RegioTcpServer listening on {self.host}:{self.port}")

        sel = selectors.DefaultSelector()
        sel.register(sock, selectors.EVENT_READ)
        clients: Dict[int, _Client] = {}
        try:
            while not self._stopped:
                try:
                    events = sel.select(timeout=0.0)
                except InterruptedError:
                    events = []
                for key, mask in events:
                    if key.fileobj is sock:
                        self._accept(sock, sel, clients)
                    else:
                        self._on_data(key, mask, clients, sel)
                for client in list(clients.values()):
                    try:
                        await self._process_requests(client, sel, clients)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:  # noqa: BLE001 — a misbehaving
                        # regio device must not kill the whole server
                        print(f"Error handling client {client.peer}: {e}")
                        self._drop_client(client, sel, clients)
                # give the driver (event loop / simulator) a turn
                await self._yield_once()
        except KeyboardInterrupt:
            print("Server shutting down (KeyboardInterrupt)")
        finally:
            for client in list(clients.values()):
                self._drop_client(client, sel, clients)
            sock.close()
            sel.close()

    def _accept(self, sock: socket.socket, sel: selectors.BaseSelector, clients: Dict[int, _Client]):
        try:
            conn, peer = sock.accept()
        except OSError:
            return
        client = _Client(conn, peer)
        sel.register(conn, selectors.EVENT_READ)
        clients[conn.fileno()] = client
        print(f"Accepted connection from {peer}")

    def _on_data(
        self, key: selectors.SelectorKey, mask: int,
        clients: Dict[int, _Client], sel: selectors.BaseSelector,
    ):
        client = clients.get(key.fileobj.fileno())
        if client is None:
            return
        if not (mask & selectors.EVENT_READ):
            return
        # connection errors (e.g. ECONNRESET) surface as OSError below
        try:
            data = client.sock.recv(65536)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            self._drop_client(client, sel, clients)
            return
        if not data:
            # client closed the connection
            self._drop_client(client, sel, clients)
            return
        client.buf.extend(data)

    def _drop_client(
        self, client: _Client, sel: selectors.BaseSelector,
        clients: Dict[int, _Client],
    ):
        clients.pop(client.sock.fileno(), None)
        try:
            sel.unregister(client.sock)
        except (KeyError, ValueError):
            pass
        try:
            client.sock.close()
        except OSError:
            pass
        print(f"Connection from {client.peer} closed")

    async def _process_requests(
        self, client: _Client, sel: selectors.BaseSelector,
        clients: Dict[int, _Client],
    ):
        """Process every complete request in the client's buffer.

        The ``regio`` operations are awaited here, so the device never
        sees more than one operation in flight; other clients' data
        stays buffered until then.
        """
        buf = client.buf
        while len(buf) >= RQST_HEAD_SIZE:
            try:
                rqst_head = unpack_rqst_head(bytes(buf[:RQST_HEAD_SIZE]))
            except (struct.error, ValueError):
                print(f"Malformed header from {client.peer}; closing connection")
                self._drop_client(client, sel, clients)
                return

            total = RQST_HEAD_SIZE + rqst_head.payload_size
            if len(buf) < total:
                return  # wait for the rest of the payload

            payload = bytes(buf[RQST_HEAD_SIZE:total])
            del buf[:total]

            if rqst_head.flag_we:
                # write request: the payload is the data to write
                # (the protocol defines no response for writes)
                await self.regio.write(rqst_head.addr, payload)
            else:
                # read request (flag_we == 0)
                rd_data = await self.regio.read(rqst_head.addr, rqst_head.size)
                if not isinstance(rd_data, (bytes, bytearray)):
                    raise TypeError("Regio.read must return bytes")
                if len(rd_data) != rqst_head.size:
                    # treat mismatch as error
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
                client.sock.sendall(rply_head_bytes)
                client.sock.sendall(bytes(rd_data))
                # continue to next request from same client
