#include "hdlskel/regio/regio.hpp"

#include <format>

namespace {



void append_op_str(std::ostream & os, bool we, size_t addr, std::span<const std::byte> data) {
    os << std::format("[{:08x}] ", addr);
    os << (we ? "<<-" : "->>");
    os << " {";
    for (const auto b : data) {
        os << std::format(" {:02x}", int(b));
    }
    os << " }\n";
}

}

namespace hdlskel::regio {

void Regio::write(size_t addr, std::span<const std::byte> data) {
    if(m_log) {
        append_op_str(*m_log, true, addr, data);
    }
    dev_write(addr, data);
}

void Regio::read(size_t addr, std::span<std::byte> data) {
    dev_read(addr, data);
    if(m_log) {
        append_op_str(*m_log, false, addr, data);
    }
}

}
