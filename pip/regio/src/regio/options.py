from typing import Optional
from pathlib import Path
from dataclasses import dataclass

from . import cache
from . import tcp_client

@dataclass
class RegioOptions:
    tcp_host : Optional[str] = None
    tcp_port : int = tcp_client.PORT_DEFAULT
    load_cache_file : Optional[Path] = None

    def check(self):
        assert self.tcp_host is None or self.load_cache_file is None, "One read option at a time"
        assert self.tcp_host is not None or self.load_cache_file is not None, "One option must be specified"

    async def make_regio(self):
        if self.tcp_host is not None:
            rio = tcp_client.RegioTcpClient(host=self.tcp_host, port=self.tcp_port)
            await rio.connect()
        elif self.load_cache_file is not None:
            rio = cache.RegioCache()
            rio.load_from_file(self.load_cache_file)
            rio._error_on_write = True
        else:
            assert False, "Unreachable"
        return rio



