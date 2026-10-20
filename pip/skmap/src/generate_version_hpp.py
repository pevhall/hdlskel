#!/usr/bin/env python3

import skmap

import sys
import logging
import argparse
from pathlib import Path
from typing import Optional, Sequence

log = logging.getLogger(__name__)

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="skmap-version-hpp",
        description=(
            "Generate the C++ version.hpp from the python skmap version constants "
            "(single source of truth: skmap.basic_types)"
        ),
    )
    parser.add_argument(
        "hpp_file",
        type=Path,
        help=f"Path of the {skmap.code_generator_version_hpp.VERSION_HPP_NAME} to generate",
    )
    parser.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="Do not write; report whether the file would change",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit with status 1 if version.hpp is missing or out of date",
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Rewrite version.hpp even if its content is unchanged",
    )
    parser.add_argument(
        "-v",
        dest="verbose",
        action="count",
        default=0,
        help="Increase logging verbosity (repeat up to -vv)",
    )
    return parser.parse_args(argv)

def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    level = logging.WARNING
    if args.verbose == 1:
        level = logging.INFO
    elif args.verbose >= 2:
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    dry_run = args.dry_run or args.check
    changed = skmap.generate_version_hpp(
        args.hpp_file,
        dry_run = dry_run,
        show    = args.dry_run,
        force   = args.force,
    )
    if args.check and changed:
        log.warning("%s is out of date", args.hpp_file)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
