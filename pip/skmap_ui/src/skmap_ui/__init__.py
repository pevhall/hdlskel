"""skmap_ui — textual TUI for browsing skmap module register maps.

The app takes a real ``skmap.Module`` and shows:

- a **tree view** of the module tree (like ``print_tree_cached``)
- a **register map table** for the selected module
  (like ``print_reg_map_cached``)
- a **log view** of triggered register assets (asserts) from
  ``check_assert_tree_cached``

Run the built-in demo::

    skmap-ui          # console script
    python -m skmap_ui

Or a module from a skelregi cache file (see ``test.sh``)::

    skmap-ui -f tree.skmap -m test_skmap_tree_module.py

Or your own module::

    from skmap import make_module
    from skmap_ui import SkmapUiApp

    module = await make_module(regio, addr)
    SkmapUiApp(module).run()
"""

__version__ = "0.6.1"

from skmap_ui.app import SkmapUiApp, main

__all__ = ["SkmapUiApp", "main", "__version__"]
