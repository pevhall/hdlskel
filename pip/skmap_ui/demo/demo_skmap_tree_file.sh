#!/usr/bin/env bash
# Smoke test: build the module tree from the tree.skmap cache file and
# run the TUI against it.
#
#   bash demo_skmap_tree_file.sh            # interactive TUI
#   bash demo_skmap_tree_file.sh --smoke    # headless smoke test (exits 0)
#   SKMAP_UI_ARGS="--smoke" bash demo_skmap_tree_file.sh   # the same, CI style
#
# tree.skmap and test_skmap_tree_module.py are symlinks (in this demo/
# directory) into the tb; the module .py must be imported (-I) so its
# class is registered before make_module() runs.  tree.skmap points at
# the cache the tree testbench writes
# (tb_py_skmap_tree/build/nvc/skmap_tree_cache.skelregio), so build that
# testbench once (run.py) before running this.
set -euo pipefail
cd "$(dirname "$0")"
# find the skmap_ui package next to this directory, no install needed
export PYTHONPATH="$(cd ../src && pwd)${PYTHONPATH:+:$PYTHONPATH}"
SKMAP_UI_ARGS="${SKMAP_UI_ARGS:-}"
exec python3 -m skmap_ui -f tree.skmap -I test_skmap_tree_module.py $SKMAP_UI_ARGS "$@"
