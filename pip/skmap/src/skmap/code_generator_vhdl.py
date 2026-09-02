from pathlib import Path
from datetime import datetime
from typing import Literal, Optional, Union

from .code_generator_parse_resolvable import ResolvableFunctionOperation, ResolvableT, ResolvableFunctionBuiltIn
from .code_generator_parse_recipe import parse_recipe_file, RecipeK, RecipeVar, RecipeReg, ValueTypeT, RecipeIpkg, FwInitMode
from .basic import promote_to_sw_w, ceil_div
from .basic_types import Acc, Ass, ValueKind, ValueType, SKMAP_VER_STR


def to_vhdl_source(node: ResolvableT) -> str:
    """Render a ResolvableT tree back out as a Python source-code expression string."""
    # if isinstance(node, bool):
    #     return str(int(node))
    if isinstance(node, int):
        return str(node)
    # if isinstance(node, str):   # plain-string leaf (e.g. name_to_k[name] = name)
    #     return node
    if isinstance(node, RecipeIpkg):
        return f'{node.name}'
    if isinstance(node, RecipeK):
        return f'{node.name}'
    if isinstance(node, ResolvableFunctionOperation):
        return f'({to_vhdl_source(node.lhs)} {node.op} {to_vhdl_source(node.rhs)})'
    if isinstance(node, ResolvableFunctionBuiltIn):
        args = ', '.join(to_vhdl_source(p) for p in node.params)
        return f'skmap_recipe_{node.func.name}({args})'
    if hasattr(node, 'name'):  # RecipeK / RecipeIpkg leaf
        return node.name #type:ignore
    raise TypeError(f'Cannot render {node!r} {type(node)=} to python source')


def k_var_init_name(kvar_name : str) -> str:
    return kvar_name.upper()+"_INIT"

def port_name_trig(port_name : str) -> str:
    return port_name[:-2]+"_trigger_o"

def var_name_trig(port_name : str) -> str:
    return port_name[:-2]+"_trigger_v"

def port_name_clear(port_name : str) -> str:
    return port_name[:-2]+"_clear_o"

PortTypes = Literal['all','flat','slv_2d']

def optional_resize( s : str, width : Union[None, int, str]) -> str:
    if width == None:
        return s
    return f"resize( {s}, {width} )";

def optional_add_func_str( s : str, fstr : Optional[str]) -> str:
    if fstr == None:
        return s
    return f"{fstr}({s})"

def port_name(name : str, direction : Literal['in', 'out']):
    port_ext_in = "_i"
    port_ext_out = "_o"
    port_ext_bad = port_ext_in  if direction == 'in'  else port_ext_out
    port_ext     = port_ext_out if direction == 'out' else port_ext_in

    assert not name.endswith(port_ext_bad)
    p_name = name
    if not name.endswith(port_ext):
        p_name += port_ext
    return p_name

def var_name(name : str):
    return name + "_v"

def k_type_to_vhdl_str(t : ValueTypeT, port_types:PortTypes='all') -> str:
    elem_rng = f"({to_vhdl_source(t.width)}-1 downto 0)"
    if port_types == 'flat':
        if t.is_vec:
            vec_flat_rng = f'({to_vhdl_source(t.vec_len)}*{to_vhdl_source(t.width)}-1 downto 0)'
            return f'std_ulogic_vector{vec_flat_rng}'
        else:
            match t.kind:
                case ValueKind.uint: return "natural"
                case ValueKind.sint: return "integer"
                case ValueKind.char: return "std_ulogic_vector(7 downto 0)"
                case ValueKind.bits: return f"std_ulogic_vector{elem_rng}"
                case ValueKind.flag: return f"std_ulogic_vector{elem_rng}"
    else:
        assert port_types == 'all'
        if t.is_vec:
            vec_rng = f"(0 to {to_vhdl_source(t.vec_len)}-1)"
            str_rng = f"(1 to {to_vhdl_source(t.vec_len)})"
            match t.kind:
                case ValueKind.uint: return f"integer_vector{vec_rng}"
                case ValueKind.sint: return f"integer_vector{vec_rng}"
                case ValueKind.char: return f"string{str_rng}"
                case ValueKind.bits: return f"vec_slv_t{vec_rng}{elem_rng}"
                case ValueKind.flag: return f"vec_slv_t{vec_rng}{elem_rng}"
        else:
            match t.kind:
                case ValueKind.uint: return "natural"
                case ValueKind.sint: return "integer"
                case ValueKind.char: return "character"
                case ValueKind.bits: return f"std_ulogic_vector{elem_rng}"
                case ValueKind.flag: return f"std_ulogic_vector{elem_rng}"

def fw_init_mode_to_vhdl_type_str( varv : RecipeVar, port_types : PortTypes = 'all'):

    match varv.fw_init:
      case  FwInitMode.k:     return var_type_to_vhdl_str(varv.t, port_types)
      case  FwInitMode.k_int: return "integer_vector" if varv.t.is_vec else "integer"
      case _: raise ValueError("FwInitMode has not vhdl_type_str");

def vhdl_add_slv_cast( name : str, t: ValueTypeT) -> str:
    if t.is_vec:
        if t.kind in (ValueKind.uint, ValueKind.sint):
            return f"to_vec_slv({name})"
    else:
        if t.kind in (ValueKind.uint, ValueKind.sint):
            return f"std_ulogic_vector({name})"
    return name;

