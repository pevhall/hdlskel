package ramface_rply_w_adapt_ipkg is

  function get_LATENCY(SRC_RAMFACE_DATA_W : natural; DST_RAMFACE_DATA_W : natural) return natural;

end package;

package body ramface_rply_w_adapt_ipkg is

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

use work.ramface_rply_w_adapt_ipkg;

entity ramface_rply_w_adapt is
  generic (
    SRC_RAMFACE_DATA_W  : natural;
    DST_RAMFACE_DATA_W  : natural;

    LATENCY : natural := ramface_rply_w_adapt_ipkg.get_LATENCY(
      SRC_RAMFACE_DATA_W => SRC_RAMFACE_DATA_W,
      DST_RAMFACE_DATA_W => DST_RAMFACE_DATA_W
    );
    META_W : natural := 0
  );
  port (
    clk_i : in  std_ulogic;

    ramface_ce_i : in std_ulogic := '1';

    src_ramface_rply_i : in ramface_rply_t( data(SRC_RAMFACE_DATA_W-1 downto 0));
    src_meta_i : in std_ulogic_vector(META_W-1 downto 0) := (others => '0');

    dst_ramface_rply_o : out ramface_rply_t( data(DST_RAMFACE_DATA_W-1 downto 0));
    dst_meta_o : out std_ulogic_vector(META_W-1 downto 0)
  );
end entity;

architecture rtl of ramface_rply_w_adapt is

begin

  g_arch : if SRC_RAMFACE_DATA_W = DST_RAMFACE_DATA_W generate
    dst_ramface_rply_o <= src_ramface_rply_i;
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
