#include "hdlskel/skmap/module.hpp"
#include "hdlskel/regio/tcp/regio_tcp.hpp"
#include "hdlskel/regio/tcp/regio_tcp_client.hpp"
// Including the generated modules registers them with the ModuleFactory
#include "hdlskel/skmap/autogen_test/recipe_test_bench_module.hpp"
#include "hdlskel/skmap/autogen_test/test_skmap_tree_module.hpp"

#include <CLI/CLI.hpp>

#include <iostream>
#include <memory>
#include <vector>

using hdlskel::regio::tcp::RegioTcpClient;
using hdlskel::skmap::Module;
using hdlskel::skmap::RegOrFlag;
using hdlskel::skmap::Ass;

// Reference the generated modules' `registered` statics so the linker keeps
// the autogen library (as-needed), which registers the modules with the
// ModuleFactory in their static initialisers.
static bool modules_registered =
    hdlskel::skmap::autogen::RecipeTestBenchModule::registered &&
    hdlskel::skmap::autogen::TestSkmapTreeModule::registered;

// Mirrors parse_args in pip/skmap/src/skmap/cli_utils.py
int main(int argc, char** argv) {
    CLI::App app{
        "Skmap Utility",
        "Interact with skmap regio server or cached skmap files"
    };

    std::string host = "127.0.0.1";
    app.add_option("-i,--host", host, "Connect to SKMap TCP Regio server")->capture_default_str();

    uint16_t port = hdlskel::regio::tcp::PORT_DEFAULT;
    app.add_option("-p,--port", port, "SKMap TCP Regio server's port number")->capture_default_str();

    hdlskel::skmap::addr_t addr = 0;
    app.add_option("-a,--addr", addr, "Regio Address")
        ->capture_default_str()
        ->transform([](std::string s) { return std::to_string(std::stoul(s, nullptr, 0)); }); // allow hex

    bool map = false;
    bool tree = false;
    bool asserts = false;
    bool allow_unknowen = false;
    bool clear = false;
    bool debug_print_regio = false;
    app.add_flag("-m,--map", map, "Print SKMap reg map");
    app.add_flag("-t,--tree", tree, "Traverse tree");
    app.add_flag("-s,--asserts", asserts, "print asserts");
    app.add_flag("-x,--allow-unknowen", allow_unknowen, "allow unknown modules");
    app.add_flag("-c,--clear", clear, "Clear all `read clear` registers");
    app.add_flag("--debug-print-regio", debug_print_regio, "Debug: Print regio operations");

    CLI11_PARSE(app, argc, argv);

    auto regio = std::make_shared<RegioTcpClient>(host, port);

    if(debug_print_regio) {
        std::shared_ptr<std::ostream> cout_ptr(&std::cout, [](std::ostream*) {
            // Do not delete std::cout!
        });
        regio->set_log(cout_ptr);
    }

    // --- Mirrors main in pip/skmap/src/skmap/cli_utils.py ---
    auto module = Module::make_module(regio, addr, allow_unknowen);
    if (tree) {
        module->read_all_tree(/*read_external_mem_cache=*/false, /*skip_self=*/true);
    }

    if (tree) {
        module->make_tree();
        module->print_tree_cached();
    }

    if (map) {
        module->print_reg_map();
    }

    if (asserts) {
        Ass log_ass = Ass::debug;
        std::vector<RegOrFlag> list_reg;
        Ass ass = tree
            ? module->check_assert_tree_cached(log_ass, &list_reg)
            : module->check_assert_cached(log_ass, &list_reg);
        hdlskel::skmap::print_table_reg_list(list_reg, "Asserts (max " + hdlskel::skmap::str(ass) + ")");
    }

    if (clear) {
        if (tree) {
            std::cout << "Clearing all RC regs in tree\n";
            module->clear_reg_rc_tree();
        } else {
            std::cout << "Clearing all RC regs in module\n";
            module->clear_reg_rc();
        }
    }

    return 0;
}
