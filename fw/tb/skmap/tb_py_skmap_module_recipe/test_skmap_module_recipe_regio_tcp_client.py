#!/usr/bin/env python

import asyncio
import skmap
import regio.tcp_client
from recipe_test_bench_module import RecipeTestBenchModule


async def main():
    regio_tcp = regio.tcp_client.RegioTcpClient()
    module = await skmap.make_Module(regio_tcp, 0)
    assert isinstance(module, RecipeTestBenchModule)

    if 1:
        RW_LEN = module.regs_rw_value_type.vec_len 
        RW_VAL_W = module.regs_rw_value_type.width 
        assert RW_LEN is not None
        for ii in range(RW_LEN):
            await module.regs_rw_write_idx(ii,ii+0xA0)
            # await module.regs_rw_write_idx(ii,(1<<RW_VAL_W)-1)
        print(f'{module.regs_rw_cached()=}')
        print(f'{await module.regs_rw_read()=}')
        print(f'{await module.regs_ro_read()=}')
    await module.regs_wt_trigger(0x1F)

    print(f'{await module.regs_rw_read()=}')
    await module.read_cache_all()
    print(f'{await module.regs_rw_read()=}')
    module.reg_map_print()
    await module.write_zero_all_rc()
    module.reg_map_print()

if __name__ == '__main__':
    asyncio.run(main())

