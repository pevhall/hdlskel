#include "hdlskel/regio/tcp/regio_cli_utils.hpp"

#include "hdlskel/regio/cache.hpp"
#include "hdlskel/regio/tcp/regio_tcp_client.hpp"

#include <memory>
#include <stdexcept>

namespace hdlskel::regio::cli {

size_t auto_int(const std::string& s) {
    try {
        size_t pos = 0;
        unsigned long long v = std::stoull(s, &pos, 0);
        if (pos != s.size()) {
            throw std::invalid_argument(s);
        }
        return static_cast<size_t>(v);
    } catch (const std::exception&) {
        throw std::runtime_error("Invalid integer '" + s + "'");
    }
}

void add_parser_args(CLI::App& app, RegioArgs& args) {
    app.add_option("-i,--host", args.host,
                   "Connect to SKMap TCP Regio server")->capture_default_str();
    app.add_option("-f,--file", args.file,
                   "Take inputs from SKMap cached file");
    app.add_option("-p,--port", args.port,
                   "SKMap TCP Regio server's port")->capture_default_str();
    app.add_flag("--debug-print-regio", args.debug_print_regio,
                 "If true, print all regio operations");
    app.add_option("--mtu", args.mtu,
                   "Maximum Transmission Unit, used to split operation");
}

std::shared_ptr<Regio> make_regio_from_args(const RegioArgs& args) {
    const bool use_file = !args.file.empty();
    std::shared_ptr<Regio> rio;

    if (use_file) {
        auto cache = std::make_shared<RegioCache>();
        cache->load_from_file(args.file);
        cache->error_on_write(false);
        rio = cache;
    } else {
        rio = std::make_shared<tcp::RegioTcpClient>(args.host, args.port);
    }

    rio->mtu(args.mtu);
    if (args.debug_print_regio) {
        std::shared_ptr<std::ostream> cout_ptr(&std::cout, [](std::ostream*) {
            // Do not delete std::cout!
        });
        rio->set_log(cout_ptr);
    }
    return rio;
}

}
