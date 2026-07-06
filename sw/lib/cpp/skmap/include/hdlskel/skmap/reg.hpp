#pragma once

#include "hdlskel/skmap/basic_types.hpp"
#include <cassert>
#include <memory>
#include <vector>
#include <span>

namespace hdlskel::skmap {

class Module;
class RegFlags;
class RFlag;


class Reg {
public:
    virtual ~Reg() = default;
    Reg(const std::string& name, Acc acc, ValueType value_type, const std::string & desc);
    virtual void initalise(Module* module, addr_t addr);
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
    uint_t read_uint_cached() const;
    sint_t read_sint_cached() const;
    uint_t read_uint();
    sint_t read_sint();
    void write_uint_cached(uint_t value);
    void write_sint_cached(sint_t value);
    void write_uint(uint_t value);
    void write_sint(sint_t value);
    void write_zero();
    std::vector<bool> read_vec_bool_cached() const;
    std::vector<bool> read_vec_bool();

    virtual bool is_flags() const { return false; }
    virtual bool is_vec  () const { return false; }
    virtual std::string str_value_cached() const;

protected:
    std::span<const std::byte> cache_data() const;
    std::span<std::byte> cache_data();
    void memcpy_from_cache(void* dest) const;
    void memcpy_to_cache(void* src);

    ValueType m_value_type;
private:
    Acc m_acc;
    std::string m_name;
    std::string m_desc;
    Module * m_module;

protected:
    addr_t m_addr_off;
};

class RegVec : public Reg {

public:
    virtual ~RegVec() = default;
    RegVec(const std::string& name, Acc acc, ValueType value_type, const std::string & desc)
    :   Reg(name, acc, value_type,  desc)
    {
        if(not value_type.is_vec()) { throw std::runtime_error("Value type must be vector");}
    }
    void initalise(Module* module, addr_t addr) override;
    void update_cache() { Reg::update_cache(); }
    void write_cache() { Reg::write_cache(); }
    void write_zero() { Reg::write_zero(); }

    size_t              vec_len() const;
    std::vector<uint_t> read_vec_uint_cached() const;
    std::vector<uint_t> read_vec_uint();
    std::vector<sint_t> read_vec_sint_cached() const;
    std::vector<sint_t> read_vec_sint();
    std::vector<bool>   read_vec_bool_cached() const;
    std::vector<bool>   read_vec_bool();
    std::string         read_str_cached() const;
    std::string         read_str();

    void write_vec_uint_cache(const  std::vector<uint_t> & vec);
    void write_vec_uint(const  std::vector<uint_t> & vec);
    void write_vec_sint_cache(const  std::vector<sint_t> & vec);
    void write_vec_sint(const  std::vector<sint_t> & vec);
    void write_vec_bool_cache(const  std::vector<bool> & vec);
    void write_vec_bool(const std::vector<bool> & vec);
 
    void update_idx_cache(addr_t idx);
    uint_t read_idx_uint_cached(addr_t idx) const;
    uint_t read_idx_uint(addr_t idx);
    sint_t read_idx_sint_cached(addr_t idx) const;
    sint_t read_idx_sint(addr_t idx);

    void write_idx_cache(addr_t idx);
    void write_idx_uint_cached(addr_t idx, uint_t val);
    void write_idx_uint(addr_t idx, uint_t val);
    void write_idx_sint_cached(addr_t idx, sint_t val);
    void write_idx_sint(addr_t idx, sint_t val);

    bool is_flags() const override { return false; }
    bool is_vec  () const override { return true ; }
    std::string str_value_cached() const override;

private:
    void memcpy_idx_from_cache(void * dest, addr_t idx) const;
    void memcpy_idx_to_cache(const void * src, addr_t idx);

};

class RFlag {
public:
    RFlag(const std::string & name, uint bit, Ass ass, const std::string & desc);

    void update_reg_cache();
    void write_reg_cache();
    bool read_bool_cached() const;
    bool read_bool();
    void write_bool_cache(bool v);
    void write_bool(bool v);
    virtual Ass ass_check_cached() const;
    virtual std::string str_value_cached() const;

    std::string name() const {return m_name;}
    uint bit() const {return m_bit;}
    Ass ass() const {return m_ass;}
    std::string desc() const {return m_desc;}

