#!/usr/bin/env python3

import argparse
from pathlib import Path
from datetime import datetime
from typing import Union

from code_generator_parse_recipe import ValueTypeUnresolved, parse_recipe_file, RecipeK, RecipeVar, RecipeReg, ResolvableFunction
# from basic import promote_to_sw_w, ceil_div
from basic_types import Acc, Ass, ValueKind, ValueType, SKMAP_VER_STR

def name_to_reg_k(name : str) -> str:
    return "self.k_"+name

def name_to_reg_var(name : str) -> str:
    return "self.var_"+name

def reg_to_py_inst_str(reg : RecipeReg) -> str:
    if isinstance(reg, RecipeK):
        return name_to_reg_k(reg.name)
    assert isinstance(reg, RecipeVar)
    return name_to_reg_var(reg.name)

def py_resolve_str(v : Union[int, RecipeK, ResolvableFunction]) -> str:
    if isinstance(v, int):
        return str(v)
    if isinstance(v, RecipeK):
        return f'self.{v.name}'
    if isinstance(v, ResolvableFunction):
        return f'({v.lhs} {v.op} {v.rhs})' #type: ignore
    raise runtimeError(f"Unexpected {type(v)=}")

def resolvable_py_member_function(value : Union[ResolvableFunction, RecipeK, int]) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, RecipeK):
        return f'self.{value.name}'
    assert isinstance(value, ResolvableFunction), f"{type(value)=}"
    lhs = resolvable_py_member_function(value.lhs)
    rhs = resolvable_py_member_function(value.rhs)
    return f'({lhs} {value.op} {rhs})'

def value_type_str(value_type : Union[ValueType, ValueTypeUnresolved]):
    assert value_type.width is not None
    w = resolvable_py_member_function(value_type.width)
    t_str = f"skmap.ValueType(kind=skmap.{value_type.kind}, width={w}"
    if value_type.is_vec:
        assert value_type.vec_len is not None
        vec_len = resolvable_py_member_function(value_type.vec_len)
        t_str += f", vec_len={vec_len}"
    t_str += ")"
    return t_str

def value_py_type_str(t : Union[ValueType, ValueTypeUnresolved]):
    if t.kind == ValueKind.char:
        return 'str'
    match t.kind:
        case ValueKind.uint:
            rt = 'int'
        case ValueKind.sint:
            rt = 'int'
        case ValueKind.bits:
            rt = 'int'
        case ValueKind.flag:
            rt = 'int'
        case _:
            assert False
    if t.is_vec:
        rt = f'typing.List[{rt}]'
    return rt

def _value_kind_function_str(k : ValueKind) -> str:
    match k:
        case ValueKind.uint:
            return 'uint'
        case ValueKind.sint:
            return 'sint'
        case ValueKind.bits:
            return 'uint'
        case ValueKind.flag:
            return 'uint'
        case _:
            assert False

def _value_type_function_str(t : Union[ValueType, ValueTypeUnresolved]) -> str:
    f = ''
    if t.kind == ValueKind.char:
        if t.is_vec:
            f += 'str'
        else:
            f += 'char'
    else:
        if t.is_vec:
            f += 'vec_'
        f += _value_kind_function_str(t.kind)
    return f

def read_value_function_str(t : Union[ValueType, ValueTypeUnresolved], cached : bool) -> str:
    f = 'read_'+_value_type_function_str(t)
    if cached:
        f += '_cached'
    return f

def write_value_function_str(t : Union[ValueType, ValueTypeUnresolved]) -> str:
    return 'write_'+_value_type_function_str(t)

