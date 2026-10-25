#include "hdlskel/skmap/external_mem.hpp"
#include "hdlskel/regio/regio.hpp"
#include <cassert>
#include <cstring>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace {

using namespace hdlskel::skmap;

std::vector<std::byte> to_bytes(const std::vector<uint8_t> & v) {
    std::vector<std::byte> b(v.size());
    std::memcpy(b.data(), v.data(), v.size());
    return b;
}
std::vector<uint8_t> from_bytes(const std::vector<std::byte> & b) {
    std::vector<uint8_t> v(b.size());
    std::memcpy(v.data(), b.data(), b.size());
    return v;
}

}

namespace hdlskel::skmap {

void ExternalMem::details(const std::string & name, ValueType value_type, Acc acc, const std::string & desc) {
    // Mirrors ExternalMem.details(): the configured type must describe the
    // whole memory.
    if (m_size != value_type.size()) {
        std::ostringstream oss;
        oss << "ExternalMem \"" << name << "\" size mismatch, mem is " << m_size
            << " B, value type is " << value_type.size() << " B";
        throw std::runtime_error(oss.str());
    }
    if (m_acc == Acc::na) {
        m_acc = acc;
    } else if (m_acc != acc) {
        throw std::runtime_error("ExternalMem \"" + name + "\" access mismatch");
    }
    m_name = name;
    m_value_type = value_type;
    m_desc = desc;
}

std::string ExternalMem::name() const {
    if (m_name.empty()) {
        throw std::runtime_error("ExternalMem name not set (no details)");
    }
    return m_name;
}
ValueType ExternalMem::value_type() const {
    if (!m_value_type.has_value()) {
        throw std::runtime_error("ExternalMem value type not set (no details)");
    }
    return *m_value_type;
}
std::string ExternalMem::desc() const {
    if (m_desc.empty()) {
        throw std::runtime_error("ExternalMem desc not set (no details)");
    }
    return m_desc;
}

void ExternalMem::check_size(addr_t addr, addr_t size) const {
    if (addr + size > m_size) {
        std::ostringstream oss;
        oss << "ExternalMem at 0x" << std::hex << m_base_addr << std::dec
            << ": addr 0x" << std::hex << addr << std::dec << " + size " << size
            << " is out of range (mem size " << m_size << ")";
        throw std::runtime_error(oss.str());
    }
}

void ExternalMem::check_cached() const {
    if (!is_cached()) {
        throw std::runtime_error("ExternalMem is not cached (too large), cannot use the cached accessors");
    }
}

addr_t ExternalMem::elem_size() const {
    return value_type().sw_elem_size();
}

addr_t ExternalMem::vec_len() const {
    if (!m_value_type.has_value() || !m_value_type->is_vec()) {
        throw std::runtime_error("ExternalMem value type is not a vector");
    }
    return *m_value_type->vec_len();
}

void ExternalMem::check_idx(addr_t idx) const {
    // Mirrors the `assert idx < len(self)` style checks in python
    if (idx >= vec_len()) {
        throw std::runtime_error("ExternalMem index " + std::to_string(idx) + " out of range (len " + std::to_string(vec_len()) + ")");
    }
}

addr_t ExternalMem::idx_addr(addr_t idx) const {
    check_idx(idx);
    return elem_size() * idx;
}

void ExternalMem::write_cached(addr_t addr, const std::vector<uint8_t> & data) {
    check_size(addr, data.size());
    check_cached();
    std::memcpy(&m_cache[addr], data.data(), data.size());
}

std::vector<uint8_t> ExternalMem::read_cached(addr_t addr, addr_t size) const {
    check_size(addr, size);
    check_cached();
    std::vector<uint8_t> v(size);
    std::memcpy(v.data(), &m_cache[addr], size);
    return v;
}

void ExternalMem::write(addr_t addr, const std::vector<uint8_t> & data) {
    check_size(addr, data.size());
    m_regio->write(m_base_addr + addr, to_bytes(data));
    // Only update the cache when there is one (python has a separate
    // ExternalMemCached sub class for that).
    if (is_cached()) {
        write_cached(addr, data);
    }
}

std::vector<uint8_t> ExternalMem::read(addr_t addr, addr_t size) {
    check_size(addr, size);
    std::vector<std::byte> data(size);
    m_regio->read(m_base_addr + addr, data);
    const std::vector<uint8_t> data_u8 = from_bytes(data);
    if (is_cached()) {
        write_cached(addr, data_u8);
    }
    return data_u8;
}

// --- Vector (element) access, mirrors ExternalMemVec ---

std::vector<uint8_t> ExternalMem::read_idx_bytes_cached(addr_t idx) const {
    return read_cached(idx_addr(idx), elem_size());
}

std::vector<uint8_t> ExternalMem::read_idx_bytes(addr_t idx) {
    addr_t addr = idx_addr(idx);
    return read(addr, elem_size());
}

uint_t ExternalMem::read_idx_uint_cached(addr_t idx) const {
    const std::vector<uint8_t> b = read_idx_bytes_cached(idx);
    uint_t value = 0;
    std::memcpy(&value, b.data(), std::min<size_t>(b.size(), sizeof(uint_t)));
    return mask_to_width(value, value_type().elem_width());
}

uint_t ExternalMem::read_idx_uint(addr_t idx) {
    read_idx_bytes(idx);
    return read_idx_uint_cached(idx);
}

sint_t ExternalMem::read_idx_sint_cached(addr_t idx) const {
    return static_cast<sint_t>(sint_sign_extend(read_idx_uint_cached(idx), value_type().elem_width()));
}

sint_t ExternalMem::read_idx_sint(addr_t idx) {
    read_idx_bytes(idx);
    return read_idx_sint_cached(idx);
}

void ExternalMem::write_idx_bytes_cached(addr_t idx, const std::vector<uint8_t> & data) {
    // Mirrors `assert(len(b) == self.elem_size)`
    if (data.size() != static_cast<size_t>(elem_size())) {
        throw std::runtime_error("ExternalMem write_idx_bytes: data size " + std::to_string(data.size()) + " != elem size " + std::to_string(elem_size()));
    }
    write_cached(idx_addr(idx), data);
}

void ExternalMem::write_idx_bytes(addr_t idx, const std::vector<uint8_t> & data) {
    write_idx_bytes_cached(idx, data);
    write_idx_cache(idx);
}

void ExternalMem::write_idx_uint_cached(addr_t idx, uint_t val) {
    addr_t elem = elem_size();
    if (elem > sizeof(uint_t)) {
        throw std::runtime_error("ExternalMem element is wider than uint_t");
    }
    std::vector<uint8_t> b(elem, 0);
    std::memcpy(b.data(), &val, elem);
    write_idx_bytes_cached(idx, b);
}

void ExternalMem::write_idx_uint(addr_t idx, uint_t val) {
    write_idx_uint_cached(idx, val);
    write_idx_cache(idx);
}

void ExternalMem::write_idx_sint_cached(addr_t idx, sint_t val) {
    write_idx_uint_cached(idx, static_cast<uint_t>(val));
}

void ExternalMem::write_idx_sint(addr_t idx, sint_t val) {
    write_idx_sint_cached(idx, val);
    write_idx_cache(idx);
}

void ExternalMem::write_idx_cache(addr_t idx) {
    const std::vector<uint8_t> b = read_idx_bytes_cached(idx);
    write(idx_addr(idx), b);
}

std::string ExternalMem::read_idx_value_str_cached(addr_t idx) const {
    // Mirrors ExternalMemVec.read_idx_rich_str_cached: base 16 for bits
    // (zero padded to ceil(width/4) digits), decimal otherwise.
    const ValueType t = value_type();
    switch (t.kind()) {
        case ValueKind::uint_:
        case ValueKind::bits_: break;
        case ValueKind::sint_: {
            return std::to_string(read_idx_sint_cached(idx));
        }
        case ValueKind::flag_:
        case ValueKind::char_:
            throw std::runtime_error("ExternalMem index values are not supported for flag/char types");
    }
    uint_t value = read_idx_uint_cached(idx);
    std::ostringstream oss;
    if (t.kind() == ValueKind::bits_) {
        oss << "0x" << std::uppercase << std::hex << std::setfill('0')
            << std::setw(static_cast<int>(ceil_div(t.elem_width(), addr_t{4}))) << value;
    } else {
        oss << value;
    }
    return oss.str();
}

}
