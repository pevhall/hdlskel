#pragma once

#include "hdlskel/regio/regio.hpp"
#include "hdlskel/skmap/basic_types.hpp"
#include "hdlskel/skmap/head.hpp"
#include "hdlskel/skmap/reg.hpp"
#include <cassert>
#include <memory>
#include <vector>


namespace hdlskel::skmap {

// class Module;

class Module {

public:
    static std::shared_ptr<Module> make_module(std::shared_ptr<regio::Regio> regio, addr_t base_addr);
    virtual std::string name() const = 0;
    virtual id_t id() const = 0;
    virtual uint8_t version() const = 0;

    void print_reg_map();

    Head head() const {
        return unpack_head(std::span(m_cache).subspan(0, head_size));
    }
    addr_t base_addr() { return m_base_addr; }
    // friend std::shared_ptr<Module> make_module(std::shared_ptr<regio::Regio> regio, addr_t base_addr);

private:
    void init_first(std::shared_ptr<regio::Regio> regio, addr_t base_addr, std::vector<std::byte> && cached);

public: //would be nice to make these private
    Module() = default;
    virtual void init_reg_map_k() = 0;
    virtual void init_reg_map_var() = 0;
    virtual void init_last()  { };

    void add_reg_k  (std::shared_ptr<Reg> reg);
    void add_reg_var(std::shared_ptr<Reg> reg);
    bool cache_only() const { return m_cache_only; }
    bool cache_only(bool cache_only) { return m_cache_only = cache_only; }

public:
    std::span<std::byte> cache_data(addr_t addr_off, addr_t size);
    void update_cache() ;
    void update_cache(addr_t addr_off, addr_t update_size);
    void write_cache() ;
    void write_cache(addr_t addr_off, addr_t update_size);

private:
    void add_reg(std::shared_ptr<Reg> reg);

    void initalise(std::shared_ptr<regio::Regio> regio, addr_t base_addr);
    bool m_cache_only;
    addr_t m_base_addr;
    addr_t m_byte_idx;
    std::shared_ptr<regio::Regio> m_regio;
    std::vector<std::byte> m_cache;
    std::vector<std::shared_ptr<Reg>> m_vec_k;
    std::vector<std::shared_ptr<Reg>> m_vec_var;
};

class ModuleUnknown : public Module {
public:
    std::string name() const override { return "ModuleUnknown"; }
    id_t id() const override ;
    uint8_t version() const override { assert(false); return 0;};
public:
    void init_reg_map_k() override;
    void init_reg_map_var() override;
};

}
