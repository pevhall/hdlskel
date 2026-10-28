#pragma once

#include "hdlskel/skmap/basic_types.hpp"
#include <cassert>
#include <cmath>
#include <functional>
#include <memory>
#include <vector>
#include <span>
#include <variant>
#include <optional>

namespace hdlskel::skmap {

class Module;
class Reg;
class RegFlags;
class RFlag;

// An entry in an assert log: either a Reg (min/max, check or reg level ass) or
// an individual RFlag of a RegFlags reg.
using RegOrFlag = std::variant<std::shared_ptr<Reg>, std::shared_ptr<RFlag>>;

// v_check / v_convert of the recipe, mirrors skmap.ValueCheck / ValueConvert in
// the python library: the value of the module user and the value of the
// register are two different things. `v_check` validates the user value,
// `v_convert` converts between the user value and the value of the register
// (every read applies its inverse).
//
// The user value travels as a float_t in both directions: for an integer v_type
// the functions receive and return integral values, see VType.
// The recipe v_check="{ (v % RW_MULT) == 0}" generates
//   ValueCheck([](sint_t v) { return (v % RW_MULT()) == 0; }, "(v % 2) == 0", VType::u)
using VCheckFn   = std::function<bool(sint_t)>;  // check of an int domain
using VCheckFnF  = std::function<bool(float_t)>;  // check of a float domain

struct ValueCheck {
    // called with the value as the module user sees it
    std::function<bool(float_t)> fn;
    // the check as text with every recipe name resolved to its value, printed
    // in the reg map, in errors and in the assert table
    std::string str;
    VType v_type = VType::s;

    ValueCheck() = default;
    ValueCheck(VCheckFn fn, std::string str, VType v_type = VType::s)
    :   fn([fn](float_t v) { return fn(static_cast<sint_t>(std::llround(v))); }),
        str(std::move(str)), v_type(v_type) {}
    ValueCheck(VCheckFnF fn, std::string str, VType v_type = VType::s)
    :   fn(std::move(fn)), str(std::move(str)), v_type(v_type) {}

    bool operator()(float_t value) const { return static_cast<bool>(fn(value)); }
};

struct ValueConvert {
    // user value -> value of the register, may return a fractional value, the
    // Reg rounds it like the python runtime does
    std::function<float_t(float_t)> to_raw;
    // value of the register -> user value, the inverse of to_raw
    std::function<float_t(sint_t)> from_raw;
    // both directions as text with every recipe name resolved to its value
    std::string str;
    std::string str_inv;
    VType v_type = VType::s;

    ValueConvert(std::function<float_t(float_t)> to_raw, std::function<float_t(sint_t)> from_raw,
                 std::string str, std::string str_inv, VType v_type = VType::s)
    :   to_raw(std::move(to_raw)), from_raw(std::move(from_raw)),
        str(std::move(str)), str_inv(std::move(str_inv)), v_type(v_type) {}
};

// Round to the nearest integer with halves away from zero, same as python
// round() on floats, it decides the value that ends up in the register.
sint_t v_round_to_int(float_t value);


class Reg {
public:
    virtual ~Reg() = default;
    Reg(const std::string& name, Acc acc, ValueType value_type, const std::string & desc,
        Ass ass = Ass::none, std::optional<ValueCheck> v_check = std::nullopt,
        std::optional<ValueConvert> v_convert = std::nullopt, VType v_type = VType::s);
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
    bool read_bool_cached() const;
    char read_char_cached() const;
    uint_t read_uint();
    sint_t read_sint();
    bool read_bool();
    char read_char();
    void write_uint_cached(uint_t value);
    void write_sint_cached(sint_t value);
    void write_bool_cached(bool v);
    void write_char_cached(char v);
    void write_uint(uint_t value);
    void write_sint(sint_t value);
    void write_bool(bool v);
    void write_char(char v);
    void write_zero();
    // Raw bytes of the register, they bypass v_check and v_convert (the same
    // access a firmware can do), mirrors Reg.read_bytes_cached and
    // Reg.write_bytes_cached in python.
    std::span<const std::byte> read_bytes_cached() const;
    void write_bytes_cached(std::span<const std::byte> data);
    // Zeros in the cache only, mirrors Reg.write_zero_cached in python
    // (write_zero() is this followed by a device write).
    void write_zero_cached();

    // v_convert (see the recipe): the functions without a postfix work with
    // the value of the module user (v_check it, then convert it, a read
    // converts with the inverse), the *_raw functions bypass the conversion.
    bool has_v_convert() const { return m_v_convert.has_value(); }
    // `={ v * 16 } ` text of the v_convert, '' when there is none: printed at
    // the start of the description in the reg map, like desc_cell() of
    // pip/skmap/src/skmap/reg_map_table.py
    std::string v_convert_marker() const;
    float_t to_raw(float_t value) const;
    // v_check the user value, convert it and check that it fits the register
    sint_t to_raw_checked(float_t value) const;
    float_t from_raw(sint_t value) const;
    float_t read_converted_cached() const;
    float_t read_converted();
    void write_converted_cached(float_t value);
    void write_converted(float_t value);

