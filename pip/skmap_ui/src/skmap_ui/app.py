"""Textual TUI for browsing a real ``skmap.Module`` register map.

Layout::

    +-----------------------------------------------------------+
    | header                                                    |
    +------------------------+----------------------------------+
    | module tree            | register map table of the        |
    | (kids + external mems, | selected module:                 |
    | like print_tree_cached | Addr | T | Acc | Name | Value |  |
    | )                      | Description                      |
    +------------------------+----------------------------------+
    | value input line                                            |
    +-----------------------------------------------------------+
    | log of triggered register assets                          |
    +-----------------------------------------------------------+
    | footer                                                    |
    +-----------------------------------------------------------+

Pass a real ``skmap.Module`` (e.g. built with ``make_module``):

    from skmap import make_module
    from skmap_ui import SkmapUiApp

    module = await make_module(regio, addr)
    SkmapUiApp(module).run()

On start (and with the ``a`` key) the app runs ``make_tree()`` and
``check_assert_tree_cached()``.  The bottom log view is an *event
log* of the triggered register assets (skmap's "asserts": registers
/ flags whose value is set and that carry an ``Ass`` level):
every assert check that finds triggered asserts appends one block —
a time stamp followed by a table with one row per triggered assert
(same columns as ``print_table_reg_list``) — so the log grows after
every refresh that contains triggered asserts; checks without
triggered asserts append nothing.  The register map table mirrors
``print_reg_map_cached`` (skmap's ``RegMapTable``): address, value
type, access, name, value, description; ``k`` registers are shown
(value is fixed, never read from the device).

Assert options: ``--asserts-level`` / the ``l`` key selects the
``Ass`` level at which asserts are logged (debug -> info -> warn
-> error -> fatal; lower levels are still evaluated, just not
logged).  ``--refresh SECS`` / the ``r`` key periodically re-reads
all registers from the device (``read_all_tree()``), re-checks all
asserts (logging the triggered ones, if any), updates the register
map, then clears all ``rc`` registers of the *selected* module
(``clear_reg_rc()`` — the register map only shows that module) and
the triggered asserts of the *whole tree*
(``clear_assert_tree()`` — the log checks recursively) so the next
refresh only logs new events (0 = off).  The ``x`` key does the same
clear on demand and re-checks.  Register writes (``enter`` / ``t``)
are **held** while a refresh is in progress and only go to the device
once it has finished.  A value outside a register's configured
min / max limits is caught locally (the same condition
``Reg.check_value_limit()`` raises on) and the write is aborted
before it reaches the device.  Device I/O errors are reported on the
console via ``logging`` so the log view only ever contains triggered
asserts.

The tree starts fully expanded; ``enter``
selects the module under the cursor and shows its register map (mirrors
``print_reg_map_cached``), and the node of the module whose register map
is currently shown is highlighted in the tree.  ``left`` / ``right``
collapse / expand the cursor node.  ``enter`` on a table row edits the
value of ``rw`` / ``wt`` registers: the input line is prefilled with
the *current* value and can be edited in place (``enter`` to write,
``escape`` to cancel, both hex and decimal accepted); a *vector*
register opens one input column per vector index (each prefilled with
the current lane value via ``Reg.read_idx_value_cached``), written
lane by lane with ``Reg.write_idx_uint`` / ``Reg.write_idx_sint``;
``rc`` registers are cleared (writes zero).  Long values wrap over
multiple lines in the *Value* column, which is left-aligned.  An
external mem that is an ``ExternalMemVec`` (vec-typed external mem)
opens a vec view: a header row (the border title shows the mem's
addr, type, acc, name and description) plus one row per vector index
(the value cells are read with ``ExternalMemVec.read_idx_rich_str_cached``);
``enter`` on a lane row edits that lane (written with
``ExternalMemVec.write_idx_uint`` / ``write_idx_sint``), on the
header row it opens one input per lane; ``rc`` lanes are cleared
(writes zero) on ``enter``.  ``t`` triggers the selected register row:
writable registers / flags are *written* (``t`` on a register with
min / max limits picks a random value *within* the limits),
read-only ones are *read* (skmap's "trigger" = register write).  All
register / flag / mem device accesses use skmap's async *non-cached*
regio reads/writes (never ``*_cached``), so the value really goes to
/ comes from the regio (live TCP server or cache file) and the skmap
cache is refreshed; ``k`` (hardwired) and ``na`` (no access) assets
are never read back.  All three panes are resizable with the mouse:
drag the divider between tree and table, or between the table and the
log.  The ``v`` key toggles the display of ``uint`` / ``sint`` values
between int (decimal) and bits (hex, like the ``bits`` kind) — the
input prefill follows the display; the ``e`` key expands vector
registers in the register map into one row per vector index (like the
``ExternalMemVec`` view): ``enter`` on a lane row edits just that lane
(``enter`` on an ``rc`` lane clears it).  The active options are shown
in the table's border title.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Union

import regio.cli_utils
import skmap.cli_utils
from rich.table import Table
from rich.text import Text
from skmap import (
    Acc,
    Ass,
    ExternalMem,
    Module,
    RFlag,
    Reg,
    RegFlags,
    RegVec,
    ValueKind,
    make_module,
)
from skmap.external_mem import ExternalMemCached, ExternalMemVec
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.timer import Timer
from textual.widgets import DataTable, Footer, Header, Input, RichLog, Tree

from skmap_ui import __version__

# register map table column keys (mirror skmap RegMapTable columns)
COL_ADDR, COL_T, COL_ACC, COL_NAME, COL_VALUE, COL_DESC = (
    "addr",
    "t",
    "acc",
    "name",
    "value",
    "desc",
)

# object stored per table row: a register, a flag, or an external mem
RowObj = Union[Reg, RFlag, ExternalMem]

#: assert levels the user can select (``--asserts-level`` / ``l`` key)
asserts_levels = (Ass.debug, Ass.info, Ass.warn, Ass.error, Ass.fatal)

#: periodic refresh periods in seconds (``--refresh`` / ``r`` key);
#: None = refresh off
refresh_intervals = (None, 1.0, 5.0, 30.0)


def _timestamp() -> str:
    """Current local time stamp, e.g. ``2025-01-01 12:00:00.123``."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _hex(value: int, width: int) -> str:
    """Hex string with as many digits as the value width has bytes."""
    return f"0x{value:0{-(-width // 8)}X}"


def _assert_value_str(obj: Union[Reg, RFlag]) -> str:
    """Plain (markup-free) value string of a triggered assert asset."""
    if isinstance(obj, RFlag):
        return Text.from_markup(obj._value_rich_str()).plain
    return Text.from_markup(obj.read_rich_str_cached()).plain


class ModuleTree(Tree):
    """Module tree with left/right arrow expand/collapse of the cursor node.

    The base :class:`~textual.widgets.Tree` already binds ``enter`` to
    select the node under the cursor (which shows the module register
    map) and ``space`` to toggle expansion; this adds plain ``left`` /
    ``right``.  ``auto_expand`` is disabled so that selecting a node is
    pure selection (no expand/collapse side effect).  The node whose
    register map is currently shown is *highlighted* (see
    :meth:`set_highlighted`).
    """

    BINDINGS = [
        Binding("left", "node_collapse", "Collapse", show=False),
        Binding("right", "node_expand", "Expand", show=False),
    ]

    #: style of the node whose register map is currently shown
    HIGHLIGHT = "bold bright_blue"

    def __init__(self, label, **kwargs) -> None:
        super().__init__(label, **kwargs)
        self.auto_expand = False
        #: node whose register map is currently shown (highlighted)
        self.highlighted: Tree.Node | None = None

    def set_highlighted(self, node: Tree.Node | None) -> None:
        """Highlight the node whose register map is being shown."""
        if self.highlighted is node:
            return
        old = self.highlighted
        self.highlighted = node
        if old is not None:
            old.refresh()  # re-render the old line (un-highlight it)
        if node is not None:
            node.refresh()  # re-render the new line (highlight it)

    def render_label(self, node, base_style, style):
        text = super().render_label(node, base_style, style)
        if node is self.highlighted:
            text.stylize(self.HIGHLIGHT)
        return text

    def action_node_collapse(self) -> None:
        node = self.cursor_node
        if node is not None and node.children:
            node.collapse()

    def action_node_expand(self) -> None:
        node = self.cursor_node
        if node is not None and node.children:
            node.expand()


