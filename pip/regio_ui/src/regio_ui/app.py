"""Textual TUI for regio_ui — a live log of the regio operations that
flow between a regio TCP server and its clients, plus a form to send
new operations.

regio_ui lives **between** a regio *device* (the backend) and regio
TCP clients: it starts its own regio TCP *server*
(``--listen-host`` / ``--listen-port``, default
``0.0.0.0:0x9AB0``) for the clients and forwards every operation to
the backend — either a regio TCP server on another host/port
(``-i/--host`` / ``-p/--port``) or a regio cache file (``-f/--file``;
the backend options are shared with the regio CLI, see
``regio.cli_utils``).  Every operation a local client sends is
**logged** and **forwarded** (responses relayed back); the user can
also send operations from the form, which go through the same
backend and end up in the same log.

Layout::

    +------------------------------------------------------+
    | header                                               |
    +------------------------------------------------------+
    | operations log (DataTable)                           |
    | Time | Address | Op | Data                           |
    +------------------------------------------------------+
    | status line (listening / upstream state, op count)   |
    +------------------------------------------------------+
    | [wr]  [Address: 0x…]          [Size (B)]             |
    | [Write data: 0x… / 0b… / dec]  [Send]                |
    +------------------------------------------------------+
    | footer                                               |
    +------------------------------------------------------+

* The **log** has one row per operation: ``Time``, ``Address`` (hex),
  ``Op`` (``wr`` / ``rd``) and ``Data`` (hex bytes, up to
  ``--max-data-bytes`` per row — 1024 by default — wrapped 16 bytes
  per line).  A read's data is shown once the upstream server has
  replied (``…`` while pending); a failed operation is marked with a
  red warning.
* **Selecting a log row** (``enter`` or double click) **autofills the
  form** to match the operation — the user can then edit any field
  and send it (``enter`` in a field or the ``Send`` button).
* The **Op** button toggles ``wr`` / ``rd`` (also the ``t`` key):
  *Write data* is only editable for ``wr``; *Size* is optional for
  ``wr`` (inferred from the write data) and required for ``rd``.
* **Write data** accepts ``0x…`` (hex), ``0b…`` (bin) and plain
  decimal.  Without an explicit size the byte width is inferred from
  the digit count (``0x0A0`` -> 2 B, ``0b0101`` -> 1 B, ``3243`` ->
  4 B).

Run the TUI::

    regio-ui -i <host> -p <port> [--listen-port N]   # via a TCP server
    regio-ui -f <cache.skelregio> [--listen-port N]  # via a cache file
    python -m regio_ui
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime
from typing import Optional

from regio import Regio
from regio import cli_utils
from regio.tcp import ADDR_MAX, PORT_DEFAULT, SIZE_MAX
from regio.tcp_client import RegioTcpClient
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Footer, Header, Input, Static

from regio_ui.proxy import RegioOp, RegioProxy, backend_kind
from regio_ui.values import parse_num

# operations log table column keys
COL_TIME, COL_ADDR, COL_OP, COL_DATA = "time", "addr", "op", "data"

#: how many operations the log table keeps (the oldest are dropped)
MAX_ROWS = 2000

#: how many payload bytes the Data column shows (longer payloads are
#: truncated, the full length is shown)
MAX_DATA_BYTES = 1024

#: how many payload bytes are shown per (wrapped) line in the Data
#: column
DATA_LINE_BYTES = 16


def _timestamp() -> str:
    """Current local time, e.g. ``12:34:56.789``."""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _data_str(data: bytes, max_bytes: int = MAX_DATA_BYTES) -> str:
    """Payload as space-separated hex bytes.

    Wrapped to lines of at most ``DATA_LINE_BYTES`` bytes, so a long
    payload becomes a tall, multi-line cell instead of one huge line;
    the payload is truncated to ``max_bytes`` bytes (the total length
    is shown then).
    """
    if not data:
        return ""
    shown_n = min(len(data), max_bytes)
    lines = [
        " ".join(f"{b:02X}" for b in data[ii:ii + DATA_LINE_BYTES])
        for ii in range(0, shown_n, DATA_LINE_BYTES)
    ]
    text = "\n".join(lines)
    if len(data) > max_bytes:
        text += f"\n… ({len(data)} B)"
    return text


def _data_cell(data: bytes, max_bytes: int = MAX_DATA_BYTES) -> Text:
    text = Text(_data_str(data, max_bytes))
    text.stylize("bright_black")
    return text


def auto_int(s: str) -> int:
    """Parse a CLI number: ``0x`` / ``0b`` prefixes or decimal."""
    try:
        return int(s, 0)
    except ValueError:
        return int(s)


class RegioUiApp(App):
    """regio TCP proxy TUI: logs the operations that flow between a
    regio TCP server and its clients, and sends new operations."""

    TITLE = "regio_ui"
    SUB_TITLE = "regio TCP proxy"

    CSS = """
    #ops {
        height: 1fr;
        border: round $primary;
    }
    /* the row cursor spans the whole row: a subtle background tint so
       the selected row (not just the selected cell) stands out */
    #ops > .datatable--cursor {
        background: $primary 25%;
        color: $foreground;
        text-style: bold;
    }
    #status {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        text-style: italic;
    }
    #form-row {
        height: 3;
    }
    #form-row > .input {
        border: round $accent;
    }
    #op-toggle {
        width: 8;
    }
    #addr {
        width: 1fr;
    }
    #size {
        width: 16;
    }
    #data {
        width: 1fr;
    }
    #send {
        width: 8;
    }
    """

    BINDINGS = [
        Binding("t", "toggle_op", "Toggle op", show=False),
        Binding("c", "clear_log", "Clear log"),
    ]

    def __init__(
        self,
        backend: Regio,
        backend_desc: str,
        listen_host: str = "0.0.0.0",
        listen_port: int = PORT_DEFAULT,
        max_data_bytes: int = MAX_DATA_BYTES,
    ) -> None:
        super().__init__()
        #: the regio device operations are forwarded to (a TCP client
        #: or a cache loaded from a file — see ``make_backend``)
        self.backend = backend
        #: human-readable backend: "host:port" (TCP) or a file path
        self.backend_desc = backend_desc
        self.listen_host = listen_host
        self.listen_port = listen_port
        #: maximum number of payload bytes shown in the Data column
        self.max_data_bytes = max_data_bytes

        backend_part = (
            f"file {backend_desc}"
            if backend_kind(backend) == "file"
            else f"upstream {backend_desc}"
        )
        self.SUB_TITLE = (
            f"{backend_part}  ·  listen {listen_host}:{listen_port}"
        )

        self._proxy: Optional[RegioProxy] = None
        self._tasks: list[asyncio.Task] = []
        #: log table row key -> operation
        self._row_ops: dict[str, RegioOp] = {}
        self._row_keys: list[str] = []
        self._n_ops = 0
        self._status_base = ""
        # the form's current op (True = wr, False = rd)
        self._op_write = True

    # ------------------------------------------------------------------
    # layout
    # ------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="ops")
        yield Static("", id="status")
        with Vertical(id="form"):
            with Horizontal(id="form-row"):
                yield Button("wr", id="op-toggle", variant="error")
                yield Input(placeholder="0x… / 0b… / decimal", id="addr")
                yield Input(placeholder="size (B)", id="size")
            with Horizontal(id="form-row2"):
                yield Input(
                    placeholder="write data (0x… / 0b… / decimal)",
                    id="data",
                )
                yield Button("Send", id="send", variant="success")
        yield Footer()

    def on_mount(self) -> None:
        self.ops = self.query_one("#ops", DataTable)
        self.status = self.query_one("#status", Static)
        self.op_button = self.query_one("#op-toggle", Button)
        self.addr_input = self.query_one("#addr", Input)
        self.size_input = self.query_one("#size", Input)
        self.data_input = self.query_one("#data", Input)
        self.send_button = self.query_one("#send", Button)

        self.ops.zebra_stripes = True
        self.ops.cursor_type = "row"
        self.ops.add_column("Time", key=COL_TIME, width=14)
        self.ops.add_column("Address", key=COL_ADDR, width=12)
        self.ops.add_column("Op", key=COL_OP, width=4)
        self.ops.add_column("Data", key=COL_DATA)

        self._proxy = RegioProxy(
            backend=self.backend,
            backend_desc=self.backend_desc,
            listen_host=self.listen_host,
            listen_port=self.listen_port,
            on_op=self._op_started,
            on_done=self._op_done,
            on_status=self._set_status_base,
        )
        for coro in (
            self._start_local_server_safe(),
            self._proxy.watch_upstream(),
        ):
            self._tasks.append(asyncio.create_task(coro))

        self._update_form()
        self.ops.focus()

    async def on_unmount(self) -> None:
        if self._proxy is not None:
            await self._proxy.close()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as err:  # noqa: BLE001
                logging.warning("regio_ui: task failed: %s", err)

    async def _start_local_server_safe(self) -> None:
        assert self._proxy is not None
        try:
            await self._proxy.start_local_server()
        except asyncio.CancelledError:
            raise
        except OSError as err:
            self.notify(
                f"cannot listen on {self.listen_host}:{self.listen_port}: "
                f"{err}",
                severity="error",
                timeout=None,
            )

    # ------------------------------------------------------------------
    # status
    # ------------------------------------------------------------------
    def _set_status_base(self, text: str) -> None:
        self._status_base = text
        self._update_status()

    @property
    def status_text(self) -> str:
        """The full status line text."""
        return f"{self._status_base}  ·  {self._n_ops} op(s)"

    def _update_status(self) -> None:
        self.status.update(self.status_text)

    # ------------------------------------------------------------------
    # proxy callbacks: log rows
    # ------------------------------------------------------------------
    def _op_started(self, op: RegioOp) -> str:
        """Add a log row for a new operation (called by the proxy)."""
        self._n_ops += 1
        key = f"op{self._n_ops}"
        # follow the log only when the cursor is already on the last
        # row (don't yank it down while the user reads the history)
        follow = self.ops.cursor_row == self.ops.row_count - 1

        self._row_ops[key] = op
        self._row_keys.append(key)
        if op.write:
            data_cell = self._data_cell(op.data or b"")
        else:
            data_cell = Text("…", style="dim")
        # height=None: the row grows to fit the (multi-line) data cell
        self.ops.add_row(
            Text(_timestamp()),
            Text(f"0x{op.addr:08X}", style="cyan"),
            Text(op.op_str, style="bold red" if op.write else "bold blue"),
            data_cell,
            key=key,
            height=None,
        )
        while len(self._row_keys) > MAX_ROWS:
            old = self._row_keys.pop(0)
            self._row_ops.pop(old, None)
            self.ops.remove_row(old)
        if follow:
            self.ops.move_cursor(row=self.ops.row_count - 1, column=0)
        self._update_status()
        return key

    def _op_done(
        self, key: str, data: Optional[bytes], error: Optional[str]
    ) -> None:
        """Update a log row when the forwarded operation has finished."""
        op = self._row_ops.get(key)
        if op is None:
            return
        if error is None:
            # a write's row was complete from the start; a read's row
            # gets its (response) data now
            if data is not None and not op.write:
                op.data = data
                self.ops.update_cell(
                    key, COL_DATA, self._data_cell(data), update_width=True
                )
            return
        if op.write:
            cell = Text(self._data_str(op.data or b"") + "  ")
        else:
            cell = Text()
        cell.append(f"⚠ {error}", style="red")
        self.ops.update_cell(key, COL_DATA, cell, update_width=True)

    def _data_cell(self, data: bytes) -> Text:
        """The Data cell for a payload (up to ``max_data_bytes``)."""
        return _data_cell(data, self.max_data_bytes)

    def _data_str(self, data: bytes) -> str:
        """The Data text for a payload (up to ``max_data_bytes``)."""
        return _data_str(data, self.max_data_bytes)

    # ------------------------------------------------------------------
    # form
    # ------------------------------------------------------------------
    def action_toggle_op(self) -> None:
        """Toggle the form's op between wr and rd (button / `t`)."""
        self._op_write = not self._op_write
        self._update_form()

    def _update_form(self) -> None:
        if self._op_write:
            self.op_button.label = "wr"
            self.op_button.variant = "error"
            self.size_input.placeholder = "size (B, optional)"
            self.data_input.placeholder = "write data (0x… / 0b… / decimal)"
            self.data_input.disabled = False
        else:
            self.op_button.label = "rd"
            self.op_button.variant = "primary"
            self.size_input.placeholder = "size (B, required)"
            self.data_input.placeholder = "(rd: no write data)"
            self.data_input.disabled = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "op-toggle":
            self.action_toggle_op()
        elif event.button.id == "send":
            self._send()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id in ("addr", "size", "data"):
            self._send()

    def _fill_form(self, op: RegioOp) -> None:
        """Autofill the form from a logged operation (the user can
        still edit every field before sending it)."""
        self._op_write = op.write
        self.addr_input.value = f"0x{op.addr:08X}"
        self.size_input.value = str(op.size)
        if op.write:
            value = int.from_bytes(op.data or b"0", "little")
            self.data_input.value = f"0x{value:X}" if value else "0x0"
        else:
            self.data_input.value = ""
        self._update_form()
        self.addr_input.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """enter (or double click) on a log row: autofill the form."""
        op = self._row_ops.get(event.row_key)
        if op is None:
            return
        self._fill_form(op)

    # ------------------------------------------------------------------
    # sending
    # ------------------------------------------------------------------
    def _form_error(self, msg: str, focus: Input) -> None:
        self.notify(msg, severity="warning", timeout=4)
        focus.focus()

    def _send(self) -> None:
        """Validate the form and send the operation."""
        parsed_addr = parse_num(self.addr_input.value)
        if parsed_addr is None:
            self._form_error(
                "address: use 0x… (hex), 0b… (bin) or decimal",
                self.addr_input,
            )
            return
        addr = parsed_addr[0]
        if not 0 <= addr <= ADDR_MAX:
            self._form_error(
                f"address must be in 0 .. 0x{ADDR_MAX:X}", self.addr_input
            )
            return

        if self._op_write:
            parsed = parse_num(self.data_input.value)
            if parsed is None:
                self._form_error(
                    "write data: use 0x… (hex), 0b… (bin) or decimal",
                    self.data_input,
                )
                return
            value, inferred_size = parsed
            size_text = self.size_input.value.strip()
            if size_text:
                parsed_size = parse_num(size_text)
                if parsed_size is None:
                    self._form_error(
                        "size: use 0x… (hex), 0b… (bin) or decimal",
                        self.size_input,
                    )
                    return
                size = parsed_size[0]
                if not 1 <= size <= SIZE_MAX:
                    self._form_error(
                        f"size must be in 1 .. {SIZE_MAX}", self.size_input
                    )
                    return
                if value >= 256**size:
                    self._form_error(
                        f"write data does not fit in {size} byte(s)",
                        self.data_input,
                    )
                    return
            else:
                # no explicit size: infer it from the digit count
                size = inferred_size
            payload = value.to_bytes(size, "little")
            self.run_worker(
                self._send_write(addr, payload),
                name="send",
                group="send",
                exclusive=False,
            )
        else:
            parsed_size = parse_num(self.size_input.value)
            if parsed_size is None:
                self._form_error(
                    "size is required for a read (rd)", self.size_input
                )
                return
            size = parsed_size[0]
            if not 1 <= size <= SIZE_MAX:
                self._form_error(
                    f"size must be in 1 .. {SIZE_MAX}", self.size_input
                )
                return
            self.run_worker(
                self._send_read(addr, size),
                name="send",
                group="send",
                exclusive=False,
            )

    async def _send_write(self, addr: int, payload: bytes) -> None:
        assert self._proxy is not None
        _, err = await self._proxy.relay_write(addr, payload)
        if err is not None:
            self.notify(f"write failed: {err}", severity="error", timeout=4)

    async def _send_read(self, addr: int, size: int) -> None:
        assert self._proxy is not None
        _, _, err = await self._proxy.relay_read(addr, size)
        if err is not None:
            self.notify(f"read failed: {err}", severity="error", timeout=4)

    # ------------------------------------------------------------------
    # log clearing
    # ------------------------------------------------------------------
    def action_clear_log(self) -> None:
        self.ops.clear()
        self._row_ops.clear()
        self._row_keys.clear()
        self._update_status()


