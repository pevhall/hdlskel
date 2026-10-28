from pathlib import Path
from datetime import datetime
from typing import Union

from .code_generator_parse_resolvable import ResolvableFunctionOperation, ResolvableT, ResolvableFunctionBuiltIn, BultiInOperation
from .code_generator_parse_resolvable import is_value_param, contains_float_value
from .code_generator_parse_recipe import ValueTypeUnresolved, parse_recipe_file, RecipeIpkg, RecipeK, RecipeVar, RecipeReg, RecipeMem
# from basic import promote_to_sw_w, ceil_div
from .basic_types import Acc, Ass, ValueKind, ValueType, SKMAP_VER_STR, SKMAP_VER_MAJOR, SKMAP_VER_MINOR, SKMAP_VER_PATCH
from . import code_generator_sw_common as common

Sw = common.Sw

def name_to_ipkg(name : str) -> str:
    return "self."+name
def name_to_reg_k(name : str) -> str:
    return "self._k_"+name
# common.name_to_reg_k = name_to_reg_k

def name_to_reg_var(name : str) -> str:
    return "self._var_"+name

def name_to_ext_mem(name : str) -> str:
    return "self._mem_"+name

def reg_to_inst_str(reg : RecipeReg) -> str:
    if isinstance(reg, Union[RecipeK, RecipeIpkg]):
        return name_to_reg_k(reg.name)
    assert isinstance(reg, RecipeVar)
    return name_to_reg_var(reg.name)

def op_to_py_source(op : BultiInOperation) -> str:
    return {
        BultiInOperation.add : "+",
        BultiInOperation.sub : "-",
        BultiInOperation.mult: "*",
        BultiInOperation.div: "//",
        BultiInOperation.power: "**",
        BultiInOperation.mod : "%",
        BultiInOperation.eq  : "==",
        BultiInOperation.ne  : "!=",
        BultiInOperation.lt  : "<",
        BultiInOperation.le  : "<=",
        BultiInOperation.gt  : ">",
        BultiInOperation.ge  : ">=",
        # The recipe spells the logic operators like c++, python uses words
        BultiInOperation.land: "and",
        BultiInOperation.lor : "or",
        BultiInOperation.lnot: "not",
        }[op]

def to_python_source(node: ResolvableT) -> str:
    """Render a ResolvableT tree back out as a Python source-code expression string."""
    # if isinstance(node, bool):
    #     return str(int(node))
    if isinstance(node, int):
        return str(node)
    # if isinstance(node, str):   # plain-string leaf (e.g. name_to_k[name] = name)
    #     return f'"{node}"'
    if isinstance(node, RecipeIpkg):
        return f'self.{node.name}'
    if isinstance(node, RecipeK):
        return f'self.{node.name}'
    if is_value_param(node):
        # the v of a v_check / v_convert
        return node.name
    if isinstance(node, ResolvableFunctionOperation):
        if node.op.is_unary:
            # 'not' / '!' take one operand, the parser keeps rhs as None
            return f'({op_to_py_source(node.op)} {to_python_source(node.lhs)})'
        if node.op == BultiInOperation.div and contains_float_value(node):
            # The recipe `/` is a integer division, in a float expression (the v
            # of a v_convert / v_check with v_type 'f') it has to be a float one.
            return f'({to_python_source(node.lhs)} / {to_python_source(node.rhs)})'
        return f'({to_python_source(node.lhs)} {op_to_py_source(node.op)} {to_python_source(node.rhs)})'
    if isinstance(node, ResolvableFunctionBuiltIn):
        args = ', '.join(to_python_source(p) for p in node.params)
        return f'skmap.recipe_functions.{node.func.name}({args})'
    if hasattr(node, 'name'):  # RecipeK / RecipeIpkg leaf
        return node.name #type:ignore
    raise TypeError(f'Cannot render {node!r} {type(node)=} to python source')


# common.name_to_reg_var = name_to_reg_var


def resolve_k_ipkg_value(v : RecipeK) -> str:
    return f'self.{v.name}'
