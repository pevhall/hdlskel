
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;
use work.vec_pkg.all;
-- use work.misc_pkg.all;

-- use work.skmap_pkg.all;

package skmap_map_acc_pkg is

  constant SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG : integer;

  procedure skmap_map_acc_ro(
    signal regs_rd_data_io : inout vec_slv32_t; 
    byte_idx_io : inout natural;
    val_i : in std_ulogic_vector;
    constant BYTE_ALIGN : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  );
  procedure skmap_map_acc_ro(
    signal regs_rd_data_io : inout vec_slv32_t; 
    byte_idx_io : inout natural;
    val_i : in vec_slv32_t;
    constant BYTE_ALIGN : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  );
  -- procedure skamp_map_acc_rw(
  --   signal regs_wr_data_i  : in    vec_slv32_t; 
  --   signal regs_rd_data_io : inout vec_slv32_t; 
  --   byte_idx_io : inout natural;
  --   reg_rw_io : inout std_ulogic_vector;
  --   constant BYTE_ALIGN : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  -- );
  function skmap_map_acc_BYTE_ALIGN(
    WORD_W : natural;
    BYTE_ALIGN : integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  ) return natural;
end package;

package body skmap_map_acc_pkg is
  constant SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG : integer := 0;

  function skmap_map_acc_BYTE_ALIGN(
    WORD_W : natural;
    BYTE_ALIGN : integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  ) return natural is
  begin
    if BYTE_ALIGN = SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG then
      report "WORD_W = "&integer'image(WORD_W);
      report "promote_to_sw_w(WORD_W) = "&integer'image(promote_to_sw_w(WORD_W));
      return promote_to_sw_w(WORD_W)/8;
    end if;

    assert BYTE_ALIGN >= 0
    report "Unsupported"
    severity FAILURE;
    return BYTE_ALIGN;
  end function;

  procedure skmap_map_acc_ro(
    signal regs_rd_data_io : inout vec_slv32_t; 
    byte_idx_io : inout natural;
    val_i : in std_ulogic_vector;
    constant BYTE_ALIGN : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  ) is
    -- constant REG_BYTE_LEN : natural := ceil_div(reg_i'length, 8);
    -- variable reg_byte     : natural := 0;
    constant BYTE_ALIGN_INTL : natural := skmap_map_acc_BYTE_ALIGN(val_i'length, BYTE_ALIGN);
    variable val_dt : std_ulogic_vector(val_i'length-1 downto 0) := rng_dt(val_i);
    variable val_len_left : natural := val_i'length;
    variable len          : natural;
    variable b_start : natural;
    variable reg_idx : natural;
    variable reg_low  : natural;
    variable reg_high : natural;
    variable val_low, val_high : natural;

  begin

    byte_idx_io := ceil_multiple(byte_idx_io, BYTE_ALIGN_INTL);

    reg_idx := byte_idx_io / 4;
    b_start := byte_idx_io - reg_idx*4;
    val_low := 0;
    while val_len_left > 0 loop
      len := minimum(32-8*b_start, val_len_left);

      reg_low  := b_start;
      reg_high := reg_low + len-1;
      val_high := val_low + len-1;
      regs_rd_data_io(reg_idx)(reg_high downto reg_low) <= val_dt(val_high downto val_low);

      inc(val_low, len);
      inc(val_len_left, -len);
      inc(reg_idx);
      b_start := 0;
    end loop;

    inc(byte_idx_io, ceil_div(val_i'length, 8));
    byte_idx_io := ceil_multiple(byte_idx_io, BYTE_ALIGN_INTL);

  end procedure;

  procedure skmap_map_acc_ro(
    signal regs_rd_data_io : inout vec_slv32_t; 
    byte_idx_io : inout natural;
    val_i : in vec_slv32_t;
    constant BYTE_ALIGN : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  ) is
  begin
    for idx in val_i'range loop
      skmap_map_acc_ro(regs_rd_data_io, byte_idx_io, val_i(idx), BYTE_ALIGN);
    end loop;
  end procedure;

  -- procedure skamp_map_acc_rw(
  --   signal regs_wr_data_i  : in    vec_slv32_t; 
  --   signal regs_rd_data_io : inout vec_slv32_t; 
  --   byte_idx_io : inout natural;
  --   reg_io : inout std_ulogic_vector
  -- );

end package body;
