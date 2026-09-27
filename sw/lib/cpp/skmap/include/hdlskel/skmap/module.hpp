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


namespace hdlskel::skmap {

class Module;

class ModuleFactory {
public:
    static std::shared_ptr<ModuleFactory> get_instance() {
        static std::shared_ptr<ModuleFactory> instance = std::make_shared<ModuleFactory>();
        return instance;
    }

    static bool register_module(std::shared_ptr<const Module> module) {
        return get_instance()->instance_register_module(module);
    }
    static std::shared_ptr<Module> get_module(id_t id, version_t version, bool allow_unkowen=false) {
        return get_instance()->instance_get_module(id, version, allow_unkowen);
    }
    ModuleFactory(const ModuleFactory &) = delete;
    void operator=(ModuleFactory const&)  = delete;
    ModuleFactory() {} //TODO: make private
private:
    bool instance_register_module(std::shared_ptr<const Module> module);
    std::shared_ptr<Module> instance_get_module(id_t id, version_t version, bool allow_unkowen);

    std::map<id_t, std::map<version_t, std::shared_ptr<const Module>>> m_lookup;

};

class Module {

public:
    static std::shared_ptr<Module> make_module(std::shared_ptr<regio::Regio> regio, addr_t base_addr, bool allow_unkowen = false);
    virtual std::string name()     const = 0;
    virtual id_t        id()       const = 0;
    virtual version_t   version()  const = 0;
    virtual checksum_t  checksum() const = 0;

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
    const std::vector<std::shared_ptr<Module>> & kids_cached() const { return m_kids; }
    template <class T>
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
        assert(k.size() == 1);
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
    // Regs that have an ass level or min/max limits (checked by check_assert_*).
    const std::vector<std::shared_ptr<Reg>> & arr_reg_var_ass() const { return m_arr_reg_var_ass; }

    // --- Printing ---
    std::string info_line_str() const;
    void print_tree_cached() const;

private:
    // Print this module's mems and kids under `prefix` (box-drawing chars).
    void _print_tree_cached_walk(std::ostream & os, const std::string & prefix) const;
    // "<base_addr> <name> <head>" for another module (for tree lines).
    std::string info_line_of(const Module * m) const;

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
    void update_cache() ;
    void update_cache(addr_t addr_off, addr_t update_size);
    void write_cache() ;
    void write_cache(addr_t addr_off, addr_t update_size);
    bool cache_only() const { return m_cache_only; }
    bool cache_only(bool cache_only) { return m_cache_only = cache_only; }
    addr_t align_byte(addr_t val_size);
    size_t len_external_mem() const { return m_arr_external_mem.size(); }
    std::shared_ptr<ExternalMem> external_mem_at(size_t idx) { return m_arr_external_mem[idx]; }

private:
    void align_byte_idx(addr_t size);
    void add_reg(std::shared_ptr<Reg> reg);

    void initalise(std::shared_ptr<regio::Regio> regio, addr_t base_addr);
    bool m_cache_only;
    addr_t m_base_addr;
    addr_t m_byte_idx;
    addr_t m_byte_align;
    std::shared_ptr<regio::Regio> m_regio;
    std::vector<std::byte> m_cache;
    std::vector<std::shared_ptr<Reg>> m_vec_k;
    std::vector<std::shared_ptr<Reg>> m_vec_var;
    std::vector<std::shared_ptr<Reg>> m_arr_reg_var_ass;
    std::vector<std::shared_ptr<ExternalMem>> m_arr_external_mem;
    std::vector<addr_t> m_kid_addrs;
    std::vector<std::shared_ptr<Module>> m_kids;

    friend ModuleFactory;
};

// Print a table of regs/flags as logged by check_assert_* (mirrors
// print_table_reg_list in pip/skmap/src/skmap/reg_map_table.py).
void print_table_reg_list(const std::vector<RegOrFlag> & list, const std::string & title);

class ModuleUnknown : public Module {
public:
    constexpr static std::string class_name = "ModuleUnknown";
    std::string name()     const override { return ModuleUnknown::class_name; }
    id_t        id()       const override ;
    version_t   version()  const override { assert(false); return 0;};
    checksum_t  checksum() const override { assert(false); return 0;};

public:
    virtual std::shared_ptr<Module> make_empty() const override {
        return std::make_shared<ModuleUnknown>();
    };

    void init_reg_map_k() override;
    void init_reg_map_var() override;
};

}