class RegMapTable(DataTable):
    """Register map table where ``enter`` requests editing the row.

    The table's built-in ``enter`` binding (``select_cursor``) is
    overridden: instead of posting a row-selected message it posts
    :attr:`EditRequested`, which the app uses to open the value editor
    for the cursor row.
    """

    class EditRequested(Message):
        """Posted when ``enter`` is pressed on the table."""

    def action_select_cursor(self) -> None:
        self.post_message(self.EditRequested())


class ValueInput(Input):
    """Input line for a new register value.

    ``enter`` submits (posts ``Input.Submitted``); ``escape`` cancels
    the edit (posts :attr:`Canceled`).
    """

    BINDINGS = Input.BINDINGS + [
        Binding("escape", "cancel_edit", "Cancel", show=False),
    ]

    class Canceled(Message):
        """Posted when the user cancels the edit with ``escape``."""

    def action_cancel_edit(self) -> None:
        self.post_message(self.Canceled())


class SkmapUiApp(App):
    """Register map browser for a real ``skmap.Module`` tree."""

    TITLE = "skmap_ui"
    SUB_TITLE = f"register map explorer v{__version__}"

    CSS = """
    #workspace { height: 80%; }
    #modules { width: 35%; border: round $primary; }
    #registers { width: 1fr; border: round $accent; }
    #value-inputs { height: 3; }
    #value-input { width: 100%; border: round $warning; }
    #value-inputs .lane { width: 1fr; border: round $warning; }
    #log { height: 1fr; min-height: 7; border: round $success; }
    """

    BINDINGS = [
        ("t", "trigger_selected", "Trigger"),
        ("a", "check_asserts", "Check asserts"),
        ("c", "clear_log", "Clear log"),
        ("l", "cycle_asserts_level", "Assert level"),
        ("r", "cycle_refresh", "Refresh"),
        ("x", "clear_triggered", "Clear triggered"),
        ("v", "toggle_value_bits", "Value bits"),
        ("e", "toggle_expand_vec", "Expand vec"),
        Binding("enter", "edit_selected_value", "Edit value", show=False),
    ]

    #: mouse hit-zone (cells) around a pane divider that starts a drag
    _RESIZE_EDGE = 3

    def __init__(
        self,
        top_module: Module,
        *,
        asserts_level: Ass = Ass.debug,
        refresh: float | None = None,
    ) -> None:
        super().__init__()
        self.top_module = top_module
        self.asserts_level = asserts_level
        # NB: must NOT be named "refresh" — that would shadow App.refresh()
        # and break Textual internals (e.g. screen removal when the keys
        # screen is closed: parent.refresh(layout=True) -> TypeError).
        self.refresh_period = refresh
        self._refresh_timer: Timer | None = None
        self.last_asserts: list[Union[RFlag, Reg]] = []
        self.last_worst_ass: Ass = Ass.passed
        self.asserts_checked = False
        self._asserts_checking = False
        self._log_lines: list[str] = []
        self._row_keys: list[str] = []
        self._row_objs: dict[str, RowObj] = {}
        self._row_module: Module | None = None
        self._drag: str | None = None  # "h" (tree|table) or "v" (workspace|log)
        # one regio connection on one event loop: serialize device I/O
        self._regio_lock = asyncio.Lock()
        # set while no periodic refresh is in flight.  Register writes
        # (enter / t) wait on this, so a write is never made in the
        # middle of a refresh: a refresh reads the whole tree and then
        # clears the rc registers, so a write landing inside it would
        # be observed (or wiped) by the refresh.  The write is held
        # until the refresh has finished.
        self._refresh_idle = asyncio.Event()
        self._refresh_idle.set()
        # last value strings shown in the register map (row key -> plain
        # text), plus the value-column padding used when the table was
        # built.  Used to skip DataTable.update_cell() for unchanged
        # values: every update_cell() call bumps the table's _update_count,
        # which invalidates its whole render cache, so per-tick no-op
        # updates would re-render the table and grow its caches
        # (memory churn).
        self._row_value_str: dict[str, str] = {}
        # ExternalMemVec view: row key -> vec index of the lane rows
        # (the header row's key is _mem_view_header)
        self._row_mem_idx: dict[str, int] = {}
        self._mem_view_header: str | None = None
        # (row key, lane index) the input line is currently editing
        # (index None = every lane: the header row of a vec mem view);
        # the row's obj is an ExternalMemVec or a Reg (a lane row of an
        # expanded vector register)
        self._edit_lane: tuple[str, int | None] | None = None
        # vector register lane rows of the shown module map (row key ->
        # vector index), filled while _expand_vec is on
        self._row_reg_idx: dict[str, int] = {}
        # the external mem currently shown in the table (None: a module
        # map is shown)
        self._row_mem: ExternalMem | None = None
        # value display: False = int (decimal for uint / sint),
        # True = bits (hex, like the bits kind) — the 'v' key
        self._value_bits = False
        # register map: expand vector registers into one row per vector
        # index (like the ExternalMemVec view) — the 'e' key
        self._expand_vec = False

    # ------------------------------------------------------------------
    # layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="workspace"):
            yield ModuleTree(self.top_module.name(), id="modules")
            yield RegMapTable(id="registers")
        with Horizontal(id="value-inputs"):
            yield ValueInput(
                id="value-input",
                placeholder=(
                    "enter: edit (rw/wt) / clear (rc) | l: assert level | "
                    "r: refresh | x: clear triggered | a: check asserts | "
                    "v: value bits | e: expand vec"
                ),
            )
        yield RichLog(id="log", markup=True, min_width=0)
        yield Footer()

    def on_mount(self) -> None:
        self.tree_view = self.query_one("#modules", ModuleTree)
        self.table = self.query_one("#registers", RegMapTable)
        self.value_input = self.query_one("#value-input", ValueInput)
        self.value_inputs = self.query_one("#value-inputs", Horizontal)
        self.log_view = self.query_one("#log", RichLog)
        self.workspace = self.query_one("#workspace", Horizontal)
        self.header = self.query_one(Header)
        self.footer = self.query_one(Footer)

        self.table.zebra_stripes = True
        for key, label, width in (
            (COL_ADDR, "Addr", 12),
            (COL_T, "T", 8),
            (COL_ACC, "Acc", 8),
            (COL_NAME, "Name", 24),
            (COL_VALUE, "Value", 22),
            (COL_DESC, "Description", None),
        ):
            self.table.add_column(label, key=key, width=width)

        root_node = self._build_tree()
        self._force_lines()
        self._update_log_title()
        if root_node is not None:
            # show the top module's register map right away
            self.tree_view.select_node(root_node)
        # the table gets the initial focus (otherwise the value input
        # line swallows the single-key shortcuts l / r / x)
        self.table.focus()
        self._set_refresh_timer()
        self.run_worker(self._check_asserts(), name="check_asserts", exclusive=False)

    # ------------------------------------------------------------------
    # tree view (mirrors Module.print_tree_cached)
    # ------------------------------------------------------------------

    def _build_tree(self):
        # textual 8.x trees show the (otherwise hidden) root node, and it
        # starts collapsed — use it as the top module's node and expand it
        self.tree_view.clear()
        root_node = self.tree_view.root
        root_node.set_label(self.top_module.to_one_line_rich_str())
        root_node.data = self.top_module
        root_node.expand()
        self._add_tree_children(root_node, self.top_module)
        return root_node

    def _add_tree_children(self, parent_node, module: Module) -> None:
        for mem in module.arr_external_mem:
            parent_node.add(
                f"📔 [green]{hex(mem.base_addr)}[/green] [cyan]{mem.name}[/cyan] "
                f"[blue]{mem.acc} {mem.size} B[/blue]",
                data=mem,
            )
        for ii, kid in enumerate(module.kids_cached()):
            if kid is None:
                parent_node.add(
                    f"📕 [green]{hex(module._kid_addrs[ii])}[/green] "
                    "[red]Uninitalised module[/red]"
                )
            else:
                # start fully expanded (like print_tree_cached output)
                child_node = parent_node.add(
                    kid.to_one_line_rich_str(),
                    data=kid,
                    expand=True,
                )
                self._add_tree_children(child_node, kid)

    def _force_lines(self) -> None:
        # force the (lazy) line rebuild so node._line values are up to date
        _ = self.tree_view._tree_lines  # private but stable

    def _node_for(self, obj) -> Tree.Node | None:
        if self.tree_view.root.data is obj:
            return self.tree_view.root

        def walk(node: Tree.Node):
            for child in node.children:
                if child.data is obj:
                    return child
                found = walk(child)
                if found is not None:
                    return found
            return None

        return walk(self.tree_view.root)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if isinstance(data, Module):
            self.tree_view.set_highlighted(event.node)
            self._show_module(data)
        elif isinstance(data, ExternalMem):
            self.tree_view.set_highlighted(event.node)
            self._show_mem(data)
        # uninitialised module nodes have no register map; pressing 'a'
        # (check asserts) builds the module tree first

    # ------------------------------------------------------------------
    # register map table (mirrors RegMapTable.add_module)
    # ------------------------------------------------------------------

    def _view_options_suffix(self) -> str:
        """Border title suffix with the active display options ('v' / 'e').

        NB: parentheses, not brackets — the border title is rich markup
        and a ``[bits]`` suffix would be parsed as (and swallowed by) a
        style tag.
        """
        opts = []
        if self._value_bits:
            opts.append("bits")
        if self._expand_vec:
            opts.append("expand vec")
        return f"  ({', '.join(opts)})" if opts else ""

    def _reg_value_text(self, reg: Reg) -> Text:
        """Rich value cell of a register's own row (a header row when
        the register is expanded).

        Follows the ``v`` display toggle: when on, ``uint`` / ``sint``
        values are shown as bits (hex, like the ``bits`` kind — sint
        lanes as their raw two's complement) instead of int.
        """
        kind = reg.value_type.kind
        if self._value_bits and kind in (ValueKind.uint, ValueKind.sint):
            if reg.value_type.is_vec:
                values = reg.read_list_uint_cached()
                return Text(
                    "[ "
                    + ", ".join(_hex(v, reg.value_type.width) for v in values)
                    + " ]"
                )
            return Text(_hex(reg.read_uint_cached(), reg.value_type.width))
        return Text.from_markup(reg.read_rich_str_cached())

    def _reg_lane_value_text(self, reg: Reg, idx: int) -> Text:
        """Rich value cell of one lane row of an expanded vector
        register (see ``_reg_value_text``)."""
        kind = reg.value_type.kind
        if self._value_bits and kind in (ValueKind.uint, ValueKind.sint):
            return Text(_hex(reg.read_idx_uint_cached(idx), reg.value_type.width))
        return Text(str(reg.read_idx_value_cached(idx)))

    def _mem_lane_value_text(self, mem: ExternalMemVec, idx: int) -> Text:
        """Rich value cell of one ExternalMemVec lane (see
        ``_reg_lane_value_text``)."""
        kind = mem.value_type.kind
        if self._value_bits and kind in (ValueKind.uint, ValueKind.sint):
            return Text(_hex(mem.read_idx_uint_cached(idx), mem.value_type.width))
        return Text(mem.read_idx_rich_str_cached(idx))

    def _reg_rows(self, reg: Reg) -> list[tuple[tuple, RowObj, int | None]]:
        """Table rows for a register: the register's own row, plus one
        row per vector index while ``_expand_vec`` is on (like the
        ExternalMemVec view), plus the flag sub-rows of a RegFlags.

        Each row is (cells, obj, vector index or None).
        """
        rows: list[tuple[tuple, RowObj, int | None]] = [
            (
                (
                    Text(hex(reg.addr), style="cyan"),
                    Text(reg.value_type_str(), style="blue"),
                    Text(str(reg.acc), style="blue"),
                    Text(reg.name, style="cyan"),
                    self._reg_value_text(reg),
                    Text(reg.desc, style="blue"),
                ),
                reg,
                None,
            )
        ]
        if (
            self._expand_vec
            and isinstance(reg, RegVec)
            and reg.value_type.kind
            in (ValueKind.uint, ValueKind.sint, ValueKind.bits)
        ):
            # one row per vector index (like the ExternalMemVec view)
            for idx in range(reg.value_type.vec_len):
                rows.append(
                    (
                        (
                            Text(
                                hex(reg.addr + idx * reg.elem_offset),
                                style="cyan",
                            ),
                            Text("", style="blue"),
                            Text("", style="blue"),
                            Text(f"{reg.name}[{idx}]", style="cyan"),
                            self._reg_lane_value_text(reg, idx),
                            Text("", style="blue"),
                        ),
                        reg,
                        idx,
                    )
                )
        if isinstance(reg, RegFlags):
            for f in reg.flags:
                rows.append(
                    (
                        (
                            Text("-", style="dim"),
                            Text("b", style="blue"),
                            Text(str(f.bit), style="blue"),
                            Text(f.name, style="cyan"),
                            Text.from_markup(f._value_rich_str()),
                            Text(f.desc, style="blue"),
                        ),
                        f,
                        None,
                    )
                )
        return rows

    def _mem_row(self, mem: ExternalMem) -> tuple[tuple, ExternalMem, None]:
        return (
            (
                Text(hex(mem.base_addr), style="cyan"),
                Text(mem.value_type_str(), style="blue"),
                Text(str(mem.acc), style="blue"),
                Text(mem.name, style="cyan"),
                Text(f"(Mem size:{mem.size} B)", style="dim"),
                Text(mem.desc, style="blue"),
            ),
            mem,
            None,
        )

    def _show_module(self, module: Module) -> None:
        self._row_module = module
        self._row_mem = None
        self._row_keys = []
        self._row_objs = {}
        self._row_value_str = {}
        self._row_mem_idx = {}
        self._row_reg_idx = {}
        self._mem_view_header = None
        self._edit_lane = None
        self.table.clear(columns=False)

        rows: list[tuple[tuple, RowObj, int | None]] = []
        for reg in module.arr_reg_k:
            rows.extend(self._reg_rows(reg))
        for reg in module.arr_reg_var:
            rows.extend(self._reg_rows(reg))
        for mem in module.arr_external_mem:
            rows.append(self._mem_row(mem))

        for ii, (cells, obj, idx) in enumerate(rows):
            key = f"r{ii}"
            # remember the shown value so refreshes can skip update_cell()
            # for unchanged values (keeps the table render cache warm)
            self._row_value_str[key] = cells[4].plain
            # height=None: auto-height row, so a long value wraps over
            # multiple lines instead of being clipped (value column is
            # left-aligned: a right-aligned value looks odd when it
            # wraps over two lines)
            self.table.add_row(*cells, key=key, height=None)
            self._row_keys.append(key)
            self._row_objs[key] = obj
            if idx is not None:
                # a lane row of an expanded vector register
                self._row_reg_idx[key] = idx
        if rows:
            self.table.move_cursor(row=0, column=0)
        self.table.border_title = (
            module.info_line_str() + self._view_options_suffix()
        )

    def _show_mem(self, mem: ExternalMem) -> None:
        self._row_module = None
        self._row_mem = mem
        self._row_keys = []
        self._row_objs = {}
        self._row_value_str = {}
        self._row_mem_idx = {}
        self._row_reg_idx = {}
        self._mem_view_header = None
        self._edit_lane = None
        self.table.clear(columns=False)
        if isinstance(mem, ExternalMemVec):
            self._show_mem_vec(mem)
            return
        cells, obj, _ = self._mem_row(mem)
        self._row_value_str = {"r0": cells[4].plain}
        self.table.add_row(*cells, key="r0", height=None)
        self._row_keys.append("r0")
        self._row_objs["r0"] = obj
        self.table.move_cursor(row=0, column=0)
        self.table.border_title = (
            f"{hex(mem.base_addr)} {mem.name} ({mem.acc}, {mem.size} B)"
            + self._view_options_suffix()
        )

    def _show_mem_vec(self, mem: ExternalMemVec) -> None:
        """ExternalMemVec view: a header row plus one row per vector
        index.  The border title contains the mem's addr, type, acc,
        name and description; the lane value cells are read with
        ``read_idx_rich_str_cached()`` and written with
        ``write_idx_uint`` / ``write_idx_sint`` (see the docstring)."""
        self._mem_view_header = "r0"
        cells, obj, _ = self._mem_row(mem)
        self.table.add_row(*cells, key="r0", height=None)
        self._row_keys.append("r0")
        self._row_objs["r0"] = obj
        self._row_value_str["r0"] = cells[4].plain
        for idx in range(mem.vec_len()):
            key = self._mem_lane_key(idx)
            lane_cells = (
                Text(hex(mem.base_addr + idx * mem.elem_size), style="cyan"),
                Text("", style="blue"),
                Text("", style="blue"),
                Text(f"{mem.name}[{idx}]", style="cyan"),
                self._mem_lane_value_text(mem, idx),
                Text("", style="blue"),
            )
            self.table.add_row(*lane_cells, key=key, height=None)
            self._row_keys.append(key)
            self._row_objs[key] = mem
            self._row_mem_idx[key] = idx
            self._row_value_str[key] = lane_cells[4].plain
        self.table.move_cursor(row=0, column=0)
        self.table.border_title = (
            f"{hex(mem.base_addr)} {mem.value_type_str()} {mem.acc} "
            f"{mem.name} — {mem.desc}"
            + self._view_options_suffix()
        )
        # the lane cells start from the (possibly stale / empty) cache:
        # read the whole mem from the device and refresh them
        self._run_regio(
            self._read_mem_vec_async(mem), name=f"read {mem.name}"
        )

    async def _read_mem_vec_async(self, mem: ExternalMemVec) -> None:
        """Read the whole vec mem from the device, then refresh the lane
        cells (if the view is still shown)."""
        try:
            await self._regio(mem.read(0, mem.size))
        except Exception as err:  # noqa: BLE001
            logging.warning("read of %s failed: %s", mem.name, err)
            return
        for key, idx in self._row_mem_idx.items():
            if self._row_objs.get(key) is mem:
                self._update_row_value(key, self._mem_lane_value_text(mem, idx))

    @staticmethod
    def _mem_lane_key(idx: int) -> str:
        """Table row key of lane ``idx`` in an ExternalMemVec view."""
        return f"r{idx + 1}"

    # ------------------------------------------------------------------
    # asserts: check, append log, periodic refresh, clear triggered
    # ------------------------------------------------------------------

    async def _check_asserts(self) -> None:
        """'a' key / on start: build the tree and re-check all asserts."""
        if self._asserts_checking:
            return
        self._asserts_checking = True
        log_f: list[Union[RFlag, Reg]] = []
        try:
            try:
                await self.top_module.make_tree()
            except Exception as err:  # noqa: BLE001
                logging.warning(
                    "make_tree failed: %s — checking loaded modules only", err
                )
            if self._kids_loaded(self.top_module):
                worst = self.top_module.check_assert_tree_cached(
                    self.asserts_level, log_f
                )
            else:
                worst = self._check_asserts_partial(self.top_module, log_f)
            self.last_asserts = list(log_f)
            self.last_worst_ass = worst
            self.asserts_checked = True
            self._append_assert_log(worst, log_f)
            self._refresh_shown_values()
            root_node = self._build_tree()
            self._force_lines()
            # re-select the module that was on show (tree was rebuilt)
            if self._row_module is not None:
                node = self._node_for(self._row_module)
                if node is not None:
                    self.tree_view.select_node(node)
            elif root_node is not None:
                self.tree_view.select_node(root_node)
        except Exception as err:  # noqa: BLE001
            logging.warning("check asserts failed: %s", err)
        finally:
            self._asserts_checking = False

    async def _recheck_asserts(self) -> None:
        """Re-check asserts from cached values (no make_tree, no rebuild)."""
        if self._asserts_checking:
            return
        self._asserts_checking = True
        log_f: list[Union[RFlag, Reg]] = []
        try:
            if self._kids_loaded(self.top_module):
                worst = self.top_module.check_assert_tree_cached(
                    self.asserts_level, log_f
                )
            else:
                worst = self._check_asserts_partial(self.top_module, log_f)
            self.last_asserts = list(log_f)
            self.last_worst_ass = worst
            self.asserts_checked = True
            self._append_assert_log(worst, log_f)
            self._refresh_shown_values()
        except Exception as err:  # noqa: BLE001
            logging.warning("re-check asserts failed: %s", err)
        finally:
            self._asserts_checking = False

    @staticmethod
    def _kids_loaded(module: Module) -> bool:
        return all(kid is not None for kid in module.kids_cached())

    def _check_asserts_partial(self, module: Module, log_f: list) -> Ass:
        """Like check_assert_tree_cached, but tolerates None kids."""
        worst = module.check_assert_cached(self.asserts_level, log_f)
        for kid in module.kids_cached():
            if kid is None:
                continue
            kid_worst = self._check_asserts_partial(kid, log_f)
            if kid_worst > worst:
                worst = kid_worst
        return worst

    # ------------------------------------------------------------------
    # assert log (appended blocks: time stamp + table of triggered asserts)
    # ------------------------------------------------------------------

    def _append_assert_log(self, worst: Ass, log_f: list) -> None:
        """Append a time-stamped block of the triggered asserts to the log.

        The log is append-only: one block per assert check that found
        triggered asserts — the time stamp first, then one row per
        triggered assert (register or flag) in the same column layout
        as ``print_table_reg_list``.  So the log grows after every
        refresh that contains triggered asserts; checks without
        triggered asserts append nothing.  The assert level names are
        shown in their ``Ass`` colors (the header's log level and
        worst level, and the evaluated level of each value) — the
        same colors as the register map view.
        """
        if not log_f:
            return
        level = self.asserts_level
        header = (
            f"{_timestamp()}  asserts level >= {level.name}  —  "
            f"{len(log_f)} triggered, worst: {worst.name}"
        )
        # same header with the assert level names in their Ass colors
        # (like the register map view)
        rich_header = Text()
        rich_header.append(f"{_timestamp()}  asserts level >= ")
        rich_header.append(level.name, style=level.color)
        rich_header.append(f"  —  {len(log_f)} triggered, worst: ")
        rich_header.append(worst.name, style=worst.color)
        lines = [header]
        for item in log_f:
            if isinstance(item, RFlag):
                reg = item.reg_flags
                lines.append(
                    f"{hex(reg.addr)}  b{item.bit}  {str(reg.acc)}  "
                    f"{reg.name}.{item.name}  {_assert_value_str(item)}  "
                    f"{item.desc}"
                )
            else:
                lines.append(
                    f"{hex(item.addr)}  {item.value_type_str()}  "
                    f"{str(item.acc)}  {item.name}  "
                    f"{_assert_value_str(item)}  {item.desc}"
                )
        self._log_lines.extend(lines)

        self.log_view.write(rich_header)
        table = Table(expand=True, pad_edge=False, box=None)
        table.add_column("Addr", justify="right", style="cyan", no_wrap=True)
        table.add_column("T", justify="right", style="blue", no_wrap=True)
        table.add_column("Acc", style="blue", no_wrap=True)
        table.add_column("Name", style="cyan")
        table.add_column("Value", justify="right", style=Ass.none.color)
        table.add_column("Description", style="blue", ratio=1)
        for item in log_f:
            if isinstance(item, RFlag):
                reg = item.reg_flags
                table.add_row(
                    hex(reg.addr),
                    f"b{item.bit}",
                    str(reg.acc),
                    f"{reg.name}.{item.name}",
                    # same colored markup as the register map view
                    Text.from_markup(item._value_rich_str()),
                    item.desc,
                )
            else:
                table.add_row(
                    hex(item.addr),
                    item.value_type_str(),
                    str(item.acc),
                    item.name,
                    # same colored markup as the register map view
                    Text.from_markup(item.read_rich_str_cached()),
                    item.desc,
                )
        self.log_view.write(table)

    def _update_log_title(self) -> None:
        """Border title of the log pane: current assert option values."""
        refresh = (
            f"refresh: {self.refresh_period:g} s"
            if self.refresh_period
            else "refresh: off"
        )
        self.log_view.border_title = (
            f"asserts (level >= {self.asserts_level.name})  ·  {refresh}"
        )

    def _update_row_value(self, key: str, value: Text) -> None:
        """Update a register map value cell, unless the value is unchanged.

        Skipping no-op updates keeps the DataTable render cache warm: every
        update_cell() call bumps the table's _update_count, which
        invalidates its whole cell/row/line render cache, so per-tick no-op
        updates would re-render the table and grow its caches (memory churn).
        """
        old = self._row_value_str.get(key)
        plain = value.plain
        if old == plain:
            return
        self._row_value_str[key] = plain
        self.table.update_cell(key, COL_VALUE, value, update_width=True)
        # auto-height rows are only measured when they are added: if the
        # new value needs a different number of lines, re-measure the row
        row = self.table.rows.get(key)
        if (
            row is not None
            and row.auto_height
            and old is not None
            and len(old) != len(plain)
        ):
            row.height = 0
            self.table._update_dimensions([key])  # noqa: SLF001
            self.table.refresh(layout=True)

    def _update_reg_rows(self, reg: Reg) -> None:
        """Update all the value cells of a register in the shown table:
        its own row and, when expanded (``_expand_vec``), its lane
        rows."""
        for key, obj in self._row_objs.items():
            if obj is reg and key in self._row_reg_idx:
                self._update_row_value(
                    key, self._reg_lane_value_text(reg, self._row_reg_idx[key])
                )
            elif obj is reg:
                self._update_row_value(key, self._reg_value_text(reg))

    def _refresh_shown_values(self) -> None:
        """Update the value cells of the currently shown table (cached)."""
        for key, obj in self._row_objs.items():
            try:
                if isinstance(obj, Reg):
                    # a lane row of an expanded vector register, else the
                    # register's own row (header row when expanded)
                    idx = self._row_reg_idx.get(key)
                    value = (
                        self._reg_lane_value_text(obj, idx)
                        if idx is not None
                        else self._reg_value_text(obj)
                    )
                elif isinstance(obj, RFlag):
                    value = Text.from_markup(obj._value_rich_str())
                elif isinstance(obj, ExternalMemVec):
                    idx = self._row_mem_idx.get(key)
                    if idx is None:
                        # header row (keeps its meta cell) or summary
                        # row in a module map (shows the first bytes)
                        if self._mem_view_header == key:
                            continue
                        data = obj.read_cached(0, min(8, obj.size))
                        value = Text(f"(Mem {data.hex(' ')})", style="dim")
                    else:
                        value = self._mem_lane_value_text(obj, idx)
                else:
                    data = obj.read_cached(0, min(8, obj.size))
                    value = Text(f"(Mem {data.hex(' ')})", style="dim")
            except Exception:  # noqa: BLE001
                continue
            self._update_row_value(key, value)

    # ------------------------------------------------------------------
    # assert options: level (l), refresh (r), clear triggered (x)
    # ------------------------------------------------------------------

    def action_cycle_asserts_level(self) -> None:
        """'l' key: cycle the assert level and re-check the asserts."""
        idx = asserts_levels.index(self.asserts_level)
        self.asserts_level = asserts_levels[(idx + 1) % len(asserts_levels)]
        self._update_log_title()
        self.run_worker(
            self._recheck_asserts(), name="recheck_asserts", exclusive=False
        )

    def action_cycle_refresh(self) -> None:
        """'r' key: cycle the refresh period (off -> 1 -> 5 -> 30 s)."""
        idx = refresh_intervals.index(self.refresh_period)
        self.refresh_period = refresh_intervals[(idx + 1) % len(refresh_intervals)]
        self._set_refresh_timer()
        self._update_log_title()

    def action_toggle_value_bits(self) -> None:
        """'v' key: toggle the display of ``uint`` / ``sint`` values
        between int (decimal) and bits (hex, like the ``bits`` kind);
        the input prefill follows the display."""
        self._value_bits = not self._value_bits
        self._reshow()

    def action_toggle_expand_vec(self) -> None:
        """'e' key: toggle expanding vector registers into one row per
        vector index (like the ExternalMemVec view)."""
        self._expand_vec = not self._expand_vec
        self._reshow()

    def _reshow(self) -> None:
        """Rebuild the shown table with the current display options,
        keeping the cursor on the same row (when it still exists)."""
        cur_key = None
        if 0 <= self.table.cursor_row < len(self._row_keys):
            cur_key = self._row_keys[self.table.cursor_row]
        if self._row_module is not None:
            self._show_module(self._row_module)
        elif self._row_mem is not None:
            self._show_mem(self._row_mem)
        if cur_key is not None and cur_key in self._row_objs:
            self.table.move_cursor(row=self._row_keys.index(cur_key), column=0)

    def _set_refresh_timer(self) -> None:
        if self._refresh_timer is not None:
            self._refresh_timer.stop()
            self._refresh_timer = None
        if self.refresh_period:
            self._refresh_timer = self.set_interval(
                self.refresh_period, self._on_refresh_tick, name="refresh"
            )

    def _on_refresh_tick(self) -> None:
        if self._asserts_checking:
            return  # previous check / refresh still in flight: skip tick
        self.run_worker(self._refresh_worker(), name="refresh", exclusive=False)

    async def _refresh_worker(self) -> None:
        """Periodic tick: read all registers from the device, re-check
        the asserts (appending a time-stamped block to the log if any
        are triggered, so the log grows), update the register map, and
        clear the ``rc`` registers so the next tick only logs new
        events."""
        self._refresh_idle.clear()
        try:
            try:
                await self.top_module.read_all_tree(
                    read_external_mem_cache=False
                )
            except Exception as err:  # noqa: BLE001
                logging.warning("read_all_tree failed: %s", err, exc_info=True)
                return
            await self._recheck_asserts()
            self._refresh_shown_values()
            try:
                # clear the rc registers shown in the register map (the
                # selected module only), and the triggered asserts of
                # the whole tree (the log checks recursively)
                if self._row_module is not None:
                    await self._row_module.clear_reg_rc()
                await self.top_module.clear_assert_tree()
            except Exception as err:  # noqa: BLE001
                logging.warning("clear triggered failed: %s", err, exc_info=True)
        finally:
            # register writes held by _wait_refresh_idle() may now go out
            self._refresh_idle.set()

    def action_clear_triggered(self) -> None:
        """'x' key: write zero to every triggered rc register."""
        self.run_worker(
            self._clear_triggered_worker(), name="clear_triggered", exclusive=False
        )

    async def _clear_triggered_worker(self) -> None:
        try:
            if self._row_module is not None:
                await self._row_module.clear_reg_rc()
            await self.top_module.clear_assert_tree()
        except Exception as err:  # noqa: BLE001
            logging.warning("clear triggered asserts failed: %s", err)
            return
        await self._recheck_asserts()

    # ------------------------------------------------------------------
    # device I/O: skmap async (non-cached) regio reads / writes
    # ------------------------------------------------------------------
    # never *_cached here: the async regio read/write talks to the real
    # device (live TCP server or cache file) and refreshes the skmap
    # cache, so the table then shows the true device state

    async def _regio(self, coro):
        """Run a regio device I/O coroutine, serialized on a lock."""
        async with self._regio_lock:
            return await coro

    def _run_regio(self, coro, name: str) -> None:
        """Run device I/O in a worker on the app's event loop.

        Coroutines run with ``thread=False`` (default): the I/O happens
        on the *same* event loop as the (asyncio-based) regio
        connection, which asyncio sockets require.
        """
        self.run_worker(coro, name=name, group="regio-io")

    @staticmethod
    def _async_read_coro(reg: Reg):
        """Non-cached async read coroutine for ``reg`` (kind/vec aware)."""
        vt = reg.value_type
        if vt.is_vec:
            if vt.kind == ValueKind.sint:
                return reg.read_list_sint()
            if vt.kind == ValueKind.char:
                return reg.read_str()
            return reg.read_list_uint()
        if vt.kind == ValueKind.sint:
            return reg.read_sint()
        if vt.kind == ValueKind.char:
            return reg.read_char()
        return reg.read_uint()

    async def _read_row_async(self, key: str, obj: RowObj) -> None:
        """Read one table row's asset from the device and refresh the cell.

        The non-cached read also updates the skmap cache.
        """
        mem_idx = (
            self._row_mem_idx.get(key) if isinstance(obj, ExternalMemVec) else None
        )
        if mem_idx is not None:
            coro = obj.read_idx_bytes(mem_idx)
        elif isinstance(obj, ExternalMem):
            n = min(8, obj.size)
            coro = obj.read(0, n)
        elif isinstance(obj, RFlag):
            coro = obj.read_bool()
        else:
            coro = self._async_read_coro(obj)
        try:
            await self._regio(coro)
        except Exception as err:  # noqa: BLE001
            logging.warning(
                "read of %s failed: %s", getattr(obj, "name", "?"), err
            )
            return
        if self._row_objs.get(key) is not obj:
            return  # the row was replaced meanwhile (module switched)
        if mem_idx is not None:
            self._update_row_value(key, self._mem_lane_value_text(obj, mem_idx))
        elif isinstance(obj, ExternalMem):
            data = obj.read_cached(0, n)
            self._update_row_value(
                key, Text(f"(Mem {data.hex(' ')})", style="dim")
            )
        elif isinstance(obj, RFlag):
            self._update_row_value(
                key, Text.from_markup(obj._value_rich_str())
            )
        else:
            self._update_reg_rows(obj)

    # ------------------------------------------------------------------
    # mouse-resizable panes
    # ------------------------------------------------------------------

    def _hit_divider(self, sx: int, sy: int) -> str | None:
        """Return which pane divider the screen position is on.

        ``"v"`` = vertical divider between tree and table, ``"h"`` =
        horizontal divider between workspace and log, ``None`` otherwise.
        """
        ws = self.workspace.region
        tree = self.tree_view.region
        inp = self.value_input.region
        edge = self._RESIZE_EDGE
        # horizontal divider (workspace | input+log) first: full-width band
        # at the bottom edge of the workspace (the input bar sits below it,
        # so it cannot be the anchor anymore)
        if ws.x <= sx < ws.right and ws.bottom - edge <= sy <= ws.bottom + 1:
            return "h"
        # vertical divider (tree | registers): narrow band, workspace rows only
        if (
            ws.y <= sy < inp.y
            and tree.right - edge <= sx <= tree.right + edge
        ):
            return "v"
        return None

    def on_mouse_down(self, event: events.MouseDown) -> None:
        hit = self._hit_divider(event.screen_x, event.screen_y)
        if hit is not None:
            self._drag = hit
            event.stop()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self._drag is None:
            return
        event.stop()
        if self._drag == "v":
            ws = self.workspace.region
            if ws.width > 0:
                pct = (event.screen_x - ws.x) / ws.width * 100
                self.tree_view.styles.width = f"{min(max(pct, 10), 90):.1f}%"
        else:
            avail = (
                self.screen.size.height
                - self.header.region.height
                - self.footer.region.height
            )
            top = self.header.region.height
            if avail > 0:
                pct = (event.screen_y - top) / avail * 100
                self.workspace.styles.height = f"{min(max(pct, 20), 85):.1f}%"

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if self._drag is not None:
            self._drag = None
            event.stop()

    # ------------------------------------------------------------------
    # actions / key bindings
    # ------------------------------------------------------------------

    def action_check_asserts(self) -> None:
        self.run_worker(self._check_asserts(), name="check_asserts", exclusive=False)

    def action_clear_log(self) -> None:
        self._log_lines.clear()
        self.log_view.clear()

    # ------------------------------------------------------------------
    # value editing (enter on a table row -> input line -> write/clear)
    # ------------------------------------------------------------------

    async def action_edit_selected_value(self) -> None:
        await self._edit_cursor_row()

    async def on_reg_map_table_edit_requested(
        self, event: RegMapTable.EditRequested
    ) -> None:
        await self._edit_cursor_row()

    async def _edit_cursor_row(self) -> None:
        """Enter on a table row: edit (rw/wt) or clear (rc) its value."""
        if self.table.row_count == 0:
            return
        row = self.table.cursor_row
        if row < 0 or row >= len(self._row_keys):
            return
        key = self._row_keys[row]
        obj = self._row_objs[key]
        if isinstance(obj, ExternalMemVec):
            # an ExternalMemVec view row: one lane, or the header row
            await self._edit_mem_row(key, obj, self._row_mem_idx.get(key))
            return
        if not isinstance(obj, Reg):
            return  # flag / plain external mem rows are not editable
        lane_idx = self._row_reg_idx.get(key)
        if lane_idx is not None:
            # a lane row of an expanded vector register
            if obj.acc in (Acc.rw, Acc.wt):
                self._edit_lane = (key, lane_idx)
                self.value_input.placeholder = (
                    f"{obj.name}[{lane_idx}]: "
                    f"{obj.value_type.width}-bit value (0x-hex or decimal)"
                )
                # prefill with the current lane value, editable in place
                self.value_input.value = self._value_str(obj, lane_idx)
                self.value_input.focus()
            elif obj.acc == Acc.rc:
                self._write_vec_row(key, obj, [(lane_idx, 0)], "CLEAR")
            # k (hardwired), na (no access), ro: nothing to edit
            return
        if obj.acc in (Acc.rw, Acc.wt):
            await self._open_value_input(row, obj)
        elif obj.acc == Acc.rc:
            self._clear_row(row, obj)
        # k (hardwired), na (no access), ro: nothing to edit

    async def _edit_mem_row(
        self, key: str, mem: ExternalMemVec, idx: int | None
    ) -> None:
        """Enter on an ExternalMemVec view row: ``idx`` None = the
        header row (edit / clear every lane), else one lane row."""
        if mem.acc in (Acc.rw, Acc.wt):
            if idx is None:
                self._edit_lane = (key, None)
                await self._open_vector_inputs(mem)
            else:
                self._edit_lane = (key, idx)
                self.value_input.placeholder = (
                    f"{mem.name}[{idx}]: "
                    f"{mem.value_type.width}-bit value (0x-hex or decimal)"
                )
                # prefill with the current lane value, editable in place
                self.value_input.value = self._value_str(mem, idx)
                self.value_input.focus()
        elif mem.acc == Acc.rc:
            self._clear_mem_lanes(key, mem, idx)
        # k (hardwired) / na (no access) / ro: nothing to edit

    def _value_str(
        self, reg: Union[Reg, ExternalMemVec], idx: int | None = None
    ) -> str:
        """Current value of ``reg`` / mem (or lane ``idx``) for the
        input line.

        Hex for ``bits`` kinds (and for ``uint`` / ``sint`` while the
        ``v`` bits display is on), decimal otherwise — the same number
        bases the table shows.  The input accepts both hex and decimal.
        """
        kind = reg.value_type.kind
        if kind is ValueKind.bits or (
            kind in (ValueKind.uint, ValueKind.sint) and self._value_bits
        ):
            raw = (
                reg.read_idx_uint_cached(idx)
                if idx is not None
                else reg.read_uint_cached()
            )
            return _hex(raw, reg.value_type.width)
        value = (
            reg.read_idx_value_cached(idx) if idx is not None
            else reg.read_value_cached()
        )
        if isinstance(value, str):
            return value
        return str(value)

    async def _open_value_input(self, row: int, reg: Reg) -> None:
        vt = reg.value_type
        if vt.vec_len:
            await self._open_vector_inputs(reg)
            return
        self.value_input.placeholder = (
            f"{reg.name}: {vt.width}-bit value (0x-hex or decimal)"
        )
        # prefill with the current value so it can be edited in place
        self.value_input.value = self._value_str(reg)
        self.value_input.focus()

    async def _open_vector_inputs(self, reg: Union[Reg, ExternalMemVec]) -> None:
        """Open one input column per vector index, each prefilled with
        the current lane value (``read_idx_value_cached``)."""
        vt = reg.value_type
        container = self.value_inputs
        # hide the single input for the duration of the vector edit
        await self.value_input.remove()
        for idx in range(vt.vec_len):
            lane = ValueInput(
                id=f"value-input-{idx}",
                classes="lane",
                placeholder=f"{reg.name}[{idx}]",
                value=self._value_str(reg, idx),
            )
            await container.mount(lane)
        container.query_one("ValueInput.lane").focus()

    async def _close_vector_inputs(self) -> None:
        """Remove the lane inputs and restore the single input."""
        container = self.value_inputs
        for lane in container.query("ValueInput.lane"):
            await lane.remove()
        if self.value_input.parent is None:
            await container.mount(self.value_input)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if self.table.row_count == 0:
            return
        row = self.table.cursor_row
        if row < 0 or row >= len(self._row_keys):
            return
        lanes = self.value_inputs.query("ValueInput.lane")
        edit_lane = self._edit_lane
        self._edit_lane = None
        if edit_lane is not None:
            # a lane edit: one lane of an ExternalMemVec view, one lane
            # of an expanded vector register, or (index None) the header
            # row of a vec mem view (every lane)
            key, idx = edit_lane
            obj = self._row_objs.get(key)
            if not isinstance(obj, (Reg, ExternalMemVec)):
                return
            if idx is None:
                if not lanes:
                    return
                values = [self._parse_lane(obj, str(l.value)) for l in lanes]
                if any(v is None for v in values):
                    # keep focus + values so the user can fix them
                    self._edit_lane = edit_lane
                    return
                await self._close_vector_inputs()
                self.table.focus()
                pairs = [
                    (self._mem_lane_key(i), i, v) for i, v in enumerate(values)
                ]
                self._run_regio(
                    self._write_mem_lanes_async(obj, pairs),
                    name=f"write {obj.name}",
                )
            else:
                value = self._parse_lane(obj, event.input.value)
                if value is None:
                    # keep focus + value so the user can fix the input
                    self._edit_lane = edit_lane
                    return
                self.table.focus()
                event.input.value = ""
                if isinstance(obj, ExternalMemVec):
                    self._run_regio(
                        self._write_mem_lanes_async(obj, [(key, idx, value)]),
                        name=f"write {obj.name}[{idx}]",
                    )
                else:
                    self._write_vec_row(key, obj, [(idx, value)])
            return
        obj = self._row_objs[self._row_keys[row]]
        if not isinstance(obj, Reg) or obj.acc not in (Acc.rw, Acc.wt):
            return
        if lanes:
            await self._submit_vector_edit(obj, lanes)
        else:
            self._submit_scalar_edit(row, obj, event.input)

    def _submit_scalar_edit(self, row: int, reg: Reg, inp: Input) -> None:
        value = self._parse_value(reg, inp.value)
        if value is None:
            # keep focus + value so the user can fix the input
            return
        self.table.focus()
        inp.value = ""
        self._write_row(row, reg, value, "WRITE")

    async def _submit_vector_edit(self, reg: Reg, lanes) -> None:
        values = [self._parse_lane(reg, str(l.value)) for l in lanes]
        if any(v is None for v in values):
            # keep focus + values so the user can fix them
            return
        row = self.table.cursor_row
        await self._close_vector_inputs()
        self.table.focus()
        self._write_vec_row(self._row_keys[row], reg, list(enumerate(values)))

    async def on_value_input_canceled(self, event: ValueInput.Canceled) -> None:
        if self.value_inputs.query("ValueInput.lane"):
            await self._close_vector_inputs()
        self._edit_lane = None
        self.value_input.value = ""
        self.table.focus()

    @staticmethod
    def _parse_lane(asset, text: str) -> int | None:
        """Parse a value for ``asset`` (Reg or ExternalMemVec): decimal
        or 0x-prefixed hex.

        Returns ``None`` if the text does not fit the value kind / width
        (sint values may be negative) or, for a Reg, outside its
        configured min / max limits — the same condition
        ``Reg.check_value_limit()`` would raise on, so the write is
        aborted before it reaches the device.
        """
        vt = asset.value_type
        try:
            v = int(text.strip(), 0)
        except ValueError:
            return None
        if vt.kind is ValueKind.sint:
            if not -(1 << (vt.width - 1)) <= v < (1 << (vt.width - 1)):
                return None
        elif not 0 <= v < (1 << vt.width):
            return None
        if (
            isinstance(asset, Reg)
            and asset.ass_check_value_limit(v) >= Ass.error
        ):
            return None
        return v

    @staticmethod
    def _random_limit_value(reg: Reg) -> int | None:
        """A random trigger value for ``reg``: within the value kind /
        width range, clamped to the reg's configured min / max limits.

        Returns ``None`` if the limits leave no valid value.
        """
        vt = reg.value_type
        if vt.kind is ValueKind.sint:
            lo, hi = -(1 << (vt.width - 1)), (1 << (vt.width - 1)) - 1
        else:
            lo, hi = 0, (1 << vt.width) - 1
        if reg.min is not None:
            lo = max(lo, reg.min)
        if reg.max is not None:
            hi = min(hi, reg.max)
        if lo > hi:
            return None
        return random.randint(lo, hi)

    @staticmethod
    def _parse_value(reg: Reg, text: str) -> int | None:
        """Parse the input text for a scalar ``reg``.

        Accepts decimal or 0x-prefixed hex.  Returns ``None`` if the
        text does not fit the register (sint regs may be negative,
        min / max limits included — see ``_parse_lane``).
        """
        return SkmapUiApp._parse_lane(reg, text)

    def _write_vec_row(
        self,
        key: str,
        reg: Reg,
        pairs: list[tuple[int, int]],
        op: str = "WRITE",
    ) -> None:
        """Write (idx, value) lanes of a vector register to the device,
        async (see ``_write_vec_row_async``)."""
        self._run_regio(
            self._write_vec_row_async(key, reg, pairs, op),
            name=f"{op.lower()} {reg.name}",
        )

    def _clear_row(self, row: int, reg: Reg) -> None:
        value = (
            [0] * reg.value_type.vec_len if reg.value_type.vec_len else 0
        )
        self._write_row(row, reg, value, "CLEAR")

    def _write_row(self, row: int, reg: Reg, value, op: str) -> None:
        """Write ``value`` (or zero for ``CLEAR``) to the device, async.

        Uses skmap's non-cached ``write_*`` so the write reaches the
        regio (firmware / cache file); the row is then refreshed with a
        non-cached read so the table shows the real device state.
        """
        key = self._row_keys[row]
        self._run_regio(
            self._write_row_async(key, reg, value, op), name=f"write {reg.name}"
        )

    async def _wait_refresh_idle(self) -> None:
        """Hold until no periodic refresh is in flight (see
        ``_refresh_idle``): a register write must not land in the
        middle of a refresh, or the refresh would read (or clear) the
        value while it is being written."""
        while not self._refresh_idle.is_set():
            await self._refresh_idle.wait()

    async def _write_row_async(self, key: str, reg: Reg, value, op: str) -> None:
        # hold the write until an in-flight refresh has finished
        await self._wait_refresh_idle()
        # abort values outside the reg's configured min / max limits
        # before the write (Reg.check_value_limit() would raise)
        values = value if isinstance(value, list) else [value]
        if any(reg.ass_check_value_limit(v) >= Ass.error for v in values):
            logging.warning(
                "%s to %s @ %s aborted: value outside [%s, %s]",
                op, reg.name, hex(reg.addr), reg.min, reg.max,
            )
            return
        try:
            if op == "CLEAR":
                await self._regio(reg.write_zero())
            elif isinstance(value, list):
                if reg.value_type.kind is ValueKind.sint:
                    await self._regio(reg.write_list_sint(value))
                else:
                    await self._regio(reg.write_list_uint(value))
            else:
                await self._regio(reg.write_uint(value))
        except Exception as err:  # noqa: BLE001
            logging.warning(
                "%s to %s @ %s failed: %s", op, reg.name, hex(reg.addr), err
            )
            return
        # read the value back from the device (updates the cache too)
        await self._read_row_async(key, reg)

    async def _write_vec_row_async(
        self, key: str, reg: Reg, pairs: list[tuple[int, int]], op: str = "WRITE"
    ) -> None:
        """Write the given (idx, value) lanes one at a time:
        ``write_idx_uint`` / ``write_idx_sint`` (chosen by the value
        kind), then read the register back (updates the register's own
        row and every lane row)."""
        # hold the write until an in-flight refresh has finished
        await self._wait_refresh_idle()
        # abort values outside the reg's configured min / max limits
        # before the write (see _write_row_async)
        if any(reg.ass_check_value_limit(v) >= Ass.error for _idx, v in pairs):
            logging.warning(
                "%s to %s @ %s aborted: value outside [%s, %s]",
                op, reg.name, hex(reg.addr), reg.min, reg.max,
            )
            return
        writer = (
            reg.write_idx_sint
            if reg.value_type.kind is ValueKind.sint
            else reg.write_idx_uint
        )
        try:
            async with self._regio_lock:
                for idx, value in pairs:
                    await writer(idx, value)
        except Exception as err:  # noqa: BLE001
            logging.warning(
                "%s to %s @ %s failed: %s", op, reg.name, hex(reg.addr), err
            )
            return
        # read the value back from the device (updates the cache too)
        await self._read_row_async(key, reg)

    async def _write_mem_lanes_async(
        self, mem: ExternalMemVec, pairs: list[tuple[str, int, int]]
    ) -> None:
        """Write (row key, lane, value) pairs to an ExternalMemVec with
        ``write_idx_uint`` / ``write_idx_sint`` (chosen by the value
        kind), then read the lanes back from the device."""
        # hold the write until an in-flight refresh has finished
        await self._wait_refresh_idle()
        writer = (
            mem.write_idx_sint
            if mem.value_type.kind is ValueKind.sint
            else mem.write_idx_uint
        )
        try:
            async with self._regio_lock:
                for _key, idx, value in pairs:
                    await writer(idx, value)
        except Exception as err:  # noqa: BLE001
            logging.warning(
                "write to %s @ %s idx %s failed: %s",
                mem.name,
                hex(mem.base_addr),
                [i for _k, i, _v in pairs],
                err,
            )
            return
        for key, idx, _value in pairs:
            if self._row_objs.get(key) is not mem:
                continue  # the view was switched meanwhile
            try:
                await self._regio(mem.read_idx_bytes(idx))
            except Exception as err:  # noqa: BLE001
                logging.warning("read of %s[%d] failed: %s", mem.name, idx, err)
                continue
            if self._row_objs.get(key) is not mem:
                continue
            self._update_row_value(key, self._mem_lane_value_text(mem, idx))

    def _clear_mem_lanes(
        self, key: str, mem: ExternalMemVec, idx: int | None
    ) -> None:
        """Enter on an rc ExternalMemVec view row: write zero to the
        lane (or to every lane on the header row)."""
        if idx is None:
            pairs = [
                (self._mem_lane_key(i), i) for i in range(mem.vec_len())
            ]
        else:
            pairs = [(key, idx)]
        self._run_regio(
            self._clear_mem_lanes_async(mem, pairs), name=f"clear {mem.name}"
        )

    async def _clear_mem_lanes_async(
        self, mem: ExternalMemVec, pairs: list[tuple[str, int]]
    ) -> None:
        """Write zero to the lanes, then read them back from the device."""
        # hold the write until an in-flight refresh has finished
        await self._wait_refresh_idle()
        writer = (
            mem.write_idx_sint
            if mem.value_type.kind is ValueKind.sint
            else mem.write_idx_uint
        )
        try:
            async with self._regio_lock:
                for _key, idx in pairs:
                    await writer(idx, 0)
        except Exception as err:  # noqa: BLE001
            logging.warning(
                "clear of %s @ %s failed: %s", mem.name, hex(mem.base_addr), err
            )
            return
        for key, idx in pairs:
            if self._row_objs.get(key) is not mem:
                continue
            try:
                await self._regio(mem.read_idx_bytes(idx))
            except Exception as err:  # noqa: BLE001
                logging.warning("read of %s[%d] failed: %s", mem.name, idx, err)
                continue
            if self._row_objs.get(key) is not mem:
                continue
            self._update_row_value(key, self._mem_lane_value_text(mem, idx))

    def action_trigger_selected(self) -> None:
        if self.table.row_count == 0 or self.table.cursor_row < 0:
            return
        row = self.table.cursor_row
        if row >= len(self._row_keys):
            return
        obj = self._row_objs[self._row_keys[row]]
        if isinstance(obj, RFlag):
            self._trigger_flag(row, obj)
        elif isinstance(obj, ExternalMem):
            self._trigger_mem(row, obj)
        else:
            lane_idx = self._row_reg_idx.get(self._row_keys[row])
            if lane_idx is not None:
                self._trigger_reg_lane(row, obj, lane_idx)
            else:
                self._trigger_reg(row, obj)

    def _trigger_reg(self, row: int, reg: Reg) -> None:
        """'t' on a register row (device I/O, see module docstring)."""
        key = self._row_keys[row]
        if reg.acc in (Acc.rw, Acc.wt):
            if isinstance(reg, RegVec):
                value = [
                    self._random_limit_value(reg)
                    for _ in range(reg.value_type.vec_len)
                ]
            else:
                value = self._random_limit_value(reg)
            values = value if isinstance(value, list) else [value]
            if any(v is None for v in values):
                logging.warning(
                    "trigger of %s @ %s skipped: no value fits its min / max limits",
                    reg.name, hex(reg.addr),
                )
                return
            self._write_row(row, reg, value, "WRITE")
        elif reg.acc in (Acc.k, Acc.na):
            return  # k (hardwired) / na (no access): nothing to do
        else:
            # ro / rc: read from the device (updates the cache too)
            self._run_regio(
                self._read_row_async(key, reg), name=f"read {reg.name}"
            )

    def _trigger_reg_lane(self, row: int, reg: Reg, idx: int) -> None:
        """'t' on a lane row of an expanded vector register: writable
        lanes are *written* (a random value within the reg's min / max
        limits, just that lane); ro / rc lanes *read* the register
        (the header row and every lane row are updated)."""
        key = self._row_keys[row]
        if reg.acc in (Acc.rw, Acc.wt):
            value = self._random_limit_value(reg)
            if value is None:
                logging.warning(
                    "trigger of %s[%d] @ %s skipped: no value fits its min / max limits",
                    reg.name, idx, hex(reg.addr),
                )
                return
            self._write_vec_row(key, reg, [(idx, value)])
        elif reg.acc in (Acc.k, Acc.na):
            return  # k (hardwired) / na (no access): nothing to do
        else:
            self._run_regio(
                self._read_row_async(key, reg), name=f"read {reg.name}"
            )

    def _trigger_flag(self, row: int, flag: RFlag) -> None:
        """'t' on a flag row (device I/O, see module docstring)."""
        key = self._row_keys[row]
        reg = flag.reg_flags
        if reg.acc in (Acc.rw, Acc.wt):
            value = random.random() < 0.5
            self._run_regio(
                self._flag_write_async(key, flag, value),
                name=f"write {reg.name}.{flag.name}",
            )
        elif reg.acc in (Acc.k, Acc.na):
            return  # k (hardwired) / na (no access): nothing to do
        else:
            self._run_regio(
                self._read_row_async(key, flag),
                name=f"read {reg.name}.{flag.name}",
            )

    async def _flag_write_async(self, key: str, flag: RFlag, value: bool) -> None:
        reg = flag.reg_flags
        # hold the write until an in-flight refresh has finished
        await self._wait_refresh_idle()
        try:
            await self._regio(flag.write_bool(value))
        except Exception as err:  # noqa: BLE001
            logging.warning(
                "write to %s.%s @ %s failed: %s",
                reg.name, flag.name, hex(reg.addr), err,
            )
            return
        # read the value back from the device (updates the cache too)
        await self._read_row_async(key, flag)

    def _trigger_mem(self, row: int, mem: ExternalMem) -> None:
        """'t' on an external mem row: read it from the device (a lane
        row of an ExternalMemVec view reads just that lane)."""
        if not isinstance(mem, ExternalMemCached):
            logging.warning(
                "%s @ %s not cached yet (run read_cache_tree first)",
                mem.name, hex(mem.base_addr),
            )
            return
        if mem.acc in (Acc.k, Acc.na):
            return  # k (hardwired) / na (no access): nothing to do
        key = self._row_keys[row]
        self._run_regio(self._read_row_async(key, mem), name=f"read {mem.name}")


