#pragma once

// #include <optional>
#include <memory>
#include <ostream>
#include <stddef.h>
#include <span>

namespace hdlskel::regio {

class ReadError : public std::runtime_error {
public:
    ReadError(const char* m) : std::runtime_error(m) { }
};

class Regio {

public:
    void write(size_t addr, std::span<const std::byte> data);
    void read(size_t addr,  std::span<std::byte> data);
    void set_log(std::shared_ptr<std::ostream> log) { m_log = log; }
    virtual ssize_t alignment_size() const { return 1; }

protected:
    virtual void dev_write(size_t addr, std::span<const std::byte> data) = 0;
    virtual void dev_read(size_t addr, std::span<std::byte> data) = 0;
    void dev_max_size(size_t max){ m_dev_max_size = max; }

private:
    std::shared_ptr<std::ostream> m_log;
    size_t m_dev_max_size = SIZE_MAX;
    //bool m_print_dev_ops;
};

}
