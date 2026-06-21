#pragma once

// #include "hdlskel/regio/regio.hpp"

#include <cstdint>
#include <stddef.h>
// #include <span>

namespace hdlskel::regio::tcp {

static constexpr uint8_t RQST_SYNC = 0x9A;
static constexpr uint8_t RPLY_SYNC = 0x9B;
static constexpr uint16_t PORT_DEFAULT = 0x9A9B;

static constexpr size_t rqst_head_size = 1+1+2+4;

struct __attribute__((packed)) RqstHead{
    uint8_t sync;
    uint8_t flag_we;
    uint16_t size;
    uint32_t addr;
};
static_assert(sizeof(RqstHead) == rqst_head_size);

struct __attribute__((packed)) RplyHead{
    uint8_t sync;
    uint8_t flag_error;
    uint16_t size;
    uint32_t addr;
};
static_assert(sizeof(RplyHead) == rqst_head_size);



}
