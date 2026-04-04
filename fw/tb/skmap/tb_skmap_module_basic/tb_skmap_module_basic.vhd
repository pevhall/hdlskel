library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;
use work.vec_pkg.all;

use work.ramface_pkg.all;
use work.ramface_sim_pkg.all;
use work.skmap_pkg.all;

use work.ramface_regs_rw_ipkg;
use work.skmap_module_ipkg;

entity tb_skmap_module_basic is
  generic(
    -- RAMFACE_DATA_W : natural := 64
    RAMFACE_DATA_W : natural := 32 --TODO try 64, 128
  );
end entity;

architecture sim of tb_skmap_module_basic is

 constant SKMAP_ID : string := "TestBsic";
 constant SKMAP_VER_MAJOR : skmap_ver_major_t := 1;
 constant SKMAP_VER_MINOR : skmap_ver_minor_t := 0;
 constant SKMAP_KIDS : integer_vector := VOID_INTEGER_VECTOR;
 constant SKMAP_LEN_VAR : skmap_len_var_t := 0;

 constant BASE_ADDR       : natural := 16#1000#;
 constant RAMFACE_ADDR_W  : natural := 16;
 constant RAMFACE_WREN_W  : natural := RAMFACE_DATA_W/8;
 constant RAMFACE_LATENCY : natural := skmap_module_ipkg.RAMFACE_LATENCY;

 constant  REGS_K_INT      : integer_vector := (16#C01#, 16#C02#, 16#C03#);
 constant  REGS_VAR_LEN    : natural := 3;


  signal ramface_ce : std_logic := '1';
  signal ramface_ctrl : ramface_sim_ctrl_t(rqst(
      addr(RAMFACE_ADDR_W-1 downto 0),
      data(RAMFACE_DATA_W-1 downto 0),
      wren(RAMFACE_WREN_W-1 downto 0)
    )) := init_ramface_sim_ctrl(
      latency => RAMFACE_LATENCY, 
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
  signal regs_var_wr_wren : vec_slv4_t (0 to REGS_VAR_LEN-1);
  signal regs_var_wr_data : vec_slv32_t(0 to REGS_VAR_LEN-1);
  signal regs_var_rd_data : vec_slv32_t(0 to REGS_VAR_LEN-1);

begin

  p_ctrl : process
    constant BASE_ADDR_REGS_K   : natural := BASE_ADDR + SKMAP_HEAD_LEN;
    constant BASE_ADDR_REGS_VAR : natural := BASE_ADDR_REGS_K + REGS_K_INT'length;
    constant RW_DATA_INT : integer_vector := get_vec_int_range(REGS_VAR_LEN) + 256;
    constant RW_DATA_SLV : std_logic_vector := to_flat(to_vec_unsigned(RW_DATA_INT, 32));
    constant K_DATA_SLV  : std_ulogic_vector := to_flat(to_vec_unsigned(REGS_K_INT, 32));
    variable rd_data_head_v : std_ulogic_vector(SKMAP_HEAD_W-1 downto 0);
    variable rd_data_k_v : std_logic_vector(RW_DATA_SLV'length-1 downto 0);
    variable rd_data_var_v : std_logic_vector(REGS_VAR_LEN*32-1 downto 0);
    variable rd_checks_passed_v : integer := 0;
  begin
    cyc(ramface_ctrl);
    ramface_sim_rqst_rd(ramface_ctrl, ramface_rply, BASE_ADDR, rd_data_head_v);
    ramface_sim_rqst_rd(ramface_ctrl, ramface_rply, BASE_ADDR_REGS_K, rd_data_k_v);
    if rd_data_k_v = K_DATA_SLV then
      inc(rd_checks_passed_v);
    else
      report "K data error" severity ERROR;
    end if;
    ramface_sim_rqst_wr(ramface_ctrl, BASE_ADDR_REGS_VAR, RW_DATA_SLV);
    ramface_sim_rqst_rd(ramface_ctrl, ramface_rply, BASE_ADDR_REGS_VAR, rd_data_var_v);
    if rd_data_var_v = rw_data_slv then
      inc(rd_checks_passed_v);
    else
      report "RW data error" severity ERROR;
    end if;
    assert rd_data_var_v = RW_DATA_SLV severity ERROR;

    assert rd_checks_passed_v mod 10 /= 0
    report "passed "&integer'image(rd_checks_passed_v)&" checks"
    severity NOTE;

    for idx in 0 to 10 loop
      cyc(ramface_ctrl);
    end loop;
  end process;



  i_skmap_module : entity work.skmap_module
  generic map (
    SKMAP_ID           => SKMAP_ID,
    SKMAP_VER_MAJOR    => SKMAP_VER_MAJOR,
    SKMAP_VER_MINOR    => SKMAP_VER_MINOR,
    SKMAP_KIDS         => SKMAP_KIDS,
    SKMAP_LEN_VAR      => SKMAP_LEN_VAR,
    BASE_ADDR          => BASE_ADDR,
    RAMFACE_ADDR_W     => RAMFACE_ADDR_W,
    RAMFACE_DATA_W     => RAMFACE_DATA_W,
    RAMFACE_WREN_W     => RAMFACE_WREN_W,
    RAMFACE_LATENCY    => RAMFACE_LATENCY,
    REGS_K_INT         => REGS_K_INT,
    REGS_VAR_LEN       => REGS_VAR_LEN
  )
  port map (
    clk_i              => clk,
    ramface_ce_i       => ramface_ce,
    ramface_rqst_i     => ramface_rqst,
    ramface_rply_o     => ramface_rply,
    regs_var_wr_wren_o => regs_var_wr_wren,
    regs_var_wr_data_o => regs_var_wr_data,
    regs_var_rd_data_i => regs_var_rd_data
  );

  regs_var_rd_data <= regs_var_wr_data;


end architecture;
