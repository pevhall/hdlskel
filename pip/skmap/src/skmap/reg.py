import ast
from typing import Optional, Type, Literal, Union, Callable, TYPE_CHECKING

from .basic_types import Acc, Ass, ValueKind, ValueType, VType, value_kind_to_v_type, value_type_u8, value_type_x32
from .basic import ceil_log2, ceil_div, ceil_multiple, promote_to_sw_w, bytes_to_list_int, list_int_to_bytes, cast_uint_to_sint, to_rich_str, set_bit, set_bits

if TYPE_CHECKING:
    from .module import Module

def round_half_away(value : Union[int, float]) -> int:
    """Round half away from zero, used to turn a float value into a register value."""
    if isinstance(value, int):
        return value
    return int((value + 0.5)//1) if value >= 0 else -int((-value + 0.5)//1)

class ValueCheck:
    """A recipe `v_check` option: a boolean function of the register value.

    It is the value limit of a register (it replaces the old `min` / `max`
    options), for a vector register it applies to every element. A value that
    fails the check raises when written (the write is not allowed) and is
    reported as an assert when reading / printing the register.

    The recipe v_check="{ (v % RW_MULT) == 0}" generates
    `skmap.ValueCheck(lambda v: ((v % 2) == 0), '(v % 2) == 0')` (and the
    matching `ValueCheck{...}` of the c++ library, see reg.hpp). The text has
    every name resolved to its value so the check prints the same in every
    language and does not need the recipe at runtime.

    Args:
        fn : takes the register value, True when the value is allowed
        str : expression text with resolved values, for printing and errors
        v_type : type of the value, 'f' is a float (see the recipe v_type)
    """
    def __init__(self, fn : Callable[[Union[int, float]], bool], str : str = '', v_type : VType = VType.s):
        self.fn = fn
        self._str = str
        self.v_type = v_type

    def __call__(self, value : Union[int, float]) -> bool:
        return bool(self.fn(value))

    def __str__(self) -> str:
        return self._str

class ValueConvert:
    """A recipe `v_convert` option: converts a user value to a register value.

    A register stores an integer, `v_convert` maps the value the user of the
    module works with into that integer, eg v_convert="{ v * 16 }" for a Q4
    fixed point temperature. Reading uses the *inverse* of the same expression
    (derived while parsing the recipe, see invert_resolvable), so writing 1.5
    stores 24 and reading gives 1.5 back.

      * `fn`     user value -> register value, a float result is rounded
      * `fn_inv` register value -> user value, what a read returns

    Args:
        fn, fn_inv : the conversion and its inverse
        str, str_inv : their text (names resolved to values), for printing
        v_type : type of the user value (see the recipe v_type)
    """
    def __init__(self, fn : Callable[[Union[int, float]], Union[int, float]], fn_inv : Callable[[int], Union[int, float]],
                 str : str = '', str_inv : str = '', v_type : VType = VType.s):
        self.fn = fn
        self.fn_inv = fn_inv
        self._str = str
        self._str_inv = str_inv
        self.v_type = v_type

    def to_raw(self, value : Union[int, float]) -> int:
        """User value as the value stored in the register (always an int)."""
        return round_half_away(self.fn(value))

    def from_raw(self, raw : int) -> Union[int, float]:
        """Value stored in the register as the user value."""
        return self.fn_inv(raw)

    def __call__(self, value : Union[int, float]) -> int:
        return self.to_raw(value)

    @property
    def str_inv(self) -> str:
        return self._str_inv

    def __str__(self) -> str:
        return self._str

class Reg:
    def __init__(self, module : "Module", name : str, value_type : ValueType, acc : Acc, desc : str, ass : Ass = Ass.none,
                 v_check : Optional[ValueCheck] = None, v_convert : Optional[ValueConvert] = None, v_type : Optional[VType] = None):
        # assert (ass != ass.passed)
        self.module = module
        self.name   = name
        self.value_type  = value_type
        self.acc    = acc
        self.desc   = desc
        self.size   = promote_to_sw_w(value_type.width)>>3
        self.elem_size = self.size
        self.addr : Optional[int]  = None
        self.ass    = ass
        assert v_check is None or value_type.kind in (ValueKind.uint, ValueKind.sint, ValueKind.bits), \
            f'a v_check is only supported on int registers ({name})'
        assert v_convert is None or value_type.kind in (ValueKind.uint, ValueKind.sint, ValueKind.bits), \
            f'a v_convert is only supported on int registers ({name})'
        self.v_check = v_check
        self.v_convert = v_convert
        self.v_type = v_type if v_type is not None else value_kind_to_v_type(value_type.kind)

    @property
    def is_flag(self) -> bool:
        return False

    @property
    def is_reg(self) -> bool:
       return True

    def has_ass(self) -> bool:
        return self.ass != Ass.none or self.has_limit()

    @property
    def has_v_convert(self) -> bool:
        return self.v_convert is not None

    def v_convert_marker(self) -> str:
        """`= { v * 16 } ` text of the `v_convert` of the register, '' when it
        has none.

        Printed at the start of the description in the reg map, where the value
        of the register and the value of the module user are shown next to each
        other. The text is the recipe source with every recipe name resolved to
        its value. See RegMapTable and the c++ print_reg_map.
        """
        if self.v_convert is None:
            return ''
        conv = str(self.v_convert)      # resolved, eg '(v * 16)'
        if len(conv) > 2 and conv[0] in '({' and conv[-1] in '})':
            conv = conv[1:-1].strip()
        return f'={{ {conv} }} '

    def value_type_str(self) -> str:
        return f'{self.value_type}'

    def read_bytes_cached(self) -> bytes:
        assert isinstance(self.addr, int)
        return self.module.read_cached(self.addr, self.size)

    async def read_bytes(self) -> bytes:
        if self.acc != Acc.k:
            assert isinstance(self.addr, int)
            return await self.module.read_bytes(self.addr, self.size)
        return self.read_bytes_cached()

    async def read_cache(self) -> None:
        _ = await self.read_bytes()

    def read_uint_cached(self) -> int:
        b = self.read_bytes_cached()
        value_int = int.from_bytes(b, byteorder='little')
        if self.value_type.width != (self.size*8):
            mask = (1<<self.value_type.width)-1
            value_int &= mask
        return value_int

    async def read_uint(self) -> int:
        _ = await self.read_bytes()
        return self.read_uint_cached()

    def read_sint_cached(self) -> int:
        value_int = self.read_uint_cached()
        return cast_uint_to_sint(value_int, self.value_type.width)

    async def read_sint(self) -> int:
        _ = await self.read_bytes()
        return self.read_sint_cached()

    def read_bool_cached(self) -> bool:
        return self.read_uint_cached() != 0

    async def read_bool(self) -> bool: 
        _ = await self.read_bytes()
        return self.read_bool_cached()

    def read_char_cached(self) -> str:
        assert self.value_type.width == 8
        value_uint = self.read_uint_cached()
        return chr(value_uint)

    async def read_char(self) -> str:
        _ = await self.read_bytes()
        return self.read_char_cached()

    def read_value_cached(self):
        match self.value_type.kind:
            case ValueKind.uint:
                return self.read_uint_cached()
            case ValueKind.sint:
                return self.read_sint_cached()
            case ValueKind.bits:
                return self.read_uint_cached()
            case ValueKind.flag:
                return self.read_uint_cached()
            case ValueKind.char:
                return self.read_char_cached()

    def ass_check_cached(self, log_ass : Ass = Ass.none, log_f : list[Union["RFlag","Reg"]] = []) -> Ass:
        if self.has_limit():
            ass = self.ass_check_limit_cached()
        elif self.ass == Ass.none:
            return Ass.none
        else:
            value = self.read_bool_cached()
            ass = self.ass if value else Ass.passed
        if log_ass != Ass.none and ass >= log_ass:
            log_f.append(self)
        return ass

    async def ass_check(self, log_ass : Ass = Ass.none, log_f : list[Union["RFlag","Reg"]] = []) -> Ass:
        if self.ass == Ass.none:
            return Ass.none
        _ = await self.read_bytes()
        return self.ass_check_cached(log_ass, log_f)

    def ass_check_value_limit(self, value : Union[int, float]) -> Ass:
        """Ass of a (user) value against the recipe `v_check`, none when it passes."""
        if self.v_check is None:
            return Ass.none
        if self.v_check(value):
            return Ass.none
        if self.ass != Ass.none:
            return self.ass
        return Ass.error

    def check_value_limit(self, value : Union[int, float]):
        """Raise when a (user) value does not pass the recipe `v_check`."""
        ass = self.ass_check_value_limit(value)
        if (ass >= Ass.error):
            raise ValueError(f"for reg {self.name} {value=} does not pass the check '{self.v_check}'")

    def check_value_fits_reg(self, value : int):
        """Raise when a register value does not fit the width of the register.

        A `v_convert` result is not bounded by the conversion, so the value that
        goes into the register is checked here.
        """
        value_int = int(value)
        width = self.value_type.width
        if self.value_type.kind == ValueKind.sint:
            lo, hi = -(1<<(width-1)), (1<<(width-1))-1
        else:
            lo, hi = 0, (1<<width)-1
        if not lo <= value_int <= hi:
            conv = f' (converted from {value} with v_convert {self.v_convert})' if self.has_v_convert else ''
            raise ValueError(f'for reg {self.name} register value {value_int} does not fit '
                             f'{self.value_type_str()} [{lo} , {hi}]{conv}')

    def to_raw(self, value : Union[int, float]) -> int:
        """User value as the value stored in the register (identity without a conversion)."""
        return self.v_convert.to_raw(value) if self.has_v_convert else value

    def from_raw(self, raw : int) -> Union[int, float]:
        """Value stored in the register as the user value (identity without a conversion)."""
        return self.v_convert.from_raw(raw) if self.has_v_convert else raw

    def has_limit(self):
        # A `v_check` is the value limit of a register, it is printed and
        # asserted (flags have their own assert per flag).
        return self.value_type.kind in (ValueKind.uint, ValueKind.sint, ValueKind.bits) and \
            self.v_check is not None

    def ass_check_limit_cached(self) -> Ass:
        return self.ass_check_value_limit(self.read_converted_cached())

    def _str_num(self, value : int, base : Literal[2, 10, 16]) -> str:
        match (base):
            case 2:  return f'0b{value:0{self.value_type.width}b}'
            case 10: return str(value)
            case 16: return f'0x{value:0{ceil_div(self.value_type.width,4)}X}'

    def _v_check_bound_str(self, v_color : str) -> str:
        """The `v_check` printed as its expression, names resolved to values.

        Coloured with the assert of the value, which includes this check.
        """
        return f"{to_rich_str(str(self.v_check), v_color)} "

    def read_rich_str_cached(self) -> str:
        value_str = None
        value_int = None
        base = 10
        match self.value_type.kind:
            case ValueKind.uint:
                value_int = self.read_uint_cached()
            case ValueKind.sint:
                value_int = self.read_sint_cached()
            case ValueKind.bits:
                value_int = self.read_uint_cached()
                base = 16
            case ValueKind.flag:
                if self.value_type.is_bool:
                    value_str = str(self.read_bool_cached())
                else:
                    value_str = self._str_num(self.read_uint_cached(), 2)
                    # f'0b{self.read_uint_cached():0{self.value_type.width}b}'
            case ValueKind.char:
                value_str = self.read_char_cached()

        s = ''
        ass = Ass.none
        if self.ass != Ass.none:
            ass = self.ass_check_cached()
            s += to_rich_str(str(self.ass), ass.color)+": "
        if self.has_limit():
            ass = max(ass, self.ass_check_limit_cached())
            s += self._v_check_bound_str(ass.color)
        if self.has_v_convert:
            # The user value is printed, the raw register value is available
            # through the `*_raw` functions
            value_str = str(self.read_converted_cached())
        if value_str is None:
            assert value_int is not None
            value_str = self._str_num(value_int, base)
        s += to_rich_str(value_str, ass.color)
        return s

    async def write_cache(self):
        assert isinstance(self.addr, int)
        b = self.read_bytes_cached();
        assert self.acc in (Acc.rw, Acc.wt) or (self.acc == Acc.rc and not any(b))
        await self.module.write_bytes(self.addr, b)

    def write_bytes_cached(self, b : bytes):
        assert isinstance(self.addr, int)
        assert self.acc in (Acc.rw, Acc.wt) or (self.acc == Acc.rc and not any(b))
        assert len(b) == self.size
        # assert len(b) <= self.size
        # assert len(b) >= ceil_div(self.value_type.width, 8)
        return self.module.write_bytes_cached(self.addr, b)

    async def write_bytes(self, b : bytes):
        self.write_bytes_cached(b)
        await self.write_cache()

    def write_uint_cached(self, v : int):
        # v is the value stored in the register, the v_check is checked against
        # the user value it stands for (see write_converted_cached)
        self.check_value_fits_reg(v)
        self.check_value_limit(self.from_raw(v))
        b = v.to_bytes(self.size, byteorder='little', signed=False)
        return self.write_bytes_cached(b)

    async def write_uint(self, v : int):
        self.write_uint_cached(v)
        await self.write_cache()

    def write_sint_cached(self, v : int):
        self.check_value_fits_reg(v)
        self.check_value_limit(self.from_raw(v))
        b = v.to_bytes(self.size, byteorder='little', signed=True)
        return self.write_bytes_cached(b)

    async def write_sint(self, v : int):
        self.write_sint_cached(v)
        await self.write_cache()

    def read_converted_cached(self):
        """Value of the register as the user of the module sees it.

        Without a `v_convert` this is the value of the register itself, with one
        it is the register value converted by the inverse of `v_convert`.
        """
        return self.from_raw(self.read_value_cached())

    async def read_converted(self):
        _ = await self.read_bytes()
        return self.read_converted_cached()

    def write_converted_cached(self, value : Union[int, float]):
        """Write a user value: `v_check` it, convert it with `v_convert` and write it.

        Raises when the value does not pass the check, or when the converted
        value does not fit the register.
        """
        self.check_value_limit(value)
        value_raw = self.to_raw(value)
        self.check_value_fits_reg(value_raw)
        match self.value_type.kind:
            case ValueKind.sint:
                self.write_sint_cached(value_raw)
            case ValueKind.uint | ValueKind.bits | ValueKind.flag:
                self.write_uint_cached(value_raw)
            case _:
                assert False, f'a v_convert is not supported on {self.value_type_str()} registers ({self.name})'

    async def write_converted(self, value : Union[int, float]):
        self.write_converted_cached(value)
        await self.write_cache()

    def write_bool_cached(self, v : bool):
        return self.write_uint_cached(int(v))

    async def write_bool(self, v : bool):
        self.write_bool_cached(v)
        await self.write_cache()

    def write_zero_cached(self):
        return self.write_uint_cached(0)

    async def write_zero(self):
        self.write_zero_cached()
        await self.write_cache()

class RegVec(Reg):

    def __init__(self,  *args, **kwargs):
        super().__init__(*args, **kwargs)
        assert isinstance(self.value_type.vec_len, int)
        self.elem_offset = self.module._byte_aligment_from_val_width(self.size*8);
        self.size = self.elem_offset * self.value_type.vec_len

    def _bytes_to_list_uint(self, b:bytes) -> list[int]:
        value_vec_int = bytes_to_list_int(b, self.elem_offset)
        # elem_size is in bytes, value_type.width in bits
        if self.elem_size*8 != self.value_type.width:
            mask = (1<<self.value_type.width)-1
            for ii in range(len(value_vec_int)):
                value_vec_int[ii] &= mask
        return value_vec_int

    def _bytes_to_list_sint(self, b:bytes) -> list[int]:
        value_vec_int = self._bytes_to_list_uint(b)
        for ii in range(len(value_vec_int)):
            value_vec_int[ii] = cast_uint_to_sint(value_vec_int[ii], self.value_type.width)
        return value_vec_int

    def _bytes_to_list_bool(self, b:bytes) -> list[bool]:
        value_vec_int = self._bytes_to_list_uint(b)
        return [bool(a) for a in value_vec_int]

    def read_list_uint_cached(self) -> list[int]:
        b = self.read_bytes_cached()
        return self._bytes_to_list_uint(b)

    async def read_list_uint(self) -> list[int]:
        _ = await self.read_bytes()
        return self.read_list_uint_cached()

    def read_list_sint_cached(self) -> list[int]:
        b = self.read_bytes_cached()
        return self._bytes_to_list_sint(b)

    async def read_list_sint(self) -> list[int]:
        _ = await self.read_bytes()
        return self.read_list_sint_cached()

    def read_list_bool_cached(self) -> list[bool]:
        b = self.read_bytes_cached()
        return self._bytes_to_list_bool(b)

    async def read_list_bool(self) -> list[bool]:
        b = await self.read_bytes()
        return self._bytes_to_list_bool(b)

    def _idx_elem_offset(self, idx) -> int:
        assert isinstance(self.addr, int)
        return self.addr + idx*self.elem_offset

    def read_idx_bytes_cached(self, idx : int) -> bytes:
        return self.module.read_cached(self._idx_elem_offset(idx), self.elem_size)

    async def read_idx_bytes(self, idx : int) -> bytes:
        if self.acc != Acc.k:
            _ =  await self.module.read_bytes(self._idx_elem_offset(idx), self.elem_size)
        return self.read_idx_bytes_cached(idx)

    async def write_idx_cache(self, idx : int):
        b = self.read_idx_bytes_cached(idx)
        await self.module.write_bytes(self._idx_elem_offset(idx), b)

    def write_idx_bytes_cached(self, idx : int, b : bytes):
        # assert len(b) <= self.elem_size
        # assert len(b) >= ceil_div(self.value_type.width, 8)
        assert self.acc in (Acc.rw, Acc.wt) or (self.acc == Acc.rc and not any(b))
        assert(len(b) == self.elem_size)
        self.module.write_bytes_cached(self._idx_elem_offset(idx), b)

    async def write_idx_bytes(self, idx : int, b : bytes):
        self.write_idx_bytes_cached(idx, b)
        await self.write_idx_cache(idx)

    def read_idx_uint_cached(self, idx : int) -> int:
        b = self.read_idx_bytes_cached(idx)
        value_int = int.from_bytes(b, byteorder='little')
        # Mask to the value width, an element can be wider than the value
        # (e.g. 12 bit values in 2 byte elements, 8 bit chars in 4 byte
        # elements). read_idx_sint_cached() sign extends from this value.
        return value_int & ((1 << self.value_type.width) - 1)

    async def read_idx_uint(self, idx : int) -> int:
        _ = await self.read_idx_bytes(idx)
        return self.read_idx_uint_cached(idx)

    def read_idx_sint_cached(self, idx : int) -> int:
        value_int = self.read_idx_uint_cached(idx)
        return cast_uint_to_sint(value_int, self.value_type.width)

    async def read_idx_sint(self, idx : int) -> int:
        _ = await self.read_idx_bytes(idx)
        return self.read_idx_sint_cached(idx)

    def read_idx_bool_cached(self, idx : int) -> bool:
        return self.read_idx_uint_cached(idx) != 0

    async def read_idx_bool(self, idx : int) -> bool:
        return await self.read_idx_uint(idx) != 0

    def read_idx_char_cached(self, idx : int) -> str:
        assert self.value_type.width == 8
        value_uint = self.read_idx_uint_cached(idx)
        return chr(value_uint)

    def read_idx_value_cached(self, idx : int):
        match self.value_type.kind:
            case ValueKind.uint: return self.read_idx_uint_cached(idx)
            case ValueKind.sint: return self.read_idx_sint_cached(idx)
            case ValueKind.bits: return self.read_idx_uint_cached(idx)
            case ValueKind.flag:
                assert self.value_type.is_bool
                # A single flag, read_idx_value_cached() must return the same
                # type (int/bool) as every other kind, not the whole vector.
                return self.read_idx_bool_cached(idx)
            case ValueKind.char: return self.read_idx_char_cached(idx)

    def write_idx_uint_cached(self, idx : int, val : int):
        # val is the value stored in this element of the register
        self.check_value_fits_reg(val)
        self.check_value_limit(self.from_raw(val))
        b = val.to_bytes(self.elem_size, byteorder='little', signed=False)
        self.write_idx_bytes_cached(idx, b)

    async def write_idx_uint(self, idx : int, val : int):
        self.write_idx_uint_cached(idx, val)
        await self.write_idx_cache(idx)

    def write_idx_sint_cached(self, idx : int, val : int):
        self.check_value_fits_reg(val)
        self.check_value_limit(self.from_raw(val))
        b = val.to_bytes(self.elem_size, byteorder='little', signed=True)
        self.write_idx_bytes_cached(idx, b)

    async def write_idx_sint(self, idx : int, val : int):
        self.write_idx_sint_cached(idx, val)
        await self.write_idx_cache(idx)

    def read_converted_idx_cached(self, idx : int):
        """One element as the user of the module sees it (see v_convert)."""
        return self.from_raw(self.read_idx_value_cached(idx))

    async def read_converted_idx(self, idx : int):
        _ = await self.read_idx_bytes(idx)
        return self.read_converted_idx_cached(idx)

    def write_converted_idx_cached(self, idx : int, value : Union[int, float]):
        """Write one element with the user value (v_check, then v_convert)."""
        self.check_value_limit(value)
        value_raw = self.to_raw(value)
        self.check_value_fits_reg(value_raw)
        match self.value_type.kind:
            case ValueKind.sint:
                self.write_idx_sint_cached(idx, value_raw)
            case ValueKind.uint | ValueKind.bits | ValueKind.flag:
                self.write_idx_uint_cached(idx, value_raw)
            case _:
                assert False, f'a v_convert is not supported on {self.value_type_str()} registers ({self.name})'

    async def write_converted_idx(self, idx : int, value : Union[int, float]):
        self.write_converted_idx_cached(idx, value)
        await self.write_idx_cache(idx)

    def read_str_cached(self)  -> str:
        # Every element holds one char, only the low byte of each element is
        # used (mirrors RegVec::read_str_cached in the C++ library). This also
        # works for 8 bit char vectors, which the previous element size check
        # rejected.
        b = self.read_bytes_cached()
        assert self.value_type.vec_len is not None
        return ''.join(chr(b[ii*self.elem_offset]) for ii in range(self.value_type.vec_len))

    async def read_str(self)  -> str:
        _ = await self.read_bytes()
        return self.read_str_cached()

    def _list_int_to_bytes(self, value : list[int], signed : bool) -> bytes:
        # Every element lives in an aligned element of elem_offset bytes (the
        # value itself is elem_size bytes), mirroring
        # RegVec::write_vec_uint_cached in the C++ library. Packing the values
        # without the padding (list_int_to_bytes) did not match how the values
        # are read back with bytes_to_list_int(b, elem_offset).
        b = bytearray(self.size)
        for ii, v in enumerate(value):
            off = ii*self.elem_offset
            b[off:off+self.elem_size] = v.to_bytes(self.elem_size, byteorder='little', signed=signed)
        return bytes(b)

    def check_value_list(self, value : list[int]):
        # The v_check applies to every element of a vector register
        for v in value:
            self.check_value_limit(v)

    def read_converted_cached(self) -> list[Union[int, float]]:
        """All elements as the user of the module sees them (see v_convert)."""
        return [self.from_raw(v) for v in self._read_list_raw_cached()]

    async def read_converted(self) -> list[Union[int, float]]:
        _ = await self.read_bytes()
        return self.read_converted_cached()

    def _read_list_raw_cached(self) -> list[int]:
        match self.value_type.kind:
            case ValueKind.sint:  return self.read_list_sint_cached()
            case ValueKind.uint:  return self.read_list_uint_cached()
            case ValueKind.bits:  return self.read_list_uint_cached()
            case ValueKind.flag:  return [int(v) for v in self.read_list_bool_cached()]
            case _: assert False, f'{self.value_type_str()} registers have no int value list ({self.name})'

    def write_converted_cached(self, value : list[Union[int, float]]):
        """Write all elements with the user values (v_check, then v_convert)."""
        assert isinstance(self.value_type.vec_len, int)
        assert len(value) == self.value_type.vec_len, \
            f'{self.name} expects {self.value_type.vec_len} values, got {len(value)}'
        value_raw = []
        for v in value:
            self.check_value_limit(v)
            v_raw = self.to_raw(v)
            self.check_value_fits_reg(v_raw)
            value_raw.append(v_raw)
        match self.value_type.kind:
            case ValueKind.sint:
                self.write_list_sint_cached(value_raw)
            case ValueKind.uint | ValueKind.bits:
                self.write_list_uint_cached(value_raw)
            case _:
                assert False, f'a v_convert is not supported on {self.value_type_str()} registers ({self.name})'

    async def write_converted(self, value : list[Union[int, float]]):
        self.write_converted_cached(value)
        await self.write_cache()

    def write_list_uint_cached(self, value : list[int]):
        self.check_value_list([self.from_raw(v) for v in value])
        for v in value:
            self.check_value_fits_reg(v)
        b = self._list_int_to_bytes(value, signed=False)
        self.write_bytes_cached(b)

    async def write_list_uint(self, value : list[int]):
        self.write_list_uint_cached(value)
        await self.write_cache()

    def write_list_sint_cached(self, value : list[int]):
        self.check_value_list([self.from_raw(v) for v in value])
        for v in value:
            self.check_value_fits_reg(v)
        b = self._list_int_to_bytes(value, signed=True)
        self.write_bytes_cached(b)

    async def write_list_sint(self, value : list[int]):
        self.write_list_sint_cached(value)
        await self.write_cache()

    def ass_check_limit_cached(self) -> Ass:
        ass = Ass.none
        assert isinstance(self.value_type.vec_len, int)
        for idx in range(self.value_type.vec_len):
            v_ass = self.ass_check_value_limit(self.read_converted_idx_cached(idx))
            if ass < v_ass:
                ass = v_ass
        return ass

    def ass_check_cached(self, log_ass : Ass = Ass.none, log_f : list[Union["RFlag",Reg]] = []) -> Ass:
        if self.has_limit():
            ass =  self.ass_check_limit_cached()
        elif self.ass == Ass.none:
            return Ass.none
        else:
            value = max(self.read_list_bool_cached())
            ass = self.ass if value else Ass.passed
        if log_ass != Ass.none and ass >= log_ass:
            log_f.append(self)
        return ass

    async def ass_check(self, log_ass : Ass = Ass.none, log_f : list[Union["RFlag",Reg]] = []) -> Ass:
        _ = await self.read_bytes()
        return self.ass_check_cached(log_ass, log_f)

    def ass_check_cached_idx(self, idx : int, log_ass : Ass = Ass.none, log_f : list[Union["RFlag",Reg]] = []) -> Ass:
        if self.has_limit():
            ass = self.ass_check_value_limit(self.read_converted_idx_cached(idx))
        elif self.ass == Ass.none:
            return Ass.none
        else:
            value = self.read_idx_bool_cached(idx)
            ass = self.ass if value else Ass.passed
        # Log on the assert of the checked flag, not on the register default
        if log_ass != Ass.none and ass >= log_ass:
            log_f.append(self)
        return ass

    async def ass_check_idx(self, idx : int, log_ass : Ass = Ass.none, log_f : list[Union["RFlag",Reg]] = []) -> Ass:
        _ = await self.read_idx_bytes(idx)
        return self.ass_check_cached_idx(idx, log_ass, log_f)

    def read_rich_str_cached(self) -> str:
        base = 10
        match self.value_type.kind:
            case ValueKind.uint:
                value = self.read_list_uint_cached()
            case ValueKind.sint:
                value = self.read_list_sint_cached()
            case ValueKind.bits:
                value = self.read_list_uint_cached()
                base = 16
            case ValueKind.flag:
                assert self.value_type.is_bool
                value = self.read_list_bool_cached()
            case ValueKind.char:
                value = self.read_str_cached()
        # assert self.fmt == Fmt.hex
        ass = Ass.none
        s = ''
        if self.ass != Ass.none:
            ass_checked = self.ass_check_cached()
            s += to_rich_str(f'{self.ass}', ass_checked.color)+": "
        if self.has_limit():
            ass = max(ass, self.ass_check_limit_cached())
            s += self._v_check_bound_str(ass.color)
        if self.has_v_convert:
            # The user values are printed, the raw values are available through
            # the `*_raw` functions
            value = self.read_converted_cached()
        s += "[ "
        for idx, v in enumerate(value):
            ass = self.ass_check_cached_idx(idx)
            if isinstance(v, int):
                v_str = self._str_num(v, base)
            else:
                v_str= str(v)
            s +=to_rich_str(v_str, ass.color)
            if idx != len(value)-1:
                s += ", "
        s += " ]"
        return s

class RegK(Reg):
    # the acc of a constant is 'k', it is not a parameter here: because Reg
    # takes the acc before the description, pass the desc as a keyword
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, acc = Acc.k) #, ass = Ass.none)

    async def read_int(self)  -> int:
        return self.read_uint_cached()

