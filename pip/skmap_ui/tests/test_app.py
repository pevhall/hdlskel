"""Headless smoke tests for the skmap_ui TUI (Textual 8.x, no plugins).

Each test wraps an ``async`` runner in ``asyncio.run`` (pytest-asyncio is
not a dependency).  The TUI is exercised against the real ``skmap`` demo
module from :mod:`skmap_ui.demo`.
"""

import asyncio
import itertools
import re

from skmap import Acc, Ass, Head, RFlag, Reg, RegVec, ValueKind, ValueType
from skmap import register_Module
from skmap.external_mem import ExternalMemVec
from skmap_ui import SkmapUiApp
# column indices of the register map table (see SkmapUiApp.on_mount)
ADDR, T, ACC, NAME, VALUE, DESC = range(6)
from skmap_ui.app import ModuleTree
from skmap_ui.demo import (
    MemRegio,
    _DemoModule,
    _SYSCTRL_ADDR,
    _SYSCTRL_DATA,
    _head_bytes,
    _mem_sub,
    _u32,
)
from rich.text import Text
from textual.css.scalar import Unit
from textual.widgets import DataTable, RichLog, Tree
from textual.widgets._data_table import Coordinate


def _run(coro):
    return asyncio.run(coro)


def _iter_nodes(tree: Tree):
    """Yield every tree node, including the root (which holds the top
    module in this app)."""

    def walk(node):
        for child in node.children:
            yield child
            yield from walk(child)

    yield tree.root
    yield from walk(tree.root)


async def _wait_asserts(app, pilot, max_pause=500):
    for _ in range(max_pause):
        if app.asserts_checked:
            return
        await pilot.pause()
    raise AssertionError("asserts were not checked in time")


async def _select_node(app, node, pilot, max_pause=50):
    app.tree_view.select_node(node)
    for _ in range(max_pause):
        await pilot.pause()
        if app._row_keys:
            return
    raise AssertionError("table was not populated after node selection")


async def _wait_log(app, pilot, pred, max_pause=500):
    """Wait until ``pred(app._log_lines)`` is true.

    The log is append-only: each check / refresh that found triggered
    asserts appends a time-stamped block (in a worker, a few event
    loop turns after the triggering device I/O finished).
    """
    for _ in range(max_pause):
        if pred(app._log_lines):
            return
        await pilot.pause()
    raise AssertionError("expected log line never appeared")


def _last_block(lines: list[str]) -> list[str]:
    """Lines of the last logged block (its time-stamped header + rows)."""
    for i in range(len(lines) - 1, -1, -1):
        if "triggered, worst:" in lines[i]:
            return lines[i:]
    return []


def _n_blocks(lines: list[str]) -> int:
    """Number of time-stamped blocks in the log."""
    return sum(1 for line in lines if "triggered, worst:" in line)


async def _wait_cell(app, pilot, row, col, expected, max_pause=500):
    """Wait until cell (row, col) equals ``expected``."""
    for _ in range(max_pause):
        if _cell(app, row, col).strip() == expected:
            return
        await pilot.pause()
    raise AssertionError(
        f"cell ({row}, {col}) never became {expected!r} "
        f"(got {_cell(app, row, col)!r})"
    )


def make_demo():
    from skmap_ui.demo import make_demo_module

    return make_demo_module()


def _cell(app, row, col):
    cell = app.table.get_cell_at(Coordinate(row, col))
    if hasattr(cell, "plain"):
        return cell.plain
    return str(cell)


def _find_node(app, module):
    for node in _iter_nodes(app.tree_view):
        if node.data is module:
            return node
    raise AssertionError(f"tree node for {module.name()} not found")


# ---------------------------------------------------------------------------
# app / tree
# ---------------------------------------------------------------------------


def test_app_layout():
    async def run():
        app = SkmapUiApp(make_demo())
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.tree_view, ModuleTree)
            assert isinstance(app.table, DataTable)
            assert isinstance(app.log_view, RichLog)
            # the top module's register map is shown right away
            assert "DEMO_TOP" in app.table.border_title
            assert app.top_module.name() == "DEMO_TOP"

    _run(run())


def test_tree_starts_expanded():
    async def run():
        app = SkmapUiApp(make_demo())
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)

            expanded = [n for n in _iter_nodes(app.tree_view) if n.children]
            assert expanded, "expected module nodes with children"
            for node in expanded:
                assert node.is_expanded, f"{node.label.plain} not expanded"

    _run(run())


def test_tree_left_right_expand_collapse():
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)

            sysctrl = top.kids_cached()[0]
            node = _find_node(app, sysctrl)
            assert node.children and node.is_expanded

            app.tree_view.focus()
            app.tree_view.move_cursor(node)
            await pilot.pause()

            await pilot.press("left")
            await pilot.pause()
            assert node.is_collapsed

            await pilot.press("right")
            await pilot.pause()
            assert node.is_expanded

    _run(run())


def test_enter_opens_register_map():
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            assert "DEMO_TOP" in app.table.border_title

            # move the cursor (without selecting) to a kid node
            sysctrl = top.kids_cached()[0]
            node = _find_node(app, sysctrl)
            app.tree_view.focus()
            app.tree_view.move_cursor(node)
            await pilot.pause()

            # enter = Tree.select_cursor -> NodeSelected -> register map
            await pilot.press("enter")
            for _ in range(50):
                if "DEMO_SYSCTRL" in app.table.border_title:
                    break
                await pilot.pause()
            assert "DEMO_SYSCTRL" in app.table.border_title
            assert app.table.row_count == 2

    _run(run())


def test_mouse_resize_dividers():
    async def run():
        app = SkmapUiApp(make_demo())
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            await pilot.pause()

            tree = app.tree_view
            ws = app.workspace

            def pct(widget, attr="width"):
                # textual normalises width:% -> w and height:% -> h units
                scalar = getattr(widget.styles, attr)
                assert scalar.unit in (Unit.PERCENT, Unit.WIDTH, Unit.HEIGHT), (attr, scalar)
                return float(scalar.value)

            assert pct(tree) == 35.0

            ws_region = ws.region
            # --- vertical divider (tree | table) ---
            divider_x = tree.region.right - 1
            y = ws_region.y + 3
            await pilot.mouse_down(None, (divider_x, y))
            await pilot.pause()
            target_x = divider_x + 20
            await pilot.hover(None, (target_x, y))
            await pilot.mouse_up(None, (target_x, y))
            await pilot.pause()

            expected = (target_x - ws_region.x) / ws_region.width * 100
            assert abs(pct(tree) - expected) < 1.0
            assert pct(tree) > 35.0

            # --- horizontal divider (workspace | log) ---
            avail = (
                app.screen.size.height
                - app.header.region.height
                - app.footer.region.height
            )
            top = app.header.region.height
            ws_height = ws.region.height
            divider_y = ws_region.y + ws_height - 1
            x = ws_region.x + 5
            await pilot.mouse_down(None, (x, divider_y))
            await pilot.pause()
            target_y = divider_y - 10
            await pilot.hover(None, (x, target_y))
            await pilot.mouse_up(None, (x, target_y))
            await pilot.pause()

            expected_h = (target_y - top) / avail * 100
            assert abs(pct(app.workspace, "height") - expected_h) < 1.0
            assert ws.region.height < ws_height

    _run(run())


