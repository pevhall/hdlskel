"""Headless tests for the regio_ui TUI (Textual 8.x, no plugins).

Each test wraps an ``async`` runner in ``asyncio.run`` (pytest-asyncio
is not a dependency).  The TUI is exercised end-to-end against a
*fake* upstream regio TCP server (raw asyncio, speaking the
``regio.tcp`` wire protocol): the app's local TCP server is driven by
a raw client, and the form-sent operations are checked on the fake
upstream side.
"""

import asyncio
import socket
import struct

from regio.cache import RegioCache
from regio.tcp import (
    RPLY_SYNC,
    RQST_HEAD_SIZE,
    RQST_SYNC,
    RplyHead,
    pack_rply_head,
    unpack_rqst_head,
)
from regio.tcp_client import RegioTcpClient
from regio_ui import RegioUiApp
from regio_ui.app import build_parser, make_backend
from regio_ui.values import parse_num
from textual.widgets._data_table import Coordinate, RowKey

# operations log table column indices (see RegioUiApp.on_mount)
TIME, ADDR, OP, DATA = range(4)


def _run(coro):
    return asyncio.run(coro)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _rqst_head(flag_we: bool, size: int, addr: int) -> bytes:
    return struct.pack("<BBHI", RQST_SYNC, flag_we, size, addr)


class FakeUpstream:
    """A minimal regio TCP server for the tests: records every
    request; reads reply with a deterministic payload
    (0x00, 0x01, 0x02, ...) and writes get no reply (per protocol)."""

    def __init__(self) -> None:
        self.port = _free_port()
        self.requests: list[tuple[str, int, bytes]] = []
        self._server: asyncio.Server | None = None
        self._clients: list[asyncio.StreamWriter] = []

    async def _handle(self, reader, writer) -> None:
        self._clients.append(writer)
        try:
            while True:
                try:
                    head_bytes = await reader.readexactly(RQST_HEAD_SIZE)
                except asyncio.IncompleteReadError:
                    return
                rqst = unpack_rqst_head(head_bytes)
                if rqst.flag_we:
                    payload = await reader.readexactly(rqst.size)
                    self.requests.append(("wr", rqst.addr, payload))
                else:
                    self.requests.append(("rd", rqst.addr, b""))
                    payload = bytes(i & 0xFF for i in range(rqst.size))
                    writer.write(
                        pack_rply_head(
                            RplyHead(
                                flag_error=False,
                                size=rqst.size,
                                addr=rqst.addr,
                            )
                        )
                        + payload
                    )
                    await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle, "127.0.0.1", self.port
        )

    async def stop(self) -> None:
        # close the client connections first: wait_closed() waits for
        # the active connections to go away
        for writer in list(self._clients):
            writer.close()
        self._clients.clear()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    def got(self, op: str, addr: int, payload: bytes) -> bool:
        return (op, addr, payload) in self.requests


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _cell(app: RegioUiApp, row: int, col: int) -> str:
    cell = app.ops.get_cell_at(Coordinate(row, col))
    if hasattr(cell, "plain"):
        return cell.plain
    return str(cell)


async def _wait(pilot, pred, max_pause=500):
    for _ in range(max_pause):
        if pred():
            return
        await pilot.pause()
    raise AssertionError("condition was not met in time")


async def _wait_status(app: RegioUiApp, pilot, substr: str) -> None:
    await _wait(pilot, lambda: substr in app.status_text)


def _make_app(fake: FakeUpstream) -> RegioUiApp:
    return RegioUiApp(
        backend=RegioTcpClient(host="127.0.0.1", port=fake.port),
        backend_desc=f"127.0.0.1:{fake.port}",
        listen_host="127.0.0.1",
        listen_port=_free_port(),
    )


# ---------------------------------------------------------------------------
# value parsing
# ---------------------------------------------------------------------------


