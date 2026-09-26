import os
from pathlib import Path
from datetime import datetime
from typing import Union

from .code_generator_parse_resolvable import ResolvableFunctionOperation, ResolvableT, ResolvableFunctionBuiltIn, BultiInOperation
from .code_generator_parse_recipe import ValueTypeUnresolved, parse_recipe_file, RecipeIpkg, RecipeK, RecipeVar, RecipeReg, RecipeMem
from .basic_types import Acc, Ass, ValueKind, ValueType, SKMAP_VER_STR, SKMAP_VER_MAJOR, SKMAP_VER_MINOR, SKMAP_VER_PATCH
from . import code_generator_sw_common as common

namespace = "hdlskel::skmap::autogen"

SW = common.Sw.cpp

def name_to_ipkg(name : str) -> str:
    return name

def name_to_reg_k(name : str) -> str:
    return "m_k_"+name

def name_to_reg_var(name : str) -> str:
    return "m_var_"+name

def name_to_ext_mem(name : str) -> str:
    return "m_mem_"+name

def reg_to_inst_str(reg : RecipeReg) -> str:
    if isinstance(reg, Union[RecipeK, RecipeIpkg]):
        return name_to_reg_k(reg.name)
    assert isinstance(reg, RecipeVar)
    return name_to_reg_var(reg.name)

def to_cpp_source(node: ResolvableT) -> str:
    """Render a ResolvableT tree back out as a C++ source-code expression string."""
    # if isinstance(node, bool):
    #     return str(int(node))
    if isinstance(node, int):
        return str(node)
    if isinstance(node, str):   # plain-string leaf (e.g. name_to_k[name] = name)
        return node
    if isinstance(node, RecipeIpkg):
        return f'{node.name}()'
    if isinstance(node, RecipeK):
        return f'{node.name}()'
    if isinstance(node, ResolvableFunctionOperation):
        if node.op == BultiInOperation.power:
            # C++ has no ** operator, std::pow returns double, recipe math is integer
            return f'static_cast<int>(std::pow({to_cpp_source(node.lhs)}, {to_cpp_source(node.rhs)}))'
        return f'({to_cpp_source(node.lhs)} {node.op} {to_cpp_source(node.rhs)})'
    if isinstance(node, ResolvableFunctionBuiltIn):
        args = ', '.join(to_cpp_source(p) for p in node.params)
        return f'recipe_functions::{node.func.name}({args})'
    if hasattr(node, 'name'):  # RecipeK / RecipeIpkg leaf
        return node.name #type:ignore
    raise TypeError(f'Cannot render {node!r} {type(node)=} to cpp source')

def value_type_str(value_type : Union[ValueType, ValueTypeUnresolved]):
    assert value_type.width is not None
    w = to_cpp_source(value_type.width)
    t_str = f"make_ValueType({cpp_value_kind_str(value_type.kind)}, {w}"
    if value_type.is_vec:
        assert value_type.vec_len is not None
        vec_len = to_cpp_source(value_type.vec_len)
        t_str += f", {vec_len}"
    t_str += ")"
    return t_str

def cpp_value_kind_str(value_kind : ValueKind):
    return f'ValueKind::{value_kind.str()}_'

def value_ret_type_str(t : Union[ValueType, ValueTypeUnresolved], ignore_vec = False, wr = False):
    match t.kind:
        case ValueKind.char:
            rt = 'char'
        case ValueKind.uint:
            rt = 'uint_t'
        case ValueKind.sint:
            rt = 'sint_t'
        case ValueKind.bits:
            rt = 'uint_t'
        case ValueKind.flag:
            rt = 'uint_t'
        case _:
            assert False
    if not ignore_vec and t.is_vec:
        if t.kind == ValueKind.char:
            rt = 'std::string'
        else:
            rt = f'std::vector<{rt}>'
            if wr:
                rt = f'const {rt} &'
    return rt

def reg_inst_type_str(reg : RecipeReg) -> str:
    if reg.t.kind == ValueKind.flag:
        if reg.flags is not None:
            return 'RegFlags'
    return 'RegVec' if reg.t.is_vec else 'Reg'

