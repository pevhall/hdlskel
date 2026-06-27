
#include "hdlskel/skmap/reg.hpp"
#include "hdlskel/skmap/module.hpp"
#include <cstring>
#include <sstream>

namespace {

using sint_t = hdlskel::skmap::sint_t;
inline sint_t sint_sign_extend_w(sint_t value, int w) {
    sint_t mask = 1 << ( w - 1);
    return (value & (mask - 1)) - (value & mask);
}

}

namespace hdlskel::skmap {

Reg::Reg(const std::string & name, Acc acc, ValueType value_type, const std::string & desc)
    : m_value_type(value_type) 
    , m_acc(acc) 
    , m_name(name) 
    , m_desc(desc) 
{ }

void Reg::initalise(Module* module, addr_t addr_off) {
    m_module = module;
    m_addr_off   = addr_off;
}
addr_t Reg::addr() const { return (module()->base_addr()) + m_addr_off; }

bool Reg::cache_only() const { return module()->cache_only(); }

std::span<std::byte> Reg::cache_data() const { return m_module->cache_data(m_addr_off, size()); }

void Reg::memcpy_from_cache(void* dest) const {
    auto data = cache_data();
    std::memcpy(dest, data.data(), data.size());
}

void Reg::memcpy_to_cache(void* src) const {
    auto data = cache_data();
    std::memcpy(data.data(), src, data.size());
}

void Reg::update_cache() { module()->update_cache(m_addr_off, size()); }

void Reg::write_cache() { module()->write_cache(m_addr_off, size()); }

uint_t Reg::value_uint_cached() const {
    uint_t value = 0;
    memcpy_from_cache(&value);
    return value;
}

sint_t Reg::value_sint_cached() const {
    sint_t value;
    memcpy_from_cache(&value);
    return sint_sign_extend_w(value, elem_w());
}

uint_t Reg::value_uint() {
    if( not cache_only() ) { update_cache(); }
    return value_uint_cached();
}

sint_t Reg::value_sint() {
    if( not cache_only() ) { update_cache(); }
    return value_sint_cached();
}

void Reg::value_uint_cached(uint_t value) const { 
    memcpy_to_cache(&value);
}
void Reg::value_sint_cached(sint_t value) const { 
    memcpy_to_cache(&value);
}
void Reg::value_uint(uint_t value) { 
    value_uint_cached(value);
    if( not cache_only() ) { write_cache(); }
}
void Reg::value_sint(sint_t value) { 
    value_sint_cached(value);
    if( not cache_only() ) { write_cache(); }
}

std::string Reg::str_value_cached() const {
    std::stringstream ss;
    switch(m_value_type.kind()) {
        case ValueKind::uint_: {
            ss << value_uint_cached();
            break;
        }
        case ValueKind::sint_: {
            ss << value_sint_cached();
            break;
        }
        case ValueKind::char_: { 
            assert(false);
            return "ERROR";
        }
        case ValueKind::bits_: {
            ss << "0x"<< std::hex << value_uint_cached();
            break;
        }
        case ValueKind::flag_: {
            ss << (value_uint_cached() != 0 ? "true" : "false");
            break;
        };
    }
    return ss.str();
}


}