def all_reg_value_functions_str_not_flag(reg : RecipeReg) -> str:
    assert reg.t.width is not None
    reg_name = reg_to_py_inst_str(reg)
    t_str = value_py_type_str(reg.t)
    func_read_cached = read_value_function_str(reg.t, cached=True)
    func_read        = read_value_function_str(reg.t, cached=False)
    func_write      = write_value_function_str(reg.t)
    kind_f_s = _value_kind_function_str(reg.t.kind)
    func_read_idx_cached = f'read_idx_{kind_f_s}_cached'
    func_read_idx = f'read_idx_{kind_f_s}'
    func_write_idx = f'write_idx_{kind_f_s}'

    s = ''
    is_vec_int = reg.t.vec_len != None and reg.t.kind in (ValueKind.uint, ValueKind.sint, ValueKind.bits)
    s += f'    @property\n'
    s += f'    def {reg.name}_value_type(self) -> skmap.ValueType:\n'
    s += f'        return {value_type_str(reg.t)}\n\n'

    # s += f'    @property\n'
    # s += f'    def {reg.name}_value_kind(self) -> skmap.ValueKind:\n'
    # s += f'        return skmap.{reg.t.kind}\n\n'
    #
    # s += f'    @property\n'
    # s += f'    def {reg.name}_w(self) -> int:\n'
    # s += f'        return {py_resolve_str(reg.t.width)}\n\n'
    # if reg.t.vec_len is not None:
    #     s += f'    @property\n'
    #     s += f'    def {reg.name}_len(self) -> int:\n'
    #     s += f'        return {py_resolve_str(reg.t.vec_len)}\n\n'
    # if reg.t.vec_len is not None:
    #     s += f'    @property\n'
    #     s += f'    def {reg.name}_len(self) -> int:\n'
    #     s += f'        return {py_resolve_str(reg.t.vec_len)}()\n\n'

    match reg.acc:
        case Acc.k:
            s += f'    @property\n'
            s += f'    def {reg.name}(self) -> {t_str}:\n'
            s += f'        return {reg_name}.{func_read_cached}()\n\n'
        case Acc.ro:
            s += f'    def {reg.name}_cached(self) -> {t_str}:\n'
            s += f'        return {reg_name}.{func_read_cached}()\n\n'
            s += f'    async def {reg.name}_read(self) -> {t_str}:\n'
            s += f'        return await {reg_name}.{func_read}()\n\n'
            if is_vec_int:
                s += f'    def {reg.name}_cached_idx(self, idx : int) -> int:\n'
                s += f'        return {reg_name}.{func_read_idx_cached}(idx)\n\n'
                s += f'    async def {reg.name}_read_idx(self, idx : int) -> int:\n'
                s += f'        return await {reg_name}.{func_read_idx}(idx)\n\n'
        case Acc.rc:
            s += f'    def {reg.name}_cached(self) -> {t_str}:\n'
            s += f'        return {reg_name}.{func_read_cached}()\n\n'
            s += f'    async def {reg.name}_read(self, clear : bool) -> {t_str}:\n'
            s += f'        val = await {reg_name}.{func_read}()\n'
            s += f'        if clear:\n'
            s += f'            await self.{reg.name}_clear()\n'
            s += f'        return val\n\n'
            s += f'    async def {reg.name}_clear(self):\n'
            s += f'        await {reg_name}.write_zero()\n\n'
            if is_vec_int:
                s += f'    def {reg.name}_cached_idx(self, idx : int) -> int:\n'
                s += f'        return {reg_name}.{func_read_idx_cached}(idx)\n\n'
                s += f'    async def {reg.name}_read_idx(self, idx : int) -> int:\n'
                s += f'        return await {reg_name}.{func_read_idx}(idx)\n\n'
                s += f'    async def {reg.name}_clear_idx(self, idx : int):\n'
                s += f'        await {reg_name}.{func_write_idx}(idx, 0)\n\n'
        case Acc.rw:
            s += f'    def {reg.name}_cached(self) -> {t_str}:\n'
            s += f'        return {reg_name}.{func_read_cached}()\n\n'
            s += f'    async def {reg.name}_read(self) -> {t_str}:\n'
            s += f'        return await {reg_name}.{func_read}()\n\n'
            s += f'    async def {reg.name}_write(self, value : {t_str}):\n'
            s += f'        await {reg_name}.{func_write}(value)\n\n'
            if is_vec_int:
                s += f'    def {reg.name}_cached_idx(self, idx : int) -> int:\n'
                s += f'        return {reg_name}.{func_read_idx_cached}(idx)\n\n'
                s += f'    async def {reg.name}_read_idx(self, idx : int) -> int:\n'
                s += f'        return await {reg_name}.{func_read_idx}(idx)\n\n'
                s += f'    async def {reg.name}_write_idx(self, idx : int, val : int):\n'
                s += f'        await {reg_name}.{func_write_idx}(idx, val)\n\n'
        case Acc.wt:
            s += f'    def {reg.name}_cached(self) -> {t_str}:\n'
            s += f'        return {reg_name}.{func_read_cached}()\n\n'
            s += f'    async def {reg.name}_read(self) -> {t_str}:\n'
            s += f'        return await {reg_name}.{func_read}()\n\n'
            if not is_vec_int:
                s += f'    async def {reg.name}_trigger(self, value : {t_str}):\n'
                s += f'        await {reg_name}.{func_write}(value)\n\n'
            if is_vec_int:
                s += f'    def {reg.name}_cached_idx(self, idx : int) -> int:\n'
                s += f'        return await {reg_name}.{func_read_idx_cached}(idx)\n\n'
                s += f'    async def {reg.name}_read_idx(self, idx : int) -> int:\n'
                s += f'        return await {reg_name}.{func_read_idx}(idx)\n\n'
                s += f'    async def {reg.name}_trigger_idx(self, idx : int, val : int):\n'
                s += f'        await {reg_name}.{func_write_idx}(idx, val)\n\n'
        case _:
            assert False
    return s

