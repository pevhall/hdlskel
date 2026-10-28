#!/usr/bin/env bash
#
# Capture the cached regio images of `test/data` from the simulations.
#
# The images are the input of the hermetic tests (`sw/test/test_skmap_file.sh`,
# the meson / cmake test `skmap_file`, and the python test which checks that an
# image still matches the recipe it was captured with,
# `pip/skmap/tests/test_recipe_checksum.py`). Capture them again when a recipe
# changes:
#
#   bash test/data/capture_images.sh                # both images
#   PORT=39600 bash test/data/capture_images.sh     # other regio port
#
# An image is written with `skmap -t -w`: `-w` only writes what is in the
# cache, `-t` reads the whole tree into it. A tree test bench writes the
# address of the kid modules while the simulation runs, so the capture waits
# until the whole tree answers.
#
# Needs the app (`ninja -C sw/build`) and the simulator of the test benches.
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
ROOT=$(realpath "$SCRIPT_DIR/../..")
PORT="${PORT:-39600}"                  # regio PORT_DEFAULT = 0x9AB0
SKMAP="$ROOT/sw/build/app/skmap/skmap"
LOG=$(mktemp); TREE=$(mktemp)
trap 'rm -f "$LOG" "$TREE"' EXIT

[ -x "$SKMAP" ] || { echo "build the app first: ninja -C $ROOT/sw/build" >&2; exit 1; }

capture() { # <test bench dir> <image file> <modules expected in the tree>
    local tb=$1 out=$2 want=$3 sim pg

    # a leftover simulation (or any other server) would answer instead of the
    # simulation started here, the image would be from another design
    # a leftover simulation (or any other server) would answer instead of the
    # simulation started here, the image would be from another design. The
    # simulation of the previous capture can still be on its way out, wait for
    # the port instead of failing right away.
    for _ in $(seq 1 20); do
        (echo > "/dev/tcp/127.0.0.1/$PORT") 2>/dev/null || break
        sleep 0.5
    done
    if (echo > "/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
        echo "ERROR: something is still listening on 127.0.0.1:$PORT, stop it first" >&2
        exit 1
    fi

    echo "--- $out from $tb ---"
    cd "$ROOT/$tb"
    setsid python3 run.py -s > "$LOG" 2>&1 &
    sim=$!                      # setsid is the leader of its own process group
    pg=$sim
    cd "$ROOT"

    cleanup() {
        [ -n "${pg:-}" ] || return 0
        kill -TERM -- "-$pg" 2>/dev/null || true
        for _ in $(seq 1 10); do
            kill -0 "$sim" 2>/dev/null || return 0
            sleep 0.5
        done
        kill -KILL -- "-$pg" 2>/dev/null || true
    }
    trap cleanup EXIT

    for _ in $(seq 1 240); do
        (echo > "/dev/tcp/127.0.0.1/$PORT") 2>/dev/null && break
        kill -0 "$sim" 2>/dev/null || { echo "simulation died:"; tail -20 "$LOG"; exit 1; }
        sleep 0.5
    done
    (echo > "/dev/tcp/127.0.0.1/$PORT") 2>/dev/null || { echo "server did not come up:"; tail -20 "$LOG"; exit 1; }

    local n=0
    for _ in $(seq 1 60); do
        if "$SKMAP" -p "$PORT" -t > "$TREE" 2>&1; then
            n=$(grep -ac "0x" "$TREE" || true)
            [ "$n" -ge "$want" ] && break
        fi
        sleep 1
    done
    if [ "$n" -lt "$want" ]; then
        echo "ERROR: only $n of $want modules of the tree answered" >&2
        exit 1
    fi

    "$SKMAP" -p "$PORT" -t -w "$ROOT/$out"
    echo "captured $out ($n modules)"
    cleanup
    trap - EXIT
}

capture fw/tb/skmap/tb_py_skmap_tree            test/data/test_tree.skmap   30
capture fw/tb/skmap/tb_py_skmap_module_recipe   test/data/test_recipe.skmap 1
echo DONE
