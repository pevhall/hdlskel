SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)

# Regenerate version.hpp from the python skmap version constants
# (single source of truth: pip/skmap/src/skmap/basic_types.py)
python3 $SCRIPT_DIR/../../../../pip/skmap/src/generate_version_hpp.py $SCRIPT_DIR/include/hdlskel/skmap/version.hpp
