#!/usr/bin/env bash
# Smoke test: build the module tree from the tree.skmap cache file and
# run the TUI against it.
#
#   bash test.sh            # interactive TUI
#   bash test.sh --smoke    # headless smoke test (exits 0 on success)
#
# tree.skmap and test_skmap_tree_module.py are symlinks into the
# generated tb/ directory; the module .py must be imported (-m) so its
# class is registered before make_module() runs.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 ./__main__.py -f tree.skmap -m test_skmap_tree_module.py "$@"