def test_tree_structure():
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            assert app.asserts_checked

            nodes = list(_iter_nodes(app.tree_view))
            # top + DEMO_SYSCTRL + DEMO_UART + DEMO_PMU + DMEM (external mem)
            assert len(nodes) == 5

            data = {id(n.data) for n in nodes}
            assert id(top) in data
            assert id(top.arr_external_mem[0]) in data
            sysctrl, pmu = top.kids_cached()
            assert id(sysctrl) in data and id(pmu) in data
            assert id(sysctrl.kids_cached()[0]) in data

            labels = [n.label.plain for n in nodes]
            assert any("DEMO_TOP" in l for l in labels)
            assert any("DEMO_SYSCTRL" in l for l in labels)
            assert any("DEMO_UART" in l for l in labels)
            assert any("DEMO_PMU" in l for l in labels)
            assert any("DMEM" in l for l in labels)
            assert not any("Uninitalised" in l for l in labels)

    _run(run())


# ---------------------------------------------------------------------------
# register map table
# ---------------------------------------------------------------------------


def test_register_map_top():
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)

            # K_ID, V_RESET, FLAGS, f0, f1, DMEM
            assert app.table.row_count == 6
            assert "DEMO_TOP" in app.table.border_title

            assert _cell(app, 0, NAME) == "K_ID"
            assert _cell(app, 0, ACC) == "k"
            assert _cell(app, 0, VALUE).strip() == "0xDEAD0001"
            assert _cell(app, 0, T) == "x32"

            assert _cell(app, 1, NAME) == "V_RESET"
            assert _cell(app, 1, ACC) == "rw"
            assert _cell(app, 1, VALUE).strip() == "0x0005"

            assert _cell(app, 2, NAME) == "FLAGS"
            assert _cell(app, 2, VALUE).strip() == "0b00000001"

            # flags are expanded as sub-rows
            assert _cell(app, 3, NAME) == "f0"
            assert _cell(app, 3, T) == "b"
            assert _cell(app, 3, ACC) == "0"
            assert "warn: True" in _cell(app, 3, VALUE)

            assert _cell(app, 4, NAME) == "f1"
            assert _cell(app, 4, VALUE).strip() == "False"

            # external mem row
            assert _cell(app, 5, NAME) == "DMEM"
            assert _cell(app, 5, VALUE).strip() == "(Mem size:16 B)"

            # row objects are real skmap instances
            assert isinstance(app._row_objs[app._row_keys[0]], Reg)
            assert isinstance(app._row_objs[app._row_keys[3]], RFlag)

    _run(run())


def test_register_map_kid():
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            sysctrl = top.kids_cached()[0]
            await _select_node(app, _find_node(app, sysctrl), pilot)

            assert app.table.row_count == 2
            assert "DEMO_SYSCTRL" in app.table.border_title

            assert _cell(app, 0, NAME) == "STATUS"
            assert _cell(app, 0, ACC) == "ro"
            assert "error: 0x0001" in _cell(app, 0, VALUE)

            assert _cell(app, 1, NAME) == "CTRL"
            assert _cell(app, 1, ACC) == "rw"

    _run(run())


def test_external_mem_node():
    """The demo's DMEM is an ExternalMemVec: selecting it in the tree
    opens the vec view (header row + one row per index); enter on a
    lane row prefills and edits that lane (write_idx_uint)."""
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            mem = top.arr_external_mem[0]
            assert isinstance(mem, ExternalMemVec)
            await _select_node(app, _find_node(app, mem), pilot)

            # header row + one row per vec index
            assert app.table.row_count == 1 + mem.vec_len()
            assert _cell(app, 0, NAME) == "DMEM"
            assert _cell(app, 0, ACC) == "rw"
            # the header contains addr, type, acc, name and description
            title = app.table.border_title
            assert hex(mem.base_addr) in title
            assert mem.value_type_str() in title
            assert "rw" in title
            assert "DMEM" in title
            assert "demo data memory" in title
            assert app._row_module is None
            assert _cell(app, 1, NAME) == "DMEM[0]"
            assert _cell(app, 2, NAME) == "DMEM[1]"

            # the (empty) device reads back zero in the lanes
            await _wait_cell(app, pilot, 1, VALUE, "0")

            # enter on a lane row prefills the current value
            app.table.move_cursor(row=1, column=0)
            await pilot.press("enter")
            await pilot.pause()
            assert app.value_input.value == "0"
            app.value_input.value = "0x2a"
            await pilot.press("enter")
            await pilot.pause()
            await _wait_cell(app, pilot, 1, VALUE, "42")
            assert mem.read_idx_uint_cached(0) == 0x2A

    _run(run())


# ---------------------------------------------------------------------------
# asserts -> log view
# ---------------------------------------------------------------------------


def test_asserts_logged():
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)

            assert app.asserts_checked
            assert app.last_worst_ass == Ass.error
            names = {getattr(i, "name", None) for i in app.last_asserts}
            assert names == {"f0", "STATUS", "V_EVENT"}

            # the log is a *snapshot*: one time stamp header, then one
            # line per triggered assert (print_table_reg_list columns)
            lines = app._log_lines
            assert len(lines) == 1 + len(app.last_asserts)
            header = lines[0]
            assert re.match(
                r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}", header
            ), header
            assert "asserts level >= debug" in header
            assert "3 triggered, worst: error" in header

            joined = "\n".join(lines)
            assert "FLAGS.f0" in joined
            assert "warn: True" in joined
            assert "STATUS" in joined
            assert "error: 0x0001" in joined
            assert "V_EVENT" in joined
            assert "info: 0x0001" in joined

            # the RichLog view holds the rendered snapshot too
            assert len(app.log_view.lines) > 3

    _run(run())


# ---------------------------------------------------------------------------
# triggering (write / read)
# ---------------------------------------------------------------------------


