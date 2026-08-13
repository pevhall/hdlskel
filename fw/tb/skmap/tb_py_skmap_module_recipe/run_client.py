import asyncio

import skmap
import skmap.cli_utils

import recipe_test_bench_module

if __name__ == '__main__':
    args = skmap.cli_utils.parse_args()
    asyncio.run(skmap.cli_utils.main(args))

