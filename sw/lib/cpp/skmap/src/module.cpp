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
void Module::init_first(std::shared_ptr<regio::Regio> regio, addr_t base_addr, std::vector<std::byte> && cached) {
    m_regio     = regio;
    m_base_addr = base_addr;
    m_cache     = std::move(cached);
}



void Module::add_reg(std::shared_ptr<Reg> reg) {
    reg->initalise(this, m_byte_idx);
    m_byte_idx += reg->size() ;
    m_byte_idx = ceil_multiple(m_byte_idx, reg->elem_size());
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
    ss << "0x" << std::setfill('0') << std::setw(sizeof(addr_t)*2) 
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

    table.add_row({"Addr", "Name", "Acc", "Type", "Value", "Description"});
    size_t rows = 1;
    // for (const auto & reg : m_vec_k) {
    for (size_t ii = 0; ii <  m_vec_k.size(); ii++) {
        const auto & reg = m_vec_k[ii];
        table.add_row({str_addr(reg->addr()), reg->name(), str(reg->acc()), reg->value_type().str(), reg->str_value_cached(), reg->desc()});
        if (ii != 0) {
            table.row(rows).format().hide_border_top();
        }
        rows++;
    }
    // for (const auto & reg : m_vec_var) {
    for (size_t ii = 0; ii <  m_vec_var.size(); ii++) {
        const auto & reg = m_vec_var[ii];
        table.add_row({str_addr(reg->addr()), reg->name(), str(reg->acc()), reg->value_type().str(), reg->str_value_cached(), reg->desc()});
        if (ii != 0) {
            table.row(rows).format().hide_border_top();
        }
        rows++;
    }
    table.column(0).format().width(12);
    table.column(1).format().width(18);
    table.column(2).format().width(5);
    table.column(3).format().width(10);
    table.column(4).format().width(20);


    std::cout << table << "\n";
    // tabular::render(table.str() + '\n', stdout);
}

std::shared_ptr<Module> Module::make_module(std::shared_ptr<regio::Regio> regio, addr_t base_addr) {
    std::vector<std::byte> data(head_size);
    regio->read(base_addr, data);
    Head head = unpack_head(data);
    std::cout << "head: "<<head.to_str()<<"\n";
    data.resize(head.module_size());
    std::span<std::byte> data_span(data);
    regio->read(head_size, data_span.subspan(head_size, data.size()-head_size));

    auto module = std::make_shared<ModuleUnknown>();
    module->init_first(regio, base_addr, std::move(data));

    module->m_byte_idx = head_size;
    // for (uint ii = 0; ii < head.len_kids; ii++) {}
    module->m_byte_idx += head.len_kids*word_size;

    for (uint ii = 0; ii < head.len_sub; ii++) {
    } // TODO check sub is all zero
    module->m_byte_idx += head.len_sub*word_size;

    addr_t byte_idx_expected = module->m_byte_idx + head.len_k*word_size;
    module->init_reg_map_k();
    assert(module->m_byte_idx == byte_idx_expected);

    byte_idx_expected = module->m_byte_idx + head.len_var*word_size;
    module->init_reg_map_var();
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
