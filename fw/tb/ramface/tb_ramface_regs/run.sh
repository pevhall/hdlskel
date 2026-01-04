#!/usr/bin/env sh

hdldepends hdldepends.toml --top-file ./tb_ramface_regs.vhd --compile-order-path-only ./compile_order.txt
hdlworkflow nvc tb_ramface_regs compile_order.txt --gui --wave gtkwave --stop-time 1 us
