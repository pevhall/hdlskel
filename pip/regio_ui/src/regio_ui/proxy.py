"""The network side of regio_ui: a regio TCP *server* in front of a
backend regio *device* (``Regio``), with the TUI living between them.

regio_ui listens on a local TCP port (its TCP **server** side, based
on the multi-client server from ``regio.tcp_server_async_multi``) for
regio clients (a testbench, ``skmap_ui``, ...) and forwards every
operation to the **backend** regio device, relaying the responses
back.  The backend is created with ``regio.cli_utils``:

* a regio TCP server on another host/port (``-i/--host``, ``-p/--port``)
  — a ``regio.tcp_client.RegioTcpClient`` connection, **or**
* a regio cache file (``-f/--file``) — a ``regio.cache.RegioCache``
  loaded from a ``skelregio`` file (no other server needed).

Every operation — received from a local client *or* sent by the user
from the "new operation" form — is reported through the callbacks, so
the TUI can log it (and offer it for re-sending).

Wire protocol (see ``regio.tcp``): little-endian; a request is an
8-byte header ``u8 sync (0x9A), u8 flag_we, u16 size, u32 addr``
followed, for writes (``flag_we = 1``), by ``size`` payload bytes.  A
read (``flag_we = 0``) is answered by an 8-byte header
``u8 sync (0x9B), u8 flag_error, u16 size, u32 addr`` + payload
(a failed read has ``flag_error = 1`` and no payload).  The protocol
defines no response for writes.
"""

from __future__ import annotations

import asyncio
import logging
import struct
from dataclasses import dataclass, field
from typing import Callable, Optional

from regio import Regio
from regio import tcp_server_async_multi
from regio.cache import RegioCache
from regio.tcp import ADDR_MAX, PORT_DEFAULT, SIZE_MAX

__all__ = ["ProxyError", "RegioOp", "RegioProxy"]


class ProxyError(Exception):
    """A regio operation could not be (fully) forwarded."""


@dataclass
class RegioOp:
    """One regio operation: a write (``wr``) or a read (``rd``)."""

    addr: int
    write: bool  # True = wr, False = rd
    size: int  # wr: payload length, rd: read size
    data: Optional[bytes] = field(default=None, compare=False)
    # wr: the write payload; rd: filled with the response payload once
    # the backend replied (None while pending / on error)

    @property
    def op_str(self) -> str:
        return "wr" if self.write else "rd"


#: reports a new operation (from a local client or the user's form)
#: *before* it is forwarded; returns the log row's key
OpStarted = Callable[["RegioOp"], str]
#: reports the outcome of a forwarded operation: (row key, payload
#: read back, error message or None)
OpDone = Callable[[str, Optional[bytes], Optional[str]], None]
#: reports the connection / listening status
Status = Callable[[str], None]


def backend_kind(backend: Regio) -> str:
    """"file" for a cache (``RegioCache``) backend, "tcp" for a TCP
    client backend."""
    return "file" if isinstance(backend, RegioCache) else "tcp"


class _RelayingRegio(Regio):
    """The regio *device* driven by the multi-client TCP server.

    Every operation is logged by the proxy and forwarded to the
    backend (the exact same path as the user's form operations).  A
    read that could not be completed yields an empty payload, which
    the server turns into a ``flag_error`` response (the client
    connection stays open); a failed write is reported in the log
    (the protocol defines no response for writes).
    """

    def __init__(self, proxy: "RegioProxy") -> None:
        super().__init__()
        self._proxy = proxy

    async def dev_write(self, addr: int, data: bytes) -> None:
        await self._proxy.relay_write(addr, data)

    async def dev_read(self, addr: int, size: int) -> bytes:
        _, payload, err = await self._proxy.relay_read(addr, size)
        return b"" if err is not None else payload


