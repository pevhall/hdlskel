# import socket
# import logging
#
# from .regio import Regio
#
# def run_regio_tcp_server(regio : Regio, port : int, ip : str = '0.0.0.0'):
#     tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#     tcp_socket.bind((ip, port))
#     logging.info(f"Listening at {ip}:{port}")
#
#     try:
#         while True:
#             # 4. Accept a connection (blocks until a client connects)
#             client_socket, client_address = tcp_socket.accept()
#             logging.info(f"Connection established with {client_address}")
#
#             # 5. Receive and process data in a loop
#             while True:
#                 data = client_socket.recv(9000) # Buffer size of 1024 bytes
#                 if not data:
#                     logging.debug(f"Connection {client_address} closed")
#                     # No data means the client closed the connection safely
#                     break
#
#                 print(f"Received from client: {data.decode('utf-8')}")
#
#                 # 6. Send the data back to the client
#                 client_socket.sendall(data)
#
#             # Clean up the client connection
#             client_socket.close()
#             print(f"Connection with {client_address} closed.")
#
#     except KeyboardInterrupt:
#         logging.info("\nShutting down the server.")
#     finally:
#         tcp_socket.close()
#
# class RegioServer:
#
#     def __init__(self, regio : Regio):
#         self.regio = regio
#         self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)


import asyncio
import struct
from typing import Optional

from . import Regio

from .tcp import RQST_HEAD_SIZE, RqstHead, RplyHead, unpack_rqst_head, pack_rply_head, PORT_DEFAULT


class RegioTcpServer:
    """
    TCP server that speaks the binary protocol and delegates storage
    operations to a Regio instance.
    """
    def __init__(self, regio : Regio, port : int = 0x9A9B, host : str = "0.0.0.0"):
        self.regio = regio
        self.host = host
        self.port = port
        self._server: Optional[asyncio.base_events.Server] = None

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peer = writer.get_extra_info("peername")
        try:
            # Read request header
            rqst_head_bytes = await reader.readexactly(RQST_HEAD_SIZE)
        except asyncio.IncompleteReadError:
            writer.close()
            await writer.wait_closed()
            return

        try:
            rqst_head = unpack_rqst_head(rqst_head_bytes)
        except (struct.error, ValueError):
            writer.close()
            await writer.wait_closed()
            return

        # If write request, read 'size' bytes of payload
        if rqst_head.flag_we:
            try:
                data = await reader.readexactly(rqst_head.size)
            except asyncio.IncompleteReadError:
                # malformed request, close
                writer.close()
                await writer.wait_closed()
                return

            # Call the Regio.write implementation
            try:
                await self.regio.write(rqst_head.addr, data)
                # For write requests, no reply format was specified.
                # We'll send a minimal acknowledgement: sync + flag_error=0 + size=0 + addr(low16)
                flag_error = 0
            except Exception:
                flag_error = 1

            # rply_head = RplyHead(flag_error=False, size=rqst_head.size, addr=rqst_head.addr)
            # resp_head = pack_rply_head(rply_head)
            # writer.write(resp_head)
            # await writer.drain()
            # writer.close()
            # await writer.wait_closed()
            return

        # Read request is when flag_we == 0
        # Call Regio.read(addr, size) and reply with the response format
        try:
            data = await self.regio.read(rqst_head.addr, rqst_head.size)
            if not isinstance(data, (bytes, bytearray)):
                raise TypeError("Regio.read must return bytes")
            # If returned data length differs from requested size, treat as error

            if len(data) != rqst_head.size:
                raise ValueError("Unexpected Length")
                # We'll treat this as an error condition
                rply_head = RplyHead(
                    flag_error = True,
                    size = rqst_head.size,
                    addr = rqst_head.addr
                )
                data = b"",

            else:
                rply_head = RplyHead(
                    flag_error = False,
                    size = rqst_head.size,
                    addr = rqst_head.addr
                )
        except Exception as e:
            raise e

        rply_head_bytes = pack_rply_head(rply_head)
        writer.write(rply_head_bytes)
        if rply_head.payload_size() > 0:
            writer.write(data)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def start(self):
        self._server = await asyncio.start_server(self.handle_client, self.host, self.port)

    async def serve_forever(self):
        if self._server is None:
            await self.start()
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def wait_closed(self):
        if self._server:
            await self._server.wait_closed()

async def tcp_serve_regio_forever(regio : Regio, port : int = PORT_DEFAULT, host : str = "0.0.0.0"):
    server = RegioTcpServer(regio, host=host, port=port)
    await server.start()
    print(f"Server listening on {server.host}:{server.port}")
    try:
        await server.serve_forever()
    except asyncio.CancelledError:
        await server.stop()

def asyncio_tcp_serve_regio_forever(regio : Regio, port : int = PORT_DEFAULT, host : str = "0.0.0.0"):
    try:
        asyncio.run(tcp_serve_regio_forever(regio = regio, port = port, host = host))
    except KeyboardInterrupt:
        pass

