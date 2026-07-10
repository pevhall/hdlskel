use work.ramface_regs_rw_ipkg;
use work.ramface_rply_combine_ipkg;
use work.skmap_module_ipkg;

package test_skmap_tree_top_ipkg is
  -- constant TOTAL_MODULES : natural := 4;
  -- constant RAMFACE_LATENCY_DEFAULT : natural :=
    -- skmap_module_ipkg.RAMFACE_LATENCY +
    -- ramface_rply_combine_ipkg.get_latency(WRKER_LEN=>TOTAL_MODULES);

  function get_ramface_latency(
    TOTAL_MODULES : natural
  ) return natural;

end package;

package body test_skmap_tree_top_ipkg is

  function get_ramface_latency(
    TOTAL_MODULES : natural
  ) return natural is
  begin
    return ramface_rply_combine_ipkg.get_latency(WRKR_LEN=>TOTAL_MODULES) + skmap_module_ipkg.RAMFACE_LATENCY;
  end function;

end package body;

--------------------------------------------------------------------------------

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;
use work.vec_pkg.all;

use work.ramface_pkg.all;
use work.skmap_pkg.all;
use work.skmap_map_acc_pkg.all;

use work.skmap_module_ipkg;
use work.test_skmap_tree_top_ipkg;

entity test_skmap_tree_top is
  generic (
    TREE_DEPTH      : positive range 2 to positive'high;
    TREE_WIDTH      : positive;
    SKMAP_BYTE_ALIGN : natural := 1;
    TOTAL_MODULES   : natural := TREE_DEPTH+TREE_WIDTH-1;
    RAMFACE_ADDR_W  : natural;
    RAMFACE_DATA_W  : natural;
    RAMFACE_WREN_W  : natural := RAMFACE_DATA_W/8;
    RAMFACE_LATENCY : natural := 4+test_skmap_tree_top_ipkg.get_ramface_latency(TOTAL_MODULES=>TOTAL_MODULES)
  );
  port (
    clk_i : in  std_ulogic;

    ramface_ce_i   : in std_ulogic := '1';
    ramface_rqst_i : in ramface_rqst_t(
      addr(RAMFACE_ADDR_W-1 downto 0),
      wren(RAMFACE_WREN_W-1 downto 0),
      data(RAMFACE_DATA_W-1 downto 0)
    );
    ramface_rply_o : out ramface_rply_t(
      data(RAMFACE_DATA_W -1 downto 0)
    )
  );
end entity;

-- use work.ramface_rply_combine_ipkg;
use work.skmap_module_ipkg;

architecture rtl of test_skmap_tree_top is

  constant RAMFACE_LATENCY_MODULE  : natural := skmap_module_ipkg.RAMFACE_LATENCY;
  constant RAMFACE_LATENCY_COMBINE : natural := RAMFACE_LATENCY - RAMFACE_LATENCY_MODULE;
  constant SKMAP_ADDR_DEPTH_SEP : natural := 16#1000#;
  constant SKMAP_ADDR_WIDTH_SEP : natural := 16#100#;
  signal vec_ramface_rply : vec_ramface_rply_t(0 to TOTAL_MODULES-1)(data(RAMFACE_DATA_W-1 downto 0));
  alias vec_ramface_rply_depth is vec_ramface_rply(0 to TREE_DEPTH-1);
  alias vec_ramface_rply_width:vec_ramface_rply_t(0 to TREE_WIDTH-1) is vec_ramface_rply(TREE_DEPTH-1 to TOTAL_MODULES-1);
  constant SKMAP_ADDR_DEPTH : integer_vector :=  get_vec_int_range(TREE_DEPTH) * SKMAP_ADDR_DEPTH_SEP;
  constant SKMAP_ADDR_WIDTH : integer_vector := (get_vec_int_range(TREE_WIDTH) * SKMAP_ADDR_WIDTH_SEP) +
    SKMAP_ADDR_DEPTH(TREE_DEPTH-1);

