#pragma once

#include "hdlskel/regio/regio.hpp"
#include "hdlskel/skmap/basic_types.hpp"
#include "hdlskel/skmap/head.hpp"
#include "hdlskel/skmap/reg.hpp"
#include "hdlskel/skmap/external_mem.hpp"
#include <cassert>
#include <memory>
#include <vector>
#include <map>


namespace hdlskel::regio {
class RegioCache;
}

namespace hdlskel::skmap {

class Module;

// Format an address like python's hex(): "0x0", "0x2c"
std::string str_addr(addr_t addr);

class ModuleFactory {
public:
    static std::shared_ptr<ModuleFactory> get_instance() {
        static std::shared_ptr<ModuleFactory> instance = std::make_shared<ModuleFactory>();
        return instance;
    }

    static bool register_module(std::shared_ptr<const Module> module) {
        return get_instance()->instance_register_module(module);
    }
    static std::shared_ptr<Module> get_module(const Head & head, bool allow_unkowen=false) {
        return get_instance()->instance_get_module(head, allow_unkowen);
    }
    ModuleFactory(const ModuleFactory &) = delete;
    void operator=(ModuleFactory const&)  = delete;
    ModuleFactory() {} //TODO: make private
private:
    bool instance_register_module(std::shared_ptr<const Module> module);
    std::shared_ptr<Module> instance_get_module(const Head & head, bool allow_unkowen);

    std::map<id_t, std::map<version_t, std::shared_ptr<const Module>>> m_lookup;

};

class Module {

public:
    static std::shared_ptr<Module> make_module(std::shared_ptr<regio::Regio> regio, addr_t base_addr, bool allow_unkowen = false);
    virtual std::string name()     const = 0;
    virtual id_t        id()       const = 0;
    virtual version_t   version()  const = 0;
    virtual checksum_t  checksum() const = 0;

    virtual int skmap_ver_major() const  = 0;
    virtual int skmap_ver_minor() const  = 0;
    virtual int skmap_ver_patch() const  = 0;
    virtual std::string skmap_ver_str() const  = 0;

    void print_reg_map();

    Head head() const {
        return unpack_head(std::span(m_cache).subspan(0, head_size));
    }
    addr_t base_addr() const { return m_base_addr; }
    // friend std::shared_ptr<Module> make_module(std::shared_ptr<regio::Regio> regio, addr_t base_addr);

    // --- Tree of modules (mirrors Module in pip/skmap/src/skmap/module.py) ---
    size_t len_kids() const { return m_kid_addrs.size(); }
    addr_t kid_addr_at(size_t ii) const { return m_kid_addrs[ii]; }
    // Return the kid at idx, creating it from the regio if not yet made.
    std::shared_ptr<Module> kid_at(size_t ii);

    // Create all kids.
    std::vector<std::shared_ptr<Module>> & kids();
    // Kids that have already been created (nullptr when not yet made).
    const std::vector<std::shared_ptr<Module>> & kids_cached() const { return m_kids; }

    template<typename T>
    std::vector<std::shared_ptr<T>> kids_with_class_cached() const {
        std::vector<std::shared_ptr<T>> out;
        for (const auto & k : m_kids) {
            auto t = std::dynamic_pointer_cast<T>(k);
            if (t) { out.push_back(t); }
        }
        return out;
    }
    template <class T>
    std::shared_ptr<T> only_kid_with_class_cached() const {
        auto k = kids_with_class_cached<T>();
        if (k.size() != 1) {
            throw std::runtime_error("Expected single kid of this type, got " + std::to_string(k.size()));
        }
        return k[0];
    }
    // Recursively create all modules in the tree.
    void make_tree();
    // Read the var region (and optionally external mem caches) of this module.
    void read_all(bool read_external_mem_cache, bool skip_self = false);
    // read_all of this module and all its kids (recursively).
    void read_all_tree(bool read_external_mem_cache, bool skip_self = false);

    // --- Asserts ---
    // Check the asserts of this module's var regs.
    // If log_f is not null, regs/flags with ass >= log_ass are logged in it.
    Ass check_assert_cached(Ass log_ass = Ass::none, std::vector<RegOrFlag> * log_f = nullptr) const;
    // Same, but recursively over the whole tree (all kids must be created).
    Ass check_assert_tree_cached(Ass log_ass = Ass::none, std::vector<RegOrFlag> * log_f = nullptr) const;
    // Clear (write zero) all read-clear regs of this module / the whole tree.
    void clear_reg_rc();
    void clear_reg_rc_tree();
    // Clear the asserts of this module / tree: write zero every rc reg whose
    // assert is currently raised (mirrors clear_assert / clear_assert_tree).
    void clear_assert();
    void clear_assert_tree();
    // Write zero to all var regs in the cache (device write for the rc ones).
    // Names match python, note write_zero_all_rc_cached covers *all* var regs.
    void write_zero_all_rc_cached();
    void write_zero_all_rc();
    // Regs that have an ass level or min/max limits (checked by check_assert_*).
    const std::vector<std::shared_ptr<Reg>> & arr_reg_var_ass() const { return m_arr_reg_var_ass; }
    // The constant (k) registers of the module, their values are reported by
    // the firmware (used to resolve the k names of printed v_check /
    // v_convert_wr / v_convert_rd expressions, see Reg::resolve_expr_names).
    const std::vector<std::shared_ptr<Reg>> & vec_k() const { return m_vec_k; }

    // --- Printing ---
    std::string info_line_str() const;
    void print_tree_cached() const;

