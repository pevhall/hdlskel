#include "hdlskel/regio/cache.hpp"

#include <algorithm>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <sstream>

namespace hdlskel::regio {

namespace {

// Regions are packed as little-endian uint32 address + uint32 size
constexpr size_t REGION_HDR_SIZE = 8;

void put_u32_le(std::vector<char>& out, uint32_t v) {
    for (unsigned ii = 0; ii < 4; ii++) {
        out.push_back(static_cast<char>((v >> (8 * ii)) & 0xFF));
    }
}

uint32_t get_u32_le(const char* p) {
    uint32_t v = 0;
    for (unsigned ii = 0; ii < 4; ii++) {
        v |= static_cast<uint32_t>(static_cast<uint8_t>(p[ii])) << (8 * ii);
    }
    return v;
}

}

void RegioCache::validate_addr_size(size_t addr, size_t size) {
    if (addr > REGIO_UINT32_MAX || (addr + size) > (static_cast<size_t>(REGIO_UINT32_MAX) + 1)) {
        throw CacheError("addr/size exceed 32-bit address space");
    }
}

void RegioCache::cache_write(size_t addr, std::span<const std::byte> data) {
    validate_addr_size(addr, data.size());
    if (data.empty()) {
        return;
    }
    merge_write(addr, data);
}

std::vector<std::byte> RegioCache::cache_read(size_t addr, size_t size) const {
    validate_addr_size(addr, size);
    if (size == 0) {
        return {};
    }

    const size_t read_start = addr;
    const size_t read_end   = addr + size;

    if (m_regions.empty()) {
        throw CacheError("Not all data has been previously written");
    }

    // Same lookup as bisect_left(starts, read_start) in python.
    auto it = std::lower_bound(
        m_regions.begin(), m_regions.end(), read_start,
        [](const Region& r, size_t v) { return r.first < v; });
    if (it == m_regions.end() || (it != m_regions.begin() && it->first != read_start)) {
        --it;
    }

    const size_t rstart = it->first;
    const size_t rend   = rstart + it->second.size();
    if (read_end > rend || read_start < rstart) {
        std::ostringstream oss;
        oss << read_end << " > " << rend << " or " << read_start << " < " << rstart;
        throw CacheError("Not all data has been previously written (" + oss.str() + ")");
    }

    const size_t off = read_start - rstart;
    return std::vector<std::byte>(it->second.begin() + off,
                                  it->second.begin() + off + size);
}

void RegioCache::merge_write(size_t addr, std::span<const std::byte> data) {
    const size_t new_start = addr;
    const size_t new_end   = addr + data.size();

    size_t merged_start = new_start;
    size_t merged_end   = new_end;

    std::vector<const Region*> overlapping;
    std::vector<Region> remaining;

    for (const auto& region : m_regions) {
        const size_t rstart = region.first;
        const size_t rend   = rstart + region.second.size();
        // Touching (rend == new_start or rstart == new_end) counts
        // as adjacent and must be merged, hence strict < / > below.
        if (rend < new_start || rstart > new_end) {
            remaining.push_back(region);
        } else {
            overlapping.push_back(&region);
            merged_start = std::min(merged_start, rstart);
            merged_end   = std::max(merged_end, rend);
        }
    }

    std::vector<std::byte> merged_buf(merged_end - merged_start, std::byte{0});

    // Lay down old (overlapping) data first...
    for (const auto* region : overlapping) {
        const size_t off = region->first - merged_start;
        std::copy(region->second.begin(), region->second.end(),
                  merged_buf.begin() + off);
    }

    // ...then overlay the new write so it takes precedence on overlapping bytes.
    const size_t off = new_start - merged_start;
    std::copy(data.begin(), data.end(), merged_buf.begin() + off);

    remaining.push_back({merged_start, std::move(merged_buf)});
    std::sort(remaining.begin(), remaining.end(),
              [](const Region& a, const Region& b) { return a.first < b.first; });
    m_regions = std::move(remaining);
}

std::string RegioCache::to_str() const {
    std::ostringstream oss;
    oss << "RegioCache(";
    for (size_t ii = 0; ii < m_regions.size(); ii++) {
        if (ii) { oss << ", "; }
        oss << "0x" << std::hex << m_regions[ii].first << std::dec
            << "+" << m_regions[ii].second.size();
    }
    oss << ")";
    return oss.str();
}

void RegioCache::save_to_file(const std::string& path) const {
    std::ofstream f(path, std::ios::binary | std::ios::trunc);
    if (!f) {
        throw CacheError("Could not open '" + path + "' for writing");
    }
    f.write(CACHE_FILE_HEADER, std::strlen(CACHE_FILE_HEADER));
    for (const auto& [addr, data] : m_regions) {
        if (data.size() > REGIO_UINT32_MAX) {
            throw CacheError("region too large to serialize (>4GiB)");
        }
        std::vector<char> hdr;
        hdr.reserve(REGION_HDR_SIZE);
        put_u32_le(hdr, static_cast<uint32_t>(addr));
        put_u32_le(hdr, static_cast<uint32_t>(data.size()));
        f.write(hdr.data(), hdr.size());
        if (!data.empty()) {
            f.write(reinterpret_cast<const char*>(data.data()),
                    static_cast<std::streamsize>(data.size()));
        }
    }
    if (!f) {
        throw CacheError("Failed writing '" + path + "'");
    }
}

void RegioCache::load_from_file(const std::string& path, bool replace) {
    std::ifstream f(path, std::ios::binary);
    if (!f) {
        throw CacheError("Could not open '" + path + "' for reading");
    }

    const size_t header_size = std::strlen(CACHE_FILE_HEADER);
    std::vector<char> header(header_size);
    f.read(header.data(), static_cast<std::streamsize>(header_size));
    if (f.gcount() != static_cast<std::streamsize>(header_size)
        || std::memcmp(header.data(), CACHE_FILE_HEADER, header_size) != 0) {
        throw CacheError(std::string("Not a valid regio cache file (bad header, expected '")
                         + CACHE_FILE_HEADER + "')");
    }

    std::vector<Region> loaded;
    std::vector<char> hdr(REGION_HDR_SIZE);
    while (true) {
        f.read(hdr.data(), REGION_HDR_SIZE);
        if (f.gcount() == 0) {
            break;   // EOF
        }
        if (f.gcount() != static_cast<std::streamsize>(REGION_HDR_SIZE)) {
            throw CacheError("Truncated file: incomplete region header");
        }
        const size_t addr = get_u32_le(hdr.data());
        const size_t size = get_u32_le(hdr.data() + 4);
        std::vector<std::byte> data(size);
        if (size) {
            f.read(reinterpret_cast<char*>(data.data()),
                   static_cast<std::streamsize>(size));
            if (f.gcount() != static_cast<std::streamsize>(size)) {
                throw CacheError("Truncated file: incomplete region data");
            }
        }
        loaded.push_back({addr, std::move(data)});
    }

    if (replace) {
        m_regions = std::move(loaded);
    } else {
        for (auto& [addr, data] : loaded) {
            merge_write(addr, std::span<const std::byte>(data));
        }
    }
}

}