    // Asserts and limits (mirrors Reg in pip/skmap/src/skmap/reg.py).
    // ass_check_cached computes the assert status of this reg from the cache:
    //   * if the reg has a v_check, the value is checked with it
    //   * else if the reg has an ass level, a non-zero value raises that ass
    // If log_flags is given and this is a RegFlags, the failing flags are
    // appended to it. Plain regs never append anything (the Module decides
    // whether to log the reg itself).
    virtual Ass ass_check_cached(Ass log_ass, std::vector<std::shared_ptr<RFlag>> * log_flags) const;
    virtual Ass ass_check_limit_cached() const;
    Ass ass_check_value_check(float_t value) const;
    Ass ass_check_value_limit(float_t value) const;
    void check_value_limit(float_t value) const;
    virtual bool has_ass() const { return m_ass != Ass::none || has_limit(); }
    bool has_limit() const;
    // True if the value fits in the register's bytes, mirrors python raising
    // OverflowError from int.to_bytes(self.size).
    void check_value_fits(uint_t value) const;
    void check_value_fits(sint_t value) const;
    // Same for the value of the register of a v_convert write
    void check_value_fits_reg(sint_t value) const;
    Ass ass() const { return m_ass; }
    const std::optional<ValueCheck> & v_check() const { return m_v_check; }
    const std::optional<ValueConvert> & v_convert() const { return m_v_convert; }
    VType v_type() const { return m_v_type; }
    bool is_bool() const { return m_value_type.is_bool(); }
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
    Ass m_ass;
    std::optional<ValueCheck>   m_v_check;
    std::optional<ValueConvert> m_v_convert;
    // domain of the user value, follows the recipe v_type
    VType m_v_type = VType::s;
};

class RegVec : public Reg {

public:
    virtual ~RegVec() = default;
    RegVec(const std::string& name, Acc acc, ValueType value_type, const std::string & desc,
        Ass ass = Ass::none, std::optional<ValueCheck> v_check = std::nullopt,
        std::optional<ValueConvert> v_convert = std::nullopt, VType v_type = VType::s)
    :   Reg(name, acc, value_type,  desc, ass, v_check, v_convert, v_type)
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

    void write_vec_uint_cached(const  std::vector<uint_t> & vec);
    void write_vec_uint(const  std::vector<uint_t> & vec);
    void write_vec_sint_cached(const  std::vector<sint_t> & vec);
    void write_vec_sint(const  std::vector<sint_t> & vec);
    void write_vec_bool_cached(const  std::vector<bool> & vec);
    void write_vec_bool(const std::vector<bool> & vec);
    // For char vectors (mirrors the string accessors the code generators emit)
    void write_str_cached(const std::string & str);
    void write_str(const std::string & str);
 
    void update_idx_cache(addr_t idx);
    // Raw bytes of one element, they bypass v_check and v_convert (like python
    // RegVec.read_idx_bytes_cached / write_idx_bytes_cached)
    std::span<const std::byte> read_idx_bytes_cached(addr_t idx) const;
    void write_idx_bytes_cached(addr_t idx, std::span<const std::byte> data);
    uint_t read_idx_uint_cached(addr_t idx) const;
    uint_t read_idx_uint(addr_t idx);
    sint_t read_idx_sint_cached(addr_t idx) const;
    sint_t read_idx_sint(addr_t idx);

    void write_idx_cache(addr_t idx);
    void write_idx_uint_cached(addr_t idx, uint_t val);
    void write_idx_uint(addr_t idx, uint_t val);
    void write_idx_sint_cached(addr_t idx, sint_t val);
    void write_idx_sint(addr_t idx, sint_t val);

    // v_convert of the recipe, same as Reg, applied to every element
    std::vector<float_t> read_vec_converted_cached() const;
    std::vector<float_t> read_vec_converted();
    void write_vec_converted_cached(const std::vector<float_t> & vec);
    void write_vec_converted(const std::vector<float_t> & vec);
    float_t read_idx_converted_cached(addr_t idx) const;
    float_t read_idx_converted(addr_t idx);
    void write_idx_converted_cached(addr_t idx, float_t value);
    void write_idx_converted(addr_t idx, float_t value);

    // stride between vector elements in bytes (aligned to the module byte alignment)
    addr_t elem_off() const { return m_value_type.sw_elem_offset(); }

    bool is_flags() const override { return false; }
    bool is_vec  () const override { return true ; }
    std::string str_value_cached() const override;
    Ass ass_check_cached(Ass log_ass, std::vector<std::shared_ptr<RFlag>> * log_flags) const override;
    Ass ass_check_limit_cached() const override;

private:
    void memcpy_idx_from_cache(void * dest, addr_t idx) const;
    void memcpy_idx_to_cache(const void * src, addr_t idx);
    void check_idx(addr_t idx) const;
    void check_vec_len(size_t len) const;

};

class RFlag {
public:
    RFlag(const std::string & name, uint32_t bit, Ass ass, const std::string & desc);

    void update_reg_cache();
    void write_reg_cache();
    bool read_bool_cached() const;
    bool read_bool();
    void write_bool_cached(bool v);
    void write_bool(bool v);
    virtual Ass ass_check_cached() const;
    virtual std::string str_value_cached() const;

