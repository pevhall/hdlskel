package ramface_map_local_ipkg is

  function get_LATENCY(
    RAMFACE_DATA_W        : natural;
    LOCAL_RAMFACE_DATA_W  : natural;
    LOCAL_RAMFACE_LATENCY : natural
  ) return natural;

end package;

use work.ramface_rqst_w_adapt_ipkg;
use work.ramface_rply_w_adapt_ipkg;
use work.ramface_rqst_local_decode_ipkg;

package body ramface_map_local_ipkg is

  function get_LATENCY(
    RAMFACE_DATA_W        : natural;
    LOCAL_RAMFACE_DATA_W  : natural;
    LOCAL_RAMFACE_LATENCY : natural
  ) return natural is
  begin
    return LOCAL_RAMFACE_LATENCY + ramface_rqst_local_decode_ipkg.LATENCY
    + ramface_rqst_w_adapt_ipkg.get_LATENCY(SRC_RAMFACE_DATA_W=>RAMFACE_DATA_W,DST_RAMFACE_DATA_W=>LOCAL_RAMFACE_DATA_W)
    + ramface_rply_w_adapt_ipkg.get_LATENCY(SRC_RAMFACE_DATA_W=>RAMFACE_DATA_W,DST_RAMFACE_DATA_W=>LOCAL_RAMFACE_DATA_W);
  end function;

end package body;

--------------------------------------------------------------------------------

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;
use work.ramface_pkg.all;

use work.ramface_map_local_ipkg;

entity ramface_map_local is
  generic (
    RAMFACE_ADDR_W  : natural;
    RAMFACE_DATA_W  : natural;
    RAMFACE_WREN_W  : natural := RAMFACE_DATA_W/8;

    RAMFACE_LOCAL_BASE_ADDR : natural;

    LOCAL_RAMFACE_DEPTH   : natural;
    LOCAL_RAMFACE_DATA_W  : natural;
    LOCAL_RAMFACE_WREN_W  : natural := LOCAL_RAMFACE_DATA_W/8;
    LOCAL_RAMFACE_LATENCY : natural;

    RAMFACE_LATENCY : natural := ramface_map_local_ipkg.get_LATENCY (
      RAMFACE_DATA_W        => RAMFACE_DATA_W,
      LOCAL_RAMFACE_DATA_W  => LOCAL_RAMFACE_DATA_W,
      LOCAL_RAMFACE_LATENCY => LOCAL_RAMFACE_LATENCY
    )
  );
  port (
    clk_i        : in  std_ulogic;
    ramface_ce_i : in  std_ulogic;
    ramface_rqst_i : in  ramface_rqst_t(
      addr(RAMFACE_ADDR_W-1 downto 0),
      wren(RAMFACE_WREN_W-1 downto 0),
      data(RAMFACE_DATA_W-1 downto 0)
    );
    local_ramface_rqst_o : out ramface_rqst_t(
      addr(ceil_log2(LOCAL_RAMFACE_DEPTH)-1 downto 0),
      wren(LOCAL_RAMFACE_WREN_W-1 downto 0),
      data(LOCAL_RAMFACE_DATA_W-1 downto 0)
    );
    local_ramface_rqst_en_rd_o : out std_ulogic;
    local_ramface_rqst_en_wr_o : out std_ulogic;

    local_ramface_rply_i : in  ramface_rply_t(
      data(LOCAL_RAMFACE_DATA_W-1 downto 0)
    );
    ramface_rply_o : out  ramface_rply_t(
      data(RAMFACE_DATA_W-1 downto 0)
    )
  );
end entity;

use work.ramface_rqst_w_adapt_ipkg;
use work.ramface_rply_w_adapt_ipkg;
use work.ramface_rqst_local_decode_ipkg;

