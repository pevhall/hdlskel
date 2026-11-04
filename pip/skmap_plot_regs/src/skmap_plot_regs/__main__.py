"""Allow `python -m skmap_plot_regs` (or `python3 __main__.py` from this dir)."""

try:
    from skmap_plot_regs.app import main
except ImportError:  # running the script directly, package not installed
    from app import main  # type: ignore

if __name__ == "__main__":
    main()
