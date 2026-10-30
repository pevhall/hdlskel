"""Headless smoke tests for the skmap_ui TUI (Textual 8.x, no plugins).

Each test wraps an ``async`` runner in ``asyncio.run`` (pytest-asyncio is
not a dependency).  The TUI is exercised against the real ``skmap`` demo
module from :mod:`skmap_ui.demo`.
"""

import asyncio
import itertools
import re

from skmap import Acc, Ass, Head, RFlag, Reg, RegVec, ValueCheck, ValueConvert, ValueKind, ValueType, VType
from skmap import register_Module
from skmap.external_mem import ExternalMemVec
from skmap_ui import SkmapUiApp
# column indices of the register map table (see SkmapUiApp.on_mount)
ADDR, T, ACC, NAME, VALUE, DESC = range(6)
from skmap_ui.app import (
    COL_DESC,
    COL_NAME,
    COL_VALUE,
    ModuleTree,
    RegMapTable,
    _hex,
)
from skmap_ui.demo import (
    MemRegio,
    _DemoModule,
    _SYSCTRL_ADDR,
    _SYSCTRL_DATA,
    _TOP_ADDR,
    _TOP_DATA,
    _UART_ADDR,
    _UART_DATA,
    _head_bytes,
    _mem_sub,
    _u32,
)
from rich.text import Text
from textual.css.scalar import Unit
from textual.widgets import DataTable, RichLog, Tabs, Tree
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
            # the workspace's height percentage resolves against its
            # container's content area (the tab pane), so the drag math
            # (app and test) works in that frame, not the screen's
            cont = app.workspace.parent.content_region
            top = cont.y
            avail = cont.height
            ws_region = ws.region
            ws_height = ws_region.height
            divider_y = ws_region.y + ws_height - 1
            x = ws_region.x + 5
            await pilot.mouse_down(None, (x, divider_y))
            await pilot.pause()
            # 3 rows up: on the small test terminal the workspace sits
            # low in its pane, and the resize clamps at 20 % — a bigger
            # drag would hit the clamp and not mirror the drag position
            target_y = divider_y - 3
            await pilot.hover(None, (x, target_y))
            await pilot.mouse_up(None, (x, target_y))
            await pilot.pause()

            expected_h = (target_y - top) / avail * 100
            assert abs(pct(app.workspace, "height") - expected_h) < 1.0
            assert ws.region.height < ws_height

    _run(run())


def test_mouse_resize_value_column():
    """Dragging the boundary between the *Value* and the *Description*
    column of the register map resizes the value column (the description
    takes what is left); double-clicking the boundary gives the default
    width back.  The width belongs to the column, so it also survives
    showing another module."""
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        # wide enough that the value column can really grow (the drag
        # clamps so the description keeps a few cells of the table)
        async with app.run_test(size=(200, 30)) as pilot:
            await _wait_asserts(app, pilot)
            await pilot.pause()
            table = app.table
            default = table.value_col_width()
            assert default == RegMapTable.VALUE_COL_DEFAULT
            y = table.region.y + table.header_height + 1   # a row of the body
            bx = table.value_col_boundary_screen_x()

            # the boundary is where the two columns really meet: a few cells
            # to the left hover the value cell, to the right the description
            await pilot.hover(None, (bx - 4, y))
            await pilot.pause()
            assert table.hover_coordinate.column == table.get_column_index(COL_VALUE)
            await pilot.hover(None, (bx + 4, y))
            await pilot.pause()
            assert table.hover_coordinate.column == table.get_column_index(COL_DESC)

            # drag right: the value column gets wider
            await pilot.mouse_down(None, (bx, y))
            await pilot.pause()
            assert app._drag == "col"
            await pilot.hover(None, (bx + 12, y))
            await pilot.pause()
            wide = table.value_col_width()
            assert wide > default
            await pilot.mouse_up(None, (bx + 12, y))
            await pilot.pause()
            assert app._drag is None

            # drag left: narrower than the default again
            await pilot.mouse_down(None, (bx + 12, y))
            await pilot.hover(None, (bx - 8, y))
            await pilot.pause()
            narrow = table.value_col_width()
            await pilot.mouse_up(None, (bx - 8, y))
            assert narrow < default

            # the columns are not rebuilt when another module is shown
            await _select_node(app, _find_node(app, top.kids_cached()[0]), pilot)
            assert table.value_col_width() == narrow
            await _select_node(app, _find_node(app, top), pilot)
            assert table.value_col_width() == narrow

            # double-click the boundary: the default width is back
            bx = table.value_col_boundary_screen_x()
            await pilot.double_click(None, (bx, y))
            await pilot.pause()
            assert table.value_col_width() == default
    _run(run())


def test_mouse_resize_value_column_scrolled():
    """On a narrow terminal the Value | Description boundary is out of the
    table (the fixed columns before it do not fit), and scrolling the
    register map horizontally brings it back: the drag follows the
    scrolled position."""
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test(size=(120, 30)) as pilot:
            await _wait_asserts(app, pilot)
            await pilot.pause()
            table = app.table
            y = table.region.y + table.header_height + 1
            assert table.value_col_boundary_screen_x() > table.region.right
            # no hit outside of the table
            assert app._hit_divider(table.region.right + 2, y) != "col"

            table.scroll_x = table.scroll_x + 30
            await pilot.pause()
            bx = table.value_col_boundary_screen_x()
            assert bx < table.region.right
            assert app._hit_divider(bx, y) == "col"

            await pilot.mouse_down(None, (bx, y))
            await pilot.hover(None, (bx - 10, y))
            await pilot.pause()
            narrower = table.value_col_width()
            await pilot.mouse_up(None, (bx - 10, y))
            assert narrower < RegMapTable.VALUE_COL_DEFAULT
            assert narrower >= RegMapTable.VALUE_COL_MIN

            # dragging all the way to the right of the table is clamped, the
            # description keeps some cells and the boundary stays grabbable
            edge = table.region.right - 1
            bx = table.value_col_boundary_screen_x()   # the first drag moved it
            await pilot.mouse_down(None, (bx, y))
            await pilot.hover(None, (edge, y))
            await pilot.pause()
            await pilot.mouse_up(None, (edge, y))
            assert table.value_col_width() > narrower
            assert table.value_col_boundary_screen_x() < table.region.right
    _run(run())


def _desc_column_of_rows(app):
    """For every visible body row of the register map: the column at which
    its *Description* text is rendered, read back from the rendered line
    (so a row that is drawn with a stale column layout shows up)."""
    table = app.table
    col_name = table.get_column_index(COL_NAME)
    col_desc = table.get_column_index(COL_DESC)
    out = {}
    for row in range(table.row_count):
        name = _cell(app, row, col_name).strip()
        desc = _cell(app, row, col_desc).strip()
        if not name or not desc:
            continue
        for y in range(table.region.height):
            line = "".join(seg.text for seg in table.render_line(y))
            if f" {name} " in line and desc in line:
                out[name] = line.rindex(desc)
                break
    assert out, "no register row of the module could be rendered"
    return out


