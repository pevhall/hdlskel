SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)


ROOT=$SCRIPT_DIR/../../../..
$ROOT/pip/skmap/src/generate_cpp.py $ROOT/fw/tb/skmap/tb_py_skmap_module_recipe/recipe_test_bench_module.toml $SCRIPT_DIR/include/hdlskel/skmap/autogen_test/recipe_test_bench_module.hpp $SCRIPT_DIR/src/recipe_test_bench_module.cpp
