
import asyncio
from typing import Optional
from pathlib import Path

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

        parser.add_argument(
            "--rd-file",
            type=Path,
            help="Write file"
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
        write_group.add_argument(
            "--wr-file",
            type=Path,
            help="Write file"
        )

        args = parser.parse_args()

        # Auto-calculate size if not explicitly provided.
        if args.size is None:
            if args.wr_int is not None:
                # Smallest number of bytes needed to represent the integer.
                args.size = max(1, (args.wr_int.bit_length() + 7) // 8)
            elif args.wr_bytes is not None:
                args.size = len(args.wr_bytes)
            elif args.wr_file is not None:
                args.size = args.wr_file.stat().st_size

        if args.wr_bytes is None:
            if args.wr_int is not None:
                args.wr_bytes = args.wr_int.to_bytes(args.size, byteorder='little', signed=True)
            elif args.wr_file is not None:
                with open(args.wr_file, "rb") as wr_f:
                    args.wr_bytes = wr_f.read()
        return args

    def main():
        args = parse_args()
        print(args)

        rd_bytes = asyncio.run( single_op(args) )
        if args.rd_file is not None:
            with open(args.rd_file, "wb") as rd_f:
                rd_f.write(rd_bytes)
        print(f'rd_bytes = {[hex(a) for a in rd_bytes]}')

    main()

 