def test_resize_value_column_redraws_every_row():
    """The DataTable caches rendered rows, so changing the width of the
    Value column must invalidate them: otherwise only the row under the
    cursor is drawn with the new width and all the other rows keep the
    old Value | Description split."""
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test(size=(200, 30)) as pilot:
            await _wait_asserts(app, pilot)
            await pilot.pause()
            table = app.table
            default = table.value_col_width()
            y = table.region.y + table.header_height + 1
            before = _desc_column_of_rows(app)
            assert len(set(before.values())) == 1, before

            bx = table.value_col_boundary_screen_x()
            await pilot.mouse_down(None, (bx, y))
            await pilot.hover(None, (bx + 10, y))
            await pilot.pause()
            await pilot.mouse_up(None, (table.value_col_boundary_screen_x(), y))

            assert table.value_col_width() == default + 10   # the column did resize
            after = _desc_column_of_rows(app)
            assert len(set(after.values())) == 1, after            # every row agrees
            assert set(after.values()) == {v + 10 for v in before.values()}, (before, after)

            # and the same when the width is reset with a double-click
            bx = table.value_col_boundary_screen_x()
            await pilot.double_click(None, (bx, y))
            await pilot.pause()
            back = _desc_column_of_rows(app)
            assert set(back.values()) == set(before.values()), (before, back)
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
            assert _cell(app, 1, VALUE).strip() == "0x00000005"

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
            assert "error: 0x00000001" in _cell(app, 0, VALUE)

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
            assert "error: 0x00000001" in joined
            assert "V_EVENT" in joined
            assert "info: 0x00000001" in joined

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

            # async: the (random) write reaches the (fake) device in a
            # worker; the write updates the skmap cache (no read-back). The
            # trigger writes a random value, so it can (very unlikely) pick the value
            # that is already there, another trigger picks a different one.
            for _try in range(3):
                app.action_trigger_selected()
                for _ in range(500):
                    if v_reset.read_uint_cached() != before:
                        break
                    await pilot.pause()
                if v_reset.read_uint_cached() != before:
                    break
            assert v_reset.read_uint_cached() != before
            # the cell shows the written value (from the skmap cache),
            # the number of hex digits comes from the width of the register
            await _wait_cell(
                app, pilot, 1, VALUE,
                _hex(v_reset.read_uint_cached(), v_reset.value_type.width),
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
            await _wait_cell(app, pilot, 0, VALUE, "error: 0x00000002")

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
    top_mid = f"BTOP{n:04d}"
    kid_mid = f"NCHD{n:04d}"

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
            # for bits registers, zero-padded to width/4 hex chars)
            assert app.value_input.value == "0x00000000"
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
            # the cell is refreshed from the skmap cache (no read-back)
            await _wait_cell(app, pilot, 1, VALUE, "0x0000002F")

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
            # the cell is refreshed from the skmap cache (no read-back)
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

    # sint hex is a bit pattern: any hex value that fits the width is
    # accepted; with the width-MSB set the value is negative (static
    # cast: 0xFF -> -1, 0x80 -> -128 for an 8-bit sint)
    assert parse(s8, "0xFF") == -1
    assert parse(s8, "0x80") == -128
    assert parse(s8, "0x7F") == 127
    assert parse(s8, "0x100") is None  # does not fit the 8-bit width
    # non-byte width: only the elem_w MSB (bit w-1) is the sign bit
    s12 = _RegStub(ValueKind.sint, 12)
    assert parse(s12, "0xF8") == 248  # bit 11 clear: stays positive
    assert parse(s12, "0xFF8") == -8
    assert parse(s12, "0xFFF") == -1
    assert parse(s12, "0x1000") is None  # does not fit the 12-bit width
    assert parse(s12, "4056") is None  # decimal still needs the signed range
    assert parse(s12, "-8") == -8
    # hex values below the sint range are not bit patterns (rejected)
    assert parse(s8, "-0x81") is None
    # uint: unchanged (hex only wraps within the width, never negative)
    assert parse(r32, "-0x1") is None


# ---------------------------------------------------------------------------
# value editing: prefill, vector lane inputs, value-cell wrapping
# ---------------------------------------------------------------------------

_edit_top_counter = itertools.count()


def make_edit_top():
    """A module with wide / vector registers for the edit tests."""
    n = next(_edit_top_counter)
    edit_mid = f"EDTOP{n:03d}"   # 8 chars: the module id field of the head
    big = 0xDEADBEEFCAFEBABE1234567890ABCDEF

    vt_big = ValueType(kind=ValueKind.bits, width=128)
    vt_u4 = ValueType(kind=ValueKind.uint, width=8, vec_len=4)
    vt_s2 = ValueType(kind=ValueKind.sint, width=8, vec_len=2)
    vt_lmt = ValueType(kind=ValueKind.bits, width=32)
    vt_s16 = ValueType(kind=ValueKind.sint, width=16)

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
                    desc="checked",
                    # a recipe v_check is the value limit of the module user,
                    # the replaced min / max of the register value are gone
                    v_check=ValueCheck(lambda v: 2 <= v <= 100, "(v >= 2) && (v <= 100)"),
                )
            )
            self._add_reg_var(
                Reg(
                    self, "TEMP", vt_s16, acc=Acc.rw, desc="scaled",
                    # the value of the module user is a float, the register
                    # holds it scaled by 16 (a recipe v_convert_wr)
                    v_type=VType.f,
                    v_check=ValueCheck(lambda v: -1000 <= v <= 1000,
                                       "((v >= -1000) && (v <= 1000))", VType.f),
                    v_convert=ValueConvert(lambda v: v * 16, lambda v: v / 16,
                                           "(v * 16)", "(v / 16)", VType.f),
                )
            )

    register_Module(_EditTop)

    data = (
        # 16 + 4 + 2 + 4 + 4 = 30 bytes of regs, word padded -> 8 words
        _head_bytes(edit_mid, 1, 0, len_kids=0, len_sub=0, len_k=0, len_var=8)
        + big.to_bytes(16, "little")
        + bytes([0xAA, 0xBB, 0xCC, 0xDD])
        + bytes([5, 0xAB])  # sint lanes: 5 and -85
        + b"\x00" * 2  # LMT is word aligned
        + (30).to_bytes(4, "little")  # LMT passes (2 <= 30 <= 100)
        + (-68).to_bytes(4, "little", signed=True)  # TEMP raw, -68/16 = -4.25
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


def test_edit_failing_v_check_aborted():
    """A value that does not pass the v_check of a reg is caught locally
    (the condition Reg.check_value_limit() would raise on) and the write
    is aborted before it reaches the device; triggering picks random
    values that pass the check."""
    async def run():
        top = make_edit_top()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            lmt = top.arr_reg_var[3]
            assert lmt.name == "LMT" and lmt.v_check is not None

            app.table.focus()
            app.table.move_cursor(row=3, column=0)
            await pilot.press("enter")
            await pilot.pause()
            # bits kind: prefilled in hex (like the table shows —
            # ceil_div(32, 4) = 8 digits)
            assert app.value_input.value == "0x0000001E"

            # 256 fails the v_check: rejected, the input stays open for a fix
            app.value_input.value = "0x100"
            await pilot.press("enter")
            await pilot.pause()
            assert app.app.focused is app.value_input
            assert app.value_input.value == "0x100"
            assert lmt.read_uint_cached() == 30

            # 1 fails the v_check as well
            app.value_input.value = "1"
            await pilot.press("enter")
            await pilot.pause()
            assert app.app.focused is app.value_input
            assert lmt.read_uint_cached() == 30

            # passing the check: written (the cell shows the check text)
            app.value_input.value = "100"
            await pilot.press("enter")
            await pilot.pause()
            await _wait_cell(
                app, pilot, 3, VALUE, "(v >= 2) && (v <= 100) 0x00000064"
            )
            assert lmt.read_uint_cached() == 100

            # trigger (no longer a key) picks random values that pass the check
            for _ in range(5):
                app.table.move_cursor(row=3, column=0)
                app.action_trigger_selected()
                for _ in range(50):
                    if 2 <= lmt.read_uint_cached() <= 100:
                        break
                    await pilot.pause()
                assert 2 <= lmt.read_uint_cached() <= 100
    _run(run())


def test_edit_v_convert_float():
    """A reg with a recipe value conversion is shown, prefilled and edited with
    the value of the module user (a float for ``v_type = 'f'``), not with the
    raw value stored in the register."""
    async def run():
        top = make_edit_top()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            temp = top.arr_reg_var[4]
            assert temp.name == "TEMP" and temp.has_v_convert

            app.table.focus()
            app.table.move_cursor(row=4, column=0)
            await pilot.press("enter")
            await pilot.pause()
            # prefilled with the user value of the raw -68 (a v / 16 inverse)
            assert app.value_input.value == "-4.25"

            # 1.55 -> raw 24.8, the value of a register is an int
            app.value_input.value = "1.55"
            await pilot.press("enter")
            await pilot.pause()
            await _wait_cell(
                app, pilot, 4, VALUE,
                "((v >= -1000) && (v <= 1000)) 1.5625",
            )
            assert temp.read_sint_cached() == 25
            assert temp.read_converted_cached() == 25 / 16

            # 2000 fails the v_check, the write is aborted
            app.value_input.value = "2000"
            await pilot.press("enter")
            await pilot.pause()
            assert app.app.focused is app.value_input
            assert temp.read_sint_cached() == 25

            # bits display: the raw value of the register (-68 of a 16 bit
            # sint is 0xFFBC), the conversion is in the description column
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("x")
            await pilot.pause()
            await _wait_cell(app, pilot, 4, VALUE, "0x0019")
            await _wait_cell(app, pilot, 4, DESC, "={ v * 16 } scaled")
            # the marker is colored like Ass.none, the description keeps the
            # blue of the column (see _reg_desc_text)
            cell = app.table.get_cell_at(Coordinate(4, DESC))
            assert [span.style for span in cell.spans] == [Ass.none.color, "blue"]
            assert cell.spans[0].end == len("={ v * 16 } ")
            # a register without a value conversion has a plain description (a Text
            # with only the blue style of the row, nothing is highlighted)
            cell_other = app.table.get_cell_at(Coordinate(0, DESC))
            assert cell_other.plain == top.arr_reg_var[0].desc
            assert cell_other.style == "blue"
            assert Ass.none.color not in [span.style for span in cell_other.spans]

            # a hex value writes the bits of the register directly, it does not
            # go through the conversion (0x10 = 16, not 16 * 16)
            app.table.move_cursor(row=4, column=0)
            await pilot.press("enter")
            await pilot.pause()
            assert app.value_input.value == "0x0019"  # prefilled with the raw bits
            app.value_input.value = "0x10"
            await pilot.press("enter")
            await pilot.pause()
            await _wait_cell(app, pilot, 4, VALUE, "0x0010")
            assert temp.read_sint_cached() == 16
            assert temp.read_converted_cached() == 1.0

            # every bit pattern that stands for a valid user value can be set,
            # 0xFFFF is -1 raw, -1/16 for the user
            app.table.move_cursor(row=4, column=0)
            await pilot.press("enter")
            await pilot.pause()
            app.value_input.value = "0xFFFF"
            await pilot.press("enter")
            await pilot.pause()
            await _wait_cell(app, pilot, 4, VALUE, "0xFFFF")
            assert temp.read_sint_cached() == -1

            # 0x7FFF would be 2047.9375 for the user, above the v_check: the
            # write fails (the reg checks the value the bits stand for)
            app.table.move_cursor(row=4, column=0)
            await pilot.press("enter")
            await pilot.pause()
            app.value_input.value = "0x7FFF"
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert temp.read_sint_cached() == -1
    _run(run())


# ---------------------------------------------------------------------------
# display options: v (uint / sint shown as bits / hex), e (expand vec regs)
# ---------------------------------------------------------------------------


def test_value_bits_toggle():
    """'x' toggles the uint / sint (hex) value display between int (decimal)
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
            # bits: hex, ceil_div(width, 4) digits (S2 lane 1 = -85
            # is shown as 0xAB)
            await pilot.press("x")
            await pilot.pause()
            await _wait_cell(app, pilot, 1, VALUE, "[ 0xAA, 0xBB, 0xCC, 0xDD ]")
            await _wait_cell(app, pilot, 2, VALUE, "[ 0x05, 0xAB ]")
            # the active option shows in the border title
            assert "bits" in app.table.border_title
            # toggle back to int
            await pilot.press("x")
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
            await pilot.press("x")
            await pilot.pause()
            app.table.move_cursor(row=2, column=0)
            await pilot.press("enter")
            await pilot.pause()
            lanes = list(app.value_inputs.query("ValueInput.lane"))
            assert [l.value for l in lanes] == ["0x05", "0xAB"]
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
            # 5 registers -> 5 rows
            assert len(app._row_keys) == 5
            assert app._row_reg_idx == {}
            await pilot.press("e")
            await pilot.pause()
            # V4: header + 4 lanes (rows 1-5), S2: header + 2 lanes
            # (rows 6-8) -> 11 rows
            assert len(app._row_keys) == 11
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
            assert len(app._row_keys) == 5
            assert _cell(app, 1, NAME) == "V4"
            assert app._row_reg_idx == {}
    _run(run())


def test_expand_vec_lane_edit():
    """enter on a lane row of an expanded vector register prefills and
    edits just that lane (write_idx_uint); the header row and the other
    lanes are updated from the register cache, the untouched lanes keep their
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
    """the display options compose: expanded lanes honor the 'x' bits
    display (hex, sint lanes as raw two's complement)."""
    async def run():
        top = make_edit_top()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            await pilot.press("e")
            await pilot.pause()
            await pilot.press("x")
            await pilot.pause()
            assert len(app._row_keys) == 11
            await _wait_cell(app, pilot, 2, VALUE, "0xAA")
            await _wait_cell(app, pilot, 5, VALUE, "0xDD")
            await _wait_cell(app, pilot, 7, VALUE, "0x05")
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


_sintw_counter = itertools.count()


def make_sintw_top():
    """A module with sint registers whose width is not a byte multiple
    (4-bit vector lanes, 12-bit scalar) for the sign-extension tests."""
    n = next(_sintw_counter)
    sintw_mid = f"STW{n:05d}"
    vt_s4 = ValueType(kind=ValueKind.sint, width=4, vec_len=4)
    vt_s12 = ValueType(kind=ValueKind.sint, width=12)

    class _SintWTop(_DemoModule):
        mid = sintw_mid

        @classmethod
        def name(cls) -> str:
            return "SINTW"

        @classmethod
        def checksum(cls) -> int:
            return n

        def _init_reg_map_k(self) -> None:
            pass

        def _init_reg_map_var(self) -> None:
            self._add_reg_var(
                RegVec(self, "S4", vt_s4, acc=Acc.rw, desc="sint4 vec")
            )
            self._add_reg_var(
                Reg(self, "S12", vt_s12, acc=Acc.rw, desc="sint12")
            )

    register_Module(_SintWTop)

    data = (
        # S4: 4 x 1 byte lanes (-1, 5, -2, 3) + S12: 4-byte word (-40)
        # = 8 bytes = 2 words
        _head_bytes(sintw_mid, 1, 0, len_kids=0, len_sub=0, len_k=0, len_var=2)
        + bytes([0xF, 5, 0xE, 3])
        + ((-40) & ((1 << 12) - 1)).to_bytes(4, "little")  # -40 as 12-bit
    )
    regio = MemRegio()
    regio.write_mem(0x70000000, data)
    return _SintWTop(regio, 0x70000000, Head(data), bytearray(data))


def test_bits_display_sign_extends_sint():
    """sint values in the bits display are sign-extended to
    ceil_div(width, 4) hex digits (dependent on value_type.width):
    a 12-bit -40 shows as 0xFD8, a 4-bit -2 as 0xE, a 4-bit -1 as 0xF;
    positive values and the int display are unaffected; the input
    prefill follows."""
    async def run():
        top = make_sintw_top()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            s4 = top.arr_reg_var[0]
            s12 = top.arr_reg_var[1]
            assert s4.read_idx_sint_cached(0) == -1
            assert s12.read_sint_cached() == -40
            await pilot.press("e")
            await pilot.pause()
            # int mode: signed decimal (row 0 = S4 header row)
            await _wait_cell(app, pilot, 0, VALUE, "[ -1, 5, -2, 3 ]")
            await _wait_cell(app, pilot, 5, VALUE, "-40")
            await pilot.press("x")
            await pilot.pause()
            # bits mode: ceil_div(width, 4) digits, sign-extended
            await _wait_cell(app, pilot, 0, VALUE, "[ 0xF, 0x5, 0xE, 0x3 ]")
            await _wait_cell(app, pilot, 5, VALUE, "0xFD8")
            # the lane prefill follows the sign-extended display
            app.table.focus()
            app.table.move_cursor(row=2, column=0)  # S4[1] = 5
            await pilot.press("enter")
            await pilot.pause()
            assert app.value_input.value == "0x5"
            await pilot.press("escape")
            await pilot.pause()
            app.table.move_cursor(row=5, column=0)  # S12 header
            await pilot.press("enter")
            await pilot.pause()
            assert app.value_input.value == "0xFD8"
            await pilot.press("escape")
            await pilot.pause()
    _run(run())


def test_edit_scalar_sint_negative_decimal():
    """A sint scalar accepts a negative decimal: the value is written
    with Reg.write_sint and the device holds the two's-complement bits
    (12-bit -8 -> 0xFF8), interpreted as the signed value."""
    async def run():
        top = make_sintw_top()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            s12 = top.arr_reg_var[1]
            assert s12.read_sint_cached() == -40
            app.table.focus()
            app.table.move_cursor(row=1, column=0)  # S12
            await pilot.press("enter")
            await pilot.pause()
            # int mode: prefilled with the signed decimal
            assert app.value_input.value == "-40"
            app.value_input.value = "-8"
            await pilot.press("enter")
            await pilot.pause()
            assert app.app.focused is app.table
            for _ in range(500):
                if s12.read_sint_cached() == -8:
                    break
                await pilot.pause()
            assert s12.read_sint_cached() == -8
            # the device holds the 12-bit two's-complement pattern
            assert s12.read_uint_cached() == 0xFF8
            await _wait_cell(app, pilot, 1, VALUE, "-8")
    _run(run())


def test_edit_scalar_sint_hex_is_bit_pattern():
    """A sint scalar accepts a hex value as a raw bit pattern of the
    value width: it only has to fit 12 bits, and with the elem_w MSB
    set it is negative (static cast: 0xFF8 -> -8); hex that does not
    fit the width is rejected (the write aborts, input kept)."""
    async def run():
        top = make_sintw_top()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            s12 = top.arr_reg_var[1]
            assert s12.read_sint_cached() == -40
            app.table.focus()
            app.table.move_cursor(row=1, column=0)  # S12
            await pilot.press("enter")
            await pilot.pause()
            # hex with the 12-bit MSB set: written as the negative value
            app.value_input.value = "0xFF8"
            await pilot.press("enter")
            await pilot.pause()
            for _ in range(500):
                if s12.read_sint_cached() == -8:
                    break
                await pilot.pause()
            assert s12.read_sint_cached() == -8
            assert s12.read_uint_cached() == 0xFF8

            # hex without the MSB: a positive value (0xF8 -> 248)
            app.table.move_cursor(row=1, column=0)
            await pilot.press("enter")
            await pilot.pause()
            app.value_input.value = "0xF8"
            await pilot.press("enter")
            await pilot.pause()
            for _ in range(500):
                if s12.read_sint_cached() == 248:
                    break
                await pilot.pause()
            assert s12.read_sint_cached() == 248

            # hex that does not fit the 12-bit width: rejected, the
            # input stays open and the device value is unchanged
            app.table.move_cursor(row=1, column=0)
            await pilot.press("enter")
            await pilot.pause()
            app.value_input.value = "0xFFF8"
            await pilot.press("enter")
            await pilot.pause()
            assert app.app.focused is app.value_input
            assert app.value_input.value == "0xFFF8"
            assert s12.read_sint_cached() == 248
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
    """'C' (and the refresh) clear the rc registers of the *selected*
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

            await _wait_cell(app, pilot, 0, VALUE, "error: 0x00000007")
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
            await _wait_cell(app, pilot, 1, VALUE, "0x00000042")
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

            await pilot.press("u")
            await pilot.pause()
            assert app.refresh_period == 1.0
            assert app._refresh_timer is not None

            await pilot.press("u")
            await pilot.pause()
            assert app.refresh_period == 5.0

            await pilot.press("u")
            await pilot.pause()
            assert app.refresh_period == 30.0

            await pilot.press("u")  # back to off
            await pilot.pause()
            assert app.refresh_period is None
            assert app._refresh_timer is None
            assert "update: off" in app.log_view.border_title
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


def test_clear_triggered_write_only_no_new_log():
    """'C' (clear RC) is *write-only*: it writes zero to every triggered
    rc register but performs no device reads and does NOT re-check the
    asserts, so it triggers / logs no new assert block."""
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            pmu = top.kids_cached()[1]
            v_event = pmu.arr_reg_var[0]
            assert v_event.name == "V_EVENT"
            assert v_event.read_uint_cached() == 1  # triggered on start
            n0 = _n_blocks(app._log_lines)
            assert n0 == 1  # only the initial check appended a block

            # x: write zero to V_EVENT (a triggered rc register of the
            # whole tree) ...
            await pilot.press("C")
            for _ in range(500):
                if v_event.read_uint_cached() == 0:
                    break
                await pilot.pause()
            assert v_event.read_uint_cached() == 0
            await pilot.pause()

            # ...but it did NOT re-check: no new block was appended (the
            # clear cannot trigger / log any new assert)
            assert _n_blocks(app._log_lines) == n0
            # the shown value cell is refreshed from the cache (now 0)
            await _select_node(app, _find_node(app, pmu), pilot)
            await _wait_cell(app, pilot, 0, VALUE, "info: 0x00000000")
    _run(run())


def test_clear_rc_clears_rc_register_not_non_rc_assert():
    """'C' (clear RC) writes zero to the *rc* registers that are
    triggered asserts (the whole tree) but leaves non-rc triggered
    asserts (ro / rw) untouched."""
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            # V_EVENT is an rc reg triggered assert (PMU); STATUS is an ro
            # reg triggered assert (SYSCTRL).  x must clear V_EVENT but
            # leave STATUS set.
            pmu = top.kids_cached()[1]
            sysctrl = top.kids_cached()[0]
            v_event = pmu.arr_reg_var[0]
            status = sysctrl.arr_reg_var[0]
            assert v_event.name == "V_EVENT" and v_event.acc == Acc.rc
            assert status.name == "STATUS" and status.acc == Acc.ro
            assert v_event.read_uint_cached() == 1  # triggered
            assert status.read_uint_cached() == 1   # triggered (ro)

            # show any module (the clear covers the whole tree)
            await _select_node(app, _find_node(app, top), pilot)
            await pilot.press("C")
            for _ in range(500):
                if v_event.read_uint_cached() == 0:
                    break
                await pilot.pause()
            assert v_event.read_uint_cached() == 0  # the rc reg was cleared
            assert status.read_uint_cached() == 1   # the ro reg was NOT
            # no re-check: the log did not grow
            assert _n_blocks(app._log_lines) == 1
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


# ---------------------------------------------------------------------------
# keymap: row-cursor highlight, 'u' update, 'r' read all (no 't' trigger)
# ---------------------------------------------------------------------------


def test_table_highlights_whole_row():
    """The register map table highlights the *whole row* of the
    selected cell (cursor_type=\"row\"), not just the cell."""
    async def run():
        app = SkmapUiApp(make_demo())
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            assert app.table.cursor_type == "row"
            await _select_node(app, _find_node(app, app.top_module), pilot)
            app.table.focus()
            app.table.move_cursor(row=1, column=3)  # V_RESET row, Name col
            await pilot.pause()
            assert app.table.cursor_row == 1
            # the CSS rule that styles the row cursor must be loaded
            # (with a background, so the whole row is tinted)
            styles = app.table.get_component_styles("datatable--cursor")
            assert styles.background is not None
    _run(run())


def test_read_all_key_reads_device_and_refreshes():
    """'R' (read all): a one-shot read of all modules from the device
    (read_all on every module) that updates the assert log and the
    shown values — without clearing the triggered rc registers."""
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            sysctrl = top.kids_cached()[0]
            status = sysctrl.arr_reg_var[0]
            assert status.name == "STATUS" and status.acc == Acc.ro
            pmu = top.kids_cached()[1]
            v_event = pmu.arr_reg_var[0]
            assert v_event.read_uint_cached() == 1  # triggered at start
            n_blocks_before = _n_blocks(app._log_lines)

            # show the SYSCTRL map (STATUS is its first row)
            await _select_node(app, _find_node(app, sysctrl), pilot)

            # put the cursor on CTRL (row 1), not the top row: a read-all
            # must keep the selected highlighted row where it is
            app.table.focus()
            app.table.move_cursor(row=1, column=0)
            await pilot.pause()

            # change the (fake) device STATUS value, then 'R' (read all)
            data = bytearray(_SYSCTRL_DATA)
            data[20:24] = _u32(0x42)
            top._regio.write_mem(_SYSCTRL_ADDR, bytes(data))
            await pilot.press("R")
            # the read reaches the cache: the shown value is refreshed
            await _wait_cell(app, pilot, 0, VALUE, "error: 0x00000042")
            assert status.read_uint_cached() == 0x42
            # ...and the selected (highlighted) row is kept
            assert app.table.cursor_row == 1
            # the assert re-check appended a block (still triggered) and
            # nothing was cleared (the rc register is still set)
            await _wait_log(
                app, pilot, lambda ls: _n_blocks(ls) > n_blocks_before
            )
            assert v_event.read_uint_cached() == 1  # rc NOT cleared by 'R'
    _run(run())


def test_read_selected_table_reads_cursor_reg():
    """'r' (read) with the register map focused reads the register under
    the table cursor from the device (updating the cache + cell)."""
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            sysctrl = top.kids_cached()[0]
            status = sysctrl.arr_reg_var[0]  # STATUS (ro)
            assert status.name == "STATUS"
            assert status.read_uint_cached() == 1  # initial value
            # show the SYSCTRL map (row 0 = STATUS)
            await _select_node(app, _find_node(app, sysctrl), pilot)
            app.table.focus()
            app.table.move_cursor(row=0, column=0)
            await pilot.pause()
            # change the (fake) device STATUS value (offset 20)
            data = bytearray(_SYSCTRL_DATA)
            data[20:24] = _u32(0x17)
            top._regio.write_mem(_SYSCTRL_ADDR, bytes(data))
            # the cache still shows the old value ...
            assert status.read_uint_cached() != 0x17
            # ...'r' (table focused) reads just the selected register
            await pilot.press("r")
            for _ in range(500):
                if status.read_uint_cached() == 0x17:
                    break
                await pilot.pause()
            assert status.read_uint_cached() == 0x17
    _run(run())


def test_read_selected_tree_reads_module():
    """'r' (read) with the tree focused calls ``Module.read_all()`` on
    the module under the tree cursor (all its registers, not just one)."""
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            sysctrl = top.kids_cached()[0]
            status = sysctrl.arr_reg_var[0]  # STATUS (ro)
            ctrl = sysctrl.arr_reg_var[1]    # CTRL (rw)
            # change BOTH device values (read_all reads all regs)
            data = bytearray(_SYSCTRL_DATA)
            data[20:24] = _u32(0x2A)  # STATUS (offset 20)
            data[24:28] = _u32(0x55)  # CTRL (offset 24)
            top._regio.write_mem(_SYSCTRL_ADDR, bytes(data))
            # focus the tree, cursor on the SYSCTRL node
            app.tree_view.select_node(_find_node(app, sysctrl))
            for _ in range(50):
                await pilot.pause()
            app.tree_view.focus()
            await pilot.pause()
            # 'r' (tree focused): read_all on the selected module
            await pilot.press("r")
            for _ in range(500):
                if (
                    status.read_uint_cached() == 0x2A
                    and ctrl.read_uint_cached() == 0x55
                ):
                    break
                await pilot.pause()
            assert status.read_uint_cached() == 0x2A
            assert ctrl.read_uint_cached() == 0x55
    _run(run())


def test_read_flag_updates_all_flags_of_reg():
    """'r' (read) on a flag row reads the whole RegFlags and refreshes
    every flag row under it (not just the selected one)."""
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            top_flags = top.arr_reg_var[1]
            f0, f1 = top_flags.flags[0], top_flags.flags[1]
            assert f1.read_bool_cached() is False  # f1 clear in the cache
            # set f1 in the *device* (the cache still has it clear)
            off = top_flags.addr - _TOP_ADDR
            data = bytearray(_TOP_DATA)
            data[off] = 3  # 0b11: f0 + f1
            top._regio.write_mem(_TOP_ADDR, bytes(data))
            # show the top module and put the cursor on the f0 row
            await _select_node(app, _find_node(app, top), pilot)
            f0_row = next(
                ii for ii, key in enumerate(app._row_keys)
                if app._row_objs[key] is f0
            )
            f1_row = next(
                ii for ii, key in enumerate(app._row_keys)
                if app._row_objs[key] is f1
            )
            app.table.focus()
            app.table.move_cursor(row=f0_row, column=0)
            await pilot.pause()
            # 'r' (table focused): read the whole FLAGS register
            await pilot.press("r")
            for _ in range(500):
                if f1.read_bool_cached() is True:
                    break
                await pilot.pause()
            # both flags were refreshed from the read (f1 now set)
            assert f1.read_bool_cached() is True
            assert _cell(app, f0_row, VALUE).strip() == "warn: True"
            assert _cell(app, f1_row, VALUE).strip() == "True"
    _run(run())


def test_read_triggered_reg_appends_log():
    """'r' (read) on a register whose assert is triggered appends a new
    block to the assert log (the read re-evaluates the assert too)."""
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            sysctrl = top.kids_cached()[0]
            status = sysctrl.arr_reg_var[0]  # STATUS (ro, error, set)
            assert status.read_bool_cached() is True  # triggered
            assert _n_blocks(app._log_lines) == 1
            await _select_node(app, _find_node(app, sysctrl), pilot)
            status_row = next(
                ii for ii, key in enumerate(app._row_keys)
                if app._row_objs[key] is status
            )
            app.table.focus()
            app.table.move_cursor(row=status_row, column=0)
            await pilot.pause()
            await pilot.press("r")
            await _wait_log(app, pilot, lambda lines: _n_blocks(lines) == 2)
            assert any("STATUS" in line for line in _last_block(app._log_lines))
    _run(run())


def test_read_module_appends_its_asserts_to_log():
    """'r' (read) with the tree focused reads the selected module and
    appends a block with *that module's* triggered asserts only (here
    STATUS — not the other modules' asserts)."""
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            sysctrl = top.kids_cached()[0]
            assert _n_blocks(app._log_lines) == 1
            app.tree_view.select_node(_find_node(app, sysctrl))
            for _ in range(50):
                await pilot.pause()
            app.tree_view.focus()
            await pilot.pause()
            await pilot.press("r")
            await _wait_log(app, pilot, lambda lines: _n_blocks(lines) == 2)
            last = _last_block(app._log_lines)
            assert any("STATUS" in line for line in last)
            assert not any("V_EVENT" in line for line in last)
            assert not any("FLAGS.f0" in line for line in last)
    _run(run())


def test_step_flag_toggles_selected_flag():
    """'+' / '-' on a flag row toggle it (a flag is one bit, so stepping
    wraps to the other value): here a flag bit of the FLAGS register."""
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            # the top module's FLAGS register: f0 (bit0) set, f1 clear
            top_flags = top.arr_reg_var[1]
            assert top_flags.name == "FLAGS"
            f0, f1 = top_flags.flags[0], top_flags.flags[1]
            assert f0.read_bool_cached() is True
            assert f1.read_bool_cached() is False
            # show the top module and put the cursor on the f0 flag row
            await _select_node(app, _find_node(app, top), pilot)
            f0_row = next(
                ii for ii, key in enumerate(app._row_keys)
                if app._row_objs[key] is f0
            )
            app.table.focus()
            app.table.move_cursor(row=f0_row, column=0)
            await pilot.pause()
            # '+' (table focused): the 1 bit flag wraps, so it toggles (f0)
            await pilot.press("+")
            for _ in range(500):
                if f0.read_bool_cached() is False:
                    break
                await pilot.pause()
            assert f0.read_bool_cached() is False  # f0 toggled off
            assert f1.read_bool_cached() is False  # f1 untouched
    _run(run())


def test_step_flag_toggles_flag_register():
    """'+' / '-' on a flag-register (bitfield) row toggle every flag of
    the register and write the result."""
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            top_flags = top.arr_reg_var[1]  # FLAGS: f0 set, f1 clear (0b01)
            assert top_flags.read_uint_cached() == 1
            # show the top module and put the cursor on the FLAGS row
            await _select_node(app, _find_node(app, top), pilot)
            flags_row = next(
                ii for ii, key in enumerate(app._row_keys)
                if app._row_objs[key] is top_flags
            )
            app.table.focus()
            app.table.move_cursor(row=flags_row, column=0)
            await pilot.pause()
            # '+' (table focused): toggle every flag of the register
            await pilot.press("+")
            for _ in range(500):
                if top_flags.read_uint_cached() == 2:  # 0b10
                    break
                await pilot.pause()
            assert top_flags.read_uint_cached() == 2  # f0 off, f1 on
    _run(run())


def _row_of(app, obj, lane=None) -> int:
    """Table row of ``obj`` (``lane``: the vector lane of an expanded row)."""
    for ii, key in enumerate(app._row_keys):
        if app._row_objs[key] is not obj:
            continue
        if app._row_reg_idx.get(key) == lane and key not in app._row_mem_idx:
            return ii
    raise AssertionError(f"no row for {obj} lane {lane}")


def _row_of_mem(app, mem, lane=None) -> int:
    """Table row of an ExternalMemVec (``lane=None``: the header row)."""
    for ii, key in enumerate(app._row_keys):
        if app._row_objs[key] is not mem:
            continue
        if app._row_mem_idx.get(key) == lane:
            return ii
    raise AssertionError(f"no row for {mem} lane {lane}")


async def _settles(pilot, cond, n=500) -> None:
    """Wait until ``cond()`` holds (the device write is async, via a worker)."""
    for _ in range(n):
        if cond():
            return
        await pilot.pause()
    raise AssertionError("condition never became true")


def test_step_up_down_wraps_vector_lanes():
    """'+' / '-' step the bits of the value and wrap at the width of the
    value: on the header row every lane of the vector, on a lane row just
    that lane (V4 is a uint8 x4 rw register)."""
    async def run():
        top = make_edit_top()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            v4 = top.arr_reg_var[1]
            assert v4.name == "V4"
            assert [v4.read_idx_uint_cached(i) for i in range(4)] == [
                0xAA, 0xBB, 0xCC, 0xDD
            ]
            # '+' on the header row: every lane one up (0xDD + 1 = 0xDE)
            app.table.focus()
            app.table.move_cursor(row=_row_of(app, v4), column=0)
            await pilot.pause()
            await pilot.press("+")
            await _settles(pilot, lambda: v4.read_idx_uint_cached(3) == 0xDE)
            assert [v4.read_idx_uint_cached(i) for i in range(4)] == [
                0xAB, 0xBC, 0xCD, 0xDE
            ]
            # expand into lane rows, set lane 3 to all ones and step just it:
            # 0xFF + 1 wraps to 0x00, the other lanes are not written
            await pilot.press("e")
            await pilot.pause()
            v4.write_idx_uint_cached(3, 0xFF)
            app.table.move_cursor(row=_row_of(app, v4, 3), column=0)
            await pilot.pause()
            await pilot.press("+")
            await _settles(pilot, lambda: v4.read_idx_uint_cached(3) == 0x00)
            assert v4.read_idx_uint_cached(2) == 0xCD  # stays as stepped above
            # '-' on the header row: every lane one down, 0x00 - 1 wraps
            # back to all ones (0xFF), the stepped-down lanes follow
            app.table.move_cursor(row=_row_of(app, v4), column=0)
            await pilot.pause()
            await pilot.press("-")
            await _settles(pilot, lambda: v4.read_idx_uint_cached(3) == 0xFF)
            assert [v4.read_idx_uint_cached(i) for i in range(4)] == [
                0xAA, 0xBB, 0xCC, 0xFF
            ]
    _run(run())


def test_step_signed_wraps_to_negative():
    """'+' steps the bits, so the largest value of a sint wraps to the
    most negative one (s8: 0x7F + 1 = 0x80 = -128)."""
    async def run():
        top = make_edit_top()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            s2 = top.arr_reg_var[2]
            assert s2.name == "S2" and s2.read_idx_sint_cached(1) == -85
            await pilot.press("e")
            await pilot.pause()
            s2.write_idx_sint_cached(0, 0x7F)  # the largest positive s8
            app.table.focus()
            app.table.move_cursor(row=_row_of(app, s2, 0), column=0)
            await pilot.pause()
            await pilot.press("+")
            await _settles(pilot, lambda: s2.read_idx_sint_cached(0) == -128)
            assert s2.read_idx_sint_cached(1) == -85  # the other lane stays
            # and one step down wraps back to the largest positive value
            await pilot.press("-")
            await _settles(pilot, lambda: s2.read_idx_sint_cached(0) == 0x7F)
    _run(run())


def test_step_rejected_by_v_check():
    """A stepped value is written by the register, so a value that does
    not pass the v_check of the register is not written (LMT: 2..100)."""
    async def run():
        top = make_edit_top()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            lmt = top.arr_reg_var[3]
            assert lmt.name == "LMT"
            lmt.write_uint_cached(100)  # the highest value that passes
            app.table.focus()
            app.table.move_cursor(row=_row_of(app, lmt), column=0)
            await pilot.pause()
            await pilot.press("+")  # 101 does not pass the check
            await pilot.pause(0.5)  # let the (rejected) write finish
            assert lmt.read_uint_cached() == 100
            # one step down passes and is written
            await pilot.press("-")
            await _settles(pilot, lambda: lmt.read_uint_cached() == 99)
    _run(run())


def test_step_cannot_write_a_read_only_register():
    """'+' / '-' only write 'rw' / 'wt' values: a read-only register is left
    alone, the app reports why it cannot write it."""
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            sysctrl = top.kids_cached()[0]  # DEMO_SYSCTRL: its STATUS is ro
            await _select_node(app, _find_node(app, sysctrl), pilot)
            ro = next(r for r in sysctrl.arr_reg_var if r.acc == Acc.ro)
            assert ro.name == "STATUS"
            before = ro.read_uint_cached()
            app.table.focus()
            app.table.move_cursor(row=_row_of(app, ro), column=0)
            await pilot.pause()
            await pilot.press("+")
            await pilot.pause(0.5)  # a write would have settled by now
            assert ro.read_uint_cached() == before
    _run(run())


def test_minus_and_plus_are_still_typeable_in_the_input():
    """'+' / '-' are app keys now, but the value input has the focus
    while a value is edited, so the keys must still reach it (a negative
    decimal value starts with '-', and the app action must not fire)."""
    async def run():
        top = make_edit_top()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            lmt = top.arr_reg_var[3]
            assert lmt.name == "LMT" and lmt.read_uint_cached() == 30
            app.table.focus()
            app.table.move_cursor(row=_row_of(app, lmt), column=0)
            await pilot.pause()
            await pilot.press("enter")  # edit the scalar, the input is focused
            await pilot.pause()
            app.value_input.value = ""
            await pilot.press("-")
            await pilot.pause()
            assert app.value_input.value == "-"
            await pilot.press("+")
            await pilot.pause()
            assert app.value_input.value == "-+"
            await pilot.press("escape")
            await pilot.pause()
            # nothing was written: the keys went to the input, not to the app
            assert lmt.read_uint_cached() == 30
    _run(run())


def test_step_external_mem_lane():
    """'+' / '-' also step an ExternalMemVec: the lane under the cursor,
    or every lane on the header row (wrapping in the width of a lane)."""
    async def run():
        top = make_vecmem_top()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            mem = top.arr_external_mem[0]
            assert isinstance(mem, ExternalMemVec)
            await _select_node(app, _find_node(app, mem), pilot)
            assert mem.read_idx_uint_cached(1) == 0xBB
            # the lane row: only that lane is stepped
            app.table.focus()
            app.table.move_cursor(row=_row_of_mem(app, mem, 1), column=0)
            await pilot.pause()
            await pilot.press("+")
            await _settles(pilot, lambda: mem.read_idx_uint_cached(1) == 0xBC)
            assert mem.read_idx_uint_cached(2) == 0xCC  # the other lanes stay
            # the header row: every lane, and the 0xFF lane wraps to 0x00
            mem.write_idx_uint_cached(3, 0xFF)
            app.table.move_cursor(row=_row_of_mem(app, mem), column=0)
            await pilot.pause()
            await pilot.press("+")
            await _settles(pilot, lambda: mem.read_idx_uint_cached(3) == 0x00)
            assert mem.read_idx_uint_cached(0) == 0xAB
            assert mem.read_idx_uint_cached(1) == 0xBD
    _run(run())


def test_keymap_read_keys_and_u_is_update():
    """'u' cycles the update period; 'R' is the one-shot read all;
    'r' is the one-shot read of the selection; the +/- step, 'C' clear RC
    and 'x' hex keys are bound (the old 't' / 'v' keys are gone)."""
    by_key = {}
    for b in SkmapUiApp.BINDINGS:
        if isinstance(b, tuple):
            by_key[b[0]] = b[1]
        else:
            by_key[b.key] = b.action
    keys = set(by_key)
    assert "u" in keys and "R" in keys and "r" in keys
    assert by_key["u"] == "cycle_refresh"       # u: update (periodic refresh)
    assert by_key["R"] == "read_all_modules"    # R: read all (one-shot)
    assert by_key["r"] == "read_selected"       # r: read the selection
    assert by_key["+"] == "value_step_up"       # +: one up, wrapping
    assert by_key["-"] == "value_step_down"     # -: one down, wrapping
    assert by_key["C"] == "clear_triggered"     # C: clear the rc registers
    assert by_key["x"] == "toggle_value_bits"   # x: show hex
    assert by_key["c"] == "clear_log"           # c: clear the log
    # 't' (toggle) and 'v' (bits) are replaced by +/- and x
    assert "t" not in keys and "v" not in keys

    async def run():
        app = SkmapUiApp(make_demo())
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            # 'u' cycles the update period, 'R' does not
            await pilot.press("u")
            await pilot.pause()
            assert app.refresh_period == 1.0
            await pilot.press("u")
            await pilot.pause()
            await pilot.press("u")
            await pilot.pause()
            await pilot.press("u")  # back to off
            await pilot.pause()
            assert app.refresh_period is None
            before = app.refresh_period
            await pilot.press("R")  # read all: no change to the period
            await pilot.pause()
            assert app.refresh_period is before
    _run(run())


def test_shift_up_down_moves_5_rows_table_and_tree():
    """'shift+up' / 'shift+down' move the selected row (table) / the
    cursor (tree) 5 lines at a time instead of one."""
    async def run():
        app = SkmapUiApp(make_demo())
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)

            # ---- register map table: the cursor moves 5 rows ----
            # show a module with several rows: expand a vector register
            # so the table has > 5 rows.  The top module's FLAGS has 2
            # flag sub-rows; simpler: put enough rows via expand on the
            # external mem vec (16 lanes).  Select DMEM (ExternalMemVec)
            # in the tree -> one row per lane (16 rows).
            dmem = app.top_module.arr_external_mem[0]
            await _select_node(app, _find_node(app, dmem), pilot)
            n = len(app._row_keys)
            assert n >= 6  # 16 lanes (>= 6)
            app.table.focus()
            app.table.move_cursor(row=0, column=0)
            await pilot.pause()
            # shift+down from row 0 -> row 5
            await pilot.press("shift+down")
            await pilot.pause()
            assert app.table.cursor_row == 5
            # shift+down again -> row 10
            await pilot.press("shift+down")
            await pilot.pause()
            assert app.table.cursor_row == 10
            # shift+up clamps at 0
            app.table.move_cursor(row=3, column=0)
            await pilot.pause()
            await pilot.press("shift+up")
            await pilot.pause()
            assert app.table.cursor_row == 0

            # ---- module tree: the cursor moves 5 lines ----
            # the demo tree is short (5 lines), so exercise the 5-step
            # move directly and check it clamps; a plain 'up'/'down' still
            # moves one line (so the 5-step is a real difference)
            tree = app.tree_view
            tree.focus()
            nlines = len(tree._tree_lines)  # noqa: SLF001
            assert nlines >= 3
            tree.cursor_line = nlines - 1  # bottom line
            await pilot.pause()
            # shift+up from the bottom clamps at 0 (a 5-step that is larger
            # than the remaining distance), unlike plain up (which would
            # land one line up)
            tree._move_cursor_by(5, up=True)
            await pilot.pause()
            assert tree.cursor_line == 0
            # shift+down from the top moves 5 lines (clamped to the bottom)
            tree.cursor_line = 0
            tree._move_cursor_by(5, up=False)
            await pilot.pause()
            assert tree.cursor_line == nlines - 1
    _run(run())


def test_shift_left_right_scrolls_table_horizontally():
    """In the register map table, 'shift+left' / 'shift+right' scroll
    the view horizontally (5 cells each, cursor unchanged); a plain
    'left' / 'right' still moves the cursor one column (not scroll)."""
    async def run():
        app = SkmapUiApp(make_demo())
        async with app.run_test(size=(60, 20)) as pilot:
            await _wait_asserts(app, pilot)
            app.table.focus()
            app.table.move_cursor(row=0, column=0)
            await pilot.pause()
            before_x, _ = app.table.scroll_offset
            # shift+right scrolls 5 cells right, the cursor stays put
            await pilot.press("shift+right")
            await pilot.pause()
            after_x, _ = app.table.scroll_offset
            assert after_x == before_x + 5
            assert app.table.cursor_column == 0  # cursor did not move
            # shift+left scrolls back 5 cells
            await pilot.press("shift+left")
            await pilot.pause()
            back_x, _ = app.table.scroll_offset
            assert back_x == before_x
    _run(run())


def test_shift_left_right_scrolls_tree_horizontally():
    """In the module tree, 'shift+left' / 'shift+right' scroll the view
    horizontally (5 cells each) without moving the cursor node (a plain
    'left' / 'right' expands / collapses the node there instead)."""
    async def run():
        app = SkmapUiApp(make_demo())
        async with app.run_test(size=(60, 20)) as pilot:
            await _wait_asserts(app, pilot)
            tree = app.tree_view
            tree.focus()
            node = tree.cursor_node
            tree.cursor_line = 0
            await pilot.pause()
            before_x, _ = tree.scroll_offset
            # shift+right scrolls 5 cells right, the node stays
            await pilot.press("shift+right")
            await pilot.pause()
            after_x, _ = tree.scroll_offset
            assert after_x == before_x + 5
            assert tree.cursor_node is node  # node did not move
            # shift+left scrolls back
            await pilot.press("shift+left")
            await pilot.pause()
            back_x, _ = tree.scroll_offset
            assert back_x == before_x
    _run(run())


def test_tab_focus_toggles_tree_and_table():
    """'tab' / 'shift+tab' move the focus between the two panels only
    (the tree and the register map table), never to the input / log."""
    async def run():
        app = SkmapUiApp(make_demo())
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            # the table has the initial focus
            assert app.app.focused is app.table

            def focus_panel():
                """The panel (tree / table) that has the focus."""
                focused = app.app.focused
                if focused is None:
                    return None
                if focused in app.tree_view.ancestors_with_self:
                    return app.tree_view
                if focused in app.table.ancestors_with_self:
                    return app.table
                return None

            assert focus_panel() is app.table
            # tab -> the tree, tab again -> back to the table
            await pilot.press("tab")
            await pilot.pause()
            assert focus_panel() is app.tree_view
            await pilot.press("tab")
            await pilot.pause()
            assert focus_panel() is app.table
            # shift+tab -> the tree as well (only two panels)
            await pilot.press("shift+tab")
            await pilot.pause()
            assert focus_panel() is app.tree_view
            await pilot.press("shift+tab")
            await pilot.pause()
            assert focus_panel() is app.table
            # the input and the log never receive the focus
            assert app.app.focused is not app.value_input
            assert app.app.focused is not app.log

    _run(run())


def test_x_clears_shown_module_rc_and_triggered_rc_asserts():
    """'C' (clear RC) writes zero to every rc register of the module
    whose register map is shown AND to every rc register that is a
    triggered assert (the log checks the whole tree)."""
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test(size=(90, 30)) as pilot:
            await _wait_asserts(app, pilot)
            sysctrl = top.kids_cached()[0]
            # UART.RSR (rc) starts clear: set the (fake) device RSR so
            # it becomes a triggered assert.  RSR lives in UART — not
            # the shown module — so 'C' must clear it as a *triggered
            # rc assert*, not via the shown module's clear_reg_rc().
            uart = sysctrl.kids_cached()[0]
            rsr = uart.arr_reg_var[0]
            assert rsr.name == "RSR" and rsr.acc == Acc.rc
            data = bytearray(_UART_DATA)
            data[20:24] = _u32(1)
            top._regio.write_mem(_UART_ADDR, bytes(data))
            # the assert check reads from the skmap cache, so pull the
            # (fake) device RSR value into the cache first
            await uart.read_bytes(rsr.addr, rsr.size)
            # force a re-check so RSR joins the triggered asserts
            app.action_check_asserts()
            for _ in range(500):
                if any(
                    isinstance(a, Reg) and a.name == "RSR"
                    for a in app.last_asserts
                ):
                    break
                await pilot.pause()
            assert any(
                isinstance(a, Reg) and a.name == "RSR"
                for a in app.last_asserts
            ), app.last_asserts

            # show the UART map (which owns RSR), then 'x' (clear RC):
            # the shown module's own rc registers are cleared via
            # clear_reg_rc() and RSR — a triggered rc assert — via
            # write_zero_cached()
            await _select_node(app, _find_node(app, uart), pilot)
            app.action_clear_triggered()
            for _ in range(500):
                if rsr.read_uint_cached() == 0:
                    break
                await pilot.pause()
            assert rsr.read_uint_cached() == 0
    _run(run())


# ---------------------------------------------------------------------------
# regio tab (embedded regio_ui view, fed by a RegioTap)
# ---------------------------------------------------------------------------


def _view_cell(view, row, col):
    """Plain text of a regio log table cell (columns: time, addr, op,
    data)."""
    cell = view.ops.get_cell_at(Coordinate(row, col))
    return cell.plain if hasattr(cell, "plain") else str(cell)


def test_regio_tab_embedded_capture_and_read():
    async def run():
        app = SkmapUiApp(make_demo())
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)

            view = app._regio_view
            # skmap_ui starts the embedded view **not** capturing: the
            # boot-time traffic (tree build, first read-all, assert
            # check) is not logged (regio_ui on its own captures from
            # the start)
            assert view.capture is False
            assert view.ops.row_count == 0

            # '2' switches to the regio tab (focus: the operations log)
            await pilot.press("2")
            await pilot.pause()
            assert app.tabs.active == "tab-regio"
            assert app.app.focused is view.ops

            # 'p' starts the capture (a view binding, so it acts while
            # the regio tab is shown)
            await pilot.press("p")
            await pilot.pause()
            assert view.capture is True

            # '1' switches back to the register map (focus: the table)
            await pilot.press("1")
            await pilot.pause()
            assert app.tabs.active == "tab-registers"
            assert app.app.focused is app.table

            # read the selected register: it now flows through the tap
            # and is logged on the (hidden) regio tab
            key, vreset = next(
                (k, o)
                for k, o in app._row_objs.items()
                if getattr(o, "name", "") == "V_RESET"
            )
            app.table.move_cursor(row=app._row_keys.index(key), column=0)
            await pilot.pause()
            await pilot.press("r")
            for _ in range(500):
                if view.ops.row_count:
                    break
                await pilot.pause()
            assert view.ops.row_count == 1
            assert int(_view_cell(view, 0, 1), 16) == vreset.addr
            assert _view_cell(view, 0, 2) == "rd"

            # 'p' (via the regio tab) stops the capture again
            await pilot.press("2")
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            assert view.capture is False

    _run(run())