def var_type_to_vhdl_str(t : ValueTypeT, port_types:PortTypes = 'all', sl2slv : bool = False) -> str:
    if not sl2slv and t.is_bool:
        return "std_ulogic";
    elem_rng = f"({to_vhdl_source(t.width)}-1 downto 0)"

    if port_types == 'flat':
        if t.is_vec:
            vec_flat_rng = f'({to_vhdl_source(t.vec_len)}*{to_vhdl_source(t.width)}-1 downto 0)'
            return f'std_ulogic_vector{vec_flat_rng}'
        else:
            return f"std_ulogic_vector{elem_rng}"

    elif port_types == 'slv_2d':
        if t.is_vec:
            vec_rng = f"(0 to {to_vhdl_source(t.vec_len)}-1)"
            return f"vec_slv_t{vec_rng}{elem_rng}"
        else:
            return f"std_ulogic_vector{elem_rng}"

    elif port_types == 'all':
        if t.is_vec:
            vec_rng = f"(0 to {to_vhdl_source(t.vec_len)}-1)"
            str_rng = f"(1 to {to_vhdl_source(t.vec_len)})"
            match t.kind:
                case ValueKind.uint: return f"vec_unsigned_t{vec_rng}{elem_rng}"
                case ValueKind.sint: return f"vec_signed_t{vec_rng}{elem_rng}"
                case ValueKind.char: return f"string{str_rng}"
                case ValueKind.bits: return f"vec_slv_t{vec_rng}{elem_rng}"
                case ValueKind.flag: return f"vec_slv_t{vec_rng}{elem_rng}"
        else:
            match t.kind:
                case ValueKind.uint: return f"u_unsigned{elem_rng}"
                case ValueKind.sint: return f"u_signed{elem_rng}"
                case ValueKind.char: return f"character"
                case ValueKind.bits: return f"std_ulogic_vector{elem_rng}"
                case ValueKind.flag: return f"std_ulogic_vector{elem_rng}"

def vhdl_skmap_map_acc_byte_inc_func_str(r : RecipeReg, k : bool) -> str:
    s = (f"    skmap_map_acc_byte_inc(byte_idx, VAL_W=>{to_vhdl_source(r.t.width)}")
    if not k:
        s += (", BYTE_ALIGN=>BYTE_ALIGN")
    if r.t.is_vec:
        s += (f", VEC_LEN=>{to_vhdl_source(r.t.vec_len)}");
    s += (f"); -- {r.name}\n")
    return s;

def regs_len_str(regs : list[RecipeReg], name : str, k : bool = False, offset_bytes = 0) -> str:

    s = (f"""
  function get_{name} return natural is
    variable byte_idx : natural := {offset_bytes};
  begin\n""")
    for r in regs:
        s += vhdl_skmap_map_acc_byte_inc_func_str(r, k)
    if offset_bytes != 0:
        s += (f"    inc(byte_idx, -1*({offset_bytes}));\n")
    s += (f"""    return ceil_div(byte_idx, 4);
  end function;
  constant {name} : natural := get_{name};\n""")
    return s;

