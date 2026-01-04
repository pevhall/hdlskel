library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

package basic_pkg is

  function zeros(w : natural) return std_ulogic_vector;

  --
  function if_then_else(b : boolean; num1 : integer; num2 : integer) return integer;

  -- conversions
  function to_sl(b : boolean) return std_ulogic;
  function to_sl(l : std_ulogic_vector) return std_ulogic;
  function to_slv(l : std_ulogic) return std_ulogic_vector;
  function to_slv(num : integer; w : natural) return std_ulogic_vector;

  -- maths
  function ceil_div(num : integer; div : integer) return integer;
  function ceil_log_base(num : natural; base : natural) return natural;
  function ceil_log2(num : natural) return natural;
  procedure inc(num_io : inout integer; inc_i : in integer := 1);
  procedure inc(num_io : inout unsigned; inc_i : in integer := 1);

  -- flat_vec
  function from_flat_vec(flat : std_ulogic_vector; idx : natural; elem_w : natural) return std_ulogic_vector;
  procedure to_flat_vec(flat_io : inout std_ulogic_vector; idx_i : in natural; elem_i : in std_ulogic_vector);
end package;

package body basic_pkg is

  function zeros(w : natural) return std_ulogic_vector is
    constant SLV : std_ulogic_vector(w-1 downto 0) := (others => '0');
  begin
    return SLV;
  end function;

  function if_then_else(b : boolean; num1 : integer; num2 : integer) return integer is
  begin
    if b then
      return num1;
    end if;
    return num2;
  end function;

  function to_sl(b : boolean) return std_ulogic is
  begin
    if b then
      return '1';
    end if;
    return '0';
  end function;

  function to_sl(l : std_ulogic_vector) return std_ulogic is
  begin
    assert l'length = 1
    severity FAILURE;
    return l(l'low);
  end function;

  function to_slv(l : std_ulogic) return std_ulogic_vector is
    variable slv : std_ulogic_vector(0 downto 0) := (0 => l);
  begin
    return slv;
  end function;

  function to_slv(num : integer; w : natural) return std_ulogic_vector is
  begin
    return std_ulogic_vector(to_signed(num, w));
  end function;

  function ceil_div(num : integer; div : integer) return integer is
  begin
    return (num + div-1) / div;
  end function;

  function ceil_log_base(num : natural; base : natural) return natural is
    variable temp   : natural := num;
    variable result : natural := 1;
  begin
    while temp > base - 1 loop
      result := result + 1;
      temp   := temp / base;
    end loop;

    return result;
  end function;

  function ceil_log2(num : natural) return natural is
  begin
    return ceil_log_base(num, 2);
  end function;

  procedure inc(num_io : inout integer; inc_i : in integer := 1) is
  begin
    num_io := num_io + inc_i;
  end procedure;

  procedure inc(num_io : inout unsigned; inc_i : in integer := 1) is
  begin
    num_io := num_io + inc_i;
  end procedure;

  function from_flat_vec(flat : std_ulogic_vector; idx : natural; elem_w : natural) return std_ulogic_vector is
  begin
    return flat(elem_w*(idx+1)-1 downto elem_w*idx);
  end function;

  procedure to_flat_vec(flat_io : inout std_ulogic_vector; idx_i : in natural; elem_i : in std_ulogic_vector) is
    constant L : natural := elem_i'length;
  begin
    flat_io(L*(idx_i+1)-1 downto L*idx_i) := elem_i;
  end procedure;

end package body;
