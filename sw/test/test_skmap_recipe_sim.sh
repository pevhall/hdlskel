#!/usr/bin/env bash
# Run the TUI against a simulated version of the firmware.
#
#   1. start the cocotb testbench (run.py -s): it simulates
#      test_skmap_tree_top with nvc and serves the module over
#      regio TCP (default 127.0.0.1:39600 = 0x9AB0);
#   2. wait until the simulation's server accepts connections;
#   3. run the cpp app
#
# The simulation runs in its own process group; when the app exits
# the whole simulation (run.py + nvc) is killed.
#
# Override the server location with HOST / PORT environment vars:
#   PORT=39600 bash test_skmap_tree_sim.sh
set -euo pipefail

TB_DIR="../../fw/tb/skmap/tb_py_skmap_module_recipe"
HOST="127.0.0.1"
PORT="${PORT:-39600}"   # regio PORT_DEFAULT = 0x9AB0

# --- start the simulation in its own session / process group ---------
cd "$(dirname "$0")"
setsid python3 "$TB_DIR/run.py" -s &
SIM_PID=$!

cleanup() {
    kill -0 "$SIM_PID" 2>/dev/null || return 0
    # kill the whole process group (run.py + nvc + children)
    kill -TERM -- "-$SIM_PID" 2>/dev/null || true
    for _ in $(seq 1 20); do
        kill -0 "$SIM_PID" 2>/dev/null || return 0
        sleep 0.5
    done
    kill -KILL -- "-$SIM_PID" 2>/dev/null || true
}
trap cleanup EXIT

# --- wait for the simulation's regio server port (~60 s max) ---------
echo "waiting for the simulation regio server at $HOST:$PORT ..."
ready=0
for _ in $(seq 1 120); do
    if ! kill -0 "$SIM_PID" 2>/dev/null; then
        echo "ERROR: simulation died while waiting for the server" >&2
        exit 1
    fi
    if (echo > "/dev/tcp/$HOST/$PORT") 2>/dev/null; then
        ready=1
        break
    fi
    sleep 0.5
done
if [ "$ready" -ne 1 ]; then
    echo "ERROR: simulation server did not come up at $HOST:$PORT" >&2
    exit 1
fi
echo "simulation server is up;"

meson compile -C ../build -v
../build/app/skmap/skmap -p $PORT


