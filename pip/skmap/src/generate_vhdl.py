#!/usr/bin/env python3

import argparse
from pathlib import Path
from datetime import datetime
from typing import Literal

from skmap.code_generator_vhdl import generate_vhdl_module

def parse_args():
    parser = argparse.ArgumentParser(
        description="Parse a skmap module recipe file and generate skmap module"
    )
    parser.add_argument(
        "recipe_file",
        type=Path,
        help="Path to skmap recipe file"
    )
    parser.add_argument(
        "vhdl_file",
        type=Path,
        help="Path to VHDL file to generate"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    generate_vhdl_module(args.recipe_file, args.vhdl_file) 

if __name__ == '__main__':
    main()