def is_vec_int(t : Union[ValueType, ValueTypeUnresolved]) -> bool:
    return t.is_vec and t.kind in (ValueKind.uint, ValueKind.sint, ValueKind.bits)

def all_ipkg_value_parameters_str(ipkgv : RecipeIpkg) -> str:
    if isinstance(ipkgv.value, str):
        # plain-string leaf (char vector ipkg)
        t_str = 'std::string'
        value = f'"{ipkgv.value}"'
    else:
        t_str = 'int'
        value = to_cpp_source(ipkgv.value)

    s = ''
    s += f'    {t_str} {ipkgv.name}() const {{ return {value}; }}\n'
    return s

def all_reg_value_functions_str_not_flag(reg : RecipeReg) -> str:
    assert reg.t.width is not None
    reg_name = reg_to_inst_str(reg)
    t_str = value_ret_type_str(reg.t)
    t_str_wr = value_ret_type_str(reg.t, wr=True)
    t_elem_str = value_ret_type_str(reg.t, ignore_vec=True)
    func_read_cached = read_value_function_str (reg.t, cached=True,  sw=SW)
    func_read        = read_value_function_str (reg.t, cached=False, sw=SW)
    func_write_cached= write_value_function_str(reg.t, cached=True,  sw=SW)
    func_write       = write_value_function_str(reg.t, cached=False, sw=SW)
    kind_f_s = _value_kind_function_str(reg.t.kind)
    func_read_idx_cached = f'read_idx_{kind_f_s}_cached'
    func_read_idx = f'read_idx_{kind_f_s}'
    func_write_idx_cached = f'write_idx_{kind_f_s}_cached'
    func_write_idx = f'write_idx_{kind_f_s}'

    s = ''
    s += f'    //{reg.name}: {reg.desc}\n'
    s += f'    std::shared_ptr<{reg_inst_type_str(reg)}> {reg.name}_inst() const {{ return {reg_name}; }}\n'

    if isinstance(reg, RecipeVar):
        if reg.max is not None:
            s += f'    int {reg.name}_max() const {{ return {to_cpp_source(reg.max)}; }}\n'
        if reg.min is not None:
            s += f'    int {reg.name}_min() const {{ return {to_cpp_source(reg.min)}; }}\n'

    match reg.acc:
        case Acc.k:
            s += f'    {t_str} {reg.name}() const {{ return {reg_name}->{func_read_cached}(); }}\n'
        case Acc.ro:
            s += f'    {t_str} {reg.name}_read_cached() const {{ return {reg_name}->{func_read_cached}(); }}\n'
            s += f'    {t_str} {reg.name}_read() {{ return {reg_name}->{func_read}(); }}\n'
            if is_vec_int(reg.t):
                s += f'    {t_elem_str} {reg.name}_read_idx_cached(addr_t idx) const {{ return {reg_name}->{func_read_idx_cached}(idx); }}\n'
                s += f'    {t_elem_str} {reg.name}_read_idx(addr_t idx) {{ return {reg_name}->{func_read_idx}(idx); }}\n'
        case Acc.rc:
            s += f'    {t_str} {reg.name}_read_cached() const {{ return {reg_name}->{func_read_cached}(); }}\n'
            s += f'    {t_str} {reg.name}_read(bool clear) {{\n'
            s += f'        {t_str} val = {reg_name}->{func_read}();\n'
            s += f'        if ( clear ) {{ {reg.name}_clear(); }}\n'
            s += f'        return val;\n'
            s += f'    }}\n'
            s += f'    void {reg.name}_clear() {{ {reg_name}->write_zero(); }}\n'
            if is_vec_int(reg.t):
                s += f'    {t_elem_str} {reg.name}_read_idx_cached(addr_t idx) const {{ return {reg_name}->{func_read_idx_cached}(idx); }}\n'
                s += f'    {t_elem_str} {reg.name}_read_idx(addr_t idx) {{ return {reg_name}->{func_read_idx}(idx); }}\n'
                s += f'    void {reg.name}_clear_idx(addr_t idx) {{ {reg_name}->{func_write_idx}(idx, 0); }}\n'
        case Acc.rw:
            s += f'    {t_str} {reg.name}_read_cached() const {{ return {reg_name}->{func_read_cached}(); }}\n'
            s += f'    {t_str} {reg.name}_read() {{ return {reg_name}->{func_read}(); }}\n'
            s += f'    void {reg.name}_write_cached( {t_str_wr} value ) {{ {reg_name}->{func_write_cached}(value); }}\n'
            s += f'    void {reg.name}_write( {t_str_wr} value ) {{ {reg_name}->{func_write}(value); }}\n'
            if is_vec_int(reg.t):
                s += f'    {t_elem_str} {reg.name}_read_idx_cached(addr_t idx) const {{ return {reg_name}->{func_read_idx_cached}(idx); }}\n'
                s += f'    {t_elem_str} {reg.name}_read_idx(addr_t idx) {{ return {reg_name}->{func_read_idx}(idx); }}\n'
                s += f'    void {reg.name}_write_idx_cached(addr_t idx, {t_elem_str} val) {{ {reg_name}->{func_write_idx_cached}(idx, val); }}\n'
                s += f'    void {reg.name}_write_idx(addr_t idx, {t_elem_str} val) {{ {reg_name}->{func_write_idx}(idx, val); }}\n'
        case Acc.wt:
            s += f'    {t_str} {reg.name}_read_cached() const {{ return {reg_name}->{func_read_cached}(); }}\n'
            s += f'    {t_str} {reg.name}_read() {{ return {reg_name}->{func_read}(); }}\n'
            if not is_vec_int(reg.t):
                s += f'    void {reg.name}_write_trigger( {t_str_wr} value ) {{ {reg_name}->{func_write}(value); }}\n'
            if is_vec_int(reg.t):
                s += f'    {t_elem_str} {reg.name}_read_idx_cached(addr_t idx) const {{ return {reg_name}->{func_read_idx_cached}(idx); }}\n'
                s += f'    {t_elem_str} {reg.name}_read_idx(addr_t idx) {{ return {reg_name}->{func_read_idx}(idx); }}\n'
                s += f'    void {reg.name}_write_trigger_idx(addr_t idx, {t_elem_str} val) {{ {reg_name}->{func_write_idx}(idx, val); }}\n'
        case _:
            assert False
    return s