def test_trigger_writable_reg():
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)

            v_reset = app._row_objs[app._row_keys[1]]
            before = v_reset.read_uint_cached()
            assert before == 5

            app.table.move_cursor(row=1, column=0)
            app.action_trigger_selected()

            # async: the (random) write reaches the (fake) device in a
            # worker; the read-back updates the skmap cache
            for _ in range(500):
                if v_reset.read_uint_cached() != before:
                    break
                await pilot.pause()
            assert v_reset.read_uint_cached() != before
            # the cell shows the value as read back from the (fake) device
            await _wait_cell(
                app, pilot, 1, VALUE, f"0x{v_reset.read_uint_cached():04X}"
            )

    _run(run())


def test_trigger_readonly_reg():
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            sysctrl = top.kids_cached()[0]
            await _select_node(app, _find_node(app, sysctrl), pilot)

            # change the (fake) device value first (STATUS is at offset
            # 20 of the SYSCTRL data block); the trigger read must pick
            # up the new device state
            data = bytearray(_SYSCTRL_DATA)
            data[20:24] = _u32(0x2)
            top._regio.write_mem(_SYSCTRL_ADDR, bytes(data))

            app.table.move_cursor(row=0, column=0)  # STATUS (ro)
            app.action_trigger_selected()

            # async: ro register is read from the (fake) device
            await _wait_cell(app, pilot, 0, VALUE, "error: 0x0002")

    _run(run())


def test_trigger_flag_write():
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)

            f0 = app._row_objs[app._row_keys[3]]
            assert isinstance(f0, RFlag)
            app.table.move_cursor(row=3, column=0)
            n_writes = top._regio.n_writes
            app.action_trigger_selected()

            # async: the flag write reaches the (fake) device in a worker
            for _ in range(500):
                if top._regio.n_writes == n_writes + 1:
                    break
                await pilot.pause()
            assert top._regio.n_writes == n_writes + 1

    _run(run())


# ---------------------------------------------------------------------------
# make_tree failure -> partial checks + "Uninitalised" tree entries
# ---------------------------------------------------------------------------

_bad_top_counter = itertools.count()


def make_bad_top():
    """A module whose kid has an unregistered (unknown) head ID."""
    n = next(_bad_top_counter)
    top_mid = f"BADTOP{n}"[:8]
    kid_mid = f"NOCHILD{n}"[:8]

    class _BadTop(_DemoModule):
        mid = top_mid

        @classmethod
        def name(cls) -> str:
            return "BADTOP"

        @classmethod
        def checksum(cls) -> int:
            return n

        def _init_reg_map_k(self):
            pass

        def _init_reg_map_var(self):
            pass

    register_Module(_BadTop)

    kid_data = _head_bytes(kid_mid, 1, 0, len_kids=0, len_sub=0, len_k=0, len_var=0)
    top_data = (
        _head_bytes(top_mid, 1, 0, len_kids=1, len_sub=0, len_k=0, len_var=0)
        + _u32(0x60000000)
    )
    regio = MemRegio()
    regio.write_mem(0x60000000, kid_data)
    regio.write_mem(0x60000100, top_data)
    return _BadTop(regio, 0x60000100, Head(top_data), bytearray(top_data))


def test_unknown_kid_partial_asserts():
    async def run():
        bad = make_bad_top()
        app = SkmapUiApp(bad)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)

            # make_tree's failure is reported via logging (not in the
            # log); nothing triggered -> no block appended at all
            lines = app._log_lines
            assert lines == []
            assert _n_blocks(lines) == 0
            assert app.last_worst_ass == Ass.none  # nothing triggered

            # the uninitialised kid shows up in the tree
            labels = [n.label.plain for n in _iter_nodes(app.tree_view)]
            assert any("Uninitalised module" in l for l in labels)
            uninit = [n for n in _iter_nodes(app.tree_view) if n.data is None]
            assert len(uninit) == 1

    _run(run())


def test_clear_log():
    async def run():
        app = SkmapUiApp(make_demo())
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            assert len(app._log_lines) > 3

            app.action_clear_log()
            assert len(app._log_lines) == 0
            assert len(app.log_view.lines) == 0

    _run(run())


# ---------------------------------------------------------------------------
# tree highlight for the displayed module
# ---------------------------------------------------------------------------


def test_tree_highlight_follows_displayed_module():
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            assert app.tree_view.highlighted is app.tree_view.root

            sysctrl = top.kids_cached()[0]
            node = _find_node(app, sysctrl)
            await _select_node(app, node, pilot)
            assert app.tree_view.highlighted is node
            assert "DEMO_SYSCTRL" in app.table.border_title

            mem = top.arr_external_mem[0]
            mem_node = _find_node(app, mem)
            await _select_node(app, mem_node, pilot)
            assert app.tree_view.highlighted is mem_node

    _run(run())


def test_render_label_highlight_style():
    from rich.style import Style

    def has_bold(text):
        for sp in text.spans:
            st = sp.style
            if isinstance(st, str):
                st = Style.parse(st)
            if st and st.bold:
                return True
        return False

    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            root = app.tree_view.root
            assert has_bold(app.tree_view.render_label(root, Style(), Style()))

            other = _find_node(app, top.kids_cached()[0])
            assert not has_bold(
                app.tree_view.render_label(other, Style(), Style())
            )

            app.tree_view.set_highlighted(None)
            assert not has_bold(
                app.tree_view.render_label(root, Style(), Style())
            )

    _run(run())


# ---------------------------------------------------------------------------
# value editing (enter on a table row -> input line -> write/clear)
# ---------------------------------------------------------------------------


def test_enter_edits_rw_value():
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            sysctrl = top.kids_cached()[0]
            await _select_node(app, _find_node(app, sysctrl), pilot)
            ctrl = app._row_objs[app._row_keys[1]]
            assert ctrl.read_uint_cached() == 0

            app.table.focus()
            app.table.move_cursor(row=1, column=0)
            await pilot.press("enter")
            await pilot.pause()
            assert app.app.focused is app.value_input
            assert "CTRL" in app.value_input.placeholder

            # the input line is prefilled with the current value (hex
            # for x32 bits registers, zero-padded to the byte width)
            assert app.value_input.value == "0x0000"
            app.value_input.value = "0x2f"
            await pilot.press("enter")
            await pilot.pause()
            assert app.app.focused is app.table

            # async: the write reaches the (fake) device in a worker
            for _ in range(500):
                if ctrl.read_uint_cached() == 0x2F:
                    break
                await pilot.pause()
            assert ctrl.read_uint_cached() == 0x2F
            # the cell is refreshed by the device read-back
            await _wait_cell(app, pilot, 1, VALUE, "0x002F")

    _run(run())


