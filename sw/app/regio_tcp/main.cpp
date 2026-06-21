#include "hdlskel/regio/tcp/regio_tcp.hpp"
#include "hdlskel/regio/tcp/regio_tcp_client.hpp"

#include <CLI/CLI.hpp>

#include <cassert>
#include <iostream>
#include <optional>
#include <memory>
#include <vector>

using hdlskel::regio::tcp::RegioTcpClient;

int main(int argc, char** argv) {
    CLI::App app{"Regio TCP Client CLI application"};

    size_t addr;
    std::optional<size_t> cli_size;
    uint16_t port = hdlskel::regio::tcp::PORT_DEFAULT;
    std::string host = "127.0.0.1";
    app.add_option("addr", addr, "address")->required();
    app.add_option("-s,--size", cli_size, "size");
    app.add_option("-p,--port", port, "port")->capture_default_str();
    app.add_option("-i,--host", host, "host")->capture_default_str();

    CLI11_PARSE(app, argc, argv);

    assert(cli_size);
    size_t size = *cli_size;
    RegioTcpClient regio(host, port);

    // app.add_option("-b,--bytes", my_bytes, "Input byte values (0-255)")
    //    ->expected(-1); // -1 means unlimited arguments
    std::shared_ptr<std::ostream> cout_ptr(&std::cout, [](std::ostream*) {
        // Do not delete std::cout!
    });
    regio.set_log(cout_ptr);

    std::vector<uint8_t> data({1, 2, 3, 4, 5, 6});
    std::span<std::byte> data_span{
        reinterpret_cast<std::byte*>(data.data()),
        data.size()
    };
    std::vector<std::byte> rd_data(size);
    regio.read(addr, rd_data);
}
