#!/usr/bin/env python3

import skmap

import sys
import logging
import argparse
from typing import Optional, Sequence

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="skmap-all-hpp",
        description="Create an all.hpp umbrella header that includes every other *.hpp in a directory",
    )
    parser.add_argument(
        "directory",
        nargs="*",
        default=["."],
        help="Directory (or directories) to scan (defaults to current directory)",
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Recurse into sub-directories (include paths stay relative to the scanned directory)",
    )
    parser.add_argument(
        "-x", "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="Glob/name of files or directories to skip (repeatable). all.hpp is always skipped",
    )
    parser.add_argument(
        "-p", "--prefix",
        default="",
        metavar="PATH",
        help="Prefix prepended to every include path (e.g. 'hdlskel/skmap')",
    )
    parser.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="Print the generated all.hpp instead of writing it",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit with status 1 if all.hpp is missing or out of date",
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Rewrite all.hpp even if its content is unchanged",
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

    rc = 0
    for directory in args.directory:
        try:
            _, changed = skmap.generate_all_hpp(
                directory,
                recursive=args.recursive,
                exclude=args.exclude,
                prefix=args.prefix,
                dry_run=args.dry_run or args.check,
                show=args.dry_run,
                force=args.force,
            )
        except (OSError, NotADirectoryError) as e:
            log.error(f"{directory}: {e}")
            return 1
        if args.check and changed:
            log.warning(f"{directory}: {ALL_HPP_NAME} is out of date")
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
