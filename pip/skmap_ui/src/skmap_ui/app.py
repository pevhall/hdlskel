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
map, then clears the triggered ``rc`` registers
(``clear_reg_rc_tree()`` + ``clear_assert_tree()``) so the next
refresh only logs new events (0 = off).  The ``x`` key does the same
clear on demand and re-checks.  Register writes (``enter`` / ``t``)
are **held** while a refresh is in progress and only go to the device
once it has finished.  Device I/O errors are reported on the console
via ``logging`` so the log view only ever contains triggered asserts.

The tree starts fully expanded; ``enter``
selects the module under the cursor and shows its register map (mirrors
``print_reg_map_cached``), and the node of the module whose register map
is currently shown is highlighted in the tree.  ``left`` / ``right``
collapse / expand the cursor node.  ``enter`` on a table row edits the
value of ``rw`` / ``wt`` registers (type the new value, ``enter`` to
write, ``escape`` to cancel) and clears ``rc`` registers (writes zero);
vector registers take comma-separated lanes (or one value for all
lanes).  ``t`` triggers the selected register row: writable registers /
flags are *written*, read-only ones are *read* (skmap's "trigger" =
register write).  All register / flag / mem device accesses use
skmap's async *non-cached* regio reads/writes (never ``*_cached``), so
the value really goes to / comes from the regio (live TCP server or
cache file) and the skmap cache is refreshed; ``k`` (hardwired) and
``na`` (no access) assets are never read back.  All three panes are
resizable with the mouse: drag the divider between tree and table, or
between the table and the log.
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
from skmap.external_mem import ExternalMemCached
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
    #value-input { height: 3; border: round $warning; }
    #log { height: 1fr; min-height: 7; border: round $success; }
    """

    BINDINGS = [
        ("t", "trigger_selected", "Trigger"),
        ("a", "check_asserts", "Check asserts"),
        ("c", "clear_log", "Clear log"),
        ("l", "cycle_asserts_level", "Assert level"),
        ("r", "cycle_refresh", "Refresh"),
        ("x", "clear_triggered", "Clear triggered"),
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
        self._value_pad = 2

    # ------------------------------------------------------------------
    # layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="workspace"):
            yield ModuleTree(self.top_module.name(), id="modules")
            yield RegMapTable(id="registers")
        yield ValueInput(
            id="value-input",
            placeholder=(
                "enter: edit (rw/wt) / clear (rc) | l: assert level | "
                "r: refresh | x: clear triggered | a: check asserts"
            ),
        )
        yield RichLog(id="log", markup=True, min_width=0)
        yield Footer()

    def on_mount(self) -> None:
        self.tree_view = self.query_one("#modules", ModuleTree)
        self.table = self.query_one("#registers", RegMapTable)
        self.value_input = self.query_one("#value-input", ValueInput)
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

    def _reg_rows(self, reg: Reg) -> list[tuple[tuple, RowObj]]:
        rows: list[tuple[tuple, RowObj]] = [
            (
                (
                    Text(hex(reg.addr), style="cyan"),
                    Text(reg.value_type_str(), style="blue"),
                    Text(str(reg.acc), style="blue"),
                    Text(reg.name, style="cyan"),
                    Text.from_markup(reg.read_rich_str_cached()),
                    Text(reg.desc, style="blue"),
                ),
                reg,
            )
        ]
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
                    )
                )
        return rows

    def _mem_row(self, mem: ExternalMem) -> tuple[tuple, ExternalMem]:
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
        )

    def _show_module(self, module: Module) -> None:
        self._row_module = module
        self._row_keys = []
        self._row_objs = {}
        self._row_value_str = {}
        self.table.clear(columns=False)

        rows: list[tuple[tuple, RowObj]] = []
        for reg in module.arr_reg_k:
            rows.extend(self._reg_rows(reg))
        for reg in module.arr_reg_var:
            rows.extend(self._reg_rows(reg))
        for mem in module.arr_external_mem:
            rows.append(self._mem_row(mem))

        # right-align the value column (8.x DataTable has no per-column justify)
        pad = 2
        for cells, _ in rows:
            pad = max(pad, len(cells[4].plain))
        self._value_pad = pad

        for ii, (cells, obj) in enumerate(rows):
            key = f"r{ii}"
            # remember the shown value so refreshes can skip update_cell()
            # for unchanged values (keeps the table render cache warm)
            self._row_value_str[key] = cells[4].plain
            # rich Text.pad() has no left/right in 8.x-era rich: prefix spaces
            cells = (
                cells[:4]
                + (Text(" " * (pad - len(cells[4].plain))) + cells[4],)
                + cells[5:]
            )
            self.table.add_row(*cells, key=key)
            self._row_keys.append(key)
            self._row_objs[key] = obj
        if rows:
            self.table.move_cursor(row=0, column=0)
        self.table.border_title = module.info_line_str()

    def _show_mem(self, mem: ExternalMem) -> None:
        self._row_module = None
        self._row_keys = []
        self._row_objs = {}
        self.table.clear(columns=False)
        cells, obj = self._mem_row(mem)
        self._row_value_str = {"r0": cells[4].plain}
        self._value_pad = 2
        self.table.add_row(*cells, key="r0")
        self._row_keys.append("r0")
        self._row_objs["r0"] = obj
        self.table.move_cursor(row=0, column=0)
        self.table.border_title = (
            f"{hex(mem.base_addr)} {mem.name} ({mem.acc}, {mem.size} B)"
        )

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
        plain = value.plain
        if self._row_value_str.get(key) == plain:
            return
        self._row_value_str[key] = plain
        padded = Text(" " * max(0, self._value_pad - len(plain))) + value
        self.table.update_cell(key, COL_VALUE, padded, update_width=True)

    def _refresh_shown_values(self) -> None:
        """Update the value cells of the currently shown table (cached)."""
        for key, obj in self._row_objs.items():
            try:
                if isinstance(obj, Reg):
                    value = Text.from_markup(obj.read_rich_str_cached())
                elif isinstance(obj, RFlag):
                    value = Text.from_markup(obj._value_rich_str())
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
                await self.top_module.clear_reg_rc()
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
        if isinstance(obj, ExternalMem):
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
        if isinstance(obj, ExternalMem):
            data = obj.read_cached(0, n)
            self._update_row_value(
                key, Text(f"(Mem {data.hex(' ')})", style="dim")
            )
        elif isinstance(obj, RFlag):
            self._update_row_value(
                key, Text.from_markup(obj._value_rich_str())
            )
        else:
            self._update_row_value(
                key, Text.from_markup(obj.read_rich_str_cached())
            )

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

    def action_edit_selected_value(self) -> None:
        self._edit_cursor_row()

    def on_reg_map_table_edit_requested(
        self, event: RegMapTable.EditRequested
    ) -> None:
        self._edit_cursor_row()

    def _edit_cursor_row(self) -> None:
        """Enter on a table row: edit (rw/wt) or clear (rc) its value."""
        if self.table.row_count == 0:
            return
        row = self.table.cursor_row
        if row < 0 or row >= len(self._row_keys):
            return
        obj = self._row_objs[self._row_keys[row]]
        if not isinstance(obj, Reg):
            return  # flag / external mem rows are not editable
        if obj.acc in (Acc.rw, Acc.wt):
            self._open_value_input(row, obj)
        elif obj.acc == Acc.rc:
            self._clear_row(row, obj)
        # k (hardwired), na (no access), ro: nothing to edit

    def _open_value_input(self, row: int, reg: Reg) -> None:
        vt = reg.value_type
        hint = f"{reg.name}: {vt.width}-bit value (0x-hex or decimal)"
        if vt.vec_len:
            hint += (
                f", {vt.vec_len} lanes: comma-separate, or one for all"
            )
        self.value_input.placeholder = hint
        self.value_input.value = ""
        self.value_input.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input is not self.value_input:
            return
        if self.table.row_count == 0:
            return
        row = self.table.cursor_row
        if row < 0 or row >= len(self._row_keys):
            return
        obj = self._row_objs[self._row_keys[row]]
        if not isinstance(obj, Reg) or obj.acc not in (Acc.rw, Acc.wt):
            self.value_input.value = ""
            return
        value = self._parse_value(obj, event.value)
        if value is None:
            # keep focus + value so the user can fix the input
            return
        self.table.focus()
        self.value_input.value = ""
        self._write_row(row, obj, value, "WRITE")

    def on_value_input_canceled(self, event: ValueInput.Canceled) -> None:
        self.value_input.value = ""
        self.table.focus()

    @staticmethod
    def _parse_value(reg: Reg, text: str) -> Union[int, list, None]:
        """Parse the input text for ``reg``: int, or per-lane list (vec).

        Accepts decimal or 0x-prefixed hex.  Vector registers take
        comma-separated lanes; a single value repeats over all lanes.
        Returns ``None`` if the text does not fit the register.
        """
        vt = reg.value_type

        def one(s: str) -> int | None:
            try:
                v = int(s.strip(), 0)
            except ValueError:
                return None
            return v if 0 <= v < (1 << vt.width) else None

        if vt.vec_len:
            vals = [one(s) for s in text.split(",")]
            if any(v is None for v in vals):
                return None
            if len(vals) == 1:
                return vals * vt.vec_len
            if len(vals) != vt.vec_len:
                return None
            return vals
        return one(text)

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
        try:
            if op == "CLEAR":
                await self._regio(reg.write_zero())
            elif isinstance(value, list):
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
            self._trigger_reg(row, obj)

    def _trigger_reg(self, row: int, reg: Reg) -> None:
        """'t' on a register row (device I/O, see module docstring)."""
        key = self._row_keys[row]
        if reg.acc in (Acc.rw, Acc.wt):
            if isinstance(reg, RegVec):
                value = [
                    random.getrandbits(reg.value_type.width)
                    for _ in range(reg.value_type.vec_len)
                ]
            else:
                value = random.getrandbits(reg.value_type.width)
            self._write_row(row, reg, value, "WRITE")
        elif reg.acc in (Acc.k, Acc.na):
            return  # k (hardwired) / na (no access): nothing to do
        else:
            # ro / rc: read from the device (updates the cache too)
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
        """'t' on an external mem row: read the first bytes from device."""
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
