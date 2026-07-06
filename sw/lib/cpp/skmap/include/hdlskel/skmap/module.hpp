#pragma once

#include "hdlskel/regio/regio.hpp"
#include "hdlskel/skmap/basic_types.hpp"
#include "hdlskel/skmap/head.hpp"
#include "hdlskel/skmap/reg.hpp"
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
    addr_t base_addr() { return m_base_addr; }
    // friend std::shared_ptr<Module> make_module(std::shared_ptr<regio::Regio> regio, addr_t base_addr);

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

    friend ModuleFactory;
};

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
