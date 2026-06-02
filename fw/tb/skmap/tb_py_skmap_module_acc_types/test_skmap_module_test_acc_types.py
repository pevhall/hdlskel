
import cocotb
import tbskel.ramface
import skmap

from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

class ModuleTestAcc(skmap.Module):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def name(cls) -> str:
        return "Test Access";

    @classmethod
    def id(cls) -> str:
        return "Test_Acc"

    @classmethod
    def ver_major(cls) -> int:
        return 1

    def _init_reg_map_k(self):
        reg = skmap.RegK(self, name=f'REGS_RO_LEN',    value_type=skmap.value_type_u8, desc="RO length")
        self._add_reg_k(reg)
        self.REGS_RO_LEN = reg.value_int()
        reg = skmap.RegK(self, name=f'REGS_RO_ELEM_W', value_type=skmap.value_type_u8, desc="RO element width")
        self._add_reg_k(reg)
        self.REGS_RO_ELEM_W = reg.value_int()
        reg = skmap.RegK(self, name=f'REGS_RW_LEN',    value_type=skmap.value_type_u8, desc="RW length")
        self._add_reg_k(reg)
        self.REGS_RW_LEN = reg.value_int()
        reg = skmap.RegK(self, name=f'REGS_RW_ELEM_W', value_type=skmap.value_type_u8, desc="RW element width")
        self._add_reg_k(reg)
        self.REGS_RW_ELEM_W = reg.value_int()
        reg = skmap.RegK(self, name=f'REGS_WS_LEN',    value_type=skmap.value_type_u8, desc="WS length")
        self._add_reg_k(reg)
        self.REGS_WS_LEN = reg.value_int()
        reg = skmap.RegK(self, name=f'REGS_WS_ELEM_W', value_type=skmap.value_type_u8, desc="WS element width")
        self._add_reg_k(reg)
        self.REGS_WS_ELEM_W = reg.value_int()
        reg = skmap.RegK(self, name=f'REGS_RC_W',      value_type=skmap.value_type_u8, desc="RC width")
        self._add_reg_k(reg)
        self.REGS_RC_W = reg.value_int()

    def _init_reg_map_var(self):
        print(self.REGS_RW_LEN)
        # reg = skmap.RegVec(self, name=f'regs_rw', length=self.REGS_RW_LEN, width=self.REGS_RW_ELEM_W, desc=f"Read write regsiters", acc=skmap.Acc.na, ass=skmap.Ass.error)
        reg = skmap.RegVec(self, vec_len=self.REGS_RO_LEN, name=f'regs_ro', value_type=skmap.ValueType(kind=skmap.ValueKind.bits, width=self.REGS_RO_ELEM_W), desc=f"Read only regsiters", acc=skmap.Acc.ro)
        self._add_reg_var(reg)
        reg = skmap.RegVec(self, vec_len=self.REGS_RW_LEN, name=f'regs_rw', value_type=skmap.ValueType(kind=skmap.ValueKind.bits, width=self.REGS_RW_ELEM_W), desc=f"Read write regsiters", acc=skmap.Acc.rw)
        self._add_reg_var(reg)
        reg = skmap.RegVec(self, vec_len=self.REGS_WS_LEN, name=f'regs_rw', value_type=skmap.ValueType(kind=skmap.ValueKind.bits, width=self.REGS_RW_ELEM_W), desc=f"Write Strobe Registers", acc=skmap.Acc.ws)
        self._add_reg_var(reg)
        print(f'{self.REGS_RC_W=}')
        reg = skmap.Reg(self, name=f'regs_ws', value_type=skmap.ValueType(kind=skmap.ValueKind.bits, width=self.REGS_RC_W), desc=f"Write Strobe Registers", acc=skmap.Acc.rc)
        flags = {}
        for b in range(self.REGS_RC_W):
            ass = skmap.Ass((b % 4) + 1)
            flags[b] = skmap.RFlag(name=f'Flag{b}', ass=ass, desc = f'Flag {b}')
        reg = skmap.RegFlags(self, name=f'regs_ws', width=self.REGS_RC_W, flags=flags, desc=f"Read clear flags", acc=skmap.Acc.rc)
        self._add_reg_var(reg)
skmap.register_Module(ModuleTestAcc)

@cocotb.test()
async def test_skmap_module_test_acc_types(dut):

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

