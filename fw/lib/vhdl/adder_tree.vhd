use work.basic_pkg.all;

package adder_tree_ipkg is
  function get_latency(SRC_LEN : natural) return natural;
end package;

package body adder_tree_ipkg is

  function get_latency(SRC_LEN : natural) return natural is
  begin
    return ceil_log2(SRC_LEN);
  end function;

end package body;

--------------------------------------------------------------------------------

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;
use work.vec_pkg.all;

use work.adder_tree_ipkg;

entity adder_tree is
  generic (
    NUM_W   : natural;
    SRC_LEN : natural;
    LATENCY : natural := adder_tree_ipkg.get_latency(SRC_LEN => SRC_LEN)
  );
  port (
    clk_i : std_ulogic;
    ce_i  : std_ulogic := '1';

    src_vec_num_i : in  vec_unsigned_t(0 to SRC_LEN-1)(NUM_W-1 downto 0);
    dst_num_o     : out u_unsigned(NUM_W-1 downto 0)
  );
end entity;

architecture rtl of adder_tree is

begin

  assert SRC_LEN = 1 or LATENCY > 0
  severity FAILURE;

  g_impl : if SRC_LEN = 1 generate

    dst_num_o <= src_vec_num_i(0);

  else generate

    constant OPS_PER_STEP : natural := ceil_log_base(SRC_LEN, LATENCY);
    constant EX_LEN       : natural := OPS_PER_STEP * LATENCY;

    signal z_vec_num : vec2_unsigned_t(0 to LATENCY)(0 to EX_LEN-1)(NUM_W-1 downto 0) := (others => (others => (others => '0')));

    alias z_vec_num_0   is z_vec_num(0);
    alias z_vec_num_reg is z_vec_num(1 to LATENCY);

    function reduce_step (data_vec : vec_unsigned_t) return vec_unsigned_t is
      constant RESULT_LEN : natural := ceil_div(data_vec'length, OPS_PER_STEP);
      variable result : vec_unsigned_t(0 to RESULT_LEN-1)(NUM_W-1 downto 0);
      variable v : vec_unsigned_t(0 to OPS_PER_STEP-1)(NUM_W-1 downto 0);
    begin
      for ii in 0 to RESULT_LEN-1 loop
        v := data_vec(OPS_PER_STEP*ii to OPS_PER_STEP*(ii+1)-1);
        result(ii) := + v;
      end loop;
      return result;
    end function;

begin

    z_vec_num_0(0 to SRC_LEN-1) <= src_vec_num_i;

    process(clk_i)
      variable l : natural;
      variable pl : natural;
    begin
      if rising_edge(clk_i) then
        if ce_i = '1' then
          pl := EX_LEN;
          for idx in 0 to LATENCY-1 loop
            l := maximum(1, pl/OPS_PER_STEP);
            z_vec_num_reg(idx+1)(0 to l-1) <= reduce_step(z_vec_num(idx)(0 to pl-1));
            pl := l;
          end loop;
        end if;
      end if;
    end process;
  dst_num_o <= z_vec_num_reg(LATENCY)(0);

  end generate;

end architecture;