def test_enter_clears_rc_value():
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            pmu = top.kids_cached()[1]
            await _select_node(app, _find_node(app, pmu), pilot)
            v_event = app._row_objs[app._row_keys[0]]
            assert v_event.read_uint_cached() == 1

            app.table.focus()
            app.table.move_cursor(row=0, column=0)
            await pilot.press("enter")
            await pilot.pause()

            # rc: enter writes zero immediately (no input line), async
            assert app.app.focused is app.table
            for _ in range(500):
                if v_event.read_uint_cached() == 0:
                    break
                await pilot.pause()
            assert v_event.read_uint_cached() == 0
            # the cell is refreshed by the device read-back
            # (V_EVENT has an ass, so the cell carries the ass prefix)
            from rich.text import Text

            expected = Text.from_markup(
                v_event.read_rich_str_cached()
            ).plain
            await _wait_cell(app, pilot, 0, VALUE, expected)

    _run(run())


def test_enter_edit_cancel_and_invalid():
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            sysctrl = top.kids_cached()[0]
            await _select_node(app, _find_node(app, sysctrl), pilot)
            ctrl = app._row_objs[app._row_keys[1]]
            assert ctrl.read_uint_cached() == 0

            app.table.focus()
            app.table.move_cursor(row=1, column=0)

            # escape cancels the edit
            await pilot.press("enter")
            await pilot.pause()
            assert app.app.focused is app.value_input
            await pilot.press("7")
            await pilot.press("escape")
            await pilot.pause()
            assert ctrl.read_uint_cached() == 0
            assert app.app.focused is app.table
            assert app.value_input.value == ""

            # out-of-range value is rejected: no write, the input is kept
            # (focus stays on the input line to fix the value)
            await pilot.press("enter")
            await pilot.pause()
            app.value_input.value = "0x100000000"
            await pilot.press("enter")
            await pilot.pause()
            assert ctrl.read_uint_cached() == 0
            assert app.app.focused is app.value_input
            assert app.value_input.value == "0x100000000"

    _run(run())


def test_enter_on_readonly_and_flag_rows():
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)

            # K_ID (k) is row 0: hardwired, nothing to edit
            app.table.focus()
            app.table.move_cursor(row=0, column=0)
            await pilot.press("enter")
            await pilot.pause()
            assert app.app.focused is app.table
            assert app.value_input.value == ""

            # f0 (flag row) is row 3: not a register
            app.table.move_cursor(row=3, column=0)
            await pilot.press("enter")
            await pilot.pause()
            assert app.app.focused is app.table
            assert app.value_input.value == ""

    _run(run())


def test_parse_value():
    class _VT:
        def __init__(self, kind, width):
            self.kind = kind
            self.width = width

    class _RegStub:
        def __init__(self, kind, width):
            self.value_type = _VT(kind, width)

    parse = SkmapUiApp._parse_value

    # scalar: decimal or 0x-hex, in range [0, 2**width)
    r32 = _RegStub(ValueKind.uint, 32)
    assert parse(r32, "255") == 255
    assert parse(r32, "0x2f") == 0x2F
    assert parse(r32, " 0xff ") == 0xFF
    assert parse(r32, "0x0") == 0
    assert parse(r32, "0x100000000") is None  # too big
    assert parse(r32, "-1") is None
    assert parse(r32, "zz") is None
    assert parse(r32, "") is None

    # sint: negative values fit in [-2**(w-1), 2**(w-1))
    s8 = _RegStub(ValueKind.sint, 8)
    assert parse(s8, "-1") == -1
    assert parse(s8, "-128") == -128
    assert parse(s8, "127") == 127
    assert parse(s8, "128") is None
    assert parse(s8, "-129") is None


# ---------------------------------------------------------------------------
# value editing: prefill, vector lane inputs, value-cell wrapping
# ---------------------------------------------------------------------------

_edit_top_counter = itertools.count()


def make_edit_top():
    """A module with wide / vector registers for the edit tests."""
    n = next(_edit_top_counter)
    edit_mid = f"EDITTOP{n}"[:8]
    big = 0xDEADBEEFCAFEBABE1234567890ABCDEF

    vt_big = ValueType(kind=ValueKind.bits, width=128)
    vt_u4 = ValueType(kind=ValueKind.uint, width=8, vec_len=4)
    vt_s2 = ValueType(kind=ValueKind.sint, width=8, vec_len=2)
    vt_lmt = ValueType(kind=ValueKind.bits, width=32)

    class _EditTop(_DemoModule):
        mid = edit_mid

        @classmethod
        def name(cls) -> str:
            return "EDITTOP"

        @classmethod
        def checksum(cls) -> int:
            return n

        def _init_reg_map_k(self) -> None:
            pass

        def _init_reg_map_var(self) -> None:
            self._add_reg_var(
                Reg(self, "BIG", vt_big, acc=Acc.rw, desc="wide value")
            )
            self._add_reg_var(
                RegVec(self, "V4", vt_u4, acc=Acc.rw, desc="uint vec")
            )
            self._add_reg_var(
                RegVec(self, "S2", vt_s2, acc=Acc.rw, desc="sint vec")
            )
            self._add_reg_var(
                Reg(
                    self, "LMT", vt_lmt, acc=Acc.rw,
                    desc="limited", max=100, min=2,
                )
            )

    register_Module(_EditTop)

    data = (
        # 16 + 4 + 2 + 4 = 26 bytes of regs, word padded -> 7 words
        _head_bytes(edit_mid, 1, 0, len_kids=0, len_sub=0, len_k=0, len_var=7)
        + big.to_bytes(16, "little")
        + bytes([0xAA, 0xBB, 0xCC, 0xDD])
        + bytes([5, 0xAB])  # sint lanes: 5 and -85
        + b"\x00" * 2  # LMT is word aligned
        + (30).to_bytes(4, "little")  # LMT within [2, 100]
    )
    regio = MemRegio()
    regio.write_mem(0x70000000, data)
    return _EditTop(regio, 0x70000000, Head(data), bytearray(data))


def test_scalar_edit_prefills_current_value():
    """enter on a register prefills the input line with the current
    value (hex for bits kinds, decimal for uint/sint)."""
    async def run():
        top = make_edit_top()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)

            # BIG (bits, row 0): prefilled in hex (like the table shows)
            app.table.focus()
            app.table.move_cursor(row=0, column=0)
            await pilot.press("enter")
            await pilot.pause()
            assert app.value_input.value == (
                "0xDEADBEEFCAFEBABE1234567890ABCDEF"
            )

            # V4 is a vector: enter opens one input per index instead
            await pilot.press("escape")
            await pilot.pause()
            assert len(app.value_inputs.query("ValueInput.lane")) == 0
            app.table.move_cursor(row=1, column=0)
            await pilot.press("enter")
            await pilot.pause()
            lanes = list(app.value_inputs.query("ValueInput.lane"))
            assert len(lanes) == 4
            # uint lanes are prefilled in decimal
            assert [l.value for l in lanes] == ["170", "187", "204", "221"]
            # the single input is hidden while the lanes are open
            assert app.value_input.parent is None
    _run(run())


