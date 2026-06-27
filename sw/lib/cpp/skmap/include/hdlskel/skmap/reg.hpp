#pragma once

#include "hdlskel/skmap/basic_types.hpp"
#include "hdlskel/skmap/reg.hpp"
#include <cassert>
#include <memory>
#include <span>

namespace hdlskel::skmap {

class Module;



class Reg {
public:
    Reg(const std::string& name, Acc acc, ValueType value_type, const std::string & desc);
    void initalise(Module* module, addr_t addr);
    addr_t elem_size() const {return m_value_type.sw_elem_size();}
    addr_t elem_w() const {return m_value_type.elem_width();}
    addr_t size() const {return m_value_type.size();}
    addr_t addr() const;
    addr_t addr_off() const { return m_addr_off; }
    std::string name() const { return m_name; }
    std::string desc() const { return m_desc; }
    Acc acc() const { return m_acc; }
    ValueType value_type() const { return m_value_type; }
    // std::string acc_str() const {return m_acc.str(); };
    Module * module() const { assert (m_module); return m_module; }
    bool cache_only() const;


    void update_cache();
    void write_cache();
    uint_t value_uint_cached() const;
    sint_t value_sint_cached() const;
    uint_t value_uint();
    sint_t value_sint();
    void value_uint_cached(uint_t value) const;
    void value_sint_cached(sint_t value) const;
    void value_uint(uint_t value);
    void value_sint(sint_t value);
    std::string str_value_cached() const;

private:
    std::span<std::byte> cache_data() const;
    void memcpy_from_cache(void* dest) const;
    void memcpy_to_cache(void* src) const;

    ValueType m_value_type;
    Acc m_acc;
    std::string m_name;
    std::string m_desc;
    Module * m_module;
    addr_t m_addr_off;
};

inline std::shared_ptr<Reg> make_reg(const std::string & name, Acc acc, ValueType value_type, const std::string & desc) {
    return std::make_shared<Reg>(name, acc, value_type, desc);
}
inline std::shared_ptr<Reg> make_reg_k(const std::string & name, ValueType value_type, const std::string & desc) {
    return make_reg(name, Acc::k, value_type, desc);
}

}
