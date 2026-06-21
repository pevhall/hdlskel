class Regio:

    async def write(self, addr : int, data : bytes) -> None:
        raise NotImplementedError

    async def read(self, addr : int, size : int) -> bytes:
        raise NotImplementedError