def test_vector_edit_writes_lanes():
    """enter on a vector register opens one input column per index
    (prefilled via Reg.read_idx_value_cached); submit writes every lane
    with Reg.write_idx_uint (hex and decimal both accepted)."""
    async def run():
        top = make_edit_top()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            v4 = top.arr_reg_var[1]
            assert v4.name == "V4"

            app.table.focus()
            app.table.move_cursor(row=1, column=0)
            await pilot.press("enter")
            await pilot.pause()
            lanes = list(app.value_inputs.query("ValueInput.lane"))
            assert len(lanes) == 4
            # edit one lane (0x-hex), keep the prefilled others
            lanes[2].value = "0xF0"
            await pilot.press("enter")
            await pilot.pause()

            # the lane inputs close and the write goes out per lane
            assert len(app.value_inputs.query("ValueInput.lane")) == 0
            await _wait_cell(app, pilot, 1, VALUE, "[ 170, 187, 240, 221 ]")
            assert v4.read_idx_uint_cached(2) == 0xF0
            assert v4.read_idx_uint_cached(0) == 0xAA
    _run(run())


def test_vector_edit_sint_lanes():
    """sint vector lanes are prefilled as signed decimal and written
    with Reg.write_idx_sint (negative values accepted)."""
    async def run():
        top = make_edit_top()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            s2 = top.arr_reg_var[2]
            assert s2.name == "S2"

            app.table.focus()
            app.table.move_cursor(row=2, column=0)
            await pilot.press("enter")
            await pilot.pause()
            lanes = list(app.value_inputs.query("ValueInput.lane"))
            assert [l.value for l in lanes] == ["5", "-85"]
            lanes[0].value = "-1"
            await pilot.press("enter")
            await pilot.pause()
            await _wait_cell(app, pilot, 2, VALUE, "[ -1, -85 ]")
            assert s2.read_idx_sint_cached(0) == -1
            assert s2.read_idx_sint_cached(1) == -85
    _run(run())


def test_value_cells_wrap_over_multiple_lines():
    """A value wider than the Value column wraps over multiple lines
    (auto-height rows) instead of being clipped."""
    async def run():
        top = make_edit_top()
        app = SkmapUiApp(top)
        async with app.run_test(size=(70, 24)) as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            await pilot.pause()
            # the 34-char hex value of BIG does not fit the 22-wide
            # Value column: its row must grow to at least 2 lines
            assert app.table.get_row_height("r0") >= 2

            # a short value (different length) makes the row collapse to
            # one line again: the auto-height row is re-measured
            app._update_row_value("r0", Text("0x0"))
            assert app.table.get_row_height("r0") == 1
    _run(run())


def test_edit_outside_min_max_aborted():
    """A value outside a reg's configured min / max limits is caught
    locally (the condition Reg.check_value_limit() would raise on) and
    the write is aborted before it reaches the device; 't' picks random
    values within the limits."""
    async def run():
        top = make_edit_top()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            lmt = top.arr_reg_var[3]
            assert lmt.name == "LMT" and lmt.min == 2 and lmt.max == 100

            app.table.focus()
            app.table.move_cursor(row=3, column=0)
            await pilot.press("enter")
            await pilot.pause()
            # bits kind: prefilled in hex (like the table shows)
            assert app.value_input.value == "0x001E"

            # 256 > max 100: rejected, the input stays open for a fix
            app.value_input.value = "0x100"
            await pilot.press("enter")
            await pilot.pause()
            assert app.app.focused is app.value_input
            assert app.value_input.value == "0x100"
            assert lmt.read_uint_cached() == 30

            # 1 < min 2: rejected as well
            app.value_input.value = "1"
            await pilot.press("enter")
            await pilot.pause()
            assert app.app.focused is app.value_input
            assert lmt.read_uint_cached() == 30

            # in range: written (the cell shows the limit range prefix)
            app.value_input.value = "100"
            await pilot.press("enter")
            await pilot.pause()
            await _wait_cell(app, pilot, 3, VALUE, "(0x0002 <= v <= 0x0064) 0x0064")
            assert lmt.read_uint_cached() == 100

            # 't' picks random values within [2, 100]
            for _ in range(5):
                app.table.move_cursor(row=3, column=0)
                await pilot.press("t")
                await pilot.pause()
                assert 2 <= lmt.read_uint_cached() <= 100
    _run(run())


# ---------------------------------------------------------------------------
# display options: v (uint / sint shown as bits / hex), e (expand vec regs)
# ---------------------------------------------------------------------------


def test_value_bits_toggle():
    """'v' toggles the uint / sint value display between int (decimal)
    and bits (hex, like the bits kind — sint lanes as their raw two's
    complement); the input prefill follows the display."""
    async def run():
        top = make_edit_top()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            # default: int (decimal)
            await _wait_cell(app, pilot, 1, VALUE, "[ 170, 187, 204, 221 ]")
            await _wait_cell(app, pilot, 2, VALUE, "[ 5, -85 ]")
            # bits: hex (S2 lane 1 = -85 is shown as 0xAB)
            await pilot.press("v")
            await pilot.pause()
            await _wait_cell(app, pilot, 1, VALUE, "[ 0xAA, 0xBB, 0xCC, 0xDD ]")
            await _wait_cell(app, pilot, 2, VALUE, "[ 0x5, 0xAB ]")
            # the active option shows in the border title
            assert "bits" in app.table.border_title
            # toggle back to int
            await pilot.press("v")
            await pilot.pause()
            await _wait_cell(app, pilot, 1, VALUE, "[ 170, 187, 204, 221 ]")
            await _wait_cell(app, pilot, 2, VALUE, "[ 5, -85 ]")
            assert "bits" not in app.table.border_title
            # the vector input prefill follows the display mode
            app.table.focus()
            app.table.move_cursor(row=2, column=0)
            await pilot.press("enter")
            await pilot.pause()
            lanes = list(app.value_inputs.query("ValueInput.lane"))
            assert [l.value for l in lanes] == ["5", "-85"]
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("v")
            await pilot.pause()
            app.table.move_cursor(row=2, column=0)
            await pilot.press("enter")
            await pilot.pause()
            lanes = list(app.value_inputs.query("ValueInput.lane"))
            assert [l.value for l in lanes] == ["0x5", "0xAB"]
            await pilot.press("escape")
            await pilot.pause()
    _run(run())


