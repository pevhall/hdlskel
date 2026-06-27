#include "hdlskel/skmap/head.hpp"
#include <cassert>
#include <cstring>
#include <sstream>
#include <iomanip>

namespace {

std::ostream & to_hex(std::ostream & os, size_t w, uint val) {
    return os << std::hex << std::setw(w) << std::setfill('0') << val;
}

}

namespace hdlskel::skmap {

const Head unpack_head(std::span<const std::byte> head_bytes) {
    assert (head_bytes.size_bytes() == head_size);
    Head head;
    std::memcpy(&head, head_bytes.data(), head_size);
    return head;
}

std::string Head::id_str() const {
    return std::string(id.begin(), id.end());
}
std::string Head::checksum_str() const {
    std::ostringstream oss;
    to_hex(oss, 4, checksum);
    return oss.str();
}
// std::string id_str() const {
// }

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

    oss << "{" << id_str() << ", v" << static_cast<int>(version) << ", f=" << static_cast<int>(flags)
        << ", c=" << checksum_str()
        << " l=" << len_sub << "s+" << +len_kids << "c+" << +len_k << "k+" << +len_var << "v" << "}";

    return oss.str();
}

}
