use work.basic_pkg.all;

package reduce_bitwise_tree_ipkg is
  constant DEV_LUT_INPUTS_OPTIMAL : natural := 6;
  type reduce_bitwise_tree_op_t is (op_or, op_and, op_xor);
  function get_latency(
    SRC_LEN : natural; 
    LUT_W : natural := DEV_LUT_INPUTS_OPTIMAL
  ) return natural;
end package;

package body reduce_bitwise_tree_ipkg is
  function get_latency(
    SRC_LEN : natural;
    LUT_W : natural := DEV_LUT_INPUTS_OPTIMAL
  ) return natural is
  begin
    if SRC_LEN = 1 then
      return 0;
    end if;
    return ceil_log_base(SRC_LEN, LUT_W);
  end function;
end package body;

--------------------------------------------------------------------------------

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use ieee.math_real.all;

use work.basic_pkg.all;
use work.vec_pkg.all;

use work.reduce_bitwise_tree_ipkg;
use work.reduce_bitwise_tree_ipkg.reduce_bitwise_tree_op_t;

entity reduce_bitwise_tree is
  generic (
    OP : reduce_bitwise_tree_op_t;
    DATA_W  : natural;
    SRC_LEN : natural;
    LATENCY : natural := reduce_bitwise_tree_ipkg.get_latency(SRC_LEN=>SRC_LEN)
  );
  port (
    clk_i : in  std_logic;
    ce_i  : in std_logic := '1';

    src_vec_data_i : in vec_slv_t(0 to SRC_LEN-1)(DATA_W-1 downto 0);
    dst_data_o : out std_logic_vector(DATA_W-1 downto 0)
  );
end entity;

architecture rtl of reduce_bitwise_tree is

begin

  assert SRC_LEN = 1 or LATENCY > 0
  severity FAILURE;

  g_impl : if SRC_LEN = 1 generate

    dst_data_o <= src_vec_data_i(0);

  else generate

    constant FANIN  : natural := ceil_root(SRC_LEN, LATENCY);
    constant LEN   : natural := SRC_LEN;
    -- S ** (1/L)

    -- function ignore return std_ulogic is
    -- begin
    --   report "SRC_LEN = "&integer'image(SRC_LEN);
    --   report "LATENCY = "&integer'image(LATENCY);
    --   report "FANIN = "&integer'image(FANIN);
    --   return '1';
    -- end function;
    -- constant IGN : std_ulogic := ignore;

    signal z_vec_data : vec2_slv_t(0 to LATENCY)(0 to LEN-1)(DATA_W-1 downto 0) := (others => (others => (others => '0')));
    alias z_vec_data_0   is z_vec_data(0);
    alias z_vec_data_reg is z_vec_data(1 to LATENCY);

    function reduce_op(v : std_logic_vector) return std_logic is
    begin
      case OP is 
        when op_and => return and v;
        when op_or  => return or  v;
        when op_xor => return xor v;
      end case;
    end function;

    function reduce_step (data_vec : vec_slv_t) return vec_slv_t is
      constant RESULT_LEN : natural := ceil_div(data_vec'length, FANIN);
      variable result : vec_slv_t(0 to RESULT_LEN-1)(DATA_W-1 downto 0);
      variable v : std_logic_vector(FANIN-1 downto 0);
      variable v_idx_len : natural;
    begin
      for r_idx in 0 to RESULT_LEN-1 loop
        for d_idx in 0 to DATA_W-1 loop
          v_idx_len := minimum(FANIN, data_vec'length-FANIN*r_idx);
          for v_idx in 0 to v_idx_len-1 loop
            v(v_idx) := data_vec(r_idx*FANIN+v_idx)(d_idx);
          end loop;
          result(r_idx)(d_idx) := reduce_op(v(v_idx_len-1 downto 0));
        end loop;
      end loop;
      return result;
    end function;

  begin

    process(all)
    begin
      z_vec_data_0(0 to SRC_LEN-1) <= src_vec_data_i;
      z_vec_data_0(SRC_LEN to LEN-1) <= (others => src_vec_data_i(SRC_LEN-1));
    end process;

    process(clk_i)
      variable l : natural;
      variable pl : natural;
    begin
      if rising_edge(clk_i) then
        if ce_i = '1' then
          pl := LEN;
          for idx in 0 to LATENCY-1 loop
            l := ceil_div(pl, FANIN);
            z_vec_data_reg(idx+1)(0 to l-1) <= reduce_step(z_vec_data(idx)(0 to pl-1));
            pl := l;
          end loop;
        end if;
      end if;
    end process;

    dst_data_o <= z_vec_data(LATENCY)(0);
  end generate;


end architecture;