def all_reg_value_functions_str_is_flag(reg : RecipeReg) -> str:
    assert reg.t.kind == ValueKind.flag
    reg_name = reg_to_inst_str(reg)

    s = ''
    s += f'    //{reg.name}: {reg.desc}\n'
    if reg.acc != Acc.k:
        s += f'    std::shared_ptr<{reg_inst_type_str(reg)}> {reg.name}_inst() const {{ return {reg_name}; }}\n'
        s += f'    void {reg.name}_update_cache() {{ {reg_name}->update_cache(); }}\n'
        if reg.acc == Acc.rc:
            s += f'    void {reg.name}_clear() {{ {reg_name}->write_zero(); }}\n'

    if reg.flags is not None:
        flags = reg.flags
    else:
        # a flag register without an explicit flag list is a single flag of its own
        flags = [reg]
    for f in flags:
        if isinstance(reg, RecipeK):
            f_name =  name_to_reg_k(f.name)
        else:
            assert isinstance(reg, RecipeVar)
            f_name = name_to_reg_var(f.name)

        if f.vec_len != None:
            t_str = 'std::vector<bool>'
            t_str_c = f'const {t_str} &'
            func_read_cached = 'read_vec_bool_cached'
            func_read        = 'read_vec_bool'
            func_write_cached= 'write_vec_bool_cached'
            func_write       = 'write_vec_bool'

            s += f'    size_t {f.name}_len() const {{ return {to_cpp_source(f.vec_len)}; }}\n'

        else:
            t_str = 'bool'
            t_str_c = 'bool'
            func_read_cached = 'read_bool_cached'
            func_read        = 'read_bool'
            func_write_cached= 'write_bool_cached'
            func_write       = 'write_bool'
        match reg.acc:
            case Acc.k:
                s += f'    {t_str} {f.name}() const {{ return {f_name}->{func_read_cached}(); }}\n'

            case Acc.ro | Acc.rc:
                s += f'    {t_str} {f.name}_read_cached() const {{ return {f_name}->{func_read_cached}(); }}\n'
                s += f'    {t_str} {f.name}_read() {{ return {f_name}->{func_read}(); }}\n'
            case Acc.rw:
                s += f'    {t_str} {f.name}_read_cached() const {{ return {f_name}->{func_read_cached}(); }}\n'
                s += f'    {t_str} {f.name}_read() {{ return {f_name}->{func_read}(); }}\n'
                s += f'    void {f.name}_write_cached( {t_str_c} value ) {{ {f_name}->{func_write_cached}(value); }}\n'
                s += f'    void {f.name}_write( {t_str_c} value ) {{ {f_name}->{func_write}(value); }}\n'
            case Acc.wt:
                s += f'    {t_str} {f.name}_read_cached() const {{ return {f_name}->{func_read_cached}(); }}\n'
                s += f'    {t_str} {f.name}_read() {{ return {f_name}->{func_read}(); }}\n'
                s += f'    void {f.name}_trigger( {t_str_c} value ) {{ {f_name}->{func_write}(value); }}\n'
                s += f'    void {f.name}_write_cached( {t_str_c} value ) {{ {f_name}->{func_write_cached}(value); }}\n'
            case _:
                assert False
    return s

