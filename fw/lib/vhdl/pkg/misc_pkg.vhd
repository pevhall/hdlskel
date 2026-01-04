
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.vec_pkg.all;

package misc_pkg is

  procedure to_flat_rec( flat_io : inout std_ulogic_vector; constant WS : in integer_vector; constant IDX : in natural; slv_i : in  std_ulogic_vector);

  function from_flat_rec ( flat : std_ulogic_vector; constant WS : integer_vector; constant IDX : in natural) return std_ulogic_vector;

end package;

package body misc_pkg is

  procedure to_flat_rec( flat_io : inout std_ulogic_vector; constant WS : in integer_vector; constant IDX : in natural; slv_i : in  std_ulogic_vector) is
    constant IDX_HIGH : integer := + WS(0 TO IDX)-1;
    constant IDX_LOW  : natural := + WS(0 TO IDX-1);
  begin
    flat_io(IDX_HIGH downto IDX_LOW) := slv_i;
  end procedure;

  function from_flat_rec ( flat : std_ulogic_vector; constant WS : integer_vector; constant IDX : in natural) return std_ulogic_vector is
    constant IDX_HIGH : integer := + WS(0 TO IDX)-1;
    constant IDX_LOW  : natural := + WS(0 TO IDX-1);
  begin
    return flat(IDX_HIGH downto IDX_LOW);
  end function;

end package body;
