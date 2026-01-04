use work.ramface_rqst_local_decode_ipkg;
package ramface_regs_rw_ipkg is
  constant LATENCY : natural := 1 + ramface_rqst_local_decode_ipkg.LATENCY;
end package;
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;
use work.vec_pkg.all;

use work.ramface_pkg.all;

use work.ramface_regs_rw_ipkg;

entity ramface_regs_rw is
  generic (
    BASE_ADDR      : natural;
    RAMFACE_ADDR_W : natural;
    RAMFACE_DATA_W : natural;
    RAMFACE_WREN_W : natural := RAMFACE_DATA_W/8;

    REGS_LEN    : natural;
    REGS_DATA_W : natural;
    LATENCY     : natural := ramface_regs_rw_ipkg.LATENCY
  );
  port (
    clk_i : in  std_ulogic;

    ramface_ce_i : in std_ulogic := '1';
    ramface_rqst_i : in ramface_rqst_t(
      addr(RAMFACE_ADDR_W-1 downto 0),
      wren(RAMFACE_WREN_W-1 downto 0),
      data(RAMFACE_DATA_W-1 downto 0)
    );
    ramface_rply_o : out ramface_rply_t (
      data( RAMFACE_DATA_W -1 downto 0)
    );

    regs_wr_wren_o : out vec_slv_t(0 to REGS_LEN-1)(REGS_DATA_W*RAMFACE_WREN_W/RAMFACE_DATA_W-1 downto 0);
    regs_wr_data_o : out vec_slv_t(0 to REGS_LEN-1)(REGS_DATA_W-1 downto 0);
    regs_rd_data_i : in  vec_slv_t(0 to REGS_LEN-1)(REGS_DATA_W-1 downto 0)
  );
end entity;

architecture rtl of ramface_regs_rw is

  constant WORD_W : natural := RAMFACE_DATA_W / RAMFACE_WREN_W;
  constant REGS_WREN_W : natural := REGS_DATA_W / WORD_W;
  constant LOCAL_RAMFACE_DEPTH : natural := get_ramface_local_depth(REGS_LEN, REGS_DATA_W, RAMFACE_DATA_W);
  constant REGS_PAD_LEN : natural := get_ramface_ram_pad(REGS_LEN, REGS_DATA_W, RAMFACE_DATA_W);

  signal regs_wren :  vec_slv_t(0 to REGS_LEN-1)(REGS_WREN_W-1 downto 0);
  signal regs_wr_data :  vec_slv_t(0 to REGS_LEN-1)(REGS_DATA_W-1 downto 0);

  constant LOCAL_RAMFACE_ADDR_W : natural := ceil_log2(LOCAL_RAMFACE_DEPTH);
  signal local_ramface_rqst : ramface_rqst_t(
    addr(LOCAL_RAMFACE_ADDR_W-1 downto 0),
    wren(RAMFACE_WREN_W-1 downto 0),
    data(RAMFACE_DATA_W-1 downto 0)
  );
  signal local_ramface_rqst_en_wr : std_ulogic;
  signal local_ramface_rqst_en_rd : std_ulogic;
  signal ramface_rply : ramface_rply_t(
    data(RAMFACE_DATA_W-1 downto 0)
  ) := (
    en   => '0',
    fail => '0',
    data => (others => '0')
  );

  signal regs_pad : vec_slv_t(0 to REGS_PAD_LEN-1)(REGS_DATA_W-1 downto 0) := (others => (others => '0'));
  signal regs_ramface_rd_data : vec_slv_t(0 to LOCAL_RAMFACE_DEPTH-1)(RAMFACE_DATA_W-1 downto 0);
  signal regs_ramface_wr_data : vec_slv_t(0 to LOCAL_RAMFACE_DEPTH-1)(RAMFACE_DATA_W-1 downto 0) := (others => (others => '0'));
  signal regs_ramface_wr_wren : vec_slv_t(0 to LOCAL_RAMFACE_DEPTH-1)(RAMFACE_WREN_W-1 downto 0) := (others => (others => '0'));

begin

  assert REGS_DATA_W <= RAMFACE_DATA_W
  report "Not yet implemented"
  severity FAILURE;

  assert ramface_regs_rw_ipkg.LATENCY = LATENCY
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
    clk_i                => clk_i,
    ramface_ce_i         => ramface_ce_i,
    ramface_rqst_i       => ramface_rqst_i,
    local_ramface_rqst_o => local_ramface_rqst,
    local_ramface_rqst_en_wr_o => local_ramface_rqst_en_wr,
    local_ramface_rqst_en_rd_o => local_ramface_rqst_en_rd
  );

  process(clk_i)
    variable addr_v : natural;
  begin
    if rising_edge(clk_i) then
      if ramface_ce_i = '1' then
        ramface_rply.en <= '0';
        addr_v := to_integer(local_ramface_rqst.addr);
        if local_ramface_rqst_en_rd = '1' then
          ramface_rply.en <= '1';
          ramface_rply.data <= regs_ramface_rd_data(addr_v);
        end if;

        regs_ramface_wr_wren <= (others => (others => '0'));
        if local_ramface_rqst_en_wr = '1' then
          regs_ramface_wr_wren(addr_v) <= local_ramface_rqst.wren;
          regs_ramface_wr_data(addr_v) <= local_ramface_rqst.data;
        end if;

      end if;
    end if;
  end process;
  ramface_rply_o <= ramface_rply;


  regs_ramface_rd_data <= to_vec_slv(to_flat(regs_rd_data_i & regs_pad), RAMFACE_DATA_W);
  regs_wr_data_o <= to_vec_slv(to_flat(regs_ramface_wr_data), REGS_DATA_W)(0 to REGS_LEN-1);
  regs_wr_wren_o <= to_vec_slv(to_flat(regs_ramface_wr_wren), REGS_WREN_W)(0 to REGS_LEN-1);

end architecture;
