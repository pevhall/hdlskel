library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;
use work.vec_pkg.all;
use work.misc_pkg.all;

package ramface_pkg is

  type ramface_rqst_t is record
    en   : std_ulogic;
    addr : u_unsigned;
    wren : std_ulogic_vector;
    data : std_ulogic_vector;
  end record;

  type ramface_rply_t is record
    en   : std_ulogic;
    fail : std_ulogic;
    data : std_ulogic_vector;
  end record;

  type vec_ramface_rqst_t is array (natural range <>) of ramface_rqst_t;

  type vec_ramface_rply_t is array (natural range <>) of ramface_rply_t;

  function init_ramface_rqst(ADDR_W : natural; DATA_W : natural) return ramface_rqst_t;
  function init_ramface_rqst(ADDR_W : natural; DATA_W : natural; WREN_W : natural) return ramface_rqst_t;

  -- function get_ramface_addr_start(BASE_ADDR : natural; RAMFACE_DATA_W : natural) return natural;
  function get_ramface_local_depth(RAM_LEN : natural; RAM_DATA_W : natural; RAMFACE_DATA_W : natural) return natural;
  function get_ramface_ram_pad(RAM_LEN : natural; RAM_DATA_W : natural; RAMFACE_DATA_W : natural) return natural;

  function get_rply_flat_w(vec_rply : vec_ramface_rply_t) return natural;
  function get_flat_w(t : ramface_rply_t) return natural;
  function to_flat (rply : ramface_rply_t) return std_ulogic_vector;
  function to_vec_flat (vec_rply : vec_ramface_rply_t) return vec_slv_t;
  function to_ramface_rply(flat : std_ulogic_vector) return ramface_rply_t;

end package;

package body ramface_pkg is

  -- function get_ramface_addr_start(BASE_ADDR : natural; RAMFACE_DATA_W : natural) return natural is
  --   constant ADDR_DIV : natural := RAMFACE_DATA_W / 8;
  -- begin
  --   assert RAMFACE_DATA_W mod 8 = 0 severity FAILURE;
  --   assert BASE_ADDR mod ADDR_DIV = 0 severity FAILURE;
  --   return BASE_ADDR / ADDR_DIV;
  -- end function;

  function get_ramface_local_depth(RAM_LEN : natural; RAM_DATA_W : natural; RAMFACE_DATA_W : natural) return natural is
  begin
    return ceil_div(RAM_LEN*RAM_DATA_W, RAMFACE_DATA_W);
  end function;

  function get_ramface_ram_pad(RAM_LEN : natural; RAM_DATA_W : natural; RAMFACE_DATA_W : natural) return natural is
    constant RAMFACE_DEPTH : natural := get_ramface_local_depth(RAM_LEN, RAM_DATA_W, RAMFACE_DATA_W);
  begin
    return (RAMFACE_DEPTH*RAMFACE_DATA_W/RAM_DATA_W) - RAM_LEN;
  end function;

  function get_flat_w(t : ramface_rply_t) return natural is
  begin
    return t.data'length + 2;
  end function;

  function init_ramface_rqst(ADDR_W : natural; DATA_W : natural) return ramface_rqst_t is
  begin
    return init_ramface_rqst(ADDR_W, DATA_W, DATA_W/8);
  end function;

  function init_ramface_rqst(ADDR_W : natural; DATA_W : natural; WREN_W : natural) return ramface_rqst_t is
    variable rqst : ramface_rqst_t(
      addr(ADDR_W-1 downto 0),
      data(DATA_W-1 downto 0),
      wren(WREN_W-1 downto 0)
    ) := (
      en   => '0',
      addr => (others => '0'),
      wren => (others => '0'),
      data => (others => '0')
    );
  begin
    return rqst;
  end function;

  function to_flat (rply : ramface_rply_t) return std_ulogic_vector is
    constant DATA_W : natural := rply.data'length;
    constant WS : integer_vector(0 to 2) := (1, 1, DATA_W);
    constant FLAT_W : natural := get_flat_w(rply);
    variable flat : std_ulogic_vector(FLAT_W-1 downto 0);
  begin
    to_flat_rec(flat, WS, 0, to_slv          (rply.en));
    to_flat_rec(flat, WS, 1, to_slv          (rply.fail));
    to_flat_rec(flat, WS, 2, std_ulogic_vector(rply.data));
    return flat;
  end function;

  -- function get_data_length(vec_rply : vec_ramface_rply_t) return natural is
  -- begin
  --   if vec_rply'length = 0 then
  --     return 0;
  --   end if;
  --   return vec_rply(vec_rply'low).data'length;
  -- end function;

  function get_rply_flat_w(vec_rply : vec_ramface_rply_t) return natural is
  begin
    if vec_rply'length = 0 then
      return 0;
    end if;
    return get_flat_w(vec_rply(vec_rply'low));
  end function;

  function to_vec_flat(vec_rply : vec_ramface_rply_t) return vec_slv_t is
    constant FLAT_W : natural := get_rply_flat_w(vec_rply);
    variable vec_slv : vec_slv_t(vec_rply'range)(FLAT_W-1 downto 0);
  begin
    for idx in vec_rply'range loop
      vec_slv(idx) := to_flat(vec_rply(idx));
    end loop;
    return vec_slv;
  end function;

  function to_ramface_rply(flat : std_ulogic_vector) return ramface_rply_t is
    constant DATA_W : natural := flat'length - 2;
    constant WS : integer_vector(0 to 2) := (1, 1, DATA_W);
    variable rply : ramface_rply_t(data(DATA_W-1 downto 0)) := (
      en   => to_sl(from_flat_rec(flat, WS, 0)),
      fail => to_sl(from_flat_rec(flat, WS, 1)),
      data =>       from_flat_rec(flat, WS, 2)
    );
  begin
    return rply;
  end function;

end package body;
