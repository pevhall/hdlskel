#include "hdlskel/skmap/basic_types.hpp"
#include "hdlskel/skmap/head.hpp"
#include "hdlskel/skmap/reg.hpp"
#include "hdlskel/skmap/module.hpp"
#include "hdlskel/skmap/log.hpp"
#include "hdlskel/regio/cache.hpp"
#include <algorithm>
#include <iomanip>
#include <iostream>

// #include "tabular/table.h"
// #include "tabular/render.h"

#include <sstream>
#include <tabulate/table.hpp>

namespace hdlskel::skmap {

// std::shared_ptr<ModuleFactorv> ModuleFactory::instance = std::make_shared<ModuleFactory>();

bool ModuleFactory::instance_register_module(std::shared_ptr<const Module> module){
    // std::cout << __FILE__ << ":" << __LINE__ << ": Registering module " << module->name() << "\n";
    if (not m_lookup.contains(module->id()) ) {
        std::map<version_t, std::shared_ptr<const Module>> lookup_version;
        m_lookup[module->id()] = std::move(lookup_version);
    }
    auto & lookup_version = m_lookup[module->id()];
    if (lookup_version.contains(module->version()) ) {
        throw std::runtime_error("Cannot add twice");
    }
    lookup_version[module->version()] = module;
    return true;
}

// Mirrors ModuleFactory.make_module in pip/skmap/src/skmap/module.py:
// the id+version lookup is only accepted when the head checksum matches the
// registered module's checksum, and the skmap library version the module was
// generated with is compared against this library's version. On any failure
// fall back to ModuleUnknown (allow_unkowen) or throw.
std::shared_ptr<Module> ModuleFactory::instance_get_module(const Head & head, bool allow_unkowen){
    static ModuleUnknown module_unkowen;

    std::shared_ptr<const Module> registered;

    auto it_id = m_lookup.find(head.id);
    if (it_id == m_lookup.end()) {
        // python: 'Cannot find module, Unkowen ID (head: %s)'
        log_error("Cannot find module, Unkowen ID (head: " + head.to_str() + ")");
    } else {
        auto & lookup_version = it_id->second;
        auto it_version = lookup_version.find(head.version());
        if (it_version == lookup_version.end()) {
            // python logs nothing here, which makes the "see previous errors"
            // below rather unhelpful, so report it.
            log_error("Cannot find module \"" + id_to_str(head.id) + "\" with version " + std::to_string(+head.version()));
        } else {
            registered = it_version->second;
            if (registered->checksum() != head.checksum) {
                log_error("Bad check sum for " + registered->name() + " v" + std::to_string(+head.version())
                          + ", module_head.checksum = "  + str_addr(head.checksum)
                          + ", module_class.checksum = " + str_addr(registered->checksum()));
                registered.reset();
            }
        }
    }

    if (registered) {
        // SkMap library version checks (severity mirrors python).
        if (registered->skmap_ver_major() != ver_major) {
            log_error("SKMAP major version missmatch module has " + registered->skmap_ver_str() + ", expected " + ver_str);
        }
        if (registered->skmap_ver_minor() > ver_minor) {
            log_error("SKMAP minor version missmatch module has " + registered->skmap_ver_str() + ", expected " + ver_str);
        } else if (registered->skmap_ver_minor() != ver_minor) {
            log_info("SKMAP minor version missmatch module has " + registered->skmap_ver_str() + ", expected " + ver_str);
        }
        if (registered->skmap_ver_patch() != ver_patch) {
            log_debug("SKMAP patch version missmatch module has " + registered->skmap_ver_str() + ", expected " + ver_str);
        }
        log_info("Creating module (head =  " + head.to_str() + ")");
        return registered->make_empty();
    }

    if (allow_unkowen) {
        log_warning("Return Unkowen module - see previous errors");
        return module_unkowen.make_empty();
    }
    throw std::runtime_error("Unkowen modules not allowed, raising error, see previous errors");
}


void Module::init_first(std::shared_ptr<regio::Regio> regio, addr_t base_addr, std::vector<std::byte> && cached) {
    m_regio     = regio;
    m_base_addr = base_addr;
    m_cache     = std::move(cached);
}

addr_t Module::align_byte(addr_t val_size) {
    return std::max(promote_to_sw_w(val_size*8)/8, m_byte_align);
}

void Module::align_byte_idx(addr_t size) {
    if (size != 0) {
        addr_t align = align_byte(size);
        m_byte_idx = ceil_multiple(m_byte_idx, align);
    }
}

void Module::add_reg(std::shared_ptr<Reg> reg) {
    align_byte_idx(reg->elem_size());
    reg->initalise(this, m_byte_idx);
    // std::cout << __FILE__ << ":" << __LINE__ << ": 0x" << std::hex<< m_byte_idx << std::dec <<" -> " <<reg->name()<< " " <<reg->size()<<" s.  es "<< reg->elem_size()<<"\n";
    m_byte_idx += reg->size() ;
    align_byte_idx(reg->elem_size());
}
void Module::add_reg_k  (std::shared_ptr<Reg> reg) {
    add_reg(reg);
    m_vec_k.push_back(reg);
}
void Module::add_reg_var(std::shared_ptr<Reg> reg) {
    add_reg(reg);
    m_vec_var.push_back(reg);
    if (reg->has_ass()) {
        m_arr_reg_var_ass.push_back(reg);
    }
}
std::span<std::byte> Module::cache_data(addr_t addr_off, addr_t size) {
    return std::span(m_cache).subspan(addr_off, size);
}

void Module::update_cache() {
    Head h = head();
    update_cache(h.module_var_addr_offset(), h.module_var_size());
}

void Module::update_cache(addr_t addr_off, addr_t update_size) {
    // cache_only is handled centrally here (mirrors Module.read_bytes /
    // use_cache in pip/skmap/src/skmap/module.py): the device is never
    // touched in cache only mode.
    if (m_cache_only) { return; }
    // Transfer size is padded up to a multiple of the module byte alignment
    // (mirrors Module._byte_align_size in python), clamped so the access
    // never runs past the end of the cached module image.
    addr_t size = std::min(ceil_multiple(update_size, m_byte_align),
                           static_cast<addr_t>(m_cache.size() - addr_off));
    auto data = std::span(m_cache).subspan(addr_off, size);
    m_regio->read(m_base_addr + addr_off, data);
}

void Module::write_cache() {
    Head h = head();
    write_cache(h.module_var_addr_offset(), h.module_var_size());
}

void Module::write_cache(addr_t addr_off, addr_t update_size) {
    // see update_cache: cache_only and byte align padding are handled here
    if (m_cache_only) { return; }
    addr_t size = std::min(ceil_multiple(update_size, m_byte_align),
                           static_cast<addr_t>(m_cache.size() - addr_off));
    auto data = std::span(m_cache).subspan(addr_off, size);
    m_regio->write(m_base_addr + addr_off, data);
}

std::string str_addr(addr_t addr) {
    // Mirrors python's hex(addr): "0x0", "0x2c"
    std::stringstream ss;
    ss << "0x" << std::hex << addr;
    return ss.str();
}

namespace {

// All skmap tables use the same columns as RegMapTable in
// pip/skmap/src/skmap/reg_map_table.py:
//   Addr | T | Acc | Name | Value | Description
// with flag rows putting the bit number in the "Acc" column (like python's
// add_flag()).
//
// Column widths are left for tabulate to compute from the cell contents,
// which is what python's rich table does. Explicit widths must not be used:
// tabulate wraps (instead of truncating) cells that do not fit, and its
// word_wrap() then loops forever allocating memory whenever the width minus
// the cell padding is smaller than 2 (observed as std::bad_alloc).
class RegMapTable {
public:
    static constexpr size_t num_cols = 6;

