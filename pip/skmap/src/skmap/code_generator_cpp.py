from pathlib import Path
from datetime import datetime
from typing import Union

from .code_generator_parse_recipe import ValueTypeUnresolved, parse_recipe_file, RecipeK, RecipeVar, RecipeReg, ResolvableFunction
# from basic import promote_to_sw_w, ceil_div
from .basic_types import Acc, Ass, ValueKind, ValueType, SKMAP_VER_STR
from . import code_generator_sw_common as common

namespace = "hdlskel::skmap::autogen"
inc_dir   = "hdlskel/skmap/autogen"

def name_to_reg_k(name : str) -> str:
    return "m_k_"+name

def name_to_reg_var(name : str) -> str:
    return "m_var_"+name


def resolve_k_value(v : RecipeK) -> str:
    return f'{v.name}()'

def cpp_value_kind_str(value_kind : ValueKind):
    return f'ValueKind::{value_kind.str()}_'

def value_type_str(value_type : Union[ValueType, ValueTypeUnresolved]):
    assert value_type.width is not None
    w = resolvable_member_function(value_type.width)
    t_str = f"make_ValueType({cpp_value_kind_str(value_type.kind)}, {w}"
    if value_type.is_vec:
        assert value_type.vec_len is not None
        vec_len = resolvable_member_function(value_type.vec_len)
        t_str += f", {vec_len}"
    t_str += ")"
    return t_str

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
        # if isinstance(t.is_vec, int):
        #     rt = f'std::array<{rt},{t.vec_len}>'
        # else:
        rt = f'std::vector<{rt}>'
        if wr:
            rt = f'const {rt} &'
    return rt


def all_reg_value_functions_str_not_flag(reg : RecipeReg) -> str:
    assert reg.t.width is not None
    reg_name = reg_to_inst_str(reg)
    t_str      = value_ret_type_str(reg.t)
    t_str_wr   = value_ret_type_str(reg.t, wr=True)
    t_elem_str = value_ret_type_str(reg.t, ignore_vec=True)
    func_read_cached = read_value_function_str(reg.t, cached=True)
    func_read        = read_value_function_str(reg.t, cached=False)
    func_write      = write_value_function_str(reg.t)
    kind_f_s = _value_kind_function_str(reg.t.kind)
    func_read_idx_cached = f'read_idx_{kind_f_s}_cached'
    func_read_idx = f'read_idx_{kind_f_s}'
    func_write_idx = f'write_idx_{kind_f_s}'

    s = ''
    s += f'    ValueType {reg.name}_value_type() const {{ return {value_type_str(reg.t)}; }}\n'

    match reg.acc:
        case Acc.k:
            s += f'    {t_str} {reg.name}() const {{ return {reg_name}->{func_read_cached}(); }}\n'
        case Acc.ro:
            s += f'    {t_str} {reg.name}_cached() const {{ return {reg_name}->{func_read_cached}(); }}\n'
            s += f'    {t_str} {reg.name}_read() {{return {reg_name}->{func_read}(); }}\n'
            if reg.t.is_vec:
                s += f'    {t_elem_str} {reg.name}_cached_idx(uint idx) const {{ return {reg_name}->{func_read_idx_cached}(idx); }}\n'
                s += f'    {t_elem_str} {reg.name}_read_idx(uint idx) {{ return {reg_name}->{func_read_idx}(idx); }}\n'
        case Acc.rc:
            s += f'    {t_str} {reg.name}_cached() const {{ return {reg_name}->{func_read_cached}(); }}\n'
            s += f'    {t_str} {reg.name}_read(bool clear) {{\n'
            s += f'        {t_str} val = {reg_name}->{func_read}();\n'
            s += f'        if ( clear ) {{ {reg.name}_clear(); }}\n'
            s += f'        return val;\n'
            s += f'    }}\n'
            s += f'    void {reg.name}_clear(){{ {reg_name}->write_zero(); }}\n'
            if reg.t.is_vec:
                s += f'    {t_elem_str} {reg.name}_cached_idx(uint idx) const {{ return {reg_name}->{func_read_idx_cached}(idx); }}\n'
                s += f'    {t_elem_str} {reg.name}_read_idx(uint idx) {{ return {reg_name}->{func_read_idx}(idx); }}\n'
                s += f'    void {reg.name}_clear_idx(uint idx) {{ {reg_name}->{func_write_idx}(idx, 0); }}\n'
        case Acc.rw:
            s += f'    {t_str} {reg.name}_cached() const {{ return {reg_name}->{func_read_cached}(); }}\n'
            s += f'    {t_str} {reg.name}_read() {{ return {reg_name}->{func_read}(); }}\n'
            s += f'    void {reg.name}_write( {t_str_wr} value ) {{ return {reg_name}->{func_write}(value); }}\n'
            if reg.t.is_vec:
                s += f'    {t_elem_str} {reg.name}_cached_idx ( uint idx ) const {{ return {reg_name}->{func_read_idx_cached}(idx); }}\n'
                s += f'    {t_elem_str} {reg.name}_read_idx( uint idx ) {{ return {reg_name}->{func_read_idx}(idx); }}\n'
                s += f'    void {reg.name}_write_idx( uint idx, {t_elem_str} val ) {{ {reg_name}->{func_write_idx}(idx, val); }}\n'
        case Acc.wt:
            s += f'    {t_str} {reg.name}_cached() const {{ return {reg_name}->{func_read_cached}(); }}\n'
            s += f'    {t_str} {reg.name}_read() {{ return {reg_name}->{func_read}(); }}\n'
            if not reg.t.is_vec:
                s += f'    void {reg.name}_trigger( {t_str_wr} value ) {{ {reg_name}->{func_write}(value); }}\n'
            if reg.t.is_vec:
                s += f'    {t_elem_str} {reg.name}_cached_idx const ( uint idx ) {{ return {reg_name}->{func_read_idx_cached}(idx); }}\n'
                s += f'    {t_elem_str} {reg.name}_read_idx(uint idx) {{ return {reg_name}->{func_read_idx}(idx); }}\n'
                s += f'    void {reg.name}_trigger_idx(uint idx, {t_elem_str} val) {{ {reg_name}->{func_write_idx}(idx, val); }}\n'
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
            t_str = 'std::vector<bool>'
            t_str_c = 'const & std::vector<bool>'
            func_read_cached = 'read_vec_bool_cached'
            func_read        = 'read_vec_bool'
            func_write       = 'write_vec_bool'

            s += f'    size_t {f.name}_size() const {{ return {resolvable_str(f.vec_len)}; }}\n'

        else:
            t_str = 'bool'
            t_str_c = t_str
            func_read_cached = 'read_bool_cached'
            func_read        = 'read_bool'
            func_write       = 'write_bool'
        match reg.acc:
            case Acc.k:
                s += f'    {t_str} {f.name}() {{ return {f_name}->{func_read_cached}(); }}\n'

            case Acc.ro | Acc.rc:
                s += f'    {t_str} {f.name}_cached() const {{ return {f_name}->{func_read_cached}(); }}\n'
                s += f'    {t_str} {f.name}_read() {{ return {f_name}->{func_read}(); }}\n'
            case Acc.rw:
                s += f'    {t_str} {f.name}_cached() const {{ return {f_name}->{func_read_cached}(); }}\n'
                s += f'    {t_str} {f.name}_read() {{ return {f_name}->{func_read}(); }}\n'
                s += f'    void {f.name}_write( {t_str_c} value ) {{ {f_name}->{func_write}(value); }}\n'
            case Acc.wt:
                s += f'    {t_str} {f.name}_cached() const {{return {f_name}->{func_read_cached}(); }}\n'
                s += f'    {t_str} {f.name}_read() {{ return {f_name}->{func_read}(); }}\n'
                s += f'    void {f.name}_trigger( {t_str_c} value ) {{ {f_name}->{func_write}(value); }}\n'
            case _:
                assert False
        if reg.acc in ( Acc.ro, Acc.rw, Acc.wt ):
            s += f'    void {f.name}_update_cache() {{ {f_name}->read_bytes(); }}\n'

        if reg.acc == Acc.rc:
            reg_name = reg_to_inst_str(reg)
            func_write      = write_value_function_str(reg.t)
            s += f'    void {f.name}_clear() {{ {reg_name}->write_zero(); }}\n'

    return s