def test_expand_vec_toggle():
    """'e' expands vector registers into one row per vector index
    (like the ExternalMemVec view: the register's own row becomes the
    header row) and collapses them again."""
    async def run():
        top = make_edit_top()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            # 4 registers -> 4 rows
            assert len(app._row_keys) == 4
            assert app._row_reg_idx == {}
            await pilot.press("e")
            await pilot.pause()
            # V4: header + 4 lanes (rows 1-5), S2: header + 2 lanes
            # (rows 6-8) -> 10 rows
            assert len(app._row_keys) == 10
            assert app._row_reg_idx == {
                "r2": 0, "r3": 1, "r4": 2, "r5": 3, "r7": 0, "r8": 1,
            }
            # lane rows: lane address + name[idx] + the lane value
            assert _cell(app, 2, ADDR) == "0x70000020"
            assert _cell(app, 2, NAME) == "V4[0]"
            await _wait_cell(app, pilot, 2, VALUE, "170")
            await _wait_cell(app, pilot, 3, VALUE, "187")
            assert _cell(app, 6, NAME) == "S2"  # S2 header row
            assert _cell(app, 7, NAME) == "S2[0]"
            assert _cell(app, 7, ADDR) == "0x70000024"
            await _wait_cell(app, pilot, 7, VALUE, "5")
            await _wait_cell(app, pilot, 8, VALUE, "-85")
            # the header rows keep the full value
            await _wait_cell(app, pilot, 1, VALUE, "[ 170, 187, 204, 221 ]")
            assert "expand vec" in app.table.border_title
            # toggle back: one row per register again
            await pilot.press("e")
            await pilot.pause()
            assert len(app._row_keys) == 4
            assert _cell(app, 1, NAME) == "V4"
            assert app._row_reg_idx == {}
    _run(run())


def test_expand_vec_lane_edit():
    """enter on a lane row of an expanded vector register prefills and
    edits just that lane (write_idx_uint); the header row and the other
    lanes are updated by the read-back, the untouched lanes keep their
    values."""
    async def run():
        top = make_edit_top()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            await pilot.press("e")
            await pilot.pause()
            v4 = top.arr_reg_var[1]
            assert v4.name == "V4"
            # edit lane 2 of V4 (row 4)
            app.table.focus()
            app.table.move_cursor(row=4, column=0)
            await pilot.press("enter")
            await pilot.pause()
            assert app.value_input.value == "204"
            app.value_input.value = "0xF0"
            await pilot.press("enter")
            await pilot.pause()
            await _wait_cell(app, pilot, 4, VALUE, "240")
            assert v4.read_idx_uint_cached(2) == 0xF0
            assert v4.read_idx_uint_cached(0) == 0xAA  # untouched
            assert v4.read_idx_uint_cached(3) == 0xDD  # untouched
            # the header row reflects the new lane
            await _wait_cell(app, pilot, 1, VALUE, "[ 170, 187, 240, 221 ]")
    _run(run())


def test_expand_vec_bits_display():
    """the display options compose: expanded lanes honor the 'v' bits
    display (hex, sint lanes as raw two's complement)."""
    async def run():
        top = make_edit_top()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            await pilot.press("e")
            await pilot.pause()
            await pilot.press("v")
            await pilot.pause()
            assert len(app._row_keys) == 10
            await _wait_cell(app, pilot, 2, VALUE, "0xAA")
            await _wait_cell(app, pilot, 5, VALUE, "0xDD")
            await _wait_cell(app, pilot, 7, VALUE, "0x5")
            await _wait_cell(app, pilot, 8, VALUE, "0xAB")
            # header rows in bits mode too
            await _wait_cell(app, pilot, 1, VALUE, "[ 0xAA, 0xBB, 0xCC, 0xDD ]")
            # the lane input prefill follows the bits display
            app.table.focus()
            app.table.move_cursor(row=4, column=0)
            await pilot.press("enter")
            await pilot.pause()
            assert app.value_input.value == "0xCC"
            await pilot.press("escape")
            await pilot.pause()
    _run(run())


# ---------------------------------------------------------------------------
# ExternalMemVec views: header + lane rows, lane / all-lane edits, rc clear
# ---------------------------------------------------------------------------

_vecmem_top_counter = itertools.count()


def make_vecmem_top():
    """A module with two vec external mems (rw uint8 x4, rc sint8 x2)."""
    n = next(_vecmem_top_counter)
    vec_mid = f"VECMEM{n}"[:8]
    vt_rw = ValueType(kind=ValueKind.uint, width=8, vec_len=4)
    vt_rc = ValueType(kind=ValueKind.sint, width=8, vec_len=2)
    rw_addr = 0x70001000
    rc_addr = 0x70002000

    class _VecMemTop(_DemoModule):
        mid = vec_mid

        @classmethod
        def name(cls) -> str:
            return "VECMEM"

        @classmethod
        def checksum(cls) -> int:
            return n

        def _init_reg_map_k(self) -> None:
            pass

        def _init_reg_map_var(self) -> None:
            pass

        def _init_external_mem(self) -> None:
            assert self.len_external_mem == 2
            self.external_mem_at(0).details(
                "MEMV", vt_rw, Acc.rw, "vec mem rw"
            )
            self.external_mem_at(1).details(
                "MRC", vt_rc, Acc.rc, "vec mem rc"
            )

    register_Module(_VecMemTop)

    data = (
        _head_bytes(vec_mid, 1, 0, len_kids=0, len_sub=6, len_k=0, len_var=0)
        + _mem_sub(rw_addr, 4, Acc.rw)
        + _mem_sub(rc_addr, 2, Acc.rc)
    )
    regio = MemRegio()
    regio.write_mem(0x70000000, data)
    regio.write_mem(rw_addr, bytes([0xAA, 0xBB, 0xCC, 0xDD]))
    regio.write_mem(rc_addr, bytes([7, 0xF0]))  # sint lanes: 7 and -16
    return _VecMemTop(regio, 0x70000000, Head(data), bytearray(data))


