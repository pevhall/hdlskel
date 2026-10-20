#!/usr/bin/env bash
# Run the cpp skmap / regio apps against cached regio (.skmap) files.
#
# No simulation is needed: the .skmap files are regio cache dumps, so this is
# a fast, hermetic check of:
#   * the regio cache file reader/writer  (hdlskel/regio/cache.hpp)
#   * -f/--file and --mtu cli options     (mirrors regio/cli_utils.py)
#   * the whole-tree parse when every module is unknown (-x), see
#     Module::make_module(..., allow_unkowen)
#   * the cache file writer               (-w, write_cache_tree_to_file)
#
# The .skmap files were captured from the firmware simulations:
#   cd fw/tb/skmap/tb_py_skmap_module_recipe && python3 -s ./run.py
#   ../sw/build/app/skmap/skmap -m -w test/data/test_recipe.skmap
#   cd fw/tb/skmap/tb_py_skmap_tree && python3 -s ./run.py
#   ../sw/build/app/skmap/skmap -t -m -w test/data/test_tree.skmap
set -euo pipefail

cd "$(dirname "$0")"
BUILD=../build
RECIPE=../../test/data/test_recipe.skmap
TREE=../../test/data/test_tree.skmap

meson compile -C "$BUILD" -v

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

fails=0
check() { # <description> <command...>
    local desc="$1"; shift
    if "$@" > "$TMP/out" 2>&1; then
        echo "PASS: $desc"
    else
        echo "FAIL: $desc"
        sed 's/^/      /' "$TMP/out"
        fails=$((fails+1))
    fi
}
check_has() { # <description> <needle> <file>
    if grep -aq -- "$2" "$3"; then
        echo "PASS: $1"
    else
        echo "FAIL: $1 (missing '$2')"
        sed 's/^/      /' "$3"
        fails=$((fails+1))
    fi
}
check_absent() { # <description> <needle> <file>
    if grep -aq -- "$2" "$3"; then
        echo "FAIL: $1 (unexpected '$2')"
        fails=$((fails+1))
    else
        echo "PASS: $1"
    fi
}

echo "--- regio_op: read from a cache file ---"
SKMAP="$BUILD/app/skmap/skmap"
REGIO="$BUILD/app/regio_op/regio_op"

$REGIO -f "$RECIPE" -a 0 -s 16          > "$TMP/head.txt"
check_has "reads the module id 'TBRecip'"  "0x54, 0x42, 0x52, 0x65" "$TMP/head.txt"

$REGIO -f "$RECIPE" -a 0 -s 16 --mtu 4  > "$TMP/head_mtu.txt"
check "same bytes with --mtu 4" diff -q "$TMP/head.txt" "$TMP/head_mtu.txt"

$REGIO -f "$TREE" -a 0x1000 -s 28 --rd-file "$TMP/kid.bin" > /dev/null
check_has "--rd-file dumps the kid head" "TBTrMod" "$TMP/kid.bin"

echo "--- skmap: recipe module reg map ---"
$SKMAP -f "$RECIPE" -m -s               > "$TMP/recipe.txt"
check_has "reg map printed"             "TBRecip"                   "$TMP/recipe.txt"
check_has "k reg value"                 "RO_LEN"                    "$TMP/recipe.txt"
check_has "external mem rows"           "Mem size:"                 "$TMP/recipe.txt"
check_has "value limits shown"          "-2 <= v <= 100"            "$TMP/recipe.txt"
check_has "asserts listed"              "Asserts (max debug)"       "$TMP/recipe.txt"

echo "--- skmap: whole tree ---"
$SKMAP -f "$TREE" -t                    > "$TMP/tree.txt"
lines=$(grep -ac "test_skmap_tree_module" "$TMP/tree.txt" || true)
if [ "$lines" -eq 30 ]; then
    echo "PASS: tree traversed all 30 modules"
else
    echo "FAIL: expected 30 modules in the tree, got $lines"
    fails=$((fails+1))
fi
check_has "tree uses box drawing"       "┗" "$TMP/tree.txt"

echo "--- skmap: cache file round trip ---"
$SKMAP -f "$TREE"   -t -w "$TMP/tree_out.skmap" > /dev/null
$SKMAP -f "$TMP/tree_out.skmap" -t              > "$TMP/tree2.txt"
check "written file re-reads identically" diff -q "$TMP/tree.txt" "$TMP/tree2.txt"

$SKMAP -f "$RECIPE" -m -s -w "$TMP/recipe_out.skmap" > /dev/null
$SKMAP -f "$TMP/recipe_out.skmap" -m -s              > "$TMP/recipe2.txt"
check "recipe written file re-reads identically" diff -q "$TMP/recipe.txt" "$TMP/recipe2.txt"

echo "--- skmap: unknown modules ---"
# Every module in these files is registered by the autogen library, so make a
# copy whose module id nothing knows about. Without -x the app must fail; with
# -x it must parse the whole tree as ModuleUnknown (allow_unkowen propagates
# from the top level module to every kid).
python3 - "$TREE" "$TMP/unknown_tree.skmap" <<'PY'
import sys
data = open(sys.argv[1], 'rb').read()
assert data.count(b'TBTrMod\x00') == 30, data.count(b'TBTrMod\x00')
open(sys.argv[2], 'wb').write(data.replace(b'TBTrMod\x00', b'TBTuMod\x00'))
PY

if $SKMAP -f "$TMP/unknown_tree.skmap" -t > "$TMP/unk_nox.txt" 2>&1; then
    echo "FAIL: expected an error for unknown modules without -x"
    fails=$((fails+1))
else
    echo "PASS: unknown modules rejected without -x"
fi

$SKMAP -f "$TMP/unknown_tree.skmap" -t -x  > "$TMP/unk_x.txt" 2>/dev/null
unk=$(grep -ac "ModuleUnknown" "$TMP/unk_x.txt" || true)
if [ "$unk" -eq 30 ]; then
    echo "PASS: -x parsed all 30 unknown modules"
else
    echo "FAIL: expected 30 unknown modules, got $unk"
    fails=$((fails+1))
fi

# Every unknown module still gets a generic register map.
$SKMAP -f "$TMP/unknown_tree.skmap" -x -m  > "$TMP/unk_map.txt" 2>/dev/null
check_has "unknown module reg map" "Unkowen_var\[0\]" "$TMP/unk_map.txt"

echo
echo "--- error handling ---"
# A read of an address that was never captured must fail cleanly (exit 1,
# not an uncaught exception).
if $SKMAP -f "$RECIPE" -a 0x8000 -m > "$TMP/bad.txt" 2>&1; then
    echo "FAIL: expected an error for an unmapped address"
    fails=$((fails+1))
elif grep -aq -- "Error:" "$TMP/bad.txt"; then
    echo "PASS: unmapped address reports an error"
else
    echo "FAIL: unmapped address did not report an error"
    fails=$((fails+1))
fi

echo
if [ "$fails" -ne 0 ]; then
    echo "$fails FAILURES"
    exit 1
fi
echo "ALL PASSED"
