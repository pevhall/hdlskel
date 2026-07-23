#!/usr/bin/env python3

import argparse
from pathlib import Path

from skmap.code_generator_py import generate_py_module

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
        "py_file",
        type=Path,
        help="Path to Python file to generate"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    generate_py_module(args.recipe_file, args.py_file) 

if __name__ == '__main__':
    main()
