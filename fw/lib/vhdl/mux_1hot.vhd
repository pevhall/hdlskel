use work.basic_pkg.all;
use work.reduce_bitwise_tree_ipkg;

package mux_1hot_ipkg is
  
  function get_latency(
    SRC_LEN : natural;
    LUT_W  : natural := reduce_bitwise_tree_ipkg.DEV_LUT_INPUTS_OPTIMAL
  ) return natural;

  function get_latency_or_reduce(
    SRC_LEN : natural;
    LUT_W  : natural := reduce_bitwise_tree_ipkg.DEV_LUT_INPUTS_OPTIMAL
  ) return natural;

end package;

package body mux_1hot_ipkg is

  function get_latency( 
    SRC_LEN : natural;
    LUT_W  : natural := reduce_bitwise_tree_ipkg.DEV_LUT_INPUTS_OPTIMAL
  ) return natural is
  begin
    if SRC_LEN = 1 then
      return 0;
    end if;
    if SRC_LEN <= 4 then
      return 1;
    end if;
    return get_latency_or_reduce(SRC_LEN=>SRC_LEN, LUT_W=>LUT_W);
  end function;

  function get_latency_or_reduce( 
    SRC_LEN : natural;
    LUT_W  : natural := reduce_bitwise_tree_ipkg.DEV_LUT_INPUTS_OPTIMAL
  ) return natural is
  begin
    return reduce_bitwise_tree_ipkg.get_latency(SRC_LEN=>SRC_LEN, LUT_W=>LUT_W) + 1;
  end function;

end package body;


library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;
use work.vec_pkg.all;

use work.ramface_pkg.all;

use work.mux_1hot_ipkg;
use work.reduce_bitwise_tree_ipkg.reduce_bitwise_tree_op_t;

entity mux_1hot is
  generic (
    DATA_W : natural;
    SRC_LEN : natural;
    LATENCY : natural := mux_1hot_ipkg.get_latency(SRC_LEN => SRC_LEN)
  );
  port (
    clk_i : in  std_logic;
    ce_i  : in  std_logic := '1';

    src_sel_1hot_i : in std_logic_vector(SRC_LEN-1 downto 0);
    src_vec_data_i : in vec_slv_t(0 to SRC_LEN-1)(DATA_W-1 downto 0);
    dst_sel_error_o : out std_logic;
    dst_sel_or_reduce_o  : out std_logic;
    dst_data_o : out std_logic_vector(DATA_W-1 downto 0)
  );
end entity;

architecture rtl of mux_1hot is

begin

  g_arch : if SRC_LEN = 1 and LATENCY = 0 generate
    dst_data_o <= src_vec_data_i(0);
    dst_sel_or_reduce_o <= src_sel_1hot_i(0);
    dst_sel_error_o <= '0';
  elsif LATENCY = 1 generate
    signal dst_sel_error : std_logic := '0';
    signal dst_sel_or_reduce : std_logic := '0';
    signal dst_data : std_logic_vector(DATA_W-1 downto 0) := (others => '0');
  begin
    process(clk_i)
      variable got_sel : std_logic;
    begin
      if rising_edge(clk_i) then
        if ce_i = '1' then
          dst_sel_or_reduce <= or src_sel_1hot_i;

          dst_sel_error <= '0';
          dst_data <= (others => '0' );
          got_sel := '0';
          for ii in 0 to SRC_LEN-1 loop
            if src_sel_1hot_i(ii) = '1' then
              dst_sel_error <= got_sel;
              got_sel := '1';
              dst_data <= src_vec_data_i(ii);
            end if;
          end loop;
        end if;
      end if;
    end process;
    dst_sel_error_o <= dst_sel_error;
    dst_sel_or_reduce_o <= dst_sel_or_reduce;
    dst_data_o <= dst_data;

  else generate
    signal zeromask_data : vec_slv_t(0 to SRC_LEN-1)(DATA_W-1 downto 0) := ( others => ( others => '0') );
    signal zeromask_sel_1hot : std_logic_vector(SRC_LEN-1 downto 0) := (others => '0');
    signal zeromask_sel_1hot_vec : vec_slv_t(0 to SRC_LEN-1)(0 downto 0);

    constant SUM_EN_W : natural := ceil_log2(SRC_LEN);
    signal zeromask_sel_1hot_ext : vec_unsigned_t(0 to SRC_LEN-1)(SUM_EN_W-1 downto 0);
    signal dst_sel_sum : unsigned(SUM_EN_W-1 downto 0);
  begin

    process(clk_i)
    begin
      if rising_edge(clk_i) then
        if ce_i = '1' then
          zeromask_sel_1hot <= src_sel_1hot_i;
          for idx in 0 to SRC_LEN-1 loop
            if src_sel_1hot_i(idx) = '1' then
              zeromask_data(idx) <= src_vec_data_i(idx);
            else
              zeromask_data(idx) <= (others => '0');
            end if;
          end loop;
        end if;
      end if;
    end process;

    i_reduce_tree_data : entity work.reduce_bitwise_tree
    generic map (
      OP             => op_or,
      DATA_W         => DATA_W,
      SRC_LEN        => SRC_LEN,
      LATENCY        => LATENCY-1
    )
    port map (
      clk_i          => clk_i,
      ce_i           => ce_i,
      src_vec_data_i => zeromask_data,
      dst_data_o     => dst_data_o
    );

    zeromask_sel_1hot_vec <= transpose(to_vec_slv(zeromask_sel_1hot));
    i_reduce_tree_sel : entity work.reduce_bitwise_tree
    generic map (
      OP             => op_or,
      DATA_W         => 1,
      SRC_LEN        => SRC_LEN,
      LATENCY        => LATENCY-1
    )
    port map (
      clk_i          => clk_i,
      ce_i           => ce_i,
      src_vec_data_i => zeromask_sel_1hot_vec,
      dst_data_o(0)  => dst_sel_or_reduce_o
    );

    zeromask_sel_1hot_ext <= resize(to_vec_unsigned(zeromask_sel_1hot_vec), SUM_EN_W);
    i_adder_tree : entity work.adder_tree
    generic map (
      NUM_W         => SUM_EN_W,
      SRC_LEN       => SRC_LEN,
      LATENCY       => LATENCY-1
    )
    port map (
      clk_i         => clk_i,
      ce_i          => ce_i,
      src_vec_num_i => zeromask_sel_1hot_ext,
      dst_num_o     => dst_sel_sum
    );
    dst_sel_error_o <= to_sl(dst_sel_sum > 1);

  end generate;



end architecture;
