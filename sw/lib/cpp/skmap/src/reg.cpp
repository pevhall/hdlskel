
#include "hdlskel/skmap/reg.hpp"
#include "hdlskel/skmap/module.hpp"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <iomanip>
// #include <memory>
#include <sstream>
#include <stdexcept>

namespace {

using uint_t = hdlskel::skmap::uint_t;
using sint_t = hdlskel::skmap::sint_t;

// mask_to_width() and sint_sign_extend_w() live in basic_types.hpp so the
// external memory helpers can use them too.
using hdlskel::skmap::mask_to_width;
using hdlskel::skmap::sint_sign_extend;
inline sint_t sint_sign_extend_w(uint64_t value, int w) {
    return sint_sign_extend(value, static_cast<uint64_t>(w));
}

}

namespace hdlskel::skmap {

// Round half away from zero, like python round() on a float. A v_convert with
// a float v_type decides the register value with this.
sint_t v_round_to_int(double value) {
    return static_cast<sint_t>(value >= 0 ? std::floor(value + 0.5) : std::ceil(value - 0.5));
}

Reg::Reg(const std::string & name, Acc acc, ValueType value_type, const std::string & desc,
    Ass ass, std::optional<ValueCheck> v_check, std::optional<ValueConvert> v_convert, VType v_type)
    : m_value_type(value_type) 
    , m_acc(acc) 
    , m_name(name) 
    , m_desc(desc) 
    , m_ass(ass)
    , m_v_check(v_check)
    , m_v_convert(v_convert)
    , m_v_type(v_type)
{
    if (v_convert.has_value() && v_check.has_value() && v_convert->v_type != v_check->v_type) {
        throw std::runtime_error("Reg "" + name + "" has a v_check and a v_convert with a different v_type");
    }
}

void Reg::initalise(Module* module, addr_t addr_off) {
    m_module = module;
    m_addr_off   = addr_off;
}
addr_t Reg::addr() const { return (module()->base_addr()) + m_addr_off; }

bool Reg::cache_only() const { return module()->cache_only(); }

std::span<const std::byte> Reg::cache_data() const { return m_module->cache_data(m_addr_off, size()); }
std::span<      std::byte> Reg::cache_data() { return m_module->cache_data(m_addr_off, size()); }

void Reg::memcpy_from_cache(void* dest) const {
    std::span<const std::byte> data = cache_data();
    std::memcpy(dest, data.data(), data.size());
}

void Reg::memcpy_to_cache(void* src) {
    std::span< std::byte> data = cache_data();
    std::memcpy(data.data(), src, data.size());
}

// Device access is centralized in Module::update_cache/write_cache which
// honor cache_only(); here we additionally never read the device for
// constants (mirrors Reg.read_bytes in pip/skmap/src/skmap/reg.py which
// returns the cache directly for Acc.k).
void Reg::update_cache() {
    if (m_acc == Acc::k) { return; }
    module()->update_cache(m_addr_off, size());
}

void Reg::write_cache() { module()->write_cache(m_addr_off, size()); }

uint_t Reg::read_uint_cached() const {
    if ( size() > sizeof(uint_t) ) {
        throw std::runtime_error("uint_t not large enough to fit register");
    }
    uint_t value = 0;
    memcpy_from_cache(&value);
    // Mask off anything above the register bit width (neighbouring fields
    // can share the same storage word).
    return mask_to_width(value, elem_w());
}

sint_t Reg::read_sint_cached() const {
    if ( size() > sizeof(sint_t) ) {
        throw std::runtime_error("sint_t not large enough to fit register");
    }
    sint_t value = 0;
    memcpy_from_cache(&value);
    return sint_sign_extend_w(mask_to_width(static_cast<uint_t>(value), elem_w()), elem_w());
}

bool Reg::read_bool_cached() const {
    return read_uint_cached() != 0;
}

// Mirrors Reg.read_char_cached in pip/skmap/src/skmap/reg.py
char Reg::read_char_cached() const {
    if (elem_w() != 8) {
        throw std::runtime_error("Char must be 8 bits, reg \"" + m_name + "\" is " + std::to_string(elem_w()));
    }
    unsigned char c = 0;
    memcpy_from_cache(&c);
    return static_cast<char>(c);
}

uint_t Reg::read_uint() {
    update_cache();
    return read_uint_cached();
}

sint_t Reg::read_sint() {
    update_cache();
    return read_sint_cached();
}

bool Reg::read_bool() {
    update_cache();
    return read_bool_cached();
}

char Reg::read_char() {
    update_cache();
    return read_char_cached();
}

// A value must fit in the register's bytes, mirroring python's
// int.to_bytes(self.size) which raises OverflowError. Note python checks
// against the register *size* (rounded up to the byte alignment), not the
// declared bit width.
void Reg::check_value_fits(uint_t value) const {
    if (size() >= sizeof(uint_t)) {
        return;
    }
    uint_t limit = uint_t{1} << (8*size());
    if (value >= limit) {
        throw std::runtime_error("Value " + std::to_string(value) + " does not fit in reg \"" + m_name + "\" (" + std::to_string(8*size()) + " bits)");
    }
}

void Reg::check_value_fits(sint_t value) const {
    if (size() >= sizeof(sint_t)) {
        return;
    }
    sint_t bits = sint_t{8*size()};
    sint_t max = (sint_t{1} << (bits-1)) - 1;
    sint_t min = -(sint_t{1} << (bits-1));
    if (value < min || value > max) {
        throw std::runtime_error("Value " + std::to_string(value) + " does not fit in reg \"" + m_name + "\" (" + std::to_string(bits) + " bits signed)");
    }
}

void Reg::write_uint_cached(uint_t value) { 
    if ( size() > sizeof(uint_t) ) {
        throw std::runtime_error("uint_t not large enough to fit register");
    }
    check_value_fits(value);
    // The raw value is the user value when there is no v_convert, with one the
    // written value has to be a raw value that came from a valid user value.
    check_value_limit(from_raw(static_cast<sint_t>(value)));
    memcpy_to_cache(&value);
}
void Reg::write_sint_cached(sint_t value) { 
    if ( size() > sizeof(sint_t) ) {
        throw std::runtime_error("sint_t not large enough to fit register");
    }
    check_value_fits(value);
    check_value_limit(from_raw(value));
    memcpy_to_cache(&value);
}
void Reg::write_bool_cached(bool v) {
    write_uint_cached(static_cast<uint_t>(v));
}
// Mirrors Reg.write_char_cached added for the char accessors the code
// generators emit (python packs the character through write_bytes).
void Reg::write_char_cached(char v) {
    if (elem_w() != 8) {
        throw std::runtime_error("Char must be 8 bits, reg \"" + m_name + "\" is " + std::to_string(elem_w()));
    }
    unsigned char c = static_cast<unsigned char>(v);
    memcpy_to_cache(&c);
}
void Reg::write_uint(uint_t value) { 
    write_uint_cached(value);
    write_cache();
}
void Reg::write_sint(sint_t value) { 
    write_sint_cached(value);
    write_cache();
}
void Reg::write_bool(bool v) {
    write_bool_cached(v);
    write_cache();
}
void Reg::write_char(char v) {
    write_char_cached(v);
    write_cache();
}
// Mirrors Reg.write_zero_cached in pip/skmap/src/skmap/reg.py: zeros in the
// cache only. write_zero() is this followed by a device write.
// Raw byte access to the cache of the register, it bypasses v_check and
// v_convert, mirrors Reg.read_bytes_cached / Reg.write_bytes_cached in python
// (fw can put any value in a register, the reads report it as an assert).
std::span<const std::byte> Reg::read_bytes_cached() const {
    return cache_data();
}

void Reg::write_bytes_cached(std::span<const std::byte> data) {
    if (data.size() != static_cast<size_t>(size())) {
        throw std::runtime_error("Writing " + std::to_string(data.size()) + " bytes to reg "" + m_name + "" with a size of " + std::to_string(size()));
    }
    std::memcpy(cache_data().data(), data.data(), size());
}

void Reg::write_zero_cached() {
    check_value_limit(0);
    std::vector<std::byte> z(size(), std::byte{0});
    memcpy_to_cache(z.data());
}

void Reg::write_zero() {
    // Mirrors Reg.write_zero in pip/skmap/src/skmap/reg.py:
    // write_zero_cached() followed by write_cache() (device write is
    // skipped centrally by Module::write_cache when cache_only).
    write_zero_cached();
    write_cache();
}
std::vector<bool> Reg::read_vec_bool_cached() const {
    std::span<const std::byte> data = cache_data();
    std::vector<bool> vec(elem_w());
    size_t byte = (elem_w()-1) / 8;
    uint8_t bit = (elem_w()-1) % 8;
    for(size_t ii = 0; ii < elem_w(); ii++) {
        uint8_t bit_mask = 1<<bit;
        vec[ii] = (static_cast<uint8_t>(data[byte]) & bit_mask) != 0;
        if (bit==0) {
            byte--;
            bit = 7;
        } else { bit--; }
    }
    return vec;
}

std::vector<bool> Reg::read_vec_bool() {
    update_cache();
    return read_vec_bool_cached();
}

// --- Asserts and limits (mirrors Reg in pip/skmap/src/skmap/reg.py) ---

// v_check of the recipe, the only value limit a register can have (see the
// python runtime: the value of a register is always the value of the module
// user, min and max of the register value are replaced by v_check).
Ass Reg::ass_check_value_check(double value) const {
    if (!m_v_check.has_value()) {
        return Ass::none;
    }
    if ((*m_v_check)(value)) {
        return Ass::none;
    }
    if (m_ass != Ass::none) {
        return m_ass;
    }
    return Ass::error;
}

Ass Reg::ass_check_value_limit(double value) const {
    return ass_check_value_check(value);
}

void Reg::check_value_limit(double value) const {
    if (ass_check_value_limit(value) >= Ass::error) {
        std::stringstream ss;
        ss << "v_check failed for reg \"" << m_name << "\"";
        if (m_v_check.has_value()) {
            ss << " (" << m_v_check->str << ")";
        }
        ss << ", value " << value;
        throw std::runtime_error(ss.str());
    }
}

bool Reg::has_limit() const {
    // Only a v_check is a value limit (flags have their own assert per flag)
    return m_value_type.kind() != ValueKind::char_ && m_value_type.kind() != ValueKind::flag_
        && m_v_check.has_value();
}

// ---------- v_convert ----------

double Reg::to_raw(double value) const {
    // user value -> value of the register
    if (!m_v_convert.has_value()) {
        return value;
    }
    return m_v_convert->to_raw(value);
}

double Reg::from_raw(sint_t value) const {
    // value of the register -> user value
    if (!m_v_convert.has_value()) {
        return static_cast<double>(value);
    }
    return m_v_convert->from_raw(value);
}

void Reg::check_value_fits_reg(sint_t value) const {
    if (m_value_type.kind() == ValueKind::sint_) {
        check_value_fits(value);
    } else {
        check_value_fits(static_cast<uint_t>(value));
    }
}

sint_t Reg::to_raw_checked(double value) const {
    // v_check the user value, convert it, check the result
    check_value_limit(value);
    double value_raw = to_raw(value);
    if (!std::isfinite(value_raw)) {
        throw std::runtime_error("v_convert of reg "" + m_name + "" returned a value that is not a number");
    }
    sint_t value_raw_int = v_round_to_int(value_raw);
    check_value_fits_reg(value_raw_int);
    return value_raw_int;
}

double Reg::read_converted_cached() const {
    return from_raw(m_value_type.kind() == ValueKind::sint_ ? read_sint_cached()
                                                            : static_cast<sint_t>(read_uint_cached()));
}

double Reg::read_converted() {
    update_cache();
    return read_converted_cached();
}

void Reg::write_converted_cached(double value) {
    sint_t value_raw = to_raw_checked(value);
    if (m_value_type.kind() == ValueKind::sint_) {
        write_sint_cached(value_raw);
    } else {
        write_uint_cached(static_cast<uint_t>(value_raw));
    }
}

void Reg::write_converted(double value) {
    write_converted_cached(value);
    write_cache();
}

Ass Reg::ass_check_limit_cached() const {
    // The v_check works on the value of the module user
    return ass_check_value_limit(read_converted_cached());
}

Ass Reg::ass_check_cached(Ass log_ass, std::vector<std::shared_ptr<RFlag>> * log_flags) const {
    (void)log_ass;
    (void)log_flags;
    if (has_limit()) {
        return ass_check_limit_cached();
    }
    if (m_ass == Ass::none) {
        return Ass::none;
    }
    bool value = read_bool_cached();
    return value ? m_ass : Ass::passed;
}

// Mirrors Reg._str_num in pip/skmap/src/skmap/reg.py:
//   base  2 -> 0b<zero padded to width bits>
//   base 10 -> plain decimal
//   base 16 -> 0x<zero padded to ceil(width/4) upper case digits>
std::string str_num(sint_t value, addr_t width, int base) {
    std::ostringstream oss;
    uint64_t u = static_cast<uint64_t>(value);
    if (base == 2) {
        oss << "0b";
        for (addr_t bit = width; bit > 0; bit--) {
            oss << ((u >> (bit - 1)) & 1);
        }
    } else if (base == 16) {
        oss << "0x" << std::uppercase << std::hex << std::setfill('0')
            << std::setw(static_cast<int>((width + 3) / 4)) << u;
    } else {
        oss << value;
    }
    return oss.str();
}

// Mirrors skmap.value_to_str_from_int: a float v_type prints as a double,
// everything else keeps the register formatting. Used to print the value a
// v_convert gives the module user.
std::string value_to_str_from_int(double value, addr_t width, int base, bool v_type_is_float) {
    if (v_type_is_float) {
        std::ostringstream oss;
        oss << value;
        return oss.str();
    }
    return str_num(static_cast<sint_t>(value), width, base);
}

std::string Reg::str_value_cached() const {
    // Mirrors Reg.read_rich_str_cached in pip/skmap/src/skmap/reg.py (minus colour):
    //   [ass: ][(min <= v <= max) ]value
    std::stringstream ss;
    sint_t value_int = 0;
    bool have_int = false;
    std::string value_str;
    int base = 10;
    switch(m_value_type.kind()) {
        case ValueKind::uint_: {
            value_int = static_cast<sint_t>(read_uint_cached());
            have_int = true;
            break;
        }
        case ValueKind::sint_: {
            value_int = read_sint_cached();
            have_int = true;
            break;
        }
        case ValueKind::char_: {
            value_str = std::string(1, read_char_cached());
            break;
        }
        case ValueKind::bits_: {
            value_int = static_cast<sint_t>(read_uint_cached());
            have_int = true;
            base = 16;
            break;
        }
        case ValueKind::flag_: {
            // A single bit flag reads as a bool, a wider one as binary (like py).
            if (is_bool()) {
                value_str = read_bool_cached() ? "True" : "False";
            } else {
                value_int = static_cast<sint_t>(read_uint_cached());
                have_int = true;
                base = 2;
            }
            break;
        };
    }

    Ass ass = Ass::none;
    if (m_ass != Ass::none) {
        ass = ass_check_cached(Ass::none, nullptr);
        ss << str(m_ass) << ": ";
    }
    if (has_limit()) {
        Ass limit_ass = ass_check_limit_cached();
        if (limit_ass > ass) { ass = limit_ass; }
        // The v_check is printed as its expression, with every recipe name
        // resolved to a value, so it prints without the recipe
        ss << m_v_check->str << " ";
    }
    if (has_v_convert()) {
        // The user value is printed, the raw one is available through the
        // *_raw functions
        value_str = value_to_str_from_int(read_converted_cached(), m_value_type.elem_width(), base, m_v_type == VType::f);
        have_int = false;
    }

    if (!value_str.empty()) {
        ss << value_str;
    } else {
        assert(have_int);
        ss << str_num(value_int, m_value_type.elem_width(), base);
    }
    return ss.str();
}

void RegVec::initalise(Module* module, addr_t addr) {
    Reg::initalise(module, addr);
    m_value_type._sw_elem_offset(module->align_byte(m_value_type.sw_elem_size()));
}

size_t RegVec::vec_len() const {
    return *m_value_type.vec_len();
}

std::vector<uint_t> RegVec::read_vec_uint_cached() const {
    std::span<const std::byte> data = cache_data();
    std::vector<uint_t> vec(vec_len());
    addr_t v_off = 0;
    for(auto & v : vec) {
        v = 0;
        std::memcpy(&v, &data[v_off], elem_size());
        v = mask_to_width(v, elem_w());
        v_off += elem_off();
    }
    return vec;
}

std::vector<uint_t> RegVec::read_vec_uint() {
    update_cache();
    return read_vec_uint_cached();
}

std::vector<sint_t> RegVec::read_vec_sint_cached() const {
    std::span<const std::byte> data = cache_data();
    std::vector<sint_t> vec(vec_len());
    addr_t v_off = 0;
    for(auto & v : vec) {
        uint_t u = 0;
        std::memcpy(&u, &data[v_off], elem_size());
        u = mask_to_width(u, elem_w());
        v = sint_sign_extend_w(u, elem_w());
        v_off += elem_off();
    }
    return vec;
}

std::vector<sint_t> RegVec::read_vec_sint() {
    update_cache();
    return read_vec_sint_cached();
}

std::vector<bool> RegVec::read_vec_bool_cached() const {
    std::span<const std::byte> data = cache_data();
    std::vector<bool> vec(vec_len());
    addr_t b_idx = 0;
    for(addr_t ii = 0; ii < vec_len(); ii++) {
        vec[ii] = (static_cast<uint8_t>(data[b_idx])) != 0;
        b_idx += elem_off();
    }
    return vec;
}

std::vector<bool> RegVec::read_vec_bool() {
    update_cache();
    return read_vec_bool_cached();
}

std::string RegVec::read_str_cached() const {
    if(elem_w() != 8) {
        throw std::runtime_error("Only ASCII strings/characters are supported");
    }
    std::span<const std::byte> data = cache_data();
    std::string str(vec_len(), '\0');
    addr_t v_off = 0;
    for(char & c : str) {
        c = static_cast<char>(data[v_off]);
        v_off += elem_off();
    }
    return str;
}

std::string RegVec::read_str() {
    update_cache();
    return read_str_cached();
}

void RegVec::check_idx(addr_t idx) const {
    // Mirrors the `assert idx < len(self)` in the python index accessors.
    if (idx >= vec_len()) {
        throw std::runtime_error("Index " + std::to_string(idx) + " out of range for vector reg \"" + name() + "\" (len " + std::to_string(vec_len()) + ")");
    }
}

void RegVec::check_vec_len(size_t len) const {
    // Mirrors `assert len(b) == self.size` in python write_bytes_cached.
    if (len != static_cast<size_t>(vec_len())) {
        throw std::runtime_error("Vector of length " + std::to_string(len) + " does not match vector reg \"" + name() + "\" (len " + std::to_string(vec_len()) + ")");
    }
}

void RegVec::write_vec_uint_cached(const  std::vector<uint_t> & vec) {
    check_vec_len(vec.size());
    std::span<std::byte> data = cache_data();
    addr_t ii = 0;
    for(const uint_t v : vec) {
        // the v_check applies to every element (mirrors python
        // RegVec.check_value_list), with the value of the module user
        check_value_limit(from_raw(static_cast<sint_t>(v)));
        std::memcpy(&data[ii], &v, elem_size());
        ii += elem_off();
    }
}

void RegVec::write_vec_sint_cached(const  std::vector<sint_t> & vec) {
    check_vec_len(vec.size());
    std::span<std::byte> data = cache_data();
    addr_t ii = 0;
    for(const sint_t v : vec) {
        check_value_limit(from_raw(v));
        std::memcpy(&data[ii], &v, elem_size());
        ii += elem_off();
    }
}

void RegVec::write_vec_bool_cached(const  std::vector<bool> & vec) {
    check_vec_len(vec.size());
    std::span<std::byte> data = cache_data();
    addr_t ii = 0;
    for(const bool v : vec) {
        uint_t v_int = static_cast<int>(v);
        std::memcpy(&data[ii], &v_int, elem_size());
        ii += elem_off();
    }
}
void RegVec::write_vec_uint(const  std::vector<uint_t> & vec) {
    write_vec_uint_cached(vec);
    write_cache();
}
void RegVec::write_vec_sint(const  std::vector<sint_t> & vec) {
    write_vec_sint_cached(vec);
    write_cache();
}
void RegVec::write_vec_bool(const std::vector<bool> & vec) {
    write_vec_bool_cached(vec);
    write_cache();
}

// Character vectors: the code generators emit these for rw char vectors on
// both python and C++.
void RegVec::write_str_cached(const std::string & str) {
    if (elem_w() != 8) {
        throw std::runtime_error("Only ASCII strings/characters are supported");
    }
    check_vec_len(str.size());
    std::span<std::byte> data = cache_data();
    addr_t ii = 0;
    for(const char c : str) {
        data[ii] = static_cast<std::byte>(static_cast<unsigned char>(c));
        ii += elem_off();
    }
}

void RegVec::write_str(const std::string & str) {
    write_str_cached(str);
    write_cache();
}

// Raw byte access to one element of a vector register (mirrors the python
// RegVec.read_idx_bytes_cached / write_idx_bytes_cached), bypasses all checks.
std::span<const std::byte> RegVec::read_idx_bytes_cached(addr_t idx) const {
    check_idx(idx);
    std::span<const std::byte> data = cache_data();
    return data.subspan(idx*elem_off(), elem_size());
}

void RegVec::write_idx_bytes_cached(addr_t idx, std::span<const std::byte> data) {
    check_idx(idx);
    if (data.size() != static_cast<size_t>(elem_size())) {
        throw std::runtime_error("Writing " + std::to_string(data.size()) + " bytes to element " + std::to_string(idx) + " of reg "" + name() + "" with an element size of " + std::to_string(elem_size()));
    }
    std::span<std::byte> cache = cache_data();
    std::memcpy(&cache[idx*elem_off()], data.data(), elem_size());
}

void RegVec::memcpy_idx_from_cache(void * dest, addr_t idx) const {
    check_idx(idx);
    std::span<const std::byte> data = cache_data();
    std::memcpy(dest, &data[idx*elem_off()], elem_size());
}

void RegVec::memcpy_idx_to_cache(const void * src, addr_t idx) {
    check_idx(idx);
    std::span<std::byte> data = cache_data();
    std::memcpy(&data[idx*elem_off()], src, elem_size());
}
void RegVec::update_idx_cache(addr_t idx) {
    if (acc() == Acc::k) { return; } // constants come from the cache (like py)
    check_idx(idx);
    addr_t addr = m_addr_off + idx*elem_off();
    module()->update_cache(addr, elem_size());
}

uint_t RegVec::read_idx_uint_cached(addr_t idx) const {
    uint_t val = 0;
    memcpy_idx_from_cache(&val, idx);
    return mask_to_width(val, elem_w());
}

uint_t RegVec::read_idx_uint(addr_t idx) {
    update_idx_cache(idx);
    return read_idx_uint_cached(idx);
}

sint_t RegVec::read_idx_sint_cached(addr_t idx) const {
    uint_t val = 0;
    memcpy_idx_from_cache(&val, idx);
    return sint_sign_extend_w(mask_to_width(val, elem_w()), elem_w());
}

sint_t RegVec::read_idx_sint(addr_t idx) {
    update_idx_cache(idx);
    return read_idx_sint_cached(idx);
}

void RegVec::write_idx_cache(addr_t idx) {
    check_idx(idx);
    addr_t addr = m_addr_off + idx*elem_off();
    module()->write_cache(addr, elem_size());
}
void RegVec::write_idx_uint_cached(addr_t idx, uint_t val) {
    check_value_limit(from_raw(static_cast<sint_t>(val)));
    memcpy_idx_to_cache(&val, idx);
}
void RegVec::write_idx_sint_cached(addr_t idx, sint_t val) {
    check_value_limit(from_raw(val));
    memcpy_idx_to_cache(&val, idx);
}

// ---------- v_convert of a vector register, applied to every element ----------

std::vector<double> RegVec::read_vec_converted_cached() const {
    std::vector<double> vec;
    vec.reserve(vec_len());
    for(addr_t idx = 0; idx < vec_len(); idx++) {
        vec.push_back(read_idx_converted_cached(idx));
    }
    return vec;
}

std::vector<double> RegVec::read_vec_converted() {
    update_cache();
    return read_vec_converted_cached();
}

double RegVec::read_idx_converted_cached(addr_t idx) const {
    return from_raw(m_value_type.kind() == ValueKind::sint_ ? read_idx_sint_cached(idx)
                                                            : static_cast<sint_t>(read_idx_uint_cached(idx)));
}

double RegVec::read_idx_converted(addr_t idx) {
    update_idx_cache(idx);
    return read_idx_converted_cached(idx);
}

void RegVec::write_vec_converted_cached(const std::vector<double> & vec) {
    check_vec_len(vec.size());
    if (m_value_type.kind() == ValueKind::sint_) {
        std::vector<sint_t> vec_raw;
        vec_raw.reserve(vec.size());
        for(double v : vec) { vec_raw.push_back(to_raw_checked(v)); }
        write_vec_sint_cached(vec_raw);
    } else {
        std::vector<uint_t> vec_raw;
        vec_raw.reserve(vec.size());
        for(double v : vec) { vec_raw.push_back(static_cast<uint_t>(to_raw_checked(v))); }
        write_vec_uint_cached(vec_raw);
    }
}

void RegVec::write_vec_converted(const std::vector<double> & vec) {
    write_vec_converted_cached(vec);
    write_cache();
}

void RegVec::write_idx_converted_cached(addr_t idx, double value) {
    sint_t value_raw = to_raw_checked(value);
    if (m_value_type.kind() == ValueKind::sint_) {
        write_idx_sint_cached(idx, value_raw);
    } else {
        write_idx_uint_cached(idx, static_cast<uint_t>(value_raw));
    }
}

void RegVec::write_idx_converted(addr_t idx, double value) {
    write_idx_converted_cached(idx, value);
    write_idx_cache(idx);
}

// Only the written element reaches the device (mirrors python
// RegVec.write_idx_uint / write_idx_sint awaiting write_idx_cache(idx)).
void RegVec::write_idx_uint(addr_t idx, uint_t val) {
    write_idx_uint_cached(idx, val);
    write_idx_cache(idx);
}
void RegVec::write_idx_sint(addr_t idx, sint_t val) {
    write_idx_sint_cached(idx, val);
    write_idx_cache(idx);
}
std::string RegVec::str_value_cached() const {
    // Mirrors RegVec.read_rich_str_cached in pip/skmap/src/skmap/reg.py (minus colour):
    //   [ass: ][(min <= v <= max) ][ v0, v1, ... ]
    if (m_value_type.kind() == ValueKind::char_ ) {
        return read_str_cached();
    }
    std::stringstream ss;

    Ass ass = Ass::none;
    if (m_ass != Ass::none) {
        ass = ass_check_cached(Ass::none, nullptr);
        ss << str(m_ass) << ": ";
    }
    if (has_limit()) {
        Ass limit_ass = ass_check_limit_cached();
        if (limit_ass > ass) { ass = limit_ass; }
        // One v_check expression for the whole vector, printed with every
        // recipe name resolved to a value
        ss << m_v_check->str << " ";
    }
    // With a v_convert the user values are printed, the raw ones are
    // available through the *_raw functions
    const bool conv = has_v_convert();
    const int base_conv = (m_value_type.kind() == ValueKind::bits_) ? 16 : 10;

    int base = 10;
    if (m_value_type.kind() == ValueKind::bits_) { base = 16; }
    ss << "[ ";
    switch(m_value_type.kind()) {
        case ValueKind::uint_: {
            if (conv) {
                bool first = true;
                for (double v : read_vec_converted_cached()) {
                    if (!first) { ss << ", "; }
                    first = false;
                    ss << value_to_str_from_int(v, m_value_type.elem_width(), base_conv, m_v_type == VType::f);
                }
                break;
            }
            const auto vec = read_vec_uint_cached();
            for (size_t ii = 0; ii < vec.size(); ii++) {
                if (ii) { ss << ", "; }
                ss << str_num(static_cast<sint_t>(vec[ii]), m_value_type.elem_width(), base);
            }
            break;
        }
        case ValueKind::sint_: {
            if (conv) {
                bool first = true;
                for (double v : read_vec_converted_cached()) {
                    if (!first) { ss << ", "; }
                    first = false;
                    ss << value_to_str_from_int(v, m_value_type.elem_width(), base_conv, m_v_type == VType::f);
                }
                break;
            }
            const auto vec = read_vec_sint_cached();
            for (size_t ii = 0; ii < vec.size(); ii++) {
                if (ii) { ss << ", "; }
                ss << str_num(vec[ii], m_value_type.elem_width(), base);
            }
            break;
        }
        case ValueKind::bits_: {
            const auto vec = read_vec_uint_cached();
            for (size_t ii = 0; ii < vec.size(); ii++) {
                if (ii) { ss << ", "; }
                ss << str_num(static_cast<sint_t>(vec[ii]), m_value_type.elem_width(), base);
            }
            break;
        }
        case ValueKind::flag_: {
            const auto vec = read_vec_bool_cached();
            for (size_t ii = 0; ii < vec.size(); ii++) {
                if (ii) { ss << ", "; }
                ss << (vec[ii] ? "True" : "False");
            }
            break;
        };
        case ValueKind::char_:
            // Char vectors are printed as a string by the early return above
            assert(false);
            break;
    }
    ss << " ]";
    return ss.str();
}

Ass RegVec::ass_check_limit_cached() const {
    Ass ass = Ass::none;
    for (addr_t idx = 0; idx < vec_len(); idx++) {
        Ass v_ass = ass_check_value_limit(read_idx_converted_cached(idx));
        if (v_ass > ass) { ass = v_ass; }
    }
    return ass;
}

Ass RegVec::ass_check_cached(Ass log_ass, std::vector<std::shared_ptr<RFlag>> * log_flags) const {
    (void)log_ass;
    (void)log_flags;
    if (has_limit()) {
        return ass_check_limit_cached();
    }
    if (m_ass == Ass::none) {
        return Ass::none;
    }
    bool value = false;
    for (bool v : read_vec_bool_cached()) { value = value || v; }
    return value ? m_ass : Ass::passed;
}

RFlag::RFlag(const std::string & name, uint32_t bit, Ass ass, const std::string & desc)
:   m_bit(bit)
,   m_ass(ass)
,   m_name(name)
,   m_desc(desc)
{

}

void RFlag::update_reg_cache() { reg_flags_ref().update_cache(); }
void RFlag::write_reg_cache() { reg_flags_ref().write_cache();}

// Flags are owned by a RegFlags which assigns itself in the RegFlags
// constructor; using a flag before that would dereference a null pointer.
const RegFlags & RFlag::reg_flags() const {
    return reg_flags_ref();
}

const RegFlags & RFlag::reg_flags_ref() const {
    if (!m_reg_flags) {
        throw std::runtime_error("RFlag \"" + m_name + "\" is not assigned to a RegFlags");
    }
    return *m_reg_flags;
}

RegFlags & RFlag::reg_flags_ref() {
    if (!m_reg_flags) {
        throw std::runtime_error("RFlag \"" + m_name + "\" is not assigned to a RegFlags");
    }
    return *m_reg_flags;
}

bool RFlag::read_bool_at_cached(uint32_t bit) const {
    std::span<const std::byte> data = reg_flags_ref().cache_data();
    uint32_t byte = bit / 8;
    bit  = bit % 8;
    return (static_cast<uint8_t>(data[byte]) & (1<<bit)) != 0;
}
void RFlag::write_bool_at_cache(uint32_t bit, bool v) {
    std::span<std::byte> data = reg_flags_ref().cache_data();
    uint32_t byte = bit / 8;
    uint8_t b  = bit % 8;
    // uint8_t b = v<<bit;
    // uint8_t mask = 1<<bit;
    data[byte] = static_cast<std::byte>(
        (static_cast<uint8_t>(data[byte]) & ~(1<<b)) | (static_cast<uint8_t>(v)<<b)
    );
}
bool RFlag::read_bool_cached() const {
    return read_bool_at_cached(m_bit);
}
bool RFlag::read_bool() {
    update_reg_cache();
    return read_bool_cached();
}
void RFlag::write_bool_cached(bool v) {
    write_bool_at_cache(m_bit, v);
}
void RFlag::write_bool(bool v) {
    write_bool_cached(v);
    write_reg_cache();
}
Ass RFlag::ass_check_value(bool value) const {
    if (m_ass == Ass::none) { return Ass::none; }
    if (!value) { return Ass::passed; }
    return m_ass;
}

Ass RFlag::ass_check_cached() const {
    return ass_check_value(read_bool_cached());
}
std::string RFlag::str_value_cached() const {
    std::ostringstream oss;
    if (m_ass != Ass::none) {
        ::operator<<(oss, m_ass) << ": ";
    }
    // python prints the bool, i.e. True / False
    oss << (read_bool_cached() ? "True" : "False");
    return oss.str();
}
void RFlagVec::check_idx(addr_t idx) const {
    if (idx >= m_vec_size) {
        throw std::runtime_error("Index " + std::to_string(idx) + " out of range for flag vec \"" + name() + "\" (len " + std::to_string(m_vec_size) + ")");
    }
}

void RFlagVec::check_vec_len(size_t len) const {
    if (len != static_cast<size_t>(m_vec_size)) {
        throw std::runtime_error("Vector of length " + std::to_string(len) + " does not match flag vec \"" + name() + "\" (len " + std::to_string(m_vec_size) + ")");
    }
}

bool RFlagVec::read_idx_bool_cached(addr_t idx) const {
    check_idx(idx);
    return read_bool_at_cached(m_bit + idx);
}
void RFlagVec::write_idx_bool_cached(addr_t idx, bool v) {
    check_idx(idx);
    return write_bool_at_cache(m_bit + idx, v);
}
std::vector<bool> RFlagVec::read_vec_bool_cached() const {
    std::vector<bool> vec(m_vec_size);
    for(addr_t ii = 0; ii < m_vec_size; ii++) {
        vec[ii] = read_idx_bool_cached(ii);
    }
    return vec;
}
std::vector<bool> RFlagVec::read_vec_bool() {
    update_reg_cache();
    return read_vec_bool_cached();
}
void RFlagVec::write_vec_bool_cached(const std::vector<bool> & vec) {
    check_vec_len(vec.size());
    for(addr_t ii = 0; ii < m_vec_size; ii++) {
        write_idx_bool_cached(ii, vec[ii]);
    }
}
void RFlagVec::write_vec_bool(const std::vector<bool> & vec) {
    write_vec_bool_cached(vec);
    write_reg_cache();
}
Ass RFlagVec::ass_check_cached() const {
    bool value = false;
    for(bool v : read_vec_bool_cached()) { value = value || v; }
    return ass_check_value(value);
}

std::string RFlagVec::str_value_cached() const {
    std::ostringstream oss;
    if (m_ass != Ass::none) {
        ::operator<<(oss, m_ass) << ": ";
    }
    oss << "0b";
    // Most significant bit first (python iterates lv[::-1]).
    const auto vec = read_vec_bool_cached();
    for (size_t ii = vec.size(); ii > 0; ii--) {
        oss << static_cast<int>(vec[ii - 1]);
    }
    return oss.str();
}

bool RegFlags::has_ass() const {
    for( const auto & f : m_flags) {
        if (f->ass() != Ass::none) { return true; }
    }
    return false;
}

Ass RegFlags::ass_check_cached(Ass log_ass, std::vector<std::shared_ptr<RFlag>> * log_flags) const {
    Ass ass = Ass::none;
    for( const auto & f : m_flags) {
        Ass f_ass = f->ass_check_cached();
        if (log_flags && log_ass != Ass::none && f_ass >= log_ass) {
            log_flags->push_back(f);
        }
        if (f_ass > ass ) { ass = f_ass; }
    }
    return ass;
}

std::string RegFlags::str_value_cached() const {
    // Inherited from Reg, which renders a non bool flag register as
    // 0b<width bits, most significant bit first>, exactly like
    // Reg.read_rich_str_cached() in python (RegFlags has no override there).
    return Reg::str_value_cached();
}

Ass RegFlags::ass_check() {
    update_cache();
    return ass_check_cached(Ass::none, nullptr);
}

}