def test_external_mem_vec_lane_edit():
    """An ExternalMemVec is shown as a header row plus one row per vec
    index (read_idx_rich_str_cached); enter on a lane row prefills and
    edits that lane (write_idx_uint)."""
    async def run():
        top = make_vecmem_top()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            mem = top.arr_external_mem[0]
            assert isinstance(mem, ExternalMemVec)
            await _select_node(app, _find_node(app, mem), pilot)

            # header row + 4 lane rows
            assert len(app._row_keys) == 5
            assert app._row_mem_idx == {"r1": 0, "r2": 1, "r3": 2, "r4": 3}
            # uint8 lanes are shown in decimal
            assert _cell(app, 1, NAME) == "MEMV[0]"
            await _wait_cell(app, pilot, 1, VALUE, "170")
            assert _cell(app, 2, VALUE).strip() == "187"
            assert _cell(app, 3, VALUE).strip() == "204"
            assert _cell(app, 4, VALUE).strip() == "221"

            # edit one lane: enter prefills the current value
            app.table.focus()
            app.table.move_cursor(row=2, column=0)
            await pilot.press("enter")
            await pilot.pause()
            assert app.value_input.value == "187"
            app.value_input.value = "0xF0"
            await pilot.press("enter")
            await pilot.pause()
            await _wait_cell(app, pilot, 2, VALUE, "240")
            assert mem.read_idx_uint_cached(1) == 0xF0

    _run(run())


def test_external_mem_vec_all_lanes_edit():
    """enter on the header row of an ExternalMemVec view opens one input
    per lane (all prefilled); submit writes every lane."""
    async def run():
        top = make_vecmem_top()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            mem = top.arr_external_mem[0]
            await _select_node(app, _find_node(app, mem), pilot)

            app.table.focus()
            app.table.move_cursor(row=0, column=0)
            await pilot.press("enter")
            await pilot.pause()
            lanes = list(app.value_inputs.query("ValueInput.lane"))
            assert [l.value for l in lanes] == ["170", "187", "204", "221"]
            lanes[2].value = "1"
            await pilot.press("enter")
            await pilot.pause()
            assert len(app.value_inputs.query("ValueInput.lane")) == 0
            await _wait_cell(app, pilot, 3, VALUE, "1")
            assert _cell(app, 1, VALUE).strip() == "170"
            assert mem.read_idx_uint_cached(2) == 1
    _run(run())


def test_external_mem_vec_rc_clear():
    """enter on an rc ExternalMemVec lane row writes zero to the lane;
    on the header row it clears every lane (write_idx_uint(idx, 0))."""
    async def run():
        top = make_vecmem_top()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            mem = top.arr_external_mem[1]
            assert mem.acc == Acc.rc
            await _select_node(app, _find_node(app, mem), pilot)

            # header row + 2 lane rows; lane 1 is a -16 sint8
            assert len(app._row_keys) == 3
            await _wait_cell(app, pilot, 1, VALUE, "7")
            await _wait_cell(app, pilot, 2, VALUE, "-16")

            # enter on the lane row clears just that lane
            app.table.focus()
            app.table.move_cursor(row=2, column=0)
            await pilot.press("enter")
            await pilot.pause()
            await _wait_cell(app, pilot, 2, VALUE, "0")
            assert _cell(app, 1, VALUE).strip() == "7"

            # enter on the header row clears every lane
            app.table.move_cursor(row=0, column=0)
            await pilot.press("enter")
            await pilot.pause()
            await _wait_cell(app, pilot, 1, VALUE, "0")
            assert _cell(app, 2, VALUE).strip() == "0"
            assert mem.read_idx_sint_cached(0) == 0
            assert mem.read_idx_sint_cached(1) == 0
    _run(run())


def test_clear_triggered_clears_shown_module_rc():
    """'x' (and the refresh) clear the rc registers of the *selected*
    module (clear_reg_rc) and the triggered asserts of the whole tree
    (clear_assert_tree)."""
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            # the PMU's V_EVENT rc reg is triggered (info, level >= debug)
            pmu = top.kids_cached()[1]
            v_event = pmu.arr_reg_var[0]
            assert v_event.read_uint_cached() == 1

            # show the PMU map, then clear triggered: V_EVENT (the rc reg
            # of the selected module) is written zero ...
            await _select_node(app, _find_node(app, pmu), pilot)
            app.action_clear_triggered()
            for _ in range(500):
                if v_event.read_uint_cached() == 0:
                    break
                await pilot.pause()
            assert v_event.read_uint_cached() == 0
    _run(run())


# ---------------------------------------------------------------------------
# assert options: level (l), refresh (r / --refresh), clear triggered (x)
# ---------------------------------------------------------------------------


def test_cycle_asserts_level():
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        assert app.asserts_level == Ass.debug
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            assert "3 triggered" in app._log_lines[0]
            n0 = _n_blocks(app._log_lines)
            assert n0 == 1  # the initial check appended one block

            # l: info -> all three still logged (V_EVENT is info);
            # the check appends a new block (the log grows)
            await pilot.press("l")
            await pilot.pause()
            assert app.asserts_level == Ass.info
            await _wait_log(
                app, pilot,
                lambda ls: _n_blocks(ls) == n0 + 1
                and "asserts level >= info" in _last_block(ls)[0],
            )
            assert "3 triggered, worst: error" in _last_block(app._log_lines)[0]

            # l: warn -> V_EVENT (info) drops out of the new block
            await pilot.press("l")
            await pilot.pause()
            assert app.asserts_level == Ass.warn
            await _wait_log(
                app, pilot,
                lambda ls: _n_blocks(ls) == n0 + 2
                and "2 triggered" in _last_block(ls)[0],
            )
            assert "V_EVENT" not in "\n".join(_last_block(app._log_lines))

            # l: error -> only STATUS in the new block
            await pilot.press("l")
            await pilot.pause()
            assert app.asserts_level == Ass.error
            await _wait_log(
                app, pilot,
                lambda ls: _n_blocks(ls) == n0 + 3
                and "1 triggered" in _last_block(ls)[0],
            )
            joined = "\n".join(_last_block(app._log_lines))
            assert "STATUS" in joined
            assert "f0" not in joined

            # the log border title tracks the current options
            assert "level >= error" in app.log_view.border_title
    _run(run())


def test_refresh_reads_all_registers():
    async def run():
        top = make_demo()
        app = SkmapUiApp(top, refresh=0.05)  # read_all_tree every 50 ms
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            sysctrl = top.kids_cached()[0]
            await _select_node(app, _find_node(app, sysctrl), pilot)

            # change the (fake) device value (STATUS is at offset 20);
            # the periodic read_all_tree must pick it up without any
            # user interaction
            data = bytearray(_SYSCTRL_DATA)
            data[20:24] = _u32(0x7)
            top._regio.write_mem(_SYSCTRL_ADDR, bytes(data))

            await _wait_cell(app, pilot, 0, VALUE, "error: 0x0007")
    _run(run())