def generate_vhdl_module(recipe_file : Path, vhdl_file : Path):
    recipe = parse_recipe_file(recipe_file)

    if recipe.fw_opts.ports_use_basic_types:
        port_types : PortTypes = 'flat'
    else:
        port_types : PortTypes = 'all'
    hdlskel_lib : str  = recipe.fw_opts.hdlskel_vhdl_lib

    with open(vhdl_file, 'w') as vhdl_f:
        # write start 
        vhdl_f.write(f""" --------------------------------------------------------------------------------
-- NOTE: this file is autogenerated:
--    * From {__file__}
--    * On {datetime.now()} 
--    * Using HDLSkel SkMap {SKMAP_VER_STR}
--    * For {recipe.name} {recipe.id} v{recipe.version}
--    * Checksum {recipe.checksum_str()}
--------------------------------------------------------------------------------
\n""")
        if hdlskel_lib != 'work':
            vhdl_f.write(f"""
library {hdlskel_lib};""")

        vhdl_f.write(f"""

use {hdlskel_lib}.skmap_module_ipkg.SKMAP_SIZE_RESERVED_DEFAULT;

package {recipe.fw_module}_ipkg is\n\n""")
        if len(recipe.ipkg) > 1:
            vhdl_f.write('\n')
        for ipkgv in recipe.ipkg:
            vhdl_t = k_type_to_vhdl_str(ipkgv.t, port_types='all')
            value = ipkgv.value
            if ipkgv.t.kind == ValueKind.char:
                if ipkgv.t.is_vec:
                    value = f'"{value}"'
                else:
                    value = f"'{value}'"
            vhdl_f.write(f"    constant {ipkgv.name} : {vhdl_t} := {value};")
            if ipkgv.desc is not None:
                vhdl_f.write(f" --! {ipkgv.desc}")
            vhdl_f.write("\n")


        vhdl_f.write(f"""\n
    constant SKMAP_SIZE_RESERVED           : natural := {recipe.fw_opts.size_reserved};
    constant SKMAP_SIZE_RESERVED_BASE_REGS : natural := {recipe.fw_opts.size_reserved_base_regs};

end package;

---------------------------------------------------------------

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;\n""")
        if hdlskel_lib != 'work':
            vhdl_f.write(f"""
library {hdlskel_lib};""")

        vhdl_f.write(f"""
use {hdlskel_lib}.basic_pkg.all;
use {hdlskel_lib}.vec_pkg.all;

use {hdlskel_lib}.ramface_pkg.all;
use {hdlskel_lib}.skmap_pkg.all;
use {hdlskel_lib}.skmap_map_acc_pkg.all;
use {hdlskel_lib}.skmap_recipe_functions_pkg.all;

use {hdlskel_lib}.skmap_module_ipkg;

use work.{recipe.fw_module}_ipkg;\n""")
        if len(recipe.ipkg) > 0:

            vhdl_f.write(f"use work.{recipe.fw_module}_ipkg.all;\n")


        #write module entity declaration begining
        vhdl_f.write(f"""\n
entity {recipe.fw_module} is
  generic (
    BASE_ADDR       : natural;\n""")
        if port_types == 'flat':
            vhdl_f.write(f'    SKMAP_KIDS_FLAT : std_ulogic_vector := "";\n')
        else:
            vhdl_f.write(f"    SKMAP_KIDS : integer_vector := NULL_INTEGER_VECTOR;\n")
        vhdl_f.write(f"""\n
    SKMAP_BYTE_ALIGN : integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG;""");
        # assert recipe.with_vec_external_mem == False or recipe.with_external_mem == False
        # if recipe.with_vec_external_mem:
        #     vhdl_f.write("\n    SKMAP_VEC_EXTERNAL_MEM : skmap_vec_external_mem_t := NULL_SKMAP_VEC_EXTERNAL_MEM;")
        # if recipe.with_external_mem:
        #     vhdl_f.write("\n    SKMAP_EXTERNAL_MEM : skmap_external_mem_t;")
        #     vhdl_f.write("\n    SKMAP_VEC_EXTERNAL_MEM : skmap_vec_external_mem_t(0 to 0) := (0 => SKMAP_EXTERNAL_MEM);")
        vhdl_f.write("""
    RAMFACE_ADDR_W  : natural;
    RAMFACE_DATA_W  : natural;
    RAMFACE_WREN_W  : natural := RAMFACE_DATA_W/8;
    RAMFACE_LATENCY : natural := skmap_module_ipkg.get_RAMFACE_LATENCY""")
        # if recipe.with_vec_external_mem or recipe.with_external_mem:
        #     vhdl_f.write("(SKMAP_VEC_EXTERNAL_MEM=>SKMAP_VEC_EXTERNAL_MEM)");
        last_desc = None
        if len(recipe.k) > 0:
            vhdl_f.write(";\n")
        for ii, kv in enumerate(recipe.k):
            if last_desc is not None:
                vhdl_f.write(f" --! {last_desc}")
            if kv.t.kind == ValueKind.flag and kv.flags is not None:
                for jj, f in enumerate(kv.flags):
                    if f.vec_len != None:
                        vhdl_t = f'boolean_vector(0 to {to_vhdl_source(f.vec_len)}-1)'
                    else:
                        vhdl_t = 'boolean'
                    vhdl_f.write(f'\n    {f.name} : {vhdl_t}')
                    if jj != len(kv.flags)-1: vhdl_f.write(";")
                    last_desc = f.desc

            else:
                vhdl_t = k_type_to_vhdl_str(kv.t, port_types=port_types)
                vhdl_f.write(f'\n    {kv.name} : {vhdl_t}')
            if ii != len(recipe.k)-1: vhdl_f.write(";")
            last_desc = kv.desc

        for varv in recipe.var:
            if varv.fw_init.is_k:
                vhdl_f.write(f";")
                if last_desc is not None:
                    vhdl_f.write(f" --! {last_desc}")
                    last_desc = None
                init_t_str = fw_init_mode_to_vhdl_type_str(varv, port_types=port_types)
                vhdl_f.write(f'\n    {k_var_init_name(varv.name)} : {init_t_str}')
                last_desc = f'{varv.name} inital value'

        if last_desc is not None:
            vhdl_f.write(f" --! {last_desc}")
            last_desc = None

        vhdl_f.write(f"""
  );
  port (
    clk_i : in  std_ulogic;

    ramface_ce_i : in std_ulogic := '1';""")

        if port_types == 'flat':
            vhdl_f.write(f"""
    ramface_rqst_en_i   : in  std_ulogic;
    ramface_rqst_addr_i : in  std_ulogic_vector(RAMFACE_ADDR_W-1 downto 0);
    ramface_rqst_wren_i : in  std_ulogic_vector(RAMFACE_WREN_W-1 downto 0);
    ramface_rqst_data_i : in  std_ulogic_vector(RAMFACE_DATA_W-1 downto 0);
    ramface_rply_en_o   : out std_ulogic;
    ramface_rply_fail_o : out std_ulogic;
    ramface_rply_data_o : out std_ulogic_vector(RAMFACE_DATA_W -1 downto 0)""")
        else:
            vhdl_f.write(f"""
    ramface_rqst_i : in ramface_rqst_t(
      addr(RAMFACE_ADDR_W-1 downto 0),
      wren(RAMFACE_WREN_W-1 downto 0),
      data(RAMFACE_DATA_W-1 downto 0)
    );
    ramface_rply_o : out ramface_rply_t(
      data(RAMFACE_DATA_W -1 downto 0)
    )""")

        if len(recipe.var) > 0:
            vhdl_f.write(";\n")
        prev_desc = None;
        for ii, varv in enumerate(recipe.var):
            assert varv.acc != Acc.na
            output = varv.acc.sw_writable
            # assert output is not None
            varv.direction = "out" if output else "in"

            # name = varv.name
            # assert not name.endswith(port_ext_bad)
            # if not name.endswith(port_ext):
            #     name += port_ext
            # varv.name_ext = name

            if varv.flags is not None:
                varv.name_ext = var_name(varv.name)
                varv.uses_var_name = True
                for jj, f in enumerate(varv.flags):
                    f.name_ext = port_name(f.name, varv.direction)
                    if f.is_vec:
                        rng = f"({f.vec_len}-1 downto 0)"
                        vhdl_t = f'std_ulogic_vector{rng}'
                    else:
                        vhdl_t = f'std_logic'
                    if prev_desc is not None:
                        vhdl_f.write(f" --! {prev_desc}")
                    prev_desc = f.desc
                    vhdl_f.write(f'\n    {f.name_ext} : {varv.direction} {vhdl_t}')
                    if jj != len(varv.flags)-1: vhdl_f.write(";")
            else:
                if varv.direction == 'out' and (varv.t.kind in (ValueKind.uint, ValueKind.sint) or varv.t.is_bool):
                    varv.uses_var_name = True
                    varv.name_ext = var_name(varv.name)
                    varv.p_name = port_name(varv.name, varv.direction)
                else:
                    varv.uses_var_name = False
                    varv.name_ext = port_name(varv.name, varv.direction)
                    varv.p_name = port_name(varv.name, varv.direction)

                if varv.acc == Acc.wt or (varv.acc == Acc.rc and varv.t.kind != ValueKind.flag):
                    # print(f'{varv.t=}')
                    if varv.t.is_vec:
                        rng = f"({varv.t.vec_len}-1 downto 0)"
                        vhdl_t = f'std_ulogic_vector{rng}'
                    else:
                        vhdl_t = f'std_logic'
                    if varv.acc == Acc.wt:
                        assert isinstance(varv.name_ext, str)
                        p_name = port_name_trig(varv.name_ext)
                    else:
                        assert varv.acc == Acc.rc
                        assert isinstance(varv.name_ext, str)
                        p_name = port_name_clear(varv.name_ext)
                    if prev_desc is not None:
                        vhdl_f.write(f" --! {prev_desc}")
                    prev_desc = None
                    vhdl_f.write(f'\n    {p_name} : out {vhdl_t};')

                vhdl_t = var_type_to_vhdl_str(varv.t, port_types=port_types)
                if prev_desc is not None:
                    vhdl_f.write(f" --! {prev_desc}")
                prev_desc = varv.desc
                vhdl_f.write(f'\n    {varv.p_name} : {varv.direction} {vhdl_t}')
            if ii != len(recipe.var)-1: vhdl_f.write(";")
        if len(recipe.mem) > 0:
            vhdl_f.write(";")
        if prev_desc is not None:
            vhdl_f.write(f" --! {prev_desc}")
        if len(recipe.mem) > 0:
            vhdl_f.write(";\n")
        prev_desc = None
        for ii, memv in enumerate(recipe.mem):
            assert memv.acc in (Acc.rw, Acc.ro), "Not yet implemented for memory interfaces"
            vhdl_f.write(f"    --! {memv.desc}")
            if memv.acc == Acc.rw or memv.acc == Acc.wt:
                if port_types == 'flat':
                    vhdl_f.write(f"""
    {memv.name}_rqst_en_o   : out std_ulogic;
    {memv.name}_rqst_addr_o : out std_ulogic_vector(ceil_log2({memv.fw_depth})-1 downto 0);
    {memv.name}_rqst_wren_o : out std_ulogic_vector({memv.fw_width}/8-1 downto 0);
    {memv.name}_rqst_data_o : out std_ulogic_vector({memv.fw_width}-1 downto 0);""")
                else:
                    vhdl_f.write(f"""
    {memv.name}_rqst_o : out ramface_rqst_t(
      addr(ceil_log2({memv.fw_depth})-1 downto 0),
      wren({memv.fw_width}/8-1 downto 0),
      data({memv.fw_width}-1 downto 0)
    );""")
            elif memv.acc == Acc.rc:
                if port_types == 'flat':
                    vhdl_f.write(f"""
    {memv.name}_rqst_en_o   : out std_ulogic;
    {memv.name}_rqst_addr_o : out std_ulogic_vector(ceil_log2({memv.fw_depth})-1 downto 0);
    {memv.name}_rqst_wren_o : out std_ulogic_vector({memv.fw_width}/8-1 downto 0);""")
                else:
                    vhdl_f.write(f"""
    {memv.name}_rqst_o : out ramface_rqst_rc_t(
      addr(ceil_log2({memv.fw_depth})-1 downto 0),
      wren({memv.fw_width}/8-1 downto 0)
    );""")
            elif memv.acc == Acc.ro or memv.acc == Acc.k:
                if port_types == 'flat':
                    vhdl_f.write(f"""
    {memv.name}_rqst_en_o   : out std_ulogic;
    {memv.name}_rqst_addr_o : out std_ulogic_vector(ceil_log2({memv.fw_depth})-1 downto 0);""")
                else:
                    vhdl_f.write(f"""
    {memv.name}_rqst_o : out ramface_rqst_ro_t(
      addr(ceil_log2({memv.fw_depth})-1 downto 0)
    );""")
            if port_types == 'flat':
                vhdl_f.write(f"""
    {memv.name}_rply_en_i   : in  std_ulogic;
    {memv.name}_rply_fail_i : in  std_ulogic;
    {memv.name}_rply_data_i : in  std_ulogic_vector({memv.fw_width} -1 downto 0)""")
            else:
                vhdl_f.write(f"""
    {memv.name}_rply_i : in  ramface_rply_t(
      data({memv.fw_width} -1 downto 0)
    )""")
            if ii != len(recipe.mem)-1: vhdl_f.write(";")

        vhdl_f.write(f"""
  );
end entity;

architecture rtl of {recipe.fw_module} is

  alias BYTE_ALIGN is SKMAP_BYTE_ALIGN;\n""")

        if port_types == 'flat':
            vhdl_f.write(f"  constant SKMAP_KIDS : integer_vector :=   to_vec_int(to_vec_signed(to_vec_slv(rng_dt(SKMAP_KIDS_FLAT),32)));\n")
        vhdl_f.write("  constant SKMAP_VEC_EXTERNAL_MEM : skmap_vec_external_mem_t := ");
        if (len(recipe.mem) == 0 ):
            vhdl_f.write("NULL_SKMAP_VEC_EXTERNAL_MEM;\n")
        else:
            vhdl_f.write("( ")
            for ii, memv in enumerate(recipe.mem):
                vhdl_f.write(f""" {ii} => (
    data_w    => {memv.fw_width},
    depth     => {memv.fw_depth},
    latency   => {memv.fw_latency},
    acc       => {memv.acc}
  ) """)
                if ( ii != len(recipe.mem)-1 ):
                    vhdl_f.write(',')
                else:
                    vhdl_f.write(') ;\n')
            vhdl_f.write("""
    signal vec_ramface_external_mem_rqst : vec_ramface_rqst_t ( 0 to SKMAP_VEC_EXTERNAL_MEM'length-1)(
      addr(skmap_get_external_mem_max_addr_w(SKMAP_VEC_EXTERNAL_MEM)-1 downto 0),
      wren(skmap_get_external_mem_max_data_w(SKMAP_VEC_EXTERNAL_MEM)/8-1 downto 0),
      data(skmap_get_external_mem_max_data_w(SKMAP_VEC_EXTERNAL_MEM)-1 downto 0)
    );
    signal vec_ramface_external_mem_rqst_en_rd : std_ulogic_vector(SKMAP_VEC_EXTERNAL_MEM'length-1 downto 0);
    signal vec_ramface_external_mem_rqst_en_wr : std_ulogic_vector(SKMAP_VEC_EXTERNAL_MEM'length-1 downto 0);

    signal vec_ramface_external_mem_rply :  vec_ramface_rply_t ( 0 to SKMAP_VEC_EXTERNAL_MEM'length-1)(
      data(skmap_get_external_mem_max_data_w(SKMAP_VEC_EXTERNAL_MEM)-1 downto 0)
    );
    
""")


        for kv in recipe.k:
            if kv.t.kind == ValueKind.flag:
                vhdl_f.write(f"""
  function get_{kv.name} return boolean_vector is
    variable flags : boolean_vector(0 to {kv.t.width}-1) := (others => false);
  begin\n""")
                # vhdl_f.write(f'  constant {kv.name} : boolean_vector(0 to {kv.t.width}-1) := ( ');
                assert kv.flags is not None
                for ii, f in enumerate(kv.flags):
                    if f.vec_len != None:
                        vhdl_f.write(f'    flags({f.bit} to {f.bit} + {f.vec_len} - 1) := {f.name};\n')
                    else:
                        vhdl_f.write(f'    flags({f.bit}) := {f.name};\n')
                vhdl_f.write(f"""    return flags;
  end function;
  constant {kv.name} : boolean_vector := get_{kv.name};\n """)
                        

        vhdl_f.write(regs_len_str(recipe.k, 'REGS_K_INT_LEN', k = True));

        vhdl_f.write(f"""
  function get_REGS_K_INT return integer_vector is
    variable k_vec_int : integer_vector(0 to REGS_K_INT_LEN-1) := (others => 0);
    variable byte_idx : integer := 0;
  begin\n""")
    # variable offset_v : integer := 0;
        # for ii in range(total_k_with_fixed_idx):
        #     kv = recipe.k[ii]
        for kv in recipe.k:
            if kv.t.kind == ValueKind.flag:
                vhdl_f.write(f"    skmap_map_acc_k(k_vec_int_io=>k_vec_int, byte_idx_io=>byte_idx, val_i=>{kv.name});\n")
            else:
                if(kv.t.width > 32):
                   raise RuntimeError(f"Currently k must support 32bit integers {kv.t.width=} {kv.t.kind=}")

                is_signed_str = 'TRUE' if kv.t.kind == ValueKind.sint else 'FALSE'
                vhdl_f.write(f"    skmap_map_acc_k(k_vec_int_io=>k_vec_int, byte_idx_io=>byte_idx, val_i=>{kv.name}, w_i=>{kv.t.width}, signed_i=>{is_signed_str});\n")
                # name = kv.name
                # if addr_byte % 4 == 0:
                #     if addr_byte != 0: vhdl_f.write(f",\n")
                #     vhdl_f.write(f"    {addr_byte//4} => {name}")
                # else:
                #     if ((addr_byte + kv.t.width//8) % 4) == 0:
                #         if kv.t.width == 8:
                #             name = f"to_sint8({name})"
                #         elif kv.t.width == 16:
                #             name = f"to_sint16({name})"
                #     vhdl_f.write(f" + {name} *2**{(addr_byte % 4)*8}")
        vhdl_f.write(f"""    return k_vec_int;
    end function;
    constant REGS_K_INT : integer_vector := get_REGS_K_INT;

  constant HEAD_AND_K_LEN : natural := skmap_module_ipkg.head_and_k_len(
    SKMAP_BYTE_ALIGN => SKMAP_BYTE_ALIGN,
    RAMFACE_DATA_W => RAMFACE_DATA_W,
    SKMAP_KIDS => SKMAP_KIDS,
    REGS_K_INT => REGS_K_INT 
  );\n""")
        # arecipe.k:

        vhdl_f.write(regs_len_str(recipe.var, 'REGS_VAR_LEN', offset_bytes="HEAD_AND_K_LEN*4"))

