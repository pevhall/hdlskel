# skmap_ui

A debug user interface for the SkMap protocol.

**WARNING**: this part of the project is still in draft and this part was mostly wirrten by AI. It is supposed to be used for debugging purposes only use at own risk.

A [Textual](https://textual.textualize.io/) TUI for browsing
[skmap](https://github.com/pevhall/hdlskel) register maps.

Pass a real `skmap.Module` (e.g. built with `make_module`) and the app shows:

| view | content |
|------|---------|
| **left tree** | the module tree — top module (as the tree root), kids + external memories, laid out like `Module.print_tree_cached` |
| **right table** | the register map of the selected module — `Addr | T | Acc | Name | Value | Description` (mirrors `Module.print_reg_map_cached` / `RegMapTable`), flags expanded as sub-rows |
| **bottom log** | the triggered register assets (asserts) as a **timestamped table** (like `print_table_reg_list(list_reg, title='Asserts')`) — refreshed by `make_tree()` + `Module.check_assert_tree_cached()` |

Uses skmap's native vocabulary: `Acc` codes `na/k/ro/rc/rw/wt` in the *Acc*
column, and skmap's notion of a **trigger** (register write).

## Layout & controls

The three panes are resizable by **dragging a divider with the mouse**
(between tree/table, and between workspace/log). The tree starts
**fully expanded**, and the tree node of the module whose register map is
currently displayed is **highlighted** (bold bright blue).

| key | action |
|-----|--------|
| `enter` | tree: open the register map of the node under the cursor; table: **edit** the value of the row under the cursor (see below) |
| `left` / `right` | collapse / expand the tree node under the cursor (`space` toggles too) |
| `t` | *trigger* the selected table row: writable regs (`rw`/`wt`) and flags are **written** (random value); `ro`/`rc` regs, flags and external mems are **read from the device**; `k`/`na` are never read (hardwired / no access); the *Value* cell is refreshed from the device |
| `a` | re-run `make_tree()` + `check_assert_tree_cached()` and redraw the assert log |
| `l` | cycle the **assert level** (debug → info → warn → error → fatal): asserts below the level are no longer logged (see *Assert log*) |
| `r` | cycle the **refresh period** (off → 1 → 5 → 30 s): every period the app calls `Module.read_all_tree()` and re-checks the asserts (see *Assert log*) |
| `x` | **clear triggered**: write zero to every triggered `rc` register (skmap's `Module.clear_assert_tree()`), re-read from the device, re-check (see *Assert log*) |
| `c` | clear the log view (the next assert check redraws it) |

On start the top module is selected (its register map is shown right away)
and the assert check runs automatically.

### Editing register values

Pressing `enter` on a register-map row edits its value in the input bar
between the workspace and the log:

| row's `Acc` | `enter` does |
|------|--------|
| `rw` / `wt` | focuses the input bar; type the new value (decimal or `0x`-hex, vector regs take comma-separated lanes or one value for all lanes) and `enter` writes it to the **device** via `Reg.write_uint` / `RegVec.write_list_uint`; `escape` cancels |
| `rc` | **clears** the register immediately (writes zero to the device) |
| `ro` | nothing (read-only; use `t` to read it from the device) |
| `k` / `na` | nothing — the value is hardwired / has no access, so it is never read back |

Flag and external-mem rows cannot be edited from the input bar (use `t`
to toggle a flag). Device errors are reported on stderr (Python
`logging`), never in the log view.

## Assert log

The bottom log is a **snapshot, not a stream**: on every assert check it
is cleared and redrawn as

1. a header line with a **time stamp** and the current options:  
   `2026-08-30 05:54:04.519  asserts level >= debug  —  3 triggered, worst: error`, and
2. a table (same columns as the register map: `Addr | T | Acc | Name |
   Value | Description`) with one row per **triggered** assert — the same
   assets/rows as `print_table_reg_list(list_reg, title='Asserts')`.

The log view's border shows the current options, e.g.
`asserts (level >= debug)  ·  refresh: 5 s` (or `refresh: off`).

The three options:

| option | CLI | key | effect |
|--------|-----|-----|--------|
| assert level | `--asserts-level {debug,info,warn,error,fatal}` (default `debug`) | `l` | asserts below the level still count for the *worst* level, but are **not** listed in the log table |
| refresh period | `--refresh SECS` (default `0` = off) | `r` (cycles off/1/5/30) | every period the app calls `Module.read_all_tree()` (all registers of the whole tree, including external mem caches, are **read from the device**) and re-checks the asserts — the log and the *Value* cells of the displayed table update automatically |
| clear triggered | — | `x` | write zero to every triggered `rc` register via `Module.clear_assert_tree()`, then re-read the tree from the device and re-check |

`make_tree()` is only re-run by `a` (it loads uninitalised kids); the
periodic refresh and `x` work on the already-built tree, so they never
block on an unreadable module.

## Device I/O

All register / flag / external-mem device accesses use skmap's **async
*non-cached* regio reads and writes** (never `*_cached`), so the value
really goes to / comes from the regio — a live TCP server, a simulation,
or a cache file — and skmap's cache is refreshed as a side effect. Each
operation runs in a Textual worker **on the app's event loop** (asyncio
sockets require it), serialized by a lock so the single regio
connection never sees concurrent requests. After every write the app
performs a device **read-back**, so the *Value* cell always shows the
true device state. Assets with `Acc.k` (hardwired) or `Acc.na` (no
access) are never read back: reading them is redundant (or would fault
the firmware).

## Install

```bash
# siblings first (they live in this repo's pip/ dir)
pip install ../regio ../skmap
pip install -e .
```

## Run the demo

The console script builds a small, self-contained demo SoC (a real
`skmap.Module` tree backed by an in-memory fake `Regio`, see
`src/skmap_ui/demo.py`) and opens the TUI:

```bash
skmap-ui          # console script
python -m skmap_ui
```

The demo tree:

```
DEMO_TOP @ 0x40000000
├── 📔 DMEM @ 0x50000000 (external mem, rw, 1024 B)
├── DEMO_SYSCTRL @ 0x40001000
│   ├── STATUS (ro, error assert set → triggers)
│   ├── CTRL   (rw)
│   └── DEMO_UART @ 0x40001100
│       ├── K_BAUD (k)
│       └── RSR    (rc, info assert, not set)
└── DEMO_PMU @ 0x40002000
    └── V_EVENT (rc, info assert set → triggers)
```

plus `K_ID` (k), `V_RESET` (rw) and `FLAGS` (rw flag reg, `f0` warn assert
set → triggers) on the top module itself. On start the log view shows the
three triggered asserts (worst level `error`).

## Use a real module (file or TCP)

The CLI can build the top module from a **skelregi cache file** (via the
`regio` package) or a **live TCP regio**:

```bash
skmap-ui -f tree.skmap -m test_skmap_tree_module.py       # cache file
skmap-ui -i <host> -p <port> -a 0x40000000 -m module.py  # live TCP
```

| flag | meaning |
|------|---------|
| `-f/--file` | build the module from a skelregi cache file (writes are applied to the in-memory cache) |
| `-i/--host`, `-p/--port` | connect to a live regio over TCP |
| `-a/--addr` | module regio address (default `0`, decimal or `0x`-prefixed) |
| `-m/--module-file` | generated skmap module `.py` to import first (its `skmap.register_Module` calls make the head IDs known) |
| `--asserts-level` | initial assert level (see *Assert log*); cycle at runtime with `l` |
| `--refresh` | initial refresh period in seconds, `0` = off (see *Assert log*); cycle at runtime with `r` |
| `--smoke` | headless: start, wait for the assert check, print the result and exit |

With neither `-f` nor `-i`, the built-in demo is used. `regio`'s
`--debug-print-regio` flag is also available.

### Example: `src/skmap_ui/test_skmap_tree_file.sh`

`src/skmap_ui/` contains symlinks `tree.skmap` and
`test_skmap_tree_module.py` into a generated `tb/` directory; the script
runs the TUI against the cache file:

```bash
cd src/skmap_ui
bash test_skmap_tree_file.sh            # interactive TUI on the tree.skmap cache
bash test_skmap_tree_file.sh --smoke    # headless: prints e.g. "smoke OK: ... worst=passed asserts=0"
```

### Example: live simulation (`src/skmap_ui/test_skmap_tree_sim.sh`)

The script starts the cocotb testbench
(`fw/tb/skmap/tb_py_skmap_tree/run.py -s`), which simulates the module
with nvc and serves it over regio TCP, waits until the server port
accepts connections, then runs the TUI against the live server:

```bash
cd src/skmap_ui
bash test_skmap_tree_sim.sh     # Ctrl+Q quits and kills the simulation
```

Every trigger / edit then does real regio I/O against the simulation.
The server location can be overridden with `HOST` / `PORT` env vars.
Module build and TUI run happen in a single asyncio loop
(`App.run_async()`), so the regio TCP connection created while building
the module stays alive inside the TUI event loop.

## Use your own module (programmatically)

```python
import asyncio
from skmap import make_module
from skmap_ui import SkmapUiApp

async def main():
    # any skmap Regio implementation (see the skmap package)
    regio = ...
    module = await make_module(regio, 0x40000000)
    app = SkmapUiApp(module, asserts_level=Ass.debug, refresh=5.0)
    await app.run_async()    # same event loop as the regio connection

asyncio.run(main())
```

Notes:

- Build the module and run the app in **one asyncio loop**
  (`await app.run_async()`): the regio TCP client is asyncio-based, so a
  connection created while building the module must keep living inside
  the TUI event loop.
- Trigger / edit actions use the non-cached async regio I/O (see
  *Device I/O*), so device accesses never block the UI thread.
- Modules that fail to load (unknown ID) are shown in the tree as
  *Uninitalised module* and asserts of the loaded modules are still checked.

## Develop

```bash
pip install -e '.[dev]'
pytest            # headless smoke tests (no pytest-asyncio needed)
textual run       # dev server
```