def test_parse_num():
    # hex: ceil(hex digits / 2) bytes
    assert parse_num("0x0A0") == (0xA0, 2)
    assert parse_num("0x1") == (1, 1)
    assert parse_num("0xFF") == (255, 1)
    assert parse_num("0x0000000A") == (10, 4)
    assert parse_num("0x0") == (0, 1)
    # bin: ceil(bin digits / 8) bytes
    assert parse_num("0b0101") == (5, 1)
    assert parse_num("0b11111111") == (255, 1)
    assert parse_num("0b111111111") == (511, 2)
    assert parse_num("0b0") == (0, 1)
    # decimal: assumed 32-bit (4 bytes)
    assert parse_num("3243") == (3243, 4)
    assert parse_num("0") == (0, 4)
    assert parse_num("255") == (255, 4)
    # whitespace is ignored; prefixes are case-insensitive
    assert parse_num(" 0x2A ") == (42, 1)
    assert parse_num("0B0101") == (5, 1)
    # invalid
    assert parse_num("") is None
    assert parse_num("   ") is None
    assert parse_num("0x") is None
    assert parse_num("0b") is None
    assert parse_num("0b2") is None
    assert parse_num("0xG") is None
    assert parse_num("zz") is None
    assert parse_num("-1") is None
    assert parse_num("1.5") is None


# ---------------------------------------------------------------------------
# layout / connections
# ---------------------------------------------------------------------------


def test_app_layout():
    async def run():
        fake = FakeUpstream()
        await fake.start()
        app = _make_app(fake)
        async with app.run_test() as pilot:
            await _wait_status(app, pilot, "listening on")
            await _wait_status(app, pilot, "connected")
            headers = [c.label.plain for c in app.ops.ordered_columns]
            assert headers == ["Time", "Address", "Op", "Data"]
            assert app.data_input.disabled is False  # wr by default
        await fake.stop()

    _run(run())


# ---------------------------------------------------------------------------
# relay: local client -> upstream server, log rows
# ---------------------------------------------------------------------------


def test_relay_wr_and_rd_from_local_client():
    async def run():
        fake = FakeUpstream()
        await fake.start()
        app = _make_app(fake)
        async with app.run_test() as pilot:
            await _wait_status(app, pilot, "listening on")

            reader, writer = await asyncio.open_connection(
                "127.0.0.1", app.listen_port
            )
            try:
                # --- write: forwarded, logged with its payload ---
                wr_data = b"\x01\x02\x03\x04"
                writer.write(_rqst_head(1, len(wr_data), 0x100) + wr_data)
                await writer.drain()
                await _wait(pilot, lambda: fake.got("wr", 0x100, wr_data))

                assert app.ops.row_count == 1
                assert _cell(app, 0, ADDR) == "0x00000100"
                assert _cell(app, 0, OP) == "wr"
                assert _cell(app, 0, DATA) == "01 02 03 04"
                time = _cell(app, 0, TIME)
                assert len(time) == 12 and time[2] == ":"  # HH:MM:SS.mmm

                # --- read: pending ("…") until the reply is relayed ---
                writer.write(_rqst_head(0, 4, 0x200))
                await writer.drain()
                rply_head = await reader.readexactly(RQST_HEAD_SIZE)
                sync, flag_error, size, addr = struct.unpack(
                    "<BBHI", rply_head
                )
                rply_data = await reader.readexactly(size)
                assert sync == RPLY_SYNC
                assert flag_error == 0
                assert addr == 0x200
                assert rply_data == bytes([0, 1, 2, 3])

                await _wait(
                    pilot,
                    lambda: _cell(app, 1, DATA) == "00 01 02 03",
                )
                assert _cell(app, 1, ADDR) == "0x00000200"
                assert _cell(app, 1, OP) == "rd"
                assert fake.got("rd", 0x200, b"")
            finally:
                writer.close()
        await fake.stop()

    _run(run())


