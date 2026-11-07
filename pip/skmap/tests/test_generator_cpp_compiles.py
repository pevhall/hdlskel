"""The generated c++ module has to compile against the c++ library.

The functions of a generated module only name the functions of the c++ runtime
(``Reg``, ``RegVec``, ``ExternalMem``), so a recipe option that the generator
serves with the function of another kind is invisible in the generated text: a
scalar function of a vector register (``read_converted`` of a vector, which
returns one value where the generated function returns a ``std::vector``), a
conversion function of a char register (whose generated functions carry a
``std::string``) both look right and do not compile.

So this test generates one module with every combination of value kind, access
and value option (``v_type`` / ``v_check`` / ``v_convert_wr`` /
``v_convert_rd``) and compiles it with ``-fsyntax-only`` against the headers of
the c++ library. It needs a c++ compiler, without one it is skipped (the
meson / cmake builds compile the generated modules of the test recipes the
same way, they only do not cover every combination).

Run with: python3 -m pytest pip/skmap/tests -q
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'pip' / 'skmap' / 'src'))

import skmap  # noqa: E402

SKMAP_INCLUDE = ROOT / 'sw' / 'lib' / 'cpp' / 'skmap' / 'include'
REGIO_INCLUDE = ROOT / 'sw' / 'lib' / 'cpp' / 'regio' / 'include'

RECIPE = """
name = "compile_test_module"
sw_module = "CompileTestModule"
fw_module = "compile_test_module"
id = "TComp"
version = 1

ipkg = [
  {name = "LEN", value = 3 },
  {name = "W",   value = 16 },
]

k = [
  {name = "K_LEN",  t = "u8", desc = "k length"},
  {name = "K_CHK",  t = "u8", desc = "k with a v_check", v_check = "{ (v % 2) == 0 }"},
  {name = "K_FLAG", t = "b",  desc = "k flags", flags = [
     {name = "KF0", ass = "debug", desc = "flag k 0"},
  ]},
]

