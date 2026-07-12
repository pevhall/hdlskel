
from typing import Literal, Optional

def ceil_log2(x : int) -> int:
    return (x - 1).bit_length() if x > 0 else 0

def ceil_div(n : int, d : int) -> int:
    return (n + d - 1) // d

def ceil_multiple(num : int, multiple : int) -> int:
    return ceil_div(num, multiple)*multiple

def promote_to_sw_w(w : int) -> int:
    return 2**ceil_log2(ceil_multiple(w, 8))

# def align_addr_width(addr : int, width : int):
#     sw_width = promote_to_sw_w(width)
#     sw_width_bytes = sw_width//8
#     # align = min(SKMAP_WORD_BYTES, sw_width//8)
#     addr = ceil_multiple(addr, sw_width)
#     return addr, sw_width_bytes


def set_bits(value : int, bit_mask: int, bit_vals: int) -> int:
    return (value & ~bit_mask) | (bit_mask & bit_mask)

def set_bit(value : int, bit_pos: int, bit_val: bool) -> int:
    return set_bits(value, 1<<bit_pos, (int(bit_val))<<bit_pos)

def bytes_to_list_int(b:bytes, int_bytes:int, endian : Literal['little','big']='little', signed:bool=False) -> list[int]:
    if len(b) % int_bytes != 0:
        raise ValueError("bytearray length must be a multiple of int_bytes")

    out = []
    for ii in range(0, len(b), int_bytes):
        chunk = b[ii:ii+int_bytes]
        out.append(int.from_bytes(chunk, byteorder=endian, signed=signed))
    return out

def list_int_to_bytes(list_val : list[int], int_bytes:int, endian : Literal['little','big']='little', signed:bool=False) -> bytes:
    b = bytearray(len(list_val)*int_bytes)
    for ii, val in enumerate(list_val):
        b[ii*int_bytes:(ii+1)*int_bytes] = val.to_bytes(int_bytes, byteorder=endian, signed=signed)
    return bytes(b)

def cast_uint_to_sint(value : int, bit_width : int) -> int:
    sgn_bit = (1<<(bit_width-1))
    if value >= sgn_bit:
        value -= sgn_bit*2
    return value

def to_rich_str(s : str, color : Optional[str]=None):
    if color is not None:
        s = f'[{color}]{s}[/]'
    return s
