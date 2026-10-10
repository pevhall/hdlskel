# regio_ui

**WARNING**: this part of the project is still in draft and was mostly
written by AI. It is supposed to be used for debugging purposes only —
use at own risk.

A [Textual](https://textual.textualize.io/) TUI that lives
**between a regio device and regio TCP clients**: it starts its own
regio TCP *server* (local listeners, for the clients to connect to)
and forwards every operation to a **backend** regio device — either
the real regio TCP server on another host/port (`-i` / `-p`) or a
regio **cache file** (`-f`, a `skelregio` file served directly, no
other server needed).  It **logs every operation** that flows
through, relays the responses back, and lets the user **send new
operations** and **re-send logged ones**.  The backend options are
shared with the regio CLI (`regio.cli_utils`).

```
 +----------+   regio TCP    +----------------------------+   regio TCP   +----------------+
 | client   | -------------> |              regio_ui      | ------------> | regio TCP      |
 | (tb,     | <-------------- |  TCP server <----> TCP     | <-------------- | server         |
 | skmap_ui) |   responses    |               client       |   responses    | (real device)  |
 +----------+                 +----------------------------+                +----------------+

 or, with a cache file instead of a TCP server:

 +----------+   regio TCP    +---------------------------+
 | client   | -------------> |         regio_ui          |
 | (tb,     | <-------------- |  TCP server <----> cache  |
 | skmap_ui) |   responses    |               file        |
 +----------+                 +---------------------------+
```

## Layout

| pane | content |
|------|---------|
| **operations log** (top) | one row per operation: `Time \| Address \| Op \| Data` — *Address* is hex, *Op* is `wr` / `rd`, *Data* is the payload as hex bytes, **up to `--max-data-bytes` per row (1024 by default)**, wrapped 16 bytes per line (a **read** shows its data once the upstream server replies — `…` while pending — a failed operation is marked with a red `⚠` warning) |
| **status line** | `listening on <host>:<port> · upstream <host>:<port> (connected) · N op(s)` (the TCP connection is (re)tried automatically every 2 s) or `… · file <path> · N op(s)` when serving a cache file |
| **operation form** (bottom) | the **Op** button toggles `wr` / `rd` (also the `t` key); *Address* (hex / bin / decimal), *Size* in bytes, *Write data* (only enabled for `wr`), **Send** button |

| key / action | effect |
|--------------|--------|
| `enter` / double click on a log row | **autofill the form** to match the operation (address, op, size and — for `wr` — the write data) so it can be edited and sent |
| `enter` in a form field / `Send` button | validate and send the operation (goes through the upstream connection and is logged like any other) |
| Op button / `t` | toggle the form's op between `wr` and `rd` (*Write data* is disabled for `rd`, *Size* becomes required) |
| `c` | clear the operations log |
| `q` | quit |

The log keeps the most recent 2000 operations (the oldest are
dropped).  The Data column shows up to `--max-data-bytes` bytes of a
payload (1024 by default — raise it to show more, e.g.
`--max-data-bytes 65535` for the full protocol maximum), wrapped 16
bytes per line; longer payloads are truncated with the total length
shown (`… (N B)`).

## The new-operation form

| field | `wr` | `rd` |
|-------|------|------|
| **Address** | required, `0 .. 0xFFFFFFFF` | required, `0 .. 0xFFFFFFFF` |
| **Size** (bytes) | **optional** — when omitted it is inferred from the write data (see below); when given it must hold the value (1 .. 65535) | **required** (1 .. 65535) |
| **Write data** | required, the value to write | not used (field disabled) |

**Write data** accepts the following types (decimal, `0x`-hex or
`0b`-binary): `0x0A0`, `0b0101`, `3243`.  When the size is not
provided it is calculated from the **number of digits** of the value:
one hex digit is half a byte (`0x0A0` -> 3 digits -> 2 B), one bin
digit is one bit (`0b0101` -> 4 bits -> 1 B), and a plain decimal is
assumed to be a 32-bit value (`3243` -> 4 B).  The value is sent
little-endian, zero-padded to the (inferred or given) size.

Selecting an operation in the log (the `enter` key or a double
click) fills the form with exactly that operation (the write data is
filled as hex, the size as the operation's byte width, so a
re-send is byte-identical) — every field can then be edited before
sending.

## Install

```bash
# sibling first (lives in this repo's pip/ dir)
pip install ../regio
pip install -e .
```

## Run

```bash
# backend = the real regio TCP server; the TUI listens on 0.0.0.0:0x9AB0
# for the clients (point them at it instead of the real server)
regio-ui -i <host> -p <port>

# e.g. real server on 192.168.0.9:0x9AB0, clients connect to 0x9AB1
regio-ui -i 192.168.0.9 -p 0x9AB0 --listen-port 0x9AB1

# backend = a regio cache file (no other server needed); the TUI
# serves the file's contents to the clients on 0x9AB0
regio-ui -f cache.skelregio
```

| flag | meaning |
|------|---------|
| `-f/--file` | serve this regio cache file (`skelregio`) instead of connecting to a TCP server |
| `-i/--host` | regio TCP server host (default `127.0.0.1`; ignored when `-f` is given) |
| `-p/--port` | regio TCP server port (default `0x9AB0`; ignored when `-f` is given) |
| `--debug-print-regio` | print all regio operations (debug logging) |
| `--listen-host` | host of the local (client-facing) regio TCP server (default `0.0.0.0`) |
| `--listen-port` | port of the local (client-facing) regio TCP server (default `0x9AB0`) |
| `--max-data-bytes` | maximum number of payload bytes shown in the Data column of each log row (default `1024`) |

Notes:

* With `-f`, reads are served from the file's contents and writes
  update the **in-memory** cache (the file itself is not modified —
  restart to reload it).  Reading data the cache does not hold is
  reported as an error response, like a device error.
* With `-i`/`-p`, the upstream server does not have to be running at
  start-up: the TUI keeps (re)connecting every 2 s and operations
  sent while it is away are logged with a `⚠` warning.
* `-f` takes precedence over `-i`/`-p` when both are given.

## Develop

```bash
pip install -e '.[dev]'
pytest            # headless end-to-end tests (fake upstream server)
textual run       # dev server
```
