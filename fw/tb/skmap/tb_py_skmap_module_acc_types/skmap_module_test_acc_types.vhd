
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

  constant SKMAP_ID : string := "Test_ACC";
  constant SKMAP_VER_MAJOR : skmap_ver_major_t := 1;
  constant SKMAP_VER_MINOR : skmap_ver_minor_t := 0;
  constant SKMAP_KIDS : integer_vector := VOID_INTEGER_VECTOR;
  constant REGS_RO_LEN : natural := 3;

  -- constant REGS_K_INT      : integer_vector := get_vec_int_range(7) + 16#C_0000#;
  constant REGS_K_INT      : integer_vector := (0 => REGS_RO_LEN);
  constant REGS_VAR_LEN    : natural := REGS_RO_LEN;

  constant REGS_RO        : vec_slv32_t := to_vec_slv(to_vec_unsigned(get_vec_int_range(REGS_RO_LEN) + 16#D_0000#, 32));

  signal regs_var_wr_wren : vec_slv4_t (0 to REGS_VAR_LEN-1);
  signal regs_var_wr_data : vec_slv32_t(0 to REGS_VAR_LEN-1);
  signal regs_var_rd_data : vec_slv32_t(0 to REGS_VAR_LEN-1);

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
  )
  port map (
    clk_i              => clk_i,
    ramface_ce_i       => ramface_ce_i,
    ramface_rqst_i     => ramface_rqst_i,
    ramface_rply_o     => ramface_rply_o,

    regs_var_wr_wren_o => regs_var_wr_wren,
    regs_var_wr_data_o => regs_var_wr_data,
    regs_var_rd_data_i => regs_var_rd_data
  );

  process(all)
    variable byte_idx : natural;
  begin
    byte_idx := 0;
    skmap_map_acc_ro(regs_var_rd_data, byte_idx, REGS_RO);
  end process;


end architecture;
