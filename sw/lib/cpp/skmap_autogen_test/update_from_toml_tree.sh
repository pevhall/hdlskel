SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)


ROOT=$SCRIPT_DIR/../../../..
$ROOT/pip/skmap/src/generate_cpp.py $ROOT/fw/tb/skmap/tb_py_skmap_tree/test_skmap_tree_module.toml $SCRIPT_DIR/include/hdlskel/skmap/autogen_test/test_skmap_tree_module.hpp $SCRIPT_DIR/src/test_skmap_tree_module.cpp
