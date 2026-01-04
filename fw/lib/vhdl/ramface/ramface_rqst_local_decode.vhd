package ramface_rqst_local_decode_ipkg is
  constant LATENCY : natural := 1;
end package;
--------------------------------------------------------------------------------

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;
use work.ramface_pkg.all;

entity ramface_rqst_local_decode is
  generic (
    BASE_ADDR : natural;
    RAMFACE_ADDR_W : natural;
    RAMFACE_DATA_W : natural;
    RAMFACE_WREN_W : natural := RAMFACE_DATA_W/8;
    LOCAL_RAMFACE_DEPTH  : natural;
    LOCAL_RAMFACE_ADDR_W : natural := ceil_log2(LOCAL_RAMFACE_DEPTH)
  );
  port (
    clk_i : in  std_ulogic;

    ramface_ce_i : in std_ulogic := '1';
    ramface_rqst_i : in ramface_rqst_t(
      addr(RAMFACE_ADDR_W-1 downto 0),
      wren(RAMFACE_WREN_W-1 downto 0),
      data(RAMFACE_DATA_W-1 downto 0)
    );
    local_ramface_rqst_o : out ramface_rqst_t(
      addr(LOCAL_RAMFACE_ADDR_W-1 downto 0),
      wren(RAMFACE_WREN_W-1 downto 0),
      data(RAMFACE_DATA_W-1 downto 0)
    );
    local_ramface_rqst_en_rd_o : out std_ulogic;
    local_ramface_rqst_en_wr_o : out std_ulogic
);
end entity;

architecture rtl of ramface_rqst_local_decode is

  constant ADDR_END : natural := BASE_ADDR + LOCAL_RAMFACE_DEPTH;

  signal local_ramface_rqst : ramface_rqst_t(
    addr(LOCAL_RAMFACE_ADDR_W-1 downto 0),
    wren(RAMFACE_WREN_W-1 downto 0),
    data(RAMFACE_DATA_W-1 downto 0)
  ) := (
    en => '0',
    addr => (others => '0'),
    wren => (others => '0'),
    data => (others => '0')
  );
  signal local_ramface_rqst_wr : std_ulogic := '0';
  signal local_ramface_rqst_rd : std_ulogic := '0';

begin

  assert FALSE
  report "BASE_ADDR = "&integer'image(BASE_ADDR) & ", LEN = "&integer'image(LOCAL_RAMFACE_DEPTH)
  severity NOTE;

  assert ceil_log2(LOCAL_RAMFACE_DEPTH) >= LOCAL_RAMFACE_ADDR_W
  report "LOCAL_RAMFACE_ADDR_W too small to address total length"
  severity FAILURE;

  process(clk_i)
    variable en_v : std_ulogic;
    variable addr_v : unsigned(RAMFACE_ADDR_W-1 downto 0);
  begin
    if rising_edge(clk_i) then
      if ramface_ce_i = '1' then
        addr_v := ramface_rqst_i.addr;
        en_v   := ramface_rqst_i.en
               and to_sl(addr_v >= BASE_ADDR)
               and to_sl(addr_v < ADDR_END);
        local_ramface_rqst.en   <= en_v;
        local_ramface_rqst.addr <= resize(addr_v - BASE_ADDR, LOCAL_RAMFACE_ADDR_W);
        if en_v = '1' then
          local_ramface_rqst.wren <= ramface_rqst_i.wren;
        else
          local_ramface_rqst.wren <= (others => '0');
        end if;
        local_ramface_rqst.data <= ramface_rqst_i.data;

        local_ramface_rqst_wr <= en_v and     (or ramface_rqst_i.wren);
        local_ramface_rqst_rd <= en_v and not (or ramface_rqst_i.wren);
      end if;
    end if;
  end process;

  local_ramface_rqst_o       <= local_ramface_rqst;
  local_ramface_rqst_en_wr_o <= local_ramface_rqst_wr;
  local_ramface_rqst_en_rd_o <= local_ramface_rqst_rd;

end architecture;
