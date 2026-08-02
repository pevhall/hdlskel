package ramface_rqst_w_adapt_ipkg is

  function get_LATENCY(SRC_RAMFACE_DATA_W : natural; DST_RAMFACE_DATA_W : natural) return natural;

end package;

package body ramface_rqst_w_adapt_ipkg is

  function get_LATENCY(SRC_RAMFACE_DATA_W : natural; DST_RAMFACE_DATA_W : natural) return natural is
  begin
    if SRC_RAMFACE_DATA_W = DST_RAMFACE_DATA_W then
      return 0;
    end if;
    report "Not yet implemented" severity FAILURE;
  end function;

end package body;

-------------------------------------------------------------------------------

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;
use work.ramface_pkg.all;
use work.skmap_pkg.all;

use work.ramface_rqst_w_adapt_ipkg;

entity ramface_rqst_w_adapt is
  generic (
    SRC_RAMFACE_ADDR_W  : natural;
    SRC_RAMFACE_DATA_W  : natural;
    SRC_RAMFACE_WREN_W  : natural := SRC_RAMFACE_DATA_W/8;

    DST_RAMFACE_DATA_W  : natural;
    DST_RAMFACE_ADDR_W  : natural := SRC_RAMFACE_ADDR_W
      + ceil_log2(SRC_RAMFACE_DATA_W) - ceil_log2(DST_RAMFACE_DATA_W);
    DST_RAMFACE_WREN_W  : natural := SRC_RAMFACE_DATA_W/8;

    LATENCY : natural := ramface_rqst_w_adapt_ipkg.get_LATENCY(
      SRC_RAMFACE_DATA_W => SRC_RAMFACE_DATA_W,
      DST_RAMFACE_DATA_W => DST_RAMFACE_DATA_W
    );
    META_W : natural := 0
  );
  port (
    clk_i : in  std_ulogic;

    ramface_ce_i : in std_ulogic := '1';

    src_ramface_rqst_i : in ramface_rqst_t(
      addr(SRC_RAMFACE_ADDR_W-1 downto 0),
      wren(SRC_RAMFACE_WREN_W-1 downto 0),
      data(SRC_RAMFACE_DATA_W-1 downto 0)
    );
    src_meta_i : in std_ulogic_vector(META_W-1 downto 0) := (others => '0');

    dst_ramface_rqst_o : out ramface_rqst_t(
      addr(DST_RAMFACE_ADDR_W-1 downto 0),
      wren(DST_RAMFACE_WREN_W-1 downto 0),
      data(DST_RAMFACE_DATA_W-1 downto 0)
    );
    dst_meta_o : out std_ulogic_vector(META_W-1 downto 0)
  );
end entity;

architecture rtl of ramface_rqst_w_adapt is

begin

  g_arch : if SRC_RAMFACE_DATA_W = DST_RAMFACE_DATA_W generate
    dst_ramface_rqst_o <= src_ramface_rqst_i;
    assert LATENCY = 0 report "TODO" severity FAILURE;
  else generate
    assert FALSE report "TODO" severity FAILURE;
  end generate;

  i_delay_fixed : entity work.delay_fixed
  generic map (
    DELAY      => LATENCY,
    DATA_W     => META_W
  ) port map (
    clk_i      => clk_i,
    ce_i       => ramface_ce_i,
    src_data_i => src_meta_i,
    dst_data_o => dst_meta_o
  );

end architecture;
