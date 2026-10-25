#include "hdlskel/skmap/head.hpp"
#include <cassert>
#include <cstring>
#include <stdexcept>
#include <sstream>
#include <iomanip>

namespace {

std::ostream & to_hex(std::ostream & os, size_t w, uint val) {
    return os << std::hex << std::setw(w) << std::setfill('0') << val;
}

}

namespace hdlskel::skmap {

const Head unpack_head(std::span<const std::byte> head_bytes) {
    // Throwing (rather than asserting) means a short span is caught in
    // release builds too, instead of reading out of bounds.
    if (head_bytes.size_bytes() != head_size) {
        throw std::runtime_error("unpack_head: expected " + std::to_string(head_size) + " bytes, got " + std::to_string(head_bytes.size_bytes()));
    }
    Head head;
    std::memcpy(&head, head_bytes.data(), head_size);
    return head;
}

std::string Head::id_str() const {
    // id_to_str() trims the zero padding (like python's get_id_str)
    return id_to_str(id);
}
std::string Head::checksum_str() const {
    // python: f"{self.checksum:0{SIZE_CHECKSUM}X}", so upper case hex
    std::ostringstream oss;
    oss << std::uppercase;
    to_hex(oss, 4, checksum);
    return oss.str();
}

std::string Head::to_str() const {
    std::ostringstream oss;

    if (not valid_sync()) {
        oss << "{BAD id=";

        // encode() → show raw bytes of id
        oss << "b'";
        for (unsigned char c : id) {
            // printable ASCII stays as-is, others hex-escaped
            if (std::isprint(c)) {
                oss << c;
            } else {
                oss << "\\x";
                to_hex(oss, 2, c);
            }
        }
        oss << "', ";
        to_hex(oss, 2, sync) << "}";
        return oss.str();
    }

    oss << "{" << id_str() << ", v" << static_cast<int>(version()) // << ", f=" << static_cast<int>(flags)
        << ", c=" << checksum_str()
        << " l=" << +len_sub << "s+" << +len_kids << "c+" << +len_k << "k+" << +len_var << "v";
    oss << "}";

    return oss.str();
}

}