###################################
        use_var_wr_init = False
        for varv in recipe.var:
            if varv.fw_init != FwInitMode.zero:
                use_var_wr_init = True
                break

        if use_var_wr_init:
            vhdl_f.write(f"""
  function get_REGS_VAR_WR_INIT return integer_vector is
    variable vec_int : integer_vector(0 to REGS_VAR_LEN-1) := (others => 0);
    variable byte_idx : integer := 0;
  begin\n""")
            # variable offset_v : integer := 0;
            # for ii in range(total_k_with_fixed_idx):
            #     kv = recipe.k[ii]
            align_str = "BYTE_ALIGN=>BYTE_ALIGN"
            for varv in recipe.var:
                init_name = k_var_init_name(varv.name)
                if varv.fw_init == FwInitMode.zero:
                    vhdl_f.write(vhdl_skmap_map_acc_byte_inc_func_str(varv,k=False))
                elif varv.fw_init.is_k_int:
                    is_signed_str = 'TRUE' if varv.t.kind == ValueKind.sint else 'FALSE'
                    vhdl_f.write(f"    skmap_map_acc_k(k_vec_int_io=>vec_int, byte_idx_io=>byte_idx, val_i=>{init_name}, w_i=>{varv.t.width}, signed_i=>{is_signed_str}, {align_str});\n")
                elif varv.fw_init == FwInitMode.k :
                    init_name = vhdl_add_slv_cast(init_name, varv.t)
                    vhdl_f.write(f"    skmap_map_acc_k(k_vec_int_io=>vec_int, byte_idx_io=>byte_idx, val_i=>{init_name}, {align_str});\n")
            vhdl_f.write(f"""    return vec_int;
  end function;
  constant REGS_VAR_WR_INIT : integer_vector := get_REGS_VAR_WR_INIT;""")