def test_relay_rd_error_response():
    async def run():
        # the fake upstream answers the read at 0x300 with flag_error
        async def handle(reader, writer):
            try:
                while True:
                    try:
                        head_bytes = await reader.readexactly(RQST_HEAD_SIZE)
                    except asyncio.IncompleteReadError:
                        return
                    rqst = unpack_rqst_head(head_bytes)
                    if not rqst.flag_we:
                        writer.write(
                            pack_rply_head(
                                RplyHead(
                                    flag_error=True,
                                    size=rqst.size,
                                    addr=rqst.addr,
                                )
                            )
                        )
                        await writer.drain()
            except (ConnectionError, OSError):
                pass
            finally:
                writer.close()

        port = _free_port()
        server = await asyncio.start_server(handle, "127.0.0.1", port)
        app = RegioUiApp(
            backend=RegioTcpClient(host="127.0.0.1", port=port),
            backend_desc=f"127.0.0.1:{port}",
            listen_host="127.0.0.1",
            listen_port=_free_port(),
        )
        async with app.run_test() as pilot:
            await _wait_status(app, pilot, "listening on")
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", app.listen_port
            )
            try:
                writer.write(_rqst_head(0, 2, 0x300))
                await writer.drain()
                rply_head = await reader.readexactly(RQST_HEAD_SIZE)
                sync, flag_error, size, addr = struct.unpack(
                    "<BBHI", rply_head
                )
                assert sync == RPLY_SYNC and flag_error == 1
                assert size == 2 and addr == 0x300
                # no payload on error; the log row is marked
                await _wait(
                    pilot,
                    lambda: "⚠" in _cell(app, 0, DATA),
                )
            finally:
                writer.close()
        server.close()
        await server.wait_closed()

    _run(run())


# ---------------------------------------------------------------------------
# the Data column shows (at least) 1024 bytes per log message
# ---------------------------------------------------------------------------


def _hex_lines(data: bytes, per_line=16) -> list[str]:
    return [
        " ".join(f"{b:02X}" for b in data[ii:ii + per_line])
        for ii in range(0, len(data), per_line)
    ]


def test_log_shows_1024_bytes_truncated():
    """a 2000 B write: the Data cell shows all 1024 bytes (16 per
    line) + the total length; the rest is not shown."""
    async def run():
        fake = FakeUpstream()
        await fake.start()
        app = _make_app(fake)
        async with app.run_test() as pilot:
            await _wait_status(app, pilot, "listening on")
            payload = bytes(i & 0xFF for i in range(2000))
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", app.listen_port
            )
            try:
                writer.write(_rqst_head(1, len(payload), 0x100) + payload)
                await writer.drain()
                await _wait(pilot, lambda: fake.got("wr", 0x100, payload))
                await _wait(
                    pilot,
                    lambda: app.ops.row_count == 1
                    and "… (2000 B)" in _cell(app, 0, DATA),
                )
            finally:
                writer.close()

            shown = _cell(app, 0, DATA)
            lines = shown.split("\n")
            # 1024 B = 64 lines of 16 B + the total-length line
            assert len(lines) == 1024 // 16 + 1
            assert lines[0] == _hex_lines(payload)[0]
            assert lines[-2] == _hex_lines(payload[:1024])[-1]
            assert lines[-1] == "… (2000 B)"
            # the (auto-height) row grew to fit the 65 lines
            assert app.ops.get_row_height(RowKey("op1")) == 65
        await fake.stop()

    _run(run())


def test_log_shows_full_1024_bytes():
    """a 1024 B write is shown in full (no truncation)."""
    async def run():
        fake = FakeUpstream()
        await fake.start()
        app = _make_app(fake)
        async with app.run_test() as pilot:
            await _wait_status(app, pilot, "listening on")
            payload = bytes(i & 0xFF for i in range(1024))
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", app.listen_port
            )
            try:
                writer.write(_rqst_head(1, len(payload), 0x200) + payload)
                await writer.drain()
                await _wait(pilot, lambda: fake.got("wr", 0x200, payload))
                await _wait(
                    pilot,
                    lambda: app.ops.row_count == 1
                    and _cell(app, 0, DATA) == "\n".join(_hex_lines(payload)),
                )
            finally:
                writer.close()
        await fake.stop()

    _run(run())


