use work.vec_pkg.all;

use work.ramface_pkg.all;
use work.skmap_pkg.all;

package skmap_module_ipkg is

  constant PRIV_RAMFACE_REGS_LATENCY : natural;
  constant SKMAP_SIZE_RESERVED_DEFAULT : natural := 16#100#;

  function get_RAMFACE_LATENCY(RAMFACE_DATA_W : natural := 0; SKMAP_VEC_EXTERNAL_MEM : skmap_vec_external_mem_t := NULL_SKMAP_VEC_EXTERNAL_MEM) return natural;
  function head_and_k_len (SKMAP_BYTE_ALIGN : natural; RAMFACE_DATA_W : natural; SKMAP_KIDS : integer_vector; REGS_K_INT : integer_vector; SKMAP_VEC_EXTERNAL_MEM : skmap_vec_external_mem_t := NULL_SKMAP_VEC_EXTERNAL_MEM) return natural;

  function priv_EXTERNAL_MEM_BASE_ADDR_OFF(SKMAP_VEC_EXTERNAL_MEM : skmap_vec_external_mem_t; SKMAP_SIZE_RESERVED_BASE_REGS : natural := SKMAP_SIZE_RESERVED_DEFAULT) return natural;

  function priv_VEC_RAMFACE_LATENCY_EXT_MEM(RAMFACE_DATA_W : natural; SKMAP_VEC_EXTERNAL_MEM : skmap_vec_external_mem_t := NULL_SKMAP_VEC_EXTERNAL_MEM) return integer_vector;


end package;

use work.basic_pkg.all;

use work.ramface_rqst_local_decode_ipkg;
use work.ramface_regs_rw_ipkg;
use work.ramface_rply_combine_ipkg;
use work.ramface_map_local_ipkg;

