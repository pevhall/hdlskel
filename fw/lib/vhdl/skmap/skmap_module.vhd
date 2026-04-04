use work.ramface_regs_rw_ipkg;
use work.ramface_rply_combine_ipkg;

package skmap_module_ipkg is
  constant PRIV_RPLY_COMBINE_LATENCY : natural;
  constant PRIV_RAMFACE_REGS_LATENCY : natural := ramface_regs_rw_ipkg.RAMFACE_LATENCY;
  constant RAMFACE_LATENCY : natural;
end package;

package body skmap_module_ipkg is

  function get_priv_rply_combine_latency return natural is
    constant WRKR_LEN : natural := 2;
  begin
    return ramface_rply_combine_ipkg.get_latency(WRKR_LEN=>WRKR_LEN) + PRIV_RAMFACE_REGS_LATENCY;
  end function;
  constant PRIV_RPLY_COMBINE_LATENCY : natural := get_priv_rply_combine_latency;
  constant RAMFACE_LATENCY : natural := skmap_module_ipkg.PRIV_RPLY_COMBINE_LATENCY + PRIV_RAMFACE_REGS_LATENCY;

end package body;
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;
use work.vec_pkg.all;

use work.ramface_pkg.all;
use work.skmap_pkg.all;

use work.skmap_module_ipkg;

entity skmap_module is
  generic (
    SKMAP_ID : string;
    SKMAP_VER_MAJOR : skmap_ver_major_t;
    SKMAP_VER_MINOR : skmap_ver_minor_t;
    SKMAP_KIDS : integer_vector := VOID_INTEGER_VECTOR;
    SKMAP_LEN_VAR : skmap_len_var_t := 0;

    BASE_ADDR       : natural;
    RAMFACE_ADDR_W  : natural;
    RAMFACE_DATA_W  : natural;
    RAMFACE_WREN_W  : natural := RAMFACE_DATA_W/8;
    RAMFACE_LATENCY : natural := skmap_module_ipkg.RAMFACE_LATENCY;

    REGS_K_INT      : integer_vector := VOID_INTEGER_VECTOR;
    REGS_VAR_LEN    : natural
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
    );

    regs_var_wr_wren_o : out vec_slv4_t (0 to REGS_VAR_LEN-1);
    regs_var_wr_data_o : out vec_slv32_t(0 to REGS_VAR_LEN-1);
    regs_var_rd_data_i : in  vec_slv32_t(0 to REGS_VAR_LEN-1)
  );
end entity;

architecture rtl of skmap_module is

  constant RAMFACE_REG_LATENCY  : natural := skmap_module_ipkg.PRIV_RAMFACE_REGS_LATENCY;
  constant RPLY_COMBINE_LATENCY : natural := RAMFACE_LATENCY - RAMFACE_REG_LATENCY;

  constant REGS_DATA_W : natural := 32;
  constant SKMAP_SUBHEAD_PAD_LEN : natural := get_ramface_ram_pad(SKMAP_HEAD_LEN + SKMAP_KIDS'length + REGS_K_INT'length, REGS_DATA_W, RAMFACE_DATA_W);
  constant RAMFACE_K_SKMAP_LEN : natural := SKMAP_HEAD_LEN + SKMAP_KIDS'length + SKMAP_SUBHEAD_PAD_LEN + REGS_K_INT'length;
  constant RAMFACE_K_DEPTH : natural := get_ramface_local_depth(RAMFACE_K_SKMAP_LEN, REGS_DATA_W, RAMFACE_DATA_W);

  constant SKMAP_HEAD : skmap_head_t := (
    id          => SKMAP_ID,
    ver_major   => SKMAP_VER_MAJOR,
    ver_minor   => SKMAP_VER_MINOR,
    len_kids    => SKMAP_KIDS'length,
    len_sub     => SKMAP_SUBHEAD_PAD_LEN,
    len_k       => REGS_K_INT'length,
    len_var     => SKMAP_LEN_VAR
  );
  constant RAMFACE_K_REGS_INT : integer_vector := (
      to_vec_int(SKMAP_HEAD)
    & SKMAP_KIDS
    & zeros_vec_int(SKMAP_SUBHEAD_PAD_LEN)
    & REGS_K_INT
  );
  constant BASE_ADDR_REGS_RW : natural := BASE_ADDR + RAMFACE_K_DEPTH;

  signal ramface_rply_regs_k : ramface_rply_t(
    data(RAMFACE_DATA_W -1 downto 0)
  );
  signal ramface_rply_regs_rw : ramface_rply_t(
    data(RAMFACE_DATA_W -1 downto 0)
  );

begin


  i_ramface_regs_k : entity work.ramface_regs_k
  generic map (
    BASE_ADDR      => BASE_ADDR,
    RAMFACE_ADDR_W => RAMFACE_ADDR_W,
    RAMFACE_DATA_W => RAMFACE_DATA_W,
    RAMFACE_WREN_W => RAMFACE_WREN_W,
    REGS_DATA_W    => REGS_DATA_W,
    REGS_K_INT     => RAMFACE_K_REGS_INT,
    RAMFACE_LATENCY => RAMFACE_REG_LATENCY
  )
  port map (
    clk_i          => clk_i,
    ramface_ce_i   => ramface_ce_i,
    ramface_rqst_i => ramface_rqst_i,
    ramface_rply_o => ramface_rply_regs_k
  );


  i_ramface_regs_rw : entity work.ramface_regs_rw
  generic map (
    BASE_ADDR      => BASE_ADDR_REGS_RW,
    RAMFACE_ADDR_W => RAMFACE_ADDR_W,
    RAMFACE_DATA_W => RAMFACE_DATA_W,
    RAMFACE_WREN_W => RAMFACE_WREN_W,
    REGS_DATA_W    => REGS_DATA_W,
    REGS_LEN       => REGS_VAR_LEN,
    RAMFACE_LATENCY => RAMFACE_REG_LATENCY
  )
  port map (
    clk_i          => clk_i,
    ramface_ce_i   => ramface_ce_i,
    ramface_rqst_i => ramface_rqst_i,
    ramface_rply_o => ramface_rply_regs_rw,
    regs_wr_wren_o => regs_var_wr_wren_o,
    regs_wr_data_o => regs_var_wr_data_o,
    regs_rd_data_i => regs_var_rd_data_i
  );


  i_ramface_rply_combine : entity work.ramface_rply_combine
  generic map (
    RAMFACE_DATA_W  => RAMFACE_DATA_W,
    WRKR_LEN    => 2,
    LATENCY     => RPLY_COMBINE_LATENCY
  )
  port map (
    clk_i          => clk_i,
    ce_i           => ramface_ce_i,
    wrkr_rply_i(0) => ramface_rply_regs_k,
    wrkr_rply_i(1) => ramface_rply_regs_rw,
    mstr_rply_o    => ramface_rply_o
  );

end architecture;
