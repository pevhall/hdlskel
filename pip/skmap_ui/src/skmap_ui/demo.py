"""Self-contained demo SoC built from real ``skmap`` classes.

Builds a small, fully functional ``skmap.Module`` tree on top of an
in-memory fake ``Regio`` (no hardware or SoC image needed)::

    DEMO_TOP @ 0x40000000
    +-- DMEM  (external mem, rw, 1024 B) @ 0x50000000
    +-- DEMO_SYSCTRL @ 0x40001000
    |   +-- DEMO_UART @ 0x40001100
    +-- DEMO_PMU @ 0x40002000

``make_demo_module()`` returns a *fresh* top module on each call (register
cache starts with the values below), so it is safe to use from both the
``skmap-ui`` console script and the test suite.  Three asserts are set to
trigger out of the box, so the log view has something to show:

- ``DEMO_TOP.FLAGS.f0`` is set    -> ``Ass.warn``
- ``DEMO_SYSCTRL.STATUS`` is set  -> ``Ass.error``
- ``DEMO_PMU.V_EVENT`` is set     -> ``Ass.info``
"""

from __future__ import annotations

from skmap import (
    Acc,
    Ass,
    Head,
    Module,
    Reg,
    RegFlags,
    RegK,
    RFlag,
    Regio,
    register_Module,
)
from skmap.basic_types import (
    SKMAP_VER_MAJOR,
    SKMAP_VER_MINOR,
    SKMAP_VER_PATCH,
    SKMAP_VER_STR,
    value_type_u8,
    value_type_x32,
)
from skmap.head import SYNC

# ---------------------------------------------------------------------------
# in-memory fake Regio
# ---------------------------------------------------------------------------


class MemRegio(Regio):
    """Tiny in-memory Regio.

    ``write_mem()`` maps flat byte blocks at fixed addresses; reads of
    unmapped bytes return 0.  Enough for a demo / test, no hardware.
    """

    def __init__(self) -> None:
        super().__init__()
        self._mem: dict[int, bytearray] = {}
        self.n_writes = 0

    def write_mem(self, addr: int, data: bytes) -> None:
        self._mem[addr] = bytearray(data)

    async def dev_read(self, addr: int, size: int) -> bytes:
        out = bytearray()
        for a in range(addr, addr + size):
            v = 0
            for base, block in self._mem.items():
                if base <= a < base + len(block):
                    v = block[a - base]
                    break
            out.append(v)
        return bytes(out)

    async def dev_write(self, addr: int, data: bytes) -> None:
        self.n_writes += 1
        for base, block in self._mem.items():
            if base <= addr and addr + len(data) <= base + len(block):
                block[addr - base : addr - base + len(data)] = data
                return
        # write into unmapped space: create a new block
        self._mem[addr] = bytearray(data)


# ---------------------------------------------------------------------------
# module byte builders (mirror the skmap module data layout)
# ---------------------------------------------------------------------------


def _u32(v: int) -> bytes:
    return v.to_bytes(4, "little")


def _head_bytes(
    mid: str,
    version: int,
    checksum: int,
    len_kids: int,
    len_sub: int,
    len_k: int,
    len_var: int,
) -> bytes:
    idb = mid.encode().ljust(8, b"\x00")[:8]
    return (
        idb
        + bytes([SYNC, version, checksum & 0xFF, (checksum >> 8) & 0xFF])
        + bytes([len_kids, len_sub, len_k, len_var])
    )


def _mem_sub(base_addr: int, size: int, acc: Acc) -> bytes:
    """One EXTERNAL_MEM sub entry (3 words)."""
    return bytes([0x3B, acc.value, 0, 0]) + _u32(base_addr) + _u32(size)


# addresses of the demo modules
_TOP_ADDR = 0x40000000
_SYSCTRL_ADDR = 0x40001000
_UART_ADDR = 0x40001100
_PMU_ADDR = 0x40002000
_DMEM_ADDR = 0x50000000

# DEMO_TOP: 2 kids, 1 external mem, 1 k-reg, 2 var regs (V_RESET + FLAGS)
_TOP_DATA = (
    _head_bytes("DEMO_TOP", 1, 0x1234, len_kids=2, len_sub=3, len_k=1, len_var=2)
    + _u32(_SYSCTRL_ADDR)
    + _u32(_PMU_ADDR)
    + _mem_sub(_DMEM_ADDR, 1024, Acc.rw)
    + _u32(0xDEAD0001)  # K_ID
    + _u32(5)  # V_RESET (rw)
    + bytes([0b01])  # FLAGS (rw): f0 (warn) set, f1 (none) clear
    + b"\x00" * 3  # pad to 2 words
)

# DEMO_SYSCTRL: 1 kid (UART), 2 var regs (STATUS ro/error + CTRL rw)
# (head ID field is 8 bytes -> id "DEMO_SYS", display name "DEMO_SYSCTRL")
_SYSCTRL_DATA = (
    _head_bytes("DEMO_SYS", 1, 0x5678, len_kids=1, len_sub=0, len_k=0, len_var=2)
    + _u32(_UART_ADDR)
    + _u32(1)  # STATUS (ro, Ass.error): set -> triggers error
    + _u32(0)  # CTRL (rw)
)

# DEMO_UART: 1 k-reg (K_BAUD), 1 var reg (RSR rc/info)
_UART_DATA = (
    _head_bytes("DEMOUART", 1, 0x9ABC, len_kids=0, len_sub=0, len_k=1, len_var=1)
    + _u32(115200)  # K_BAUD (k)
    + _u32(0)  # RSR (rc, Ass.info): clear
)

