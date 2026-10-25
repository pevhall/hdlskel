#include "hdlskel/regio/regio.hpp"

#include <algorithm>
#include <iomanip>   // for std::hex, std::setw, std::setfill

namespace {

// Note: the python library logs operations as `0x10 --> b'...'`, this uses a
// compact hex dump instead:
//   [00000010] ->> { 54 42 52 65 ... }
void append_op_str(std::ostream& os, bool we, size_t addr, std::span<const std::byte> data) {
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

    if (m_mtu.has_value() && data.size() > *m_mtu) {
        const size_t mtu = *m_mtu;
        for (size_t offset = 0; offset < data.size(); offset += mtu) {
            auto chunk = data.subspan(offset, std::min(mtu, data.size() - offset));
            if (m_log) {
                append_op_str(*m_log, true, addr + offset, chunk);
            }
            if (m_pre_write_callback) {
                m_pre_write_callback(addr + offset, chunk);
            }
            if (!m_error_on_write) {
                dev_write(addr + offset, chunk);
            }
        }
    } else {
        if (m_log) {
            append_op_str(*m_log, true, addr, data);
        }
        if (m_pre_write_callback) {
            m_pre_write_callback(addr, data);
        }
        if (!m_error_on_write) {
            dev_write(addr, data);
        }
    }
}

void Regio::read(size_t addr, std::span<std::byte> data) {
    if (m_mtu.has_value() && data.size() > *m_mtu) {
        const size_t mtu = *m_mtu;
        for (size_t offset = 0; offset < data.size(); offset += mtu) {
            auto chunk = data.subspan(offset, std::min(mtu, data.size() - offset));
            dev_read(addr + offset, chunk);
            if (m_log) {
                append_op_str(*m_log, false, addr + offset, chunk);
            }
            if (m_post_read_callback) {
                m_post_read_callback(addr + offset, chunk);
            }
        }
    } else {
        dev_read(addr, data);
        if (m_log) {
            append_op_str(*m_log, false, addr, data);
        }
        if (m_post_read_callback) {
            m_post_read_callback(addr, data);
        }
    }
}

}
