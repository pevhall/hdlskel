#!/usr/bin/env bash
# Run the TUI against a simulated version of the firmware.
#
#   1. start the cocotb testbench (run.py -s): it simulates
#      test_skmap_tree_top with nvc and serves the module over
#      regio TCP (default 127.0.0.1:39600 = 0x9AB0);
#   2. wait until the simulation's server accepts connections;
#   3. run the skmap_ui TUI against the live server.  Every trigger
#      ('t') and edit (enter) does real, *non-cached* regio reads /
#      writes against the simulation, so the register map always
#      shows the device state.
#
# The simulation runs in its own process group; when the TUI exits
# (Ctrl+Q) the whole simulation (run.py + nvc) is killed.
#
# Override the server location with HOST / PORT environment vars:
#   HOST=127.0.0.1 PORT=39600 bash demo_skmap_tree_sim.sh
# Extra args for the TUI (CI uses --smoke: start, wait for the assert check,
# print the result and exit, no terminal needed):
#   SKMAP_UI_ARGS="--smoke" bash demo_skmap_tree_sim.sh
# any other argument reaches the TUI as well (bash demo_skmap_tree_sim.sh --smoke)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

TB_DIR="../../../fw/tb/skmap/tb_py_skmap_tree"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-39600}"   # regio PORT_DEFAULT = 0x9AB0
REG_MODULE="$TB_DIR/test_skmap_tree_module.py"

# --- the simulation port has to be free before anything is started -----
# A leftover simulation (for instance of the previous run of this demo) would
# answer instead of the one started here, the TUI would then talk to another
# design.  A process of the previous run can still be on its way out, wait for
# the port instead of failing right away.
for _ in $(seq 1 20); do
    (echo > "/dev/tcp/$HOST/$PORT") 2>/dev/null && { sleep 0.5; continue; }
    break
done
if (echo > "/dev/tcp/$HOST/$PORT") 2>/dev/null; then
    echo "ERROR: something is still listening on $HOST:$PORT (the simulation regio server port), stop it first" >&2
    exit 1
fi

# --- start the simulation in its own session / process group ---------
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
        echo "ERROR: simulation died while waiting for the server, its output above says why" >&2
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
echo "simulation server is up; starting TUI (Ctrl+Q to quit)"

# no exec: the EXIT trap must fire to clean up the simulation
# find the skmap_ui package next to this directory, no install needed
export PYTHONPATH="$(cd "$(dirname "$0")/../src" && pwd)${PYTHONPATH:+:$PYTHONPATH}"
SKMAP_UI_ARGS="${SKMAP_UI_ARGS:-}"
python3 -m skmap_ui -i "$HOST" -p "$PORT" -I "$REG_MODULE" $SKMAP_UI_ARGS "$@"
