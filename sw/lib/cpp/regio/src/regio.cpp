



#include "hdlskel/regio/regio.hpp"

#include <iomanip>   // for std::hex, std::setw, std::setfill
namespace {

void append_op_str(std::ostream& os, bool we, size_t addr,

                   std::span<const std::byte> data) {
    // address in 8 digit hex, zero padded
    os << '[' << std::hex << std::setw(8) << std::setfill('0')
       << static_cast<std::uint64_t>(addr) << std::dec << "] ";
    os << (we ? "<<-" : "->>");
    os << " {";
    for (const auto b : data) {
        os << ' ' << std::hex << std::setw(2) << std::setfill('0')



           << static_cast<int>(b) << std::dec;
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
