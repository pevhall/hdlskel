#pragma once

#include <functional>
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
    // Called with the address and data of every operation that reaches (or
    // would reach) the device. Mirrors the pre write / post read callback
    // functions of the python Regio (whose signature returns an int that is
    // never used, so this is void).
    using Callback = std::function<void(size_t addr, std::span<const std::byte> data)>;

    // Write/read `data` at `addr`. If an MTU is set and the transfer is
    // larger than it, the operation is split into MTU sized chunks
    // (mirrors write()/read() in pip/regio/src/regio/regio.py).
    void write(size_t addr, std::span<const std::byte> data);
    void read(size_t addr,  std::span<std::byte> data);
    void set_log(std::shared_ptr<std::ostream> log) { m_log = log; }
    virtual ssize_t alignment_size() const { return 1; }

    // Maximum Transmission Unit, used to split operations. nullopt = no split.
    // A zero MTU would make the split loops spin forever, so it is rejected
    // (python's range() step must not be zero either).
    void mtu(std::optional<size_t> mtu) {
        if (mtu.has_value() && *mtu == 0) {
            throw std::invalid_argument("mtu must be greater than zero");
        }
        m_mtu = mtu;
    }
    std::optional<size_t> mtu() const { return m_mtu; }

    // When true, writes are silently dropped instead of hitting the device
    // (same meaning as `_error_on_write` in the python Regio).
    void error_on_write(bool error_on_write) { m_error_on_write = error_on_write; }
    bool error_on_write() const { return m_error_on_write; }

    // python calls these add_pre_write_callback_func / add_post_read_callback_func
    void add_pre_write_callback_func(Callback cb)  { m_pre_write_callback = std::move(cb); }
    void add_post_read_callback_func(Callback cb)  { m_post_read_callback = std::move(cb); }

protected:
    virtual void dev_write(size_t addr, std::span<const std::byte> data) = 0;
    virtual void dev_read(size_t addr, std::span<std::byte> data) = 0;

private:
    std::shared_ptr<std::ostream> m_log;
    std::optional<size_t> m_mtu;
    bool m_error_on_write = false;
    Callback m_pre_write_callback;
    Callback m_post_read_callback;
};

}
