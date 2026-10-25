"""A *tap* on a :class:`regio.Regio` device — regio_ui's embed path.

The :class:`~regio_ui.proxy.RegioProxy` sees operations because the
traffic flows through its own TCP server.  When regio_ui is embedded
in another app (the ``skmap_ui`` *Regio* tab) there is no proxy: the
app already owns a ``Regio`` device and its operations go directly to
the backend.

:class:`RegioTap` attaches to that device with regio's own hooks
(:meth:`Regio.add_pre_write_callback_func` /
:meth:`Regio.add_post_read_callback_func`), so every write / read the
host app performs is reported through the same ``on_op`` / ``on_done``
callbacks the :class:`~regio_ui.view.RegioUiView` expects — no extra
TCP hop, no re-routing of the host app's connection.

Operations sent from the view's form go through
:meth:`relay_write` / :meth:`relay_read` (the proxy's relay API); they
use the host app's device too and are reported by the tap like any
other operation (a failed send additionally surfaces the error to the
caller, which the tap's pre-write / post-read reports cannot do).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from regio import Regio

from regio_ui.proxy import RegioOp

__all__ = ["RegioTap"]

#: optional runner for relay operations: ``runner(coro) -> awaitable``
#: (skmap_ui passes its serialized device I/O so a form operation
#: cannot interleave with the host app's traffic on the connection)


class RegioTap:
    """Watch a ``Regio`` device and report its operations.

    ``on_op`` / ``on_done`` use the same signatures as the
    :class:`~regio_ui.proxy.RegioProxy` callbacks (see
    :mod:`regio_ui.proxy`), so the same
    :class:`~regio_ui.view.RegioUiView` can be fed by a proxy or by a
    tap.

    Tapped operations are complete when reported (regio's hooks fire
    when the operation is issued / has its data), so they are logged
    and immediately completed — no pending ``…`` read rows.
    """

    def __init__(
        self,
        regio: Regio,
        on_op: Optional[Callable[[RegioOp], str]] = None,
        on_done: Optional[
            Callable[[str, Optional[bytes], Optional[str]], None]
        ] = None,
        runner: Optional[Callable[[Awaitable], Awaitable]] = None,
    ) -> None:
        self._regio = regio
        self.on_op = on_op
        self.on_done = on_done
        # wraps relay operations (e.g. the host app's regio lock);
        # default: run the coroutine directly
        self._runner = runner or (lambda coro: coro)
        # attach regio's hooks (single-slot; a second tap would
        # replace this one — one view per device is the design)
        regio.add_pre_write_callback_func(self._tap_write)
        regio.add_post_read_callback_func(self._tap_read)

    @property
    def regio(self) -> Regio:
        return self._regio

    # ------------------------------------------------------------------
    # reporting (proxy callback protocol)
    # ------------------------------------------------------------------
    def _op_started(self, op: RegioOp) -> str:
        if self.on_op is not None:
            return self.on_op(op)
        return ""

    def _op_done(
        self, key: str, data: Optional[bytes], error: Optional[str]
    ) -> None:
        if error is not None and key:
            logging.warning("regio tap: %s", error)
        if self.on_done is not None and key:
            self.on_done(key, data, error)

    # ------------------------------------------------------------------
    # regio hooks: every operation flowing through the device
    # ------------------------------------------------------------------
    def _tap_write(self, addr: int, data: bytes) -> int:
        op = RegioOp(addr=addr, write=True, size=len(data), data=bytes(data))
        key = self._op_started(op)
        self._op_done(key, op.data, None)
        return 0

    def _tap_read(self, addr: int, data: bytes) -> int:
        data = bytes(data)
        op = RegioOp(addr=addr, write=False, size=len(data), data=data)
        key = self._op_started(op)
        self._op_done(key, data, None)
        return 0

    # ------------------------------------------------------------------
    # relay (the view's form): send through the tapped device
    # ------------------------------------------------------------------
    async def relay_write(
        self, addr: int, data: bytes
    ) -> tuple[str, Optional[str]]:
        """Forward a write to the tapped device (the tap logs it).

        Returns (row key, error or None) like
        :meth:`RegioProxy.relay_write` (the key is empty: the row is
        added by the write hook, not here)."""
        try:
            await self._runner(self._regio.write(addr, data))
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001 — never crash the UI
            msg = f"0x{addr:x} wr {len(data)} B: {err}"
            logging.warning("regio tap: %s", msg)
            return "", msg
        return "", None

    async def relay_read(
        self, addr: int, size: int
    ) -> tuple[str, bytes, Optional[str]]:
        """Forward a read to the tapped device (the tap logs it).

        Returns (row key, payload, error) like
        :meth:`RegioProxy.relay_read` (the key is empty: the row is
        added by the read hook, not here)."""
        try:
            payload = await self._runner(self._regio.read(addr, size))
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001 — never crash the UI
            msg = f"0x{addr:x} rd {size} B: {err}"
            logging.warning("regio tap: %s", msg)
            return "", b"", msg
        return "", payload, None
