
import asyncio
import cocotb
import tbskel.ramface
import regio.tcp_server
import skmap

from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from recipe_test_bench_module import RecipeTestBenchModule





async def reg_loopback(dut):
    while True:
        await RisingEdge(dut.clk_i)
        if dut.regs_wt_trigger_o.value != 0:
            wt = int(dut.regs_wt_o.value)
            print(f'{wt=}')
            dut.flag0_i.value = (wt>>0)&1
            dut.flag1_i.value = (wt>>1)&1
            dut.flag2_i.value = (wt>>2)&1
            dut.flag3_i.value = (wt>>3)&1
            dut.flag4_i.value = (wt>>4)&1
            await RisingEdge(dut.clk_i)
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

    dut.ramface_ce_i.value = 1

    for ii in range(dut.RO_LEN.value):
        dut.regs_ro_i[ii].value = ii
    dut.flag0_i.value = 0
    dut.flag1_i.value = 0
    dut.flag2_i.value = 0
    dut.flag3_i.value = 0
    dut.flag4_i.value = 0
    for ii in range(dut.RW_LEN.value):
        dut.regs_rc_i[ii].value = 0
    cocotb.start_soon(Clock(dut.clk_i, 1, unit="ns").start())
    cocotb.start_soon(reg_loopback(dut))

    ramface_ctrl = tbskel.ramface.make_RamfaceCtrlBytes_default_ports(dut)
    await RisingEdge(dut.clk_i)

    # await skmap.Module.read_init_module_data(ramface_ctrl, 0)
    module = await skmap.make_Module(ramface_ctrl, 0)
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

    server = regio.tcp_server.RegioTcpServer(ramface_ctrl)
    await server.start()
    print('DONE')

    for _ in range(100):
        await RisingEdge(dut.clk_i)


    # await Timer(50, unit="ns")  # wait a bit
    # await FallingEdge(dut.clk_i)  # wait for falling edge/"negedge"

    assert True