# common.resolve_k_ipkg_value = resolve_k_ipkg_value

# reg_to_inst_str = common.reg_to_inst_str
# resolvable_str = common.resolvable_str
# resolvable_member_function = common.resolvable_member_function

def value_type_str(value_type : Union[ValueType, ValueTypeUnresolved]):
    assert value_type.width is not None
    # w = resolvable_member_function(value_type.width)
    w = to_python_source(value_type.width)
    t_str = f"skmap.ValueType(kind=skmap.{value_type.kind}, width={w}"
    if value_type.is_vec:
        assert value_type.vec_len is not None
        vec_len = to_python_source(value_type.vec_len)
        t_str += f", vec_len={vec_len}"
    t_str += ")"
    return t_str

def value_ret_type_str(t : Union[ValueType, ValueTypeUnresolved]):
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
            if t.elem_w == 1:
                rt = 'bool'
            else:
                rt = 'int'
        case _:
            assert False
    if t.is_vec:
        rt = f'list[{rt}]'
    return rt

_value_kind_function_str = common._value_kind_function_str
read_value_function_str  = common.read_value_function_str
write_value_function_str  = common.write_value_function_str

def value_check_str_py(reg : RecipeReg) -> str:
    """The `v_check=skmap.ValueCheck(...)` ctor argument, '' when there is none.

    The lambda gets the register value as `v`, recipe k / ipkg values are read
    through `self`. The text is the check with every name resolved to a value
    (see resolvable_print_source), so it prints without the recipe.
    """
    if reg.v_check is None:
        return ''
    return (f", v_check=skmap.ValueCheck(lambda v: {to_python_source(reg.v_check)},"
            f" {reg.v_check_str!r}, skmap.VType.{reg.v_type.value})")

def value_convert_str_py(reg : RecipeReg) -> str:
    """The `v_convert=skmap.ValueConvert(...)` ctor argument, '' when there is none.

    The first lambda is the recipe expression (user value -> register value),
    the second one is its inverse (register value -> user value, used by every
    read), both are generated from the same recipe expression.
    """
    if reg.v_convert is None:
        return ''
    return (f", v_convert=skmap.ValueConvert(lambda v: {to_python_source(reg.v_convert)},"
            f" lambda v: {to_python_source(reg.v_convert_inv)},"
            f" {reg.v_convert_str!r}, {reg.v_convert_inv_str!r}, skmap.VType.{reg.v_type.value})"
            f", v_type=skmap.VType.{reg.v_type.value}")

def value_user_type_str_py(reg : RecipeReg, ignore_vec : bool = False) -> str:
    """Return / argument type of the user facing functions of a register.

    With a `v_convert` the functions work on the user value, which follows the
    recipe `v_type` ('f' is a float), without one they work on the value of the
    register itself.
    """
    t = reg.t
    if reg.v_type.is_float:
        rt = 'float'
    elif t.kind == ValueKind.flag and t.elem_w == 1:
        rt = 'bool'
    else:
        rt = 'int'
    if not ignore_vec and t.is_vec:
        rt = f'list[{rt}]'
    return rt

def has_v_convert(reg : RecipeReg) -> bool:
    return getattr(reg, 'v_convert', None) is not None

def all_ipkg_value_parameters_str(ipkgv : RecipeIpkg) -> str:
    t_str = value_ret_type_str(ipkgv.t)
    value = ipkgv.value
    if ipkgv.t.kind == ValueKind.char:
        if ipkgv.t.is_vec:
            value = f'"{value}"'
        else:
            value = f"'{value}'"
    else:
        value = to_python_source(value)

    s = ''
    s += f'    @property\n'
    s += f'    def {ipkgv.name}(self) -> {t_str}:\n'
    s += f'        return {value}\n\n'
    return s

