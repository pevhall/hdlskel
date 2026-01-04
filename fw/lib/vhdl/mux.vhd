use work.basic_pkg.all;

package mux_ipkg is
  function get_latency(
    TOTAL_SRC : natural;
    USE_1HOT  : boolean := FALSE
) return natural;
end package;

package body mux_ipkg is
  constant MUX_W_OPTIMAL       : natural := 4;
  constant OR_REDUCE_W_OPTIMAL : natural := 6;

  function get_latency( 
    TOTAL_SRC : natural;
    USE_1HOT  : boolean := FALSE
  ) return natural is
  begin
    if TOTAL_SRC = 1 then
      return 1;
    end if;
    if TOTAL_SRC <= MUX_W_OPTIMAL and not USE_1HOT then
      return 1;
    end if;
      return ceil_log_base(TOTAL_SRC, OR_REDUCE_W_OPTIMAL);
    assert FALSE
    report "not yet implemented"
    severity FAILURE;
  end function;

end package body;


library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;
use work.vec_pkg.all;

use work.mux_ipkg;

entity mux is
  generic (
    DATA_W : natural;
    TOTAL_SRC : natural;
    LATENCY : natural := mux_ipkg.get_latency(TOTAL_SRC => TOTAL_SRC);
    USE_1HOT : boolean := FALSE
  );
  port (
    clk_i : in  std_logic;
    ce_i  : in  std_logic := '1';

    src_sel_i : in unsigned(ceil_log2(TOTAL_SRC)-1 downto 0);
    src_vec_data_i : in vec_slv_t(0 to TOTAL_SRC-1)(DATA_W-1 downto 0);
    dst_data_o : out std_logic_vector(DATA_W-1 downto 0)
  );
end entity;

architecture rtl of mux is

  constant SEL_W : natural := ceil_log2(TOTAL_SRC);

begin

  g_arch : if LATENCY <= 1 generate
    signal dst_data : std_logic_vector(DATA_W-1 downto 0) := (others => '0');
    signal dst_sel  : unsigned         (SEL_W-1 downto 0) := (others => '0');
  begin
    process(clk_i)
    begin
      if rising_edge(clk_i) then
        if ce_i = '1' then
          dst_data <= src_vec_data_i(to_integer(src_sel_i));
        end if;
      end if;
    end process;
    dst_data_o <= dst_data;

  else generate
    assert FALSE
    report "not yet implemented"
    severity FAILURE;
  end generate;

end architecture;
