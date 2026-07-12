from dataclasses import dataclass
import struct

# Protocol constants
RQST_SYNC = 0x9A
RPLY_SYNC = 0x9B

# Request header: uint8 sync, uint8 flag_we, uint16 size, uint32 addr
RQST_HEAD_FMT = "<BBHI" # B litten endian,=uint8, B=uint8, H=uint16, I=uint32
RQST_HEAD_SIZE = struct.calcsize(RQST_HEAD_FMT)

# Response header: uint8 sync, uint8 flag_error, uint16 size, uint16 addr
RPLY_HEAD_FMT = "<BBHI" # litten endian, B=uint8, B=uint8, H=uint16, I=uint32
RPLY_HEAD_SIZE = struct.calcsize(RPLY_HEAD_FMT)

SIZE_MAX = 0xFFFF
ADDR_MAX = 0xFFFF_FFFF

PORT_DEFAULT = 0x9AB0

@dataclass 
class RqstHead:
    flag_we : bool
    size : int
    addr : int

    @property
    def has_payload(self) -> bool:
        return self.flag_we

    @property
    def payload_size(self) -> int:
        return int(self.has_payload)*self.size

@dataclass 
class RplyHead:
    flag_error : bool
    size : int
    addr : int

    @property
    def has_payload(self) -> bool:
        return not self.flag_error

    @property
    def payload_size(self) -> int:
        return int(self.has_payload)*self.size

def unpack_rqst_head(data : bytes) -> RqstHead:
    sync, flag_we, size, addr = struct.unpack(RQST_HEAD_FMT, data)
    if sync != RQST_SYNC:
        raise ValueError
    return RqstHead(flag_we=flag_we, size=size, addr=addr)

def unpack_rply_head(data : bytes) -> RplyHead:
    sync, flag_error, size, addr = struct.unpack(RPLY_HEAD_FMT, data)
    if sync != RPLY_SYNC:
        raise ValueError
    return RplyHead(flag_error=flag_error, size=size, addr=addr)

def pack_rqst_head(rqst_head : RqstHead):
    return struct.pack(RQST_HEAD_FMT, RQST_SYNC, rqst_head.flag_we, rqst_head.size, rqst_head.addr)

def pack_rply_head(rply_head : RplyHead):
    return struct.pack(RPLY_HEAD_FMT, RPLY_SYNC, rply_head.flag_error, rply_head.size, rply_head.addr)