def build_parser() -> argparse.ArgumentParser:
    """The regio_ui CLI: the shared regio backend options (from
    ``regio.cli_utils``: ``-i/--host``, ``-f/--file``, ``-p/--port``,
    ``--debug-print-regio``) plus the local-listen / display options."""
    parser = argparse.ArgumentParser(
        prog="regio-ui",
        description=(
            "regio_ui — regio proxy TUI: logs all regio operations "
            "flowing to a regio device (a TCP server on another port, "
            "or a regio cache file), and can send new operations"
        ),
    )
    cli_utils.add_parser_args(parser)
    parser.add_argument(
        "--listen-host",
        default="0.0.0.0",
        help="Host of the local (client-facing) regio TCP server "
        "(default: 0.0.0.0)",
    )
    parser.add_argument(
        "--listen-port",
        type=auto_int,
        default=PORT_DEFAULT,
        help=f"Port of the local (client-facing) regio TCP server "
        f"(default: {PORT_DEFAULT})",
    )
    parser.add_argument(
        "--max-data-bytes",
        type=int,
        default=MAX_DATA_BYTES,
        help="Maximum number of payload bytes shown in the Data column "
        f"of each log row (default: {MAX_DATA_BYTES})",
    )
    return parser


async def make_backend(
    args: argparse.Namespace,
) -> tuple[Regio, str]:
    """Create the backend regio device from the parsed CLI args (via
    ``regio.cli_utils``): a regio TCP server (``-i``/``-p``) or a
    regio cache file (``-f``).

    Returns ``(backend, description)``.  A TCP server that is not
    reachable *yet* is not an error — the backend is returned
    unconnected and the proxy keeps (re)trying to connect.  A cache
    file that cannot be loaded is fatal (``SystemExit``).
    """
    try:
        backend = await cli_utils.make_regio_from_args(args)
    except (OSError, asyncio.TimeoutError, ValueError) as err:
        if args.file is not None:
            raise SystemExit(
                f"regio-ui: cannot load cache file {args.file}: {err}"
            )
        logging.warning(
            "regio-ui: cannot connect to upstream %s:%s: %s (will keep "
            "trying)", args.host, args.port, err,
        )
        backend = RegioTcpClient(host=args.host, port=args.port)
        if args.debug_print_regio:
            backend.log_regio = True
    if args.file is not None:
        return backend, str(args.file)
    return backend, f"{args.host}:{args.port}"


def main() -> None:
    """Console-script entry point: run the regio_ui TUI."""
    args = build_parser().parse_args()

    logging.basicConfig(level=logging.WARNING)

    async def _run() -> None:
        backend, backend_desc = await make_backend(args)
        app = RegioUiApp(
            backend=backend,
            backend_desc=backend_desc,
            listen_host=args.listen_host,
            listen_port=args.listen_port,
            max_data_bytes=args.max_data_bytes,
        )
        await app.run_async()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
