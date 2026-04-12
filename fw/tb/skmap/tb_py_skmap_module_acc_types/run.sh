#!/usr/bin/env sh

SCRIPT_DIR=$(realpath -e -- "$(dirname -- "$0")")

mkdir -p $SCRIPT_DIR/build
cd $SCRIPT_DIR/build

TOP=skmap_module_test_acc_types

hdldepends hdldepends.toml --top-entity=$TOP --compile-order-path-only=compile_order.txt

export PYTHONPATH="$PYTHONPATH:$SCRIPT_DIR"

hdlworkflow nvc $TOP compile_order.txt --cocotb=test_skmap_module_test_acc_types $@ --pythonpath=$SCRIPT_DIR -g SKMAP_ID="ABCDEFGH" -g SKMAP_VER_MAJOR=5 -g SKMAP_VER_MINOR=6 -g BASE_ADDR=0 -g RAMFACE_ADDR_W=8 -g RAMFACE_DATA_W=32 -g REGS_VAR_LEN=8
