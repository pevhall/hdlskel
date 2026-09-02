
import asyncio
from typing import Optional
import regio
import regio.cli_utils


 

async def single_op(args) -> bytes:

    rio : regio.Regio = await regio.cli_utils.make_regio_from_args(args)
    addr = args.addr;
    size = args.size
    wr_data = args.wr_bytes
    assert size is not None or wr_data is not None

    if  wr_data is not None:
        await rio.write(addr, wr_data)
    if size is None:
        assert wr_data is not None
        size = len(wr_data)

    rd_data = await rio.read(addr, size)


    return rd_data

 

if __name__ == '__main__':

    import argparse

    def parse_args():
        parser = argparse.ArgumentParser(
            prog="regio_tcp_client",
            description="Regio TCP Client"
        )

        regio.cli_utils.add_parser_args(parser);

        parser.add_argument(
            "-v",
            "--verbose",
            action="count",
            default=0,
            help="Increase verbosity (-v, -vv, -vvv)"
        )

        parser.add_argument(
            "-a,",
            "--addr",
            type=regio.cli_utils.auto_int,
            required=True,
            help="Target register address"
        )

        parser.add_argument(
            "-s",
            "--size",
            type=regio.cli_utils.auto_int,
            default=None,
            help="Transfer size in bytes"
        )

        write_group = parser.add_mutually_exclusive_group()

        write_group.add_argument(
            "--wr-int",
            type=regio.cli_utils.auto_int,
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

        rd_bytes = asyncio.run( single_op(args) )
        print(f'rd_bytes = {[hex(a) for a in rd_bytes]}')

    main()

 
