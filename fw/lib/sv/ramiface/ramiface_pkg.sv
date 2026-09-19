`default_nettype none

package ramiface_pkg;

  class Ramiface # (
    parameter int DATA_W,
    parameter int ADDR_W=32-$clog2(DATA_W/8),
    parameter int WREN_W=DATA_W/8
  );

    typedef struct packed {
      logic vld;
      logic [WREN_W-1] wren;
      logic unsigned [ADDR_W-1] addr;
      logic unsigned [DATA_W-1] data;
    } rqst_t;

    typedef struct packed {
      logic vld;
      logic error;
      logic unsigned [DATA_W-1] data;
    } rply_t;
  endclass

endpackage

`default_nettype wire