def all_reg_value_functions_str(reg : RecipeReg) -> str:
    if reg.t.kind == ValueKind.flag:
        return all_reg_value_functions_str_is_flag(reg)
    else:
        return all_reg_value_functions_str_not_flag(reg)

def all_mem_value_functions_str(memv : RecipeMem) -> str:
    inst = name_to_ext_mem(memv.name)
    s = ''
    s += f'    //{memv.name}: {memv.desc}\n'
    s += f'    std::shared_ptr<ExternalMem> {memv.name}_inst() const {{ return {inst}; }}\n'
    s += f'    addr_t {memv.name}_size() const {{ return {inst}->size(); }}\n'
    if memv.acc == Acc.rc:
        s += f'    void {memv.name}_clear(addr_t addr, addr_t size) {{ {inst}->write(addr, std::vector<uint8_t>(size)); }}\n'
        s += f'    std::vector<uint8_t> {memv.name}_read(addr_t addr, addr_t size, bool clear = false) {{\n'
        s += f'        std::vector<uint8_t> data = {inst}->read(addr, size);\n'
        s += f'        if ( clear ) {{ {memv.name}_clear(addr, size); }}\n'
        s += f'        return data;\n'
        s += f'    }}\n'
    else:
        if memv.acc in (Acc.rw, Acc.wt):
            s += f'    void {memv.name}_write(addr_t addr, const std::vector<uint8_t> & data) {{ {inst}->write(addr, data); }}\n'
        s += f'    std::vector<uint8_t> {memv.name}_read(addr_t addr, addr_t size) {{ return {inst}->read(addr, size); }}\n'
    return s

def hpp_include_str(hpp_file : Path, cpp_file : Path) -> str:
    """Work out the #include line for the hpp from the cpp file.
    If the hpp path contains the hdlskel/skmap include root, use the
    canonical include path from that point on, else use a path relative
    to the cpp file."""
    parts = hpp_file.parts
    for ii, part in enumerate(parts):
        if part == 'hdlskel' and ii + 1 < len(parts) and parts[ii+1] == 'skmap':
            return '/'.join(parts[ii:])
    return os.path.relpath(hpp_file, start=cpp_file.parent).replace('\\', '/')