    virtual std::string value_type_str() const { return "b"; }

protected:
    bool read_bool_at_cached(uint bit) const;
    void write_bool_at_cache(uint bit, bool v);
private:
    void assign(RegFlags * reg_flags) { m_reg_flags = reg_flags; }

    RegFlags * m_reg_flags;
protected:
    uint m_bit;
    Ass m_ass;
    const std::string m_name;
    const std::string m_desc;

    friend RegFlags;
};

class RFlagVec : public RFlag {
public:
    RFlagVec(const std::string & name, addr_t bit, Ass ass, const std::string & desc, addr_t vec_size)
    : RFlag(name, bit, ass, desc)
    , m_vec_size(vec_size)
    {  }

    void update_reg_cache() { RFlag::update_reg_cache(); }
    void write_reg_cache()  { RFlag::write_reg_cache(); }
    bool read_idx_bool_cached(addr_t idx) const;
    void write_idx_bool_cache(addr_t idx, bool v);
    std::vector<bool> read_vec_bool_cached() const;
    std::vector<bool> read_vec_bool();
    void write_vec_bool_cached(const std::vector<bool> & vec);
    Ass ass_check_cached() const override;
    std::string str_value_cached() const override;

    std::string value_type_str() const override { return "b"+std::to_string(m_vec_size); }
private:
    addr_t m_vec_size;
};

class RegFlags: public Reg {
public:
    virtual ~RegFlags() = default;
    RegFlags(const std::string& name, Acc acc, uint width, std::vector<std::shared_ptr<RFlag>> flags, const std::string & desc)
    :   Reg( name, acc, make_ValueType(ValueKind::flag_, width),  desc)
    ,   m_flags(flags)
    {
        for(auto & f : flags) { f->assign(this); }
    }
    void update_cache() { Reg::update_cache(); }
    void write_cache() { Reg::write_cache(); }
    void write_zero() { Reg::write_zero(); }
    size_t flags_size() const { return m_flags.size(); }
    std::shared_ptr<RFlag> flag_at(size_t idx) { return m_flags[idx]; }
    std::shared_ptr<const RFlag> flag_at(size_t idx) const { return m_flags[idx]; }


    bool is_flags() const override { return true ; }
    bool is_vec  () const override { return false; }
    std::string str_value_cached() const override;

    Ass ass_check_cached() const;
    Ass ass_check();

private:
    std::vector<std::shared_ptr<RFlag>> m_flags;
    friend RFlag;
};

inline void push_back_flag(std::vector<std::shared_ptr<RFlag>> & flags, std::shared_ptr<RFlag> f) {
    flags.push_back(f);
}

inline std::shared_ptr<Reg> make_reg(const std::string & name, Acc acc, ValueType value_type, const std::string & desc) {
    return std::make_shared<Reg>(name, acc, value_type, desc);
}
inline std::shared_ptr<RegVec> make_reg_vec(const std::string & name, Acc acc, ValueType value_type, const std::string & desc) {
    return std::make_shared<RegVec>(name, acc, value_type, desc);
}
inline std::shared_ptr<Reg> make_reg_k(const std::string & name, ValueType value_type, const std::string & desc) {
    return make_reg(name, Acc::k, value_type, desc);
}
inline std::shared_ptr<RegVec> make_reg_vec_k(const std::string & name, ValueType value_type, const std::string & desc) {
    return make_reg_vec(name, Acc::k, value_type, desc);
}
inline std::shared_ptr<RegFlags> make_reg_flags(const std::string& name, Acc acc, uint width, std::vector<std::shared_ptr<RFlag>> flags, const std::string & desc) {
    return std::make_shared<RegFlags>(name, acc, width, flags, desc);
}
inline std::shared_ptr<RegFlags> make_reg_flags_k(const std::string& name, uint width, std::vector<std::shared_ptr<RFlag>> flags, const std::string & desc) {
    return make_reg_flags(name, Acc::k, width, flags, desc);
}
inline std::shared_ptr<RFlag> make_r_flag(const std::string & name, uint bit, Ass ass, const std::string & desc) {
    return std::make_shared<RFlag>(name, bit, ass,  desc);
}
inline std::shared_ptr<RFlagVec> make_r_flag_vec(const std::string & name, uint bit, Ass ass, const std::string & desc, addr_t vec_len) {
    return std::make_shared<RFlagVec>(name, bit, ass,  desc, vec_len);
}


}
