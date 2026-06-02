
import cocotb
import tbskel.ramface
import skmap

from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

class ModuleUnkowen(skmap.Module):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def name(cls) -> str:
        return "Unkowen";

    @classmethod
    def id(cls) -> str:
        assert False

    @classmethod
    def ver_major(cls) -> int:
        assert False

    def _init_reg_map_k(self):
        for ii in range(self.head.len_k):
            reg = RegK(self, f'UNKOWN_K_{ii}', SIZE_WORD*8, "Unkowen constant {ii}")
            self._add_reg_k(reg)

    def _init_reg_map_var(self):
        for ii in range(self.head.len_var):
            reg = Reg(self, f'UNKOWN_VAR_{ii}', SIZE_WORD*8, f"Unkowen variable {ii}", acc=Acc.na, ass=Ass.error)
            self._add_reg_var(reg)

async def reg_loopback(dut):
    while True:
        await RisingEdge(dut.clk_i)
        for ii in range(len(dut.regs_var_wr_data_o)):
            dut.regs_var_rd_data_i[ii].value = dut.regs_var_wr_data_o[ii].value
        

@cocotb.test()
async def test_skmap_module(dut):

    dut.ramface_ce_i.value = 1
    cocotb.start_soon(Clock(dut.clk_i, 1, unit="ns").start())
    cocotb.start_soon(reg_loopback(dut))

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