# def recipe_to_reg_type_k(kv : RecipeK):
#     reg_class = 'RegVec' if kv.t.is_vec else 'Reg'
#     reg_type = f'std::shared_ptr<{reg_class}>'
#     return reg_type

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

#include <cassert>
#include <memory>

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

    static bool registered;
\n""")
        for kv in recipe.k:
            hpp_f.write(all_reg_value_functions_str(kv))

        for varv in recipe.var:
            hpp_f.write(all_reg_value_functions_str(varv))

        hpp_f.write(f"""
protected:
    void init_reg_map_k()   override;
    void init_reg_map_var() override;
""")


        hpp_f.write(f"""
protected:
    virtual std::shared_ptr<Module> make_empty() const override {{
        return std::make_shared<{recipe.sw_module}>();
    }};\n""");


        hpp_f.write(f"\nprivate:\n")
        add_new_line = False
        for kv in recipe.k:
            if add_new_line:
                hpp_f.write('\n')
                add_new_line = False
            name_k = name_to_reg_k(kv.name)
            if kv.t.kind == ValueKind.flag:
                assert kv.flags is not None
                for f in kv.flags:
                    f_name = name_to_reg_k(f.name)
                    f_class = 'RFlagVec' if kv.t.is_vec else 'RFlag'
                    f_type = f'std::shared_ptr<{f_class:8}>'
                    hpp_f.write(f'    {f_type} {f_name};\n')

                t_str = value_type_str(kv.t)
                reg_class = 'RegFlags'
                add_new_line = True
            else:
                t_str = value_type_str(kv.t)
                reg_class = 'RegVec' if kv.t.is_vec else 'Reg'
            reg_type = f'std::shared_ptr<{reg_class:6}>'
            hpp_f.write(f'    {reg_type} {name_k};\n')
        hpp_f.write('\n')

        add_new_line = False
        for varv in recipe.var:
            if add_new_line:
                hpp_f.write('\n')
                add_new_line = False
            name_var = name_to_reg_var(varv.name)
            if varv.t.kind == ValueKind.flag:
                assert varv.flags is not None
                for f in varv.flags:
                    f_name = name_to_reg_var(f.name)
                    f_class = 'RFlagVec' if f.is_vec else 'RFlag'
                    f_type = f'std::shared_ptr<{f_class:8}>'
                    hpp_f.write(f'    {f_type} {f_name};\n')

                t_str = value_type_str(varv.t)
                reg_class = 'RegFlags'
                add_new_line = True
            else:
                reg_class = 'RegVec' if varv.t.is_vec else 'Reg'
            reg_type = f'std::shared_ptr<{reg_class:6}>'
            hpp_f.write(f'    {reg_type} {name_var};\n')
        hpp_f.write(f"}};\n")
        hpp_f.write(f"\n}}\n")

        cpp_f.write(f"""{file_header}

