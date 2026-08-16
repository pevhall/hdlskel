use work.basic_pkg.all;

package skmap_recipe_functions_pkg is

  function skmap_recipe_clog2(x : natural) return natural;
  function skmap_recipe_cdiv(n : natural; d : natural) return natural;

end package;

package body  skmap_recipe_functions_pkg is

  function skmap_recipe_clog2(x : natural) return natural is
  begin
    return ceil_log2(x);
  end function;

  function skmap_recipe_cdiv(n : natural; d : natural) return natural is
  begin
    return ceil_div(n, d);
  end function;
  
end package body;


