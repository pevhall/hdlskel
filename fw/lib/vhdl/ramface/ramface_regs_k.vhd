use work.ramface_rqst_local_decode_ipkg;
package ramface_regs_k_ipkg is
  constant LATENCY : natural := 1 + ramface_rqst_local_decode_ipkg.LATENCY;
end package;
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;
use work.vec_pkg.all;

use work.ramface_pkg.all;

use work.ramface_regs_k_ipkg;

entity ramface_regs_k is
  generic (
    BASE_ADDR      : natural;
    RAMFACE_ADDR_W : natural;
    RAMFACE_DATA_W : natural;
    RAMFACE_WREN_W : natural := RAMFACE_DATA_W/8;

    REGS_DATA_W : natural;
    REGS_K_INT  : integer_vector;
    LATENCY     : natural := ramface_regs_k_ipkg.LATENCY
  );
  port (
    clk_i : in  std_ulogic;

    ramface_ce_i : in std_ulogic := '1';
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

architecture rtl of ramface_regs_k is
  -- constant ADDR_START : natural := get_ramface_addr_start(BASE_ADDR, RAMFACE_DATA_W);
  constant REGS_LEN : natural := REGS_K_INT'length; 
  constant LOCAL_RAMFACE_DEPTH : natural := get_ramface_local_depth(REGS_LEN, REGS_DATA_W, RAMFACE_DATA_W);

  function get_ROM return vec_slv_t is
    variable result : vec_slv_t(0 to LOCAL_RAMFACE_DEPTH-1)(RAMFACE_DATA_W-1 downto 0) := (others => (others => '0') );

    constant REG_PER_RAMFACE : natural := RAMFACE_DATA_W/REGS_DATA_W;
    variable idx_reg : natural := 0;
    variable reg_data : std_ulogic_vector(REGS_DATA_W-1 downto 0);
  begin
    assert REGS_DATA_W <= RAMFACE_DATA_W
    report "Not yet implemented"
    severity FAILURE;

    for ii in 0 to LOCAL_RAMFACE_DEPTH-1 loop
      for JJ in 0 to REG_PER_RAMFACE-1 loop
        if idx_reg < REGS_LEN then
          reg_data := to_slv(REGS_K_INT(idx_reg), REGS_DATA_W);
          inc(idx_reg);
        else
          reg_data := (others => '0');
        end if;
        to_flat_vec(result(ii), jj, reg_data);
      end loop;
    end loop;

    return result;
  end function;

  constant ROM : vec_slv_t := get_ROM;

  constant LOCAL_RAMFACE_ADDR_W : natural := ceil_log2(LOCAL_RAMFACE_DEPTH);
  signal local_ramface_rqst : ramface_rqst_t(
    addr(LOCAL_RAMFACE_ADDR_W-1 downto 0),
    wren(RAMFACE_WREN_W-1 downto 0),
    data(RAMFACE_DATA_W-1 downto 0)
  );
  signal local_ramface_rqst_en_rd : std_ulogic;
  signal ramface_rply : ramface_rply_t(
    data(RAMFACE_DATA_W-1 downto 0)
  ) := (
    en   => '0',
    fail => '0',
    data => (others => '0')
  );

begin

  assert ramface_regs_k_ipkg.LATENCY = LATENCY
  report "Not yet implemented"
  severity FAILURE;

  i_ramface_rqst_decode : entity work.ramface_rqst_local_decode
  generic map (
    BASE_ADDR          => BASE_ADDR,
    RAMFACE_ADDR_W     => RAMFACE_ADDR_W,
    RAMFACE_DATA_W     => RAMFACE_DATA_W,
    RAMFACE_WREN_W     => RAMFACE_WREN_W,
    LOCAL_RAMFACE_DEPTH  => LOCAL_RAMFACE_DEPTH,
    LOCAL_RAMFACE_ADDR_W => LOCAL_RAMFACE_ADDR_W
  )
  port map (
    clk_i              => clk_i,
    ramface_ce_i       => ramface_ce_i,
    ramface_rqst_i => ramface_rqst_i,
    local_ramface_rqst_o => local_ramface_rqst,
    local_ramface_rqst_en_rd_o => local_ramface_rqst_en_rd
  );

  process(clk_i)
  begin
    if rising_edge(clk_i) then
      if ramface_ce_i = '1' then
        ramface_rply.en <= local_ramface_rqst_en_rd;
        ramface_rply.fail <= '0';
        if local_ramface_rqst_en_rd = '1' then
          ramface_rply.data <= ROM(to_integer(local_ramface_rqst.addr));
        end if;
      end if;
    end if;
  end process;
  ramface_rply_o <= ramface_rply;

end architecture;
