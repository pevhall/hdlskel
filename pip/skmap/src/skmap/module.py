import logging
from enum import Enum, auto, IntEnum
from typing import Optional, Type, Literal, Union
from abc import ABC, abstractmethod

# import rich
from rich.table import Table

from .console import console
from .regio import Regio
from .head import Head, SIZE_HEAD, SIZE_WORD, SYNC
from .basic_types import Acc, Ass, ValueKind, ValueType, value_type_u8, value_type_x32, SKMAP_VER_STR, SKMAP_VER_MAJOR, SKMAP_VER_MINOR, SKMAP_VER_PATCH
from .basic import ceil_log2, ceil_div, ceil_multiple, promote_to_sw_w, bytes_to_list_int, list_int_to_bytes, cast_uint_to_sint, to_rich_str
from .reg import Reg, RegVec, RegK, RegVecK, RegFlags, RegFlagsK, RFlag
from .reg_map_table import RegMapTable

# class Fmt(Enum):
#     default = auto()
#     hex = auto()
#

RegKTypes = Union[RegK, RegFlagsK]
class Module(ABC):

    def __init__(self, regio : Regio, addr : int, module_head : Head, module_data : bytearray):
        self.regio     = regio
        self.base_addr = addr
        self.head      = module_head
        self.cache     = module_data
        self._kid_addrs= [0] * self.head.len_kids
        self._kids     : list[Optional['Module']] = [None] * self.head.len_kids
        self.arr_reg_k   : list[RegKTypes] = []
        self.arr_reg_var : list[Reg]  = []
        self.arr_reg_var_ass_flags : list[RegFlags] = []
        # self.map_reg_k   : dict[str, RegKTypes] = {}
        # self.map_reg_var : dict[str, Reg]  = {}
        self.use_cache = False
        self.byte_align = 1

        assert(self.head.sync == SYNC)
        assert(self.head.flags == 0)

        self.byte_idx = SIZE_HEAD

        for kk in range(self.head.len_kids):
            self._kid_addrs[kk] = int.from_bytes(module_data[self.byte_idx:self.byte_idx+SIZE_WORD], byteorder='little')
            self.byte_idx += SIZE_WORD
            assert self._kid_addrs[kk] != 0, "addr 0 should never be a kid"
        # if 0 and len(self._kid_addrs) > 0:
        #     print(f'kids = {[hex(a) for a in self._kid_addrs]}')

        byte_idx_sub_end = self.byte_idx + self.head.len_sub*SIZE_WORD

        class SubID(IntEnum):
            PAD = 0x00
            BYTE_ALIGN = 0x1A

        sub_byte_align = self.byte_align
        while self.byte_idx < byte_idx_sub_end:
            # sub_id : int = int.from_bytes(module_data[self.byte_idx:self.byte_idx+1])
            sub_id = module_data[self.byte_idx]
            match sub_id:
                case SubID.PAD:
                    break
                case SubID.BYTE_ALIGN:
                    sub_byte_align = module_data[self.byte_idx+1]
                    # print(f'sub_head BYTE_ALIGN = {sub_byte_align=}')
                    logging.info(f'sub_head BYTE_ALIGN = {sub_byte_align=}')
                    assert sub_byte_align.bit_count() == 1
                    self.byte_idx += SIZE_WORD
                case _:
                    raise Exception(f"Unkowen {sub_id=}")

        self.byte_idx = byte_idx_sub_end

        byte_idx_expected = self.byte_idx + self.head.len_k * SIZE_WORD
        self._init_reg_map_k()
        self.byte_idx = ceil_div(self.byte_idx, SIZE_WORD) * SIZE_WORD
        # print(f'{byte_idx_expected=} {self.byte_idx=}, {self.head.len_k=}')
        assert(byte_idx_expected == self.byte_idx)

        self.base_addr_var = self.byte_idx + self.base_addr
        self.size_var = self.head.len_var * SIZE_WORD
        byte_idx_expected = self.byte_idx + self.size_var

        self.byte_align = sub_byte_align
        self._init_reg_map_var()
        # print(f'{byte_idx_expected=} {self.byte_idx=}, {self.head.len_var=}')
        self.byte_idx = ceil_div(self.byte_idx, SIZE_WORD) * SIZE_WORD
        assert byte_idx_expected == self.byte_idx, f'head var len = {self.head.len_var=}, map var len {self.byte_idx/SIZE_WORD-self.base_addr_var/SIZE_WORD}'

        self.use_cache = False

    def _cache_addr(self, addr:int) -> int:
        return addr - self.base_addr


    async def kid_at(self, idx : int) -> 'Module':
        if self._kids[idx] is None:
            self._kids[idx] = await make_module(self.regio, self._kid_addrs[idx])

        kid = self._kids[idx]
        assert kid is not None
        return kid

    async def kids(self) -> list['Module']:
        for idx in range(self.len_kids):
            await self.kid_at(idx)
        # self._kids : list['Module']
        return self._kids

    def kids_cached(self) -> list[Optional['Module']]:
        # self._kids : list[Optional['Module']]
        return self._kids

    def kids_with_class_cached(self, clss) -> list['Module']:
        kids = []
        for k in self._kids:
            if isinstance(k, clss):
                kids.append(k)
        return kids

    def get_kid_with_class_cached(self, clss) -> 'Module':
        k = self.kids_with_class_cached(clss)
        assert(len(k) == 1)
        return k[0]

    @property
    def len_kids(self) -> int:
        return self.head.len_kids

    def read_cached(self, addr:int, size : int) -> bytes:
        cache_addr = self._cache_addr(addr)
        ba = self.cache[cache_addr:cache_addr + size]
        # print(f'{ba=}, {addr=}, {cache_addr=}, {size=}')
        return bytes(ba)

    def write_bytes_cached(self, addr:int, b:bytes):
        cache_addr = self._cache_addr(addr)
        self.cache[cache_addr:cache_addr + len(b)] = b

    def _byte_align_size(self, size:int, addr:Optional[int] = None):
        if addr is not None:
            assert addr % self.byte_align == 0
        return ceil_multiple(size, self.byte_align)

    async def read_bytes(self, addr:int, size : int) -> bytes:
        if self.use_cache:
            return self.read_cached(addr, size)
        else:
            op_size = self._byte_align_size(size, addr=addr)
            b = await self.regio.read(addr, op_size)
            self.write_bytes_cached(addr, b)
            # self.cache[cache_addr:cache_addr + size] = b[:size]
            return b[:size]

    async def write_bytes(self, addr:int, b : bytes):
        # print(f'self.regio.write({addr}, {b})')
        self.write_bytes_cached(addr, b)
        if not self.use_cache:
            op_size = self._byte_align_size(len(b), addr=addr)
            await self.regio.write(addr, self.read_cached(addr, op_size))


    async def read_cache(self):
        assert not self.use_cache
        _ = await self.read_bytes(self.base_addr_var, self.size_var)

    async def read_cache_tree(self):
        await self.read_cache()
        for kid in await self.kids():
            await kid.read_cache_tree()

    async def write_cache(self):
        cache_addr = self._cache_addr(self.base_addr_var)
        assert not self.use_cache
        await self.write_bytes(self.base_addr_var, bytes(self.cache[cache_addr:cache_addr+self.size_var]))

    def _byte_idx_add_reg(self, reg):
        self.byte_idx += reg.size

    def _byte_aligment_from_val_width(self, width): 
        val_sw_bytes = promote_to_sw_w(width)//8
        align_bytes = max(self.byte_align, val_sw_bytes)
        return align_bytes

    def _byte_idx_align_addr_width(self, width):
        if width == 0:
            return 0
        align_bytes = self._byte_aligment_from_val_width(width)
        self.byte_idx = ceil_multiple(self.byte_idx, align_bytes)

    def _add_reg_k(self, reg : RegKTypes):
        self._byte_idx_align_addr_width(reg.value_type.width)
        reg.addr = self.byte_idx + self.base_addr
        self.arr_reg_k.append(reg)
        # self.map_reg_k[reg.name] = reg
        self._byte_idx_add_reg(reg)
        self._byte_idx_align_addr_width(reg.value_type.width)

    def _add_reg_var(self, reg : Reg):
        self._byte_idx_align_addr_width(reg.value_type.width)

        reg.addr = self.byte_idx + self.base_addr
        self.arr_reg_var.append(reg)
        if isinstance(reg, RegFlags):
            if reg.has_ass:
                self.arr_reg_var_ass_flags.append(reg)
        # self.map_reg_var[reg.name] = reg
        self._byte_idx_add_reg(reg)

        self._byte_idx_align_addr_width(reg.value_type.width)
        # print(f'map var {reg.name} at {self.byte_idx=} {self.byte_align=} {reg.value_type.width=}')

    def write_zero_all_rc_cached(self):
        for reg_var in self.arr_reg_var:
            reg_var.write_zero_cache()

    async def write_zero_all_rc(self):
        for reg_var in self.arr_reg_var:
            if reg_var.acc == Acc.rc:
                await reg_var.write_zero()

    @classmethod
    @abstractmethod
    def name(cls) -> str:
        pass

    @classmethod
    @abstractmethod
    def id(cls) -> str:
        pass

    @classmethod
    @abstractmethod
    def version(cls) -> int:
        pass

    @classmethod
    @abstractmethod
    def checksum(cls) -> int:
        pass

    @classmethod
    @abstractmethod
    def skmap_ver_major(cls) -> int:
        pass

    @classmethod
    @abstractmethod
    def skmap_ver_minor(cls) -> int:
        pass

    @classmethod
    @abstractmethod
    def skmap_ver_patch(cls) -> int:
        pass

    @classmethod
    @abstractmethod
    def skmap_ver_str(cls) -> str:
        pass

    @abstractmethod
    def _init_reg_map_k(self) -> None:
        pass

    @abstractmethod
    def _init_reg_map_var(self) -> None:
        pass

    def _init_post_reg_maps(self) -> None:
        pass

    def print_reg_map(self) :
        table = RegMapTable(title=self.info_line_str())
        table.add_module(self)
        table.print()

    def info_line_str(self) -> str:
        return f"{hex(self.base_addr)} {self.name()} {self.head}"

    async def make_kids(self):
        await self.kids()

    async def make_tree(self):
        for k in await self.kids():
            await k.make_tree()

    def print_tree_cached(self, indent : str =''):
        print(indent+self.info_line_str())
        indent = '  ─ '+indent
        # if idx == self.len_kids-1:
        #     indent = '└─'+indent
        # else:
        #     indent = '├─'+indent 
        for ii, kid in enumerate(self._kids):
            if kid is None:
                print (f'{indent} {self._kid_addrs[ii]} Uninitalised')
            else:
                kid.print_tree_cached(indent)

    def check_assert_cached(self, log_ass : Ass = Ass.none, log_f : list[RFlag] = []) -> Ass:
        ass = Ass.none
        for reg in self.arr_reg_var_ass_flags:
            f_ass = reg.ass_check_cached(log_ass, log_f)
            if f_ass >= ass:
                ass = f_ass
        return ass

    def check_assert_tree_cached(self, log_ass : Ass = Ass.none, log_f : list[RFlag] = []) -> Ass:
        ass = self.check_assert_cached(log_ass, log_f)
        for kid in self.kids_cached():
            assert kid is not None
            ass_kid = kid.check_assert_tree_cached(log_ass, log_f)
            if ass_kid > ass:
                ass = ass_kid
        return ass

    async def clear_assert(self):
        for reg_f in self.arr_reg_var_ass_flags:
            reg_f_ass = reg_f.ass_check_cached()
            if reg_f_ass >= Ass.debug:
                # print(f'{reg_f_ass=}')
                if reg_f.acc == Acc.rc:
                    await reg_f.write_zero()

    async def clear_assert_tree(self):
        await self.clear_assert()
        for k in await self.kids():
            await k.clear_assert_tree()


