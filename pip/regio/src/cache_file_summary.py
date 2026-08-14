import argparse
from pathlib import Path

from regio.cache import RegioCache

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog="skelregio finaly summary",
        description="Print a summary of the cached regions inside the passed skelregio file"
    )
    parser.add_argument(
        'file',
        type=Path,
        help="skelregio file"
    )
    args =  parser.parse_args()

    import argparse

    cache2 = RegioCache()
    cache2.load_from_file(args.file)
    for r in cache2.regions():
        print(f" * addr={hex(r[0])}: size={len(r[1])}")
