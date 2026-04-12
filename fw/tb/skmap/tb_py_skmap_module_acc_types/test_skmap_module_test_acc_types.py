
import cocotb
import tbskel.ramface
import skmap

from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

        

@cocotb.test()
async def test_skmap_module_test_acc_types(dut):
    print('TESTING123!!!!')

    dut.ramface_ce_i.value = 1
    cocotb.start_soon(Clock(dut.clk_i, 1, unit="ns").start())

    ramface_ctrl = tbskel.ramface.make_RamfaceCtrlBytes_default_ports(dut)
    await RisingEdge(dut.clk_i)


    if 0:
        a = 19
        wr_data = list(range(3,3+6))
        await ramface_ctrl.write_list(a, wr_data)

        rd_data = await ramface_ctrl.read_list(a, len(wr_data))
        rd_data2 = await ramface_ctrl.read(a, len(wr_data))
        print(f'{rd_data=}')
        print(f'{rd_data2=}')

    # await skmap.Module.read_init_module_data(ramface_ctrl, 0)
    module = await skmap.make_Module(ramface_ctrl, 0)
    module.reg_map_print()

    # assert wr_data == rd_data

    for _ in range(5):
        await RisingEdge(dut.clk_i)


    # await Timer(50, unit="ns")  # wait a bit
    # await FallingEdge(dut.clk_i)  # wait for falling edge/"negedge"

    assert True

