#            ╓──────────┬──────────┬──────────┬──────────┐
#            ║  Byte 0  │  Byte 1  │  Byte 2  │  Byte 3  │
# ╒══════════╬══════════╧══════════╧══════════╧══════════╡
# │  Word 0  ║                                           │
# ├──────────╢                    ID          ┌──────────┤
# │  Word 1  ║                                │   Sync   │
# ├──────────╫──────────┬──────────┬──────────┴──────────┤
# │  Word 2  ║ Version  │  Flags   │       Checksum      │
# ├──────────╫──────────┼──────────┼──────────┬──────────┤
# │  Word 3  ║ Len_Kids │ Len_Sub  │  Len_K   │  Len_Var │
# └──────────╨──────────┴──────────┴──────────┴──────────┘

from dataclasses import dataclass

SIZE_WORD       : int = 4
SIZE_HEAD_WORDS : int = 4
SIZE_HEAD       : int = SIZE_HEAD_WORDS * SIZE_WORD
SIZE_ID         : int = 7
SIZE_CHECKSUM   : int = 2
SYNC            : int = 0xD8


@dataclass
class Head:

    id        : str
    sync      : int
    version   : int
    flags     : int
    checksum  : int
    len_kids  : int
    len_sub   : int
    len_k     : int
    len_var   : int


    def __init__(self, data : bytes):
        self.id        = data[0:SIZE_ID].decode()
        ii = SIZE_ID;
        self.sync      = data[ii]; ii += 1
        self.version   = data[ii]; ii += 1
        self.flags     = data[ii]; ii += 1
        self.checksum  = int.from_bytes(data[ii:ii+SIZE_CHECKSUM], byteorder='little')
        ii += SIZE_CHECKSUM
        self.len_kids  = data[ii]; ii += 1
        self.len_sub   = data[ii]; ii += 1
        self.len_k     = data[ii]; ii += 1
        self.len_var   = data[ii]; ii += 1
        # print(f'{data=}, {self.len_var=}')

    def valid_sync(self):
        return self.sync == SYNC

    def valid(self):
        return self.valid_sync()

    def __repr__(self) -> str:
        if not self.valid_sync():
            return f"{{BAD id={self.id.encode()}, {self.sync}}}"
        return f"{{{self.id}, v{self.version}, f={self.flags}, c={self.checksum_str()} l={self.len_sub}s+{self.len_kids}c+{self.len_k}k+{self.len_var}v}}"

    def checksum_str(self) -> str:
        return f'{self.checksum:0{SIZE_CHECKSUM}X}'

    def module_size_words(self) -> int:
        return SIZE_HEAD_WORDS + self.len_sub + self.len_kids + self.len_k + self.len_var

    def module_size(self) -> int:
        return self.module_size_words() * SIZE_WORD