class RegVecK(RegVec):
    # like RegK: the acc is 'k', pass the desc as a keyword
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, acc = Acc.k) #, ass = Ass.none)

    async def read_int(self)  -> int:
        return self.read_uint_cached()

class RFlag:
    def __init__(self, name : str, bit : int, ass : Ass, desc : str, vec_len:Optional[int]=None):
        self.name = name
        self.bit  = bit
        self.ass  = ass
        self.desc = desc
        self.vec_len = vec_len

    @property
    def is_flag(self) -> bool:
        return True

    @property
    def is_reg(self) -> bool:
       return False

    def assign(self, reg_flags : 'RegFlags'):
        self.reg_flags = reg_flags

    def _ass_check(self, v : Union[list[bool], bool]) -> Ass:
        if self.ass == Ass.none:
            return Ass.none
        if isinstance(v, (list, tuple)):
            v = any(v)
        if not v:
            return Ass.passed
        return self.ass

    def _value_rich_str(self):
        if self.vec_len is None:
            v = self.read_bool_cached()
            ass_checked = self._ass_check(v)
            if self.ass == Ass.none:
                return f'{v}'
            return to_rich_str(f'{self.ass}: {v}', ass_checked.color)

        lv = self.read_list_bool_cached()
        ass_checked = self._ass_check(lv)
        s = ''
        if self.ass != Ass.none:
           s += to_rich_str(f'{self.ass}: ', ass_checked.color) 
        s += '0b'
        for v in lv[::-1]:
            
            if ass_checked <= Ass.passed or v:
                a = ass_checked
            else:
                a = Ass.passed
            v = str(int(v))
            s += to_rich_str(v, a.color) 
        return s

    def read_bool_cached(self) -> bool:
        assert self.vec_len is None or self.vec_len == 1
        return (self.reg_flags.read_uint_cached() & (1<<self.bit)) != 0

    async def read_bool(self) -> bool:
        _ = await self.reg_flags.read_bytes()
        return self.read_bool_cached()
        # assert self.vec_len is None or self.vec_len == 1
        # return (await self.reg_flags.read_uint() & (1<<self.bit)) != 0

    def write_bool_cached(self, v : bool):
        b = bytearray(self.reg_flags.read_bytes_cached())
        ii_byte = self.bit // 8
        ii_bit  = self.bit  % 8
        b[ii_byte] = set_bit(int(b[ii_byte]), ii_bit, v)
        # print(f'b[{ii_byte}] = {b[ii_byte]}')
        self.reg_flags.write_bytes_cached(bytes(b))

    async def write_bool(self, v : bool):
        self.write_bool_cached(v)
        await self.reg_flags.write_cache()

    def read_list_bool_cached(self) -> list[bool]:
        assert self.vec_len is not None
        value_list_bool = []
        value_uint =  self.reg_flags.read_uint_cached()
        for ii in range(self.vec_len):
            value_list_bool.append(value_uint & (1<<(self.bit+ii)) != 0)
        return value_list_bool

    async def read_list_bool(self) -> list[bool]:
        await self.reg_flags.read_cache()
        return self.read_list_bool_cached()

    def write_list_bool_cached(self, value : list[bool]):
        assert self.vec_len is not None
        assert len(value) == self.vec_len
        wr_uint : int = 0
        for ii, b in enumerate(value):
            wr_uint |= int(b)<<(self.bit+ii)
        wr_mask = ((1<<(self.vec_len))-1)<<self.bit
        rd_uint =  self.reg_flags.read_uint_cached()
        wr_uint = set_bits(rd_uint, wr_mask, wr_uint)
        self.reg_flags.write_uint_cached(wr_uint)

    async def write_list_bool(self, v : list[bool]):
        self.write_list_bool_cached(v)
        await self.reg_flags.write_cache()

    async def ass_check(self) -> Ass:
        return self._ass_check(await self.read_bool())

    def ass_check_cached(self) -> Ass:
        return self._ass_check(self.read_bool_cached())

    # def add_to_table(self, table):
    #     table.add_row('-', 'b',  f'{self.bit}',  self.name, self._value_rich_str(), self.desc)

