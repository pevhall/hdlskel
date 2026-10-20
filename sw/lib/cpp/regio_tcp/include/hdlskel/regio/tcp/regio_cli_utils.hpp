#pragma once

// C++ mirror of pip/regio/src/regio/cli_utils.py
//
// Shared command line options for all regio based applications, plus
// make_regio_from_args() which builds either a cached (file) regio or a
// TCP client regio.

#include "hdlskel/regio/regio.hpp"
#include "hdlskel/regio/tcp/regio_tcp.hpp"

#include <CLI/CLI.hpp>

#include <optional>
#include <string>

namespace hdlskel::regio::cli {

// int(s, 0) in python: accepts 0x.., 0b.., 0o.., decimal.
size_t auto_int(const std::string& s);

struct RegioArgs {
    std::string host = "127.0.0.1";
    std::string file;      // empty -> not set
    uint16_t    port = tcp::PORT_DEFAULT;
    bool        debug_print_regio = false;
    std::optional<size_t> mtu;
};

// Add the shared regio options to `app` (writes into `args`).
void add_parser_args(CLI::App& app, RegioArgs& args);

// Build the regio described by `args`.
//   * "--file <path>"      -> RegioCache loaded from the cache file
//   * otherwise "--host .." -> RegioTcpClient connected to host:port
// Throws if neither or both are given (mirrors RegioOptions.check()).
std::shared_ptr<Regio> make_regio_from_args(const RegioArgs& args);

}