def auto_int(s: str) -> int:
    """argparse type: integer from a decimal or 0x-prefixed string."""
    return int(s, 0)


def _import_module_file(path) -> None:
    """Import a generated skmap module ``.py`` file.

    Executing the module registers its ``skmap.Module`` subclasses
    (``skmap.register_Module``), so ``make_module`` can instantiate the
    head IDs found in the regio / cache file.
    """
    import importlib.util

    path = Path(path).resolve()
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import module file: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


async def _smoke(app: "SkmapUiApp") -> None:
    """Headless smoke test: start, wait for the assert check, report, exit."""
    async with app.run_test() as pilot:
        for _ in range(500):
            if app.asserts_checked:
                break
            await pilot.pause()
    if not app.asserts_checked:
        raise SystemExit("smoke FAILED: assert check did not complete")
    print(
        f"smoke OK: {app.top_module.name()} "
        f"worst={app.last_worst_ass.name} asserts={len(app.last_asserts)}"
    )
    for line in app._log_lines:
        print(f"  {line}")


def main() -> None:
    """Console-script entry point: run the TUI on a skmap module.

    By default a live regio TCP connection is used (``-i/--host`` /
    ``-p/--port``).  With ``-f/--file`` the module is built from a
    skelregi cache file (see ``regio``); with ``--demo`` the built-in
    demo module is used (no device needed).

    Module build and TUI run in a *single* asyncio loop (``run_async()``):
    the regio TCP client is asyncio-based, so the connection created
    while building the module must stay alive inside the TUI event loop.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="skmap-ui",
        description="SKMap User Interface — browse a skmap module register map",
    )
    parser.add_argument(
        "-a", "--addr",
        type=auto_int,
        default=0,
        help="Module regio address (defaults to 0)",
    )
    parser.add_argument(
        "-m", "--module-file",
        type=Path,
        default=None,
        help="Generated skmap module .py file to import first "
             "(registers the module classes; needed for -f/--file and -i/--host)",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Headless smoke test: start, wait for the assert check, "
             "print the result and exit",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run in demo mode"
    )
    parser.add_argument(
        "--asserts-level",
        default="debug",
        choices=[ass.name for ass in asserts_levels],
        help="Assert level (default: debug); asserts at or above this "
             "level are logged. Cycle at runtime with the 'l' key.",
    )
    parser.add_argument(
        "--refresh",
        type=float,
        default=0.0,
        help="Periodically read all registers (read_all_tree) and "
             "re-check the asserts every N seconds (0 = off, default: 0). "
             "Cycle at runtime with the 'r' key.",
    )

    regio.cli_utils.add_parser_args(parser)

    args = parser.parse_args()

    if args.module_file is not None:
        _import_module_file(args.module_file)

    if args.demo:
        print("mode: built-in demo module")
    elif args.file is not None:
        print(f"mode: regio cache file {args.file}")
    else:
        print(f"mode: live regio TCP server {args.host}:{args.port}")

    logging.basicConfig(level=logging.WARNING)
    asyncio.run(_main_async(args))


async def _main_async(args) -> None:
    """Build the module and run the TUI in one asyncio loop."""
    if args.demo:
        from skmap_ui.demo import make_demo_module
        top_module = make_demo_module()
    else:
        top_module = await skmap.cli_utils.make_module_from_args(args)
    app = SkmapUiApp(
        top_module,
        asserts_level=Ass[args.asserts_level],
        refresh=args.refresh or None,
    )
    if args.smoke:
        await _smoke(app)
    else:
        await app.run_async()