class RFlagK(RFlag):

    def __init__(self,  *args, **kwargs):
        super().__init__(*args, **kwargs)

class RegFlags(Reg):

    def __init__(self, *args, width : int, flags: list[RFlag], **kwargs):
        # assert 'value_type' not in kwargs
        # kwargs['value_type'] = ValueType(kind=ValueKind.flag, width=width)
        super().__init__(*args, value_type=ValueType(kind=ValueKind.flag, width=width), **kwargs) #, ass = Ass.none)
        self.flags = flags
        self.bit_flags = {}
        self.name_flags = {}
        for f in flags:
            f.assign(self)
            self.bit_flags[f.bit] = f
            self.name_flags[f.name] = f

    # def add_to_table(self, table):
    #     Reg.add_to_table(self, table)
    #     # value_int = self.read_uint_cached()
    #     for f in self.flags:
    #         # b = f.bit
    #         # v = bool((value_int >> b) & 1)
    #         table.add_row('-', 'b',  f'{f.bit}',  f.name, f._value_rich_str(), f.desc)

        # table.add_row(str(self.addr), self.value_type_str(),  str(self.acc),  self.name, self.read_rich_str_cached(), self.desc)

    def ass_check_cached(self, log_ass : Ass = Ass.none, log_f : list[Union[RFlag,Reg]] = []) -> Ass:
        result = Ass.none
        value_int = self.read_uint_cached()
        # print(f'{value_int=}')
        for f in self.flags:
            v = bool((value_int >> f.bit) & 1)
            ass = f._ass_check(v)
            if log_ass != Ass.none and ass >= log_ass:
                log_f.append(f)
            if ass > result:
                result = ass
        return result

    def has_ass(self) -> bool:
        for f in self.flags:
            # RFlag.ass defaults to Ass.none (not None), so comparing against
            # None is always true
            if f.ass != Ass.none:
                return True
        return False

    async def ass_check(self, log_ass : Ass = Ass.none, log_f : list[Union[RFlag,Reg]] = []) -> Ass:
        await self.read_cache()
        return self.ass_check_cached(log_ass, log_f)

class RegFlagsK(RegFlags):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, acc = Acc.k, **kwargs) #, ass = Ass.none)

