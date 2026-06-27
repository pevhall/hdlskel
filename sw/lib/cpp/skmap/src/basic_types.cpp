#include "include/hdlskel/skmap/basic_types.hpp"

#include <sstream>


std::ostream& operator<<(std::ostream& os, hdlskel::skmap::Acc v) {
    switch (v) {
        case hdlskel::skmap::Acc::na: return os << "na";
        case hdlskel::skmap::Acc::k:  return os << "k";
        case hdlskel::skmap::Acc::ro: return os << "ro";
        case hdlskel::skmap::Acc::rc: return os << "rc";
        case hdlskel::skmap::Acc::rw: return os << "rw";
        case hdlskel::skmap::Acc::wt: return os << "wt";
    }
    return os << "<unknown Acc>";
}

std::ostream& operator<<(std::ostream& os, hdlskel::skmap::Ass v) {
    switch (v) {
        case hdlskel::skmap::Ass::none    : return os << "none";
        case hdlskel::skmap::Ass::passed  : return os << "passed";
        case hdlskel::skmap::Ass::debug   : return os << "debug";
        case hdlskel::skmap::Ass::info    : return os << "info";
        case hdlskel::skmap::Ass::warn    : return os << "warn";
        case hdlskel::skmap::Ass::error   : return os << "error";
        case hdlskel::skmap::Ass::crit    : return os << "crit";
        case hdlskel::skmap::Ass::fatal   : return os << "fatal";
    }
    return os << "<unknown Ass>";
}

std::ostream& operator<<(std::ostream& os, hdlskel::skmap::ValueKind v) {
    switch (v) {
        case hdlskel::skmap::ValueKind::uint_: return os << "uint";
        case hdlskel::skmap::ValueKind::sint_: return os << "sint";
        case hdlskel::skmap::ValueKind::char_: return os << "char";
        case hdlskel::skmap::ValueKind::bits_: return os << "bits";
        case hdlskel::skmap::ValueKind::flag_: return os << "flag";
    }
    return os << "<unknown ValueKind>";
}

// std::ostream& operator<<(std::ostream& os, hdlskel::skmap::ValueType v) {
//     os << v.kind();
// }

namespace hdlskel::skmap {

std::string ValueType::str() const {
    std::ostringstream os;
    ::operator<<(os, m_kind) << elem_width();
    if (m_vec_len) {
        os << "[" << *m_vec_len << "]";
    }
    return os.str();
}

std::string str(Acc v){
    std::ostringstream os;
    ::operator<<(os, v);
    return os.str();
}

std::string str(Ass v){
    std::ostringstream os;
    ::operator<<(os, v);
    return os.str();
}

std::string str(ValueKind v){
    std::ostringstream os;
    ::operator<<(os, v);
    return os.str();
}

}