def test_regio_tab_form_write_reaches_device():
    async def run():
        app = SkmapUiApp(make_demo())
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            view = app._regio_view

            await pilot.press("2")
            await pilot.pause()
            # start capturing so the write shows up in the log
            await pilot.press("p")
            await pilot.pause()

            sysctrl = app.top_module.kids_cached()[0]
            ctrl = next(r for r in sysctrl._arr_reg_var if r.name == "CTRL")
            assert ctrl.read_uint_cached() == 0

            # send a write from the form (enter in the data field);
            # it goes through the tap onto the app's regio device
            view.addr_input.value = hex(ctrl.addr)
            view.data_input.value = "0x2A"
            view.data_input.focus()
            await pilot.pause()
            await pilot.press("enter")
            for _ in range(500):
                if view.ops.row_count:
                    break
                await pilot.pause()
            assert view.ops.row_count == 1
            assert int(_view_cell(view, 0, 1), 16) == ctrl.addr
            assert _view_cell(view, 0, 2) == "wr"
            assert "2A" in _view_cell(view, 0, 3)
            # the write reached the device (fresh read comes back 0x2A)
            assert (await ctrl.read_uint()) == 0x2A
            # enter on the regio tab must NOT start editing a register
            # map row
            assert app.value_input.value == ""

    _run(run())


