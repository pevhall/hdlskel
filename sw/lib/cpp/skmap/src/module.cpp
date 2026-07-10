#include "hdlskel/skmap/basic_types.hpp"
#include "hdlskel/skmap/head.hpp"
#include "hdlskel/skmap/reg.hpp"
#include "hdlskel/skmap/module.hpp"
#include <iomanip>
#include <iostream>

// #include "tabular/table.h"
// #include "tabular/render.h"

#include <sstream>
#include <tabulate/table.hpp>

namespace hdlskel::skmap {

// std::shared_ptr<ModuleFactorv> ModuleFactory::instance = std::make_shared<ModuleFactory>();

bool ModuleFactory::instance_register_module(std::shared_ptr<const Module> module){
    std::cout << __FILE__ << ":" << __LINE__ << ": Registering moduole " << module->name() << "\n";
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

std::shared_ptr<Module> ModuleFactory::instance_get_module(id_t id, version_t version, bool allow_unkowen){
    static ModuleUnknown module_unkowen;
    std::cout << __FILE__ << ":" << __LINE__ << ": m_lookup = { ";
    for(const auto & k : m_lookup) { std::cout <<id_to_str(k.first)<<", "; }
    std::cout <<"}"<< std::endl;

    if (not m_lookup.contains(id) ) {
        if (allow_unkowen) {
            std::cerr << "Could not find registered module with id. Return ModuleUnknown";
            return module_unkowen.make_empty();
        } else {
            throw std::runtime_error("Could not find registered module with id");
        }
    }
    auto & lookup_version = m_lookup[id];
    if (not lookup_version.contains(version) ) {
        if (allow_unkowen) {
            std::cerr << "Could not find registered module with version. Return ModuleUnknown";
            return module_unkowen.make_empty();
        } else {
            throw std::runtime_error("Could not find registered module with version");
        }
    }
    return lookup_version[version]->make_empty();


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
    m_byte_idx += reg->size() ;
    align_byte_idx(reg->elem_size());
    // std::cout << __FILE__ << ":" << __LINE__ << ":" <<  m_byte_idx <<" = " <<i<< " + " <<reg->size()<<".  es "<< reg->elem_size()<<"\n";
}
void Module::add_reg_k  (std::shared_ptr<Reg> reg) {
    add_reg(reg);
    m_vec_k.push_back(reg);
}
void Module::add_reg_var(std::shared_ptr<Reg> reg) {
    add_reg(reg);
    m_vec_var.push_back(reg);
}
std::span<std::byte> Module::cache_data(addr_t addr_off, addr_t size) {
    return std::span(m_cache).subspan(addr_off, size);
}

void Module::update_cache() {
    Head h = head();
    update_cache(m_base_addr + h.module_var_addr_offset(), h.module_var_size());
}

void Module::update_cache(addr_t addr_off, addr_t update_size) {
    auto data = std::span(m_cache).subspan(addr_off, update_size);
    m_regio->read(m_base_addr + addr_off, data);
}

void Module::write_cache() {
    Head h = head();
    write_cache(m_base_addr + h.module_var_addr_offset(), h.module_var_size());
}

void Module::write_cache(addr_t addr_off, addr_t update_size) {
    auto data = std::span(m_cache).subspan(addr_off, update_size);
    m_regio->write(m_base_addr + addr_off, data);
}

std::string str_addr(addr_t addr) {
    std::stringstream ss;
    ss << "" << std::setfill('0') << std::setw(sizeof(addr_t)*2) 
       << std::hex << addr;
    return ss.str();
}

void Module::print_reg_map() {
    std::cout << "Base Addr:" << base_addr() << ", head: "<<head().to_str()<<"\n";

    tabulate::Table table;
    table.format()
    .border_left("│")
    .border_right("│")
    .border_top("─")
    .border_bottom("─")
    .corner_top_left("┼") // ("┌")
    .corner_top_right("┼") // ("┐")
    .corner_bottom_left("┼") // ("└")
    .corner_bottom_right("┼"); // ("┘")

    table.add_row({"Addr(0x)", "Name", "Ac", "Type", "Value", "Description"});
    size_t rows = 1;
    auto add_row_reg = [&table, &rows](const std::shared_ptr<const Reg> reg, bool hide_border_top) {
        table.add_row({str_addr(reg->addr()), reg->name(), str(reg->acc()), reg->value_type().str(), reg->str_value_cached(), reg->desc()});
        if (hide_border_top) {
            table.row(rows).format().hide_border_top();
        }
        rows++;
        if (reg->is_flags()) {
            const std::shared_ptr<const RegFlags> reg_flags = static_pointer_cast<const RegFlags>(reg);
            for (size_t ii = 0; ii < reg_flags->flags_size(); ii++) {
                const auto & f = reg_flags->flag_at(ii);
                table.add_row({"-", f->name(), std::to_string(f->bit()), f->value_type_str(), f->str_value_cached(), f->desc()});
                table.row(rows).format().hide_border_top();
                rows++;
            }
        }
    };
    // for (const auto & reg : m_vec_k) {
    for (size_t ii = 0; ii <  m_vec_k.size(); ii++) {
        const std::shared_ptr<const Reg> & reg = m_vec_k[ii];
        add_row_reg(reg, ii != 0);
    }
    // for (const auto & reg : m_vec_var) {
    for (size_t ii = 0; ii <  m_vec_var.size(); ii++) {
        const std::shared_ptr<const Reg> & reg = m_vec_var[ii];
        add_row_reg(reg, ii != 0);
    }

    table.column(0).format().width(10);
    table.column(1).format().width(18);
    table.column(2).format().width(4);
    table.column(3).format().width(12);
    table.column(4).format().width(20);
    table.column(5).format().width(26);

    table.column(4).format().font_align(tabulate::FontAlign::right);
    std::cout << table << "\n";
    // tabular::render(table.str() + '\n', stdout);
}

std::shared_ptr<Module> Module::make_module(std::shared_ptr<regio::Regio> regio, addr_t base_addr, bool allow_unkowen) {
    std::vector<std::byte> data(head_size);
    regio->read(base_addr, data);
    Head head = unpack_head(data);
    std::cout << "head: "<<head.to_str()<<"\n";
    data.resize(head.module_size());
    std::span<std::byte> data_span(data);
    regio->read(head_size, data_span.subspan(head_size, data.size()-head_size));

    auto module = ModuleFactory::get_module(head.id, head.version, allow_unkowen);
    module->m_byte_align = 1;
    module->m_byte_idx = head_size;

    addr_t byte_idx_sub_end = module->m_byte_idx + head.len_sub*word_size;

    enum class SubID : uint8_t {
        PAD = 0x0,
        BYTE_ALIGN = 0x1A,
    };

    addr_t var_byte_align = 1;

    while (module->m_byte_idx != byte_idx_sub_end) {
        uint8_t sub_id = static_cast<uint8_t>(data[module->m_byte_idx]);
        switch (sub_id) {
            case static_cast<uint8_t>(SubID::PAD):
                module->m_byte_idx = byte_idx_sub_end;
                break;
            case static_cast<uint8_t>(SubID::BYTE_ALIGN):
                var_byte_align = static_cast<addr_t>(data[module->m_byte_idx+1]);
                std::cout << "Sub Head: Byte Align "<<var_byte_align<<"\n";
                module->m_byte_idx += word_size;
                break;
            default:
                std::ostringstream oss;
                oss << "Unkowen sub_id 0x" << std::hex<< +sub_id << std::dec;
                throw std::runtime_error(oss.str());
        }
    } 
    //
    // auto module = std::make_shared<ModuleUnknown>();
    module->init_first(regio, base_addr, std::move(data));

    // for (uint ii = 0; ii < head.len_kids; ii++) {}
    module->m_byte_idx += head.len_kids*word_size;

    addr_t byte_idx_expected = module->m_byte_idx + head.len_k*word_size;
    std::cout <<"Initalsing map_k\n";
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
    std::cout <<"Initalsing map_var\n";
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

id_t ModuleUnknown::id() const {
    assert(false);
    id_t id;
    id.fill('\0');
    return id;
}


ValueType value_type_x32(ValueKind::bits_, 32);

void ModuleUnknown::init_reg_map_k() {
    for(uint8_t ii = 0; ii < head().len_k; ii++) {
        std::string ii_str = std::to_string(ii);
        add_reg_k(make_reg_k("Unkowen_k["+ii_str+"]", value_type_x32, "Unkowen Generic "+ii_str));
    }
}
void ModuleUnknown::init_reg_map_var() {
    for(uint8_t ii = 0; ii < head().len_var; ii++) {
        std::string ii_str = std::to_string(ii);
        add_reg_var(make_reg("Unkowen_var["+ii_str+"]", Acc::ro, value_type_x32, "Unkowen variable "+ii_str));
    }
}

}
