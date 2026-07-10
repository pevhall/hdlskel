from typing import Optional, Type, Literal, Union, TYPE_CHECKING

from .basic_types import Acc, Ass, ValueKind, ValueType, value_type_u8, value_type_x32
from .basic import ceil_log2, ceil_div, ceil_multiple, promote_to_sw_w, bytes_to_list_int, list_int_to_bytes, cast_uint_to_sint, to_rich_str

if TYPE_CHECKING:
    from module import Module

class Reg:
    def __init__(self, module : "Module", name : str, value_type : ValueType, acc : Acc, desc : str): #, fmt : Fmt = Fmt.default): #, ass : Ass = Ass.none):
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

    def value_type_str(self) -> str:
        return f'{self.value_type}'

    def read_bytes_cached(self) -> bytes:
        assert isinstance(self.addr, int)
        return self.module.read_cache(self.addr, self.size)

    async def read_bytes(self) -> bytes:
        assert isinstance(self.addr, int)
        if self.acc == Acc.k:
            return self.read_bytes_cached()
        return await self.module.read_bytes(self.addr, self.size)

    async def update_cache(self):
        _ = await self.read_bytes()

    def _bytes_to_uint(self, b:bytes) -> int:
        value_int = int.from_bytes(b, byteorder='little')
        if self.value_type.width != (self.size*8):
            mask = (1<<self.value_type.width)-1
            value_int &= mask
        return value_int

    def _bytes_to_sint(self, b:bytes) -> int:
        value_int = self._bytes_to_uint(b)
        sgn_bit = (1<<(self.value_type.width-1))
        if value_int >= sgn_bit:
            value_int -= sgn_bit*2
        return value_int

    def read_uint_cached(self) -> int:
        b = self.read_bytes_cached()
        return self._bytes_to_uint(b)

    def read_sint_cached(self) -> int:
        b = self.read_bytes_cached()
        return self._bytes_to_sint(b)

    def read_char_cached(self) -> str:
        assert self.value_type.width == 8
        value_uint = self.read_uint_cached()
        return chr(value_uint)

    def read_cached(self):
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

    async def read_uint(self) -> int:
        b = await self.read_bytes()
        value_int = int.from_bytes(b, byteorder='little')
        # print(f'{value_int=:x} = int.from_bytes({b=})')
        return value_int

    async def read_sint(self) -> int:
        value_uint = await self.read_uint()
        return cast_uint_to_sint(value_uint, self.value_type.width)

    async def read_char(self) -> str:
        assert self.value_type.width == 8
        value_uint = await self.read_uint()
        return chr(value_uint)

    def read_rich_str_cached(self) -> str:
        match self.value_type.kind:
            case ValueKind.uint:
                value_str = str(self.read_uint_cached())
            case ValueKind.sint:
                value_str = str(self.read_sint_cached())
            case ValueKind.bits:
                value_str = f'0x{self.read_uint_cached():0{ceil_div(self.value_type.width,8)}X}'
            case ValueKind.flag:
                value_str = f'0b{self.read_uint_cached():0{self.value_type.width}b}'
            case ValueKind.char:
                value_str = self.read_char_cached()

        # print(f'{value_int=:x} = int.from_bytes({b=})')
        #TODO change to hex for bits / x
        return value_str

    def write_bytes_cache(self, b : bytes):
        assert self.acc in (Acc.rw, Acc.wt) or (self.acc == Acc.rc and not any(b))
        assert isinstance(self.addr, int)
        assert len(b) <= self.size
        assert len(b) >= ceil_div(self.value_type.width, 8)
        return self.module.write_bytes_cache(self.addr, b)

    async def write_bytes(self, b : bytes):
        # print(f'{self.acc=} {not any(b)=}')
        assert self.acc in (Acc.rw, Acc.wt) or ((self.acc == Acc.rc) and not any(b))
        assert isinstance(self.addr, int)
        assert len(b) <= self.size
        assert len(b) >= ceil_div(self.value_type.width, 8)
        return await self.module.write_bytes(self.addr, b)

    def write_uint_cache(self, v : int):
        b = v.to_bytes(self.size, byteorder='little', signed=False)
        return self.write_bytes_cache(b)

    async def write_uint(self, v : int):
        b = v.to_bytes(self.size, byteorder='little', signed=False)
        return await self.write_bytes(b)

    async def write_sint(self, v : int):
        b = v.to_bytes(self.size, byteorder='little', signed=True)
        return await self.write_bytes(b)

    def write_sint_cache(self, v : int):
        b = v.to_bytes(self.size, byteorder='little', signed=True)
        return self.write_bytes_cache(b)

    def write_zero(self):
        return self.write_uint(0)

    def write_zero_cache(self):
        return self.write_sint_cache(0)

    # def add_to_table(self, table):
    #     table.add_row(str(self.addr), self.value_type_str(),  str(self.acc),  self.name, self.read_rich_str_cached(), self.desc)

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
            value_vec_int[ii] = cast_uint_to_sint(value_vec_int[ii], self.elem_size)
        return value_vec_int

    def read_vec_uint_cached(self) -> list[int]:
        b = self.read_bytes_cached()
        return self._bytes_to_list_uint(b)

    def read_vec_sint_cached(self) -> list[int]:
        b = self.read_bytes_cached()
        return self._bytes_to_list_sint(b)

    async def read_vec_uint(self) -> list[int]:
        b = self.read_bytes_cached()
        return self._bytes_to_list_uint(b)

    async def read_vec_sint(self) -> list[int]:
        b = await self.read_bytes()
        return self._bytes_to_list_sint(b)

    def read_idx_bytes_cached(self, idx : int) -> bytes:
        assert isinstance(self.addr, int)
        return self.module.read_cache(self.addr+idx*self.elem_offset, self.elem_size)

    async def read_idx_bytes(self, idx : int) -> bytes:
        assert isinstance(self.addr, int)
        if self.acc == Acc.k:
            return self.read_idx_bytes_cached(idx)
        return await self.module.read_bytes(self.addr+idx*self.elem_offset, self.elem_size)

    async def write_idx_bytes(self, idx : int, b : bytes):
        assert self.acc in (Acc.rw, Acc.wt)
        assert isinstance(self.addr, int)
        assert len(b) <= self.elem_size
        assert len(b) >= ceil_div(self.value_type.width, 8)
        return await self.module.write_bytes(self.addr+idx*self.elem_offset, b)

    def read_idx_uint_cached(self, idx : int) -> int:
        b = self.read_idx_bytes_cached(idx)
        return self._bytes_to_uint(b)

    def read_idx_sint_cached(self, idx : int) -> int:
        b = self.read_idx_bytes_cached(idx)
        return self._bytes_to_sint(b)

    async def read_idx_uint(self, idx : int) -> int:
        b = await self.read_idx_bytes(idx)
        return self._bytes_to_uint(b)

    async def read_idx_sint(self, idx : int) -> int:
        b = await self.read_idx_bytes(idx)
        return self._bytes_to_sint(b)

    async def write_idx_uint(self, idx : int, val : int):
        b = val.to_bytes(self.elem_size, byteorder='little', signed=False)
        await self.write_idx_bytes(idx, b)

    async def write_idx_sint(self, idx : int, val : int):
        b = val.to_bytes(self.elem_size, byteorder='little', signed=True)
        await self.write_idx_bytes(idx, b)

    def _vec_uint_to_str(self, value_vec_uint) -> str:
        assert self.elem_size==8
        assert self.elem_offset==8
        value_str = ''.join([chr(uint) for uint in value_vec_uint])
        return value_str

    def read_str_cached(self)  -> str:
        value_vec_uint = self.read_vec_uint_cached()
        return self._vec_uint_to_str(value_vec_uint)

    async def read_str(self)  -> str:
        value_vec_uint = await self.read_vec_uint()
        return self._vec_uint_to_str(value_vec_uint)

    async def write_vec_uint(self, value_vec_uint : list[int]):
        b = list_int_to_bytes(value_vec_uint, self.elem_size, endian='little', signed=False)
        await self.write_bytes(b)

    async def write_vec_sint(self, value_vec_uint : list[int]):
        b = list_int_to_bytes(value_vec_uint, self.elem_size, endian='little', signed=True)
        await self.write_bytes(b)

    # def value_type_str(self) -> str:
    #     return f'{super().value_type_str()}[{self.value_type.vec_len}]'

    def read_rich_str_cached(self) -> str:
        # assert self.fmt == Fmt.hex
        value_vec_int = self.read_vec_uint_cached()
        return str(value_vec_int)

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

    async def read_bool(self) -> bool:
        assert self.vec_len is None or self.vec_len == 1
        return (await self.reg_flags.read_uint() & (1<<self.bit)) != 0

    def read_bool_cached(self) -> bool:
        assert self.vec_len is None or self.vec_len == 1
        return (self.reg_flags.read_uint_cached() & (1<<self.bit)) != 0

    async def read_list_bool(self) -> list[bool]:
        assert self.vec_len is not None
        value_list_bool = []
        value_uint = await self.reg_flags.read_uint()
        for ii in range(self.vec_len):
            value_list_bool.append(value_uint & ((ii+1)<<self.bit) != 0)
        return value_list_bool

    def read_list_bool_cached(self) -> list[bool]:
        assert self.vec_len is not None
        value_list_bool = []
        value_uint =  self.reg_flags.read_uint_cached()
        for ii in range(self.vec_len):
            value_list_bool.append(value_uint & ((ii+1)<<self.bit) != 0)
        return value_list_bool

    async def ass_check(self) -> Ass:
        return self._ass_check(await self.read_bool())

    def ass_check_cached(self) -> Ass:
        return self._ass_check(self.read_bool_cached())

    # def add_to_table(self, table):
    #     table.add_row('-', 'b',  f'{self.bit}',  self.name, self._value_rich_str(), self.desc)

class RFlagK(RFlag):

    def __init__(self,  *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def read_bool(self) -> bool:
        return self.read_bool_cached()

    async def ass_check(self) -> Ass:
        return self.ass_check_cached()

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

    @property
    def has_ass(self) -> bool:
        for f in self.flags:
            if f.ass != None:
                return True
        return False


    async def ass_check(self, log_ass : Ass = Ass.none, log : list[RFlag] = []) -> Ass:
        await self.update_cache()
        return self.ass_check_cached(log_ass, log)

class RegFlagsK(RegFlags):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, acc = Acc.k, **kwargs) #, ass = Ass.none)