##################################



  #       vhdl_f.write(f"""
  # function get_REGS_VAR_LEN return natural is
  #   variable byte_idx : natural := 0;
  # begin\n""")
  #       for varv in recipe.var:
  #           vhdl_f.write(f"    skmap_map_acc_byte_inc(byte_idx, VAL_W=>{varv.t.width},")
  #           vhdl_f.write("BYTE_ALIGN=>BYTE_ALIGN")
  #           if varv.t.is_vec:
  #               vhdl_f.write(f", VEC_LEN=>{varv.t.vec_len}");
  #           vhdl_f.write(f"); -- {varv.name}\n")
  #       vhdl_f.write(f"""    return ceil_div(byte_idx, 4);
  # end function;
  # constant REGS_VAR_LEN : natural := get_REGS_VAR_LEN;\n""")
        vhdl_f.write(f"""\n
  subtype REG_VAR_RNG is integer range HEAD_AND_K_LEN to HEAD_AND_K_LEN+REGS_VAR_LEN-1;

  signal regs_var_rd_data_0 : vec_slv32_t(0 to REGS_VAR_LEN-1) := (others => (others => '0'));
  signal regs_var_wr_data_0 : vec_slv32_t(0 to REGS_VAR_LEN-1);
  signal regs_var_wr_wren_0 : vec_slv4_t (0 to REGS_VAR_LEN-1);

  alias regs_var_rd_data : vec_slv32_t(REG_VAR_RNG) is regs_var_rd_data_0;
  alias regs_var_wr_data : vec_slv32_t(REG_VAR_RNG) is regs_var_wr_data_0;
  alias regs_var_wr_wren : vec_slv4_t (REG_VAR_RNG) is regs_var_wr_wren_0;

begin
\n""")
        for kv in recipe.k:
            if kv.t.kind == ValueKind.flag:
                continue
            if kv.t.is_vec:
                # TODO: add type checking for vectors
                continue
            if kv.t.kind == ValueKind.uint:
                if not isinstance(kv.t.width, int) or kv.t.width < 31:
                    vhdl_f.write(f'  assert {kv.name} < 2**{kv.t.width} severity FAILURE;\n')
                else:
                    assert kv.t.width <= 31, "Not yet supported"
            elif kv.t.kind == ValueKind.sint:
                if not isinstance(kv.t.width, int) or kv.t.width < 32:
                    vhdl_f.write(f'  assert {kv.name} <   2**({kv.t.width}-1) severity FAILURE;\n')
                    vhdl_f.write(f'  assert {kv.name} >= -2**({kv.t.width}-1) severity FAILURE;\n')
                else:
                    assert kv.t.width <= 32, "Not yet supported"

        vhdl_f.write(f"""

  i_skmap_module : entity {hdlskel_lib}.skmap_module
  generic map (
    SKMAP_ID           => "{recipe.id}",
    SKMAP_VERSION      => {recipe.version},
    SKMAP_CHECKSUM     => 16#{recipe.checksum_str()}#,
    SKMAP_KIDS         => SKMAP_KIDS,
    SKMAP_VEC_EXTERNAL_MEM => SKMAP_VEC_EXTERNAL_MEM,
    SKMAP_BYTE_ALIGN   => SKMAP_BYTE_ALIGN,
    SKMAP_SIZE_RESERVED           => {recipe.fw_module}_ipkg.SKMAP_SIZE_RESERVED,
    SKMAP_SIZE_RESERVED_BASE_REGS => {recipe.fw_module}_ipkg.SKMAP_SIZE_RESERVED_BASE_REGS,
    BASE_ADDR          => BASE_ADDR,
    RAMFACE_ADDR_W     => RAMFACE_ADDR_W,
    RAMFACE_DATA_W     => RAMFACE_DATA_W,
    RAMFACE_WREN_W     => RAMFACE_WREN_W,
    RAMFACE_LATENCY    => RAMFACE_LATENCY,
    REGS_K_INT         => REGS_K_INT,
    REGS_VAR_LEN       => REGS_VAR_LEN""")
        if use_var_wr_init:
            vhdl_f.write(f",\n    REGS_VAR_WR_DATA_INIT_VEC_INT => REGS_VAR_WR_INIT")
        vhdl_f.write(f"""
  ) port map (
    clk_i              => clk_i,

    ramface_ce_i       => ramface_ce_i,""")
        if port_types == 'flat':
            vhdl_f.write(f"""
    ramface_rqst_i.en   => ramface_rqst_en_i,
    ramface_rqst_i.addr => u_unsigned(ramface_rqst_addr_i),
    ramface_rqst_i.wren => ramface_rqst_wren_i,
    ramface_rqst_i.data => ramface_rqst_data_i,
    ramface_rply_o.en   => ramface_rply_en_o,
    ramface_rply_o.fail => ramface_rply_fail_o,
    ramface_rply_o.data => ramface_rply_data_o,
""")
        else:
            vhdl_f.write(f"""
    ramface_rqst_i     => ramface_rqst_i,
    ramface_rply_o     => ramface_rply_o,
""")
        if len(recipe.mem) > 0:
            vhdl_f.write(f"""
    vec_ramface_external_mem_rqst_o       => vec_ramface_external_mem_rqst,
    vec_ramface_external_mem_rqst_en_rd_o => vec_ramface_external_mem_rqst_en_rd,
    vec_ramface_external_mem_rqst_en_wr_o => vec_ramface_external_mem_rqst_en_wr,
    vec_ramface_external_mem_rply_i       => vec_ramface_external_mem_rply, 
""")
        vhdl_f.write(f"""
    regs_var_wr_wren_o => regs_var_wr_wren_0,
    regs_var_wr_data_o => regs_var_wr_data_0,
    regs_var_rd_data_i => regs_var_rd_data_0
  );
""")
        vhdl_f.write(f"""
  process(all)
    variable byte_idx_v : natural;
""")
        for varv in recipe.var:
            if varv.acc == Acc.rc and varv.flags is not None:
                vhdl_f.write(f"    variable byte_idx_temp_v : natural;\n")
                break

        for varv in recipe.var:
            if varv.uses_var_name:
                vhdl_t = var_type_to_vhdl_str(varv.t, port_types='slv_2d', sl2slv = True)
                vhdl_f.write(f'    variable {varv.name_ext} : {vhdl_t};\n')
                if varv.acc == Acc.wt:
                    assert not varv.t.is_vec
                    vhdl_f.write(f'    variable {var_name_trig(varv.name_ext)} : std_logic;\n')
        vhdl_f.write("""
  begin
    byte_idx_v := HEAD_AND_K_LEN*4;\n\n""");
        for varv in recipe.var:
            if varv.uses_var_name:
                if varv.direction == "in":
                    # if varv.t.kind != ValueKind.flag:
                    #     if varv.t.is_vec:
                    #         vhdl_f.write(f'    {varv.name_ext} := to_vec_slv({varv.p_name});\n')
                    #     else:
                    #         vhdl_f.write(f'    {varv.name_ext} := std_ulogic_vector({varv.p_name});\n')
                    # else:
                    assert( varv.flags is not None )
                    assert( not varv.t.is_vec) # TODO: support vec of flags
                    for f in varv.flags:
                        if f.is_vec:
                            vhdl_f.write(f'    {varv.name_ext}({f.vec_len} -1 + {f.bit} downto {f.bit}) := {f.name_ext};\n')
                        else:
                            vhdl_f.write(f'    {varv.name_ext}({f.bit}) := {f.name_ext};\n')
                    vhdl_f.write('\n')

        align_str = "BYTE_ALIGN=>BYTE_ALIGN"
        for varv in recipe.var:
            rd_name = 'ERROR: rd_name ( file '+__file__+")"
            if not varv.acc.sw_writable:
                if varv.t.is_vec:
                    match varv.t.kind:
                        case ValueKind.uint: rd_name =  f"to_vec_slv({varv.name_ext})"
                        case ValueKind.sint: rd_name =  f"to_vec_slv({varv.name_ext})"
                        case ValueKind.char: assert False # rd_name =  f"string({varv.name_ext})"
                        case ValueKind.bits: rd_name =  varv.name_ext
                        case ValueKind.flag: 
                            if varv.flags is None and varv.t.width == 1:
                                rd_name = f"to_slv({varv.name_ext})"
                            else:
                                rd_name = varv.name_ext

                else:
                    match varv.t.kind:
                        case ValueKind.uint: rd_name =  f"std_ulogic_vector({varv.name_ext})"
                        case ValueKind.sint: rd_name =  f"std_ulogic_vector({varv.name_ext})"
                        case ValueKind.char: assert False #rd_name =  f"character"
                        case ValueKind.bits: rd_name =  varv.name_ext
                        case ValueKind.flag:
                            if varv.flags is None and varv.t.width == 1:
                                rd_name = f"to_slv({varv.name_ext})"
                            else:
                                rd_name = varv.name_ext
            match varv.acc:
                case Acc.ro:
                    vhdl_f.write(f'    skmap_map_acc_ro(regs_var_rd_data, byte_idx_v, {rd_name}, {align_str});\n')
                case Acc.rw:
                    skmap_func = 'skmap_map_acc_rw_var' if varv.uses_var_name else 'skmap_map_acc_rw'
                    # print(f'{varv.name=} {varv.name_ext=}')
                    vhdl_f.write(f'    {skmap_func}(regs_var_rd_data, regs_var_wr_data, byte_idx_v, {varv.name_ext}, {align_str});\n')
                case Acc.wt:
                    name_trig = var_name_trig(varv.name_ext) if varv.uses_var_name else port_name_trig(varv.name_ext)
                    skmap_func = 'skmap_map_acc_wt_var' if varv.uses_var_name else 'skmap_map_acc_wt'
                    vhdl_f.write(f'    {skmap_func}(regs_var_rd_data, regs_var_wr_data, regs_var_wr_wren, byte_idx_v, {varv.name_ext}, {name_trig}, {align_str});\n');
                case Acc.rc:
                    if varv.t.kind == ValueKind.flag:
                        vhdl_f.write(f"""    if rising_edge(clk_i) then
      byte_idx_temp_v := byte_idx_v;
      skmap_map_acc_rc_flags(regs_var_rd_data, regs_var_wr_wren, byte_idx_temp_v, {rd_name}, {align_str});
    end if;
    skmap_map_acc_byte_inc(byte_idx_v, {rd_name}'length, {align_str});\n""");
                    else:
                        name_clear = port_name_clear(varv.name_ext)
                        vhdl_f.write(f'    skmap_map_acc_rc(regs_var_rd_data, regs_var_wr_wren, byte_idx_v, {rd_name}, {name_clear}, {align_str});\n');
                case _:
                    print(f'ERROR {varv.acc=}')
                    assert(False)
            vhdl_f.write("")
        vhdl_f.write("\n")

        for varv in recipe.var:
            if varv.uses_var_name:
                if varv.direction == "out":
                    if varv.acc == Acc.wt:
                        vhdl_f.write(f'    {port_name_trig(varv.p_name)} <= {var_name_trig(varv.name_ext)};\n')


                    if varv.flags is None:
                        if port_types == 'flat':
                            if varv.t.is_bool:
                                vhdl_f.write(f'    {varv.p_name} <= to_sl({varv.name_ext});\n')
                            elif varv.t.is_vec:
                                vhdl_f.write(f'    {varv.p_name} <= to_flat({varv.name_ext});\n')
                            else:
                                vhdl_f.write(f'    {varv.p_name} <= {varv.name_ext};\n')
                        elif varv.t.is_vec:
                            match varv.t.kind:
                                case ValueKind.uint: vhdl_f.write(f'    {varv.p_name} <= to_vec_unsigned({varv.name_ext});\n')
                                case ValueKind.sint: vhdl_f.write(f'    {varv.p_name} <= to_vec_signed({varv.name_ext});\n')
                                case _: assert False;
                        elif varv.t.is_bool:
                            vhdl_f.write(f'    {varv.p_name} <= to_sl({varv.name_ext});\n')
                        else:
                            match varv.t.kind:
                                case ValueKind.uint: vhdl_f.write(f'    {varv.p_name} <= unsigned({varv.name_ext});\n')
                                case ValueKind.sint: vhdl_f.write(f'    {varv.p_name} <= signed({varv.name_ext});\n')
                                case _: assert False;
                    else:
                        assert( varv.flags is not None )
                        assert( not varv.t.is_vec) # TODO:
                        for f in varv.flags:
                            if f.is_vec:
                                vhdl_f.write(f'    {f.name_ext} <= {varv.name_ext}({f.vec_len} -1 + {f.bit} downto {f.bit});\n')
                            else:
                                vhdl_f.write(f'    {f.name_ext} <= {varv.name_ext}({f.bit});\n')
                        vhdl_f.write('\n')
        vhdl_f.write("  end process;\n");

        for ii, memv in enumerate(recipe.mem):
            if len(recipe.mem) == 1:
                rs_addr_w = None
                rs_data_w = None
                rs_wren_w = None
            else:
                rs_addr_w = f'ceil_log2({str(memv.fw_depth)})'
                rs_data_w = str(memv.fw_width)
                rs_wren_w = rs_data_w + "/8"
            if port_types == 'flat':
                mem_q_addr = f'{memv.name}_rqst_addr_o'
                mem_q_en   = f'{memv.name}_rqst_en_o'
                mem_q_wren = f'{memv.name}_rqst_wren_o'
                mem_q_data = f'{memv.name}_rqst_data_o'
                slv_func = 'std_ulogic_vector'
            else:
                mem_q_addr = f'{memv.name}_rqst_o.addr'
                mem_q_en   = f'{memv.name}_rqst_o.en'
                mem_q_wren = f'{memv.name}_rqst_o.wren'
                mem_q_data = f'{memv.name}_rqst_o.data'
                slv_func = None

            vhdl_f.write(f"""
    {mem_q_addr} <= { optional_add_func_str( optional_resize( f'vec_ramface_external_mem_rqst({ii}).addr', rs_addr_w), slv_func) };""");
            if memv.acc == Acc.ro or memv.acc == Acc.k:
                vhdl_f.write(f"""
    {mem_q_en}   <= vec_ramface_external_mem_rqst_en_rd({ii});""");
            elif memv.acc in (Acc.rw, Acc.rc, Acc.wt):
                vhdl_f.write(f"""
    {mem_q_en}   <= vec_ramface_external_mem_rqst({ii}).en;
    {mem_q_wren} <= { optional_resize(f'vec_ramface_external_mem_rqst({ii}).wren', rs_wren_w) };""");
                if memv.acc in (Acc.rw, Acc.wt):
                    vhdl_f.write(f"""
    {mem_q_data} <= { optional_resize(f'vec_ramface_external_mem_rqst({ii}).data', rs_data_w) };""");

            if port_types == 'flat':
                mem_p_en   = f'{memv.name}_rply_en_i'
                mem_p_fail = f'{memv.name}_rply_fail_i'
                mem_p_data = f'{memv.name}_rply_data_i'
            else:
                mem_p_en   = f'{memv.name}_rply_i.en'
                mem_p_fail = f'{memv.name}_rply_i.fail'
                mem_p_data = f'{memv.name}_rply_i.data'

            vhdl_f.write(f"""
    vec_ramface_external_mem_rply({ii}).en   <= {mem_p_en};
    vec_ramface_external_mem_rply({ii}).fail <= {mem_p_fail};
    vec_ramface_external_mem_rply({ii}).data <= { optional_resize( f'{mem_p_data}', rs_data_w) };\n""");

        vhdl_f.write("""
end architecture;
""");
