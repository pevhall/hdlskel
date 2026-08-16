library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;
use work.vec_pkg.all;
use work.misc_pkg.all;

package skmap_pkg is

  constant SKMAP_HEAD_LEN : natural := 4;
  constant SKMAP_WORD_BYTES : natural := 4;
  constant SKMAP_WORD_W   : natural := SKMAP_WORD_BYTES * 8;
  constant SKMAP_HEAD_W   : natural := SKMAP_HEAD_LEN * SKMAP_WORD_W;


--            ╓──────────┬──────────┬──────────┬──────────┐
--            ║  Byte 0  │  Byte 1  │  Byte 2  │  Byte 3  │
-- ╒══════════╬══════════╧══════════╧══════════╧══════════╡
-- │  Word 0  ║                                           │
-- ├──────────╢                    ID                     │
-- │  Word 1  ║                                           │
-- ├──────────╫──────────┬──────────┬─────────────────────┤
-- │  Word 2  ║ Version  │  Sync    │       Checksum      │
-- ├──────────╫──────────┼──────────┼──────────┬──────────┤
-- │  Word 3  ║ Len_Kids │ Len_Sub  │  Len_K   │  Len_Var │
-- └──────────╨──────────┴──────────┴──────────┴──────────┘

  constant SKMAP_ID_BYTES     : natural := 8;
  constant SKMAP_ID_W        : natural := SKMAP_ID_BYTES*8;
  constant SKMAP_SYNC_W      : natural := 8;
  constant SKMAP_VERSION_W   : natural := 8;
  constant SKMAP_CHECKSUM_W  : natural := 16;
  constant SKMAP_LEN_KIDS_W  : natural := 8;
  constant SKMAP_LEN_SUB_W   : natural := 8;
  constant SKMAP_LEN_K_W     : natural := 8;
  constant SKMAP_LEN_VAR_W   : natural := 8;

  constant SKMAP_SYNC : std_ulogic_vector(SKMAP_SYNC_W-1 downto 0) := x"D8";

  subtype skmap_id_t is string(1 to SKMAP_ID_BYTES);
  subtype skmap_version_t  is integer range 0 to 2**SKMAP_VERSION_W-1;
  subtype skmap_checksum_t is integer range 0 to 2**SKMAP_CHECKSUM_W-1;
  subtype skmap_len_kids_t is integer range 0 to 2**SKMAP_LEN_KIDS_W-1;
  subtype skmap_len_sub_t  is integer range 0 to 2**SKMAP_LEN_SUB_W -1;
  subtype skmap_len_k_t    is integer range 0 to 2**SKMAP_LEN_K_W-1;
  subtype skmap_len_var_t  is integer range 0 to 2**SKMAP_LEN_VAR_W-1;

  function to_skmap_id(id : string) return skmap_id_t;

  type skmap_head_t is record
    id       : skmap_id_t;
    version  : skmap_version_t;
    checksum : skmap_checksum_t;
    len_kids : skmap_len_kids_t;
    len_sub  : skmap_len_sub_t;
    len_k    : skmap_len_k_t;
    len_var  : skmap_len_var_t;
  end record;

  type skmap_acc_t is (
    na, k, ro, rc, rw, wt
  );

  type skmap_external_mem_t is record
    -- base_addr    : natural;
    data_w       : natural;
    depth        : natural;
    latency      : natural;
    acc          : skmap_acc_t ;
    -- byte_align   : natural;
  end record;

  type skmap_vec_external_mem_t is array (natural range <>) of skmap_external_mem_t;
  constant NULL_SKMAP_VEC_EXTERNAL_MEM : skmap_vec_external_mem_t(0 to -1);

  function to_vec_slv32(head : skmap_head_t) return vec_slv32_t;
  function to_vec_int(head : skmap_head_t) return integer_vector;

  -- sub
  constant SKMAP_SUB_ID_W : natural := 8;
  subtype skmap_sub_id_t is natural range 0 to 2**SKMAP_SUB_ID_W-1;
  constant SKMAP_SUB_ID_PAD        : skmap_sub_id_t := 16#00#;
  constant SKMAP_SUB_ID_BYTE_ALIGN : skmap_sub_id_t := 16#1A#;
  constant SKMAP_SUB_ID_EXTERNAL_MEM  : skmap_sub_id_t := 16#3B#;
  function make_skmap_sub_byte_align(byte_align : natural) return integer_vector;
  function make_skmap_sub_external_mem( mem : skmap_external_mem_t; base_addr :  integer) return integer_vector;
  function make_vec_skmap_sub_external_mem( vec_mem : skmap_vec_external_mem_t; vec_base_addr : integer_vector ) return integer_vector;

  -- external mem
  function skmap_get_external_mem_size( mem : skmap_external_mem_t ) return natural;
  function skmap_get_external_mem_max_size   ( vec_mem : skmap_vec_external_mem_t ) return natural;
  function skmap_get_external_mem_max_addr_w ( vec_mem : skmap_vec_external_mem_t ) return natural;
  function skmap_get_external_mem_max_data_w ( vec_mem : skmap_vec_external_mem_t ) return natural;
  function skmap_get_external_mem_max_latency( vec_mem : skmap_vec_external_mem_t ) return natural;

end package;