package body skmap_module_ipkg is
  constant PRIV_RAMFACE_REGS_LATENCY : natural := ramface_regs_rw_ipkg.RAMFACE_LATENCY;

  function priv_EXTERNAL_MEM_BASE_ADDR_OFF(SKMAP_VEC_EXTERNAL_MEM : skmap_vec_external_mem_t; SKMAP_SIZE_RESERVED_BASE_REGS : natural := SKMAP_SIZE_RESERVED_DEFAULT) return natural is
    constant EXT_MEM_MAX_SIZE : natural := skmap_get_external_mem_max_size(SKMAP_VEC_EXTERNAL_MEM);
  begin
    return 2**ceil_log2(maximum(EXT_MEM_MAX_SIZE, SKMAP_SIZE_RESERVED_BASE_REGS));
  end function;

  function priv_VEC_RAMFACE_LATENCY_EXT_MEM(RAMFACE_DATA_W : natural; SKMAP_VEC_EXTERNAL_MEM : skmap_vec_external_mem_t := NULL_SKMAP_VEC_EXTERNAL_MEM) return integer_vector is
    variable latency_vec : integer_vector(SKMAP_VEC_EXTERNAL_MEM'range);
    variable mem : skmap_external_mem_t;
  begin
    for ii in latency_vec'range loop
      mem := SKMAP_VEC_EXTERNAL_MEM(ii);
      latency_vec(ii) := ramface_map_local_ipkg.get_LATENCY(
        RAMFACE_DATA_W        => RAMFACE_DATA_W,
        LOCAL_RAMFACE_DATA_W  => mem.data_w,
        LOCAL_RAMFACE_LATENCY => mem.latency
      );
    end loop;
    return latency_vec;
  end function;

  function get_RAMFACE_LATENCY(RAMFACE_DATA_W : natural := 0; SKMAP_VEC_EXTERNAL_MEM : skmap_vec_external_mem_t := NULL_SKMAP_VEC_EXTERNAL_MEM) return natural is
    constant RAMFACE_REG_LATENCY  : natural := PRIV_RAMFACE_REGS_LATENCY;
    -----------------------------------------
    ---- MATCH ARCH BEGIN
    -- constant DECODE_LATENCY : natural := ramface_rqst_local_decode_ipkg.LATENCY;
    constant TOTAL_EXTERNAL_MEM : natural := skmap_vec_external_mem'length;
    constant RPLY_LATENCY_MEM : integer_vector := priv_VEC_RAMFACE_LATENCY_EXT_MEM(RAMFACE_DATA_W, SKMAP_VEC_EXTERNAL_MEM);
    constant MAX_RPLY_LATENCY : natural := maximum( RAMFACE_REG_LATENCY & RPLY_LATENCY_MEM);
    constant RPLY_TO_COMBINE_LEN : natural := 2 + TOTAL_EXTERNAL_MEM;
    ---- MATCH ARCH END
    -----------------------------------------
    constant RPLY_TO_COMBINE_LATENCY : natural := ramface_rply_combine_ipkg.get_latency(WRKR_LEN => RPLY_TO_COMBINE_LEN);
  begin
    assert SKMAP_VEC_EXTERNAL_MEM'length = 0 or RAMFACE_DATA_W > 0
    report "Misconfigured" severity FAILURE;

    report "MAX_RPLY_LATENCY = "&integer'image(MAX_RPLY_LATENCY);
    report "RPLY_TO_COMBINE_LATENCY = "&integer'image(RPLY_TO_COMBINE_LATENCY);
    -- report "DECODE_LATENCY = "&integer'image(DECODE_LATENCY);

    return MAX_RPLY_LATENCY + RPLY_TO_COMBINE_LATENCY;
  end function;

  function head_and_k_len (SKMAP_BYTE_ALIGN : natural; RAMFACE_DATA_W : natural; SKMAP_KIDS : integer_vector; REGS_K_INT : integer_vector; SKMAP_VEC_EXTERNAL_MEM : skmap_vec_external_mem_t := NULL_SKMAP_VEC_EXTERNAL_MEM) return natural is
    constant EXTERNAL_MEM_BASE_ADDRS : integer_vector := get_vec_int_range(SKMAP_VEC_EXTERNAL_MEM'length) * 0;  -- PLACE HOLDER
  ------------------------------
  -- MATCH ARCHITECTURE BELOW BEGIN
  constant REGS_DATA_W : natural := 32;
  constant SKMAP_SUB_NO_PAD : integer_vector := 
      make_skmap_sub_byte_align(SKMAP_BYTE_ALIGN)
    & make_vec_skmap_sub_external_mem(SKMAP_VEC_EXTERNAL_MEM, VEC_BASE_ADDR=>EXTERNAL_MEM_BASE_ADDRS);
  constant SKMAP_SUBHEAD_PAD_LEN : natural := get_ramface_ram_pad(SKMAP_HEAD_LEN + SKMAP_KIDS'length + REGS_K_INT'length + SKMAP_SUB_NO_PAD'length, REGS_DATA_W, RAMFACE_DATA_W);
  
  constant SKMAP_SUB : integer_vector :=  SKMAP_SUB_NO_PAD & zeros_vec_int(SKMAP_SUBHEAD_PAD_LEN) ;
  constant RAMFACE_K_SKMAP_LEN : natural := SKMAP_HEAD_LEN + SKMAP_KIDS'length + SKMAP_SUB'length + REGS_K_INT'length;
  constant RAMFACE_K_DEPTH : natural := get_ramface_local_depth(RAMFACE_K_SKMAP_LEN, REGS_DATA_W, RAMFACE_DATA_W);
  -- MATCH ARCHITECTURE BELOW END
  ------------------------------
  begin
    return RAMFACE_K_DEPTH;
  end function;

end package body;

--------------------------------------------------------------------------------

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

use work.basic_pkg.all;
use work.vec_pkg.all;

use work.ramface_pkg.all;
use work.skmap_pkg.all;

use work.skmap_module_ipkg;

entity skmap_module is
  generic (
    SKMAP_ID        : skmap_id_t;
    SKMAP_VERSION   : skmap_version_t;
    SKMAP_CHECKSUM  : skmap_checksum_t;
    SKMAP_KIDS      : integer_vector := NULL_INTEGER_VECTOR;
    SKMAP_VEC_EXTERNAL_MEM : skmap_vec_external_mem_t := NULL_SKMAP_VEC_EXTERNAL_MEM;
    SKMAP_BYTE_ALIGN : natural := 1;
    SKMAP_SIZE_RESERVED : natural := skmap_module_ipkg.SKMAP_SIZE_RESERVED_DEFAULT;
    SKMAP_SIZE_RESERVED_BASE_REGS : natural := skmap_module_ipkg.SKMAP_SIZE_RESERVED_DEFAULT;

    BASE_ADDR       : natural;
    RAMFACE_ADDR_W  : natural;
    RAMFACE_DATA_W  : natural;
    RAMFACE_WREN_W  : natural := RAMFACE_DATA_W/8;
    RAMFACE_LATENCY : natural := skmap_module_ipkg.get_RAMFACE_LATENCY(
      RAMFACE_DATA_W => RAMFACE_DATA_W,
      SKMAP_VEC_EXTERNAL_MEM => SKMAP_VEC_EXTERNAL_MEM
    );

    REGS_K_INT      : integer_vector := NULL_INTEGER_VECTOR;
    REGS_VAR_LEN    : natural
  );
  port (
    clk_i : in  std_ulogic;

    ramface_ce_i : in std_ulogic := '1';
    ramface_rqst_i : in ramface_rqst_t(
      addr(RAMFACE_ADDR_W-1 downto 0),
      wren(RAMFACE_WREN_W-1 downto 0),
      data(RAMFACE_DATA_W-1 downto 0)
    );
    ramface_rply_o : out ramface_rply_t(
      data(RAMFACE_DATA_W -1 downto 0)
    );

    vec_ramface_external_mem_rqst_o : out vec_ramface_rqst_t ( 0 to SKMAP_VEC_EXTERNAL_MEM'length-1)(
      addr(skmap_get_external_mem_max_addr_w(SKMAP_VEC_EXTERNAL_MEM)-1 downto 0),
      wren(skmap_get_external_mem_max_data_w(SKMAP_VEC_EXTERNAL_MEM)/8-1 downto 0),
      data(skmap_get_external_mem_max_data_w(SKMAP_VEC_EXTERNAL_MEM)-1 downto 0)
    );
    vec_ramface_external_mem_rqst_en_rd_o : out std_ulogic_vector(SKMAP_VEC_EXTERNAL_MEM'length-1 downto 0);
    vec_ramface_external_mem_rqst_en_wr_o : out std_ulogic_vector(SKMAP_VEC_EXTERNAL_MEM'length-1 downto 0);

    vec_ramface_external_mem_rply_i : in  vec_ramface_rply_t ( 0 to SKMAP_VEC_EXTERNAL_MEM'length-1)(
      data(skmap_get_external_mem_max_data_w(SKMAP_VEC_EXTERNAL_MEM)-1 downto 0)
    ) := NULL_VEC_RAMFACE_RPLY;

    regs_var_rd_data_i : in  vec_slv32_t(0 to REGS_VAR_LEN-1);
    regs_var_wr_wren_o : out vec_slv4_t (0 to REGS_VAR_LEN-1);
    regs_var_wr_data_o : out vec_slv32_t(0 to REGS_VAR_LEN-1)
  );
end entity;

use work.ramface_rqst_local_decode_ipkg;
use work.ramface_map_local_ipkg;
use work.ramface_rply_combine_ipkg;
use work.skmap_module_ipkg.priv_VEC_RAMFACE_LATENCY_EXT_MEM;

architecture rtl of skmap_module is

  constant RAMFACE_REG_LATENCY  : natural := skmap_module_ipkg.PRIV_RAMFACE_REGS_LATENCY;

  -- MATCH IPKG BEGIN
    -- constant DECODE_LATENCY : natural := ramface_rqst_local_decode_ipkg.LATENCY;
    constant TOTAL_EXTERNAL_MEM : natural := skmap_vec_external_mem'length;
    constant RPLY_LATENCY_MEM : integer_vector := priv_VEC_RAMFACE_LATENCY_EXT_MEM(RAMFACE_DATA_W, SKMAP_VEC_EXTERNAL_MEM);
    constant MAX_RPLY_LATENCY : natural := maximum( RAMFACE_REG_LATENCY & RPLY_LATENCY_MEM);
    constant RPLY_TO_COMBINE_LEN : natural := 2 + TOTAL_EXTERNAL_MEM;
  -- MATCH IPKG END

  -- Dump extera latency into the reply combine
  function get_RPLY_TO_COMBINE_LATENCY return natural is
    constant DESIRED : natural := RAMFACE_LATENCY - MAX_RPLY_LATENCY;
    ---- MATCH ARCH END
    constant NEEDED : natural := ramface_rply_combine_ipkg.get_latency(WRKR_LEN => RPLY_TO_COMBINE_LEN);
  begin
    assert NEEDED <= DESIRED
    report "Need more latency, DESIRED "&to_string(DESIRED)&", NEEDED "&to_string(NEEDED)
      & ", " & "RAMFACE_LATENCY = "&integer'image(RAMFACE_LATENCY)
      & ", " & "MAX_RPLY_LATENCY = "&integer'image(MAX_RPLY_LATENCY)
      -- & ", " & "DECODE_LATENCY = "&integer'image(DECODE_LATENCY)
    severity FAILURE;
    return DESIRED;
  end function;

  constant RPLY_TO_COMBINE_LATENCY : natural := get_RPLY_TO_COMBINE_LATENCY;

  constant SKMAP_LEN_VAR : skmap_len_var_t := REGS_VAR_LEN;
  
  constant EXTERNAL_MEM_BASE_ADDR_OFF : natural := skmap_module_ipkg.priv_EXTERNAL_MEM_BASE_ADDR_OFF(SKMAP_VEC_EXTERNAL_MEM => SKMAP_VEC_EXTERNAL_MEM,  SKMAP_SIZE_RESERVED_BASE_REGS => SKMAP_SIZE_RESERVED_BASE_REGS);
  constant EXTERNAL_MEM_BASE_ADDRS : integer_vector := (get_vec_int_range(TOTAL_EXTERNAL_MEM)+1) * EXTERNAL_MEM_BASE_ADDR_OFF; 
  ------------------------------
  -- MATCH IPKG ABOVE BEGIN
  constant REGS_DATA_W : natural := 32;
  constant SKMAP_SUB_NO_PAD : integer_vector := 
      make_skmap_sub_byte_align(SKMAP_BYTE_ALIGN)
    & make_vec_skmap_sub_external_mem(SKMAP_VEC_EXTERNAL_MEM, VEC_BASE_ADDR=>EXTERNAL_MEM_BASE_ADDRS);
  constant SKMAP_SUBHEAD_PAD_LEN : natural := get_ramface_ram_pad(SKMAP_HEAD_LEN + SKMAP_KIDS'length + REGS_K_INT'length + SKMAP_SUB_NO_PAD'length, REGS_DATA_W, RAMFACE_DATA_W);
  
  constant SKMAP_SUB : integer_vector :=  SKMAP_SUB_NO_PAD & zeros_vec_int(SKMAP_SUBHEAD_PAD_LEN) ;
  constant RAMFACE_K_SKMAP_LEN : natural := SKMAP_HEAD_LEN + SKMAP_KIDS'length + SKMAP_SUB'length + REGS_K_INT'length;
  constant RAMFACE_K_DEPTH : natural := get_ramface_local_depth(RAMFACE_K_SKMAP_LEN, REGS_DATA_W, RAMFACE_DATA_W);
  -- MATCH IPKG ABOVE END
  ------------------------------

  constant SKMAP_HEAD : skmap_head_t := (
    id          => SKMAP_ID,
    version     => SKMAP_VERSION,
    flags       => zeros(SKMAP_FLAGS_W),
    checksum    => SKMAP_CHECKSUM,
    len_kids    => SKMAP_KIDS'length,
    len_sub     => SKMAP_SUB'length,
    len_k       => REGS_K_INT'length,
    len_var     => SKMAP_LEN_VAR
  );
  constant EXTERNAL_MEM_ADDR_W : natural := skmap_get_external_mem_max_addr_w(SKMAP_VEC_EXTERNAL_MEM);
  constant EXTERNAL_MEM_DATA_W : natural := skmap_get_external_mem_max_data_w(SKMAP_VEC_EXTERNAL_MEM);
  constant EXTERNAL_MEM_WREN_W : natural := EXTERNAL_MEM_DATA_W/8;

  constant RAMFACE_K_REGS_INT : integer_vector := (
      to_vec_int(SKMAP_HEAD)
    & SKMAP_KIDS
    & SKMAP_SUB
    & REGS_K_INT
  );
  constant BASE_ADDR_REGS_K  : natural := BASE_ADDR / RAMFACE_WREN_W;
  constant BASE_ADDR_REGS_RW : natural := BASE_ADDR_REGS_K + RAMFACE_K_DEPTH;
  constant SKMAP_SIZE_BASE_REGS : natural := BASE_ADDR_REGS_RW*RAMFACE_WREN_W-BASE_ADDR + REGS_VAR_LEN*SKMAP_WORD_BYTES;
  constant SKMAP_SIZE_TOTAL : natural := (TOTAL_EXTERNAL_MEM+1) * EXTERNAL_MEM_BASE_ADDR_OFF; 

  signal rply_to_combine_external_mem : vec_ramface_rply_t(0 to TOTAL_EXTERNAL_MEM-1)(
    data(RAMFACE_DATA_W-1 downto 0)
  );

  signal rply_to_combine_regs_k : ramface_rply_t(
    data(RAMFACE_DATA_W -1 downto 0)
  );
  signal rply_to_combine_regs_rw : ramface_rply_t(
    data(RAMFACE_DATA_W -1 downto 0)
  );

  function get_RPLY_TO_COMBINE_WRKR_VEC_LATENCY return integer_vector is
    variable VEC_LATENCY : integer_vector(0 to RPLY_TO_COMBINE_LEN-1);
  begin
    VEC_LATENCY(0) := RAMFACE_REG_LATENCY;
    VEC_LATENCY(1) := RAMFACE_REG_LATENCY;
    for ii in 0 to total_external_mem-1 loop
      VEC_LATENCY(2+ii) := RPLY_LATENCY_MEM(ii);
    end loop;
    -- report "SKMAP_SIZE_BASE_REGS = "&integer'image(SKMAP_SIZE_BASE_REGS)
    --  & "= ("&to_string(BASE_ADDR_REGS_RW)&" + "&to_string(REGS_VAR_LEN)&") * "&to_string(SKMAP_WORD_BYTES);
    return VEC_LATENCY;
  end function;

  signal rply_to_combine : vec_ramface_rply_t(0 to RPLY_TO_COMBINE_LEN-1)(
    data(RAMFACE_DATA_W -1 downto 0)
  );

begin


  assert is_power_of_2(RAMFACE_WREN_W)
  report "RAMFACE_WREN_W needs to be power of 2 (for addr divide)"
  severity FAILURE;

  assert is_power_of_2(SKMAP_BYTE_ALIGN)
  report "SKMAP_BYTE_ALIGN needs to be power of 2, got "&integer'image(SKMAP_BYTE_ALIGN)&", "&integer'image(ceil_log2(SKMAP_BYTE_ALIGN))
  severity FAILURE;

  assert SKMAP_SIZE_BASE_REGS <= SKMAP_SIZE_RESERVED_BASE_REGS
  report "Not enough skmap size reserved for base regs"
    & ". Resereved "&to_string(SKMAP_SIZE_RESERVED_BASE_REGS)&", needs "&to_string(SKMAP_SIZE_BASE_REGS)
  severity FAILURE;

  assert SKMAP_SIZE_TOTAL <= SKMAP_SIZE_RESERVED
  report "Not enough skmap size reserved for module (including external_mem), "
    & "Resereved "&to_string(SKMAP_SIZE_RESERVED)&", needs "&to_string(SKMAP_SIZE_TOTAL)
  severity FAILURE;

  i_ramface_regs_k : entity work.ramface_regs_k
  generic map (
    BASE_ADDR      => BASE_ADDR_REGS_K,
    RAMFACE_ADDR_W => RAMFACE_ADDR_W,
    RAMFACE_DATA_W => RAMFACE_DATA_W,
    RAMFACE_WREN_W => RAMFACE_WREN_W,
    REGS_DATA_W    => REGS_DATA_W,
    REGS_K_INT     => RAMFACE_K_REGS_INT,
    RAMFACE_LATENCY => RAMFACE_REG_LATENCY
  )
  port map (
    clk_i          => clk_i,
    ramface_ce_i   => ramface_ce_i,
    ramface_rqst_i => ramface_rqst_i,
    ramface_rply_o => rply_to_combine_regs_k
  );


  i_ramface_regs_rw : entity work.ramface_regs_rw
  generic map (
    BASE_ADDR      => BASE_ADDR_REGS_RW,
    RAMFACE_ADDR_W => RAMFACE_ADDR_W,
    RAMFACE_DATA_W => RAMFACE_DATA_W,
    RAMFACE_WREN_W => RAMFACE_WREN_W,
    REGS_DATA_W    => REGS_DATA_W,
    REGS_LEN       => REGS_VAR_LEN,
    RAMFACE_LATENCY => RAMFACE_REG_LATENCY
  )
  port map (
    clk_i          => clk_i,
    ramface_ce_i   => ramface_ce_i,
    ramface_rqst_i => ramface_rqst_i,
    ramface_rply_o => rply_to_combine_regs_rw,
    regs_wr_wren_o => regs_var_wr_wren_o,
    regs_wr_data_o => regs_var_wr_data_o,
    regs_rd_data_i => regs_var_rd_data_i
  );

  gl_external_ram : for ii in 0 to TOTAL_EXTERNAL_MEM-1 generate
    constant LOCAL_MEM : skmap_external_mem_t := skmap_vec_external_mem(skmap_vec_external_mem'low+ii);

    constant LOCAL_ADDR_W : natural := ceil_log2(LOCAL_MEM.depth);
    constant LOCAL_DATA_W : natural := LOCAL_MEM.data_w;
    constant LOCAL_WREN_W : natural := LOCAL_DATA_W / 8;

    constant LATENCY_EXTERNAL_MEM_MAP : natural := ramface_map_local_ipkg.get_LATENCY(
      RAMFACE_DATA_W        => RAMFACE_DATA_W,
      LOCAL_RAMFACE_DATA_W  => LOCAL_MEM.data_w,
      LOCAL_RAMFACE_LATENCY => LOCAL_MEM.latency
    );

    signal local_ramface_rqst : ramface_rqst_t(
      addr(LOCAL_ADDR_W-1 downto 0),
      wren(LOCAL_WREN_W-1 downto 0),
      data(LOCAL_DATA_W-1 downto 0)
    );
    signal local_ramface_rqst_en_rd : std_ulogic;
    signal local_ramface_rqst_en_wr : std_ulogic;

    signal external_mem_rqst : ramface_rqst_t(
      addr(EXTERNAL_MEM_ADDR_W-1 downto 0),
      wren(EXTERNAL_MEM_WREN_W-1 downto 0),
      data(EXTERNAL_MEM_DATA_W-1 downto 0)
    );

    signal external_mem_rply : ramface_rply_t(
      data(EXTERNAL_MEM_DATA_W-1 downto 0)
    );

  begin

    i_ramface_map_local : entity work.ramface_map_local
    generic map (
      RAMFACE_ADDR_W             => RAMFACE_ADDR_W,
      RAMFACE_DATA_W             => RAMFACE_DATA_W,
      RAMFACE_WREN_W             => RAMFACE_WREN_W,
      RAMFACE_LOCAL_BASE_ADDR    => EXTERNAL_MEM_BASE_ADDRS(ii)/RAMFACE_WREN_W,
      LOCAL_RAMFACE_DEPTH        => LOCAL_MEM.depth,
      LOCAL_RAMFACE_DATA_W       => LOCAL_DATA_W,
      LOCAL_RAMFACE_WREN_W       => LOCAL_WREN_W,
      LOCAL_RAMFACE_LATENCY      => LOCAL_MEM.latency,
      RAMFACE_LATENCY            => LATENCY_EXTERNAL_MEM_MAP
    ) port map (
      clk_i                      => clk_i,
      ramface_ce_i               => ramface_ce_i,
      ramface_rqst_i             => ramface_rqst_i,
      local_ramface_rqst_o       => local_ramface_rqst,
      local_ramface_rqst_en_rd_o => local_ramface_rqst_en_rd,
      local_ramface_rqst_en_wr_o => local_ramface_rqst_en_wr,
      local_ramface_rply_i       => external_mem_rply,
      ramface_rply_o             => rply_to_combine_external_mem(ii)
    );

    vec_ramface_external_mem_rqst_en_rd_o(ii) <= local_ramface_rqst_en_rd;
    vec_ramface_external_mem_rqst_en_wr_o(ii) <= local_ramface_rqst_en_wr;

    external_mem_rqst.en   <=        local_ramface_rqst.en;
    external_mem_rqst.addr <= resize(local_ramface_rqst.addr, EXTERNAL_MEM_ADDR_W);
    external_mem_rqst.wren <= resize(local_ramface_rqst.wren, EXTERNAL_MEM_WREN_W);
    external_mem_rqst.data <= resize(local_ramface_rqst.data, EXTERNAL_MEM_DATA_W);

    vec_ramface_external_mem_rqst_o(ii) <= external_mem_rqst;
    external_mem_rply <= vec_ramface_external_mem_rply_i(ii);

  end generate;

  process(all) -- setting individuial values required to fix Vivado 2025.2 simulation bug
  begin
    rply_to_combine(0) <= rply_to_combine_regs_k;
    rply_to_combine(1) <= rply_to_combine_regs_rw;
    for ii in 0 to TOTAL_EXTERNAL_MEM-1 loop
      rply_to_combine(2+ii) <= rply_to_combine_external_mem(ii);
    end loop;
  end process;

  i_ramface_rply_combine : entity work.ramface_rply_combine
  generic map (
    RAMFACE_DATA_W => RAMFACE_DATA_W,
    WRKR_LEN    => RPLY_TO_COMBINE_LEN,
    LATENCY     => RPLY_TO_COMBINE_LATENCY,
    WRKR_VEC_LATENCY => get_RPLY_TO_COMBINE_WRKR_VEC_LATENCY
  )
  port map (
    clk_i       => clk_i,
    ce_i        => ramface_ce_i,
    wrkr_rply_i => rply_to_combine,
    mstr_rply_o => ramface_rply_o
  );

end architecture;