def test_regio_tab_footer_and_clear():
    """Regio tab: footer shows only c/p, skmap keys are disabled there,
    'c' clears only the shown tab's log, the tabs are labeled
    '1 skmap' / '2 regio' and 1/2 switch between them."""

    async def run():
        app = SkmapUiApp(make_demo())
        async with app.run_test(size=(140, 36)) as pilot:
            await _wait_asserts(app, pilot)

            # the tabs are labeled '1 skmap' / '2 regio' (the Tab
            # widget ids are prefixed by TabbedContent)
            tabs = app.query_one(Tabs)
            tab = tabs.get_tab("--content-tab-tab-registers")
            assert tab is not None and str(tab.render()).strip() == "1 skmap"
            tab = tabs.get_tab("--content-tab-tab-regio")
            assert tab is not None and str(tab.render()).strip() == "2 regio"

            def shown() -> set[str]:
                # footer keys (bindings with show=True in the chain)
                return {
                    k
                    for k, ab in app.screen.active_bindings.items()
                    if ab.binding.show
                }

            # skmap tab: the full keymap is shown
            assert {"R", "r", "a", "x", "1", "2"} <= shown()

            view = app._regio_view
            # '2' switches to the regio tab; start capturing
            await pilot.press("2")
            await pilot.pause()
            assert app.app.focused is view.ops
            await pilot.press("p")
            await pilot.pause()
            assert view.capture is True

            # regio tab footer: only 'c' (clear) and 'p' (capture) —
            # the skmap actions are disabled (and hidden), the tab
            # keys 1/2 keep working while staying out of the footer
            assert shown() == {"c", "p"}

            # 'c' clears the log of the *shown* tab: the regio log goes
            # empty while the assert log (skmap tab) is untouched
            await pilot.press("1")
            await pilot.pause()
            key = next(
                k
                for k, o in app._row_objs.items()
                if getattr(o, "name", "") == "V_RESET"
            )
            app.table.move_cursor(row=app._row_keys.index(key), column=0)
            await pilot.press("r")
            for _ in range(500):
                if view.ops.row_count:
                    break
                await pilot.pause()
            assert view.ops.row_count == 1
            await pilot.press("2")
            await pilot.pause()
            n_assert_lines = len(app._log_lines)
            assert n_assert_lines > 0
            await pilot.press("c")
            await pilot.pause()
            assert view.ops.row_count == 0
            assert len(app._log_lines) == n_assert_lines

            # the skmap keys are disabled on the regio tab: 'r' starts
            # no read (capture on, still no new op)
            await pilot.press("r")
            await pilot.pause()
            assert view.ops.row_count == 0

            # '1' switches back (hidden but working) and the keymap is
            # restored
            await pilot.press("1")
            await pilot.pause()
            assert app.tabs.active == "tab-registers"
            assert {"R", "r", "a", "x", "1", "2"} <= shown()

    _run(run())


