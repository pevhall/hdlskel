from pathlib import Path
import regio.regio_cache as regio_cache
from regio.regio_cache import RegioCache

# ----------------------------------------------------------------------
# Simple demo / smoke test when run directly
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio
    import tempfile

    async def demo():
        cache = RegioCache()

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
            path = Path(d) / f"test.{regio_cache.FILE_EXTENSION}"
            cache.save_to_file(path)

            cache2 = RegioCache()
            cache2.load_from_file(path)
            print("reloaded:", cache2.regions())
            assert cache2.regions() == cache.regions()
            print("round-trip OK")

    asyncio.run(demo())