def all_reg_value_functions_str_not_flag(reg : RecipeReg) -> str:
    assert reg.t.width is not None
    reg_name = reg_to_inst_str(reg)
    t_str = value_ret_type_str(reg.t)
    func_read_cached  = read_value_function_str(reg.t,  cached=True,  sw=Sw.py)
    func_read         = read_value_function_str(reg.t,  cached=False, sw=Sw.py)
    func_write_cached = write_value_function_str(reg.t, cached=True,  sw=Sw.py)
    func_write        = write_value_function_str(reg.t, cached=False, sw=Sw.py)
    kind_f_s = _value_kind_function_str(reg.t)
    func_read_idx_cached = f'read_idx_{kind_f_s}_cached'
    func_write_idx_cached = f'write_idx_{kind_f_s}_cached'
    func_read_idx = f'read_idx_{kind_f_s}'
    func_write_idx = f'write_idx_{kind_f_s}'

    s = ''
    is_vec_int = reg.t.vec_len != None and reg.t.kind in (ValueKind.uint, ValueKind.sint, ValueKind.bits)
    # A register with a v_convert gets the value conversion in the default
    # functions and the plain register value in the *_raw functions, the rest
    # of the module has only the plain functions.
    sfx = '_raw' if has_v_convert(reg) else ''
    s += f'    #{reg.name}: {reg.desc}\n'
    if reg.t.kind == ValueKind.flag:
        inst_type = 'RegFlags'
    if reg.t.is_vec:
        inst_type = 'RegVec'
    else:
        inst_type = 'Reg'
    s += f'    @property\n'
    s += f'    def {reg.name}_inst(self) -> skmap.{inst_type}:\n'
    s += f'        return {reg_name}\n\n'

    match reg.acc:
        case Acc.k:
            s += f'    @property\n'
            s += f'    def {reg.name}(self) -> {t_str}:\n'
            s += f'        return {reg_name}.{func_read_cached}()\n\n'
        case Acc.ro:
            s += f'    def {reg.name}_read_cached{sfx}(self) -> {t_str}:\n'
            s += f'        return {reg_name}.{func_read_cached}()\n\n'
            s += f'    async def {reg.name}_read{sfx}(self) -> {t_str}:\n'
            s += f'        return await {reg_name}.{func_read}()\n\n'
            if is_vec_int:
                s += f'    def {reg.name}_read_idx_cached{sfx}(self, idx : int) -> int:\n'
                s += f'        return {reg_name}.{func_read_idx_cached}(idx)\n\n'
                s += f'    async def {reg.name}_read_idx{sfx}(self, idx : int) -> int:\n'
                s += f'        return await {reg_name}.{func_read_idx}(idx)\n\n'
        case Acc.rc:
            s += f'    def {reg.name}_read_cached{sfx}(self) -> {t_str}:\n'
            s += f'        return {reg_name}.{func_read_cached}()\n\n'
            s += f'    async def {reg.name}_read{sfx}(self, clear : bool) -> {t_str}:\n'
            s += f'        val = await {reg_name}.{func_read}()\n'
            s += f'        if clear:\n'
            s += f'            await self.{reg.name}_clear()\n'
            s += f'        return val\n\n'
            s += f'    async def {reg.name}_clear(self):\n'
            s += f'        await {reg_name}.write_zero()\n\n'
            if is_vec_int:
                s += f'    def {reg.name}_read_idx_cached{sfx}(self, idx : int) -> int:\n'
                s += f'        return {reg_name}.{func_read_idx_cached}(idx)\n\n'
                s += f'    async def {reg.name}_read_idx{sfx}(self, idx : int) -> int:\n'
                s += f'        return await {reg_name}.{func_read_idx}(idx)\n\n'
                s += f'    async def {reg.name}_clear_idx(self, idx : int):\n'
                s += f'        await {reg_name}.{func_write_idx}(idx, 0)\n\n'
        case Acc.rw:
            s += f'    def {reg.name}_read_cached{sfx}(self) -> {t_str}:\n'
            s += f'        return {reg_name}.{func_read_cached}()\n\n'
            s += f'    async def {reg.name}_read{sfx}(self) -> {t_str}:\n'
            s += f'        return await {reg_name}.{func_read}()\n\n'
            s += f'    def {reg.name}_write_cached{sfx}(self, value : {t_str}):\n'
            s += f'        {reg_name}.{func_write_cached}(value)\n\n'
            s += f'    async def {reg.name}_write{sfx}(self, value : {t_str}):\n'
            s += f'        await {reg_name}.{func_write}(value)\n\n'
            if is_vec_int:
                s += f'    def {reg.name}_read_idx_cached{sfx}(self, idx : int) -> int:\n'
                s += f'        return {reg_name}.{func_read_idx_cached}(idx)\n\n'
                s += f'    async def {reg.name}_read_idx{sfx}(self, idx : int) -> int:\n'
                s += f'        return await {reg_name}.{func_read_idx}(idx)\n\n'
                s += f'    def {reg.name}_write_idx_cached{sfx}(self, idx : int, val : int):\n'
                s += f'        {reg_name}.{func_write_idx_cached}(idx, val)\n\n'
                s += f'    async def {reg.name}_write_idx{sfx}(self, idx : int, val : int):\n'
                s += f'        await {reg_name}.{func_write_idx}(idx, val)\n\n'
        case Acc.wt:
            s += f'    def {reg.name}_read_cached{sfx}(self) -> {t_str}:\n'
            s += f'        return {reg_name}.{func_read_cached}()\n\n'
            s += f'    async def {reg.name}_read{sfx}(self) -> {t_str}:\n'
            s += f'        return await {reg_name}.{func_read}()\n\n'
            # a wt reg is triggered with write_trigger (the regio sees a write
            # event), the write_cached functions only touch the cache
            if not is_vec_int:
                s += f'    def {reg.name}_write_cached{sfx}(self, value : {t_str}):\n'
                s += f'        {reg_name}.{func_write_cached}(value)\n\n'
                s += f'    async def {reg.name}_write_trigger{sfx}(self, value : {t_str}):\n'
                s += f'        await {reg_name}.{func_write}(value)\n\n'
            if is_vec_int:
                s += f'    def {reg.name}_read_idx_cached{sfx}(self, idx : int) -> int:\n'
                s += f'        return {reg_name}.{func_read_idx_cached}(idx)\n\n'
                s += f'    async def {reg.name}_read_idx{sfx}(self, idx : int) -> int:\n'
                s += f'        return await {reg_name}.{func_read_idx}(idx)\n\n'
                s += f'    def {reg.name}_write_idx_cached{sfx}(self, idx : int, val : int):\n'
                s += f'        {reg_name}.{func_write_idx_cached}(idx, val)\n\n'
                s += f'    async def {reg.name}_write_trigger_idx{sfx}(self, idx : int, val : int):\n'
                s += f'        await {reg_name}.{func_write_idx}(idx, val)\n\n'
        case _:
            assert False

    if has_v_convert(reg):
        # The functions above bypass the value conversion, the ones below take
        # and give the user value: v_check it, then convert it with v_convert,
        # a read converts the register value with the inverse of v_convert.
        t_str_user     = value_user_type_str_py(reg)
        t_str_user_one = value_user_type_str_py(reg, ignore_vec=True)
        s += f'    # {reg.name}: value conversion, see the recipe v_convert / v_type\n'
        match reg.acc:
            case Acc.k:
                assert False, 'a constant register cannot have a v_convert'
            case Acc.ro | Acc.rc | Acc.rw | Acc.wt:
                s += f'    def {reg.name}_read_cached(self) -> {t_str_user}:\n'
                s += f'        return {reg_name}.read_converted_cached()\n\n'
                if reg.acc == Acc.rc:
                    s += f'    async def {reg.name}_read(self, clear : bool) -> {t_str_user}:\n'
                    s += f'        val = await {reg_name}.read_converted()\n'
                    s += f'        if clear:\n'
                    s += f'            await self.{reg.name}_clear()\n'
                    s += f'        return val\n\n'
                else:
                    s += f'    async def {reg.name}_read(self) -> {t_str_user}:\n'
                    s += f'        return await {reg_name}.read_converted()\n\n'
                if reg.acc == Acc.rw:
                    s += f'    def {reg.name}_write_cached(self, value : {t_str_user}):\n'
                    s += f'        {reg_name}.write_converted_cached(value)\n\n'
                    s += f'    async def {reg.name}_write(self, value : {t_str_user}):\n'
                    s += f'        await {reg_name}.write_converted(value)\n\n'
                if reg.acc == Acc.wt and not is_vec_int:
                    s += f'    def {reg.name}_write_cached(self, value : {t_str_user}):\n'
                    s += f'        {reg_name}.write_converted_cached(value)\n\n'
                    s += f'    async def {reg.name}_write_trigger(self, value : {t_str_user}):\n'
                    s += f'        await {reg_name}.write_converted(value)\n\n'
                if is_vec_int:
                    s += f'    def {reg.name}_read_idx_cached(self, idx : int) -> {t_str_user_one}:\n'
                    s += f'        return {reg_name}.read_converted_idx_cached(idx)\n\n'
                    s += f'    async def {reg.name}_read_idx(self, idx : int) -> {t_str_user_one}:\n'
                    s += f'        return await {reg_name}.read_converted_idx(idx)\n\n'
                    if reg.acc == Acc.rw:
                        s += f'    def {reg.name}_write_idx_cached(self, idx : int, val : {t_str_user_one}):\n'
                        s += f'        {reg_name}.write_converted_idx_cached(idx, val)\n\n'
                        s += f'    async def {reg.name}_write_idx(self, idx : int, val : {t_str_user_one}):\n'
                        s += f'        await {reg_name}.write_converted_idx(idx, val)\n\n'
                    if reg.acc == Acc.wt:
                        s += f'    def {reg.name}_write_idx_cached(self, idx : int, val : {t_str_user_one}):\n'
                        s += f'        {reg_name}.write_converted_idx_cached(idx, val)\n\n'
                        s += f'    async def {reg.name}_write_trigger_idx(self, idx : int, val : {t_str_user_one}):\n'
                        s += f'        await {reg_name}.write_converted_idx(idx, val)\n\n'
    return s

