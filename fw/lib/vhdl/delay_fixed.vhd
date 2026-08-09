library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.vec_pkg.all;

entity delay_fixed is
  generic (
    DELAY : natural;
    DATA_W : natural
  );
  port (
    clk_i      : in  std_ulogic;
    ce_i       : in  std_ulogic;
    src_data_i : in  std_ulogic_vector(DATA_W-1 downto 0);
      dst_data_o : out std_ulogic_vector(DATA_W-1 downto 0)
  );
end entity;

architecture rtl of delay_fixed is


begin
  g_arch : if DELAY = 0 generate

    dst_data_o <= src_data_i;

  else generate
    signal z_data : vec_slv_t(0 to DELAY-1)(DATA_W-1 downto 0) := (others => (others => '0' ) );
  begin

    process(clk_i)
    begin
      if rising_edge(clk_i) then
        if ce_i = '1' then
          z_data <= src_data_i & z_data(0 to DELAY-2);
        end if;
      end if;
    end process;
    dst_data_o <= z_data(DELAY-1);

  end generate;


end architecture;
