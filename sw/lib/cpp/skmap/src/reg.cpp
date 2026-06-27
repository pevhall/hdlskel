
#include "hdlskel/skmap/reg.hpp"
#include "hdlskel/skmap/module.hpp"
#include <cstring>
// #include <memory>
#include <sstream>
#include <stdexcept>

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

std::span<const std::byte> Reg::cache_data() const { return m_module->cache_data(m_addr_off, size()); }
std::span<      std::byte> Reg::cache_data() { return m_module->cache_data(m_addr_off, size()); }

void Reg::memcpy_from_cache(void* dest) const {
    std::span<const std::byte> data = cache_data();
    std::memcpy(dest, data.data(), data.size());
}

void Reg::memcpy_to_cache(void* src) {
    std::span< std::byte> data = cache_data();
    std::memcpy(data.data(), src, data.size());
}

void Reg::update_cache() { module()->update_cache(m_addr_off, size()); }

void Reg::write_cache() { module()->write_cache(m_addr_off, size()); }

uint_t Reg::read_uint_cached() const {
    if ( size() > sizeof(uint_t) ) {
        std::runtime_error("uint_t not large enough to fit register");
    }
    uint_t value = 0;
    memcpy_from_cache(&value);
    return value;
}

sint_t Reg::read_sint_cached() const {
    if ( size() > sizeof(sint_t) ) {
        std::runtime_error("sint_t not large enough to fit register");
    }
    sint_t value;
    memcpy_from_cache(&value);
    return sint_sign_extend_w(value, elem_w());
}

uint_t Reg::read_uint() {
    if( not cache_only() ) { update_cache(); }
    return read_uint_cached();
}

sint_t Reg::read_sint() {
    if( not cache_only() ) { update_cache(); }
    return read_sint_cached();
}

void Reg::write_uint_cached(uint_t value) { 
    if ( size() > sizeof(uint_t) ) {
        std::runtime_error("uint_t not large enough to fit register");
    }
    memcpy_to_cache(&value);
}
void Reg::write_sint_cached(sint_t value) { 
    if ( size() > sizeof(sint_t) ) {
        std::runtime_error("sint_t not large enough to fit register");
    }
    memcpy_to_cache(&value);
}
void Reg::write_uint(uint_t value) { 
    write_uint_cached(value);
    if( not cache_only() ) { write_cache(); }
}
void Reg::write_sint(sint_t value) { 
    write_sint_cached(value);
    if( not cache_only() ) { write_cache(); }
}
void Reg::write_zero() {
    std::vector<std::byte> z(size(), std::byte{0});
    memcpy_to_cache(&z);
}
std::vector<bool> Reg::read_vec_bool_cached() const {
    std::span<const std::byte> data = cache_data();
    std::vector<bool> vec(elem_w());
    size_t byte = (elem_w()-1) / 8;
    uint8_t bit = (elem_w()-1) % 8;
    for(size_t ii = 0; ii < elem_w(); ii++) {
        uint8_t bit_mask = 1<<bit;
        vec[ii] = (static_cast<uint8_t>(data[byte]) & bit_mask) != 0;
        std::cout << std::hex<<"vec["<<ii<<"] = "<<static_cast<int>(data[byte])<<" & "<< +bit_mask<<"\n"<<std::dec;
        if (bit==0) {
            byte--;
            bit = 7;
        } else { bit--; }
    }
    return vec;
}

std::vector<bool> Reg::read_vec_bool() {
    update_cache();
    return read_vec_bool_cached();
}

std::string Reg::str_value_cached() const {
    std::stringstream ss;
    switch(m_value_type.kind()) {
        case ValueKind::uint_: {
            ss << read_uint_cached();
            break;
        }
        case ValueKind::sint_: {
            ss << read_sint_cached();
            break;
        }
        case ValueKind::char_: { 
            assert(false);
            return "ERROR";
        }
        case ValueKind::bits_: {
            ss << "0x"<< std::hex << read_uint_cached();
            break;
        }
        case ValueKind::flag_: {
            ss << (read_uint_cached() != 0 ? "true" : "false");
            break;
        };
    }
    return ss.str();
}

size_t RegVec::vec_len() const {
    return *m_value_type.vec_len();
}

std::vector<uint_t> RegVec::read_vec_uint_cached() const {
    std::span<const std::byte> data = cache_data();
    std::vector<uint_t> vec(vec_len());
    addr_t v_off = 0;
    for(auto & v : vec) {
        v = 0;
        std::memcpy(&v, &data[v_off], elem_size());
        v_off += elem_size();
    }
    return vec;
}

std::vector<uint_t> RegVec::read_vec_uint() {
    update_cache();
    return read_vec_uint_cached();
}