package body skmap_pkg is

  function to_skmap_id(id : string) return skmap_id_t is
    variable SKMAP_ID : skmap_id_t := (others => NUL);
  begin
    SKMAP_ID(id'range) := id;
    return SKMAP_ID;
  end function;

  constant SKMAP_HEAD_WS : integer_vector := (
    SKMAP_ID_W,
    SKMAP_SYNC_W,
    SKMAP_VERSION_W,
    SKMAP_CHECKSUM_W,
    SKMAP_LEN_KIDS_W,
    SKMAP_LEN_SUB_W ,
    SKMAP_LEN_K_W,
    SKMAP_LEN_VAR_W
  );

  constant NULL_SKMAP_VEC_EXTERNAL_MEM : skmap_vec_external_mem_t(0 to -1) := (others => (acc => na, data_w => 0, depth => 0, latency => 0));

  function to_vec_slv32(head : skmap_head_t) return vec_slv32_t is
    variable regs : vec_slv32_t(0 to SKMAP_HEAD_LEN-1);
    variable regs_flat : std_ulogic_vector(SKMAP_HEAD_W-1 downto 0);
  begin
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 0, to_slv(head.id));
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 1, SKMAP_SYNC);
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 2, to_slv(head.version, SKMAP_VERSION_W));
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 3, to_slv(head.checksum, SKMAP_CHECKSUM_W));
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 4, to_slv(head.len_kids, SKMAP_LEN_KIDS_W));
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 5, to_slv(head.len_sub, SKMAP_LEN_SUB_W));
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 6, to_slv(head.len_k, SKMAP_LEN_K_W));
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 7, to_slv(head.len_var, SKMAP_LEN_VAR_W));
    regs := to_vec_slv32(regs_flat);
    return regs;
  end function;

  function to_vec_int(head : skmap_head_t) return integer_vector is
  begin
    return to_vec_int(to_vec_signed(to_vec_slv32(head)));
  end function;

  function make_skmap_sub_byte_align(byte_align : natural) return integer_vector is
    variable sub : integer_vector(0 to 0) := (0 => SKMAP_SUB_ID_BYTE_ALIGN + 2**8*byte_align);
  begin
    -- report "byte_align = "&integer'image(byte_align);
    assert byte_align < 2**8;
    if byte_align = 0 or byte_align = 1 then
      return NULL_INTEGER_VECTOR;
    end if;
    return sub;
  end function;

  function priv_acc_to_int(acc : skmap_acc_t) return natural is
  begin
    case acc is
      when  na => return 0;
      when  k  => return 1;
      when  ro => return 2;
      when  rc => return 3;
      when  rw => return 4;
      when  wt => return 5;
    end case;
  end function;

  constant SKMAP_SUB_EXTERNAL_MEM_LEN : natural := 3;

  function skmap_get_external_mem_size( mem : skmap_external_mem_t ) return natural is
  begin
    return mem.data_w/8 * mem.depth;
  end function;

  function make_skmap_sub_external_mem( mem : skmap_external_mem_t; base_addr :  integer) return integer_vector is
    variable acc_int : integer := priv_acc_to_int(mem.acc);
    variable size_bytes : integer := skmap_get_external_mem_size(mem);
    variable sub : integer_vector(0 to SKMAP_SUB_EXTERNAL_MEM_LEN-1) := ( 
      skmap_sub_id_external_mem + 2**8*acc_int,
       base_addr, size_bytes
     );
  begin
    assert mem.data_w rem 8 = 0 severity Failure;
    return sub;
  end function;

  function make_vec_skmap_sub_external_mem( vec_mem : skmap_vec_external_mem_t; vec_base_addr : integer_vector ) return integer_vector is
    constant L : natural := SKMAP_SUB_EXTERNAL_MEM_LEN;
    variable vec_sub : integer_vector(0 to (vec_mem'length)*L-1);
  begin
    for ii in 0 to vec_mem'length-1 loop
      vec_sub(ii*L to (ii+1)*L-1) := make_skmap_sub_external_mem(
        vec_mem(ii+vec_mem'low),
        vec_base_addr(ii+vec_base_addr'low)
      );
    end loop;
    return vec_sub;
  end function;

  function skmap_get_external_mem_max_size   ( vec_mem : skmap_vec_external_mem_t ) return natural is
    variable size : natural;
    variable max_size : natural := 0;
  begin
    for ii in vec_mem'range loop
      size := skmap_get_external_mem_size(vec_mem(ii));
      if size > max_size then
        max_size := size;
      end if;
    end loop;
    return max_size;
  end function;

  function skmap_get_external_mem_max_addr_w( vec_mem : skmap_vec_external_mem_t ) return natural is
    variable addr_w : natural;
    variable max_addr_w : natural := 0;
  begin
    for ii in vec_mem'range loop
      addr_w := ceil_log2(vec_mem(ii).depth);
      if addr_w > max_addr_w then
        max_addr_w := addr_w;
      end if;
    end loop;
    return max_addr_w;
  end function;

  function skmap_get_external_mem_max_data_w( vec_mem : skmap_vec_external_mem_t ) return natural is
    variable max_data_w : natural := 0;
  begin
    for ii in vec_mem'range loop
      if vec_mem(ii).data_w > max_data_w then
        max_data_w := vec_mem(ii).data_w;
      end if;
    end loop;
    return max_data_w;
  end function;

  function skmap_get_external_mem_max_latency( vec_mem : skmap_vec_external_mem_t ) return natural is
    variable latency : natural := 0;
  begin
    for ii in vec_mem'range loop
      if vec_mem(ii).latency > latency then
        latency := vec_mem(ii).latency;
      end if;
    end loop;
    return latency;
  end function;


end package body;
