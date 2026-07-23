import regio.file_cache as file_cache
from regio.file_cache import FileCache

# ----------------------------------------------------------------------
# Simple demo / smoke test when run directly
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio
    import tempfile
    import os

    async def demo():
        cache = FileCache()

        await cache.dev_write(0x100, b"ABCD")
        await cache.dev_write(0x104, b"EFGH")       # adjacent -> merges
        await cache.dev_write(0x200, b"ZZZZ")       # separate region
        await cache.dev_write(0x102, b"xy")         # overlaps first region

        print(cache)
        print(cache.regions())

        data = await cache.dev_read(0x100, 7)
        print("read:", data)

        data = await cache.dev_read(0x101, 7)
        print("read:", data)

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, f"test.{file_cache.FILE_EXTENSION}")
            cache.save_to_file(path)

            cache2 = FileCache()
            cache2.load_from_file(path)
            print("reloaded:", cache2.regions())
            assert cache2.regions() == cache.regions()
            print("round-trip OK")

    asyncio.run(demo())
