
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
    val_i : in vec_slv_t;
    constant BYTE_ALIGN : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  );

  procedure skmap_map_acc_rw_var(
    signal regs_rd_data_io : inout vec_slv32_t; 
    regs_wr_data_i  : in    vec_slv32_t; 
    byte_idx_io : inout natural;
    val_io      : inout std_ulogic_vector;
    constant BYTE_ALIGN : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  );
  procedure skmap_map_acc_rw(
    signal regs_rd_data_io : inout vec_slv32_t; 
    regs_wr_data_i  : in    vec_slv32_t; 
    byte_idx_io : inout natural;
    signal val_io : inout std_ulogic_vector;
    constant BYTE_ALIGN : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  );
  procedure skmap_map_acc_rw_var(
    signal regs_rd_data_io : inout vec_slv32_t; 
    regs_wr_data_i  : in    vec_slv32_t; 
    byte_idx_io : inout natural;
    val_io : inout vec_slv_t;
    constant BYTE_ALIGN : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  );
  procedure skmap_map_acc_rw(
    signal regs_rd_data_io : inout vec_slv32_t; 
    regs_wr_data_i  : in    vec_slv32_t; 
    byte_idx_io : inout natural;
    signal val_io : inout vec_slv_t;
    constant BYTE_ALIGN : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  );

  procedure skmap_map_acc_ws_var(
    signal regs_rd_data_io : inout vec_slv32_t; 
    regs_wr_data_i  : in    vec_slv32_t; 
    regs_wr_wren_i  : in    vec_slv4_t; 
    byte_idx_io : inout natural;
    val_io      : inout std_ulogic_vector;
    val_strb_o  : out   std_ulogic;
    constant BYTE_ALIGN : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  );

  procedure skmap_map_acc_ws_var(
    signal regs_rd_data_io : inout vec_slv32_t; 
    regs_wr_data_i  : in    vec_slv32_t; 
    regs_wr_wren_i  : in    vec_slv4_t; 
    byte_idx_io : inout natural;
    val_io      : inout vec_slv_t;
    val_strb_o  : out   std_ulogic_vector;
    constant BYTE_ALIGN : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  );

  -- procedure skmap_map_acc_ws(
  --   signal regs_rd_data_io : inout vec_slv32_t; 
  --   regs_wr_data_i  : in    vec_slv32_t; 
  --   regs_wr_wren_i  : in    vec_slv4_t; 
  --   byte_idx_io : inout natural;
  --   signal val_io : inout std_ulogic_vector;
  --   signal val_strb_o  : out   std_ulogic;
  --   constant BYTE_ALIGN : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  -- );

  procedure skmap_map_acc_ws(
    signal regs_rd_data_io : inout vec_slv32_t; 
    regs_wr_data_i  : in    vec_slv32_t; 
    regs_wr_wren_i  : in    vec_slv4_t; 
    byte_idx_io : inout natural;
    signal val_io      : inout vec_slv_t;
    signal val_strb_o  : out   std_ulogic_vector;
    constant BYTE_ALIGN : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  );

  procedure skmap_map_acc_rc(
    signal regs_rd_data_io : inout vec_slv32_t; 
    regs_wr_wren_i  : in    vec_slv4_t; 
    byte_idx_io : inout natural;
    val_set_i   : in std_ulogic_vector;
    constant BYTE_ALIGN : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  );

  function skmap_map_acc_BYTE_ALIGN(
    constant VAL_W : natural;
    constant BYTE_ALIGN : integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  ) return natural;

  procedure skmap_map_acc_byte_inc(
    byte_idx_io : inout natural;
    constant VAL_W : natural;
    constant BYTE_ALIGN : integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG;
    constant VEC_LEN : natural := 1
  );

end package;

