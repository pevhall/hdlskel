#!/usr/bin/env python3

from skmap.code_generator_cpp import generate_cpp_module

import argparse
from pathlib import Path

import skmap.code_generator_sw_common as common

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
        "hpp_file",
        type=Path,
        help="Path to .hpp file to generate"
    )
    parser.add_argument(
        "cpp_file",
        type=Path,
        help="Path to .cpp file to generate"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    generate_cpp_module(args.recipe_file, args.hpp_file, args.cpp_file) 

if __name__ == '__main__':
    main()