#include "{inc_dir}/{hpp_file.stem}.hpp"

namespace {namespace} {{

bool {recipe.sw_module}::registered = Module::register_module(std::make_shared<{recipe.sw_module}>());

""")

        cpp_f.write(f"""
void {recipe.sw_module}::init_reg_map_k() {{
""")
        for kv in recipe.k:
            name_k = name_to_reg_k(kv.name)
            if kv.t.kind == ValueKind.flag:
                for f in kv.flags:
                    bit = resolvable_member_function(f.bit)
                    if f.vec_len is None:
                        cpp_f.write(f'    {name_to_reg_k(f.name)} = make_r_flag("{f.name}", {bit}, Ass::{f.ass}, "{f.desc}");\n')
                    else:
                        cpp_f.write(f'    {name_to_reg_k(f.name)} = make_r_flag_vec("{f.name}", {bit}, Ass::{f.ass}, "{f.desc}", {f.vec_len})\n')
                cpp_f.write(f"    std::vector<std::shared_ptr<RFlag>> {name_k}_flags;\n")
                for f in kv.flags:
                    cpp_f.write(f"    push_back_flag({name_k}_flags, {name_to_reg_k(f.name)});\n")
                width = resolvable_member_function(kv.t.width)
                cpp_f.write(f'    {name_k} = make_reg_flags_k("{kv.name}", {width}, {name_k}_flags, "{kv.desc}");')
            else:
                t_str = value_type_str(kv.t)
                reg_make =  'make_reg_vec_k' if kv.t.is_vec else 'make_reg_k'
                cpp_f.write(f'    {name_k} = {reg_make}("{kv.name}", {t_str}, "{kv.desc}");')
            cpp_f.write(f' add_reg_k({name_k});\n')
        cpp_f.write(f"}}\n\n")

        cpp_f.write(f"""void {recipe.sw_module}::init_reg_map_var() {{\n""")
        for varv in recipe.var:
            name_var = name_to_reg_var(varv.name)
            if varv.t.kind == ValueKind.flag:
                assert varv.flags is not None
                for f in varv.flags:
                    bit = resolvable_member_function(f.bit)
                    if f.vec_len is None:
                        cpp_f.write(f'    {name_to_reg_var(f.name)} = make_r_flag("{f.name}", {bit}, Ass::{f.ass}, "{f.desc}");\n')
                    else:
                        cpp_f.write(f'    {name_to_reg_var(f.name)} = make_r_flag_vec("{f.name}", {bit}, Ass::{f.ass}, "{f.desc}", {f.vec_len});\n')
                cpp_f.write(f"    std::vector<std::shared_ptr<RFlag>> {name_var}_flags;\n")
                for f in varv.flags:
                    cpp_f.write(f"    push_back_flag({name_var}_flags, {name_to_reg_var(f.name)});\n")
                width = resolvable_member_function(varv.t.width)
                cpp_f.write(f'    {name_var} = make_reg_flags("{varv.name}", Acc::{varv.acc}, {width}, {name_var}_flags, "{varv.desc}");')

            else:
                t_str = value_type_str(varv.t)
                reg_make =  'make_reg_vec' if varv.t.is_vec else 'make_reg'
                cpp_f.write(f'    {name_var} = {reg_make}("{varv.name}", Acc::{varv.acc}, {t_str}, "{varv.desc}"); ')
            cpp_f.write(f" add_reg_var({name_var});\n")
        cpp_f.write(f"}}\n")
        cpp_f.write(f"}}\n")

common.all_reg_value_functions_str_is_flag = all_reg_value_functions_str_is_flag
common.all_reg_value_functions_str_not_flag = all_reg_value_functions_str_not_flag
all_reg_value_functions_str = common.all_reg_value_functions_str
common.name_to_reg_k = name_to_reg_k
common.name_to_reg_var = name_to_reg_var
common.resolve_k_value = resolve_k_value
reg_to_inst_str = common.reg_to_inst_str
resolvable_str = common.resolvable_str
resolvable_member_function = common.resolvable_member_function
_value_kind_function_str = common._value_kind_function_str
read_value_function_str  = common.read_value_function_str
write_value_function_str  = common.write_value_function_str