def test_step_keys_hold_writes_each_value_once():
    """Holding '+' / '-' must not fire overlapping device operations:
    the step pump runs the queued steps one at a time — each write
    finishes (updating the cache) and the next step computes its value from
    that cache — so the device sees a strictly stepping series
    and the same value is never written twice in a row."""

    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test(size=(140, 36)) as pilot:
            await _wait_asserts(app, pilot)

            v_reset = next(
                o
                for o in app._row_objs.values()
                if getattr(o, "name", "") == "V_RESET"
            )
            key = next(k for k, o in app._row_objs.items() if o is v_reset)
            # (re)select the top module so the table rebuild from the
            # boot assert check has settled, then place the cursor
            await _select_node(app, _find_node(app, top), pilot)
            row = app._row_keys.index(key)
            app.table.focus()
            app.table.move_cursor(row=row, column=0)
            await pilot.pause()
            assert app._row_keys[app.table.cursor_row] == key

            # record every device write to the register's address
            writes: list[bytes] = []
            real_write = top._regio.dev_write

            async def spy_write(addr, data):
                if addr == v_reset.addr:
                    writes.append(bytes(data))
                return await real_write(addr, data)

            top._regio.dev_write = spy_write

            start = v_reset.read_uint_cached()
            # holding '+': four presses queue up (all land before the
            # first write can finish)
            await pilot.press("+", "+", "+", "+")
            for _ in range(1000):  # wait for the step queue to drain
                if not app._step_queue and not app._step_pumping:
                    break
                await pilot.pause()
            assert not app._step_queue and not app._step_pumping

            # exactly one write per press, in strictly incrementing
            # order: start+1 .. start+4, no value written twice in a row
            vals = [int.from_bytes(w[:4], "little") for w in writes]
            assert vals == [start + 1, start + 2, start + 3, start + 4]
            assert v_reset.read_uint_cached() == start + 4
            # V_RESET is a bits-kind register: the cell shows the hex
            # bit pattern, ceil_div(32, 4) = 8 digits
            assert _cell(app, row, VALUE) == f"0x{start + 4:08X}"

            # '-' steps down the same way
            await pilot.press("-", "-")
            for _ in range(1000):
                if not app._step_queue and not app._step_pumping:
                    break
                await pilot.pause()
            vals = [int.from_bytes(w[:4], "little") for w in writes[4:]]
            assert vals == [start + 3, start + 2]

    _run(run())


