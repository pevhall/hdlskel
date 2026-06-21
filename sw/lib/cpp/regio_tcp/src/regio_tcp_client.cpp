#include "hdlskel/regio/tcp/regio_tcp.hpp"
#include "hdlskel/regio/tcp/regio_tcp_client.hpp"

#include <arpa/inet.h>
#include <unistd.h>
#include <stdexcept>
#include <cstring>


namespace hdlskel::regio::tcp {

void RegioTcpClient::dev_write(size_t addr, std::span<const std::byte> data) {
    RqstHead rqst_head;
    rqst_head.sync = RQST_SYNC;
    rqst_head.flag_we = 1;
    rqst_head.size = data.size();
    rqst_head.addr = addr;

    send_all(&rqst_head, sizeof(rqst_head));
    send_all(data.data(), data.size());

    // // Receive reply header
    // struct __attribute__((packed)) {
    //     uint8_t sync;
    //     uint8_t error;
    //     uint16_t size;
    //     uint32_t addr;
    // } reply;
    //
    // recv_all(&reply, sizeof(reply));
    //
    // if (reply.sync != RPLY_SYNC)
    //     throw std::runtime_error("Bad reply sync");
    //
    // if (reply.error != 0)
    //     throw std::runtime_error("Write error from server");
}

void RegioTcpClient::dev_read(size_t addr, std::span<std::byte> data) {

    RqstHead rqst_head;
    rqst_head.sync = RQST_SYNC;
    rqst_head.flag_we = 0;
    rqst_head.size = data.size();
    rqst_head.addr = addr;

    send_all(&rqst_head, sizeof(rqst_head));

    // Receive reply header
    RplyHead rply_head;

    recv_all(&rply_head, sizeof(rply_head));

    if (rply_head.sync != RPLY_SYNC)
        throw std::runtime_error("Bad rply_head sync");

    if (rply_head.flag_error != 0)
        throw std::runtime_error("Read error from server");

    recv_all(data.data(), data.size());
}


RegioTcpClient::RegioTcpClient(const std::string& host, uint16_t port) {
    connect_to_server(host, port);
}

RegioTcpClient::~RegioTcpClient() {
    if (sockfd >= 0)
        close(sockfd);
}

void RegioTcpClient::connect_to_server(const std::string& host, uint16_t port) {
    sockfd = socket(AF_INET, SOCK_STREAM, 0);
    if (sockfd < 0)
        throw std::runtime_error("socket() failed");

    sockaddr_in addr {};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);

    if (inet_pton(AF_INET, host.c_str(), &addr.sin_addr) <= 0)
        throw std::runtime_error("Invalid IP address");

    if (connect(sockfd, (sockaddr*)&addr, sizeof(addr)) < 0)
        throw std::runtime_error("connect() failed");
}

void RegioTcpClient::send_all(const void* data, size_t len) {
    const unsigned char* p = reinterpret_cast<const uint8_t*>(data);
    while (len > 0) {
        ssize_t n = send(sockfd, p, len, 0);
        if (n <= 0)
            throw std::runtime_error("send() failed");
        p += n;
        len -= n;
    }
}

void RegioTcpClient::recv_all(void* data, size_t len) {
    unsigned char* p = reinterpret_cast<uint8_t*>(data);
    while (len > 0) {
        ssize_t n = recv(sockfd, p, len, 0);
        if (n <= 0)
            throw std::runtime_error("recv() failed");
        p += n;
        len -= n;
    }
}


}

