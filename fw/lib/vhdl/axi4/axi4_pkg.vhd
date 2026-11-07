library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

package axi4_pkg is
  constant AXI4_LEN_W : natural := 8;
  constant AXI4_SIZE_W : natural := 3;
  constant AXI4_BURST_W : natural := 2;
  constant AXI4_CACHE_W : natural := 4;
  constant AXI4_PROT_W : natural := 3;
  constant AXI4_RESP_W : natural := 2;

  constant AXI4_BURST_INC : std_ulogic_vector(AXI4_BURST_W-1 downto 0) := "01";

  constant AXI4_RESP_OKAY   : std_ulogic_vector(AXI4_RESP_W-1 downto 0) := "00";
  constant AXI4_RESP_EXOKAY : std_ulogic_vector(AXI4_RESP_W-1 downto 0) := "01";
  constant AXI4_RESP_SLVERR : std_ulogic_vector(AXI4_RESP_W-1 downto 0) := "10";
  constant AXI4_RESP_DECERR : std_ulogic_vector(AXI4_RESP_W-1 downto 0) := "11";

  type axi4_aw_t is record
    valid : std_logic;
    addr  : std_logic_vector;
    len   : std_logic_vector ( AXI4_LEN_W-1 downto 0 );
    size  : std_logic_vector ( AXI4_SIZE_W-1 downto 0 );
    -- lock  : std_logic;
    -- cache : std_logic_vector ( AWCACHE_W downto 0 );
    -- prot  : std_logic_vector ( 2 downto 0 );
  end record;

  type axi4_w_t is record
    valid : std_ulogic;
    last : std_ulogic;
    strb : std_ulogic_vector;
    data : std_ulogic_vector;
  end record;

  type axi4_b_t is record
    s_axi_bresp : std_logic_vector ( AXI4_RESP_W-1 downto 0 );
    s_axi_bvalid : std_logic;
  end record;

  type axi4_ar_t is record
    valid : std_logic;
    addr  : std_logic_vector;
    len   : std_logic_vector ( AXI4_LEN_W-1 downto 0 );
    size  : std_logic_vector ( AXI4_SIZE_W-1 downto 0 );
    -- s_axi_arburst : std_logic_vector ( ARBURST-1 downto 0 );
    -- s_axi_arlock : in std_logic;
    -- s_axi_arcache : in std_logic_vector ( 3 downto 0 );
    -- s_axi_arprot : in std_logic_vector ( 2 downto 0 );
  end record;

  type axi4_r_t is record
    valid : std_ulogic;
    last : std_ulogic;
    resp : std_ulogic_vector(AXI4_RESP_W-1 downto 0);
    data : std_ulogic_vector;
  end record;

  type axi4_m2s_t is record
    aw : axi4_aw_t;
    w  : axi4_w_t;
    bready : std_ulogic;
    ar : axi4_ar_t;
    rready : std_ulogic;
  end record;

  type axi4_s2m_t is record
    awready : std_ulogic;
    wready : std_ulogic;
    b : axi4_b_t;
    arready : std_ulogic;
    r : axi4_r_t;
  end record;

end package;
