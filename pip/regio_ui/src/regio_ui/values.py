"""Parsing of the numbers the user types into the form fields.

Every numeric field (Address, Size, Write Data) accepts the same
grammar: ``0x``-prefixed hex, ``0b``-prefixed binary, or plain
decimal (leading zeros allowed), case-insensitive prefixes.

The *inferred size* (in bytes) of a write-data value is derived from
the **number of digits** the user typed:

* ``0x…``: one hex digit is 4 bits -> ``ceil(hex digits / 2)`` bytes
* ``0b…``: one bin digit is 1 bit  -> ``ceil(bin digits / 8)`` bytes
* decimal: assumed to be a 32-bit value -> **4 bytes**

e.g. ``0x0A0`` -> 2 B, ``0b0101`` -> 1 B, ``3243`` -> 4 B.  A size
given explicitly by the user always wins over the inferred one.
"""

from __future__ import annotations

import re

_HEX_RE = re.compile(r"^0[xX][0-9a-fA-F]+$")
_BIN_RE = re.compile(r"^0[bB][01]+$")
_DEC_RE = re.compile(r"^[0-9]+$")

__all__ = ["parse_num"]


def parse_num(text: str) -> tuple[int, int] | None:
    """Parse ``text`` (hex / bin / decimal) into ``(value, size_bytes)``.

    ``size_bytes`` is the *inferred* byte width (see module
    docstring); callers that only need a number (address, size) may
    ignore it.  Returns ``None`` when the text is not a valid number
    of one of the three accepted types (empty, ``0x`` / ``0b``
    without digits, unknown characters, negatives, ...).
    """
    s = text.strip()
    if _HEX_RE.match(s):
        digits = s[2:]
        # 4 bits per hex digit -> ceil(digits / 2) bytes (min 1)
        return int(s, 16), max((len(digits) + 1) // 2, 1)
    if _BIN_RE.match(s):
        digits = s[2:]
        # 1 bit per bin digit -> ceil(digits / 8) bytes (min 1)
        return int(s, 2), max((len(digits) + 7) // 8, 1)
    if _DEC_RE.match(s):
        return int(s), 4
    return None