std::vector<sint_t> RegVec::read_vec_sint_cached() const {
    std::span<const std::byte> data = cache_data();
    std::vector<sint_t> vec(vec_len());
    addr_t v_off = 0;
    for(auto & v : vec) {
        v = 0;
        std::memcpy(&v, &data[v_off], elem_size());
        v_off += elem_size();
        v = sint_sign_extend_w(v, elem_w());
    }
    return vec;
}

std::vector<sint_t> RegVec::read_vec_sint() {
    update_cache();
    return read_vec_sint_cached();
}

std::vector<bool> RegVec::read_vec_bool_cached() const {
    std::span<const std::byte> data = cache_data();
    std::vector<bool> vec(vec_len());
    addr_t b_idx = 0;
    for(addr_t ii = 0; ii < vec_len(); ii++) {
        vec[ii] = (static_cast<uint8_t>(data[b_idx])) != 0;
        b_idx += elem_size();
    }
    return vec;
}

std::vector<bool> RegVec::read_vec_bool() {
    update_cache();
    return read_vec_bool_cached();
}

std::string RegVec::read_str_cached() const {
    if(elem_w() != 8) {
        throw std::runtime_error("Only ASCII strings/characters are supported");
    }
    std::span<const std::byte> data = cache_data();
    std::string str(vec_len(), '\0');
    memcpy(&str[0], &data[0], vec_len());
    return str;
}

std::string RegVec::read_str() {
    update_cache();
    return read_str_cached();
}

void RegVec::write_vec_uint_cache(const  std::vector<uint_t> & vec) {
    std::span<std::byte> data = cache_data();
    addr_t ii = 0;
    for(const uint_t v : vec) {
        std::memcpy(&data[ii++], &v, elem_size());
        ii += elem_size();
    }
}

void RegVec::write_vec_sint_cache(const  std::vector<sint_t> & vec) {
    std::span<std::byte> data = cache_data();
    addr_t ii = 0;
    for(const sint_t v : vec) {
        // v = sint_sign_extend_w(v, elem_w());
        std::memcpy(&data[ii], &v, elem_size());
        ii += elem_size();
    }
}

void RegVec::write_vec_bool_cache(const  std::vector<bool> & vec) {
    std::span<std::byte> data = cache_data();
    addr_t ii = 0;
    for(const bool v : vec) {
        uint_t v_int = static_cast<int>(v);
        std::memcpy(&data[ii], &v_int, elem_size());
        ii += elem_size();
    }
}
void RegVec::write_vec_uint(const  std::vector<uint_t> & vec) {
    write_vec_uint_cache(vec);
    write_cache();
}
void RegVec::write_vec_sint(const  std::vector<sint_t> & vec) {
    write_vec_sint_cache(vec);
    write_cache();
}
void RegVec::write_vec_bool(const std::vector<bool> & vec) {
    write_vec_bool_cache(vec);
    write_cache();
}

void RegVec::memcpy_idx_from_cache(void * dest, addr_t idx) const {
    std::span<const std::byte> data = cache_data();
    std::memcpy(dest, &data[idx*elem_size()], elem_size());
}

void RegVec::memcpy_idx_to_cache(const void * src, addr_t idx) {
    std::span<std::byte> data = cache_data();
    std::memcpy(&data[idx*elem_size()], src, elem_size());
}
void RegVec::update_idx_cache(addr_t idx) {
    addr_t addr = m_addr_off + idx*elem_size();
    module()->update_cache(addr, elem_size());
}

uint_t RegVec::read_idx_uint_cached(addr_t idx) const {
    uint_t val = 0;
    memcpy_idx_from_cache(&val, idx);
    return val;
}

uint_t RegVec::read_idx_uint(addr_t idx) {
    update_idx_cache(idx);
    return read_idx_uint_cached(idx);
}

sint_t RegVec::read_idx_sint_cached(addr_t idx) const {
    sint_t val = 0;
    memcpy_idx_from_cache(&val, idx);
    return val;
}

sint_t RegVec::read_idx_sint(addr_t idx) {
    update_idx_cache(idx);
    return read_idx_sint_cached(idx);
}

void RegVec::write_idx_cache(addr_t idx) {
    addr_t addr = m_addr_off + idx*elem_size();
    module()->write_cache(addr, elem_size());
}
void RegVec::write_idx_uint_cached(addr_t idx, uint_t val) {
    memcpy_idx_to_cache(&val, idx);
}
void RegVec::write_idx_sint_cached(addr_t idx, sint_t val) {
    memcpy_idx_to_cache(&val, idx);
}

