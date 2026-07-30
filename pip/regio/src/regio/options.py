from typing import Optional
from pathlib import Path
from dataclasses import dataclass

from . import cache
from . import tcp_client

@dataclass
class RegioOptions:
    ip_host : Optional[str] = None
    ip_port : int = tcp_client.PORT_DEFAULT
    load_cache_file : Optional[Path] = None

    def check(self):
        assert self.ip_host is None or self.load_cache_file is None, "One read option at a time"
        assert self.ip_host is not None or self.load_cache_file is not None, "One option must be specified"

    async def make_regio(self):
        if self.ip_host is not None:
            rio = tcp_client.RegioTcpClient(host=self.ip_host, port=self.ip_port)
            await rio.connect()
        elif self.load_cache_file is not None:
            rio = cache.RegioCache()
            rio.load_from_file(self.load_cache_file)
            rio.error_on_write = True
        else:
            assert False, "Unreachable"
        return rio