# ---------------------------------------------------------------------------
# the new-operation form
# ---------------------------------------------------------------------------


def test_user_send_wr_bin_inferred_size():
    """'0b0101' without a size: 4 bin digits -> 1 byte."""
    async def run():
        fake = FakeUpstream()
        await fake.start()
        app = _make_app(fake)
        async with app.run_test() as pilot:
            await _wait_status(app, pilot, "listening on")
            app.addr_input.value = "0x10"
            app.data_input.value = "0b0101"
            app.data_input.focus()
            await pilot.press("enter")
            await _wait(pilot, lambda: fake.got("wr", 0x10, b"\x05"))
            await _wait(pilot, lambda: _cell(app, 0, DATA) == "05")
            assert _cell(app, 0, OP) == "wr"
        await fake.stop()

    _run(run())


def test_user_send_wr_hex_explicit_size():
    """'0x0A0' with size 4: zero-padded to 4 bytes."""
    async def run():
        fake = FakeUpstream()
        await fake.start()
        app = _make_app(fake)
        async with app.run_test() as pilot:
            await _wait_status(app, pilot, "listening on")
            app.addr_input.value = "0"
            app.data_input.value = "0x0A0"
            app.size_input.value = "4"
            app.data_input.focus()
            await pilot.press("enter")
            # 0x0A0 = 160 = 0xA0: little-endian 4 bytes
            await _wait(pilot, lambda: fake.got("wr", 0, b"\xA0\x00\x00\x00"))
            await _wait(pilot, lambda: _cell(app, 0, DATA) == "A0 00 00 00")
        await fake.stop()

    _run(run())


def test_user_send_wr_decimal_inferred_size():
    """'3243' without a size: decimal -> 4 bytes (0x0C93)."""
    async def run():
        fake = FakeUpstream()
        await fake.start()
        app = _make_app(fake)
        async with app.run_test() as pilot:
            await _wait_status(app, pilot, "listening on")
            app.addr_input.value = "0x40"
            app.data_input.value = "3243"
            app.data_input.focus()
            await pilot.press("enter")
            # 3243 = 0x0CAB: little-endian 4 bytes
            await _wait(pilot, lambda: fake.got("wr", 0x40, b"\xAB\x0C\x00\x00"))
            await _wait(pilot, lambda: _cell(app, 0, DATA) == "AB 0C 00 00")
        await fake.stop()

    _run(run())


def test_user_send_wr_rejects_oversized_value():
    """a value that does not fit the given size is rejected locally."""
    async def run():
        fake = FakeUpstream()
        await fake.start()
        app = _make_app(fake)
        async with app.run_test() as pilot:
            await _wait_status(app, pilot, "listening on")
            app.addr_input.value = "0"
            app.data_input.value = "0xFFFF"
            app.size_input.value = "1"
            app.data_input.focus()
            await pilot.press("enter")
            await pilot.pause()
            assert app.ops.row_count == 0  # not logged
            assert not fake.requests  # not forwarded
            assert app.app.focused is app.data_input
        await fake.stop()

    _run(run())


def test_user_send_rd():
    async def run():
        fake = FakeUpstream()
        await fake.start()
        app = _make_app(fake)
        async with app.run_test() as pilot:
            await _wait_status(app, pilot, "listening on")
            # toggle to rd via the op button
            await pilot.click("#op-toggle")
            await pilot.pause()
            assert app.op_button.label == "rd"
            assert app.data_input.disabled is True
            app.addr_input.value = "0x30"
            app.size_input.value = "3"
            app.size_input.focus()
            await pilot.press("enter")
            await _wait(pilot, lambda: fake.got("rd", 0x30, b""))
            await _wait(pilot, lambda: _cell(app, 0, DATA) == "00 01 02")
            assert _cell(app, 0, OP) == "rd"
        await fake.stop()

    _run(run())


