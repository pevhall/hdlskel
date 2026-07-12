
import asyncio
from typing import Optional
from regio.tcp_client import RegioTcpClient
from regio.tcp import PORT_DEFAULT

 

async def single_op(host : str, port : int, addr : int, size : Optional[int] = None, wr_data : Optional[bytes] = None) -> bytes:
    assert size is not None or wr_data is not None
    client = RegioTcpClient(host=host, port=port, timeout=3.0)

    try:
        await client.connect()
        if  wr_data is not None:
            await client.write(addr, wr_data)
        if size is None:
            assert wr_data is not None
            size = len(wr_data)

        rd_data = await client.read(addr, size)

    finally:

        await client.close()

    return rd_data

 

if __name__ == '__main__':

    import argparse

    def parse_args():
        parser = argparse.ArgumentParser(
            prog="regio_tcp_client",
            description="Regio TCP Client"
        )

        parser.add_argument(
            "--host",
            default="127.0.0.1",
            help="Server host (default: %(default)s)"
        )

        parser.add_argument(
            "--port",
            type=int,
            default=PORT_DEFAULT,
            help=f"Server port (default: {PORT_DEFAULT})"
        )

        parser.add_argument(
            "--debug",
            action="store_true",
            help="Enable debug mode"
        )

        parser.add_argument(
            "-v",
            "--verbose",
            action="count",
            default=0,
            help="Increase verbosity (-v, -vv, -vvv)"
        )

        parser.add_argument(
            "--addr",
            type=int,
            required=True,
            help="Target register address"
        )

        parser.add_argument(
            "-s",
            "--size",
            type=int,
            default=None,
            help="Transfer size in bytes"
        )

        write_group = parser.add_mutually_exclusive_group()

        write_group.add_argument(
            "--wr-int",
            type=int,
            help="Write integer value"
        )

        write_group.add_argument(
            "--wr-bytes",
            type=lambda s: bytes.fromhex(s),
            help="Write bytes as hex string (e.g. DEADBEEF)"
        )

        args = parser.parse_args()

        # Auto-calculate size if not explicitly provided.
        if args.size is None:
            if args.write_int is not None:
                # Smallest number of bytes needed to represent the integer.
                args.size = max(1, (args.write_int.bit_length() + 7) // 8)
            elif args.write_bytes is not None:
                args.size = len(args.write_bytes)

        if args.wr_bytes is None and args.wr_int is not None:
            args.wr_bytes = args.wr_int.to_bytes(args.size, byteorder='little', signed=True)

        return args

    def main():
        args = parse_args()
        print(args)

        rd_bytes = asyncio.run( single_op(args.host, args.port, args.addr, args.size, args.wr_bytes) )
        print(f'{rd_bytes=}')

    main()

 
