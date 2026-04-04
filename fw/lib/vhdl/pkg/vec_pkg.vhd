library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;

package vec_pkg is

  type vec_slv_t      is array (natural range <>) of std_ulogic_vector;
  type vec_signed_t   is array (natural range <>) of u_signed;
  type vec_unsigned_t is array (natural range <>) of u_unsigned;

  type vec2_slv_t      is array (natural range <>) of vec_slv_t;
  type vec2_unsigned_t is array (natural range <>) of vec_unsigned_t;

  subtype vec_slv4_t  is vec_slv_t(open)( 4-1 downto 0);
  subtype vec_slv32_t is vec_slv_t(open)(32-1 downto 0);

  constant VOID_INTEGER_VECTOR : integer_vector(0 to -1);

  function zeros_vec_int  (len : integer) return integer_vector;
  function zeros_vec_slv32(len : integer) return vec_slv32_t;

  -- properties
  function get_elem_w(vec : vec_slv_t) return natural;
  function get_elem_w(vec : vec_signed_t) return natural;
  function get_elem_w(vec : vec_unsigned_t) return natural;

  -- create
  function get_vec_int_range(len : natural) return integer_vector;

  -- type conversions
  function to_vec_slv(v : std_ulogic_vector) return vec_slv_t;
  function to_vec_slv(vec : vec_unsigned_t) return vec_slv_t;
  function to_vec_unsigned(vec : vec_slv_t) return vec_unsigned_t;
  function to_vec_unsigned(v : integer_vector; elem_w : natural) return vec_unsigned_t;
  function to_vec_signed(vec : vec_slv_t) return vec_signed_t;
  function to_vec_int(vec : vec_signed_t) return integer_vector;
  function to_vec_int(vec : vec_unsigned_t) return integer_vector;

  function transpose(vec : vec_slv_t) return vec_slv_t;

  -- maths
  function "+"(lhs : integer_vector; rhs : integer) return integer_vector;
  function "+"(vec : integer_vector) return integer;
  function "+"(vec : vec_unsigned_t) return u_unsigned;
  function resize(vec : vec_unsigned_t; elem_w : natural) return vec_unsigned_t;

  -- flat
  function get_flat_w(vec : vec_slv_t) return natural;
  function get_flat_w(vec : vec_unsigned_t) return natural;
  function to_flat(vec : vec_slv_t) return std_ulogic_vector;
  function to_flat(vec : vec_unsigned_t) return std_ulogic_vector;
  function to_vec_slv(flat : std_ulogic_vector; slv_w : natural) return vec_slv_t;
  function to_vec_slv32(flat : std_ulogic_vector) return vec_slv_t;

end package;

