#include "hdlskel/skmap/module.hpp"
#include "hdlskel/regio/tcp/regio_tcp.hpp"
#include "hdlskel/regio/tcp/regio_tcp_client.hpp"
#include "hdlskel/skmap/autogen/recipe_test_bench_module.hpp"

#include <CLI/CLI.hpp>

#include <cassert>
#include <iostream>
// #include <optional>
#include <memory>
// #include <vector>

using hdlskel::regio::tcp::RegioTcpClient;

int main(int argc, char** argv) {
    CLI::App app{"Regio TCP Client CLI application"};

    size_t addr = 0;
    uint16_t port = hdlskel::regio::tcp::PORT_DEFAULT;
    std::string host = "127.0.0.1";
    app.add_option("addr", addr, "address");
    app.add_option("-p,--port", port, "port")->capture_default_str();
    app.add_option("-i,--host", host, "host")->capture_default_str();

    CLI11_PARSE(app, argc, argv);

    auto regio = std::make_shared<hdlskel::regio::tcp::RegioTcpClient>(host, port);

    std::cout << __FILE__ << ":" << __LINE__ << ": TODO REMOVE THIS LINE AND FIX THE ASSOCITATED ERROR hdlskel::skmap::autogen::RecipeTestBenchModule::registered = " << hdlskel::skmap::autogen::RecipeTestBenchModule::registered << std::endl;


    // app.add_option("-b,--bytes", my_bytes, "Input byte values (0-255)")
    //    ->expected(-1); // -1 means unlimited arguments
    std::shared_ptr<std::ostream> cout_ptr(&std::cout, [](std::ostream*) {
        // Do not delete std::cout!
    });
    regio->set_log(cout_ptr);
    auto module = hdlskel::skmap::Module::make_module(regio, addr);
    module->print_reg_map();


}
