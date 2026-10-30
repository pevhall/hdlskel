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
# Where the built apps are: the meson build dir by default, HDSKEL_BUILD_DIR
# points at another one (the cmake test sets it to its own build dir, the
# layout of the binaries below it is the same: app/skmap, app/regio_op, test)
BUILD="${HDSKEL_BUILD_DIR:-../build}"
RECIPE=../../test/data/test_recipe.skmap
TREE=../../test/data/test_tree.skmap

# rebuild first when $BUILD is a meson build dir (ctest / a plain run of this
# script from another build dir builds the binaries itself, nothing to do)
[ -f "$BUILD/build.ninja" ] && meson compile -C "$BUILD" -v
for app in "$BUILD/app/skmap/skmap" "$BUILD/app/regio_op/regio_op" "$BUILD/test/test_skmap_check"; do
    [ -x "$app" ] || { echo "FAIL: $app is not built (HDSKEL_BUILD_DIR=$BUILD)"; exit 1; }
done

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
# Same as check_has, but the needle is a fixed string (the printed check
# expressions are full of ( ) * characters that would be regex syntax)
check_has_f() { # <description> <needle> <file>
    if grep -aqF -- "$2" "$3"; then
        echo "PASS: $1"
    else
        echo "FAIL: $1 (missing '$2')"
        sed 's/^/      /' "$3"
        fails=$((fails+1))
    fi
}

# Fixed string version of check_absent
check_absent_f() { # <description> <needle> <file>
    if grep -aqF -- "$2" "$3"; then
        echo "FAIL: $1 (unexpected '$2')"
        fails=$((fails+1))
    else
        echo "PASS: $1"
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
# The recipe v_check of regs_rw, printed with every recipe name resolved to a
# value (the recipe is not needed to print a module): min / max of the register
# value are replaced by the v_check of the value of the module user
check_has_f "v_check of regs_rw shown"  "(((v >= (-1 * 2)) && (v <= 100)) && ((v % 2) == 0))" "$TMP/recipe.txt"
# temp has a v_convert_wr, the map shows the value of the module user (a float),
# not the raw value of the register
check_has_f "v_convert_wr prints the user value" "((v >= -1000) && (v <= (10 * 32))) -4.25" "$TMP/recipe.txt"
# the description of a reg with a value conversion starts with it (like
# the python reg map), the marker is not printed anywhere else, the k
# parameter RO_VAL_W (12) is resolved in the marker
check_has_f "value conversion in the description" "={ v * 12 } Temp, float scale" "$TMP/recipe.txt"
check_absent_f "no marker for a reg without a conversion" "={ v * 12 } RW registers" "$TMP/recipe.txt"
# RW_LEN has v_check="{ (v % RW_MULT) == 0}" and the firmware value 3 is odd, so
# the worst assert of the module is the error of that failed check
check_has "asserts listed"              "Asserts (max error)"       "$TMP/recipe.txt"
check_has "failing check in assert table" "RW_LEN"                  "$TMP/recipe.txt"
check_has_f "failing check shows its expression" "((v % 2) == 0) 3"  "$TMP/recipe.txt"

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
# -x it must parse the whole tree as unknown modules (allow_unkowen propagates
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
# Unknown modules print as "Unkowen" (same name python uses)
unk=$(grep -acE "Unkowen \{" "$TMP/unk_x.txt" || true)
if [ "$unk" -eq 30 ]; then
    echo "PASS: -x parsed all 30 unknown modules"
else
    echo "FAIL: expected 30 unknown modules, got $unk"
    fails=$((fails+1))
fi

# Every unknown module still gets a generic register map.
$SKMAP -f "$TMP/unknown_tree.skmap" -x -m  > "$TMP/unk_map.txt" 2>/dev/null
check_has "unknown module reg map" "UNKOWN_VAR_0" "$TMP/unk_map.txt"
check_has "unknown module reg map" "UNKOWN_K_0" "$TMP/unk_map.txt"

echo
echo "--- skmap: clearing read clear registers ---"
# -c writes zeros to every `read clear` register. The cleared tree must
# re-read with the rc registers at zero and the other registers untouched
# (this is the write cache -> regio -> file path).
$SKMAP -f "$RECIPE" -c -w "$TMP/cleared.skmap"     > /dev/null 2>&1
$SKMAP -f "$TMP/cleared.skmap" -m                  > "$TMP/cleared.txt"
check_has "rc flags cleared"             "flags.*0b00000000" "$TMP/cleared.txt"
check_has "rc vector cleared"            "regs_rc.*\[ 0, 0, 0 \]" "$TMP/cleared.txt"
check_has "constants untouched by clear" "RO_LEN.*3" "$TMP/cleared.txt"
check_has "read only registers untouched" "regs_ro.*debug: \[ 0, 1, 2 \]" "$TMP/cleared.txt"

echo
echo "--- skmap: python output parity ---"
# The cpp printing mirrors the python library: `0xADDR name {id, vN, c=XXXX
# l=..}` with a zero padded upper case checksum, and python spelling for
# bools. Column widths and the box drawing differ (tabulate vs rich).
check_has "upper case checksum in info line" "c=C805" "$TMP/tree.txt"
check_has "bools print as python True"       "True" "$TMP/recipe.txt"
check_has "bools print as python False"      "False" "$TMP/recipe.txt"
check_has "value types print like python"    "\[3\]s12" "$TMP/recipe.txt"
check_has "flags value type like python"     "b21" "$TMP/recipe.txt"

echo
echo "--- skmap: -v logging ---"
# Mirrors python's `--verbose` levels: warnings by default, info with -v.
$SKMAP -f "$RECIPE" -m                             > "$TMP/quiet.txt" 2>&1
$SKMAP -f "$RECIPE" -m -vv                         > "$TMP/vv.txt" 2>&1
check_absent "no info logging without -v" "Creating module" "$TMP/quiet.txt"
check_has    "info logging with -vv"      "Creating module" "$TMP/vv.txt"

echo
echo "--- skmap: recipe value check (C++ unit test) ---"
# The recipe v_check / v_convert_wr / v_convert_rd options (ValueCheck / ValueConvert):
# a failing check is an assert when reading and rejects a write, v_convert_wr
# written value and every read. Also runnable with `meson test -C build`.
check "v_check / v_convert_wr unit test" "$BUILD/test/test_skmap_check" "$RECIPE"

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
