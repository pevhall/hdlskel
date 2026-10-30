"""Checksum of a recipe (the ``c=`` of the module head).

The checksum is generated into the py / cpp / vhdl module and written by the
firmware into its module head, so a cached regio image and the code that parses
it can be checked against each other. Everything that changes the layout of a
module, or that is baked into the generated code, has to be part of it, see
``Recipe._caculate_checksum``.
"""

import subprocess
from pathlib import Path

import pytest

from skmap.code_generator_parse_recipe import parse_recipe_file

REPO = Path(__file__).parent.parent.parent.parent
RECIPE = REPO/'fw/tb/skmap/tb_py_skmap_module_recipe/recipe_test_bench_module.toml'
TREE   = REPO/'fw/tb/skmap/tb_py_skmap_tree/test_skmap_tree_module.toml'
IMAGE_RECIPE = REPO/'test/data/test_recipe.skmap'
IMAGE_TREE   = REPO/'test/data/test_tree.skmap'
GENERATOR = REPO/'test/data/generate_test_skmap_files.sh'

# one ipkg value, one constant and one variable register, `{}` is the value
# type of the register, `$` additional options of that register
TMPL = '''
id = "TChk"
version = 1
name = "checksum_test_module"
sw_module = "ChecksumTestModule"
fw_module = "checksum_test_module"
desc = "checksum test"
ipkg = [
  {name = "SCALED", value = %(value)s },
]
k = [
  {name = "K_0", t = "u8", desc = "a constant"%(k_extra)s},
]
var = [
  {name = "regs", t = "%(t)s", acc = "%(acc)s", desc = "a register"%(v_extra)s},
]
'''

def write_recipe(tmp_path : Path, **kwargs) -> Path:
    opts = dict(value = 2, t = 'u8', acc = 'rw', v_extra = '', k_extra = '')
    opts.update(kwargs)
    p = tmp_path/'recipe.toml'
    p.write_text(TMPL % opts)
    return p

def checksum_of(tmp_path : Path, **kwargs) -> str:
    return parse_recipe_file(write_recipe(tmp_path, **kwargs)).checksum_str()


# ---------- what is (not) hashed ----------

def test_checksum_is_stable(tmp_path):
    assert checksum_of(tmp_path) == checksum_of(tmp_path)

def test_description_is_not_hashed(tmp_path):
    """A description is not generated into the module, it does not change the
    checksum (so a comment like a name of a person does not invalidate every
    cached image)."""
    a = checksum_of(tmp_path)
    p = write_recipe(tmp_path)
    text = p.read_text().replace('desc = "a register"', 'desc = "another text"')
    p.write_text(text)
    assert parse_recipe_file(p).checksum_str() == a

def test_vec_len_is_hashed(tmp_path):
    """The same register with a different number of elements: kind, width,
    access and name are all the same, only the vector length differs, which is
    exactly the layout of the module."""
    assert checksum_of(tmp_path, t = '[2]u8') != checksum_of(tmp_path, t = '[4]u8')

def test_type_width_is_hashed_by_value(tmp_path):
    """A width is hashed as its value, `u8` and `u{4 + 4}` are the same
    register."""
    assert checksum_of(tmp_path, t = 'u{4 + 4}') == checksum_of(tmp_path, t = 'u8')
    assert checksum_of(tmp_path, t = 'u9') != checksum_of(tmp_path, t = 'u8')

def test_value_kind_and_width_are_hashed(tmp_path):
    checksums = {checksum_of(tmp_path, t = t) for t in ('u8', 's8', 'b8', 'u16')}
    assert len(checksums) == 4

def test_access_is_hashed(tmp_path):
    checksums = {checksum_of(tmp_path, acc = acc) for acc in ('ro', 'rw', 'wt')}
    assert len(checksums) == 3

def test_recipe_names_are_hashed_by_value(tmp_path):
    """An ipkg constant used in a `v_check` / `v_convert_wr` is hashed as its
    value: the same conversion written with a name or with the number has the
    same checksum, a different value of that name has not."""
    check = ', v_type="f", v_check="{ (v >= -100) && (v <= 100) }"'
    by_name  = checksum_of(tmp_path, t = 's16', v_extra=check + ', v_convert_wr="{ v * SCALED }"')
    by_value = checksum_of(tmp_path, t = 's16', v_extra=check + ', v_convert_wr="{ v * 2 }"')
    other    = checksum_of(tmp_path, t = 's16', value = 8, v_extra=check + ', v_convert_wr="{ v * SCALED }"')
    assert by_name == by_value
    assert by_name != other


# ---------- assert and value options ----------

def test_ass_is_hashed(tmp_path):
    assert checksum_of(tmp_path, v_extra=', ass = "debug"') != checksum_of(tmp_path)
    assert checksum_of(tmp_path, v_extra=', ass = "debug"') != \
           checksum_of(tmp_path, v_extra=', ass = "warn"')

def test_k_option_is_hashed(tmp_path):
    """A constant of the recipe is hashed as its name, a `v_check` of it is a
    check of the value the module reports, so it is part of the checksum."""
    assert checksum_of(tmp_path, k_extra=', v_check="{ v < 100 }"') != checksum_of(tmp_path)
    assert checksum_of(tmp_path, k_extra=', v_check="{ v < 100 }"') != \
           checksum_of(tmp_path, k_extra=', v_check="{ v < 99 }"')