architecture rtl of ramface_map_local is

  constant LOCAL_RAMFACE_ADDR_W : natural := ceil_log2(LOCAL_RAMFACE_DEPTH);

  constant LATENCY_RQST_LOCAL_DECODE : natural := ramface_rqst_local_decode_ipkg.LATENCY;
  constant LATENCY_RQST_W_ADAPT : natural := ramface_rqst_w_adapt_ipkg.get_LATENCY(
    SRC_RAMFACE_DATA_W => RAMFACE_DATA_W,
    DST_RAMFACE_DATA_W => LOCAL_RAMFACE_DATA_W
  );
  constant LATENCY_RPLY_W_ADAPT : natural := ramface_rply_w_adapt_ipkg.get_LATENCY(
    SRC_RAMFACE_DATA_W => RAMFACE_DATA_W,
    DST_RAMFACE_DATA_W => LOCAL_RAMFACE_DATA_W
  );

  signal decode_ramface_rqst : ramface_rqst_t(
    addr(RAMFACE_ADDR_W-1 downto 0),
    wren(RAMFACE_WREN_W-1 downto 0),
    data(RAMFACE_DATA_W-1 downto 0)
  );
  signal decode_ramface_rqst_en_rd : std_ulogic;
  signal decode_ramface_rqst_en_wr : std_ulogic;

  constant RAMFACE_LOCAL_RAMFACE_DEPTH : natural := ceil_div(LOCAL_RAMFACE_DEPTH * RAMFACE_WREN_W, LOCAL_RAMFACE_WREN_W);
begin

  assert LATENCY_RQST_LOCAL_DECODE + LATENCY_RQST_W_ADAPT + LATENCY_RPLY_W_ADAPT + RAMFACE_LATENCY = RAMFACE_LATENCY
  report "Not currently supported"
  severity FAILURE;

  i_ramface_rqst_decode : entity work.ramface_rqst_local_decode
  generic map (
    BASE_ADDR          => RAMFACE_LOCAL_BASE_ADDR,
    RAMFACE_ADDR_W     => RAMFACE_ADDR_W,
    RAMFACE_DATA_W     => RAMFACE_DATA_W,
    RAMFACE_WREN_W     => RAMFACE_WREN_W,
    LOCAL_RAMFACE_DEPTH => RAMFACE_LOCAL_RAMFACE_DEPTH
  ) port map (
    clk_i                => clk_i,
    ramface_ce_i         => ramface_ce_i,
    ramface_rqst_i       => ramface_rqst_i,
    local_ramface_rqst_o => decode_ramface_rqst,
    local_ramface_rqst_en_rd_o => decode_ramface_rqst_en_rd,
    local_ramface_rqst_en_wr_o => decode_ramface_rqst_en_wr
  );

  i_ramface_rqst_w_adapt: entity work.ramface_rqst_w_adapt
  generic map(
      SRC_RAMFACE_ADDR_W => RAMFACE_ADDR_W,
      SRC_RAMFACE_DATA_W => RAMFACE_DATA_W,
      DST_RAMFACE_DATA_W => LOCAL_RAMFACE_DATA_W,
      DST_RAMFACE_ADDR_W => LOCAL_RAMFACE_ADDR_W,
      DST_RAMFACE_WREN_W => LOCAL_RAMFACE_WREN_W,
      LATENCY            => LATENCY_RQST_W_ADAPT,
      META_W             => 2
  ) port map(
      clk_i              => clk_i,
      ramface_ce_i       => ramface_ce_i,
      src_ramface_rqst_i => decode_ramface_rqst,
      src_meta_i(0)      => decode_ramface_rqst_en_rd,
      src_meta_i(1)      => decode_ramface_rqst_en_wr,
      dst_ramface_rqst_o => local_ramface_rqst_o,
      dst_meta_o(0)      => local_ramface_rqst_en_rd_o,
      dst_meta_o(1)      => local_ramface_rqst_en_wr_o
  );

  i_ramface_rply_w_adapt: entity work.ramface_rply_w_adapt
  generic map(
      SRC_RAMFACE_DATA_W => LOCAL_RAMFACE_DATA_W,
      DST_RAMFACE_DATA_W => RAMFACE_DATA_W,
      LATENCY            => LATENCY_RPLY_W_ADAPT
  ) port map(
      clk_i              => clk_i,
      ramface_ce_i       => ramface_ce_i,
      src_ramface_rply_i => local_ramface_rply_i,
      dst_ramface_rply_o => ramface_rply_o
  );

end architecture;
