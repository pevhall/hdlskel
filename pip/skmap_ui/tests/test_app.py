"""Headless smoke tests for the skmap_ui TUI (Textual 8.x, no plugins).

Each test wraps an ``async`` runner in ``asyncio.run`` (pytest-asyncio is
not a dependency).  The TUI is exercised against the real ``skmap`` demo
module from :mod:`skmap_ui.demo`.
"""

import asyncio
import itertools
import re

from skmap import Ass, Head, RFlag, Reg
from skmap import register_Module
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
    _u32,
)
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
            assert _cell(app, 5, VALUE).strip() == "(Mem size:1024 B)"

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
    async def run():
        top = make_demo()
        app = SkmapUiApp(top)
        async with app.run_test() as pilot:
            await _wait_asserts(app, pilot)
            mem = top.arr_external_mem[0]
            await _select_node(app, _find_node(app, mem), pilot)

            assert app.table.row_count == 1
            assert _cell(app, 0, NAME) == "DMEM"
            assert _cell(app, 0, ACC) == "rw"
            assert "DMEM" in app.table.border_title
            assert app._row_module is None

            app.table.move_cursor(row=0, column=0)
            app.action_trigger_selected()
            # the cell shows the first bytes read from the (fake) device
            for _ in range(500):
                if _cell(app, 0, VALUE).strip().startswith("(Mem "):
                    break
                await pilot.pause()
            assert _cell(app, 0, VALUE).strip().startswith("(Mem ")

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

            await pilot.press(*"0x2f")
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
            await pilot.press(*"0x100000000")
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
        def __init__(self, width, vec_len=None):
            self.width = width
            self.vec_len = vec_len

    class _RegStub:
        def __init__(self, width, vec_len=None):
            self.value_type = _VT(width, vec_len)

    parse = SkmapUiApp._parse_value

    # scalar: decimal or 0x-hex, in range [0, 2**width)
    r32 = _RegStub(32)
    assert parse(r32, "255") == 255
    assert parse(r32, "0x2f") == 0x2F
    assert parse(r32, " 0xff ") == 0xFF
    assert parse(r32, "0x0") == 0
    assert parse(r32, "0x100000000") is None  # too big
    assert parse(r32, "-1") is None
    assert parse(r32, "zz") is None
    assert parse(r32, "") is None

    # vector: comma-separated lanes; one value repeats over all lanes
    v8 = _RegStub(8, vec_len=4)
    assert parse(v8, "1,2,3,4") == [1, 2, 3, 4]
    assert parse(v8, "0x5") == [5, 5, 5, 5]
    assert parse(v8, "1,2") is None  # wrong lane count
    assert parse(v8, "256,2,3,4") is None  # lane out of range


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
