library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;
use work.vec_pkg.all;

use work.ramface_pkg.all;

use work.ramface_regs_rw_ipkg;

entity tb_ramface_regs_viv is
  generic(
    RAMFACE_DATA_W : natural := 64
  );
end entity;

architecture sim of tb_ramface_regs_viv is
  constant RAMFACE_ADDR_W : natural := 16;
  constant RAMFACE_WREN_W : natural := RAMFACE_DATA_W/8;
  constant REGS_DATA_W : natural := 32;
  constant REGS_RW_LEN : natural := 16#20#;
  constant REGS_LATENCY : natural := ramface_regs_rw_ipkg.LATENCY;
  constant RPLY_COMBINE_LATENCY : natural := 3;
  constant LATENCY : natural := REGS_LATENCY + rply_combine_latency;

  constant BASE_ADDR_REGS_K  : natural := 16#100#;
  constant REGS_K_LEN        : natural := 16#11#;
  constant REGS_K_INT            : integer_vector := get_vec_int_range(REGS_K_LEN)+1;
  constant RAMFACE_DEPTH_LOCAL_K : natural := get_ramface_local_depth(REGS_K_LEN, REGS_DATA_W, RAMFACE_DATA_W);
  constant BASE_ADDR_REGS_RW : natural := BASE_ADDR_REGS_K + RAMFACE_DEPTH_LOCAL_K;

  constant REGS_WREN_W : natural := REGS_DATA_W*RAMFACE_WREN_W/RAMFACE_DATA_W;

  signal ramface_ce : std_logic := '1';
  signal clk : std_logic := '1';
  signal ramface_rqst : ramface_rqst_t(
    addr(RAMFACE_ADDR_W-1 downto 0),
    data(RAMFACE_DATA_W-1 downto 0),
    wren(RAMFACE_WREN_W-1 downto 0)
  ) := init_ramface_rqst(RAMFACE_ADDR_W, RAMFACE_DATA_W, RAMFACE_WREN_W);
  signal ramface_rply : ramface_rply_t(
    data(RAMFACE_DATA_W -1 downto 0)
  );
  signal ramface_rply_regs_k : ramface_rply_t(
    data(RAMFACE_DATA_W -1 downto 0)
  );
  signal ramface_rply_regs_rw : ramface_rply_t(
    data(RAMFACE_DATA_W -1 downto 0)
  );
  signal regs_wr_wren : vec_slv_t(0 to REGS_RW_LEN-1)(REGS_WREN_W-1 downto 0);
  signal regs_wr_data : vec_slv_t(0 to REGS_RW_LEN-1)(REGS_DATA_W-1 downto 0);
  signal regs_rd_data : vec_slv_t(0 to REGS_RW_LEN-1)(REGS_DATA_W-1 downto 0);
  

begin

  clk <= not clk after 0.5 ns;

  process(clk)
    variable cyc_v : integer := 0;
    variable addr_v : unsigned(RAMFACE_ADDR_W-1 downto 0) := to_unsigned(BASE_ADDR_REGS_K, RAMFACE_ADDR_W);
  begin
    if rising_edge(clk) then
      if ramface_ce = '1' then

        if cyc_v < REGS_K_LEN then 
          ramface_rqst.en   <= '1';
          ramface_rqst.addr <= ramface_rqst.addr+cyc_v;
          ramface_rqst.wren <= (others => '0');
          ramface_rqst.data <= (others => '0');
        else
          ramface_rqst.en   <= '0';
          ramface_rqst.addr <= (others => '0');
          ramface_rqst.wren <= (others => '0');
          ramface_rqst.data <= (others => '0');
        end if;
        inc(cyc_v);
      end if;
    end if;
  end process;

  i_ramface_regs_k : entity work.ramface_regs_k
  generic map (
    BASE_ADDR      => BASE_ADDR_REGS_K,
    RAMFACE_ADDR_W => RAMFACE_ADDR_W,
    RAMFACE_DATA_W => RAMFACE_DATA_W,
    RAMFACE_WREN_W => RAMFACE_WREN_W,
    REGS_DATA_W    => REGS_DATA_W,
    REGS_K_INT     => REGS_K_INT,
    LATENCY        => REGS_LATENCY
  )
  port map (
    clk_i          => clk,
    ramface_ce_i   => ramface_ce,
    ramface_rqst_i => ramface_rqst,
    ramface_rply_o => ramface_rply_regs_k
  );
  --
  --
  -- i_ramface_regs_rw : entity work.ramface_regs_rw
  -- generic map (
  --   BASE_ADDR      => BASE_ADDR_REGS_RW,
  --   RAMFACE_ADDR_W => RAMFACE_ADDR_W,
  --   RAMFACE_DATA_W => RAMFACE_DATA_W,
  --   RAMFACE_WREN_W => RAMFACE_WREN_W,
  --   REGS_DATA_W    => REGS_DATA_W,
  --   REGS_LEN       => REGS_RW_LEN,
  --   LATENCY        => REGS_LATENCY
  -- )
  -- port map (
  --   clk_i          => clk,
  --   ramface_ce_i   => ramface_ce,
  --   ramface_rqst_i => ramface_rqst,
  --   ramface_rply_o => ramface_rply_regs_rw,
  --   regs_wr_wren_o => regs_wr_wren,
  --   regs_wr_data_o => regs_wr_data,
  --   regs_rd_data_i => regs_rd_data
  -- );
  --
  -- regs_rd_data <= regs_wr_data;

  i_ramface_rply_combine : entity work.ramface_rply_combine
  generic map (
    RAMFACE_DATA_W  => RAMFACE_DATA_W,
    WRKR_LEN    => 2,
    LATENCY     => RPLY_COMBINE_LATENCY
  )
  port map (
    clk_i          => clk,
    ce_i           => ramface_ce,
    wrkr_rply_i(0) => ramface_rply_regs_k,
    wrkr_rply_i(1) => ramface_rply_regs_rw,
    mstr_rply_o    => ramface_rply
  );

end architecture;
