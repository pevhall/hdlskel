#pragma once

#include <memory>
#include <optional>
#include <ostream>
#include <stddef.h>
#include <span>
#include <stdexcept>

namespace hdlskel::regio {

class ReadError : public std::runtime_error {
public:
    ReadError(const char* m) : std::runtime_error(m) { }
};

class Regio {

public:
    // Write/read `data` at `addr`. If an MTU is set and the transfer is
    // larger than it, the operation is split into MTU sized chunks
    // (mirrors write()/read() in pip/regio/src/regio/regio.py).
    void write(size_t addr, std::span<const std::byte> data);
    void read(size_t addr,  std::span<std::byte> data);
    void set_log(std::shared_ptr<std::ostream> log) { m_log = log; }
    virtual ssize_t alignment_size() const { return 1; }

    // Maximum Transmission Unit, used to split operations. nullopt = no split.
    void mtu(std::optional<size_t> mtu) { m_mtu = mtu; }
    std::optional<size_t> mtu() const { return m_mtu; }

    // When true, writes are silently dropped instead of hitting the device
    // (same meaning as `_error_on_write` in the python Regio).
    void error_on_write(bool error_on_write) { m_error_on_write = error_on_write; }
    bool error_on_write() const { return m_error_on_write; }

protected:
    virtual void dev_write(size_t addr, std::span<const std::byte> data) = 0;
    virtual void dev_read(size_t addr, std::span<std::byte> data) = 0;
    void dev_max_size(size_t max){ m_dev_max_size = max; }

private:
    std::shared_ptr<std::ostream> m_log;
    size_t m_dev_max_size = SIZE_MAX;
    std::optional<size_t> m_mtu;
    bool m_error_on_write = false;
    //bool m_print_dev_ops;
};

}
