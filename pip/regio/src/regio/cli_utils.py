
import argparse
from pathlib import Path
from .tcp import PORT_DEFAULT
from .options import RegioOptions

def auto_int(s : str) -> int:
    return int(s, 0)

def add_praser_args(parser : argparse.ArgumentParser):
    parser.add_argument(
        "-i", "--host",
        type=str,
        default="127.0.0.1",
        help="Connect to SKMap TCP Regio server"
    )

    parser.add_argument(
        "-f", "--file",
        type=Path,
        help="Take inputs from SKMap cached file"
    )

    # --- Normal arguments ---
    parser.add_argument(
        "-p", "--port",
        type=auto_int,
        default=PORT_DEFAULT,
        help=f"TCP Regio port" # number (default: {PORT_DEFAULT})"
    )
    
    parser.add_argument(
        "--debug-print-regio",
        action="store_true",
        help="If true, print all regio operations"
    )

async def make_regio_from_args(args):
    regio_options = RegioOptions()

    if args.file is not None:
        regio_options.load_cache_file = args.file
    elif args.host is not None:
        regio_options.tcp_host = args.host
        if args.port is not None:
            regio_options.tcp_port = args.port

    regio_options.check()
    regio = await regio_options.make_regio()
    return regio

