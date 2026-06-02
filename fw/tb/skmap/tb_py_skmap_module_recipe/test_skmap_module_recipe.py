
import cocotb
import tbskel.ramface
import skmap

from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from recipe_test_bench_module import RecipeTestBenchModule


@cocotb.test()
async def test_skmap_module_test_acc_types(dut):

    dut.ramface_ce_i.value = 1

    for ii in range(dut.RO_LEN.value):
        dut.regs_ro_i[ii].value = ii
    dut.flag0_i.value = 1
    dut.flag1_i.value = 0
    dut.flag2_i.value = 1
    dut.flag3_i.value = 0
    dut.flag4_i.value = 1
    cocotb.start_soon(Clock(dut.clk_i, 1, unit="ns").start())


    ramface_ctrl = tbskel.ramface.make_RamfaceCtrlBytes_default_ports(dut)
    await RisingEdge(dut.clk_i)

    # await skmap.Module.read_init_module_data(ramface_ctrl, 0)
    module = await skmap.make_Module(ramface_ctrl, 0)
    module.reg_map_print()
    assert isinstance(module, RecipeTestBenchModule)

    RW_LEN = module.regs_rw_value_type.vec_len 
    assert RW_LEN is not None
    for ii in range(RW_LEN):
        await module.regs_rw_write_idx(ii,ii+2)
    print(f'{module.regs_rw_cached()=}')
    print(f'{await module.regs_rw_read()=}')

    # assert wr_data == rd_data

    for _ in range(5):
        await RisingEdge(dut.clk_i)


    # await Timer(50, unit="ns")  # wait a bit
    # await FallingEdge(dut.clk_i)  # wait for falling edge/"negedge"

    assert True

