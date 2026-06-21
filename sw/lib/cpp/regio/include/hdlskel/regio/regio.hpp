#pragma once

// #include <optional>
#include <memory>
#include <ostream>
#include <stddef.h>
#include <span>

namespace hdlskel::regio {

class Regio {

public:
    void write(size_t addr, std::span<const std::byte> data);
    void read(size_t addr,  std::span<std::byte> data);
    void set_log(std::shared_ptr<std::ostream> log) { m_log = log; }

protected:
    virtual void dev_write(size_t addr, std::span<const std::byte> data) = 0;
    virtual void dev_read(size_t addr, std::span<std::byte> data) = 0;

private:
    std::shared_ptr<std::ostream> m_log;
    //bool m_print_dev_ops;
};

}