begin

  g_depth : for IDX in 0 to TREE_DEPTH-3 generate
    signal trigger_flags : std_ulogic_vector(5-1 downto 0);
    signal trigger_flags_trigger : std_ulogic;
    signal trigger_flags_trigger_vec : std_ulogic_vector(5-1 downto 0);
  begin
    assert FALSE report "SKMAP_ADDR_DEPTH(IDX) = "&integer'image(SKMAP_ADDR_DEPTH(IDX)) severity NOTE;

    trigger_flags_trigger_vec <= trigger_flags and trigger_flags_trigger;
    i_test_skmap_tree_module : entity work.test_skmap_tree_module
    generic map (
      BASE_ADDR               => SKMAP_ADDR_DEPTH(IDX),
      SKMAP_KIDS              => ( 0=> SKMAP_ADDR_DEPTH(IDX+1)),
      SKMAP_BYTE_ALIGN        => SKMAP_BYTE_ALIGN,
      RAMFACE_ADDR_W          => RAMFACE_ADDR_W,
      RAMFACE_DATA_W          => RAMFACE_DATA_W,
      RAMFACE_WREN_W          => RAMFACE_WREN_W,
      RAMFACE_LATENCY         => RAMFACE_LATENCY_MODULE,
      TREE_DEPTH              => IDX,
      TREE_WIDTH              => 0
    )
    port map (
      clk_i                   => clk_i,
      ramface_ce_i            => ramface_ce_i,
      ramface_rqst_i          => ramface_rqst_i,
      ramface_rply_o          => vec_ramface_rply_depth(IDX),
      trigger_flags_trigger_o => trigger_flags_trigger,
      trigger_flags_o         => trigger_flags,
      flag_debug_i            => trigger_flags_trigger_vec(0),
      flag_info_i             => trigger_flags_trigger_vec(1),
      flag_warn_i             => trigger_flags_trigger_vec(2),
      flag_error_i            => trigger_flags_trigger_vec(3),
      flag_fatal_i            => trigger_flags_trigger_vec(4)
    );
  end generate;

  g_branch : for IDX in TREE_DEPTH-2 to TREE_DEPTH-2 generate
    signal trigger_flags : std_ulogic_vector(5-1 downto 0);
    signal trigger_flags_trigger : std_ulogic;
    signal trigger_flags_trigger_vec : std_ulogic_vector(5-1 downto 0);
  begin
    assert FALSE report "SKMAP_ADDR_DEPTH(IDX) = "&integer'image(SKMAP_ADDR_DEPTH(IDX)) severity NOTE;

    trigger_flags_trigger_vec <= trigger_flags and trigger_flags_trigger;
    i_test_skmap_tree_module : entity work.test_skmap_tree_module
    generic map (
      BASE_ADDR               => SKMAP_ADDR_DEPTH(IDX),
      SKMAP_KIDS              => SKMAP_ADDR_WIDTH,
      SKMAP_BYTE_ALIGN        => SKMAP_BYTE_ALIGN,
      RAMFACE_ADDR_W          => RAMFACE_ADDR_W,
      RAMFACE_DATA_W          => RAMFACE_DATA_W,
      RAMFACE_WREN_W          => RAMFACE_WREN_W,
      RAMFACE_LATENCY         => RAMFACE_LATENCY_MODULE,
      TREE_DEPTH              => IDX,
      TREE_WIDTH              => 0
    )
    port map (
      clk_i                   => clk_i,
      ramface_ce_i            => ramface_ce_i,
      ramface_rqst_i          => ramface_rqst_i,
      ramface_rply_o          => vec_ramface_rply_depth(IDX),
      trigger_flags_trigger_o => trigger_flags_trigger,
      trigger_flags_o         => trigger_flags,
      flag_debug_i            => trigger_flags_trigger_vec(0),
      flag_info_i             => trigger_flags_trigger_vec(1),
      flag_warn_i             => trigger_flags_trigger_vec(2),
      flag_error_i            => trigger_flags_trigger_vec(3),
      flag_fatal_i            => trigger_flags_trigger_vec(4)
    );
  end generate;

  g_width : for IDX in 0 to TREE_WIDTH-1 generate
    signal trigger_flags : std_ulogic_vector(5-1 downto 0);
    signal trigger_flags_trigger : std_ulogic;
    signal trigger_flags_trigger_vec : std_ulogic_vector(5-1 downto 0);
  begin

    assert FALSE report "SKMAP_ADDR_WIDTH(IDX) = "&integer'image(SKMAP_ADDR_WIDTH(IDX)) severity NOTE;
    trigger_flags_trigger_vec <= trigger_flags and trigger_flags_trigger;
    i_test_skmap_tree_module : entity work.test_skmap_tree_module
    generic map (
      BASE_ADDR               => SKMAP_ADDR_WIDTH(IDX),
      SKMAP_BYTE_ALIGN        => SKMAP_BYTE_ALIGN,
      RAMFACE_ADDR_W          => RAMFACE_ADDR_W,
      RAMFACE_DATA_W          => RAMFACE_DATA_W,
      RAMFACE_WREN_W          => RAMFACE_WREN_W,
      RAMFACE_LATENCY         => RAMFACE_LATENCY_MODULE,
      TREE_DEPTH              => TREE_DEPTH-1,
      TREE_WIDTH              => IDX
    )
    port map (
      clk_i                   => clk_i,
      ramface_ce_i            => ramface_ce_i,
      ramface_rqst_i          => ramface_rqst_i,
      ramface_rply_o          => vec_ramface_rply_width(IDX),
      trigger_flags_trigger_o => trigger_flags_trigger,
      trigger_flags_o         => trigger_flags,
      flag_debug_i            => trigger_flags_trigger_vec(0),
      flag_info_i             => trigger_flags_trigger_vec(1),
      flag_warn_i             => trigger_flags_trigger_vec(2),
      flag_error_i            => trigger_flags_trigger_vec(3),
      flag_fatal_i            => trigger_flags_trigger_vec(4)
    );
  end generate;

  i_ramface_rply_combine : entity work.ramface_rply_combine
  generic map (
    RAMFACE_DATA_W  => RAMFACE_DATA_W,
    WRKR_LEN    => TOTAL_MODULES,
    LATENCY     => RAMFACE_LATENCY_COMBINE
  )
  port map (
    clk_i          => clk_i,
    ce_i           => ramface_ce_i,
    wrkr_rply_i    => vec_ramface_rply,
    mstr_rply_o    => ramface_rply_o
  );
end architecture;