def all_reg_value_functions_str_is_flag(reg : RecipeReg) -> str:
    assert reg.t.kind == ValueKind.flag
    assert reg.flags is not None
    s = ''
    for f in reg.flags:
        if isinstance(reg, RecipeK):
            f_name =  name_to_reg_k(f.name)
        else:
            assert isinstance(reg, RecipeVar)
            f_name = name_to_reg_var(f.name)

        if f.vec_len != None:
            t_str = 'list[bool]'
            func_read_cached = 'read_list_bool_cached'
            func_read        = 'read_list_bool'
            func_write       = 'write_list_bool'

            s += f'    @property\n'
            s += f'    def {f.name}_len(self) -> int:\n'
            s += f'      return {py_resolve_str(f.vec_len)}\n\n'

        else:
            t_str = 'bool'
            func_read_cached = 'read_bool_cached'
            func_read        = 'read_bool'
            func_write       = 'write_bool'
        match reg.acc:
            case Acc.k:
                s += f'    @property\n'
                s += f'    def {f.name}(self) -> {t_str}:\n'
                s += f'        return {f_name}.{func_read_cached}()\n\n'
            case Acc.ro | Acc.rc:
                s += f'    def {f.name}_cached(self) -> {t_str}:\n'
                s += f'        return {f_name}.{func_read_cached}()\n\n'
                s += f'    async def {f.name}_read(self) -> {t_str}:\n'
                s += f'        return await {f_name}.{func_read}()\n\n'
            case Acc.rw:
                s += f'    def {f.name}_cached(self) -> {t_str}:\n'
                s += f'        return {f_name}.{func_read_cached}()\n\n'
                s += f'    async def {f.name}_read(self) -> {t_str}:\n'
                s += f'        return await {f_name}.{func_read}()\n\n'
                s += f'    async def {f.name}_write(self, value : {t_str}):\n'
                s += f'        await {f_name}.{func_write}(value)\n\n'
            case Acc.wt:
                s += f'    def {f.name}_cached(self) -> {t_str}:\n'
                s += f'        return {f_name}.{func_read_cached}()\n\n'
                s += f'    async def {f.name}_read(self) -> {t_str}:\n'
                s += f'        return await {f_name}.{func_read}()\n\n'
                s += f'    async def {f.name}_trigger(self, value : {t_str}):\n'
                s += f'        await {f_name}.{func_write}(value)\n\n'
            case _:
                assert False
        if reg.acc in ( Acc.ro, Acc.rw, Acc.wt ):
            s += f'    async def {reg.name}_update_cache(self) -> {t_str}:\n'
            s += f'        _ = await {f_name}.read_bytes() \n\n'

        if reg.acc == Acc.wt:
            reg_name = reg_to_py_inst_str(reg)
            func_write      = write_value_function_str(reg.t)
            s += f'    def {reg.name}_clear(self) -> {t_str}:\n'
            s += f'        await {reg_name}.write_uint(0)\n\n'

    return s
    #     for f in reg.flags:
    #         if f.vec_len != None:
    #             t_str = 'list[bool]'
    #             v_func = 'read_list_bool_cached'
    #         else:
    #             t_str = 'bool'
    #             v_func = 'read_bool_cached'
    #         return f"""
    #     @property
    #     def {f.name}(self) -> {t_str}:
    #         return {name_to_reg_k(f.name)}.{v_func}()
    # """


def all_reg_value_functions_str(reg : RecipeReg) -> str:
    if reg.t.kind == ValueKind.flag:
        return all_reg_value_functions_str_is_flag(reg)
    else:
        return all_reg_value_functions_str_not_flag(reg)

