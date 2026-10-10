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

    from regio_ui import RegioUiApp

    app = RegioUiApp(
        upstream_host="127.0.0.1",
        upstream_port=0x9AB0,
        listen_host="0.0.0.0",
        listen_port=0x9AB1,
    )
    app.run()
"""

__version__ = "0.1.0"

from regio_ui.app import RegioUiApp, main

__all__ = ["RegioUiApp", "main", "__version__"]
