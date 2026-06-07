from dataclasses import dataclass

SIZE_WORD : int = 4
SIZE_HEAD_WORDS : int = 4
SIZE_HEAD    : int = SIZE_HEAD_WORDS * SIZE_WORD
SIZE_ID : int = 2 * SIZE_WORD
SYNC    : int = 0xCC

@dataclass
class Head:

    id        : str
    sync      : int
    ver_major : int
    ver_minor : int
    reserved  : int
    flags     : int
    len_sub   : int
    len_kids  : int
    len_k     : int
    len_var   : int


    def __init__(self, data : bytes):
        self.id        = data[0:SIZE_ID].decode()
        ii = SIZE_ID;
        self.sync      = data[ii]; ii += 1
        self.ver_major = data[ii]; ii += 1
        d = data[ii]; ii += 1
        self.ver_minor = d & 0xF
        self.reserved  = d >> 4
        self.flags     = data[ii]; ii += 1
        self.len_sub   = data[ii]; ii += 1
        self.len_kids  = data[ii]; ii += 1
        self.len_k     = data[ii]; ii += 1
        self.len_var   = data[ii]; ii += 1
        print(f'{data=}, {self.len_var=}')

    def valid_sync(self):
        return self.sync == SYNC

    def valid(self):
        return (self.sync == SYNC) and (self.reserved == 0)

    def __repr__(self) -> str:
        if not self.valid_sync():
            return f"{{BAD id={self.id.encode()}, {self.sync}}}"
        return f"{{{self.id}, v={self.ver_major}.{self.ver_minor}, f={self.flags}, l={self.len_sub}s+{self.len_kids}c+{self.len_k}k+{self.len_var}v}}"

    def module_size_words(self) -> int:
        return SIZE_HEAD_WORDS + self.len_sub + self.len_kids + self.len_k + self.len_var

    def module_size(self) -> int:
        return self.module_size_words() * SIZE_WORD


