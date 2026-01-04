library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;

use work.ramface_pkg.all;

package ramface_sim_pkg is

  type ramface_sim_ctrl_t is record
    period  : time;
    latency : natural;
    clk     : std_ulogic;
    rqst    : ramface_rqst_t;
  end record;

  function init_ramface_sim_ctrl(latency : natural; ADDR_W : natural; DATA_W : natural; WREN_W : integer := -1; period : time := 1 ns) return ramface_sim_ctrl_t;

  procedure cyc(signal ctrl_io : inout ramface_sim_ctrl_t);

  procedure ramface_sim_rqst_wr(signal ctrl_io : inout ramface_sim_ctrl_t; addr_i : natural; slv_i : in std_ulogic_vector);
  procedure ramface_sim_rqst_rd(signal ctrl_io : inout ramface_sim_ctrl_t; signal rply_i : ramface_rply_t; addr_i : natural; slv_io : inout std_ulogic_vector);

end package;

package body ramface_sim_pkg is

  function init_ramface_sim_ctrl(latency : natural; ADDR_W : natural; DATA_W : natural; WREN_W : integer := -1; period : time := 1 ns) return ramface_sim_ctrl_t is
  constant INTL_WREN_W : natural := if_then_else(WREN_W = -1, DATA_W/8, WREN_W);
    variable ctrl : ramface_sim_ctrl_t(rqst(
      addr(ADDR_W-1 downto 0),
      data(DATA_W-1 downto 0),
      wren(INTL_WREN_W-1 downto 0)
    )) := (
      latency => latency,
      period  => period,
      clk     => '1',
      rqst    => init_ramface_rqst( 
        ADDR_W => ADDR_W,
        DATA_W => DATA_W,
        WREN_W => INTL_WREN_W
      )
    );
  begin
    return ctrl;
  end function;

  procedure cyc(signal ctrl_io : inout ramface_sim_ctrl_t) is
  begin
    wait for ctrl_io.period/2;
    ctrl_io.clk <= '0';
    wait for ctrl_io.period/2;
    ctrl_io.clk <= '1';
  end procedure;

  procedure ramface_sim_rqst_wr(signal ctrl_io : inout ramface_sim_ctrl_t; addr_i : natural; slv_i : in std_ulogic_vector) is
    constant ADDR_W : natural := ctrl_io.rqst.addr'length;
    constant DATA_W : natural := ctrl_io.rqst.data'length;
    constant WREN_W : natural := ctrl_io.rqst.wren'length;
    constant WORD_W : natural := DATA_W / WREN_W;
    variable slv_w  : natural := slv_i'length;
    variable wr_words : natural := slv_w/WORD_W;
    variable cycs : natural := ceil_div(slv_w, DATA_W);
    variable word : std_ulogic_vector(WORD_W-1 downto 0);
    variable addr : unsigned(ADDR_W-1 downto 0) := to_unsigned(addr_i, ADDR_W);
    variable data : std_ulogic_vector(DATA_W-1 downto 0);
    variable slv_word : integer := 0;
  begin
    assert slv_w rem WORD_W = 0 severity FAILURE;

    for c in 0 to cycs-1 loop
      ctrl_io.rqst.en <= '1';
      ctrl_io.rqst.addr <= addr;
      inc(addr);
      for w in 0 to WREN_W-1 loop
        if slv_word < wr_words then
          ctrl_io.rqst.wren(w) <= '1';
          word := from_flat_vec(slv_i, slv_word, WORD_W);
          inc(slv_word);
        else
          ctrl_io.rqst.wren(w) <= '0';
          word := (others => '0');
        end if;
        to_flat_vec(data, w, word);
      end loop;
      ctrl_io.rqst.data <= data;
      cyc(ctrl_io);
    end loop;
    ctrl_io.rqst.en <= '0';
  end procedure;

  procedure ramface_sim_rqst_rd(signal ctrl_io : inout ramface_sim_ctrl_t; signal rply_i : ramface_rply_t; addr_i : natural; slv_io : inout std_ulogic_vector) is
    constant ADDR_W : natural := ctrl_io.rqst.addr'length;
    constant DATA_W : natural := ctrl_io.rqst.data'length;
    constant WREN_W : natural := ctrl_io.rqst.wren'length;
    constant WORD_W : natural := DATA_W / WREN_W;
    variable slv_w  : natural := slv_io'length;
    variable rd_cycs : natural := ceil_div(slv_w, DATA_W);
    variable cycs : natural := rd_cycs + ctrl_io.latency;
    -- variable slv : std_ulogic_vector(slv_io'range);
    variable slv_word : natural := 0;
    variable rd_words : natural := slv_w/WORD_W;
    variable word : std_ulogic_vector(WORD_W-1 downto 0);
    variable addr : unsigned(ADDR_W-1 downto 0) := to_unsigned(addr_i, ADDR_W);
  begin

    assert slv_w rem WORD_W = 0 severity FAILURE;

    assert rply_i.fail = '0'
    report "Reply is reporting failure"
    severity ERROR;

    ctrl_io.rqst.wren <= zeros(WREN_W);
    for c in 0 to cycs-1 loop
      if c < rd_cycs then
        ctrl_io.rqst.en <= '1';
        ctrl_io.rqst.addr <= addr;
        inc(addr);
      else
        ctrl_io.rqst.en <= '0';
        ctrl_io.rqst.addr <= to_unsigned(0, ADDR_W);
      end if;
      if c >= ctrl_io.latency then
        assert rply_i.en = '1'
        report "Reply did not come at expected time"
        severity ERROR;
        for w in 0 to WREN_W-1 loop
          if slv_word < rd_words then
            word := from_flat_vec(rply_i.data, w, WORD_W);
            to_flat_vec(slv_io, slv_word, word);
            inc(slv_word);
          end if;
        end loop;
      else
        assert rply_i.en = '0'
        report "Reply came at unexpected time"
        severity ERROR;
      end if;
      cyc(ctrl_io);
    end loop;
  end procedure;

end package body;