void RegVec::write_idx_uint(addr_t idx, uint_t val) {
    write_idx_uint_cached(idx, val);
    write_cache();
}
void RegVec::write_idx_sint(addr_t idx, sint_t val) {
    write_idx_sint_cached(idx, val);
    write_cache();
}
std::string RegVec::str_value_cached() const {
    if (m_value_type.kind() == ValueKind::char_ ) {
        return read_str_cached();
    }
    std::stringstream ss;
    ss << "[";
    switch(m_value_type.kind()) {
        case ValueKind::uint_: {
            const auto vec = read_vec_uint_cached();
            for (auto v : vec) { ss << " " << v; }
            break;
        }
        case ValueKind::sint_: {
            const auto vec = read_vec_sint_cached();
            for (auto v : vec) { ss << " " << v; }
            break;
        }
        case ValueKind::bits_: {
            const auto vec = read_vec_uint_cached();
            ss << std::hex;
            for (auto v : vec) { ss << " " << v; }
            ss << std::dec;
            break;
        }
        case ValueKind::flag_: {
            const auto vec = read_vec_bool_cached();
            for (auto v : vec) { ss << " " << v; }
            break;
        };
        case ValueKind::char_: {
            ss << __FILE__ << ":" << __LINE__ << ": ERROR";
        }
    }
    ss << " ]";
    return ss.str();
}

RFlag::RFlag(const std::string & name, uint bit, Ass ass, const std::string & desc)
:   m_bit(bit)
,   m_ass(ass)
,   m_name(name)
,   m_desc(desc)
{

}

void RFlag::update_reg_cache() { m_reg_flags->update_cache(); }
void RFlag::write_reg_cache() { m_reg_flags->write_cache();}


bool RFlag::read_bool_at_cached(uint bit) const {
    std::span<const std::byte> data = m_reg_flags->cache_data();
    uint byte = bit / 8;
    bit  = bit % 8;
    return (static_cast<uint8_t>(data[byte]) & (1<<bit)) != 0;
}
void RFlag::write_bool_at_cache(uint bit, bool v) {
    std::span<std::byte> data = m_reg_flags->cache_data();
    uint byte = bit / 8;
    uint8_t b  = bit % 8;
    // uint8_t b = v<<bit;
    // uint8_t mask = 1<<bit;
    data[byte] = static_cast<std::byte>(
        (static_cast<uint8_t>(data[byte]) & ~(1<<b)) | (static_cast<uint8_t>(v)<<b)
    );
}
bool RFlag::read_bool_cached() const {
    return read_bool_at_cached(m_bit);
}
bool RFlag::read_bool() {
    update_reg_cache();
    return read_bool_cached();
}
void RFlag::write_bool_cache(bool v) {
    write_bool_at_cache(m_bit, v);
}
Ass RFlag::ass_check_cached() const {
    bool value = read_bool_cached();
    if (value) { return Ass::passed; }
    return m_ass;
}
std::string RFlag::str_value_cached() const {
    std::ostringstream oss;
    ::operator<<(oss, ass()) << ": ";
    oss << (read_bool_cached() != 0 ? " true" : "false");
    return oss.str();
}
bool RFlagVec::read_idx_bool_cached(addr_t idx) const {
    return read_bool_at_cached(m_bit + idx);
}
void RFlagVec::write_idx_bool_cache(addr_t idx, bool v) {
    return write_bool_at_cache(m_bit + idx, v);
}
std::vector<bool> RFlagVec::read_vec_bool_cached() const {
    std::vector<bool> vec(m_vec_size);
    for(addr_t ii = 0; ii < m_vec_size; ii++) {
        vec[ii] = read_idx_bool_cached(ii);
    }
    return vec;
}
std::vector<bool> RFlagVec::read_vec_bool() {
    update_reg_cache();
    return read_vec_bool_cached();
}
void RFlagVec::write_vec_bool_cached(const std::vector<bool> & vec) {
    for(addr_t ii = 0; ii < m_vec_size; ii++) {
        write_idx_bool_cache(ii, vec[ii]);
    }
}
Ass RFlagVec::ass_check_cached() const {
    std::vector<bool> vec = read_vec_bool_cached();
    for(bool v : vec) { if(v) { return m_ass; } };
    return Ass::passed;
}

std::string RFlagVec::str_value_cached() const {
    std::ostringstream oss;
    ::operator<<(oss, ass()) << ": ";
    oss << "0b";
    for( bool v : read_vec_bool_cached() ) {
        oss << static_cast<int>(v);
    }
    return oss.str();
}

Ass RegFlags::ass_check_cached() const {
    Ass ass = Ass::none;
    for( const auto & f : m_flags) {
        Ass f_ass = f->ass_check_cached();
        if (f_ass > ass ) { ass = f_ass; }
    }
    return ass;
}

std::string RegFlags::str_value_cached() const {
    std::ostringstream oss;
    oss << "0b";
    for( bool v : read_vec_bool_cached() ) {
        oss << static_cast<int>(v);
    }
    return oss.str();
}

Ass RegFlags::ass_check() {
    update_cache();
    return ass_check_cached();
}

}
