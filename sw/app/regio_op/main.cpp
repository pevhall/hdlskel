// C++ mirror of pip/regio/src/regio_op.py
//
// Single regio operation: optionally write (from an int, a hex string or a
// file) then optionally read back (to stdout and/or a file). The regio is
// either a TCP client or a cache file, selected with -i/--host or -f/--file
// (see hdlskel/regio/tcp/regio_cli_utils.hpp).
//
// Examples:
//   regio_op -a 0x4000 -s 16
//   regio_op -a 0x4000 --wr-int 0x1234
//   regio_op -a 0x4000 --wr-bytes DEADBEEF -s 4
//   regio_op -a 0x40 -s 32 --rd-file out.bin
//   regio_op -f cache.skmap -a 0 -s 8
//   regio_op -a 0 -s 4096 --mtu 64

#include "hdlskel/regio/cache.hpp"
#include "hdlskel/regio/regio.hpp"
#include "hdlskel/regio/tcp/regio_cli_utils.hpp"

#include <CLI/CLI.hpp>

#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <span>
#include <sstream>
#include <string>
#include <vector>

using hdlskel::regio::Regio;
using hdlskel::regio::cli::auto_int;
using hdlskel::regio::cli::make_regio_from_args;
using hdlskel::regio::cli::RegioArgs;

namespace {

// int.to_bytes(size, byteorder='little', signed=True)
std::vector<std::byte> int_to_bytes_le(int64_t value, size_t size) {
    std::vector<std::byte> out(size);
    uint64_t v = static_cast<uint64_t>(value);
    for (size_t ii = 0; ii < size; ii++) {
        out[ii] = static_cast<std::byte>((v >> (8 * ii)) & 0xFF);
    }
    return out;
}

// Smallest number of bytes needed to represent the integer:
//   max(1, (bit_length + 7) // 8)
size_t int_min_bytes(int64_t value) {
    uint64_t v = static_cast<uint64_t>(value);
    size_t bits = 0;
    while (v) { bits++; v >>= 1; }
    return std::max<size_t>(1, (bits + 7) / 8);
}

std::vector<std::byte> read_whole_file(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) {
        throw std::runtime_error("Could not open '" + path + "' for reading");
    }
    std::vector<char> raw(
        (std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
    std::vector<std::byte> out(raw.size());
    for (size_t ii = 0; ii < raw.size(); ii++) {
        out[ii] = static_cast<std::byte>(static_cast<uint8_t>(raw[ii]));
    }
    return out;
}

size_t file_size(const std::string& path) {
    std::ifstream f(path, std::ios::binary | std::ios::ate);
    if (!f) {
        throw std::runtime_error("Could not open '" + path + "' for reading");
    }
    return static_cast<size_t>(f.tellg());
}

// bytes.fromhex(s)
std::vector<std::byte> bytes_from_hex(const std::string& s) {
    if (s.size() % 2) {
        throw std::runtime_error("hex string needs an even number of digits, got '" + s + "'");
    }
    std::vector<std::byte> out(s.size() / 2);
    for (size_t ii = 0; ii < out.size(); ii++) {
        out[ii] = static_cast<std::byte>(std::stoul(s.substr(ii * 2, 2), nullptr, 16));
    }
    return out;
}

std::string to_hex_string(std::span<const std::byte> data) {
    std::ostringstream oss;
    oss << "[";
    for (size_t ii = 0; ii < data.size(); ii++) {
        if (ii) { oss << ", "; }
        oss << "0x" << std::hex << static_cast<int>(data[ii]);
    }
    oss << "]";
    return oss.str();
}

}

int regio_op_main(int argc, char** argv);

int main(int argc, char** argv) {
    try {
        return regio_op_main(argc, argv);
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << "\n";
        return 1;
    }
}

int regio_op_main(int argc, char** argv) {
    CLI::App app{"Regio TCP Client"};

    // --- regio.cli_utils.add_parser_args ---
    RegioArgs regio_args;
    hdlskel::regio::cli::add_parser_args(app, regio_args);

    // -v, -vv, -vvv (CLI11 counts into an int)
    int verbose = 0;
    app.add_flag("-v,--verbose", verbose, "Increase verbosity (-v, -vv, -vvv)");
    (void)verbose;   // currently only used for logging verbosity

    size_t addr = 0;
    app.add_option("-a,--addr", addr, "Target register address")
        ->required()
        ->transform([](std::string s) { return std::to_string(auto_int(s)); });

    std::optional<size_t> size;
    app.add_option("-s,--size", size, "Transfer size in bytes")
        ->transform([](std::string s) { return std::to_string(auto_int(s)); });

    std::string rd_file;
    app.add_option("--rd-file", rd_file, "Write file");

    // --- write group (mutually exclusive) ---
    std::optional<int64_t> wr_int;
    std::string wr_bytes_str;
    std::string wr_file;
    auto* opt_wr_int   = app.add_option("--wr-int", wr_int, "Write integer value");
    auto* opt_wr_bytes = app.add_option("--wr-bytes", wr_bytes_str,
                                        "Write bytes as hex string (e.g. DEADBEEF)");
    auto* opt_wr_file  = app.add_option("--wr-file", wr_file, "Write file");
    opt_wr_int->excludes(opt_wr_bytes);
    opt_wr_int->excludes(opt_wr_file);
    opt_wr_bytes->excludes(opt_wr_file);

    CLI11_PARSE(app, argc, argv);

    // --- Auto-calculate size if not explicitly provided ---
    if (!size.has_value()) {
        if (wr_int.has_value()) {
            size = int_min_bytes(*wr_int);
        } else if (!wr_bytes_str.empty()) {
            size = bytes_from_hex(wr_bytes_str).size();
        } else if (!wr_file.empty()) {
            size = file_size(wr_file);
        }
    }

    std::vector<std::byte> wr_data;
    bool has_wr = false;
    if (!wr_bytes_str.empty()) {
        wr_data = bytes_from_hex(wr_bytes_str);
        has_wr = true;
    } else if (wr_int.has_value()) {
        if (!size.has_value()) {
            throw std::runtime_error("size is required");
        }
        wr_data = int_to_bytes_le(*wr_int, *size);
        has_wr = true;
    } else if (!wr_file.empty()) {
        wr_data = read_whole_file(wr_file);
        has_wr = true;
    }

    if (!size.has_value()) {
        throw std::runtime_error("Either --size or one of the write options is required");
    }

    const bool print_rd = *size <= 4096;
    const bool rd = print_rd || !rd_file.empty();

    auto rio = make_regio_from_args(regio_args);

    if (has_wr) {
        rio->write(addr, std::span<const std::byte>(wr_data));
    }

    std::vector<std::byte> rd_data;
    if (rd) {
        rd_data.resize(*size);
        rio->read(addr, std::span<std::byte>(rd_data));
    }

    if (!rd_file.empty()) {
        std::ofstream f(rd_file, std::ios::binary | std::ios::trunc);
        if (!f) {
            throw std::runtime_error("Could not open '" + rd_file + "' for writing");
        }
        f.write(reinterpret_cast<const char*>(rd_data.data()),
                static_cast<std::streamsize>(rd_data.size()));
    }
    if (print_rd) {
        std::cout << "rd_bytes = " << to_hex_string(rd_data) << "\n";
    }

    return 0;
}