def test_v_check_printed_in_passed_color():
    """The printed v_check uses the Ass.passed color when the cached
    value passes the check, the assert color when it does not."""
    top = make_edit_top()
    lmt = next(r for r in top.arr_reg_var if r.name == "LMT")
    assert lmt.v_check is not None   # (v >= 2) && (v <= 100)

    # a passing value: the check string is printed in the passed color
    lmt.write_uint_cached(50)
    s = lmt.read_rich_str_cached()
    assert "(v >= 2) && (v <= 100)" in Text.from_markup(s).plain
    assert "[green]" in s

    # a failing value (written straight into the cache — write_uint_cached
    # would abort on the check): printed in the assert color, not green
    lmt.write_bytes_cached((0).to_bytes(lmt.size, "little"))
    s = lmt.read_rich_str_cached()
    assert "(v >= 2) && (v <= 100)" in Text.from_markup(s).plain
    assert "[green]" not in s


def test_step_increment_set_with_s_key():
    """'s' sets the '+' / '-' step increment via the value input line;
    the next step jumps by the new increment; esc / invalid input keep
    the current one."""

    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test(size=(140, 36)) as pilot:
            await _wait_asserts(app, pilot)
            v_reset = next(
                o
                for o in app._row_objs.values()
                if getattr(o, "name", "") == "V_RESET"
            )
            key = next(k for k, o in app._row_objs.items() if o is v_reset)
            await _select_node(app, _find_node(app, top), pilot)
            row = app._row_keys.index(key)
            app.table.focus()
            app.table.move_cursor(row=row, column=0)
            await pilot.pause()

            # record every device write to the register's address
            writes: list[bytes] = []
            real_write = top._regio.dev_write

            async def spy_write(addr, data):
                if addr == v_reset.addr:
                    writes.append(bytes(data))
                return await real_write(addr, data)

            top._regio.dev_write = spy_write

            assert app._step_value == 1

            # 's' opens the prompt in the value input line, prefilled
            # with the current increment; esc keeps it
            await pilot.press("s")
            await pilot.pause()
            assert app._step_prompt
            assert app.focused is app.value_input
            assert app.value_input.value == "1"
            await pilot.press("escape")
            await pilot.pause()
            assert not app._step_prompt
            assert app._step_value == 1

            # set an hex increment: one '+' step jumps by 0x10
            await pilot.press("s")
            app.value_input.value = "0x10"
            await pilot.press("enter")
            await pilot.pause()
            assert app._step_value == 16
            assert app.value_input.value == ""
            assert app.value_input.placeholder == SkmapUiApp._VALUE_PLACEHOLDER
            assert app.focused is app.table

            start = v_reset.read_uint_cached()
            await pilot.press("+")
            for _ in range(1000):  # wait for the step queue to drain
                if not app._step_queue and not app._step_pumping:
                    break
                await pilot.pause()
            assert [int.from_bytes(w[:4], "little") for w in writes] == [
                start + 16
            ]

            # a text that is not a number, and a number below one, are
            # rejected: the increment stays
            await pilot.press("s")
            app.value_input.value = "1e9"
            await pilot.press("enter")
            await pilot.pause()
            assert app._step_value == 16
            await pilot.press("s")
            app.value_input.value = "0"
            await pilot.press("enter")
            await pilot.pause()
            assert app._step_value == 16
            assert len(writes) == 1   # no further step went out

    _run(run())


