import sys
import ast
import asyncio
import cocotb
import tbskel.ramface
import regio.tcp_server
import skmap
import logging

from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from recipe_test_bench_module import RecipeTestBenchModule




async def reg_loopback(dut):
    while True:
        await RisingEdge(dut.clk_i)
        if dut.regs_wt_trigger_o.value != 0:
            wt = int(dut.regs_wt_o.value)
            dut.debug_flag0_i.value = (wt>>0)&1
            dut.info_flag1_i.value  = (wt>>1)&1
            dut.warn_flag2_i.value  = (wt>>2)&1
            dut.error_flag3_i.value = (wt>>3)&1
            dut.fatal_flag4_i.value = (wt>>4)&1
            await RisingEdge(dut.clk_i)
            dut.debug_flag0_i.value = 0
            dut.info_flag1_i.value  = 0
            dut.warn_flag2_i.value  = 0
            dut.error_flag3_i.value = 0
            dut.fatal_flag4_i.value = 0
            # dut.flag0_i.value = 0
            # dut.flag1_i.value = 0
            # dut.flag2_i.value = 0
            # dut.flag3_i.value = 0
            # dut.flag4_i.value = 0

            # print(f'{dut.flag0_i.value=}')
            # print(f'{dut.flag1_i.value=}')
            # print(f'{dut.flag2_i.value=}')
            # print(f'{dut.flag3_i.value=}')
            # print(f'{dut.flag4_i.value=}')
        # dut.regs_ro_i.value = dut.regs_rw_o.value
        # dut.regs_ro_i.value = dut.regs_rw_o.value


@cocotb.test()
async def test_skmap_module_test_acc_types(dut):
    logging.basicConfig(level=logging.DEBUG,stream=sys.stderr,force=True)
    run_server = cocotb.plusargs.get("run_server")
    assert isinstance(run_server, str)
    run_server = ast.literal_eval(run_server)
    print(f"{run_server=}")

    dut.reg_s_rc_i.value = 0

    dut.ramface_ce_i.value = 1

    for ii in range(dut.RO_LEN.value):
        dut.regs_ro_i[ii].value = ii
    dut.debug_flag0_i.value = 0
    dut.info_flag1_i.value = 0
    dut.warn_flag2_i.value = 0
    dut.error_flag3_i.value = 0
    dut.fatal_flag4_i.value = 0
    dut.debug_flag_vec_i.value = 0
    for ii in range(dut.RW_LEN.value):
        dut.regs_rc_i[ii].value = 0
    cocotb.start_soon(Clock(dut.clk_i, 1, unit="ns").start())
    cocotb.start_soon(reg_loopback(dut))

    ramface_ctrl = tbskel.ramface.make_RamfaceCtrlBytes_default_ports(dut)
    await RisingEdge(dut.clk_i)

    logging.basicConfig(level=logging.DEBUG)
    # await skmap.Module.read_init_module_data(ramface_ctrl, 0)
    module = await skmap.make_module(ramface_ctrl, 0)
    assert isinstance(module, RecipeTestBenchModule)
    if 1:
        RW_LEN   = module.regs_rw_inst.value_type.vec_len 
        RW_VAL_W = module.regs_rw_inst.value_type.width 
        # RW_LEN = module.regs_rw_value_type.vec_len 
        # RW_VAL_W = module.regs_rw_value_type.width 
        assert RW_LEN is not None
        for ii in range(RW_LEN):
            await module.regs_rw_write_idx(ii,ii+0xA0)
            # await module.regs_rw_write_idx(ii,(1<<RW_VAL_W)-1)
        print(f'{module.regs_rw_cached()=}')
        print(f'{await module.regs_rw_read()=}')
        print(f'{await module.regs_ro_read()=}')
    await module.regs_wt_trigger(0x1F)

    print(f'{await module.regs_rw_read()=}')
    await module.read_cache()
    print(f'{await module.regs_rw_read()=}')
    await module.ctrl_flag_0_write(True)
    module.print_reg_map()
    # print('write zero')
    await module.write_zero_all_rc()
    # print('update')
    await module.read_cache()
    module.print_reg_map()

    if run_server:
        server = regio.tcp_server.RegioTcpServer(ramface_ctrl)
        await server.start()

    for _ in range(100):
        await RisingEdge(dut.clk_i)


    # await Timer(50, unit="ns")  # wait a bit
    # await FallingEdge(dut.clk_i)  # wait for falling edge/"negedge"

    assert True

