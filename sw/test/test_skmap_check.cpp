// Test the recipe value options of the C++ library: `v_check` (value limit of
// the module user) and `v_convert` (conversion between the user value and the
// value of the register). Runs on a captured regio file, no simulation needed:
//   sw/build/test/test_skmap_check test/data/test_recipe.skmap
#include "hdlskel/regio/cache.hpp"
#include "hdlskel/skmap/module.hpp"
#include "hdlskel/skmap/reg.hpp"
#include "hdlskel/skmap/autogen_test/recipe_test_bench_module.hpp"

#include <array>
#include <cmath>
#include <iostream>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

using namespace hdlskel::skmap;

static int g_checks = 0;
static int g_failed = 0;

#define CHECK(cond)                                                      \
    do {                                                                 \
        g_checks++;                                                      \
        if (!(cond)) {                                                   \
            g_failed++;                                                  \
            std::cerr << "FAILED " << __FILE__ << ":" << __LINE__ << ": " \
                      << #cond << "\n";                                  \
        }                                                                \
    } while (0)

#define CHECK_THROWS(expr)                                               \
    do {                                                                 \
        g_checks++;                                                      \
        bool threw = false;                                              \
        try { (void)(expr); } catch (const std::exception &) { threw = true; } \
        if (!threw) {                                                    \
            g_failed++;                                                  \
            std::cerr << "FAILED " << __FILE__ << ":" << __LINE__        \
                      << ": expected an exception from " << #expr << "\n"; \
        }                                                                \
    } while (0)

// The checks of this test are all fatal, a failing one fails the test
#define ASSERT(cond) CHECK(cond)

static std::shared_ptr<autogen::RecipeTestBenchModule> make_module(const std::string & file) {
    auto regio = std::make_shared<hdlskel::regio::RegioCache>();
    regio->load_from_file(file);
    // the registered module with the id of the recipe is created by the factory
    auto module = Module::make_module(regio, 0);
    return std::dynamic_pointer_cast<autogen::RecipeTestBenchModule>(module);
}

// The recipe checks that RW_MULT (printed as its value 2) divides the value.
static const std::string RW_LEN_CHECK = "((v % 2) == 0)";
// regs_rw: (v >= (-1 * 2)) && (v <= 100) && ((v % 2) == 0)
static const std::string REGS_RW_CHECK = "(((v >= (-1 * 2)) && (v <= 100)) && ((v % 2) == 0))";

static void test_v_check_scalar(autogen::RecipeTestBenchModule & m) {
    // RW_LEN is a constant register (a k reg) of the recipe with a v_check,
    // the firmware value is 3, so the check has to fail and be printed
    ASSERT(m.RW_LEN_inst()->v_check().has_value());
    ASSERT(m.RW_LEN_inst()->v_check()->str == RW_LEN_CHECK);
    CHECK(m.RW_LEN_inst()->has_limit());
    // v_type of a uint register, it is what the recipe v_type defaults to
    CHECK(m.RW_LEN_inst()->v_type() == VType::u);
    CHECK(m.RW_LEN() == 3);
    CHECK(m.RW_LEN_inst()->ass_check_cached(Ass::none, nullptr) == Ass::error);
    ASSERT(m.RW_LEN_inst()->str_value_cached() == RW_LEN_CHECK + " 3");
    // the check text resolves names, the recipe is not needed to print a module
    ASSERT(m.RW_LEN_inst()->str_value_cached().find("RW_MULT") == std::string::npos);

    // RW_MULT() is 2, an even value passes
    const auto check = m.RW_LEN_inst()->v_check();
    CHECK((*check)(4));
    CHECK(!(*check)(5));
}

static void test_v_check_vec(autogen::RecipeTestBenchModule & m) {
    auto regs = m.regs_rw_inst();
    CHECK(regs->v_check().has_value());
    CHECK(regs->v_check()->str == REGS_RW_CHECK);
    CHECK(regs->v_type() == VType::s);

    // every element is checked, the value of the module user is the value of
    // the register here (no v_convert)
    regs->write_vec_sint_cached({2, 4, 6});
    CHECK_THROWS(regs->write_vec_sint_cached({2, 4, 5}));
    CHECK_THROWS(regs->write_vec_sint_cached({2, 2, 102}));   // > 100
    CHECK_THROWS(regs->write_vec_sint_cached({-4, 2, 2}));    // < -2
    CHECK_THROWS(regs->write_idx_sint_cached(0, 3));
    regs->write_idx_sint_cached(0, 4);
    CHECK(regs->read_idx_sint_cached(0) == 4);

    // a value that fails is printed with the check and asserts
    regs->write_vec_sint_cached({2, 4, 6});
    CHECK(regs->ass_check_cached(Ass::none, nullptr) == Ass::none);
    auto s = regs->str_value_cached();
    ASSERT(s == REGS_RW_CHECK + " [ 2, 4, 6 ]");
}

