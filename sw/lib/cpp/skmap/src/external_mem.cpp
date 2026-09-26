#include "hdlskel/skmap/external_mem.hpp"
#include "hdlskel/regio/regio.hpp"
#include <cassert>
#include <cstring>
#include <stdexcept>

namespace {

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
    assert(m_size == value_type.size());
    if (m_acc == Acc::na) {
        m_acc = acc;
    } else {
        assert(m_acc == acc);
    }
    m_name = name;
    m_value_type = value_type;
    m_desc = desc;
}

std::string ExternalMem::name() const {
    assert(m_name.size());
    return m_name;
}
ValueType ExternalMem::value_type() const {
    assert(m_value_type.has_value());
    return *m_value_type;
}
std::string ExternalMem::desc() const {
    assert(m_desc.size());
    return m_desc;
}

void ExternalMem::check_size(addr_t addr, addr_t size) const {
    if (addr + size > m_size) {
        throw std::runtime_error("ExternalMem::check_size: addr + size out of range");
    }
}

void ExternalMem::write_cached(addr_t addr, const std::vector<uint8_t> & data) {
    check_size(addr, data.size());
    std::memcpy(&m_cache[addr], data.data(), data.size());
}

std::vector<uint8_t> ExternalMem::read_cached(addr_t addr, addr_t size) const {
    check_size(addr, size);
    std::vector<uint8_t> v(size);
    std::memcpy(v.data(), &m_cache[addr], size);
    return v;
}

void ExternalMem::write(addr_t addr, const std::vector<uint8_t> & data) {
    check_size(addr, data.size());
    m_regio->write(m_base_addr + addr, to_bytes(data));
    write_cached(addr, data);
}

std::vector<uint8_t> ExternalMem::read(addr_t addr, addr_t size) {
    check_size(addr, size);
    std::vector<std::byte> data(size);
    m_regio->read(m_base_addr + addr, data);
    const std::vector<uint8_t> data_u8 = from_bytes(data);
    write_cached(addr, data_u8);
    return data_u8;
}

}