class ModuleUnkowen(Module):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def name(cls) -> str:
        return "Unkowen";

    @classmethod
    def id(cls) -> str:
        assert False

    @classmethod
    def version(cls) -> int:
        assert False

    @classmethod
    def checksum(cls) -> int:
        assert False

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

    def _init_reg_map_k(self):
        for ii in range(self.head.len_k):
            reg = RegK(self, name=f'UNKOWN_K_{ii}', value_type=value_type_x32, desc=f"Unkowen constant {ii}")
            self._add_reg_k(reg)

    def _init_reg_map_var(self):
        for ii in range(self.head.len_var):
            reg = Reg(self, name=f'UNKOWN_VAR_{ii}', value_type=value_type_x32, desc=f"Unkowen variable {ii}", acc=Acc.na)
            self._add_reg_var(reg)


# async def read_init_module_data(regio : Regio, addr : int):
#     head_data = await regio.read(addr, SIZE_HEAD)
#     module_head = Head(head_data)
#     print(f"{module_head=}")
#     module_size = module_head.module_size()
#     module_data = bytearray(head_data + await regio.read(addr+SIZE_HEAD, module_size-SIZE_HEAD))
#     print(f"{module_data=}")
#     return regio, addr, module_head, module_data

def singleton(cls):
    instances = {}

    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return get_instance

