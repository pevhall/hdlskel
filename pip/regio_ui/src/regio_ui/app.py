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

The UI itself is the reusable :class:`~regio_ui.view.RegioUiView`
widget (operations log + status line + form), so it can also be
embedded in another Textual app — ``skmap_ui`` hosts it on a *Regio*
tab (there it feeds the view from a :class:`~regio_ui.tap.RegioTap`
on its own regio device and starts it **not capturing**, see
``--no-capture`` here for the same option standalone).

Layout::

    +------------------------------------------------------+
    | header                                               |
    +------------------------------------------------------+
    | operations log (DataTable)                           |
    | Time | Address | Op | Data                           |
    +------------------------------------------------------+
    | status line (listening / backend state, op count,    |
    |                capture on/off)                       |
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
* **Capture** (``p``): while on (the default — but see
  ``--no-capture``) operations are logged; while off they pass by
  without being logged.

Run the TUI::

    regio-ui -i <host> -p <port> [--listen-port N]   # via a TCP server
    regio-ui -f <cache.skelregio> [--listen-port N]  # via a cache file
    python -m regio_ui
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Optional

from regio import Regio
from regio import cli_utils
from regio.tcp import PORT_DEFAULT
from regio.tcp_client import RegioTcpClient
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

from regio_ui.proxy import RegioProxy, backend_kind
from regio_ui.view import MAX_DATA_BYTES, MAX_ROWS, RegioUiView

__all__ = [
    "RegioUiApp",
    "RegioUiView",
    "main",
    "build_parser",
    "make_backend",
    "MAX_ROWS",
    "MAX_DATA_BYTES",
]


def auto_int(s: str) -> int:
    """Parse a CLI number: ``0x`` / ``0b`` prefixes or decimal."""
    try:
        return int(s, 0)
    except ValueError:
        return int(s)


class RegioUiApp(App):
    """regio TCP proxy TUI: logs the operations that flow between a
    regio TCP server and its clients, and sends new operations.

    ``capture=False`` starts the log **not capturing** (the ``p`` key
    toggles it) — used when regio_ui is started through another app
    (``skmap_ui``) so its boot-time operations do not flood the log;
    a directly started regio_ui captures from the beginning.
    """

    TITLE = "regio_ui"
    SUB_TITLE = "regio TCP proxy"

    def __init__(
        self,
        backend: Regio,
        backend_desc: str,
        listen_host: str = "0.0.0.0",
        listen_port: int = PORT_DEFAULT,
        max_data_bytes: int = MAX_DATA_BYTES,
        capture: bool = True,
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
        #: start the log capturing (True, default) or not (``p`` toggles)
        self.capture = capture

        backend_part = (
            f"file {backend_desc}"
            if backend_kind(backend) == "file"
            else f"upstream {backend_desc}"
        )
        self.SUB_TITLE = (
            f"{backend_part}  ·  listen {listen_host}:{listen_port}"
        )

        self._view: Optional[RegioUiView] = None
        self._proxy: Optional[RegioProxy] = None
        self._tasks: list[asyncio.Task] = []

    # ------------------------------------------------------------------
    # layout
    # ------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header()
        yield RegioUiView(
            backend_desc=self.backend_desc,
            capture=self.capture,
            max_data_bytes=self.max_data_bytes,
        )
        yield Footer()

    def on_mount(self) -> None:
        self._view = view = self.query_one(RegioUiView)
        self._proxy = RegioProxy(
            backend=self.backend,
            backend_desc=self.backend_desc,
            listen_host=self.listen_host,
            listen_port=self.listen_port,
            on_op=view.op_started,
            on_done=view.op_done,
            on_status=view.set_status,
        )
        # the form's operations go through the proxy (logged like all
        # the rest)
        view.sender = self._proxy
        view.ops.focus()
        for coro in (
            self._start_local_server_safe(),
            self._proxy.watch_upstream(),
        ):
            self._tasks.append(asyncio.create_task(coro))

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
    # delegates to the view (stable app-level API)
    # ------------------------------------------------------------------
    @property
    def view(self) -> RegioUiView:
        """The embedded :class:`~regio_ui.view.RegioUiView` widget."""
        return self._view_or_raise

    @property
    def _view_or_raise(self) -> RegioUiView:
        assert self._view is not None
        return self._view

    @property
    def ops(self):
        return self._view_or_raise.ops

    @property
    def status(self):
        return self._view_or_raise.status

    @property
    def op_button(self):
        return self._view_or_raise.op_button

    @property
    def addr_input(self):
        return self._view_or_raise.addr_input

    @property
    def size_input(self):
        return self._view_or_raise.size_input

    @property
    def data_input(self):
        return self._view_or_raise.data_input

    @property
    def send_button(self):
        return self._view_or_raise.send_button

    @property
    def status_text(self) -> str:
        """The full status line text."""
        return self._view_or_raise.status_text

    @property
    def _row_ops(self):
        return self._view_or_raise._row_ops

    @property
    def _op_write(self) -> bool:
        return self._view_or_raise._op_write

    def action_toggle_op(self) -> None:
        self._view_or_raise.action_toggle_op()

    def action_toggle_capture(self) -> None:
        self._view_or_raise.action_toggle_capture()

    def action_clear_log(self) -> None:
        self._view_or_raise.action_clear_log()


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
    parser.add_argument(
        "--no-capture",
        action="store_true",
        help="Start with log capturing OFF: operations pass by "
             "without being logged until the capture is started "
             "(the 'p' key toggles it).  regio_ui started through "
             "skmap_ui uses this so its boot-time operations are not "
             "logged; started directly it captures from the start.",
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
            capture=not args.no_capture,
        )
        await app.run_async()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