class RegioProxy:
    """Sits between a backend regio device and regio TCP clients.

    The backend is a ``Regio`` instance — e.g. a
    ``regio.tcp_client.RegioTcpClient`` connected to a regio TCP
    server on another port, or a ``regio.cache.RegioCache`` loaded
    from a file (see ``regio.cli_utils``).

    Start the two tasks on the running event loop::

        proxy = RegioProxy(backend, backend_desc, ...)
        asyncio.create_task(proxy.start_local_server())
        asyncio.create_task(proxy.watch_upstream())

    and send user operations with :meth:`relay_write` /
    :meth:`relay_read` (the same path the relayed local-client
    traffic takes, so everything is logged identically).
    """

    #: how often a dropped TCP backend is (re)tried, in seconds
    RECONNECT_PERIOD = 2.0

    def __init__(
        self,
        backend: Regio,
        backend_desc: str,
        listen_host: str = "0.0.0.0",
        listen_port: int = PORT_DEFAULT,
        on_op: Optional[OpStarted] = None,
        on_done: Optional[OpDone] = None,
        on_status: Optional[Status] = None,
    ) -> None:
        self._backend = backend
        #: human-readable backend: "host:port" (TCP) or a file path
        self.backend_desc = backend_desc
        #: "tcp" (a connection has to be kept up) or "file"
        self._backend_kind = backend_kind(backend)
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.on_op = on_op
        self.on_done = on_done
        self.on_status = on_status

        self._local_server: Optional[tcp_server_async_multi.RegioTcpServer] = (
            None
        )
        self._closed = False
        self._listening = False
        self._backend_up = False

    # ------------------------------------------------------------------
    # status
    # ------------------------------------------------------------------
    @property
    def backend_str(self) -> str:
        if self._backend_kind == "file":
            return f"file {self.backend_desc}"
        return f"upstream {self.backend_desc}"

    @property
    def listen_str(self) -> str:
        return f"{self.listen_host}:{self.listen_port}"

    def _emit_status(self) -> None:
        listen = (
            f"listening on {self.listen_str}"
            if self._listening
            else f"starting listener on {self.listen_str} ..."
        )
        if self._backend_kind == "tcp":
            state = (
                "connected"
                if self._backend_up
                else "not connected (retrying ...)"
            )
            text = f"{listen}  ·  {self.backend_str} ({state})"
        else:
            text = f"{listen}  ·  {self.backend_str}"
        logging.debug("proxy: %s", text)
        if self.on_status is not None:
            self.on_status(text)

    # ------------------------------------------------------------------
    # validation
    # ------------------------------------------------------------------
    @staticmethod
    def check_addr(addr: int) -> None:
        if not 0 <= addr <= ADDR_MAX:
            raise ProxyError(
                f"address 0x{addr:x} out of range (0 .. 0x{ADDR_MAX:x})"
            )

    @staticmethod
    def check_size(size: int) -> None:
        if not 1 <= size <= SIZE_MAX:
            raise ProxyError(f"size {size} out of range (1 .. {SIZE_MAX})")

    # ------------------------------------------------------------------
    # backend (re)connection — TCP backends only
    # ------------------------------------------------------------------
    async def watch_upstream(self) -> None:
        """Task: connect a TCP backend and keep (re)connecting while
        it is away.  A no-op for a file backend (nothing to connect)."""
        connect = getattr(self._backend, "connect", None)
        if connect is None:
            return
        while not self._closed:
            try:
                await connect()
                if not self._backend_up:
                    self._backend_up = True
                    self._emit_status()
            except asyncio.CancelledError:
                raise
            except (OSError, asyncio.TimeoutError):
                if self._backend_up:
                    self._backend_up = False
                    self._emit_status()
            await asyncio.sleep(self.RECONNECT_PERIOD)

    def _mark_backend(self, up: bool) -> None:
        if self._backend_kind == "file":
            return
        if self._backend_up is not up:
            self._backend_up = up
            self._emit_status()

    # ------------------------------------------------------------------
    # relay (used by the local server *and* the user's form):
    # log the operation, forward it, report the outcome
    # ------------------------------------------------------------------
    def _op_started(self, op: RegioOp) -> str:
        if self.on_op is not None:
            return self.on_op(op)
        return ""

    def _op_done(
        self, key: str, data: Optional[bytes], error: Optional[str]
    ) -> None:
        if error is not None and key:
            logging.warning("regio_ui: %s", error)
        if self.on_done is not None and key:
            self.on_done(key, data, error)

    async def relay_write(
        self, addr: int, data: bytes
    ) -> tuple[str, Optional[str]]:
        """Log + forward a write.  Returns (row key, error or None)."""
        key = self._op_started(
            RegioOp(addr=addr, write=True, size=len(data), data=data)
        )
        try:
            self.check_addr(addr)
            self.check_size(len(data))
        except ProxyError as err:
            self._op_done(key, None, str(err))
            return key, str(err)
        try:
            await self._backend.write(addr, data)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001 — any backend failure is
            # a logged error, never a crash
            msg = f"0x{addr:x} wr {len(data)} B: {err}"
            self._mark_backend(False)
            self._op_done(key, None, msg)
            return key, msg
        self._mark_backend(True)
        self._op_done(key, data, None)
        return key, None

    async def relay_read(
        self, addr: int, size: int
    ) -> tuple[str, bytes, Optional[str]]:
        """Log + forward a read.  Returns (row key, payload, error)."""
        key = self._op_started(RegioOp(addr=addr, write=False, size=size))
        try:
            self.check_addr(addr)
            self.check_size(size)
        except ProxyError as err:
            self._op_done(key, None, str(err))
            return key, b"", str(err)
        try:
            payload = await self._backend.read(addr, size)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001 — any backend failure is
            # a logged error, never a crash
            msg = f"0x{addr:x} rd {size} B: {err}"
            self._mark_backend(False)
            self._op_done(key, None, msg)
            return key, b"", msg
        self._mark_backend(True)
        self._op_done(key, payload, None)
        return key, payload, None

    # ------------------------------------------------------------------
    # local (server) side — the multi-client server from the regio
    # package; the _RelayingRegio above logs/forwards every operation
    # ------------------------------------------------------------------
    async def start_local_server(self) -> None:
        """Task: start the local (client-facing) multi-client TCP
        server and serve until :meth:`close` (raises ``OSError`` if
        the port cannot be bound)."""
        server = tcp_server_async_multi.RegioTcpServer(
            _RelayingRegio(self),
            host=self.listen_host,
            port=self.listen_port,
        )
        self._local_server = server
        self._listening = True
        self._emit_status()
        try:
            await server.start()
        except OSError:
            self._listening = False
            self._local_server = None
            self._emit_status()
            raise  # could not bind the listen port
        finally:
            self._local_server = None
            self._listening = False

    # ------------------------------------------------------------------
    # shutdown
    # ------------------------------------------------------------------
    async def close(self) -> None:
        """Stop the local server and close the backend (TCP)
        connection, if any."""
        self._closed = True
        if self._local_server is not None:
            self._local_server.stop()
        close = getattr(self._backend, "close", None)
        if close is not None:
            try:
                await close()
            except (OSError, ConnectionError):
                pass
