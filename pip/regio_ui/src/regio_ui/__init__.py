"""regio_ui — textual TUI proxy for the regio TCP protocol.

regio_ui lives **between** a regio TCP server and a regio TCP client:

* it starts a regio TCP **server** (``--listen-host`` /
  ``--listen-port``, default ``0.0.0.0:0x9AB0``) that regio clients
  connect to,
* it starts a regio TCP **client** that connects to the real
  (upstream) regio TCP server (``-i/--host`` / ``-p/--port``),
* it **logs** every operation that flows through (``Time | Address |
  Op | Data``) and **forwards** it, relaying the responses back,
* the user can **send new operations** from the form (address, wr /
  rd toggle, optional size, write data in hex / bin / decimal) and
  **select a logged operation** to autofill (and re-send) it.

Run the TUI::

    regio-ui -i <upstream host> -p <upstream port> [--listen-port N]
    python -m regio_ui

Or programmatically::

    import asyncio
    from regio.tcp_client import RegioTcpClient
    from regio_ui import RegioUiApp

    async def run():
        backend = RegioTcpClient(host="127.0.0.1", port=0x9AB0)
        await backend.connect()
        app = RegioUiApp(
            backend,
            "127.0.0.1:0x9AB0",
            listen_host="0.0.0.0",
            listen_port=0x9AB1,
        )
        await app.run_async()

    asyncio.run(run())

The UI is also reusable as a plain widget (:class:`RegioUiView`) so
another Textual app can host it as a tab — a host that already owns a
``regio.Regio`` device feeds the view with :class:`RegioTap` (this is
how ``skmap_ui`` embeds regio_ui on its *regio* tab).

The log **capture** can be toggled at runtime (``p`` key) and started
on or off (``--no-capture`` / ``RegioUiView(capture=...)``): while off
operations pass by without being logged.
"""

__version__ = "0.2.0"

from regio_ui.app import RegioUiApp, main
from regio_ui.tap import RegioTap
from regio_ui.view import RegioUiView

__all__ = [
    "RegioUiApp",
    "RegioUiView",
    "RegioTap",
    "main",
    "__version__",
]
