#!/usr/bin/env python3
import sys
import tomllib

import argparse
from pathlib import Path
import sys

def parse_recipe(file : Path):
    with open(file, "rb") as toml_f:
        d = tomllib.load(toml_f)
        # from pprint import pprint
        # pprint(d)



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
    parse_recipe(args.file)

