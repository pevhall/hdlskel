#pragma once

#include "hdlskel/skmap/basic_types.hpp"

#include <span>
#include <cstddef>
#include <cstdint>
#include <string>


//            ╓──────────┬──────────┬──────────┬──────────┐
//            ║  Byte 0  │  Byte 1  │  Byte 2  │  Byte 3  │
// ╒══════════╬══════════╧══════════╧══════════╧══════════╡
// │  Word 0  ║                                           │
// ├──────────╢                    ID          ┌──────────┤
// │  Word 1  ║                                │   Sync   │
// ├──────────╫──────────┬──────────┬──────────┴──────────┤
// │  Word 2  ║ Version  │  Flags   │       Checksum      │
// ├──────────╫──────────┼──────────┼──────────┬──────────┤
// │  Word 3  ║ Len_Kids │ Len_Sub  │  Len_K   │  Len_Var │
// └──────────╨──────────┴──────────┴──────────┴──────────┘

namespace hdlskel::skmap {



struct __attribute__((packed)) Head {
    id_t id;
    uint8_t sync;
    version_t version;
    uint8_t flags;
    checksum_t checksum;
    uint8_t len_kids;
    uint8_t len_sub;
    uint8_t len_k;
    uint8_t len_var;

    bool valid_sync() const {
        return sync == hdlskel::skmap::sync;
    }
    size_t module_len() const {
        return head_len 
         + static_cast<size_t>(len_kids)
         + static_cast<size_t>(len_sub)
         + static_cast<size_t>(len_k)
         + static_cast<size_t>(len_var);
    }

    size_t module_size() const {
        return module_len() * word_size;
    }

    size_t module_var_size() const {
        return static_cast<size_t>(len_var) * word_size;
    }
    size_t module_var_addr_offset() const {
        return (head_len 
         + static_cast<size_t>(len_kids)
         + static_cast<size_t>(len_sub)
         + static_cast<size_t>(len_k)
        ) * word_size;
    }

    // std::string id_str() const;
    std::string checksum_str() const;
    std::string id_str() const;

    std::string to_str() const;
};
static_assert (sizeof(Head) == head_size);

const Head unpack_head(std::span<const std::byte> head_bytes);


}
