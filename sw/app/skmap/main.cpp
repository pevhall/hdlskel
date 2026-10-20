#include "hdlskel/skmap/module.hpp"
#include "hdlskel/regio/tcp/regio_cli_utils.hpp"
#include "hdlskel/regio/tcp/regio_tcp.hpp"
// Including the generated modules registers them with the ModuleFactory
#include "hdlskel/skmap/autogen_test/recipe_test_bench_module.hpp"
#include "hdlskel/skmap/autogen_test/test_skmap_tree_module.hpp"

#include <CLI/CLI.hpp>

#include <iostream>
#include <memory>
#include <string>
#include <vector>

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
int skmap_main(int argc, char** argv);

int main(int argc, char** argv) {
    try {
        return skmap_main(argc, argv);
    } catch (const std::exception& e) {
        // e.g. an unknown module id, a bad cache file or an unmapped address.
        std::cerr << "Error: " << e.what() << "\n";
        return 1;
    }
}

int skmap_main(int argc, char** argv) {
    CLI::App app{
        "Interact with skmap regio server or cached skmap files",
        "Skmap Utility"
    };

    // --- regio.cli_utils.add_parser_args (-i, -f, -p, --mtu, --debug-print-regio) ---
    hdlskel::regio::cli::RegioArgs regio_args;
    hdlskel::regio::cli::add_parser_args(app, regio_args);

    hdlskel::skmap::addr_t addr = 0;
    app.add_option("-a,--addr", addr, "Regio Address")
        ->capture_default_str()
        ->transform([](std::string s) { return std::to_string(hdlskel::regio::cli::auto_int(s)); });

    bool map = false;
    bool tree = false;
    bool asserts = false;
    bool allow_unkowen = false;
    bool clear = false;
    app.add_flag("-m,--map", map, "Print SKMap reg map");
    app.add_flag("-t,--tree", tree, "Traverse tree");
    app.add_flag("-s,--asserts", asserts, "print asserts");
    // Python spells the long option --allow-unknowen, accept both.
    app.add_flag("-x,--allow-unkowen,--allow-unknowen", allow_unkowen,
                 "allow unknown modules (returns a default unknown module)");
    app.add_flag("-c,--clear", clear, "Clear all `read clear` registers");

    std::string write;
    app.add_option("-w,--write", write,
                   "If specified, write to cache file");

    // -v, -vv, -vvv
    int verbose = 0;
    app.add_flag("-v", verbose, "Increase logging verbosity (repeat up to -vv)");

    CLI11_PARSE(app, argc, argv);

    auto regio = hdlskel::regio::cli::make_regio_from_args(regio_args);

    // --- Mirrors main in pip/skmap/src/skmap/cli_utils.py ---
    auto module = Module::make_module(regio, addr, allow_unkowen);
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

    if (!write.empty()) {
        module->write_cache_tree_to_file(write);
    }

    return 0;
}
