import ast
from typing import Optional, Type, Literal, Union, TYPE_CHECKING

from .basic_types import Acc, Ass, ValueKind, ValueType, value_type_u8, value_type_x32
from .basic import ceil_log2, ceil_div, ceil_multiple, promote_to_sw_w, bytes_to_list_int, list_int_to_bytes, cast_uint_to_sint, to_rich_str, set_bit, set_bits

if TYPE_CHECKING:
    from module import Module

class Reg:
    def __init__(self, module : "Module", name : str, value_type : ValueType, acc : Acc, desc : str, ass : Ass = Ass.none, max : Optional[int] = None, min : Optional[int] = None): #, fmt : Fmt = Fmt.default): #, ass : Ass = Ass.none):
        # assert (ass != ass.passed)
        self.module = module
        self.name   = name
        self.value_type  = value_type
        self.acc    = acc
        # self.ass    = ass
        self.desc   = desc
        # self.fmt    = fmt
        self.size   = promote_to_sw_w(value_type.width)>>3
        self.elem_size = self.size
        self.addr : Optional[int]  = None
        self.ass    = ass
        self.max    = max
        self.min    = min

    def has_ass(self) -> bool:
        return self.ass != Ass.none

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
        if self.ass == Ass.none:
            return max(self.ass_check_value_min_cached(), self.ass_check_value_max_cached())
        value = self.read_bool_cached()
        if not value:
            return Ass.passed
        if log_ass != Ass.none and self.ass >= log_ass:
            log_f.append(self)
        return self.ass

    async def ass_check(self, log_ass : Ass = Ass.none, log_f : list[Union["RFlag","Reg"]] = []) -> Ass:
        if self.ass == Ass.none:
            return Ass.none
        _ = await self.read_bytes()
        return self.ass_check_cached(log_ass, log_f)

    def _limit_comparision(self, lhs : Optional[int], op : str, rhs : Optional[int]) -> bool:
        if lhs is None or rhs is None:
            return False
        b = ast.literal_eval(f'{lhs}{op}{rhs}')
        assert isinstance(b, bool)
        return b

    def _limit_comparision_lhs_read_value_cached(self, op : str, rhs : Optional[int]) -> bool:
        value = self.read_value_cached()
        if not isinstance(value, int):
            return False
        return self._limit_comparision(value, op, rhs)

    def read_value_at_min_cached(self) -> bool:
        return self._limit_comparision_lhs_read_value_cached('==', self.min)

    def read_value_at_max_cached(self) -> bool:
        return self._limit_comparision_lhs_read_value_cached('==', self.max)

    def read_value_error_min_cached(self) -> bool:
        return self._limit_comparision_lhs_read_value_cached('<', self.min)

    def read_value_error_max_cached(self) -> bool:
        return self._limit_comparision_lhs_read_value_cached('>', self.max)

    def ass_check_value_min_cached(self, value : Optional[int] = None) -> Ass:
        if self.min is None:
            return Ass.none
        if value is None:
            value = self.read_value_cached() #type:ignore
            assert isinstance(value, int)
        if value > self.min:
            return Ass.passed
        if value == self.min:
            return Ass.debug
        return Ass.error

    def ass_check_value_max_cached(self, value : Optional[int] = None) -> Ass:
        if self.max is None:
            return Ass.none
        if value is None:
            value = self.read_value_cached() #type:ignore
            assert isinstance(value, int)
        if value < self.max:
            return Ass.passed
        if value == self.max:
            return Ass.debug
        return Ass.error

    def _str_num(self, value : int, base : Literal[2, 10, 16]) -> str:
        match (base):
            case 2:  return f'0b{value:0{self.value_type.width}b}'
            case 10: return str(value)
            case 16: return f'0x{value:0{ceil_div(self.value_type.width,8)}X}'

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

        ass_color = self.ass_check_cached().color
        s = ''
        if self.ass != Ass.none:
            s += to_rich_str(str(self.ass), ass_color)+": "
        elif value_int is not None and (self.min is not None or self.max is not None):
            min_s = ''
            max_s = ''
            if self.min is not None:
                min_color = self.ass_check_value_min_cached(value_int).color;
                min_s = f'{to_rich_str(self._str_num(self.min, base), min_color)} <= '
            if self.max is not None:
                max_color = self.ass_check_value_max_cached(value_int).color;
                print(f'{self.max=}')
                max_s = f' <= {to_rich_str(self._str_num(self.max, base), max_color)}'
                print(f'{max_s=}')
            s += f"({min_s}{to_rich_str('v', ass_color)}{max_s}) "
        if value_str is None:
            assert value_int is not None
            value_str = self._str_num(value_int, base)
        s += to_rich_str(value_str, ass_color)
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
        b = v.to_bytes(self.size, byteorder='little', signed=False)
        return self.write_bytes_cached(b)

    async def write_uint(self, v : int):
        self.write_uint_cached(v)
        await self.write_cache()

    def write_sint_cached(self, v : int):
        b = v.to_bytes(self.size, byteorder='little', signed=True)
        return self.write_bytes_cached(b)

    async def write_sint(self, v : int):
        self.write_sint_cached(v)
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
        if self.elem_size != (self.value_type.width*8):
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
        return value_int

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

    def write_idx_uint_cached(self, idx : int, val : int):
        b = val.to_bytes(self.elem_size, byteorder='little', signed=False)
        self.write_idx_bytes_cached(idx, b)

    async def write_idx_uint(self, idx : int, val : int):
        self.write_idx_uint_cached(idx, val)
        await self.write_idx_cache(idx)

    def write_idx_sint_cached(self, idx : int, val : int):
        b = val.to_bytes(self.elem_size, byteorder='little', signed=True)
        self.write_idx_bytes_cached(idx, b)

    async def write_idx_sint(self, idx : int, val : int):
        self.write_idx_sint_cached(idx, val)
        await self.write_idx_cache(idx)

    def read_str_cached(self)  -> str:
        assert self.elem_size==8
        assert self.elem_offset==8
        value_list_uint = self.read_list_uint_cached()
        value_str = ''.join([chr(uint) for uint in value_list_uint])
        return value_str

    async def read_str(self)  -> str:
        _ = await self.read_bytes()
        return self.read_str_cached()

    def write_list_uint_cached(self, value : list[int]):
        b = list_int_to_bytes(value, self.elem_size, endian='little', signed=False)
        self.write_bytes_cached(b)

    async def write_list_uint(self, value : list[int]):
        self.write_list_uint_cached(value)
        await self.write_cache()

    def write_list_sint_cached(self, value : list[int]):
        b = list_int_to_bytes(value, self.elem_size, endian='little', signed=True)
        self.write_bytes_cached(b)

    async def write_list_sint(self, value : list[int]):
        self.write_list_sint_cached(value)
        await self.write_cache()

    def ass_check_cached(self, log_ass : Ass = Ass.none, log_f : list[Union["RFlag",Reg]] = []) -> Ass:
        if self.ass == Ass.none:
            return max(self.ass_check_value_min_cached(), self.ass_check_value_max_cached())
        value = max(self.read_list_bool_cached())
        if not value:
            return Ass.passed
        if log_ass != Ass.none and self.ass >= log_ass:
            log_f.append(self)
        return self.ass

    async def ass_check(self, log_ass : Ass = Ass.none, log_f : list[Union["RFlag",Reg]] = []) -> Ass:
        _ = await self.read_bytes()
        return self.ass_check_cached(log_ass, log_f)

    def ass_check_cached_idx(self, idx : int, log_ass : Ass = Ass.none, log_f : list[Union["RFlag",Reg]] = []) -> Ass:
        if self.ass == Ass.none:
            return Ass.none
        value = self.read_idx_bool_cached(idx)
        if not value:
            return Ass.passed
        if log_ass != Ass.none and self.ass >= log_ass:
            log_f.append(self)
        return self.ass

    async def ass_check_idx(self, idx : int, log_ass : Ass = Ass.none, log_f : list[Union["RFlag",Reg]] = []) -> Ass:
        _ = await self.read_idx_bytes(idx)
        return self.ass_check_cached_idx(idx, log_ass, log_f)

    def read_rich_str_cached(self) -> str:
        #TODO:!!!!! CHECK MAX MIN
        use_hex = False
        match self.value_type.kind:
            case ValueKind.uint:
                value = self.read_list_uint_cached()
            case ValueKind.sint:
                value = self.read_list_sint_cached()
            case ValueKind.bits:
                value = self.read_list_uint_cached()
                use_hex = True
            case ValueKind.flag:
                assert self.value_type.is_bool
                value = self.read_list_bool_cached()
            case ValueKind.char:
                value = self.read_str_cached()
        # assert self.fmt == Fmt.hex
        value_str = ''
        if self.ass != Ass.none:
            ass_checked = self.ass_check_cached()
            value_str = to_rich_str(f'{self.ass}', ass_checked.color)+": "
        value_str += "[ "
        for idx, v in enumerate(value):
            ass = self.ass_check_cached_idx(idx)
            if use_hex:
                assert isinstance(v, int)
                v_str = hex(v)
            else:
                v_str= str(v)
            value_str +=to_rich_str(v_str, ass.color)
            if idx != len(value)-1:
                value_str+= ", "
        value_str += " ]"
        return value_str

class RegK(Reg):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, acc = Acc.k) #, ass = Ass.none)

    async def read_int(self)  -> int:
        return self.read_uint_cached()

class RegVecK(RegVec):
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
        for v in lv:
            v = str(int(v))
            s += to_rich_str(v, ass_checked.color) 
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

        d = self.reg_flags.read_bytes_cached()

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

    def ass_check_cached(self, log_ass : Ass = Ass.none, log_f : list[RFlag] = []) -> Ass:
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
            if f.ass != None:
                return True
        return False

    async def ass_check(self, log_ass : Ass = Ass.none, log : list[RFlag] = []) -> Ass:
        await self.read_cache()
        return self.ass_check_cached(log_ass, log)

class RegFlagsK(RegFlags):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, acc = Acc.k, **kwargs) #, ass = Ass.none)

