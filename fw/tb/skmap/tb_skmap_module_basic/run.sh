#!/usr/bin/env sh

hdldepends hdldepends.toml --top-file ./tb_skmap_module_basic.vhd --compile-order-path-only ./compile_order.txt
hdlworkflow nvc tb_skmap_module_basic compile_order.txt --gui --wave gtkwave --stop-time 1 us