def test_v_check_is_hashed(tmp_path):
    a = checksum_of(tmp_path, v_extra=', v_check="{ v < 10 }"')
    b = checksum_of(tmp_path, v_extra=', v_check="{ v < 20 }"')
    assert a != b
    assert a != checksum_of(tmp_path)

def test_v_convert_is_hashed(tmp_path):
    v_check = ', v_type="f", v_check="{ (v >= -1000) && (v <= 1000) }"'
    assert checksum_of(tmp_path, t = 's16', v_extra=v_check + ', v_convert_wr="{ v * 16 }"') != \
           checksum_of(tmp_path, t = 's16', v_extra=v_check + ', v_convert_wr="{ v * 8 }"')

def test_v_convert_wr_and_rd_have_the_same_checksum(tmp_path):
    """`v_convert_wr` and `v_convert_rd` are inverses of each other, one of
    them is always derived from the other, so the same conversion written from
    either side is the same module and has the same checksum."""
    assert checksum_of(tmp_path, t = 's16', v_extra=', v_type="f", v_convert_wr="{ v * 16 }"') == \
           checksum_of(tmp_path, t = 's16', v_extra=', v_type="f", v_convert_rd="{ v / 16 }"')

def test_v_type_is_hashed(tmp_path):
    """`v_type` says what the value of the module user is (an unsigned int, a
    signed int or a float), it is generated into the code of the user."""
    check = ', v_check="{ (v >= 0) && (v <= 100) }"'
    # the register is a u8, its user value is unsigned unless v_type says else
    assert checksum_of(tmp_path, v_extra=check) != \
           checksum_of(tmp_path, v_extra=check + ', v_type="s"')


# ---------- flags ----------

def flags_of(name : str, bit : int, vec_len = None, ass = None) -> str:
    opts = ''
    if vec_len is not None:
        opts += f', vec_len = {vec_len}'
    if ass is not None:
        opts += f', ass = "{ass}"'
    return f'[ {{name = "{name}", bit = {bit}, desc = "flag"{opts}}} ]'

def checksum_of_flags(tmp_path : Path, flags : str) -> str:
    p = tmp_path/'recipe.toml'
    p.write_text(TMPL % dict(value = 2, t = 'b8', acc = 'rw',
                             v_extra=f', flags = {flags}', k_extra=''))
    return parse_recipe_file(p).checksum_str()

def test_flags_are_hashed(tmp_path):
    """A flag is only visible through its register, its name, bit, vector
    length and assert belong to the module."""
    assert checksum_of_flags(tmp_path, flags_of('f', 0)) != \
           checksum_of_flags(tmp_path, flags_of('f', 1))
    assert checksum_of_flags(tmp_path, flags_of('f', 0)) != \
           checksum_of_flags(tmp_path, flags_of('g', 0))
    assert checksum_of_flags(tmp_path, flags_of('f', 0)) != \
           checksum_of_flags(tmp_path, flags_of('f', 0, vec_len = 3))
    assert checksum_of_flags(tmp_path, flags_of('f', 0)) != \
           checksum_of_flags(tmp_path, flags_of('f', 0, ass = 'error'))


# ---------- the cached regio images ----------

def checksum_of_image(path : Path) -> str:
    """Checksum of the module head of a cached regio image.

    A regio cache file is the ascii header `skelregi`, then one entry per
    stored region (little endian uint32 address, uint32 size, data). Word 2 of
    the module head of the first region is sync, version / flags and the
    checksum as a little endian u16.
    """
    b = path.read_bytes()
    assert b[:8] == b'skelregi', f'{path} is not a regio cache file'
    addr, size = int.from_bytes(b[8:12], 'little'), int.from_bytes(b[12:16], 'little')
    assert addr == 0, f'{path} does not start at the root module (addr {addr})'
    head = b[16:16+size]
    assert head[8] == 0xD8, f'{path} does not start with a skmap head'
    return f'{int.from_bytes(head[10:12], "little"):04X}'

# the generator captures both images in one run, start the simulation only
# once even when several parametrizations of the test ask for it
_generate_attempted = False

def generate_images() -> bool:
    """Run test/data/generate_test_skmap_files.sh, True when it produced the
    images.

    The script starts the test benches in the simulator and captures the
    regio images, so it needs the simulator and the built app
    (`ninja -C sw/build`). It runs at most once per pytest session, both
    images are captured by the same run.
    """
    global _generate_attempted
    if _generate_attempted:
        return IMAGE_RECIPE.exists() and IMAGE_TREE.exists()
    _generate_attempted = True
    if not GENERATOR.exists():
        return False
    rc = subprocess.run(['bash', str(GENERATOR)], cwd=REPO).returncode
    return rc == 0 and IMAGE_RECIPE.exists() and IMAGE_TREE.exists()

@pytest.mark.parametrize('recipe_file, image_file', ((RECIPE, IMAGE_RECIPE), (TREE, IMAGE_TREE)))
def test_images_match_the_recipes(recipe_file, image_file):
    """The cached regio images of `test/data` have to be captured with the
    recipes in the repository, otherwise every test that reads them parses a
    module that does not exist anymore."""
    if not image_file.exists() and not generate_images():
        pytest.skip(f'{image_file} is not captured and {GENERATOR.name} failed '
                    '(needs the simulator and the built app: ninja -C sw/build)')
    assert checksum_of_image(image_file) == parse_recipe_file(recipe_file).checksum_str(), \
        f'{image_file} is stale, capture it again from the simulation of {recipe_file}'