static void test_v_convert_scalar(autogen::RecipeTestBenchModule & m) {
    // temp: v_type 'f', v_convert "{ v * 16 }", a Q4 style fixed point scale
    auto temp = m.temp_inst();
    CHECK(temp->has_v_convert());
    CHECK(temp->v_type() == VType::f);
    ASSERT(temp->v_convert()->str == "(v * 16)");
    ASSERT(temp->v_convert()->str_inv == "(v / 16)");

    // the default functions are the user domain (float_t), the *_raw ones the
    // register domain
    m.temp_write(1.5);
    CHECK(m.temp_read_raw() == 24);
    CHECK(m.temp_read_cached() == 1.5);
    m.temp_write_cached_raw(-16);
    CHECK(m.temp_read_cached() == -1.0);

    // the rounding is the python one, half away from zero (raw 1.5 -> 2)
    // a *_cached write only writes the cache, so it is read back with a *_cached read
    m.temp_write_cached(1.5/16);
    CHECK(m.temp_read_cached_raw() == 2);
    m.temp_write_cached(-1.5/16);
    CHECK(m.temp_read_cached_raw() == -2);

    // the user value is v_check'ed before it is converted
    CHECK_THROWS(m.temp_write(2000.0));
    // and the raw value has to fit the register
    CHECK_THROWS(m.temp_write(30000.0));    // raw 480000 does not fit in s16

    // a raw write gets the value of the register, its user value is checked too
    CHECK_THROWS(m.temp_write_raw(20000));  // 20000/16 = 1250, above the check

    // the raw bytes are what a firmware can write, they bypass the check, the
    // read has to assert
    const std::array<std::byte, 2> raw_1250 = {static_cast<std::byte>(0x20), static_cast<std::byte>(0x4E)};
    temp->write_bytes_cached(raw_1250);
    CHECK(m.temp_read_cached() == 1250.0);
    CHECK(temp->ass_check_cached(Ass::none, nullptr) == Ass::error);
    auto s = temp->str_value_cached();
    ASSERT(s == "((v >= -1000) && (v <= 1000)) 1250");

    m.temp_write(12.25);
    CHECK(m.temp_read_raw() == 196);
    ASSERT(temp->str_value_cached() == "((v >= -1000) && (v <= 1000)) 12.25");
    CHECK(temp->ass_check_cached(Ass::none, nullptr) == Ass::none);
}

// the value conversion works with float_t, the type of a recipe `v_type = "f"`,
// so a generated module does not have to change when the float width changes.
// Qualified, this file has `using namespace hdlskel::skmap`, where the
// unqualified name is also the float_t of <math.h> (see basic_types.hpp).
using skmap_float_t = hdlskel::skmap::float_t;
static_assert(std::is_same_v<decltype(std::declval<autogen::RecipeTestBenchModule &>().temp_read_cached()), skmap_float_t>);
static_assert(std::is_same_v<decltype(std::declval<autogen::RecipeTestBenchModule &>().temp_read()), skmap_float_t>);

static void test_recipe_values(autogen::RecipeTestBenchModule & m) {
    // A few plain values of the recipe, to be sure the regio layout did not move
    CHECK(m.RO_LEN() == 3);
    CHECK(m.RW_LEN() == 3);
    CHECK(m.RW_MULT() == 2);
    CHECK(m.ctrl_flag_0_read_cached() == true);
    CHECK(m.ctrl_flag_8_read_cached() == false);

    // a wt register is triggered with *_write_trigger (a regio write), the
    // *_write_cached functions only touch the cache of the module
    m.regs_wt_write_cached(0x15);
    CHECK(m.regs_wt_read_cached() == 0x15);
    m.bit_bool_wt_write_cached(true);
    CHECK(m.bit_bool_wt_read_cached() == true);

    m.regs_rw_write_cached({2, 4, 6});
    auto vec = m.regs_rw_read_cached();
    ASSERT(vec.size() == 3);
    CHECK(vec[0] == 2);
    CHECK(vec[1] == 4);
    CHECK(vec[2] == 6);
    // the vector without a v_convert keeps its int interface
    m.regs_rw_write_idx_cached(1, 8);
    CHECK(m.regs_rw_read_idx_cached(1) == 8);
    CHECK(m.regs_rw_read_idx_cached(0) == 2);
}

int main(int argc, char ** argv) {
    if (argc != 2) {
        std::cerr << "usage: " << argv[0] << " <regio cache file>\n";
        return 2;
    }
    auto module = make_module(argv[1]);
    ASSERT(module != nullptr);
    CHECK(module->name() == "recipe_test_bench_module");

    test_v_check_scalar(*module);
    test_v_check_vec(*module);
    test_v_convert_scalar(*module);
    test_recipe_values(*module);

    if (g_failed != 0) {
        std::cerr << g_failed << " of " << g_checks << " checks FAILED\n";
        return 1;
    }
    std::cout << g_checks << " checks passed\n";
    return 0;
}