    std::string name() const {return m_name;}
    uint32_t bit() const {return m_bit;}
    Ass ass() const {return m_ass;}
    std::string desc() const {return m_desc;}
    // Throws if this flag was never assigned to a RegFlags
    const RegFlags & reg_flags() const;

    virtual std::string value_type_str() const { return "b"; }

protected:
    bool read_bool_at_cached(uint32_t bit) const;
    void write_bool_at_cache(uint32_t bit, bool v);
    // Common flag assert logic: no ass -> none, value clear -> passed, else ass
    Ass ass_check_value(bool value) const;
private:
    void assign(RegFlags * reg_flags) { m_reg_flags = reg_flags; }
    // Non throwing accessor used by the read/write helpers
    const RegFlags & reg_flags_ref() const;
    RegFlags & reg_flags_ref();

    RegFlags * m_reg_flags = nullptr;
protected:
    uint32_t m_bit;
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
    void write_idx_bool_cached(addr_t idx, bool v);
    std::vector<bool> read_vec_bool_cached() const;
    std::vector<bool> read_vec_bool();
    void write_vec_bool_cached(const std::vector<bool> & vec);
    void write_vec_bool(const std::vector<bool> & vec);
    Ass ass_check_cached() const override;
    std::string str_value_cached() const override;

    std::string value_type_str() const override { return "b"; }
    addr_t vec_len() const { return m_vec_size; }
private:
    void check_idx(addr_t idx) const;
    void check_vec_len(size_t len) const;
    addr_t m_vec_size;
};

class RegFlags: public Reg {
public:
    virtual ~RegFlags() = default;
    RegFlags(const std::string& name, Acc acc, uint32_t width, std::vector<std::shared_ptr<RFlag>> flags, const std::string & desc)
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
    const std::vector<std::shared_ptr<RFlag>> & flags() const { return m_flags; }

    bool is_flags() const override { return true ; }
    bool is_vec  () const override { return false; }
    std::string str_value_cached() const override;
    bool has_ass() const override;

    Ass ass_check_cached(Ass log_ass, std::vector<std::shared_ptr<RFlag>> * log_flags) const override;
    Ass ass_check();

private:
    std::vector<std::shared_ptr<RFlag>> m_flags;
    friend RFlag;
};

inline void push_back_flag(std::vector<std::shared_ptr<RFlag>> & flags, std::shared_ptr<RFlag> f) {
    flags.push_back(f);
}

inline std::shared_ptr<Reg> make_reg(const std::string & name, Acc acc, ValueType value_type, const std::string & desc,
    Ass ass = Ass::none, std::optional<ValueCheck> v_check = std::nullopt,
    std::optional<ValueConvert> v_convert = std::nullopt, VType v_type = VType::s) {
    return std::make_shared<Reg>(name, acc, value_type, desc, ass, v_check, v_convert, v_type);
}
inline std::shared_ptr<RegVec> make_reg_vec(const std::string & name, Acc acc, ValueType value_type, const std::string & desc,
    Ass ass = Ass::none, std::optional<ValueCheck> v_check = std::nullopt,
    std::optional<ValueConvert> v_convert = std::nullopt, VType v_type = VType::s) {
    return std::make_shared<RegVec>(name, acc, value_type, desc, ass, v_check, v_convert, v_type);
}
// A constant register has no v_convert, only a v_check of the value the firmware reports
inline std::shared_ptr<Reg> make_reg_k(const std::string & name, ValueType value_type, const std::string & desc,
    std::optional<ValueCheck> v_check = std::nullopt, VType v_type = VType::s) {
    return make_reg(name, Acc::k, value_type, desc, Ass::none, v_check, std::nullopt, v_type);
}
inline std::shared_ptr<RegVec> make_reg_vec_k(const std::string & name, ValueType value_type, const std::string & desc,
    std::optional<ValueCheck> v_check = std::nullopt, VType v_type = VType::s) {
    return make_reg_vec(name, Acc::k, value_type, desc, Ass::none, v_check, std::nullopt, v_type);
}
inline std::shared_ptr<RegFlags> make_reg_flags(const std::string& name, Acc acc, uint32_t width, std::vector<std::shared_ptr<RFlag>> flags, const std::string & desc) {
    return std::make_shared<RegFlags>(name, acc, width, flags, desc);
}
inline std::shared_ptr<RegFlags> make_reg_flags_k(const std::string& name, uint32_t width, std::vector<std::shared_ptr<RFlag>> flags, const std::string & desc) {
    return make_reg_flags(name, Acc::k, width, flags, desc);
}
inline std::shared_ptr<RFlag> make_r_flag(const std::string & name, uint32_t bit, Ass ass, const std::string & desc) {
    return std::make_shared<RFlag>(name, bit, ass,  desc);
}
inline std::shared_ptr<RFlagVec> make_r_flag_vec(const std::string & name, uint32_t bit, Ass ass, const std::string & desc, addr_t vec_len) {
    return std::make_shared<RFlagVec>(name, bit, ass,  desc, vec_len);
}


}
