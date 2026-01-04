library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;
use work.vec_pkg.all;

use work.ramface_pkg.all;
use work.ramface_sim_pkg.all;

use work.ramface_regs_rw_ipkg;

entity tb_ramface_regs is
  generic(
    RAMFACE_DATA_W : natural := 64
  );
end entity;

architecture sim of tb_ramface_regs is
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
  signal ramface_ctrl : ramface_sim_ctrl_t(rqst(
      addr(RAMFACE_ADDR_W-1 downto 0),
      data(RAMFACE_DATA_W-1 downto 0),
      wren(RAMFACE_WREN_W-1 downto 0)
    )) := init_ramface_sim_ctrl(
      latency => LATENCY, 
      ADDR_W => RAMFACE_ADDR_W,
      DATA_W => RAMFACE_DATA_W, 
      WREN_W => RAMFACE_WREN_W
    );
  alias clk is ramface_ctrl.clk;
  alias ramface_rqst is ramface_ctrl.rqst;
  -- signal ramface_rqst : ramface_rqst_t(
  --   addr(RAMFACE_ADDR_W-1 downto 0),
  --   wren(RAMFACE_WREN_W-1 downto 0),
  --   data(RAMFACE_DATA_W-1 downto 0)
  -- );
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

  p_ctrl : process
    constant RW_DATA_INT : integer_vector := get_vec_int_range(REGS_RW_LEN) + 256;
    constant RW_DATA_SLV : std_logic_vector := to_flat(to_vec_unsigned(RW_DATA_INT, REGS_DATA_W));
    constant K_DATA_SLV  : std_ulogic_vector := to_flat(to_vec_unsigned(REGS_K_INT, REGS_DATA_W));
    variable rd_data_k_v : std_logic_vector(REGS_K_LEN*REGS_DATA_W-1 downto 0);
    variable rd_data_rw_v : std_logic_vector(REGS_RW_LEN*REGS_DATA_W-1 downto 0);
    variable rd_checks_passed_v : integer := 0;
  begin
    cyc(ramface_ctrl);
    ramface_sim_rqst_rd(ramface_ctrl, ramface_rply, BASE_ADDR_REGS_K, rd_data_k_v);
    if rd_data_k_v = K_DATA_SLV then
      inc(rd_checks_passed_v);
    else
      report "K data error" severity ERROR;
    end if;
    ramface_sim_rqst_wr(ramface_ctrl, BASE_ADDR_REGS_RW, RW_DATA_SLV);
    ramface_sim_rqst_rd(ramface_ctrl, ramface_rply, BASE_ADDR_REGS_RW, rd_data_rw_v);
    if rd_data_rw_v = rw_data_slv then
      inc(rd_checks_passed_v);
    else
      report "RW data error" severity ERROR;
    end if;
    assert rd_data_rw_v = RW_DATA_SLV severity ERROR;

    assert rd_checks_passed_v mod 10 /= 0
    report "passed "&integer'image(rd_checks_passed_v)&" checks"
    severity NOTE;

    for idx in 0 to 10 loop
      cyc(ramface_ctrl);
    end loop;
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


  i_ramface_regs_rw : entity work.ramface_regs_rw
  generic map (
    BASE_ADDR      => BASE_ADDR_REGS_RW,
    RAMFACE_ADDR_W => RAMFACE_ADDR_W,
    RAMFACE_DATA_W => RAMFACE_DATA_W,
    RAMFACE_WREN_W => RAMFACE_WREN_W,
    REGS_DATA_W    => REGS_DATA_W,
    REGS_LEN       => REGS_RW_LEN,
    LATENCY        => REGS_LATENCY
  )
  port map (
    clk_i          => clk,
    ramface_ce_i   => ramface_ce,
    ramface_rqst_i => ramface_rqst,
    ramface_rply_o => ramface_rply_regs_rw,
    regs_wr_wren_o => regs_wr_wren,
    regs_wr_data_o => regs_wr_data,
    regs_rd_data_i => regs_rd_data
  );

  regs_rd_data <= regs_wr_data;

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
