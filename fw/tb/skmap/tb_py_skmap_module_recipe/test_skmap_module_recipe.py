import sys
import ast
import asyncio
import cocotb
import tbskel.ramface
import regio.tcp_server
import skmap
import skmap.basic
import logging

from dataclasses import dataclass

from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from recipe_test_bench_module import RecipeTestBenchModule


MEM_RW_OFFSET = 0x1_0000;
MEM_RO_OFFSET = 0x2_0000;

def assert_all_ones(vec):
    assert vec.value == (1<<len(vec))-1

def loopback_ram(rqst, rply, data_offset, ro = False, cntrs = None):
    rply.fail.value = 0
    if rqst.en.value == 0:
        rply.en.value = 0
        rply.data.value = 0
    else:
        a = int(rqst.addr.value)
        if ro:
            rd = True
        else:
            rd = rqst.wren.value == 0
        wr = not rd
        rply.en.value = rd
        expected_data = a + data_offset
        if rd:
            rply.data.value = expected_data
        else:
            rply.data.value = 0
        if wr:
            assert_all_ones(rqst.wren)
            assert rqst.data.value == expected_data
        if cntrs is not None:
            if rd:
                cntrs.rd += 1
            if wr:
                cntrs.wr += 1


async def reg_loopback(dut, rw_cntrs, ro_cntrs):
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

        loopback_ram(dut.mem_rw_rqst_o, dut.mem_rw_rply_i, MEM_RW_OFFSET, cntrs=rw_cntrs);
        loopback_ram(dut.mem_ro_rqst_o, dut.mem_ro_rply_i, MEM_RO_OFFSET, ro = True, cntrs=ro_cntrs);


@cocotb.test()
async def test_skmap_module_test_acc_types(dut):
    logging.basicConfig(level=logging.DEBUG,stream=sys.stderr,force=True)
    run_server = cocotb.plusargs.get("run_server")
    assert isinstance(run_server, str)
    run_server = ast.literal_eval(run_server)
    print(f"{run_server=}")

    dut.ramface_ce_i.value = 1

    dut.bit_bool_rc_i.value = 0
    dut.bit_ro_i.value = 0


    for ii in range(dut.RO_LEN.value):
        dut.regs_ro_i[ii].value = ii
    for ii in range(dut.RW_LEN.value):
        dut.regs_rc_i[ii].value = 0
    dut.reg_s_rc_i.value = 0
    dut.debug_flag0_i.value = 0
    dut.info_flag1_i.value = 0
    dut.warn_flag2_i.value = 0
    dut.error_flag3_i.value = 0
    dut.fatal_flag4_i.value = 0
    dut.debug_flag_vec_i.value = 0
    dut.mem_rw_ptr_i.value = 0

    dut.mem_rw_rply_i.en.value   = 0
    dut.mem_rw_rply_i.fail.value = 0
    dut.mem_rw_rply_i.data.value = 0

    dut.mem_ro_rply_i.en.value   = 0
    dut.mem_ro_rply_i.fail.value = 0
    dut.mem_ro_rply_i.data.value = 0



    @dataclass
    class RamCntrs:
        rd : int = 0
        wr : int = 0

    rw_cntrs = RamCntrs()
    ro_cntrs = RamCntrs()

    cocotb.start_soon(Clock(dut.clk_i, 1, unit="ns").start())
    cocotb.start_soon(reg_loopback(dut, rw_cntrs, ro_cntrs))

    ramface_ctrl = tbskel.ramface.make_RamfaceCtrlBytes_default_ports(dut)
    print(f'{dut.RAMFACE_LATENCY.value=}')
    await RisingEdge(dut.clk_i)

    logging.basicConfig(level=logging.DEBUG)
    # await skmap.Module.read_init_module_data(ramface_ctrl, 0)
    module = await skmap.make_module(ramface_ctrl, 0) #type:ignore
    # module.print_reg_map_cached()
    assert isinstance(module, RecipeTestBenchModule)
    assert module.regs_wt_read_cached() == dut.REGS_WT_INIT.value
    print(f'{await module.regs_rw_read()=}')
    if 1:
        RW_LEN   = module.regs_rw_inst.value_type.vec_len 
        RW_VAL_W = module.regs_rw_inst.value_type.width 
        # RW_LEN = module.regs_rw_value_type.vec_len 
        # RW_VAL_W = module.regs_rw_value_type.width 
        assert RW_LEN is not None
        for ii in range(RW_LEN):
            await module.regs_rw_write_idx(ii,ii+0xA0)
            # await module.regs_rw_write_idx(ii,(1<<RW_VAL_W)-1)
        # print(f'{module.regs_rw_read_cached()=}')
        # print(f'{await module.regs_rw_read()=}')
        # print(f'{await module.regs_ro_read()=}')
    await module.regs_wt_write_trigger(0x1F)

    # print(f'{await module.regs_rw_read()=}')
    await module.read_all()
    # print(f'{await module.regs_rw_read()=}')
    await module.ctrl_flag_0_write(True)
    module.print_reg_map_cached()
    # print('write zero')
    await module.write_zero_all_rc()
    # print('update')
    await module.read_all()
    module.print_reg_map_cached()

    module.mem_rw_inst._regio.log_regio = True
    rw_data_bytes = await module.mem_rw_read(0, module.mem_rw_size)
    rw_data = skmap.basic.bytes_to_list_int(rw_data_bytes, 4)
    print(f'rw_data = {[hex(a) for a in rw_data]}\n')

    for ii, rw_v in enumerate(rw_data):
        assert ii + MEM_RW_OFFSET == rw_v

    await module.mem_rw_write(0, rw_data_bytes)

    ro_data = await module.mem_ro_read(0, module.mem_ro_size)
    ro_data = skmap.basic.bytes_to_list_int(ro_data, 4)
    print(f'ro_data = {[hex(a) for a in ro_data]}\n')

    for ii, ro_v in enumerate(ro_data):
        assert ii + MEM_RO_OFFSET == ro_v

    print(f'rw ops = (rd {rw_cntrs.rd}, wr {rw_cntrs.wr})')
    print(f'ro ops = (rd {ro_cntrs.rd}, wr {ro_cntrs.wr})')

    # await module.mem_ro_read(0, module.mem_ro_size)

    if run_server:
        server = regio.tcp_server.RegioTcpServer(ramface_ctrl) #type:ignore
        await server.start()

    for _ in range(100):
        await RisingEdge(dut.clk_i)


    # await Timer(50, unit="ns")  # wait a bit
    # await FallingEdge(dut.clk_i)  # wait for falling edge/"negedge"

    assert True

