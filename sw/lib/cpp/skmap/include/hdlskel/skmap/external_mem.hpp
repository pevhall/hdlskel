#pragma once

#include "hdlskel/skmap/basic_types.hpp"
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace hdlskel::regio {
class Regio;
}

namespace hdlskel::skmap {

// A memory interface external to the module register map.
// Mirrors ExternalMem/ExternalMemCached in pip/skmap/src/skmap/external_mem.py
// The base_addr is an absolute (regio) address given by the module sub head.
class ExternalMem {
public:
    ExternalMem(std::shared_ptr<regio::Regio> regio, addr_t base_addr, addr_t size, Acc acc = Acc::na)
    :   m_regio(regio)
    ,   m_base_addr(base_addr)
    ,   m_size(size)
    ,   m_acc(acc)
    ,   m_cache(size)
    { }

    // Set the details of this mem from a generated module.
    void details(const std::string & name, ValueType value_type, Acc acc, const std::string & desc);

    std::string name() const;
    ValueType value_type() const;
    std::string desc() const;
    Acc acc() const { return m_acc; }
    addr_t base_addr() const { return m_base_addr; }
    addr_t size() const { return m_size; }

    // Read/write to the cache only
    void write_cached(addr_t addr, const std::vector<uint8_t> & data);
    std::vector<uint8_t> read_cached(addr_t addr, addr_t size) const;

    // Read/write to the device and update the cache
    void write(addr_t addr, const std::vector<uint8_t> & data);
    std::vector<uint8_t> read(addr_t addr, addr_t size);

private:
    void check_size(addr_t addr, addr_t size) const;

    std::shared_ptr<regio::Regio> m_regio;
    addr_t m_base_addr;
    addr_t m_size;
    Acc m_acc;
    std::string m_name;
    std::optional<ValueType> m_value_type;
    std::string m_desc;
    std::vector<std::byte> m_cache;
};

}
