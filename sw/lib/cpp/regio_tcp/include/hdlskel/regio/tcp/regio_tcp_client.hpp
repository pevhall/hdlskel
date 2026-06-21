#pragma once

#include "hdlskel/regio/regio.hpp"
// #include "hdlskel/regio/tcp/regio_tcp.hpp"

#include <stddef.h>
#include <span>

namespace hdlskel::regio::tcp {

class RegioTcpClient : public Regio {

public:
    RegioTcpClient(const std::string& host, uint16_t port);
    ~RegioTcpClient();

protected:
    void dev_write(size_t addr, std::span<const std::byte> data) override;
    void dev_read(size_t addr, std::span<std::byte> data) override;
    //bool m_print_dev_ops;

private:
    int sockfd;

    void connect_to_server(const std::string& host, uint16_t port);
    void send_all(const void* data, size_t len);
    void recv_all(void* data, size_t len);
};


}
