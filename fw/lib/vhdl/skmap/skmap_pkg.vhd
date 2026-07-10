library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;
use work.vec_pkg.all;
use work.misc_pkg.all;

package skmap_pkg is

  constant SKMAP_HEAD_LEN : natural := 4;
  constant SKMAP_HEAD_W   : natural := SKMAP_HEAD_LEN * 32;


--            ╓──────────┬──────────┬──────────┬──────────┐
--            ║  Byte 0  │  Byte 1  │  Byte 2  │  Byte 3  │
-- ╒══════════╬══════════╧══════════╧══════════╧══════════╡
-- │  Word 0  ║                                           │
-- ├──────────╢                    ID          ┌──────────┤
-- │  Word 1  ║                                │   Sync   │
-- ├──────────╫──────────┬──────────┬──────────┴──────────┤
-- │  Word 2  ║ Version  │  Flags   │       Checksum      │
-- ├──────────╫──────────┼──────────┼──────────┬──────────┤
-- │  Word 3  ║ Len_Kids │ Len_Sub  │  Len_K   │  Len_Var │
-- └──────────╨──────────┴──────────┴──────────┴──────────┘

  constant SKMAP_ID_SIZE     : natural := 7;
  constant SKMAP_ID_W        : natural := SKMAP_ID_SIZE*8;
  constant SKMAP_SYNC_W      : natural := 8;
  constant SKMAP_VERSION_W   : natural := 8;
  constant SKMAP_FLAGS_W     : natural := 8;
  constant SKMAP_CHECKSUM_W  : natural := 16;
  constant SKMAP_LEN_KIDS_W  : natural := 8;
  constant SKMAP_LEN_SUB_W   : natural := 8;
  constant SKMAP_LEN_K_W     : natural := 8;
  constant SKMAP_LEN_VAR_W   : natural := 8;

  constant SKMAP_SYNC : std_ulogic_vector(SKMAP_SYNC_W-1 downto 0) := x"D8";

  subtype skmap_id_t is string(1 to SKMAP_ID_SIZE);
  subtype skmap_version_t  is integer range 0 to 2**SKMAP_VERSION_W-1;
  subtype skmap_flags_t    is std_ulogic_vector(SKMAP_FLAGS_W-1 downto 0);
  subtype skmap_checksum_t is integer range 0 to 2**SKMAP_CHECKSUM_W-1;
  subtype skmap_len_kids_t is integer range 0 to 2**SKMAP_LEN_KIDS_W-1;
  subtype skmap_len_sub_t  is integer range 0 to 2**SKMAP_LEN_SUB_W -1;
  subtype skmap_len_k_t    is integer range 0 to 2**SKMAP_LEN_K_W-1;
  subtype skmap_len_var_t  is integer range 0 to 2**SKMAP_LEN_VAR_W-1;

  type skmap_head_t is record
    id : string(1 to SKMAP_ID_SIZE);
    version  : skmap_version_t;
    flags    : skmap_flags_t;
    checksum : skmap_checksum_t;
    len_kids : skmap_len_kids_t;
    len_sub  : skmap_len_sub_t;
    len_k    : skmap_len_k_t;
    len_var  : skmap_len_var_t;
  end record;

  function to_vec_slv32(head : skmap_head_t) return vec_slv32_t;
  function to_vec_int(head : skmap_head_t) return integer_vector;

  -- sub
  constant SKMAP_SUB_ID_W : natural := 8;
  subtype skmap_sub_id_t is natural range 0 to 2**SKMAP_SUB_ID_W-1;
  constant SKMAP_SUB_ID_PAD        : skmap_sub_id_t := 16#00#;
  constant SKMAP_SUB_ID_BYTE_ALIGN : skmap_sub_id_t := 16#1A#;
  function make_skmap_sub_byte_align(byte_align : natural) return integer_vector;


end package;

package body skmap_pkg is

  constant SKMAP_HEAD_WS : integer_vector := (
    SKMAP_ID_W,
    SKMAP_SYNC_W,
    SKMAP_VERSION_W,
    SKMAP_FLAGS_W,
    SKMAP_CHECKSUM_W,
    SKMAP_LEN_KIDS_W,
    SKMAP_LEN_SUB_W ,
    SKMAP_LEN_K_W,
    SKMAP_LEN_VAR_W
  );

  function to_vec_slv32(head : skmap_head_t) return vec_slv32_t is
    variable regs : vec_slv32_t(0 to SKMAP_HEAD_LEN-1);
    variable regs_flat : std_ulogic_vector(SKMAP_HEAD_W-1 downto 0);
  begin
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 0, to_slv(head.id));
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 1, SKMAP_SYNC);
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 2, to_slv(head.version, SKMAP_VERSION_W));
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 3, zeros(SKMAP_FLAGS_W));
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 4, to_slv(head.checksum, SKMAP_CHECKSUM_W));
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 5, to_slv(head.len_kids, SKMAP_LEN_KIDS_W));
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 6, to_slv(head.len_sub, SKMAP_LEN_SUB_W));
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 7, to_slv(head.len_k, SKMAP_LEN_K_W));
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 8, to_slv(head.len_var, SKMAP_LEN_VAR_W));
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

end package body;