def test_refresh_appends_log_and_clears_rc():
    """Each refresh: read_all_tree -> re-check (the log grows with a
    time-stamped block of the triggered asserts) -> clear the rc
    registers so they do not re-trigger on the next refresh."""
    async def run():
        top = make_demo()
        app = SkmapUiApp(top, refresh=0.1)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            pmu = top.kids_cached()[1]
            v_event = pmu.arr_reg_var[0]
            assert v_event.name == "V_EVENT"
            assert v_event.read_uint_cached() == 1  # triggered on start
            n0 = _n_blocks(app._log_lines)

            # wait until several refreshes have appended their blocks
            for _ in range(1000):
                if _n_blocks(app._log_lines) >= n0 + 3:
                    break
                await pilot.pause()
            assert _n_blocks(app._log_lines) >= n0 + 3

            # the rc register was cleared by the first refresh
            assert v_event.read_uint_cached() == 0
            # the first block still lists V_EVENT, later blocks do not
            joined = "\n".join(app._log_lines)
            assert "V_EVENT" in joined
            last = "\n".join(_last_block(app._log_lines))
            assert "V_EVENT" not in last
            # ro STATUS (error) is not rc: it re-triggers every refresh
            assert "STATUS" in last
    _run(run())


def test_write_held_while_refresh_in_flight():
    """A register write must not go to the device while a refresh is
    in progress: the write worker holds the write until the refresh
    has finished."""
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            sysctrl = top.kids_cached()[0]
            await _select_node(app, _find_node(app, sysctrl), pilot)
            ctrl = sysctrl.arr_reg_var[1]
            assert ctrl.name == "CTRL"

            # simulate a refresh in flight: the write must be held
            assert app._refresh_idle.is_set()
            app._refresh_idle.clear()
            app._write_row(1, ctrl, 0x42, "WRITE")
            for _ in range(50):
                await pilot.pause()
            assert ctrl.read_uint_cached() == 0  # still not written

            # the refresh finishes: the held write now goes out
            app._refresh_idle.set()
            await _wait_cell(app, pilot, 1, VALUE, "0x0042")
            assert ctrl.read_uint_cached() == 0x42
    _run(run())


def test_log_assert_levels_colored():
    """Assert level names in the log use their ``Ass`` color
    (e.g. ``Ass.error.color``), matching the register map view."""
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            from rich.style import Style
            from rich.text import Text

            written: list = []
            real_write = app.log_view.write

            def spy_write(content, *args, **kwargs):
                written.append(content)
                return real_write(content, *args, **kwargs)

            app.log_view.write = spy_write
            try:
                app._append_assert_log(
                    app.last_worst_ass, list(app.last_asserts)
                )
            finally:
                app.log_view.write = real_write

            header, table = written[0], written[1]

            def norm_style(st):
                return st if isinstance(st, Style) else Style.parse(st)

            # header: the log level and the worst level in their colors
            spans = {
                header[s.start : s.end].plain: norm_style(s.style)
                for s in header.spans
            }
            assert spans[app.asserts_level.name] == Style.parse(
                app.asserts_level.color
            )
            assert spans[app.last_worst_ass.name] == Style.parse(
                app.last_worst_ass.color
            )
            # value rows: the same colored markup as the register map
            # view — each value carries its evaluated level's color
            ass_colors = {Style.parse(m.color) for m in Ass}
            value_cells = table.columns[VALUE]._cells
            assert len(value_cells) == len(app.last_asserts)
            for value in value_cells:
                assert isinstance(value, Text)
                assert any(norm_style(s.style) in ass_colors for s in value.spans)
    _run(run())


def test_cycle_refresh_key():
    async def run():
        app = SkmapUiApp(make_demo())
        assert app.refresh_period is None
        # the attribute must not shadow App.refresh() (Textual internal)
        assert callable(getattr(app, "refresh"))
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            assert app._refresh_timer is None

            await pilot.press("r")
            await pilot.pause()
            assert app.refresh_period == 1.0
            assert app._refresh_timer is not None

            await pilot.press("r")
            await pilot.pause()
            assert app.refresh_period == 5.0

            await pilot.press("r")
            await pilot.pause()
            assert app.refresh_period == 30.0

            await pilot.press("r")  # back to off
            await pilot.pause()
            assert app.refresh_period is None
            assert app._refresh_timer is None
            assert "refresh: off" in app.log_view.border_title
    _run(run())


def test_refresh_period_does_not_shadow_app_refresh():
    """Regression: the refresh period must not shadow ``App.refresh()``.

    It used to be stored as ``self.refresh`` (float | None); Textual
    internals call ``app.refresh(...)``, e.g. when a screen is removed
    (pressing the ``keys`` / help key), which then crashed with
    ``TypeError: 'NoneType' object is not callable``.
    """
    # attribute check without running the app
    off = SkmapUiApp(make_demo())
    assert off.refresh_period is None
    assert callable(off.refresh)  # still the real Textual method
    on = SkmapUiApp(make_demo(), refresh=5.0)
    assert on.refresh_period == 5.0
    assert callable(on.refresh)

    async def run():
        app = SkmapUiApp(make_demo(), refresh=0.5)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            # simulate opening / closing a screen (like the keys screen):
            # App.remove() calls parent.refresh(layout=True) on the App
            from textual.screen import Screen

            await app.push_screen(Screen())
            await pilot.pause()
            await app.pop_screen()
            await pilot.pause()
            assert app.is_running
    _run(run())


def test_clear_triggered():
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            pmu = top.kids_cached()[1]
            v_event = pmu.arr_reg_var[0]
            assert v_event.name == "V_EVENT"
            assert v_event.read_uint_cached() == 1

            # x: write zero to every triggered rc register, re-read from
            # the device, re-check
            await pilot.press("x")
            await pilot.pause()
            for _ in range(500):
                if v_event.read_uint_cached() == 0:
                    break
                await pilot.pause()
            assert v_event.read_uint_cached() == 0

            # the block appended after the clear drops V_EVENT (rc,
            # cleared); the warn flag and the error register (not rc)
            # remain in it
            await _wait_log(
                app, pilot,
                lambda ls: _last_block(ls)
                and "2 triggered, worst: error" in _last_block(ls)[0],
            )
            joined = "\n".join(_last_block(app._log_lines))
            assert "V_EVENT" not in joined
            assert "FLAGS.f0" in joined
            assert "STATUS" in joined
    _run(run())


def test_cli_asserts_level_option():
    import subprocess
    import sys

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "skmap_ui",
            "--demo",
            "--smoke",
            "--asserts-level",
            "error",
            "--refresh",
            "0",
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr
    assert "1 triggered, worst: error" in proc.stdout
    assert "STATUS" in proc.stdout