package body vec_pkg is
  constant VOID_INTEGER_VECTOR : integer_vector(0 to -1) := (others => 0);

  function zeros_vec_int  (len : integer) return integer_vector is
    variable z : integer_vector(0 to len-1) := (others => 0);
  begin
    return z;
  end function;

  function zeros_vec_slv32(len : integer) return vec_slv32_t is
    variable z : vec_slv32_t(0 to len-1) := (others => (others => '0'));
  begin
    return z;
  end function;

  function get_elem_w(vec : vec_slv_t) return natural is
  begin
    if vec'length = 0 then
      return 0;
    end if;
    return vec(vec'low)'length;
  end function;

  function get_elem_w(vec : vec_signed_t) return natural is
  begin
    if vec'length = 0 then
      return 0;
    end if;
    return vec(vec'low)'length;
  end function;

  function get_elem_w(vec : vec_unsigned_t) return natural is
  begin
    if vec'length = 0 then
      return 0;
    end if;
    return vec(vec'low)'length;
  end function;

  function get_vec_int_range(len : natural) return integer_vector is
    variable vec : integer_vector(0 to len-1);
  begin
    for ii in vec'range loop
      vec(ii) := ii;
    end loop;
    return vec;
  end function;

  function to_vec_slv(v : std_ulogic_vector) return vec_slv_t is
    variable vec_slv : vec_slv_t(0 to 0)(v'length-1 downto 0) := (0 => v);
  begin
    return vec_slv;
  end function;

  function to_vec_slv(vec : vec_unsigned_t) return vec_slv_t is
    variable v : vec_slv_t(vec'range)(get_elem_w(vec)-1 downto 0);
  begin
    for ii in v'range loop
      v(ii) := std_ulogic_vector(vec(ii));
    end loop;
    return v;
  end function;

  function to_vec_unsigned(vec : vec_slv_t) return vec_unsigned_t is
    variable result : vec_unsigned_t(vec'range)(get_elem_w(vec)-1 downto 0);
  begin
    for ii in vec'range loop
      result(ii) := u_unsigned(vec(ii));
    end loop;
    return result;
  end function;

  function to_vec_unsigned(v : integer_vector; elem_w : natural) return vec_unsigned_t is
    variable vec : vec_unsigned_t(v'range)(elem_w-1 downto 0);
  begin
    for ii in vec'range loop
      vec(ii) := to_unsigned(v(ii), elem_w);
    end loop;
    return vec;
  end function;

  function to_vec_signed(vec : vec_slv_t) return vec_signed_t is
    constant ELEM_W : natural := get_elem_w(vec);
    variable vec_signed : vec_signed_t(vec'range)(ELEM_W-1 downto 0);
  begin
    for ii in vec'range loop
      vec_signed(ii) := signed(vec(ii));
    end loop;
    return vec_signed;
  end function;

  function to_vec_int(vec : vec_signed_t) return integer_vector is
    constant ELEM_W : natural := get_elem_w(vec);
    variable vec_int : integer_vector(vec'range);
  begin
    assert ELEM_W <= 32 severity FAILURE;
    for ii in vec'range loop
      vec_int(ii) := to_integer(vec(ii));
    end loop;
    return vec_int;
  end function;

  function to_vec_int(vec : vec_unsigned_t) return integer_vector is
    constant ELEM_W : natural := get_elem_w(vec);
    variable vec_int : integer_vector(vec'range);
  begin
    assert ELEM_W <= 31 severity FAILURE;
    for ii in vec'range loop
      vec_int(ii) := to_integer(vec(ii));
    end loop;
    return vec_int;
  end function;
  function transpose(vec : vec_slv_t) return vec_slv_t is
    variable result : vec_slv_t(0 to get_elem_w(vec)-1)(vec'length-1 downto 0);
  begin
    for ii in 0 to result'length-1 loop
      for jj in 0 to vec'length-1 loop
        result(ii)(jj) := vec(jj)(ii);
      end loop;
    end loop;
    return result;
  end function;

  function "+"(lhs : integer_vector; rhs : integer) return integer_vector is
    variable result : integer_vector(lhs'range);
  begin
    for ii in lhs'range loop
      result(ii) := lhs(ii) + rhs;
    end loop;
    return result;
  end function;

  function "+"(vec : integer_vector) return integer is
    variable result : integer := 0;
  begin
    for idx in vec'range loop
      result := result + vec(idx);
    end loop;
    return result;
  end function;

  function "+"(vec : vec_unsigned_t) return u_unsigned is
    variable result : u_unsigned(get_elem_w(vec)-1 downto 0) := (others => '0');
  begin
    for idx in vec'range loop
      result := result + vec(idx);
    end loop;
    return result;
  end function;

  function resize(vec : vec_unsigned_t; elem_w : natural) return vec_unsigned_t is
    variable result : vec_unsigned_t(vec'range)(elem_w-1 downto 0);
  begin
    for ii in vec'range loop
      result(ii) := resize(vec(ii), elem_w);
    end loop;
    return result;
  end function;

  function get_flat_w(vec : vec_slv_t) return natural is
  begin
    return get_elem_w(vec) * vec'length;
  end function;

  function get_flat_w(vec : vec_unsigned_t) return natural is
  begin
    return get_elem_w(vec) * vec'length;
  end function;

  function to_flat(vec : vec_slv_t) return std_ulogic_vector is
    constant FLAT_W : natural := get_flat_w(vec);
    variable flat : std_ulogic_vector(FLAT_W-1 downto 0);
  begin
    for ii in vec'range loop
      to_flat_vec(flat, ii, vec(ii));
    end loop;
    return flat;
  end function;

  function to_flat(vec : vec_unsigned_t) return std_ulogic_vector is
  begin
    return to_flat(to_vec_slv(vec));
  end function;

  function to_vec_slv(flat : std_ulogic_vector; slv_w : natural) return vec_slv_t is
    variable vec : vec_slv_t(0 to flat'length/slv_w-1)(slv_w-1 downto 0);
  begin
    assert flat'length = get_flat_w(vec) severity FAILURE;
    for ii in vec'range loop
      vec(ii) := from_flat_vec(flat, ii, slv_w);
    end loop;
    return vec;
  end function;

  function to_vec_slv32(flat : std_ulogic_vector) return vec_slv_t is
  begin
    return to_vec_slv(flat, 32);
  end function;

end package body;
