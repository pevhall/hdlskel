
class Regio:

    async def write(self, addr : int, data : bytes) -> None:
        raise NotImplementedError

    async def read(self, addr : int, length : int) -> bytes:
        raise NotImplementedError
