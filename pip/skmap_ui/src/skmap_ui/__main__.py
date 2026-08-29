"""Allow `python -m skmap_ui` (or `python3 __main__.py` from this dir)."""

try:
    from skmap_ui.app import main
except ImportError:  # running the script directly, package not installed
    from app import main  # type: ignore

if __name__ == "__main__":
    main()
