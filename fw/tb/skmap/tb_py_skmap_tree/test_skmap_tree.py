import ast
import asyncio
import cocotb
import tbskel.ramface
import regio.tcp_server
from regio import cache as regio_cache
import skmap
import logging

from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from test_skmap_tree_module import TestSkmapTreeModule


@cocotb.test()
async def test_skmap_module_test_acc_types(dut):
    run_server = cocotb.plusargs.get("run_server")
    assert isinstance(run_server, str)
    run_server = ast.literal_eval(run_server)
    print(f"{run_server=}")

    dut.ramface_ce_i.value = 1

    cocotb.start_soon(Clock(dut.clk_i, 1, unit="ns").start())

    ramface_ctrl = tbskel.ramface.make_RamfaceCtrlBytes_default_ports(dut)
    await RisingEdge(dut.clk_i)

    logging.basicConfig(level=logging.DEBUG)
    # await skmap.Module.read_init_module_data(ramface_ctrl, 0)
    for _ in range(0):
        await RisingEdge(dut.clk_i)

    if 1:
        print(f'{dut.RAMFACE_LATENCY=}')
        print('creating module')
        module = await skmap.make_module(ramface_ctrl, 0, allow_unknowen=False)
        assert isinstance(module, TestSkmapTreeModule)
        await module.make_tree()
        module.print_reg_map_cached()
        module.print_tree_cached()
        module_top = module
        module_depth = []
        while(module is not None):
            module_depth.append(module)
            k = module.kids_with_class_cached(TestSkmapTreeModule)
            if len(k) != 0:
                module = k[0]
            else:
                module = None
        module_width = module_depth[-2].kids_cached()
        print(f'{len(module_depth)=}')
        print(f'{len(module_width)=}')
        ass = module_top.check_assert_cached()
        assert ass == skmap.Ass.passed
        m = module_depth[-1]
        await m.trigger_flags_write_trigger((1<<m.trigger_flags_inst.value_type.width)-1)
        await module_top.read_cache_tree()

        flags = []
        ass = module_top.check_assert_tree_cached(skmap.Ass.debug, flags)
        print(f'{ass=}, {len(flags)=}')
        skmap.print_table_flags(flags, title='Triggered Asserts')
        await module_top.clear_assert_tree()
        flags = []
        ass = module_top.check_assert_tree_cached(skmap.Ass.debug, flags)
        print(f'{ass=}, {len(flags)=}')

        cache_path = f'skmap_tree_cache.{regio_cache.FILE_EXTENSION}'
        module_top.write_cache_tree_to_file(cache_path)

        r_cache = regio_cache.RegioCache()
        r_cache.load_from_file(cache_path)
        print("reloaded:", r_cache.regions())



    # server = regio.tcp_server.RegioTcpServer(ramface_ctrl)
    # await server.start()

    if run_server:
        server = regio.tcp_server.RegioTcpServer(ramface_ctrl)
        await server.start()

    for _ in range(100):
        await RisingEdge(dut.clk_i)


    # await Timer(50, unit="ns")  # wait a bit
    # await FallingEdge(dut.clk_i)  # wait for falling edge/"negedge"

    assert True