def generate_cpp_module(recipe_file : Path, hpp_file : Path, cpp_file : Path):
    recipe = parse_recipe_file(recipe_file)

    file_header = f"""//-------------------------------------------------------------------------------
// NOTE: this file is autogenerated:
//    * From {__file__}
//    * On {datetime.now()} 
//    * Using HDLSkel SkMap {SKMAP_VER_STR}
//    * For {recipe.name} {recipe.id} v{recipe.version}
//    * Checksum 0x{recipe.checksum_str()}
//-------------------------------------------------------------------------------"""

    with open(hpp_file, 'w') as hpp_f, open(cpp_file, 'w') as cpp_f:
        hpp_f.write(f"""{file_header}
#include "hdlskel/skmap/basic_types.hpp"
#include "hdlskel/skmap/reg.hpp"
#include "hdlskel/skmap/module.hpp"
#include "hdlskel/skmap/recipe_functions.hpp"

#include <cassert>
#include <cmath>
#include <memory>
#include <string>
#include <vector>

namespace {namespace} {{

class {recipe.sw_module} : public skmap::Module {{
public:
    static std::string class_name() {{ return "{recipe.name}"; }}
    static id_t class_id() {{
        const static id_t id = id_str_to_id("{recipe.id}");
        return id;
    }};
    constexpr static version_t   class_version   = {recipe.version};
    constexpr static checksum_t  class_checksum  = 0x{recipe.checksum_str()};

    std::string        name()     const override {{ return {recipe.sw_module}::class_name(); }}
    id_t        id()       const override {{ return {recipe.sw_module}::class_id(); }}
    version_t   version()  const override {{ return {recipe.sw_module}::class_version; }}
    checksum_t  checksum() const override {{ return {recipe.sw_module}::class_checksum; }}

    static int  skmap_ver_major() {{ return skmap::ver_major; }}
    static int  skmap_ver_minor() {{ return skmap::ver_minor; }}
    static int  skmap_ver_patch() {{ return skmap::ver_patch; }}
    static std::string skmap_ver_str() {{ return skmap::ver_str; }}

    static bool registered;
""")
        for ipkgv in recipe.ipkg:
            hpp_f.write(all_ipkg_value_parameters_str(ipkgv))

        for kv in recipe.k:
            hpp_f.write(all_reg_value_functions_str(kv))

        for varv in recipe.var:
            hpp_f.write(all_reg_value_functions_str(varv))

        for memv in recipe.mem:
            hpp_f.write(all_mem_value_functions_str(memv))

        hpp_f.write("""
protected:
    void init_reg_map_k()   override;
    void init_reg_map_var() override;
""")
        if len(recipe.mem) > 0:
            hpp_f.write("    void init_last() override;\n")
        hpp_f.write(f"""
    virtual std::shared_ptr<Module> make_empty() const override {{
        return std::make_shared<{recipe.sw_module}>();
    }};

private:
""")
        for kv in recipe.k:
            name_k = name_to_reg_k(kv.name)
            if kv.t.kind == ValueKind.flag and kv.flags is not None:
                for f in kv.flags:
                    f_name = name_to_reg_k(f.name)
                    f_class = 'RFlagVec' if f.is_vec else 'RFlag'
                    hpp_f.write(f'    std::shared_ptr<{f_class}> {f_name};\n')
            hpp_f.write(f'    std::shared_ptr<{reg_inst_type_str(kv)}> {name_k};\n')

        for varv in recipe.var:
            name_var = name_to_reg_var(varv.name)
            if varv.t.kind == ValueKind.flag and varv.flags is not None:
                for f in varv.flags:
                    f_name = name_to_reg_var(f.name)
                    f_class = 'RFlagVec' if f.is_vec else 'RFlag'
                    hpp_f.write(f'    std::shared_ptr<{f_class}> {f_name};\n')
            hpp_f.write(f'    std::shared_ptr<{reg_inst_type_str(varv)}> {name_var};\n')

        for memv in recipe.mem:
            hpp_f.write(f'    std::shared_ptr<ExternalMem> {name_to_ext_mem(memv.name)};\n')

        hpp_f.write(f"}};\n")
        hpp_f.write(f"\n}}\n")

        cpp_f.write(f"""{file_header}

#include "{hpp_include_str(hpp_file, cpp_file)}"

namespace {namespace} {{

bool {recipe.sw_module}::registered = Module::register_module(std::make_shared<{recipe.sw_module}>());

""")

        cpp_f.write(f"""void {recipe.sw_module}::init_reg_map_k() {{
""")
        for kv in recipe.k:
            name_k = name_to_reg_k(kv.name)
            if kv.t.kind == ValueKind.flag and kv.flags is not None:
                for f in kv.flags:
                    bit = to_cpp_source(f.bit)
                    if f.vec_len is None:
                        cpp_f.write(f'    {name_to_reg_k(f.name)} = make_r_flag("{f.name}", {bit}, Ass::{f.ass.to_str()}, "{f.desc}");\n')
                    else:
                        vec_len = to_cpp_source(f.vec_len)
                        cpp_f.write(f'    {name_to_reg_k(f.name)} = make_r_flag_vec("{f.name}", {bit}, Ass::{f.ass.to_str()}, "{f.desc}", {vec_len});\n')
                cpp_f.write(f"    std::vector<std::shared_ptr<RFlag>> {name_k}_flags;\n")
                for f in kv.flags:
                    cpp_f.write(f"    push_back_flag({name_k}_flags, {name_to_reg_k(f.name)});\n")
                width = to_cpp_source(kv.t.width)
                cpp_f.write(f'    {name_k} = make_reg_flags_k("{kv.name}", {width}, {name_k}_flags, "{kv.desc}");\n')
                cpp_f.write(f'    add_reg_k({name_k});\n')
            else:
                t_str = value_type_str(kv.t)
                reg_make = 'make_reg_vec_k' if kv.t.is_vec else 'make_reg_k'
                cpp_f.write(f'    {name_k} = {reg_make}("{kv.name}", {t_str}, "{kv.desc}");\n')
                cpp_f.write(f'    add_reg_k({name_k});\n')
        cpp_f.write(f"}}\n\n")

        cpp_f.write(f"""void {recipe.sw_module}::init_reg_map_var() {{
""")
        for varv in recipe.var:
            name_var = name_to_reg_var(varv.name)
            if varv.t.kind == ValueKind.flag and varv.flags is not None:
                for f in varv.flags:
                    bit = to_cpp_source(f.bit)
                    if f.vec_len is None:
                        cpp_f.write(f'    {name_to_reg_var(f.name)} = make_r_flag("{f.name}", {bit}, Ass::{f.ass.to_str()}, "{f.desc}");\n')
                    else:
                        vec_len = to_cpp_source(f.vec_len)
                        cpp_f.write(f'    {name_to_reg_var(f.name)} = make_r_flag_vec("{f.name}", {bit}, Ass::{f.ass.to_str()}, "{f.desc}", {vec_len});\n')
                cpp_f.write(f"    std::vector<std::shared_ptr<RFlag>> {name_var}_flags;\n")
                for f in varv.flags:
                    cpp_f.write(f"    push_back_flag({name_var}_flags, {name_to_reg_var(f.name)});\n")
                width = to_cpp_source(varv.t.width)
                cpp_f.write(f'    {name_var} = make_reg_flags("{varv.name}", Acc::{varv.acc}, {width}, {name_var}_flags, "{varv.desc}");\n')
                cpp_f.write(f"    add_reg_var({name_var});\n")
            else:
                t_str = value_type_str(varv.t)
                reg_make = 'make_reg_vec' if varv.t.is_vec else 'make_reg'
                cpp_f.write(f'    {name_var} = {reg_make}("{varv.name}", Acc::{varv.acc}, {t_str}, "{varv.desc}");\n')
                cpp_f.write(f"    add_reg_var({name_var});\n")
        cpp_f.write(f"}}\n")

        if len(recipe.mem) > 0:
            cpp_f.write(f"""
void {recipe.sw_module}::init_last() {{
    assert(len_external_mem() == {len(recipe.mem)});
""")
            for ii, memv in enumerate(recipe.mem):
                name_mem = name_to_ext_mem(memv.name)
                t_str = value_type_str(memv.t)
                cpp_f.write(f"    {name_mem} = external_mem_at({ii});\n")
                cpp_f.write(f"    {name_mem}->details(\"{memv.name}\", {t_str}, Acc::{memv.acc}, \"{memv.desc}\");\n")
            cpp_f.write(f"}}\n")
        cpp_f.write(f"}}\n")

_value_kind_function_str = common._value_kind_function_str
read_value_function_str  = common.read_value_function_str
write_value_function_str  = common.write_value_function_str
