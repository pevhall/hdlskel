"""The regio_ui UI as a reusable Textual *widget* (``RegioUiView``).

The view contains the operations log (``Time | Address | Op | Data``),
the status line and the new-operation form — everything the
:class:`~regio_ui.app.RegioUiApp` TUI shows between header and footer.
Splitting it out lets the same view be embedded in another Textual app
as a tab (``skmap_ui`` hosts it on its *Regio* tab).

Operations reach the view through its proxy-callback methods
:meth:`op_started` / :meth:`op_done` — the same signatures the
:class:`~regio_ui.proxy.RegioProxy` reports to (a
:class:`~regio_ui.tap.RegioTap` uses them too).  New operations from
the form go to ``sender``, any object with the proxy's relay API::

    async relay_write(addr, data) -> (key, error | None)
    async relay_read(addr, size)  -> (key, payload, error | None)

**Capture** (:attr:`capture`, key ``p``): while on (the default when
regio_ui runs on its own), every reported operation is logged; while
off the operations are *not* logged (an embedding app can start the
view not capturing, so its boot-time traffic does not flood the log —
``skmap_ui`` does exactly that).  The status line shows the current
state, toggled with ``p``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from regio.tcp import ADDR_MAX, SIZE_MAX
from rich.text import Text
from textual.containers import Horizontal, Vertical
from textual.binding import Binding
from textual.widgets import Button, DataTable, Input, Static

from regio_ui.proxy import RegioOp
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


class RegioUiView(Vertical):
    """The regio_ui operations log + status line + new-operation form.

    The caller feeds operations with :meth:`op_started` /
    :meth:`op_done` (the :class:`~regio_ui.proxy.RegioProxy` callback
    signatures) and sets :attr:`sender` (anything with the proxy's
    ``relay_write`` / ``relay_read``) for operations sent from the
    form.  ``capture`` (key ``p``) turns the logging on / off.
    """

    DEFAULT_CSS = """
    RegioUiView {
        layout: vertical;
        /* fill the available space (the app screen when run standalone,
           the tab pane when embedded) — without this the view is
           auto-height and the 1fr log collapses */
        height: 1fr;
    }
    RegioUiView #ops {
        height: 1fr;
        border: round $primary;
    }
    /* the row cursor spans the whole row: a subtle background tint so
       the selected row (not just the selected cell) stands out */
    RegioUiView #ops > .datatable--cursor {
        background: $primary 25%;
        color: $foreground;
        text-style: bold;
    }
    RegioUiView #status {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        text-style: italic;
    }
    RegioUiView #form-row {
        height: 3;
    }
    RegioUiView #form-row > .input {
        border: round $accent;
    }
    RegioUiView #op-toggle {
        width: 8;
    }
    RegioUiView #addr {
        width: 1fr;
    }
    RegioUiView #size {
        width: 16;
    }
    RegioUiView #data {
        width: 1fr;
    }
    RegioUiView #send {
        width: 8;
    }
    """

    BINDINGS = [
        Binding("t", "toggle_op", "Toggle op", show=False),
        ("c", "clear_log", "Clear log"),
        ("p", "toggle_capture", "Capture"),
    ]

    def __init__(
        self,
        *,
        backend_desc: str = "",
        sender=None,
        capture: bool = True,
        max_data_bytes: int = MAX_DATA_BYTES,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        #: the object new form operations are sent to (a RegioProxy or
        #: RegioTap — anything with relay_write / relay_read); None
        #: until the caller wires it up
        self.sender = sender
        #: human-readable backend / source shown in the status line
        self.backend_desc = backend_desc
        #: maximum number of payload bytes shown in the Data column
        self.max_data_bytes = max_data_bytes
        #: while True every reported operation is logged; while False
        #: operations pass by without being logged (key ``p`` toggles)
        self.capture = capture

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
    def compose(self):
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

        self._update_form()
        self._update_status()
        # NB: no focus() here — embedding apps manage the focus (the
        # standalone RegioUiApp focuses this view's table on mount)

    # ------------------------------------------------------------------
    # status
    # ------------------------------------------------------------------
    def set_status(self, text: str) -> None:
        """Set the status line's base text (proxy / tap status)."""
        self._status_base = text
        self._update_status()

    @property
    def status_text(self) -> str:
        """The full status line text."""
        cap = "on" if self.capture else "off"
        return (
            f"{self._status_base}  ·  {self._n_ops} op(s)  ·  "
            f"capture: {cap} [p]"
        )

    def _update_status(self) -> None:
        if self.query("#status"):
            self.status.update(self.status_text)

    # ------------------------------------------------------------------
    # capture
    # ------------------------------------------------------------------
    def action_toggle_capture(self) -> None:
        """Start / stop logging operations (key `p`)."""
        self.capture = not self.capture
        self._update_status()

    # ------------------------------------------------------------------
    # operation log (proxy / tap callbacks)
    # ------------------------------------------------------------------
    def op_started(self, op: RegioOp) -> str:
        """Add a log row for a new operation (returns the row key).

        While capture is off nothing is logged — the returned key is
        empty, which the proxy / tap treats as "no completion report".
        """
        if not self.capture:
            return ""
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

    def op_done(
        self, key: str, data: Optional[bytes], error: Optional[str]
    ) -> None:
        """Update a log row when the reported operation has finished."""
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
        if not self.query("#op-toggle"):
            return
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
        if self.sender is None:
            self.notify("no regio backend connected", severity="error")
            return
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
        _, err = await self.sender.relay_write(addr, payload)
        if err is not None:
            self.notify(f"write failed: {err}", severity="error", timeout=4)

    async def _send_read(self, addr: int, size: int) -> None:
        _, _, err = await self.sender.relay_read(addr, size)
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