def test_user_send_rd_requires_size():
    async def run():
        fake = FakeUpstream()
        await fake.start()
        app = _make_app(fake)
        async with app.run_test() as pilot:
            await _wait_status(app, pilot, "listening on")
            app.action_toggle_op()  # rd
            app.addr_input.value = "0x30"
            app.size_input.value = ""
            app.size_input.focus()
            await pilot.press("enter")
            await pilot.pause()
            assert app.ops.row_count == 0
            assert not fake.requests
            assert app.app.focused is app.size_input
        await fake.stop()

    _run(run())


def test_send_forward_error_marks_row():
    """with the upstream server unreachable the operation is marked ⚠."""
    async def run():
        # a port nothing is listening on: connects are refused
        dead_port = _free_port()
        app = RegioUiApp(
            backend=RegioTcpClient(host="127.0.0.1", port=dead_port),
            backend_desc=f"127.0.0.1:{dead_port}",
            listen_host="127.0.0.1",
            listen_port=_free_port(),
        )
        async with app.run_test() as pilot:
            await _wait_status(app, pilot, "listening on")
            app.addr_input.value = "0x1"
            app.data_input.value = "0x1"
            app.data_input.focus()
            await pilot.press("enter")
            await _wait(
                pilot,
                lambda: app.ops.row_count == 1
                and "⚠" in _cell(app, 0, DATA),
            )

    _run(run())


# ---------------------------------------------------------------------------
# selecting a log row autofills the form (editable before sending)
# ---------------------------------------------------------------------------


def test_select_row_autofills_form_and_resends():
    async def run():
        fake = FakeUpstream()
        await fake.start()
        app = _make_app(fake)
        async with app.run_test() as pilot:
            await _wait_status(app, pilot, "listening on")
            # a wr operation: addr 0x50, data 0x0A0 (2 B inferred)
            app.addr_input.value = "0x50"
            app.data_input.value = "0x0A0"
            app.data_input.focus()
            await pilot.press("enter")
            # 0x0A0 = 160: little-endian 2 bytes
            await _wait(pilot, lambda: fake.got("wr", 0x50, b"\xA0\x00"))

            # select the log row: the form is autofilled to match it
            app.ops.focus()
            app.ops.move_cursor(row=0, column=0)
            await pilot.press("enter")
            await pilot.pause()
            assert app._op_write is True
            assert app.addr_input.value == "0x00000050"
            assert app.size_input.value == "2"
            assert app.data_input.value == "0xA0"
            assert app.data_input.disabled is False

            # edit the address and send it again
            app.addr_input.value = "0x51"
            await pilot.press("enter")
            await _wait(pilot, lambda: fake.got("wr", 0x51, b"\xA0\x00"))
            await _wait(pilot, lambda: app.ops.row_count == 2)
        await fake.stop()

    _run(run())


def test_select_rd_row_autofills_form():
    async def run():
        fake = FakeUpstream()
        await fake.start()
        app = _make_app(fake)
        async with app.run_test() as pilot:
            await _wait_status(app, pilot, "listening on")
            # a rd operation: addr 0x60, 4 B
            app.action_toggle_op()  # rd
            app.addr_input.value = "0x60"
            app.size_input.value = "4"
            app.size_input.focus()
            await pilot.press("enter")
            await _wait(
                pilot, lambda: _cell(app, 0, DATA) == "00 01 02 03"
            )

            # select the log row: rd is autofilled (no write data)
            app.ops.focus()
            app.ops.move_cursor(row=0, column=0)
            await pilot.press("enter")
            await pilot.pause()
            assert app._op_write is False
            assert app.addr_input.value == "0x00000060"
            assert app.size_input.value == "4"
            assert app.data_input.value == ""
            assert app.data_input.disabled is True
        await fake.stop()

    _run(run())