@singleton
class ModuleFactory():


    def __init__(self):
        self.lookup : dict[str, dict[int, Type[Module]]] = {}

    def register_module(self, module_class : Type[Module]):
        if module_class.id() not in self.lookup:
            self.lookup[module_class.id()] = {}
        module_lookup = self.lookup[module_class.id()]

        assert module_class.version() not in module_lookup
        module_lookup[module_class.version()] = module_class

    async def make_module(self, regio : Regio, addr : int, allow_unknowen = False) -> Module:
        head_data = await regio.read(addr, SIZE_HEAD)
        module_head = Head(head_data)
        # print(f'{module_head=}')
        module_size = module_head.module_size()
        module_data = bytearray(head_data + await regio.read(addr+SIZE_HEAD, module_size-SIZE_HEAD))
        # print(f"{module_data=}")
        if module_head.id in self.lookup:
            module_lookup = self.lookup[module_head.id]
            if module_head.version in module_lookup:
                module_class = module_lookup[module_head.version]
                if module_head.checksum == module_class.checksum():
                    if module_class.skmap_ver_major() != SKMAP_VER_MAJOR:
                        logging.error("SKMAP major version missmatch module has %s, expected %s",
                                      module_class.skmap_ver_str(), SKMAP_VER_STR)
                    if module_class.skmap_ver_minor() != SKMAP_VER_MINOR:
                        logging.error("SKMAP minor version missmatch module has %s, expected %s",
                                      module_class.skmap_ver_str(), SKMAP_VER_STR)
                    if module_class.skmap_ver_patch() != SKMAP_VER_PATCH:
                        logging.warning("SKMAP patch version missmatch module has %s, expected %s",
                                      module_class.skmap_ver_str(), SKMAP_VER_STR)
                    logging.info('Creating module (head =  %s)', module_head)
                    return module_class(regio, addr, module_head, module_data)
                else:
                    logging.error('Bad check sum for %s v%d, module_head.checksum =  %s, module_class.checksum = %s', module_class.name(), module_class.version(), hex(module_head.checksum), hex(module_class.checksum()))
        else:
            logging.error('Cannot find module, Unkowen ID (head: %s) ', module_head)

        if allow_unknowen:
            logging.warning("Return Unkowen module - see previouse warnings")
            return ModuleUnkowen(regio, addr, module_head, module_data)
        else:
            raise Exception("Unkowen modules not allowed, raising error, see previouse errors")


async def make_module(regio : Regio, addr : int, allow_unknowen = False) -> Module:
    factory = ModuleFactory()
    return await factory.make_module(regio, addr, allow_unknowen)

def register_Module(module_class : Type[Module]):
    factory = ModuleFactory()
    factory.register_module(module_class)

