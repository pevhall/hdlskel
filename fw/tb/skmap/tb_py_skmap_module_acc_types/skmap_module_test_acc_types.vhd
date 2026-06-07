
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;
use work.vec_pkg.all;

use work.ramface_pkg.all;
use work.skmap_pkg.all;
use work.skmap_map_acc_pkg.all;

use work.skmap_module_ipkg;

entity skmap_module_test_acc_types is
  generic (
    BASE_ADDR       : natural;
    RAMFACE_ADDR_W  : natural;
    RAMFACE_DATA_W  : natural;
    RAMFACE_WREN_W  : natural := RAMFACE_DATA_W/8;
    RAMFACE_LATENCY : natural := skmap_module_ipkg.RAMFACE_LATENCY
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

architecture rtl of skmap_module_test_acc_types is

  constant SKMAP_ID : string := "Test_Acc";
  constant SKMAP_VER_MAJOR : skmap_ver_major_t := 1;
  constant SKMAP_VER_MINOR : skmap_ver_minor_t := 0;
  constant SKMAP_KIDS : integer_vector := VOID_INTEGER_VECTOR;
  constant REGS_RO_LEN    : natural := 3;
  constant REGS_RO_ELEM_W : natural := 3;
  constant REGS_RW_LEN    : natural := REGS_RO_LEN;
  constant REGS_RW_ELEM_W : natural := REGS_RO_ELEM_W;
  constant REGS_WS_LEN    : natural := 9;
  constant REGS_WS_ELEM_W : natural := 5;
  constant REG_RC_W      : natural := REGS_WS_LEN;

  -- constant REGS_K_INT      : integer_vector := get_vec_int_range(7) + 16#C_0000#;
  constant REGS_K_INT      : integer_vector := pack_sw_ints((REGS_RO_LEN, REGS_RO_ELEM_W, REGS_RW_LEN, REGS_RW_ELEM_W, REGS_WS_LEN, REGS_WS_ELEM_W, REG_RC_W), 8);
  -- constant REGS_VAR_LEN    : natural := ceil_div(REGS_RW_LEN*promote_to_sw_w(REGS_RW_ELEM_W),32);
  constant REGS_VAR_LEN    : natural := 5; -- TODO: Calculate

  -- constant REGS_RO        : vec_slv32_t := to_vec_slv(to_vec_unsigned(get_vec_int_range(REGS_RO_LEN) + 16#D_0000#, 32));

  signal regs_var_rd_data : vec_slv32_t(0 to REGS_VAR_LEN-1) := (others => (others => '0'));
  signal regs_var_wr_data : vec_slv32_t(0 to REGS_VAR_LEN-1);
  signal regs_var_wr_wren : vec_slv4_t (0 to REGS_VAR_LEN-1);

  signal regs_ro : vec_slv_t(0 to REGS_RO_LEN-1)(REGS_RO_ELEM_W-1 downto 0);
  signal regs_rw : vec_slv_t(0 to REGS_RW_LEN-1)(REGS_RW_ELEM_W-1 downto 0);
  signal regs_ws : vec_slv_t(0 to REGS_WS_LEN-1)(REGS_WS_ELEM_W-1 downto 0);
  signal regs_ws_strb : std_ulogic_vector(REGS_WS_LEN-1 downto 0);
  signal reg_rc_set : std_ulogic_vector(REG_RC_W-1 downto 0);

begin

  i_skmap_module : entity work.skmap_module
  generic map (
    SKMAP_ID           => SKMAP_ID,
    SKMAP_VER_MAJOR    => SKMAP_VER_MAJOR,
    SKMAP_VER_MINOR    => SKMAP_VER_MINOR,
    SKMAP_KIDS         => SKMAP_KIDS,
    BASE_ADDR          => BASE_ADDR,
    RAMFACE_ADDR_W     => RAMFACE_ADDR_W,
    RAMFACE_DATA_W     => RAMFACE_DATA_W,
    RAMFACE_WREN_W     => RAMFACE_WREN_W,
    RAMFACE_LATENCY    => RAMFACE_LATENCY,
    REGS_K_INT         => REGS_K_INT,
    REGS_VAR_LEN       => REGS_VAR_LEN
  ) port map (
    clk_i              => clk_i,
    ramface_ce_i       => ramface_ce_i,
    ramface_rqst_i     => ramface_rqst_i,
    ramface_rply_o     => ramface_rply_o,

    regs_var_wr_wren_o => regs_var_wr_wren,
    regs_var_wr_data_o => regs_var_wr_data,
    regs_var_rd_data_i => regs_var_rd_data
  );

  regs_ro <= regs_rw;
  reg_rc_set  <= regs_ws_strb;

  process(all)
    variable byte_idx : natural;
  begin
    byte_idx := 0;
    -- skmap_map_acc_ro(regs_var_rd_data, byte_idx, REGS_RO);teste
    skmap_map_acc_ro(regs_var_rd_data, byte_idx, regs_ro);
    skmap_map_acc_rw(regs_var_rd_data, regs_var_wr_data, byte_idx, regs_rw);
    skmap_map_acc_ws(regs_var_rd_data, regs_var_wr_data, regs_var_wr_wren, byte_idx, regs_ws, regs_ws_strb);
    if rising_edge(clk_i) then
      skmap_map_acc_rc_flags(regs_var_rd_data, regs_var_wr_wren, byte_idx, reg_rc_set);
    else
      skmap_map_acc_byte_inc(byte_idx, reg_rc_set'length);
    end if;

  end process;

end architecture;