def test_value_col_resize_refits_row_heights():
    """Resizing the value | description boundary re-measures the height
    of every row: a wide value that wrapped at the old width takes one
    line when the column is widened (and wraps again when narrowed)."""

    async def run():
        top = make_edit_top()
        app = SkmapUiApp(top)
        async with app.run_test(size=(200, 30)) as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            await pilot.pause()
            # BIG's 34-char hex value does not fit the default 22-wide
            # Value column: the auto-height row grew over lines
            assert app.table.get_row_height("r0") >= 2

            # wide enough for the whole value: the row must collapse back
            # to one line (the resize re-measures every auto-height row)
            app.table.set_value_col_width(40)
            await pilot.pause()
            assert app.table.value_col_width() == 40
            assert app.table.get_row_height("r0") == 1

            # narrow again: the value wraps over multiple lines
            app.table.set_value_col_width(8)
            await pilot.pause()
            assert app.table.get_row_height("r0") >= 3

            # the reset (double-click) re-fits too
            app.table.reset_value_col_width()
            await pilot.pause()
            assert app.table.get_row_height("r0") >= 2

    _run(run())


def test_write_does_not_read_back():
    """Writing a value must NOT issue a device read: the write already
    updates the skmap cache, so the shown value is refreshed straight
    from the cache (no read-back transaction on the regio)."""

    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test(size=(140, 36)) as pilot:
            await _wait_asserts(app, pilot)
            await _select_node(app, _find_node(app, top), pilot)
            await pilot.pause()

            v_reset = next(
                o
                for o in app._row_objs.values()
                if getattr(o, "name", "") == "V_RESET"
            )
            key = next(k for k, o in app._row_objs.items() if o is v_reset)
            row = app._row_keys.index(key)
            app.table.focus()
            app.table.move_cursor(row=row, column=0)
            await pilot.pause()

            # count every device read / write from here on
            reads: list[int] = []
            writes: list[int] = []
            real_read = top._regio.dev_read
            real_write = top._regio.dev_write

            async def spy_read(addr, size):
                reads.append(addr)
                return await real_read(addr, size)

            async def spy_write(addr, data):
                writes.append(addr)
                return await real_write(addr, data)

            top._regio.dev_read = spy_read
            top._regio.dev_write = spy_write

            # write a new value through the value input line
            await pilot.press("enter")          # open + focus the input
            await pilot.pause()
            reads.clear()                       # ignore any prefill read
            app.value_input.value = "0x1234"
            await pilot.press("enter")          # submit -> write

            for _ in range(500):                # wait for the write
                if v_reset.read_uint_cached() == 0x1234:
                    break
                await pilot.pause()
            assert v_reset.read_uint_cached() == 0x1234

            # the value really went to the device ...
            assert writes, "expected a device write"
            # ... and NOT one read was issued for it (no read-back)
            assert not reads, f"a write must not read back, got {reads}"

            # the shown cell is refreshed from the cache (no read needed)
            await _wait_cell(app, pilot, row, VALUE, "0x00001234")

    _run(run())