# DEMO_PMU: 1 var reg (V_EVENT rc/info, set -> triggers info)
_PMU_DATA = (
    _head_bytes("DEMO_PMU", 1, 0x4242, len_kids=0, len_sub=0, len_k=0, len_var=1)
    + _u32(1)  # V_EVENT (rc, Ass.info): set -> triggers info
)


# ---------------------------------------------------------------------------
# demo module classes
# ---------------------------------------------------------------------------


class _DemoModule(Module):
    """Shared boilerplate for the demo module classes."""

    mid: str = ""  # 8-byte ID stored in the head (display name may be longer)

    @classmethod
    def id(cls) -> str:
        assert len(cls.mid) <= 8
        return cls.mid

    @classmethod
    def version(cls) -> int:
        return 1

    @classmethod
    def skmap_ver_major(cls) -> int:
        return SKMAP_VER_MAJOR

    @classmethod
    def skmap_ver_minor(cls) -> int:
        return SKMAP_VER_MINOR

    @classmethod
    def skmap_ver_patch(cls) -> int:
        return SKMAP_VER_PATCH

    @classmethod
    def skmap_ver_str(cls) -> str:
        return SKMAP_VER_STR

    def _init_external_mem(self) -> None:
        pass


class DemoTop(_DemoModule):
    mid = "DEMO_TOP"

    @classmethod
    def name(cls) -> str:
        return "DEMO_TOP"

    @classmethod
    def checksum(cls) -> int:
        return 0x1234

    def _init_reg_map_k(self) -> None:
        self._add_reg_k(
            RegK(self, "K_ID", value_type_x32, desc="identity constant")
        )

    def _init_reg_map_var(self) -> None:
        self._add_reg_var(
            Reg(self, "V_RESET", value_type_x32, acc=Acc.rw, desc="reset controller")
        )
        self._add_reg_var(
            RegFlags(
                self,
                "FLAGS",
                width=8,
                flags=[
                    RFlag("f0", 0, Ass.warn, "warning flag"),
                    RFlag("f1", 1, Ass.none, "misc flag"),
                ],
                acc=Acc.rw,
                desc="status flags",
            )
        )

    def _init_external_mem(self) -> None:
        self.arr_external_mem[0].details(
            "DMEM", value_type_u8, Acc.rw, "demo data memory"
        )


class DemoSysctrl(_DemoModule):
    mid = "DEMO_SYS"

    @classmethod
    def name(cls) -> str:
        return "DEMO_SYSCTRL"

    @classmethod
    def checksum(cls) -> int:
        return 0x5678

    def _init_reg_map_k(self) -> None:
        pass

    def _init_reg_map_var(self) -> None:
        self._add_reg_var(
            Reg(
                self,
                "STATUS",
                value_type_x32,
                acc=Acc.ro,
                desc="system status",
                ass=Ass.error,
            )
        )
        self._add_reg_var(
            Reg(self, "CTRL", value_type_x32, acc=Acc.rw, desc="system control")
        )


class DemoUart(_DemoModule):
    mid = "DEMOUART"

    @classmethod
    def name(cls) -> str:
        return "DEMO_UART"

    @classmethod
    def checksum(cls) -> int:
        return 0x9ABC

    def _init_reg_map_k(self) -> None:
        self._add_reg_k(
            RegK(self, "K_BAUD", value_type_x32, desc="baud rate (k=115200)")
        )

    def _init_reg_map_var(self) -> None:
        self._add_reg_var(
            Reg(
                self,
                "RSR",
                value_type_x32,
                acc=Acc.rc,
                desc="receive status",
                ass=Ass.info,
            )
        )


class DemoPmu(_DemoModule):
    mid = "DEMO_PMU"

    @classmethod
    def name(cls) -> str:
        return "DEMO_PMU"

    @classmethod
    def checksum(cls) -> int:
        return 0x4242

    def _init_reg_map_k(self) -> None:
        pass

    def _init_reg_map_var(self) -> None:
        self._add_reg_var(
            Reg(
                self,
                "V_EVENT",
                value_type_x32,
                acc=Acc.rc,
                desc="event counter",
                ass=Ass.info,
            )
        )


# ---------------------------------------------------------------------------
# factory
# ---------------------------------------------------------------------------

_registered = False


def _ensure_registered() -> None:
    """Register the demo module classes with the skmap factory (once)."""
    global _registered
    if _registered:
        return
    for cls in (DemoTop, DemoSysctrl, DemoUart, DemoPmu):
        register_Module(cls)
    _registered = True


def make_demo_module() -> Module:
    """Return a fresh ``DEMO_TOP`` module backed by an in-memory Regio.

    The top module is constructed directly; its kids are created by
    ``await top.make_tree()`` (as the TUI does), so uninitialised kids
    can be observed in the tree before that completes.
    """
    _ensure_registered()
    regio = MemRegio()
    regio.write_mem(_TOP_ADDR, _TOP_DATA)
    regio.write_mem(_SYSCTRL_ADDR, _SYSCTRL_DATA)
    regio.write_mem(_UART_ADDR, _UART_DATA)
    regio.write_mem(_PMU_ADDR, _PMU_DATA)
    return DemoTop(regio, _TOP_ADDR, Head(_TOP_DATA), bytearray(_TOP_DATA))
