#!/usr/bin/env bash
# Demo: skmap_ui (TUI) and skmap_plot_regs (pyqtgraph, command line
# application) on the same simulated skmap module — edit a register in
# the TUI, watch the plot. For the same plot driven through the
# SkmapPlotRegs class see demo_skmap_plot_regs_sim_class.sh.
#
#   1. the cocotb testbench (run.py -s) simulates the recipe test
#      bench module and serves its ramface over regio TCP; that
#      server takes only ONE client, so a proxy is used:
#   2. regio_proxy_headless.py (the network layer of regio_ui, no
#      TUI) exposes the simulation on PROXY_PORT to any number of
#      clients;
#   3. skmap_plot_regs is started in the background, plotting
#      `temp` and every lane of `regs_rw` (both RW, exactly what the
#      TUI edits) sampled every second;
#   4. the skmap_ui TUI runs in the FOREGROUND on the same proxy
#      port: move to a register, press enter, type a new value — the
#      plot curve moves with it (Ctrl+C the plot to close it later).
#
# Quitting the TUI stops everything (the EXIT trap kills the whole
# process group of every child).
#
# NOTE on the regio_ui TUI: instead of the headless proxy the full
# regio_ui TUI can relay the same traffic (`python3 -m regio_ui -p
# $SIM_PORT --listen-port $PROXY_PORT`, its own terminal window) and
# logs every operation the two clients do. Serving a *cache file*
# there (-f build/nvc/module_recipe.skmap) is NOT equivalent: the
# cache is a snapshot (it goes stale, see the module head checksum)
# and writes would never reach the simulation.
#
# Environment overrides:
#   HOST=127.0.0.1 SIM_PORT=39600 PROXY_PORT=39601 PLOT_REGS="temp regs_rw" \
#       bash demo_skmap_plot_regs_sim_cli.sh
#   SKMAP_UI_ARGS="--smoke"   extra args for the TUI (--smoke: headless,
#                             start, check the asserts and exit; used by CI)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="$SCRIPT_DIR/../src"                        # skmap_plot_regs (this project)
SKMAP_UI_SRC_DIR="$SCRIPT_DIR/../../skmap_ui/src"   # skmap_ui TUI (foreground)
REGIO_SRC_DIR="$SCRIPT_DIR/../../regio/src"   # regio_proxy_headless.py lives in the regio project
cd "$SCRIPT_DIR"

TB_DIR="../../../fw/tb/skmap/tb_py_skmap_module_recipe"
REG_MODULE="$TB_DIR/recipe_test_bench_module.py"
HOST="${HOST:-127.0.0.1}"
SIM_PORT="${SIM_PORT:-39600}"     # regio PORT_DEFAULT = 0x9AB0
PROXY_PORT="${PROXY_PORT:-39601}"
PLOT_REGS="${PLOT_REGS:-temp regs_rw}"   # registers the plot samples

# find skmap_plot_regs and skmap_ui next to their src/ directories even
# without an install (the plot runs as `python3 -m skmap_plot_regs`)
export PYTHONPATH="$SRC_DIR:$SKMAP_UI_SRC_DIR${PYTHONPATH:+:$PYTHONPATH}"

# --- both ports have to be free before anything is started -----------
# a leftover simulation or proxy (for instance of the previous run of this
# demo) would answer instead of the ones started here, the plot and the TUI
# would then talk to another design. A process of the previous run can still
# be on its way out, wait for the port instead of failing right away.
require_free_port() { # <port> <what should be on it>
    local port="$1" what="$2"
    for _ in $(seq 1 20); do
        (echo > "/dev/tcp/$HOST/$port") 2>/dev/null && { sleep 0.5; continue; }
        return 0
    done
    echo "ERROR: something is still listening on $HOST:$port ($what), stop it first" >&2
    exit 1
}
require_free_port "$SIM_PORT"   "the simulation regio server port"
require_free_port "$PROXY_PORT" "the regio proxy port"

# --- start the simulation in its own session / process group ---------
setsid python3 "$TB_DIR/run.py" -s &
SIM_PID=$!

# --- start the headless regio proxy (simulation -> many clients) -----
setsid python3 "$REGIO_SRC_DIR/regio_proxy_headless.py" -i "$HOST" -p "$SIM_PORT" \
    --listen-port "$PROXY_PORT" &
PROXY_PID=$!

PLOT_PID=""   # set once the proxy is up, see below

cleanup() {
    # kill every child (run.py + nvc, the proxy and the plot) by their
    # process groups, TERM first, then KILL for what survives
    local pid any_up
    for pid in "$PLOT_PID" "$PROXY_PID" "$SIM_PID"; do
        [ -n "$pid" ] || continue
        kill -0 "$pid" 2>/dev/null || continue
        kill -TERM -- "-$pid" 2>/dev/null || true
    done
    for _ in $(seq 1 10); do
        any_up=0
        for pid in "$PLOT_PID" "$PROXY_PID" "$SIM_PID"; do
            if kill -0 "$pid" 2>/dev/null; then any_up=1; fi
        done
        [ "$any_up" -eq 0 ] && return 0
        sleep 0.5
    done
    for pid in "$PLOT_PID" "$PROXY_PID" "$SIM_PID"; do
        if kill -0 "$pid" 2>/dev/null; then kill -KILL -- "-$pid" 2>/dev/null || true; fi
    done
    return 0
}
trap cleanup EXIT

# --- wait for a tcp port, the pid of the process that must provide it -
wait_for_port() {
    local pid="$1" port="$2" desc="$3"
    for _ in $(seq 1 120); do
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "ERROR: $desc died while waiting for $HOST:$port" >&2
            exit 1
        fi
        if (echo > "/dev/tcp/$HOST/$port") 2>/dev/null; then
            return 0
        fi
        sleep 0.5
    done
    echo "ERROR: $desc did not open $HOST:$port" >&2
    exit 1
}

echo "waiting for the simulation regio server at $HOST:$SIM_PORT ..."
wait_for_port "$SIM_PID" "$SIM_PORT" "simulation"
echo "waiting for the regio proxy at $HOST:$PROXY_PORT ..."
wait_for_port "$PROXY_PID" "$PROXY_PORT" "regio proxy"

# --- start the register plot only once the proxy accepts clients ------
setsid python3 -m skmap_plot_regs -i "$HOST" -p "$PROXY_PORT" \
    -I "$REG_MODULE" 0 $PLOT_REGS &
PLOT_PID=$!
# give the plot a moment to connect and make its first samples
sleep 2
if ! kill -0 "$PLOT_PID" 2>/dev/null; then
    echo "ERROR: the register plot exited early, see its output above" >&2
    exit 1
fi

echo "simulation, proxy and plot are up; TUI: edit a value with enter and"
echo "watch the plot window (Ctrl+Q quits the TUI and stops everything)"

# no exec: the EXIT trap must fire to clean up the children
SKMAP_UI_ARGS="${SKMAP_UI_ARGS:-}"
python3 -m skmap_ui -i "$HOST" -p "$PROXY_PORT" -I "$REG_MODULE" $SKMAP_UI_ARGS
