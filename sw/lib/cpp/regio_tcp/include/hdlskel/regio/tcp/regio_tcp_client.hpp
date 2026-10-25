#pragma once

#include "hdlskel/regio/regio.hpp"
#include "hdlskel/regio/tcp/regio_tcp.hpp"

#include <stddef.h>
#include <span>
#include <string>

namespace hdlskel::regio::tcp {

// Synchronous version of RegioTcpClient in pip/regio/src/regio/tcp_client.py
class RegioTcpClient : public Regio {

public:
    RegioTcpClient(const std::string& host, uint16_t port = PORT_DEFAULT, double timeout_s = TIMEOUT_DEFAULT_S);
    ~RegioTcpClient();

    // Mirrors check_size / check_addr in the python client: the head only has
    // 16 bits for the size and 32 for the address, and a zero size transfer is
    // rejected as well.
    static void check_size(size_t size);
    static void check_addr(size_t addr);

protected:
    void dev_write(size_t addr, std::span<const std::byte> data) override;
    void dev_read(size_t addr, std::span<std::byte> data) override;

private:
    int sockfd = -1;
    double m_timeout_s;

    void connect_to_server(const std::string& host, uint16_t port);
    void set_timeout(double timeout_s);
    void send_all(const void* data, size_t len);
    void recv_all(void* data, size_t len);
};


}