var = [
  # kinds and accesses, no value option
  {name = "bool_rc",   t = "b1",    acc = "rc", desc = "one bool"},
  {name = "bool_wt",   t = "b1",    acc = "wt", desc = "one bool, wt"},
  {name = "bits_ro",   t = "x32",   acc = "ro", desc = "bits"},
  {name = "u8_rw",     t = "u8",    acc = "rw", desc = "uint"},
  {name = "s16_rc",    t = "s16",   acc = "rc", desc = "sint"},
  {name = "char_rw",   t = "c8",    acc = "rw", desc = "char"},
  {name = "chars_rw",  t = "[4]c8", acc = "rw", desc = "char vector, whole only"},
  {name = "u_vec_rw",  t = "[3]u8", acc = "rw", desc = "uint vector"},
  {name = "s_vec_ro",  t = "[{LEN}]s{W}", acc = "ro", desc = "sint vector"},
  {name = "flags_rw",  t = "b",     acc = "rw", desc = "flags", flags = [
     {name = "F0", bit = 0, desc = "flag 0"},
     {name = "F1", bit = 1, desc = "flag 1", vec_len = 3},
  ]},
  {name = "flags_rc",  t = "b",     acc = "rc", desc = "rc flags", flags = [
     {name = "G0", bit = 0, desc = "flag 0"},
  ]},

  # only a v_check
  {name = "chk_rw", t = "u16", acc = "rw", desc = "v_check only", v_check = "{ (v % 2) == 0 }"},
  {name = "chk_vec", t = "[2]s16", acc = "ro", desc = "vector with a v_check", v_check = "{ (v >= -100) && (v <= 100) }"},

  # a value conversion of every kind of user value, of a scalar and a vector, of
  # every access, given from the write side and from the read side (a toml
  # inline table is one line). In the integer domain only a scale of 1 can be
  # reversed (raw / 2 of an odd raw value is no value anymore), so the integer
  # ones are additive, a scaled one needs v_type="f".
  {name = "conv_f", t = "s32", acc = "rw", desc = "float user value", v_type = "f", v_convert_wr = "{ v * 4 }", v_check = "{ (v >= -10) && (v <= 10) }"},
  {name = "conv_i", t = "u16", acc = "rw", desc = "int user value", v_convert_wr = "{ v + 8 }", v_check = "{ v <= 100 }"},
  {name = "conv_rd", t = "s16", acc = "ro", desc = "conversion of the read side, integer domain", v_convert_rd = "{ v + 4 }", v_check = "{ (v >= -100) && (v <= 100) }"},
  {name = "conv_rc", t = "u8", acc = "rc", desc = "rc with a conversion of an integer user value", v_convert_wr = "{ v + 2 }", v_check = "{ v <= 50 }"},
  {name = "conv_wt", t = "s16", acc = "wt", desc = "wt with a conversion", v_type = "f", v_convert_wr = "{ v * 2 }", v_check = "{ (v >= -9) && (v <= 9) }"},
  {name = "conv_vec_f", t = "[{LEN}]s12", acc = "rw", desc = "vector with a float user value", v_type = "f", v_convert_wr = "{10-v*10}", v_check = "{ (v >= -2) && (v <= 100) }"},
  {name = "conv_vec_i", t = "[2]u8", acc = "rw", desc = "vector with an integer user value", v_convert_wr = "{ v + 2 }", v_check = "{ v <= 50 }"},
  {name = "conv_vec_ro", t = "[2]s16", acc = "ro", desc = "ro vector with a float user value", v_type = "f", v_convert_rd = "{ v / 2 }", v_check = "{ (v >= -50) && (v <= 50) }"},
  {name = "conv_vec_wt", t = "[{LEN}]s16", acc = "wt", desc = "wt vector with a conversion", v_type = "f", v_convert_wr = "{ v * 2 }", v_check = "{ (v >= -9) && (v <= 9) }"},

  # a vector of the length of a k register
  {name = "conv_k_len", t = "[{K_LEN}]s8", acc = "rw", desc = "length of a k register", v_convert_wr = "{ v + 1 }", v_check = "{ (v >= -10) && (v <= 10) }"},
]
"""


def compile_cpp(hpp : Path, cpp : Path) -> str:
    """Compile the generated module against the headers of the c++ runtime,
    syntax only (no object file, no link). Returns the compiler output."""
    compiler = shutil.which('g++') or shutil.which('clang++')
    cmd = [compiler, '-std=c++20', '-Wall', '-Wextra', '-fsyntax-only',
           f'-I{SKMAP_INCLUDE}', f'-I{REGIO_INCLUDE}', f'-I{hpp.parent}', str(cpp)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    out = res.stdout + res.stderr
    assert res.returncode == 0, f'{" ".join(cmd)} failed with {res.returncode}:\n{out}'
    return out


def test_generated_cpp_compiles_against_the_runtime(tmp_path):
    """Every combination of kind, access and value option generates functions
    that exist on the runtime, with a type the generated function can return."""
    if shutil.which('g++') is None and shutil.which('clang++') is None:
        pytest.skip('no c++ compiler')
    if not SKMAP_INCLUDE.is_dir() or not REGIO_INCLUDE.is_dir():
        pytest.skip(f'c++ library headers not found ({SKMAP_INCLUDE})')
    recipe = tmp_path / 'compile_test_module.toml'
    recipe.write_text(RECIPE)
    hpp = tmp_path / 'compile_test_module.hpp'
    cpp = tmp_path / 'compile_test_module.cpp'
    skmap.generate_cpp_module(recipe, hpp, cpp)
    compile_cpp(hpp, cpp)


def test_a_char_vector_has_no_per_index_functions(tmp_path):
    """A char register is generated whole (a string), lane access to a vector
    of chars is not made by the sw generators (the same in python and c++)."""
    recipe = tmp_path / 'compile_test_module.toml'
    recipe.write_text(RECIPE)
    hpp = tmp_path / 'compile_test_module.hpp'
    py = tmp_path / 'compile_test_module.py'
    skmap.generate_cpp_module(recipe, hpp, tmp_path / 'compile_test_module.cpp')
    skmap.generate_py_module(recipe, py)
    assert 'std::string chars_rw_read_cached()' in hpp.read_text()
    assert 'chars_rw_read_idx' not in py.read_text()
    assert 'char_rw_read_cached' in py.read_text()


def test_a_generated_vector_with_a_conversion_does_not_use_scalar_functions(tmp_path):
    """The regression the type check above is the guard for: the converted
    functions of a vector register are the vector ones of the runtime."""
    recipe = tmp_path / 'compile_test_module.toml'
    recipe.write_text(RECIPE)
    hpp = tmp_path / 'compile_test_module.hpp'
    skmap.generate_cpp_module(recipe, hpp, tmp_path / 'compile_test_module.cpp')
    src = hpp.read_text()
    assert 'm_var_conv_vec_f->read_vec_converted_cached()' in src
    assert 'm_var_conv_vec_f->write_vec_converted(' in src
    assert 'm_var_conv_vec_f->read_converted' not in src
    assert 'm_var_conv_vec_f->write_converted(' not in src
    # the scalar one of the same recipe does use them
    assert 'm_var_conv_f->read_converted_cached()' in src
    assert 'm_var_conv_f->read_vec_converted' not in src
