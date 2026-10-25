#include "hdlskel/regio/tcp/regio_tcp.hpp"
#include "hdlskel/regio/tcp/regio_tcp_client.hpp"

#include <arpa/inet.h>
#include <netdb.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

#include <cstring>
#include <cerrno>
#include <stdexcept>


namespace hdlskel::regio::tcp {

void RegioTcpClient::check_size(size_t size) {
    // Mirrors python: `if size > SIZE_MAX or size <= 0: raise ValueError`
    if (size > SIZE_MAX_WIRE || size == 0) {
        throw std::invalid_argument("size " + std::to_string(size));
    }
}

void RegioTcpClient::check_addr(size_t addr) {
    if (addr > ADDR_MAX_WIRE) {
        throw std::invalid_argument("addr " + std::to_string(addr));
    }
}

void RegioTcpClient::dev_write(size_t addr, std::span<const std::byte> data) {
    check_addr(addr);
    check_size(data.size());

    RqstHead rqst_head;
    rqst_head.sync = RQST_SYNC;
    rqst_head.flag_we = 1;
    // size is checked above, no silent truncation into the 16 bit head field
    rqst_head.size = static_cast<uint16_t>(data.size());
    rqst_head.addr = static_cast<uint32_t>(addr);

    send_all(&rqst_head, sizeof(rqst_head));
    send_all(data.data(), data.size());

    // The server sends no reply for writes (python has the reply handling
    // commented out for the same reason).
}

void RegioTcpClient::dev_read(size_t addr, std::span<std::byte> data) {
    check_addr(addr);
    check_size(data.size());

    RqstHead rqst_head;
    rqst_head.sync = RQST_SYNC;
    rqst_head.flag_we = 0;
    rqst_head.size = static_cast<uint16_t>(data.size());
    rqst_head.addr = static_cast<uint32_t>(addr);

    send_all(&rqst_head, sizeof(rqst_head));

    // Receive reply header
    RplyHead rply_head;

    recv_all(&rply_head, sizeof(rply_head));

    if (rply_head.sync != RPLY_SYNC)
        throw std::runtime_error("Bad rply_head sync");

    if (rply_head.flag_error != 0)
        throw std::runtime_error("Read error from server");

    // A short reply would desynchronise the stream, every later operation
    // would then read garbage (python raises IOError here too).
    if (static_cast<size_t>(rply_head.size) != data.size()) {
        throw std::runtime_error("unexpected response size " + std::to_string(+rply_head.size)
                                 + ", expected " + std::to_string(data.size())
                                 + ". (addr=" + std::to_string(addr) + ")");
    }

    recv_all(data.data(), data.size());
}


RegioTcpClient::RegioTcpClient(const std::string& host, uint16_t port, double timeout_s)
:   m_timeout_s(timeout_s) {
    connect_to_server(host, port);
}

RegioTcpClient::~RegioTcpClient() {
    if (sockfd >= 0)
        close(sockfd);
}

void RegioTcpClient::set_timeout(double timeout_s) {
    if (timeout_s <= 0) {
        return;
    }
    timeval tv;
    tv.tv_sec  = static_cast<time_t>(timeout_s);
    tv.tv_usec = static_cast<suseconds_t>((timeout_s - tv.tv_sec) * 1e6);
    setsockopt(sockfd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(sockfd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
}

void RegioTcpClient::connect_to_server(const std::string& host, uint16_t port) {
    // Resolve by name as well as by numeric address (python's
    // asyncio.open_connection accepts host names, so `-i localhost` works).
    addrinfo hints {};
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;

    addrinfo * result = nullptr;
    int rc = getaddrinfo(host.c_str(), std::to_string(port).c_str(), &hints, &result);
    if (rc != 0) {
        throw std::runtime_error("Cannot resolve host \"" + host + "\": " + gai_strerror(rc));
    }

    std::string error = "connect() failed";
    for (addrinfo * ai = result; ai != nullptr; ai = ai->ai_next) {
        sockfd = socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
        if (sockfd < 0) {
            continue;
        }
        if (connect(sockfd, ai->ai_addr, ai->ai_addrlen) == 0) {
            freeaddrinfo(result);
            set_timeout(m_timeout_s);
            return;
        }
        error = std::strerror(errno);
        close(sockfd);
        sockfd = -1;
    }

    freeaddrinfo(result);
    throw std::runtime_error("connect() to \"" + host + "\" failed: " + error);
}

void RegioTcpClient::send_all(const void* data, size_t len) {
    const unsigned char* p = reinterpret_cast<const uint8_t*>(data);
    while (len > 0) {
        ssize_t n = send(sockfd, p, len, 0);
        if (n <= 0)
            throw std::runtime_error(n < 0 ? std::string("send() failed: ") + std::strerror(errno)
                                           : std::string("send() failed: connection closed"));
        p += n;
        len -= n;
    }
}

void RegioTcpClient::recv_all(void* data, size_t len) {
    unsigned char* p = reinterpret_cast<uint8_t*>(data);
    while (len > 0) {
        ssize_t n = recv(sockfd, p, len, 0);
        if (n <= 0)
            throw std::runtime_error(n < 0 ? std::string("recv() failed: ") + std::strerror(errno)
                                           : std::string("recv() failed: connection closed by peer"));
        p += n;
        len -= n;
    }
}


}
