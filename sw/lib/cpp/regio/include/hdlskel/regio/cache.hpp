#pragma once

// C++ mirror of pip/regio/src/regio/cache.py
//
// Implements RegioCache, a Regio backed by a sparse memory cache.
//
// - Writes are stored as an ordered list of (address, data) "regions".
// - Overlapping or byte-adjacent writes are automatically merged into a
//   single region.
// - Reads reconstruct requested bytes from whatever region covers the
//   requested range; any bytes not covered by a region raise an error.
// - The whole cache can be serialized to / loaded from a simple custom
//   binary file format:
//
//     Header:
//         ascii "skelregi"      (8 bytes, no null terminator)
//                            (short for hdlskel register file map)
//     Then, repeated until EOF, one entry per stored region:
//         uint32_t address           (little-endian)
//         uint32_t size              (little-endian)
//         uint8_t  data[size]

#include "hdlskel/regio/regio.hpp"

#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace hdlskel::regio {

constexpr uint32_t REGIO_UINT32_MAX = 0xFFFF'FFFF;

constexpr const char* CACHE_FILE_HEADER    = "skelregi";
constexpr const char* CACHE_FILE_EXTENSION = "skelregio";

class CacheError : public std::runtime_error {
public:
    CacheError(const std::string& m) : std::runtime_error(m) { }
};

class RegioCache : public Regio {

public:
    using Region = std::pair<size_t, std::vector<std::byte>>;

    RegioCache() = default;

    // --- non async version of read and write ---
    void cache_write(size_t addr, std::span<const std::byte> data);
    std::vector<std::byte> cache_read(size_t addr, size_t size) const;

    // Convenience overload for byte buffers.
    void cache_write(size_t addr, const std::vector<uint8_t>& data) {
        cache_write(addr, std::span<const std::byte>(
            reinterpret_cast<const std::byte*>(data.data()), data.size()));
    }

    // Snapshot of the current regions, sorted by address.
    std::vector<Region> regions() const { return m_regions; }
    void clear() { m_regions.clear(); }
    // e.g. RegioCache(0x0+28, 0x10000+24)
    std::string to_str() const;

    void save_to_file(const std::string& path) const;
    // If replace (default) any existing cached data is discarded first,
    // otherwise the loaded regions are merged in using normal write rules.
    void load_from_file(const std::string& path, bool replace = true);

    static void validate_addr_size(size_t addr, size_t size);

protected:
    void dev_write(size_t addr, std::span<const std::byte> data) override {
        cache_write(addr, data);
    }
    void dev_read(size_t addr, std::span<std::byte> data) override {
        auto rd = cache_read(addr, data.size());
        std::copy(rd.begin(), rd.end(), data.begin());
    }

private:
    // Perform a write and merge regions if required.
    void merge_write(size_t addr, std::span<const std::byte> data);

    std::vector<Region> m_regions;
};

}
