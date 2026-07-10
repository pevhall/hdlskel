#!/usr/bin/env sh

SCRIPT_DIR=$(realpath -e -- "$(dirname -- "$0")")

mkdir -p $SCRIPT_DIR/build
cd $SCRIPT_DIR/build

TOP=test_skmap_tree_top

hdldepends hdldepends.toml --top-entity=$TOP --compile-order-path-only=compile_order.txt

export PYTHONPATH="$PYTHONPATH:$SCRIPT_DIR"
# hdlworkflow nvc $TOP compile_order.txt --cocotb=test_skmap_module_recipe $@ --pythonpath=$SCRIPT_DIR -g BASE_ADDR=0 -g RAMFACE_ADDR_W=8 -g RAMFACE_DATA_W=32 -g RO_LEN=3 -g RO_VAL_W=3 -g RW_LEN=5 -g RW_VAL_W=17 -g FLAGK1=false -g FLAGK2=true
hdlworkflow nvc $TOP compile_order.txt --cocotb=test_skmap_tree $@ --pythonpath=$SCRIPT_DIR -g RAMFACE_ADDR_W=30 -g RAMFACE_DATA_W=32 -g SKMAP_BYTE_ALIGN=1 -g TREE_DEPTH=6 -g TREE_WIDTH=5 # -g TREE_DEPTH=6 -g TREE_WIDTH=3