# ---------------------------------------------------------------------------
# log clearing
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# serving a regio cache file instead of a TCP server
# ---------------------------------------------------------------------------


def test_serve_cache_file(tmp_path):
    """a RegioCache loaded from a file is served directly: reads come
    from the file contents, writes update the (in-memory) cache."""
    async def run():
        # build the cache file
        cache_file = tmp_path / "cache.skelregio"
        seed = RegioCache()
        await seed.write(0x100, b"\xDE\xAD\xBE\xEF")
        seed.save_to_file(cache_file)
        # the backend: a fresh cache loaded from the file (as
        # regio.cli_utils does)
        backend = RegioCache()
        backend.load_from_file(cache_file)

        app = RegioUiApp(
            backend=backend,
            backend_desc=str(cache_file),
            listen_host="127.0.0.1",
            listen_port=_free_port(),
        )
        async with app.run_test() as pilot:
            await _wait_status(app, pilot, "listening on")
            await _wait_status(app, pilot, f"file {cache_file}")

            reader, writer = await asyncio.open_connection(
                "127.0.0.1", app.listen_port
            )
            try:
                # read back the seeded data
                writer.write(_rqst_head(0, 4, 0x100))
                await writer.drain()
                rply_head = await reader.readexactly(RQST_HEAD_SIZE)
                sync, flag_error, size, addr = struct.unpack(
                    "<BBHI", rply_head
                )
                rply_data = await reader.readexactly(size)
                assert sync == RPLY_SYNC and flag_error == 0
                assert rply_data == b"\xDE\xAD\xBE\xEF"

                # a write updates the (in-memory) cache ...
                writer.write(_rqst_head(1, 2, 0x200) + b"\x11\x22")
                await writer.drain()
                await _wait(pilot, lambda: app.ops.row_count >= 2)
                # ... so a following read sees the new bytes
                writer.write(_rqst_head(0, 2, 0x200))
                await writer.drain()
                rply_head = await reader.readexactly(RQST_HEAD_SIZE)
                sync, flag_error, size, addr = struct.unpack(
                    "<BBHI", rply_head
                )
                rply_data = await reader.readexactly(size)
                assert flag_error == 0
                assert rply_data == b"\x11\x22"

                # reading data that was never written is an error
                # response (and stays logged as a warning row)
                writer.write(_rqst_head(0, 1, 0x900))
                await writer.drain()
                rply_head = await reader.readexactly(RQST_HEAD_SIZE)
                sync, flag_error, size, addr = struct.unpack(
                    "<BBHI", rply_head
                )
                assert sync == RPLY_SYNC and flag_error == 1
            finally:
                writer.close()

    _run(run())


def test_make_backend_file(tmp_path):
    """-f: the backend is a RegioCache loaded from the file; a bad
    file is a fatal error."""
    async def run():
        cache_file = tmp_path / "cache.skelregio"
        seed = RegioCache()
        await seed.write(0x10, b"\x01")
        seed.save_to_file(cache_file)

        args = build_parser().parse_args(["-f", str(cache_file)])
        backend, desc = await make_backend(args)
        assert isinstance(backend, RegioCache)
        assert desc == str(cache_file)
        assert (await backend.read(0x10, 1)) == b"\x01"

        args = build_parser().parse_args(
            ["-f", str(tmp_path / "missing.skelregio")]
        )
        try:
            await make_backend(args)
            assert False, "expected SystemExit"
        except SystemExit:
            pass

    _run(run())


def test_make_backend_tcp_unreachable():
    """-i/-p with a dead server: not an error — the backend is
    returned unconnected (the proxy keeps retrying)."""
    async def run():
        dead_port = _free_port()
        args = build_parser().parse_args(
            ["-i", "127.0.0.1", "-p", str(dead_port)]
        )
        backend, desc = await make_backend(args)
        assert isinstance(backend, RegioTcpClient)
        assert desc == f"127.0.0.1:{dead_port}"

    _run(run())


