#!/usr/bin/env python3
"""Headless regio_ui proxy: a multi-client regio TCP server in front of one upstream regio TCP server.

The simulation's regio server (``regio.tcp_server_single``) accepts only
a single client, but a plot (``skmap_ui_plot_regs``) and a TUI
(``skmap_ui``) both want to talk to the same module. This proxy is the
network layer of ``regio_ui`` (its ``RegioProxy``, which is based on the
multi-client server from ``regio.tcp_server_async_multi``) without the
textual TUI:

    python3 regio_proxy_headless.py -p 39600 --listen-port 39601

This script lives in the regio project (``pip/regio/src``) and requires
the ``regio_ui`` package for ``RegioProxy``.

Every operation still flows through the same relay code regio_ui uses,
only nothing is displayed (add ``--debug-print-regio`` to log every
operation on stdout instead).
"""

import argparse
import asyncio
import logging

from regio.tcp_client import RegioTcpClient
from regio_ui.proxy import RegioProxy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog='regio_proxy_headless',
        description=__doc__.splitlines()[0],
    )
    parser.add_argument(
        '-i', '--host', default='127.0.0.1',
        help='upstream (device side) regio TCP server host (default: 127.0.0.1)')
    parser.add_argument(
        '-p', '--port', type=lambda s: int(s, 0), required=True,
        help='upstream (device side) regio TCP server port')
    parser.add_argument(
        '--listen-host', default='0.0.0.0',
        help='host of the local (client-facing) server (default: 0.0.0.0)')
    parser.add_argument(
        '--listen-port', type=lambda s: int(s, 0), required=True,
        help='port of the local (client-facing) server')
    parser.add_argument(
        '--debug-print-regio', action='store_true',
        help='print every relayed regio operation')
    return parser.parse_args()


async def run_proxy(host : str, port : int, listen_host : str, listen_port : int,
                    print_regio : bool = False) -> None:
    """Serve listen_host:listen_port, relayed to host:port, until cancelled."""
    backend = RegioTcpClient(host=host, port=port)
    if print_regio:
        backend.log_regio = True
    proxy = RegioProxy(backend, f'{host}:{port}',
                       listen_host=listen_host, listen_port=listen_port)
    logging.info('proxy %s:%s -> %s:%s', listen_host, listen_port, host, port)
    # the two tasks of regio_ui.RegioProxy: the client-facing server and the
    # (re)connection of the upstream, exactly as the TUI starts them
    tasks = (asyncio.create_task(proxy.start_local_server()),
             asyncio.create_task(proxy.watch_upstream()))
    try:
        await asyncio.gather(*tasks)
    finally:
        await proxy.close()


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(run_proxy(args.host, args.port, args.listen_host,
                              args.listen_port, args.debug_print_regio))
    except OSError as err:
        raise SystemExit(f'regio_proxy_headless: {err}')


if __name__ == '__main__':
    main()
