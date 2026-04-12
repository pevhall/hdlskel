library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;
use work.vec_pkg.all;
use work.misc_pkg.all;

package skmap_pkg is

  constant SKMAP_HEAD_LEN : natural := 4;
  constant SKMAP_HEAD_W   : natural := SKMAP_HEAD_LEN * 32;

  constant SKMAP_ID_CHARS : natural := 8;
  constant SKMAP_ID_W : natural := SKMAP_ID_CHARS*8;
  constant SKMAP_SYNC_W : natural := 8;
  constant SKMAP_VER_MAJOR_W : natural := 8;
  constant SKMAP_VER_MINOR_W : natural := 4;
  constant SKMAP_RESERVED_W  : natural := 4;
  constant SKMAP_FLAGS_W : natural := 8;
  constant SKMAP_LEN_SUB_W  : natural := 8;
  constant SKMAP_LEN_KIDS_W : natural := 8;
  constant SKMAP_LEN_K_W : natural := 8;
  constant SKMAP_LEN_VAR_W : natural := 8;

  subtype skmap_sync_t is std_ulogic_vector(SKMAP_SYNC_W-1 downto 0);
  subtype skmap_ver_major_t is integer range 0 to 2**SKMAP_VER_MAJOR_W-1;
  subtype skmap_ver_minor_t is integer range 0 to 2**SKMAP_VER_MINOR_W-1;
  subtype skmap_flags_t is std_ulogic_vector(SKMAP_FLAGS_W-1 downto 0);
  subtype skmap_len_kids_t  is integer range 0 to 2**SKMAP_LEN_KIDS_W-1;
  subtype skmap_len_sub_t   is integer range 0 to 2**SKMAP_LEN_SUB_W -1;
  subtype skmap_len_k_t     is integer range 0 to 2**SKMAP_LEN_K_W-1;
  subtype skmap_len_var_t   is integer range 0 to 2**SKMAP_LEN_VAR_W-1;

  constant SKMAP_SYNC : skmap_sync_t := x"CC";
  type skmap_head_t is record
    id : string(1 to SKMAP_ID_CHARS);
    -- sync : skmap_sync_t;
    ver_major : skmap_ver_major_t;
    ver_minor : skmap_ver_minor_t;
    -- reserved     :
    -- flags        : skmap_flags_t;
    len_kids : skmap_len_kids_t;
    len_sub  : skmap_len_sub_t;
    len_k : skmap_len_k_t;
    len_var : skmap_len_var_t;
  end record;

  function to_vec_slv32(head : skmap_head_t) return vec_slv32_t;
  function to_vec_int(head : skmap_head_t) return integer_vector;

end package;

package body skmap_pkg is

  constant SKMAP_HEAD_WS : integer_vector := (
    SKMAP_ID_W,
    SKMAP_SYNC_W,
    SKMAP_VER_MAJOR_W,
    SKMAP_VER_MINOR_W,
    SKMAP_RESERVED_W,
    SKMAP_FLAGS_W,
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
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 2, to_slv(head.ver_major, SKMAP_VER_MAJOR_W));
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 3, to_slv(head.ver_minor, SKMAP_VER_MINOR_W));
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 4, zeros(SKMAP_RESERVED_W));
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 5, zeros(SKMAP_FLAGS_W));
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 6, to_slv(head.len_kids, SKMAP_LEN_KIDS_W));
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 7, to_slv(head.len_sub, SKMAP_LEN_SUB_W));
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 8, to_slv(head.len_k, SKMAP_LEN_K_W));
    to_flat_rec(regs_flat, SKMAP_HEAD_WS, 9, to_slv(head.len_var, SKMAP_LEN_VAR_W));
    regs := to_vec_slv32(regs_flat);
    return regs;
  end function;

  function to_vec_int(head : skmap_head_t) return integer_vector is
  begin
    return to_vec_int(to_vec_signed(to_vec_slv32(head)));
  end function;

end package body;
