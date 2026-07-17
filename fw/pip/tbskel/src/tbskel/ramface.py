from collections import deque

from .regio import Regio
# import cocotb
from cocotb.triggers import RisingEdge, Timer

def port_length(port):
    return port.left - port.right + 1

class RamfaceCtrl:
    
    def __init__(self, clk_i, ce_i, rqst_i, rply_o, LATENCY):
        self.clk_i   = clk_i
        self.ce_i    = ce_i
        self.rqst_i  = rqst_i
        self.rply_o  = rply_o
        self.LATENCY = LATENCY
        # print(dir(rqst_i.wren))

        # print(rqst_i.wren.range)
        # print(dir(rqst_i.wren.value))
        self.WREN_W  = port_length(self.rqst_i.wren)
        self.WORD_W  = port_length(self.rqst_i.data) // self.WREN_W
        self.rqst_queue = deque()
        for _ in range(self.LATENCY):
            self.rqst_queue.append(None)

    async def write_list(self, addr : int, data :list[int]):
        word_start = addr % self.WREN_W
        a = addr // self.WREN_W
        print(f'{a=} = {addr=} // {self.WREN_W=}')
        cycles = (len(data) + word_start + self.WREN_W-1)//self.WREN_W
        # MASK = 1<<(self.WREN_W-1)

        start = word_start
        # mask_start = (MASK>>word_start)<<word_start
        len_left = len(data)
        data_idx = 0
        for _ in range(cycles):
            l = min(len_left, self.WREN_W-start)
            d = 0
            for ii in range(start,start+l):
                d |= data[data_idx] << (ii*self.WORD_W)
                data_idx += 1

            self.rqst_i.en.value   = 1
            self.rqst_i.addr.value = a
            self.rqst_i.wren.value = ((1<<l)-1)<<start
            self.rqst_i.data.value = d

            await RisingEdge(self.clk_i)

            a += 1
            len_left -= l
            start=0

        self.rqst_i.en.value   = 0
        self.rqst_i.addr.value = 0
        self.rqst_i.wren.value = 0
        self.rqst_i.data.value = 0

    async def read_list(self, addr : int, length : int) -> list[int]:
        word_start = addr % self.WREN_W
        a = addr // self.WREN_W
        read_cycles = (length + word_start + self.WREN_W-1)//self.WREN_W 
        # print(f'{a=} = {addr=} // {self.WREN_W=}, {read_cycles=}')
        cycles_total = read_cycles + self.LATENCY + 1

        # MASK = 1<<(self.WREN_W-1)

        start = word_start
        data : list[int] = [0] * length
        # mask_start = (MASK>>word_start)<<word_start

        len_left = len(data)
        data_idx = 0

        WORD_MASK = (1<<self.WORD_W)-1
        for cyc_idx in range(cycles_total):
            # print(f'{cyc_idx=} {read_cycles=}')

            if cyc_idx < read_cycles:
                # print('read')

                self.rqst_i.en.value   = 1
                self.rqst_i.addr.value = a
                self.rqst_i.wren.value = 0
                self.rqst_i.data.value = 0
                a += 1
            elif cyc_idx == read_cycles:
                # print('done')
                self.rqst_i.en.value   = 0
                self.rqst_i.addr.value = 0
                self.rqst_i.wren.value = 0
                self.rqst_i.data.value = 0

            if cyc_idx > self.LATENCY:
                # print(f'{self.rply_o.en.value=}')
                assert self.rply_o.en.value
                assert not self.rply_o.fail.value

                l = min(len_left, self.WREN_W-start)
                # print(f'{self.rply_o.data.value=}')
                data_cyc = self.rply_o.data.value.to_unsigned()
                # print(f'{data_cyc=:x}, {start=}, {l=}')
                for word_idx in range(start,start+l):
                    data[data_idx] = (data_cyc>>(word_idx*self.WORD_W)) & WORD_MASK
                    data_idx += 1

                start = 0
                len_left -= l
            elif cyc_idx > 0:
                assert self.rply_o.en.value == 0

            await RisingEdge(self.clk_i)
            # await Timer(1, units='ps')

        # print(f'read {data=}')

        return data


class RamfaceCtrlBytes(RamfaceCtrl, Regio):

    def __init__(self, clk_i, ce_i, rqst_i, rply_o, LATENCY):
        RamfaceCtrl.__init__(self, clk_i, ce_i, rqst_i, rply_o, LATENCY)
        assert(self.WORD_W == 8)
        Regio.__init__(self)

    async def dev_write(self, addr : int, data : bytes) -> None:
        await self.write_list(addr, list(data))

    async def dev_read(self, addr : int, length : int) -> bytes:
        l = await self.read_list(addr, length)
        return bytes(l)

def make_RamfaceCtrl_default_ports(module):

    return RamfaceCtrl(
            clk_i  = module.clk_i,
            ce_i   = module.ramface_ce_i,
            rqst_i = module.ramface_rqst_i,
            rply_o = module.ramface_rply_o,
            LATENCY = module.RAMFACE_LATENCY.value
    )

def make_RamfaceCtrlBytes_default_ports(module):

    return RamfaceCtrlBytes(
            clk_i  = module.clk_i,
            ce_i   = module.ramface_ce_i,
            rqst_i = module.ramface_rqst_i,
            rply_o = module.ramface_rply_o,
            LATENCY = module.RAMFACE_LATENCY.value
    )

