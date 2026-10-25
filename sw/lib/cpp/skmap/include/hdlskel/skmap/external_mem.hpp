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

// External memories bigger than this are not cached (mirrors the
// maximum_external_mem_cache_size argument of Module.__init__ in
// pip/skmap/src/skmap/module.py, which defaults to 1 MiB).
constexpr addr_t maximum_external_mem_cache_size_default = 1024*1024;

// A memory interface external to the module register map.
// Mirrors ExternalMem / ExternalMemCached / ExternalMemVec in
// pip/skmap/src/skmap/external_mem.py.
// The base_addr is an absolute (regio) address given by the module sub head.
//
// The whole memory is cached when it is small enough (python's
// ExternalMemCached), otherwise the cache is not allocated at all and only
// direct device access works (python's plain ExternalMem).
//
// Note: reads and writes go through Regio::read/write (not the raw
// dev_read/dev_write python uses) so that MTU splitting and regio logging
// also apply to external memories.
class ExternalMem {
public:
    ExternalMem(std::shared_ptr<regio::Regio> regio, addr_t base_addr, addr_t size, Acc acc = Acc::na,
                addr_t maximum_cache_size = maximum_external_mem_cache_size_default)
    :   m_regio(regio)
    ,   m_base_addr(base_addr)
    ,   m_size(size)
    ,   m_acc(acc)
    {
        // python: `if size_bytes <= maximum_external_mem_cache_size`
        if (size <= maximum_cache_size) {
            m_cache.resize(size);
        }
    }

    // Set the details of this mem from a generated module.
    void details(const std::string & name, ValueType value_type, Acc acc, const std::string & desc);
    bool has_details() const { return m_value_type.has_value(); }

    std::string name() const;
    ValueType value_type() const;
    std::string desc() const;
    Acc acc() const { return m_acc; }
    addr_t base_addr() const { return m_base_addr; }
    addr_t size() const { return m_size; }

    // True when this memory is cached at all, mirrors python having an
    // ExternalMemCached (vs a plain ExternalMem) instance.
    bool is_cached() const { return not m_cache.empty(); }
    // python's ExternalMemCached.cache_loaded, true as soon as the cache
    // exists (it is allocated zero initialised and filled on first read).
    bool cache_loaded() const { return is_cached(); }

    // Read/write to the cache only
    void write_cached(addr_t addr, const std::vector<uint8_t> & data);
    std::vector<uint8_t> read_cached(addr_t addr, addr_t size) const;

    // Read/write to the device and update the cache
    void write(addr_t addr, const std::vector<uint8_t> & data);
    std::vector<uint8_t> read(addr_t addr, addr_t size);

    // --- Vector (element) access, mirrors ExternalMemVec ---
    // Only meaningful once details() has been called with a vector type.
    addr_t elem_size() const;
    addr_t vec_len() const;

    std::vector<uint8_t> read_idx_bytes_cached(addr_t idx) const;
    std::vector<uint8_t> read_idx_bytes(addr_t idx);
    uint_t read_idx_uint_cached(addr_t idx) const;
    uint_t read_idx_uint(addr_t idx);
    sint_t read_idx_sint_cached(addr_t idx) const;
    sint_t read_idx_sint(addr_t idx);

    void write_idx_bytes_cached(addr_t idx, const std::vector<uint8_t> & data);
    void write_idx_bytes(addr_t idx, const std::vector<uint8_t> & data);
    void write_idx_uint_cached(addr_t idx, uint_t val);
    void write_idx_uint(addr_t idx, uint_t val);
    void write_idx_sint_cached(addr_t idx, sint_t val);
    void write_idx_sint(addr_t idx, sint_t val);
    // Write the cached element back to the device
    void write_idx_cache(addr_t idx);

    // String of this memory as configured, mirrors
    // ExternalMemVec.read_idx_rich_str_cached
    std::string read_idx_value_str_cached(addr_t idx) const;

private:
    void check_size(addr_t addr, addr_t size) const;
    void check_cached() const;
    void check_idx(addr_t idx) const;
    addr_t idx_addr(addr_t idx) const;

    std::shared_ptr<regio::Regio> m_regio;
    addr_t m_base_addr;
    addr_t m_size;
    Acc m_acc;
    std::string m_name;
    std::optional<ValueType> m_value_type;
    std::string m_desc;
    // Empty when the memory is too large to cache (see is_cached())
    std::vector<std::byte> m_cache;
};

}
