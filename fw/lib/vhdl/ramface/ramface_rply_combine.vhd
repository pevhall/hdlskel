use work.mux_1hot_ipkg;
use work.reduce_bitwise_tree_ipkg;

package ramface_rply_combine_ipkg is
  function get_latency(
    WRKR_LEN : natural;
    LUT_W  : natural := reduce_bitwise_tree_ipkg.DEV_LUT_INPUTS_OPTIMAL
  ) return natural;
end package;

package body ramface_rply_combine_ipkg is

  function get_latency( 
    WRKR_LEN : natural;
    LUT_W  : natural := reduce_bitwise_tree_ipkg.DEV_LUT_INPUTS_OPTIMAL
  ) return natural is
  begin
    return mux_1hot_ipkg.get_latency(SRC_LEN=>WRKR_LEN, LUT_W=>LUT_W);
  end function;

end package body;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.vec_pkg.all;
use work.ramface_pkg.all;

entity ramface_rply_combine is
  generic (
    RAMFACE_DATA_W : natural;
    WRKR_LEN : natural;
    LATENCY : natural := 1
  );
  port (
    clk_i : in  std_ulogic;
    ce_i : in std_ulogic := '1';
    wrkr_rply_i : in  vec_ramface_rply_t(0 to WRKR_LEN-1)(
      data(RAMFACE_DATA_W-1 downto 0)
    );
    mstr_rply_o : out ramface_rply_t(
      data(RAMFACE_DATA_W -1 downto 0)
    )
  );
end entity;

architecture rtl of ramface_rply_combine is

  constant FLAT_W : natural := get_flat_w(mstr_rply_o);
  signal wrkr_rply_vec_flat : vec_slv_t(0 to WRKR_LEN-1)(FLAT_W-1 downto 0);
  signal wrkr_rply_vec_en : std_ulogic_vector(WRKR_LEN-1 downto 0);

  signal mstr_rply_flat_multi_drive : std_ulogic;
  signal mstr_rply_flat : std_ulogic_vector(FLAT_W-1 downto 0);
begin

  process(all)
  begin
    for idx in 0 to WRKR_LEN-1 loop
      wrkr_rply_vec_en(idx) <= wrkr_rply_i(idx).en;
    end loop;
  end process;

  wrkr_rply_vec_flat <= to_vec_flat(wrkr_rply_i);

  i_mux : entity work.mux_1hot
  generic map (
    DATA_W          => FLAT_W,
    SRC_LEN         => WRKR_LEN,
    LATENCY         => LATENCY
  )
  port map (
    clk_i           => clk_i,
    ce_i            => ce_i,
    src_sel_1hot_i  => wrkr_rply_vec_en,
    src_vec_data_i  => wrkr_rply_vec_flat,
    dst_sel_error_o => mstr_rply_flat_multi_drive,
    dst_data_o      => mstr_rply_flat
  );

  process(all)
    variable mstr_rply_v : ramface_rply_t(data(RAMFACE_DATA_W-1 downto 0));
  begin
    mstr_rply_v := to_ramface_rply(mstr_rply_flat);
    mstr_rply_v.fail := mstr_rply_v.fail or mstr_rply_flat_multi_drive;
    mstr_rply_o <= mstr_rply_v;
  end process;


end architecture;