def generate_py_module(recipe_file : Path, py_file : Path):
    recipe = parse_recipe_file(recipe_file)

    with open(py_file, 'w') as py_f:
        py_f.write(f"""#-------------------------------------------------------------------------------
# NOTE: this file is autogenerated:
#    * From {__file__}
#    * On {datetime.now()} 
#    * Using HDLSkel SkMap {SKMAP_VER_STR}
#    * For {recipe.name} {recipe.id} v{recipe.version}
#    * Checksum 0x{recipe.checksum_str()}
#-------------------------------------------------------------------------------

import typing

import skmap

class {recipe.sw_module}(skmap.Module):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def name(cls) -> str:
        return "{recipe.name}";

    @classmethod
    def id(cls) -> str:
        return "{recipe.id}"

    @classmethod
    def version(cls) -> int:
        return {recipe.version}

    @classmethod
    def checksum(cls) -> int:
        return 0x{recipe.checksum_str()}\n\n""")

        for kv in recipe.k:
            py_f.write(all_reg_value_functions_str(kv))

        for varv in recipe.var:
            py_f.write(all_reg_value_functions_str(varv))

        py_f.write("""
    def _init_reg_map_k(self):
""")
        for kv in recipe.k:
            name_k = name_to_reg_k(kv.name)
            if kv.t.kind == ValueKind.flag:
                assert kv.flags is not None
                for f in kv.flags:
                    vec_len_param = '' if f.vec_len is None else f' vec_len={py_resolve_str(f.vec_len)},'
                    bit = resolvable_py_member_function(f.bit)
                    py_f.write(f"        {name_to_reg_k(f.name)} = skmap.RFlagK(name='{f.name}', bit={bit}, ass=skmap.Ass.{f.ass.str()},{vec_len_param} desc='{f.desc}')\n")
                py_f.write("        flags = [")
                for f in kv.flags: py_f.write(f" {name_to_reg_k(f.name)}, ")
                py_f.write("]\n")
                width = resolvable_py_member_function(kv.t.width)
                py_f.write(f"        {name_k} = skmap.RegFlagsK(self, name='{kv.name}', width={width}, flags=flags, desc='{kv.desc}')\n")
            else:
                t_str = value_type_str(kv.t)
                reg_type = 'RegVecK' if kv.t.is_vec else 'RegK'
                py_f.write(f"        {name_k} = skmap.{reg_type}(self, name='{kv.name}', value_type={t_str}, desc='{kv.desc}')\n")
            py_f.write(f"        self._add_reg_k({name_k})\n\n")

        py_f.write("""    def _init_reg_map_var(self):\n""")
        for varv in recipe.var:
            name_var = name_to_reg_var(varv.name)
            if varv.t.kind == ValueKind.flag:
                assert varv.flags is not None
                for f in varv.flags:
                    vec_len_param = '' if f.vec_len is None else f' vec_len={f.vec_len},'
                    py_f.write(f"        {name_to_reg_var(f.name)} = skmap.RFlag(name='{f.name}', bit={f.bit}, ass=skmap.Ass.{f.ass.str()},{vec_len_param} desc='{f.desc}')\n")
                py_f.write("        flags = [")
                for f in varv.flags: py_f.write(f" {name_to_reg_var(f.name)}, ")
                py_f.write("]\n")
                w = resolvable_py_member_function(varv.t.width)
                py_f.write(f"        {name_var} = skmap.RegFlags(self, name='{varv.name}', width={w}, acc=skmap.Acc.{varv.acc}, flags=flags, desc='{varv.desc}')\n")
            else:
                t_str = value_type_str(varv.t)
                reg_type = 'RegVec' if varv.t.is_vec else 'Reg'
                py_f.write(f"        {name_var} = skmap.{reg_type}(self, name='{varv.name}', value_type={t_str}, acc=skmap.Acc.{varv.acc}, desc='{varv.desc}')\n")
            py_f.write(f"        self._add_reg_var({name_var})\n\n")

        py_f.write(f"skmap.register_Module({recipe.sw_module})\n")

def parse_args():
    parser = argparse.ArgumentParser(
        description="Parse a skmap module recipe file and generate skmap module"
    )
    parser.add_argument(
        "recipe_file",
        type=Path,
        help="Path to skmap recipe file"
    )
    parser.add_argument(
        "py_file",
        type=Path,
        help="Path to VHDL file to generate"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    generate_py_module(args.recipe_file, args.py_file) 

if __name__ == '__main__':
    main()