def all_reg_value_functions_str_is_flag(reg : RecipeReg) -> str:
    assert reg.flags is not None
    assert reg.t.kind == ValueKind.flag
    reg_name = reg_to_inst_str(reg)

    s = ''
    s += f'    # ------------------\n'
    s += f'    # {reg.name}:Start\n'
    s += f'    #    {reg.desc}"\n'
    if reg.acc != Acc.k:

        s += f'    @property\n'
        s += f'    def {reg.name}_inst(self) -> skmap.Reg:\n'
        s += f'        return {reg_name} \n\n'
        s += f'    async def {reg.name}_update_cache(self):\n'
        s += f'        _ = await {reg_name}.read_bytes() \n\n'
        s += f'    async def {reg.name}_write_cache(self):\n'
        s += f'        await {reg_name}.write_cache() \n\n'

        if reg.acc == Acc.rc:
            s += f'    async def {reg.name}_clear(self):\n'
            s += f'        await {reg_name}.write_zero()\n\n'


    for f in reg.flags:
        if isinstance(reg, RecipeK):
            f_name =  name_to_reg_k(f.name)
        else:
            assert isinstance(reg, RecipeVar)
            f_name = name_to_reg_var(f.name)

        if f.vec_len != None:
            t_str = 'list[bool]'
            func_read_cached  = 'read_list_bool_cached'
            func_read         = 'read_list_bool'
            func_write_cached = 'write_list_bool_cached'
            func_write        = 'write_list_bool'

            s += f'    @property\n'
            s += f'    def {f.name}_len(self) -> int:\n'
            s += f'        "{f.desc}"\n'
            s += f'        return {to_python_source(f.vec_len)}\n\n'

        else:
            t_str = 'bool'
            func_read_cached  = 'read_bool_cached'
            func_read         = 'read_bool'
            func_write_cached = 'write_bool_cached'
            func_write        = 'write_bool'
        match reg.acc:
            case Acc.k:
                s += f'    @property\n'
                s += f'    def {f.name}(self) -> {t_str}:\n'
                s += f'        return {f_name}.{func_read_cached}()\n\n'
            case Acc.ro | Acc.rc:
                s += f'    def {f.name}_read_cached(self) -> {t_str}:\n'
                s += f'        return {f_name}.{func_read_cached}()\n\n'
                s += f'    async def {f.name}_read(self) -> {t_str}:\n'
                s += f'        return await {f_name}.{func_read}()\n\n'
            case Acc.rw:
                s += f'    def {f.name}_read_cached(self) -> {t_str}:\n'
                s += f'        return {f_name}.{func_read_cached}()\n\n'
                s += f'    async def {f.name}_read(self) -> {t_str}:\n'
                s += f'        return await {f_name}.{func_read}()\n\n'
                s += f'    def {f.name}_write_cached(self, value : {t_str}):\n'
                s += f'        {f_name}.{func_write_cached}(value)\n\n'
                s += f'    async def {f.name}_write(self, value : {t_str}):\n'
                s += f'        await {f_name}.{func_write}(value)\n\n'
            case Acc.wt:
                s += f'    def {f.name}_read_cached(self) -> {t_str}:\n'
                s += f'        return {f_name}.{func_read_cached}()\n\n'
                s += f'    async def {f.name}_read(self) -> {t_str}:\n'
                s += f'        return await {f_name}.{func_read}()\n\n'
                s += f'    async def {f.name}_trigger(self, value : {t_str}):\n'
                s += f'        await {f_name}.{func_write}(value)\n\n'
                s += f'    def {f.name}_write_cached(self, value : {t_str}):\n'
                s += f'        {f_name}.{func_write_cached}(value)\n\n'
            case _:
                assert False

    s += f'    # {reg.name}:End\n'
    s += f'    # ------------------\n\n'

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
    if reg.flags is not None:
        return all_reg_value_functions_str_is_flag(reg)
    else:
        return all_reg_value_functions_str_not_flag(reg)


