
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)

python3 $SCRIPT_DIR/../../../../pip/skmap/src/generate_all_hpp.py $SCRIPT_DIR/include/hdlskel/skmap/autogen_test/
