#!/usr/bin/env sh

cd "$(dirname "$0")" || exit 1

hdldepends hdldepends.toml --top-file ./tb_ramface_regs.vhd -o compile-order-paths ./compile_order.txt
hdlworkflow nvc tb_ramface_regs compile_order.txt --gui --wave gtkwave --stop-time 1 us
