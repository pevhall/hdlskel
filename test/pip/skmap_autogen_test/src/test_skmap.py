import asyncio

import skmap.cli_utils

import skmap_autogen_test.recipe_test_bench_module
import skmap_autogen_test.test_skmap_tree_module



def main():
    args = skmap.cli_utils.parse_args()
    asyncio.run(skmap.cli_utils.main(args))

if __name__ == '__main__':
    main()