    RegMapTable() {
        m_table.format()
        .border_left("│")
        .border_right("│")
        .border_top("─")
        .border_bottom("─")
        .corner_top_left("┼")
        .corner_top_right("┼")
        .corner_bottom_left("┼")
        .corner_bottom_right("┼");
        add_row({"Addr", "T", "Acc", "Name", "Value", "Description"});
    }

    void add_row(const std::vector<std::string> & cells) {
        tabulate::Table::Row_t row(cells.begin(), cells.end());
        m_table.add_row(row);
        m_rows++;
    }

    // Draw no line above the row that was added last (used to group a flags
    // register with the rows of its individual flags).
    void join_row_with_previous() {
        if (m_rows >= 2) {
            m_table.row(m_rows-1).format().hide_border_top();
        }
    }

    void print(std::ostream & os) {
        // python column justification: Addr right, T right, Acc left,
        // Name left, Value right, Description left
        const tabulate::FontAlign align[num_cols] = {
            tabulate::FontAlign::right, tabulate::FontAlign::right, tabulate::FontAlign::left,
            tabulate::FontAlign::left,  tabulate::FontAlign::right, tabulate::FontAlign::left,
        };
        for (size_t ii = 0; ii < num_cols; ii++) {
            m_table.column(ii).format().font_align(align[ii]);
        }
        os << m_table << "\n";
    }

private:
    tabulate::Table m_table;
    size_t m_rows = 0;
};

// One register row, mirrors RegMapTable.add_reg()
void add_reg_row(RegMapTable & table, const Reg & reg) {
    table.add_row({str_addr(reg.addr()), reg.value_type().str(), str(reg.acc()), reg.name(), reg.str_value_cached(), reg.desc()});
}

// One flag row, mirrors RegMapTable.add_flag()
void add_flag_row(RegMapTable & table, const RFlag & f) {
    table.add_row({"-", "b", std::to_string(f.bit()), f.name(), f.str_value_cached(), f.desc()});
}

} // namespace

void Module::print_reg_map() {
    // python passes info_line_str() as the table title
    std::cout << info_line_str() << "\n";

    RegMapTable table;

    auto add_row_reg = [&table](const std::shared_ptr<const Reg> reg, bool join_with_previous) {
        add_reg_row(table, *reg);
        if (join_with_previous) {
            table.join_row_with_previous();
        }
        if (reg->is_flags()) {
            const std::shared_ptr<const RegFlags> reg_flags = static_pointer_cast<const RegFlags>(reg);
            for (size_t ii = 0; ii < reg_flags->flags_size(); ii++) {
                const auto & f = reg_flags->flag_at(ii);
                add_flag_row(table, *f);
                table.join_row_with_previous();
            }
        }
    };
    for (size_t ii = 0; ii <  m_vec_k.size(); ii++) {
        const std::shared_ptr<const Reg> & reg = m_vec_k[ii];
        add_row_reg(reg, ii != 0);
    }
    for (size_t ii = 0; ii <  m_vec_var.size(); ii++) {
        const std::shared_ptr<const Reg> & reg = m_vec_var[ii];
        add_row_reg(reg, ii != 0);
    }
    for (const auto & mem : m_arr_external_mem) {
        std::string type_str;
        std::string name_str = "(unnamed mem)";
        std::string desc_str;
        if (mem->has_details()) {
            type_str = mem->value_type().str();
            name_str = mem->name();
            desc_str = mem->desc();
        }
        // Mirrors RegMapTable.add_mem()
        table.add_row({
            str_addr(mem->base_addr()),
            type_str,
            str(mem->acc()),
            name_str,
            "(Mem size:" + std::to_string(mem->size()) + " B)",
            desc_str
        });
        table.join_row_with_previous();
    }

    table.print(std::cout);
}

void print_table_reg_list(const std::vector<RegOrFlag> & list, const std::string & title) {
    std::cout << title << "\n";
    RegMapTable table;
    const Reg * reg_prev = nullptr;
    for (const auto & v : list) {
        if (const auto * f_sp = std::get_if<std::shared_ptr<RFlag>>(&v)) {
            const std::shared_ptr<RFlag> & f = *f_sp;
            const Reg & reg = f->reg_flags();
            if (&reg != reg_prev) {
                add_reg_row(table, reg);
                table.join_row_with_previous();
                reg_prev = &reg;
            }
            add_flag_row(table, *f);
            table.join_row_with_previous();
        } else {
            const std::shared_ptr<Reg> & reg = std::get<std::shared_ptr<Reg>>(v);
            add_reg_row(table, *reg);
            table.join_row_with_previous();
            reg_prev = nullptr;
        }
    }

    table.print(std::cout);
}

// --- Tree of modules ---

std::shared_ptr<Module> Module::kid_at(size_t ii) {
    assert(ii < m_kid_addrs.size());
    if (m_kids[ii] == nullptr) {
        // Propagate allow_unkowen so a whole tree of unregistered modules can
        // be parsed (as ModuleUnknown) instead of throwing on the first kid.
        m_kids[ii] = make_module(m_regio, m_kid_addrs[ii], m_allow_unkowen);
    }
    return m_kids[ii];
}

std::vector<std::shared_ptr<Module>> & Module::kids() {
    for (size_t ii = 0; ii < m_kid_addrs.size(); ii++) {
        kid_at(ii);
    }
    return m_kids;
}

void Module::make_tree() {
    for (auto & k : kids()) {
        k->make_tree();
    }
}

void Module::read_all(bool read_external_mem_cache, bool skip_self) {
    if (!skip_self) {
        update_cache();
    }
    if (read_external_mem_cache) {
        for (auto & mem : m_arr_external_mem) {
            // Only cached memories are read (python checks
            // isinstance(mem, ExternalMemCached)); large ones are read on
            // demand instead.
            if (mem->is_cached()) {
                mem->read(0, mem->size());
            }
        }
    }
}

void Module::read_all_tree(bool read_external_mem_cache, bool skip_self) {
    read_all(read_external_mem_cache, skip_self);
    for (auto & k : kids()) {
        k->read_all_tree(read_external_mem_cache);
    }
}

// --- Asserts ---

Ass Module::check_assert_cached(Ass log_ass, std::vector<RegOrFlag> * log_f) const {
    Ass ass = Ass::none;
    for (const auto & reg : m_arr_reg_var_ass) {
        std::vector<std::shared_ptr<RFlag>> flag_log;
        Ass r_ass = reg->ass_check_cached(log_ass, &flag_log);
        if (log_f) {
            if (reg->is_flags()) {
                for (auto & f : flag_log) {
                    log_f->push_back(f);
                }
            } else if (log_ass != Ass::none && r_ass >= log_ass) {
                log_f->push_back(reg);
            }
        }
        if (r_ass > ass) {
            ass = r_ass;
        }
    }
    return ass;
}

Ass Module::check_assert_tree_cached(Ass log_ass, std::vector<RegOrFlag> * log_f) const {
    Ass ass = check_assert_cached(log_ass, log_f);
    for (const auto & kid : m_kids) {
        assert(kid != nullptr); // tree must be created first
        Ass kid_ass = kid->check_assert_tree_cached(log_ass, log_f);
        if (kid_ass > ass) {
            ass = kid_ass;
        }
    }
    return ass;
}

void Module::clear_reg_rc() {
    for (const auto & reg : m_vec_var) {
        if (reg->acc() == Acc::rc) {
            reg->write_zero();
        }
    }
}

void Module::clear_reg_rc_tree() {
    clear_reg_rc();
    for (auto & k : kids()) {
        k->clear_reg_rc_tree();
    }
}

// Write zero to every var reg whose assert is currently raised, only rc regs
// can actually be cleared (mirrors Module.clear_assert in python).
void Module::clear_assert() {
    for (const auto & reg : m_arr_reg_var_ass) {
        if (reg->ass_check_cached(Ass::none, nullptr) >= Ass::debug && reg->acc() == Acc::rc) {
            reg->write_zero();
        }
    }
}

void Module::clear_assert_tree() {
    clear_assert();
    for (auto & k : kids()) {
        k->clear_assert_tree();
    }
}

// Names match python; note write_zero_all_rc_cached covers *all* var regs
// (python does not filter on Acc.rc there, only the device version does).
void Module::write_zero_all_rc_cached() {
    for (const auto & reg : m_vec_var) {
        reg->write_zero_cached();
    }
}

void Module::write_zero_all_rc() {
    for (const auto & reg : m_vec_var) {
        if (reg->acc() == Acc::rc) {
            reg->write_zero();
        }
    }
}

// --- Printing ---

std::string Module::info_line_str() const {
    return str_addr(m_base_addr) + " " + name() + " " + head().to_str();
}

void Module::_print_tree_cached_walk(std::ostream & os, const std::string & prefix) const {
    // Gather the lines that belong under this module: external mems first,
    // then each kid (with its own subtree). We do two passes so we know which
    // entries are last and can use ┗ vs ┣ box-drawing connectors.
    struct Entry {
        std::string text;
        bool is_kid;            // kids can have their own subtree
        const Module * kid;     // null for mems / uninitalised
    };
    std::vector<Entry> entries;
    for (const auto & mem : m_arr_external_mem) {
        Entry e;
        e.text   = str_addr(mem->base_addr()) + " " +
                   (mem->has_details() ? mem->name() : std::string("(unnamed mem)")) + " " +
                   str(mem->acc()) + " " + std::to_string(mem->size()) + " B";
        e.is_kid = false;
        e.kid    = nullptr;
        entries.push_back(e);
    }
    for (size_t ii = 0; ii < m_kid_addrs.size(); ii++) {
        Entry e;
        e.is_kid = true;
        e.kid    = m_kids[ii].get();
        if (m_kids[ii] == nullptr) {
            e.text = str_addr(m_kid_addrs[ii]) + " Uninitialised module";
        } else {
            e.text = info_line_of(m_kids[ii].get());
        }
        entries.push_back(e);
    }
    for (size_t ii = 0; ii < entries.size(); ii++) {
        bool last = (ii + 1 == entries.size());
        const std::string & conn = last ? "┗" : "┣";
        const std::string & cont = last ? " " : "┃";
        // rich's Tree guides are "┗━━ ", "┣━━ ", "┃   " and "    "
        os << prefix << conn << "━━ " << entries[ii].text << "\n";
        if (entries[ii].kid != nullptr) {
            entries[ii].kid->_print_tree_cached_walk(os, prefix + cont + "   ");
        }
    }
}

std::string Module::info_line_of(const Module * m) const {
    // Non-static helper so we can call info_line_str() on another module.
    std::string s;
    s += str_addr(m->base_addr());
    s += " ";
    s += m->name();
    s += " ";
    s += m->head().to_str();
    return s;
}

void Module::print_tree_cached() const {
    std::cout << info_line_str() << "\n";
    _print_tree_cached_walk(std::cout, "");
}

std::shared_ptr<Module> Module::make_module(std::shared_ptr<regio::Regio> regio, addr_t base_addr, bool allow_unkowen) {
    std::vector<std::byte> data(head_size);
    regio->read(base_addr, data);
    Head head = unpack_head(data);
    // python asserts head.sync == SYNC and head.flags == 0; throw instead of
    // asserting so a corrupt image is caught in release builds too.
    if (!head.valid_sync()) {
        throw std::runtime_error("make_module: bad sync " + head.to_str());
    }
    if (head.flags() != 0) {
        throw std::runtime_error("make_module: head flags are not currently supported");
    }
    data.resize(head.module_size());
    std::span<std::byte> data_span(data);
    regio->read(base_addr + head_size, data_span.subspan(head_size, data.size()-head_size));

    auto module = ModuleFactory::get_module(head, allow_unkowen);
    module->m_allow_unkowen = allow_unkowen;
    module->m_byte_align = 1;
    module->m_byte_idx = head_size;


    // Read the kid addresses from the cache (they come right after the sub heads)
    module->m_kid_addrs.reserve(head.len_kids);
    for (uint8_t ii = 0; ii < head.len_kids; ii++) {
        addr_t kid_addr = 0;
        std::memcpy(&kid_addr, &data[module->m_byte_idx], sizeof(addr_t));
        module->m_byte_idx += 4;
        // python: assert kid_addr != 0, addr 0 should never be a kid
        if (kid_addr == 0) {
            throw std::runtime_error("make_module: kid address 0 is not valid");
        }
        module->m_kid_addrs.push_back(kid_addr);

    }
    module->m_kids.resize(head.len_kids, nullptr);

    enum class SubID : uint8_t {
        PAD = 0x0,
        BYTE_ALIGN = 0x1A,
        EXTERNAL_MEM = 0x3B,
    };

    addr_t var_byte_align = module->m_byte_align;

    addr_t byte_idx_sub_end = module->m_byte_idx + head.len_sub*word_size;
    while (module->m_byte_idx < byte_idx_sub_end) {
        uint8_t sub_id = static_cast<uint8_t>(data[module->m_byte_idx]);
        switch (sub_id) {
            case static_cast<uint8_t>(SubID::PAD):
                // python breaks out of the sub header loop on padding
                module->m_byte_idx = byte_idx_sub_end;
                break;
            case static_cast<uint8_t>(SubID::BYTE_ALIGN):
                var_byte_align = static_cast<addr_t>(data[module->m_byte_idx+1]);
                // python asserts the alignment is a power of 2
                if ((var_byte_align & (var_byte_align-1)) != 0) {
                    throw std::runtime_error("make_module: byte align " + std::to_string(var_byte_align) + " is not a power of 2");
                }
                log_info("sub_head BYTE_ALIGN = " + std::to_string(var_byte_align));
                module->m_byte_idx += word_size;
                break;
            case static_cast<uint8_t>(SubID::EXTERNAL_MEM): {
                Acc acc = static_cast<Acc>(data[module->m_byte_idx + 1]);
                addr_t ext_base_addr;
                addr_t ext_size;
                std::memcpy(&ext_base_addr, &data[module->m_byte_idx + 4], sizeof(addr_t));
                std::memcpy(&ext_size, &data[module->m_byte_idx + 8], sizeof(addr_t));
                // Only cache memories up to the configured limit (python
                // creates an ExternalMemCached, else a plain ExternalMem).
                if (ext_size > module->m_maximum_external_mem_cache_size) {
                    log_warning(module->name() + " at addr " + std::to_string(base_addr)
                                + ", will not cache external mem " + std::to_string(module->m_arr_external_mem.size())
                                + ", as size to large, got " + std::to_string(ext_size) + " B");
                } else {
                    log_info("sub_head EXTERNAL_MEM: base_addr=" + str_addr(ext_base_addr)
                             + ", size_bytes=" + std::to_string(ext_size) + ", acc=" + str(acc));
                }
                module->m_arr_external_mem.push_back(std::make_shared<ExternalMem>(
                    regio, ext_base_addr, ext_size, acc, module->m_maximum_external_mem_cache_size));
                module->m_byte_idx += 3 * word_size;
                break;
            }
            default:
                std::ostringstream oss;
                oss << "Unkowen sub_id 0x" << std::hex<< +sub_id << std::dec;
                throw std::runtime_error(oss.str());
        }
    }
    // python forces the index to the end of the sub header region
    if (module->m_byte_idx < byte_idx_sub_end) {
        module->m_byte_idx = byte_idx_sub_end;
    }

    module->init_first(regio, base_addr, std::move(data));

    addr_t byte_idx_expected = module->m_byte_idx + head.len_k*word_size;
    // std::cout <<"Initalsing map_k\n";
    module->init_reg_map_k();
    module->align_byte_idx(word_size);
    if( module->m_byte_idx != byte_idx_expected ) {
        std::ostringstream oss;
        oss << "make_module::k end idx (got "<<module->m_byte_idx<<", expected "<<byte_idx_expected<<")";
        throw std::runtime_error(oss.str());
    }
    // assert(module->m_byte_idx == byte_idx_expected);

    module->m_byte_align = var_byte_align;
    byte_idx_expected = module->m_byte_idx + head.len_var*word_size;
    // std::cout <<"Initalsing map_var\n";
    module->init_reg_map_var();
    module->align_byte_idx(word_size);
    if( module->m_byte_idx != byte_idx_expected ) {
        std::ostringstream oss;
        oss << "make_module::var end idx (got "<<module->m_byte_idx<<", expected "<<byte_idx_expected<<")";
        throw std::runtime_error(oss.str());
    }
    assert(module->m_byte_idx == byte_idx_expected);

    module->init_last();
    return module;
}

// std::shared_ptr<Module> make_Module(std::shared_ptr<regio::Regio> regio, size_t base_addr);

// --- Cache file persistence ---

void Module::write_cache_to_regio_cache(regio::RegioCache & r_cache, bool include_external_mem) {
    r_cache.cache_write(m_base_addr, std::span<const std::byte>(m_cache));

    if (include_external_mem) {
        for (auto & mem : m_arr_external_mem) {
            if (!mem->cache_loaded()) {
                // Mirrors the python warning for memories that are not cached
                // (too large) or have not been read yet.
                log_warning(name() + " at " + std::to_string(m_base_addr)
                            + ", mem interface has not cached cached (probably too large)");
                continue;
            }
            r_cache.cache_write(mem->base_addr(), mem->read_cached(0, mem->size()));
        }
    }
}

void Module::write_cache_to_regio_cache_tree(regio::RegioCache & r_cache, bool include_external_mem) {
    write_cache_to_regio_cache(r_cache, include_external_mem);

    for (auto & k : m_kids) {
        if (k == nullptr) {
            log_warning(name() + " at " + std::to_string(m_base_addr) + ", kid not yet initalised wil not write to cache");
            continue;
        }
        k->write_cache_to_regio_cache_tree(r_cache);
    }
}

void Module::write_cache_tree_to_file(const std::string & path) {
    regio::RegioCache r_cache;
    write_cache_to_regio_cache_tree(r_cache);
    r_cache.save_to_file(path);
}

// The id comes from the head that was read for this module (python's
// ModuleUnkowen keeps the head around for the same reason).
id_t ModuleUnknown::id() const {
    if (cache().size() < head_size) {
        id_t id;
        id.fill('\0');
        return id;
    }
    return head().id;
}


ValueType value_type_x32(ValueKind::bits_, 32);

// Mirrors ModuleUnkowen.initalise_reg_map_k/var in python
void ModuleUnknown::init_reg_map_k() {
    for(uint8_t ii = 0; ii < head().len_k; ii++) {
        std::string ii_str = std::to_string(ii);
        add_reg_k(make_reg_k("UNKOWN_K_"+ii_str, value_type_x32, "Unkowen constant "+ii_str));
    }
}
void ModuleUnknown::init_reg_map_var() {
    for(uint8_t ii = 0; ii < head().len_var; ii++) {
        std::string ii_str = std::to_string(ii);
        add_reg_var(make_reg("UNKOWN_VAR_"+ii_str, Acc::na, value_type_x32, "Unkowen variable "+ii_str));
    }
}

}