package body skmap_map_acc_pkg is
  constant SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG : integer := 0;

  function skmap_map_acc_BYTE_ALIGN(
    constant VAL_W : natural;
    constant BYTE_ALIGN : integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  ) return natural is
  begin
    if BYTE_ALIGN = SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG then
      return promote_to_sw_w(VAL_W)/8;
    end if;

    assert BYTE_ALIGN >= 0
    report "Unsupported"
    severity FAILURE;
    return BYTE_ALIGN;
  end function;

  procedure skmap_map_acc_byte_inc(
    byte_idx_io : inout natural;
    constant VAL_W : natural;
    constant BYTE_ALIGN : integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG;
    constant VEC_LEN : natural := 1
  ) is
    constant BYTE_ALIGN_INTL : natural := skmap_map_acc_BYTE_ALIGN(VAL_W, BYTE_ALIGN);
  begin
    if VEC_LEN /= 0 then
      byte_idx_io := ceil_multiple(byte_idx_io, BYTE_ALIGN_INTL);
      inc(byte_idx_io, ceil_div(VAL_W, 8));
      byte_idx_io := ceil_multiple(byte_idx_io, BYTE_ALIGN_INTL);
    end if;
  end procedure;

  procedure skmap_map_acc_ro(
    signal regs_rd_data_io : inout vec_slv32_t; 
    byte_idx_io : inout natural;
    val_i : in std_ulogic_vector;
    constant BYTE_ALIGN : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  ) is

    constant BYTE_ALIGN_INTL : natural := skmap_map_acc_BYTE_ALIGN(val_i'length, BYTE_ALIGN);
    variable val_dt : std_ulogic_vector(val_i'length-1 downto 0) := rng_dt(val_i);
    variable val_len_left : natural := val_i'length;
    variable len     : natural;
    variable b_start : natural;
    variable reg_idx : natural;
    variable reg_low, reg_high : natural;
    variable val_low, val_high : natural;

  begin

    byte_idx_io := ceil_multiple(byte_idx_io, BYTE_ALIGN_INTL);

    reg_idx := byte_idx_io / 4;
    b_start := byte_idx_io - reg_idx*4;
    val_low := 0;
    while val_len_left > 0 loop
      len := minimum(32-8*b_start, val_len_left);

      reg_low  := 8*b_start;
      reg_high := reg_low + len-1;
      val_high := val_low + len-1;
      -- report "len = "&integer'image(len);
      -- report "val_len_left = "&integer'image(val_len_left);
      -- report "reg_idx = "&integer'image(reg_idx);
      -- report "reg_low = "&integer'image(reg_low);
      -- report "val_low = "&integer'image(val_low);
      -- report "val_high = "&integer'image(val_high);
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
    val_i : in vec_slv_t;
    constant BYTE_ALIGN : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  ) is
  begin
    for idx in val_i'range loop
      skmap_map_acc_ro(regs_rd_data_io, byte_idx_io, val_i(idx), BYTE_ALIGN);
    end loop;
  end procedure;

  procedure skmap_map_acc_rw_var(
    signal regs_rd_data_io : inout vec_slv32_t; 
    regs_wr_data_i  : in    vec_slv32_t; 
    byte_idx_io            : inout natural;
    val_io                 : inout std_ulogic_vector;
    constant BYTE_ALIGN    : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  ) is

    variable empty : vec_slv4_t(0 to -1);
    variable ignore : std_ulogic;

  begin
    skmap_map_acc_ws_var(
      regs_rd_data_io => regs_rd_data_io,
      regs_wr_data_i  => regs_wr_data_i,
      regs_wr_wren_i  => empty,
      byte_idx_io     => byte_idx_io,
      val_io          => val_io,
      val_strb_o      => ignore,
      BYTE_ALIGN      => BYTE_ALIGN 
    );

  end procedure;

  procedure skmap_map_acc_rw(
    signal regs_rd_data_io : inout vec_slv32_t; 
    regs_wr_data_i  : in    vec_slv32_t; 
    byte_idx_io            : inout natural;
    signal val_io          : inout std_ulogic_vector;
    constant BYTE_ALIGN    : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  ) is
    variable val_v : std_ulogic_vector(val_io'range);
  begin
    skmap_map_acc_rw_var(
      regs_rd_data_io => regs_rd_data_io,
      regs_wr_data_i  => regs_wr_data_i,
      byte_idx_io     => byte_idx_io,
      val_io          => val_v,
      BYTE_ALIGN      => BYTE_ALIGN
    );
    val_io <= val_v;
  end procedure;

  procedure skmap_map_acc_rw_var(
    signal regs_rd_data_io : inout vec_slv32_t; 
    regs_wr_data_i  : in    vec_slv32_t; 
    byte_idx_io            : inout natural;
    val_io                 : inout vec_slv_t;
    constant BYTE_ALIGN    : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  ) is
  begin
    for idx in val_io'range loop
      skmap_map_acc_rw_var(
        regs_rd_data_io => regs_rd_data_io,
        regs_wr_data_i  => regs_wr_data_i,
        byte_idx_io     => byte_idx_io,
        val_io          => val_io(idx),
        BYTE_ALIGN      => BYTE_ALIGN
      );
    end loop;
  end procedure;

  procedure skmap_map_acc_rw(
    signal regs_rd_data_io : inout vec_slv32_t; 
    regs_wr_data_i  : in    vec_slv32_t; 
    byte_idx_io            : inout natural;
    signal val_io          : inout vec_slv_t;
    constant BYTE_ALIGN    : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  ) is
    constant ELEM_W : natural := get_elem_w(val_io); 
    variable val_v : vec_slv_t(val_io'range)(ELEM_W-1 downto 0);
  begin
    skmap_map_acc_rw_var(
      regs_wr_data_i  => regs_wr_data_i,
      regs_rd_data_io => regs_rd_data_io,
      byte_idx_io     => byte_idx_io,
      val_io          => val_v,
      BYTE_ALIGN      => BYTE_ALIGN
    );
    val_io <= val_v;
  end procedure;

  procedure skmap_map_acc_ws_var(
    signal regs_rd_data_io : inout vec_slv32_t; 
    regs_wr_data_i  : in    vec_slv32_t; 
    regs_wr_wren_i  : in    vec_slv4_t; 
    byte_idx_io : inout natural;
    val_io      : inout std_ulogic_vector;
    val_strb_o  : out   std_ulogic;
    constant BYTE_ALIGN : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  ) is
    constant BYTE_ALIGN_INTL : natural := skmap_map_acc_BYTE_ALIGN(val_io'length, BYTE_ALIGN);
    variable val_dt : std_ulogic_vector(val_io'length-1 downto 0);
    variable val_len_left : natural := val_io'length;
    variable len          : natural;
    variable reg_idx : natural;
    variable b_low, b_high : natural;
    variable reg_low, reg_high : natural;
    variable val_low, val_high : natural;

  begin

    byte_idx_io := ceil_multiple(byte_idx_io, BYTE_ALIGN_INTL);

    reg_idx := byte_idx_io / 4;
    b_low := byte_idx_io - reg_idx*4;
    val_low := 0;
    while val_len_left > 0 loop
      len := minimum(32-8*b_low, val_len_left);

      b_high   := b_low+len/8;
      reg_low  := b_low;
      reg_high := reg_low + len-1;
      val_high := val_low + len-1;
      val_dt(val_high downto val_low)                   := regs_wr_data_i(reg_idx)(reg_high downto reg_low);
      regs_rd_data_io(reg_idx)(reg_high downto reg_low) <= regs_wr_data_i(reg_idx)(reg_high downto reg_low);

      inc(val_low, len);
      inc(val_len_left, -len);
      inc(reg_idx);
      b_low := 0;
    end loop;
    val_io := val_dt;

    inc(byte_idx_io, ceil_div(val_io'length, 8));

    if regs_wr_wren_i'length /= 0 then
      reg_idx := (byte_idx_io-1) / 4;
      b_low := (byte_idx_io-1) - reg_idx*4;
      val_strb_o := regs_wr_wren_i(reg_idx)(b_low);
    end if;
    byte_idx_io := ceil_multiple(byte_idx_io, BYTE_ALIGN_INTL);

  end procedure;

  procedure skmap_map_acc_rc(
    signal regs_rd_data_io : inout vec_slv32_t; 
    regs_wr_wren_i  : in    vec_slv4_t; 
    byte_idx_io : inout natural;
    val_set_i   : in std_ulogic_vector;
    constant BYTE_ALIGN : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  ) is
    constant BYTE_ALIGN_INTL : natural := skmap_map_acc_BYTE_ALIGN(val_set_i'length, BYTE_ALIGN);
    variable val_dt : std_ulogic_vector(val_set_i'length-1 downto 0);
    variable val_len_left : natural := val_set_i'length;
    variable len          : natural;
    variable b_low, b_high : natural;
    variable reg_idx : natural;
    variable reg_low, reg_high : natural;
    variable val_low, val_high : natural;

  begin

    byte_idx_io := ceil_multiple(byte_idx_io, BYTE_ALIGN_INTL);

    reg_idx := byte_idx_io / 4;
    b_low := byte_idx_io - reg_idx*4;
    val_low := 0;
    while val_len_left > 0 loop
      len := minimum(32-8*b_low, val_len_left);

      b_high   := b_low+len/8;
      reg_low  := 8*b_low;
      reg_high := reg_low + len-1;
      val_high := val_low + len-1;
      for bb in b_low to b_high loop
        if regs_wr_wren_i(reg_idx)(bb) = '1' then
          regs_rd_data_io(reg_idx)(8*(bb+1)-1 downto 8*bb) <= (others => '0');
        end if;
      end loop;
      for vv in val_low to val_high loop
        if val_dt(vv) = '1' then
          regs_rd_data_io(reg_idx)(vv) <= '1';
        end if;
      end loop;
      inc(val_low, len);
      inc(val_len_left, -len);
      inc(reg_idx);
      b_low := 0;
    end loop;

    inc(byte_idx_io, ceil_div(val_set_i'length, 8));

    byte_idx_io := ceil_multiple(byte_idx_io, BYTE_ALIGN_INTL);
  end procedure;

  procedure skmap_map_acc_ws_var(
    signal regs_rd_data_io : inout vec_slv32_t; 
    regs_wr_data_i  : in    vec_slv32_t; 
    regs_wr_wren_i  : in    vec_slv4_t; 
    byte_idx_io : inout natural;
    val_io      : inout vec_slv_t;
    val_strb_o  : out   std_ulogic_vector;
    constant BYTE_ALIGN : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  ) is
  begin
    for ii in val_io'range loop
      skmap_map_acc_ws_var(
        regs_rd_data_io => regs_rd_data_io,
        regs_wr_data_i  => regs_wr_data_i,
        regs_wr_wren_i  => regs_wr_wren_i,
        byte_idx_io     => byte_idx_io,
        val_io          => val_io(ii),
        val_strb_o      => val_strb_o(ii),
        BYTE_ALIGN      => BYTE_ALIGN
      );
    end loop;
  end procedure;

  procedure skmap_map_acc_ws(
    signal regs_rd_data_io : inout vec_slv32_t; 
    regs_wr_data_i  : in    vec_slv32_t; 
    regs_wr_wren_i  : in    vec_slv4_t; 
    byte_idx_io : inout natural;
    signal val_io : inout vec_slv_t;
    signal val_strb_o  : out   std_ulogic_vector;
    constant BYTE_ALIGN : in integer := SKMAP_MAP_ACC_BYTE_ALIGN_TO_REG
  ) is
    variable val : vec_slv_t(val_io'range)(get_elem_w(val_io)-1 downto 0);
    variable val_strb : std_ulogic_vector(val_io'high downto val_io'low);
  begin
    skmap_map_acc_ws_var(
      regs_rd_data_io => regs_rd_data_io,
      regs_wr_data_i  => regs_wr_data_i,
      regs_wr_wren_i  => regs_wr_wren_i,
      byte_idx_io     => byte_idx_io,
      val_io          => val,
      val_strb_o      => val_strb,
      BYTE_ALIGN      => BYTE_ALIGN
    );
    val_io <= val;
    val_strb_o <= val_strb;
  end procedure;

end package body;
