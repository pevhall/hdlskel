
import cocotb
import ramface
# import skmap

from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

async def reg_loopback(dut):
    while True:
        await RisingEdge(dut.clk_i)
        for ii in range(len(dut.regs_var_wr_data_o)):
            dut.regs_var_rd_data_i[ii].value = dut.regs_var_wr_data_o[ii].value
        

@cocotb.test()
async def test_skmap_module(dut):
    print('TESTING123!!!!')

    dut.ramface_ce_i.value = 1
    cocotb.start_soon(Clock(dut.clk_i, 1, unit="ns").start())
    cocotb.start_soon(reg_loopback(dut))

    ramface_ctrl = ramface.make_RamFaceCtrl_default_ports(dut)
    await RisingEdge(dut.clk_i)

    a = 19
    wr_data = list(range(3,3+6))
    await ramface_ctrl.write_data(a, wr_data)
    rd_data = await ramface_ctrl.read_data(a, len(wr_data))

    # module = skmap.Module(regio, 0)

    print({'rd_data='})
    # assert wr_data == rd_data

    for _ in range(5):
        await RisingEdge(dut.clk_i)


    # await Timer(50, unit="ns")  # wait a bit
    # await FallingEdge(dut.clk_i)  # wait for falling edge/"negedge"

    assert True

