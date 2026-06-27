#pragma once

#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <optional>
#include <array>

namespace hdlskel::skmap {

constexpr int ver_major = 0;
constexpr int ver_minor = 1;
constexpr int ver_patch = 0;

const std::string ver_str = std::to_string(ver_major)+"."+std::to_string(ver_minor)+"."+std::to_string(ver_patch);

constexpr uint8_t sync = 0xD8;

constexpr size_t word_size = 4;
constexpr size_t id_size = 7;
constexpr size_t head_len  = 4;
constexpr size_t head_size = head_len*word_size;

using id_t =  std::array<char, id_size>; //+1 for null character
using addr_t = uint32_t;
using idx_t = addr_t;
using checksum_t = uint16_t;
using version_t = uint8_t;

inline addr_t ceil_div(addr_t n, addr_t d) {
    return (n + d - 1) / d;
}
inline addr_t ceil_multiple(addr_t n, addr_t mult) {
    return ceil_div(n,mult)*mult;
}
inline addr_t promote_to_sw_w(addr_t w) {
    w = ceil_multiple(w, 8);
    w = std::bit_ceil(w);
    return w;
}

enum class Acc {
    na = 0,
    k,
    ro,
    rc,
    rw,
    wt,
};
std::ostream& operator<<(std::ostream& os, Acc v);

enum class Ass {
    none = -1,
    passed = 0,
    debug,
    info,
    warn,
    error,
    crit,
    fatal
};


enum class ValueKind {
    uint_,
    sint_,
    char_,
    bits_,
    flag_
};

std::string str(Acc v);
std::string str(Ass v);
std::string str(ValueKind v);

using uint_t = uint64_t;
using sint_t = int64_t;

class ValueType {
public:
    ValueType(ValueKind kind, uint width, std::optional<uint> vec_len = {})
        : m_kind(kind)
        , m_width(width)
        , m_vec_len(vec_len)
    { }
    addr_t sw_elem_width() const { return promote_to_sw_w(m_width); }
    addr_t elem_width() const { return m_width; }
    addr_t sw_elem_size() const { return sw_elem_width()/8; }
    ValueKind kind() const { return m_kind; }
    std::string str() const;
    std::optional<uint> vec_len() const { return m_vec_len; }
    bool is_vec() const { return m_vec_len.has_value(); }
    addr_t size() const {
        addr_t s = sw_elem_size();
        if(m_vec_len) { s *= *m_vec_len; }
        return s;
    }
private:
    ValueKind m_kind;
    uint m_width;
    std::optional<uint> m_vec_len;
};

inline ValueType make_ValueType(ValueKind kind, uint width, std::optional<uint> vec_len = {}) {
    ValueType value_type(kind, width, vec_len);
    return value_type;
}

inline id_t id_str_to_id(const std::string & s) {
    if( s.size() > id_size ) {
        throw std::runtime_error("size of id_str too large");
    }
    id_t id{};
    std::memcpy(&id, &s[0], s.size());
    return id;
}
inline std::string id_to_str(id_t id) {
    std::string s(id_size, '\0');
    std::memcpy(&s[0], &id, id_size);
    return s;
}

}

std::ostream& operator<<(std::ostream& os, hdlskel::skmap::Acc v);
std::ostream& operator<<(std::ostream& os, hdlskel::skmap::Ass v);
std::ostream& operator<<(std::ostream& os, hdlskel::skmap::ValueKind v);
