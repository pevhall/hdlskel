#!/usr/bin/env python3

import argparse
from pathlib import Path

from skmap.code_generator_parse_recipe import parse_recipe_file


def parse_args():
    parser = argparse.ArgumentParser(
        description="Parse a skmap module recipe file and generate skmap module"
    )
    parser.add_argument(
        "file",
        type=Path,
        help="Path to skmap recipe file"
    )
    return parser.parse_args()

if __name__ == '__main__':

    args = parse_args()
    parse_recipe_file(args.file)