    // --- Cache file persistence (mirrors write_cache_tree_to_file in
    // pip/skmap/src/skmap/module.py) ---
    // Write this module's cache (and all its kids) to a regio cache file.
    void write_cache_tree_to_file(const std::string & path);

    // When true, modules that cannot be looked up in the factory are created
    // as ModuleUnknown instead of throwing. Propagated to all kids, so a
    // whole tree of unregistered modules can be parsed.
    bool allow_unkowen() const { return m_allow_unkowen; }

private:
    // Print this module's mems and kids under `prefix` (box-drawing chars).
    void _print_tree_cached_walk(std::ostream & os, const std::string & prefix) const;
    // "<base_addr> <name> <head>" for another module (for tree lines).
    std::string info_line_of(const Module * m) const;
    // Gather this module's (and, tree version, its kids') cache into r_cache.
    void write_cache_to_regio_cache(regio::RegioCache & r_cache, bool include_external_mem = true);
    void write_cache_to_regio_cache_tree(regio::RegioCache & r_cache, bool include_external_mem = true);

private:
    void init_first(std::shared_ptr<regio::Regio> regio, addr_t base_addr, std::vector<std::byte> && cached);

protected: //would be nice to make these private
    static bool register_module(std::shared_ptr<Module> module) { return ModuleFactory::register_module(module); }
    Module() = default;
    virtual void init_reg_map_k() = 0;
    virtual void init_reg_map_var() = 0;
    virtual void init_last()  { };
    virtual std::shared_ptr<Module> make_empty() const = 0;

    void add_reg_k  (std::shared_ptr<Reg> reg);
    // void add_reg_k  (std::shared_ptr<RegVec> reg)   { add_reg_k(std::static_pointer_cast<Reg>(reg)); }
    // void add_reg_k  (std::shared_ptr<RegFlags> reg) { add_reg_k(std::static_pointer_cast<Reg>(reg)); }
    void add_reg_var(std::shared_ptr<Reg> reg);
    // void add_reg_var(std::shared_ptr<RegVec> reg)   { add_reg_var(std::static_pointer_cast<Reg>(reg)); }
    // void add_reg_var(std::shared_ptr<RegFlags> reg) { add_reg_var(std::static_pointer_cast<Reg>(reg)); }

public:
    std::span<std::byte> cache_data(addr_t addr_off, addr_t size);
    // The whole module image (head + sub + kids + k + var) as cached.
    const std::vector<std::byte> & cache() const { return m_cache; }
    void update_cache() ;
    void update_cache(addr_t addr_off, addr_t update_size);
    void write_cache() ;
    void write_cache(addr_t addr_off, addr_t update_size);
    bool cache_only() const { return m_cache_only; }
    bool cache_only(bool cache_only) { return m_cache_only = cache_only; }
    addr_t align_byte(addr_t val_size);
    size_t len_external_mem() const { return m_arr_external_mem.size(); }
    std::shared_ptr<ExternalMem> external_mem_at(size_t idx) { return m_arr_external_mem[idx]; }
    // External memories larger than this are not cached (mirrors the
    // maximum_external_mem_cache_size argument of Module.__init__ in python).
    // Must be set before make_module() to affect module creation.
    addr_t maximum_external_mem_cache_size() const { return m_maximum_external_mem_cache_size; }
    void maximum_external_mem_cache_size(addr_t size) { m_maximum_external_mem_cache_size = size; }

private:
    void align_byte_idx(addr_t size);
    void add_reg(std::shared_ptr<Reg> reg);

    void initalise(std::shared_ptr<regio::Regio> regio, addr_t base_addr);
    // Must default to false: modules are created by make_shared<>() in the
    // generated code, so an uninitialised flag made device access random.
    bool m_cache_only = false;
    addr_t m_base_addr;
    addr_t m_byte_idx;
    addr_t m_byte_align;
    addr_t m_maximum_external_mem_cache_size = maximum_external_mem_cache_size_default;
    std::shared_ptr<regio::Regio> m_regio;
    std::vector<std::byte> m_cache;
    std::vector<std::shared_ptr<Reg>> m_vec_k;
    std::vector<std::shared_ptr<Reg>> m_vec_var;
    std::vector<std::shared_ptr<Reg>> m_arr_reg_var_ass;
    std::vector<std::shared_ptr<ExternalMem>> m_arr_external_mem;
    std::vector<addr_t> m_kid_addrs;
    std::vector<std::shared_ptr<Module>> m_kids;
    bool m_allow_unkowen = false;

    friend ModuleFactory;
};

// Print a table of regs/flags as logged by check_assert_* (mirrors
// print_table_reg_list in pip/skmap/src/skmap/reg_map_table.py).
void print_table_reg_list(const std::vector<RegOrFlag> & list, const std::string & title);

class ModuleUnknown : public Module {
public:
    // Mirrors ModuleUnkowen in pip/skmap/src/skmap/module.py
    std::string name()     const override { return "Unkowen"; }
    // The id of an unknown module comes from the head that was read (python
    // keeps the head for exactly this reason).
    id_t        id()       const override ;
    version_t   version()  const override { return head().version(); };
    checksum_t  checksum() const override { return head().checksum; };

    int skmap_ver_major() const override { return ver_major; }
    int skmap_ver_minor() const override { return ver_minor; }
    int skmap_ver_patch() const override { return ver_patch; }
    std::string skmap_ver_str() const override { return ver_str; }

public:
    virtual std::shared_ptr<Module> make_empty() const override {
        return std::make_shared<ModuleUnknown>();
    };

    void init_reg_map_k() override;
    void init_reg_map_var() override;
};

}