def all_mem_value_functions_str(memv : RecipeMem) -> str:
    inst = name_to_ext_mem(memv.name)
    inst_type = "skmap.ExternalMem"
    s = ''
    s += f'    # {memv.name}: {memv.desc}\n'
    s += f'    @property\n'
    s += f'    def {memv.name}_inst(self) -> {inst_type}:\n'
    s += f'        return {inst}\n\n'
    s += f'    @property\n'
    s += f'    def {memv.name}_size(self) -> int:\n'
    s += f'        return {inst}.size\n\n'
    if memv.acc == Acc.rc:
        s += f'    async def {memv.name}_clear(self, addr : int, size : int) -> bytes:\n'
        s += f'      await {inst}.write(addr, bytes(size))\n\n'
        s += f'    async def {memv.name}_read(self, addr : int, size : int, clear : bool = False) -> bytes:\n'
        s += f'      data = await {inst}.read(addr, size)\n'
        s += f'      if clear:\n'
        s += f'          await {memv.name}_clear(addr, size)\n'
        s += f'      return data\n\n'
    else:
        if memv.acc in (Acc.rw, Acc.wt):
            s += f'    async def {memv.name}_write(self, addr : int, data : bytes) -> None:\n'
            s += f'      return await {inst}.write(addr, data)\n\n'
        s += f'    async def {memv.name}_read(self, addr : int, size : int) -> bytes:\n'
        s += f'      return await {inst}.read(addr, size)\n\n'
    return s;

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
        return 0x{recipe.checksum_str()}\n

    @classmethod
    def skmap_ver_major(cls) -> int:
        return {SKMAP_VER_MAJOR}

    @classmethod
    def skmap_ver_minor(cls) -> int:
        return {SKMAP_VER_MINOR}

    @classmethod
    def skmap_ver_patch(cls) -> int:
        return {SKMAP_VER_PATCH}

    @classmethod
    def skmap_ver_str(cls) -> str:
        return \"{SKMAP_VER_STR}\"\n\n""")

        for ipkgv in recipe.ipkg:
            py_f.write(all_ipkg_value_parameters_str(ipkgv))

        for kv in recipe.k:
            py_f.write(all_reg_value_functions_str(kv))

        for varv in recipe.var:
            py_f.write(all_reg_value_functions_str(varv))

        for  memv in recipe.mem:
            py_f.write(all_mem_value_functions_str(memv))

        py_f.write("""
    def _init_reg_map_k(self):
""")
        for kv in recipe.k:
            name_k = name_to_reg_k(kv.name)
            if kv.flags is not None:
                for f in kv.flags:
                    vec_len_param = '' if f.vec_len is None else f' vec_len={to_python_source(f.vec_len)},'
                    bit = to_python_source(f.bit)
                    py_f.write(f"        {name_to_reg_k(f.name)} = skmap.RFlagK(name='{f.name}', bit={bit}, ass=skmap.Ass.{f.ass.to_str()},{vec_len_param} desc='{f.desc}')\n")
                py_f.write("        flags = [")
                for f in kv.flags: py_f.write(f" {name_to_reg_k(f.name)}, ")
                py_f.write("]\n")
                width = to_python_source(kv.t.width)
                py_f.write(f"        {name_k} = skmap.RegFlagsK(self, name='{kv.name}', width={width}, flags=flags, desc='{kv.desc}')\n")
            else:
                t_str = value_type_str(kv.t)
                reg_type = 'RegVecK' if kv.t.is_vec else 'RegK'
                py_f.write(f"        {name_k} = skmap.{reg_type}(self, name='{kv.name}', value_type={t_str}, desc='{kv.desc}'{value_check_str_py(kv)})\n")
            py_f.write(f"        self._add_reg_k({name_k})\n\n")

        py_f.write("""    def _init_reg_map_var(self):\n""")
        for varv in recipe.var:
            name_var = name_to_reg_var(varv.name)
            # if varv.t.kind == ValueKind.flag:
            if varv.flags is not None:
                for f in varv.flags:
                    vec_len_param = '' if f.vec_len is None else f' vec_len={to_python_source(f.vec_len)},'
                    bit = to_python_source(f.bit)
                    py_f.write(f"        {name_to_reg_var(f.name)} = skmap.RFlag(name='{f.name}', bit={bit}, ass=skmap.Ass.{f.ass.to_str()},{vec_len_param} desc='{f.desc}')\n")
                py_f.write("        flags = [")
                for f in varv.flags: py_f.write(f" {name_to_reg_var(f.name)}, ")
                py_f.write("]\n")
                w = to_python_source(varv.t.width)
                py_f.write(f"        {name_var} = skmap.RegFlags(self, name='{varv.name}', width={w}, acc=skmap.Acc.{varv.acc}, flags=flags, desc='{varv.desc}')\n")
            else:
                ass_str = ''
                if varv.ass != Ass.none:
                    ass_str = f', ass=skmap.Ass.{varv.ass.to_str()}'

                t_str = value_type_str(varv.t)
                reg_type = 'RegVec' if varv.t.is_vec else 'Reg'
                py_f.write(f"        {name_var} = skmap.{reg_type}(self, name='{varv.name}', value_type={t_str}{ass_str}, acc=skmap.Acc.{varv.acc}, desc='{varv.desc}'{value_check_str_py(varv)}{value_convert_str_py(varv)})\n")
            py_f.write(f"        self._add_reg_var({name_var})\n\n")

        py_f.write("    def _init_external_mem(self):\n")
        py_f.write(f"        assert self.len_external_mem == {len(recipe.mem)}, 'Unexpected number of external mem in fw'\n")
        for ii, memv in enumerate(recipe.mem):
            name_mem = name_to_ext_mem(memv.name)
            t_str = value_type_str(memv.t)
            py_f.write(f"        {name_mem} = self.external_mem_at({ii})\n")
            py_f.write(f"        {name_mem}.details(name='{memv.name}', value_type={t_str}, acc=skmap.Acc.{memv.acc}, desc='{memv.desc}')\n")
        if len(recipe.mem) > 0:
            py_f.write('\n')
        py_f.write(f"skmap.register_Module({recipe.sw_module})\n")