def test_clear_log():
    async def run():
        fake = FakeUpstream()
        await fake.start()
        app = _make_app(fake)
        async with app.run_test() as pilot:
            await _wait_status(app, pilot, "listening on")
            app.addr_input.value = "0x1"
            app.data_input.value = "0x1"
            app.data_input.focus()
            await pilot.press("enter")
            await _wait(pilot, lambda: app.ops.row_count == 1)

            app.ops.focus()
            await pilot.press("c")
            await pilot.pause()
            assert app.ops.row_count == 0
            assert app._row_ops == {}
        await fake.stop()

    _run(run())


# ---------------------------------------------------------------------------
# log capture (p key / capture=False when started through another app)
# ---------------------------------------------------------------------------


def test_capture_toggle_p_key():
    """Started on its own, regio_ui captures from the start; `p`
    stops / starts the capture (operations pass by unlogged while
    off)."""

    async def run():
        fake = FakeUpstream()
        await fake.start()
        app = _make_app(fake)
        async with app.run_test() as pilot:
            await _wait_status(app, pilot, "listening on")
            assert app.view.capture is True

            # stop capturing, then send an operation: it reaches the
            # backend but is not logged
            app.ops.focus()
            await pilot.press("p")
            await pilot.pause()
            assert app.view.capture is False
            assert "capture: off" in app.status_text
            app.addr_input.value = "0x1"
            app.data_input.value = "0x1"
            app.data_input.focus()
            await pilot.press("enter")
            await _wait(pilot, lambda: len(fake.requests) >= 1)
            await pilot.pause()
            assert app.ops.row_count == 0

            # start capturing again: the same operation is now logged
            app.ops.focus()
            await pilot.press("p")
            await pilot.pause()
            assert app.view.capture is True
            app.data_input.focus()
            await pilot.press("enter")
            await _wait(pilot, lambda: app.ops.row_count == 1)
        await fake.stop()

    _run(run())


def test_capture_off_at_boot():
    """capture=False (what skmap_ui uses when it embeds the view):
    operations pass by without being logged until the capture is
    started with `p`."""

    async def run():
        fake = FakeUpstream()
        await fake.start()
        app = RegioUiApp(
            backend=RegioTcpClient(host="127.0.0.1", port=fake.port),
            backend_desc=f"127.0.0.1:{fake.port}",
            listen_host="127.0.0.1",
            listen_port=_free_port(),
            capture=False,
        )
        async with app.run_test() as pilot:
            await _wait_status(app, pilot, "listening on")
            assert app.view.capture is False

            app.addr_input.value = "0x2"
            app.data_input.value = "0x2"
            app.data_input.focus()
            await pilot.press("enter")
            await _wait(pilot, lambda: len(fake.requests) >= 1)
            await pilot.pause()
            assert app.ops.row_count == 0

            app.ops.focus()
            await pilot.press("p")
            await pilot.pause()
            app.data_input.focus()
            await pilot.press("enter")
            await _wait(pilot, lambda: app.ops.row_count == 1)
        await fake.stop()

    _run(run())


def test_view_embeddable_widget():
    """The UI is the reusable RegioUiView widget (embedding apps, like
    skmap_ui, host it directly and feed it through its op_started /
    op_done callbacks)."""

    async def run():
        fake = FakeUpstream()
        await fake.start()
        app = _make_app(fake)
        async with app.run_test() as pilot:
            await _wait_status(app, pilot, "listening on")
            view = app.view
            # the view is the app's single content widget between the
            # header and the footer
            assert view.backend_desc == f"127.0.0.1:{fake.port}"
            assert app.ops is view.ops
            assert app.addr_input is view.addr_input
        await fake.stop()

    _run(run())
