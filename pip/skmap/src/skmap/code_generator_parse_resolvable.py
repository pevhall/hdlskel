"""Parsing of recipe expressions ("resolvables").

A recipe value is either a plain integer or an expression string, eg
"{DATA_W*(DEPTH+1)}". This module parses those expressions into a small tree of
ResolvableT nodes, the code generators then render the tree back into python,
c++ and vhdl source.

Two recipe options are expressions of the register value `v`:

  * `v_check`       a boolean expression, a value that fails it is an assert on
                    a read and is rejected on a write.
  * `v_convert_wr`  an int expression converting the user value into the raw
                    register value (the write side). Its inverse, the read side
                    `v_convert_rd`, is derived here, see invert_resolvable().
  * `v_convert_rd`  the read side given directly (register value -> user
                    value), the write side is derived as its inverse. A
                    register never has both, they are inverses of each other.

All three options can use the constants of the recipe, the `ipkg` values and
the `k` registers, as parameters of the expression (only `v` and the recipe
names are allowed, an ipkg / k name resolves to its value).
"""

import copy
import re as _re
from fractions import Fraction
from math import gcd
from enum import Enum, auto
from typing import Union, Optional
from dataclasses import dataclass

from .basic_types import VType, value_kind_to_v_type

KObjT = object
NameToKT = dict[str, KObjT]

# Re-exported for the code generators and the runtime
__all__ = ['VType', 'value_kind_to_v_type']


class BultiInOperation(Enum):
    add  = auto()
    sub = auto() 
    mult = auto()
    div = auto()
    power = auto()
    mod  = auto()
    # Comparisions and logic, used by the `check` recipe option. The strings
    # below are the c++ spelling, code_generator_py maps them to python.
    eq   = auto()
    ne   = auto()
    lt   = auto()
    le   = auto()
    gt   = auto()
    ge   = auto()
    land = auto()
    lor  = auto()
    lnot = auto()   # unary, rhs is None

    @property
    def is_unary(self) -> bool:
        return self == BultiInOperation.lnot

    @property
    def is_comparision(self) -> bool:
        return self in (
            BultiInOperation.eq, BultiInOperation.ne,
            BultiInOperation.lt, BultiInOperation.le,
            BultiInOperation.gt, BultiInOperation.ge,
        )

    def __str__(self) -> str:
        return {
            BultiInOperation.add : "+",
            BultiInOperation.sub : "-",
            BultiInOperation.mult: "*",
            BultiInOperation.div: "/",
            BultiInOperation.power: "**",
            BultiInOperation.mod : "%",
            BultiInOperation.eq  : "==",
            BultiInOperation.ne  : "!=",
            BultiInOperation.lt  : "<",
            BultiInOperation.le  : "<=",
            BultiInOperation.gt  : ">",
            BultiInOperation.ge  : ">=",
            BultiInOperation.land: "&&",
            BultiInOperation.lor : "||",
            BultiInOperation.lnot: "!",
        }[self]



class BuiltInFunctionEnum(Enum):
    clog2 = auto()
    cdiv = auto()

@dataclass
class BuiltInFunction():

    enum : BuiltInFunctionEnum
    name : str
    parameters : int

function_clog2 = BuiltInFunction(BuiltInFunctionEnum.clog2 ,'clog2', 1)
function_cdiv  = BuiltInFunction(BuiltInFunctionEnum.cdiv ,'cdiv' , 2)

_BUILTIN_FUNCTIONS = {'clog2': function_clog2, 'cdiv': function_cdiv}

class ResolvableValueParam():
    """Leaf for a named parameter of a resolvable expression.

    Only used by the `v_check` / `v_convert_wr` / `v_convert_rd` recipe
    options, where the register value is available as the parameter `v`, eg
    v_check="{ (v % RW_MULT) == 0}".
    `v_type` is the type `v` has inside the expression (recipe `v_type`).
    """
    def __init__(self, name : str, v_type : VType = VType.s):
        self.name = name
        self.v_type = v_type

    def __repr__(self) -> str:
        return self.name

    def __eq__(self, other) -> bool:
        return (isinstance(other, ResolvableValueParam) and other.name == self.name
                and other.v_type == self.v_type)

    def __hash__(self) -> int:
        return hash(('ResolvableValueParam', self.name, self.v_type))

ResolvableT = Union['ResolvableFunctionOperation', 'ResolvableFunctionBuiltIn', 'ResolvableValueParam', KObjT, int]
class ResolvableFunctionOperation():
    def __init__(self, lhs : ResolvableT, op : BultiInOperation, rhs : ResolvableT):
        assert not op.is_unary or rhs is None, f'{op} is unary and takes no rhs'
        self.lhs = lhs
        self.op  = op
        self.rhs = rhs

    def __repr__(self) -> str:
        if self.op.is_unary:
            return f'({self.op}{self.lhs})' #type: ignore
        return f'({self.lhs} {self.op} {self.rhs})' #type: ignore

class ResolvableFunctionBuiltIn:
    def __init__(self, func : BuiltInFunction, params : list[ResolvableT]):
        self.func = func
        self.params = params
    def __repr__(self) -> str:
        return f"${self.func.name}({', '.join([str(p) for p in self.params])})" #type: ignore

def make_resolvable_function(lhs : ResolvableT, op : BultiInOperation, rhs : ResolvableT) -> ResolvableT:
    if isinstance(rhs, int):
        if isinstance(lhs, int):
            match op:
                case BultiInOperation.add : return lhs + rhs
                case BultiInOperation.sub : return lhs - rhs
                case BultiInOperation.mult: return lhs * rhs
                case BultiInOperation.div:  return lhs // rhs
                case BultiInOperation.power:  return lhs ** rhs
        elif isinstance(lhs, ResolvableFunctionOperation):
            if isinstance(lhs.rhs, int) and op == BultiInOperation.add and lhs.op == BultiInOperation.add:
                lhs = copy.copy(lhs)
                assert isinstance(lhs.rhs, int)
                lhs.rhs += rhs
                return lhs
    return ResolvableFunctionOperation(lhs, op, rhs)


_TOKEN_SPEC = [
    ('NAME',   r'[A-Za-z_][A-Za-z0-9_]*'),
    ('FUNC',   r'\$[A-Za-z_][A-Za-z0-9_]*'),
    ('NUMBER', r'\d+'),
    ('POWER',  r'\*\*'),          # must precede MUL, else "**" tokenizes as two "*"
    ('EQ',     r'=='),            # must precede the single character ops
    ('NE',     r'!='),
    ('LE',     r'<='),
    ('GE',     r'>='),
    ('LAND',   r'&&'),
    ('LOR',    r'\|\|'),
    ('PLUS',   r'\+'),
    ('MINUS',  r'-'),
    ('MUL',    r'\*'),
    ('DIV',    r'/'),
    ('MOD',    r'%'),
    ('LT',     r'<'),
    ('GT',     r'>'),
    ('LNOT',   r'!'),
    ('LPAREN', r'\('),
    ('RPAREN', r'\)'),
    ('COMMA',  r','),
    ('SKIP',   r'[ \t\n\r]+'),
]
_TOKEN_RE = _re.compile('|'.join(f'(?P<{n}>{p})' for n, p in _TOKEN_SPEC))

_BINARY_OP = {
    'PLUS': BultiInOperation.add, 'MINUS': BultiInOperation.sub,
    'MUL': BultiInOperation.mult, 'DIV': BultiInOperation.div,
    'MOD': BultiInOperation.mod,
    'EQ':  BultiInOperation.eq,  'NE':  BultiInOperation.ne,
    'LT':  BultiInOperation.lt,  'LE':  BultiInOperation.le,
    'GT':  BultiInOperation.gt,  'GE':  BultiInOperation.ge,
    'LAND': BultiInOperation.land, 'LOR': BultiInOperation.lor,
}


class _Token:
    __slots__ = ('kind', 'value', 'pos')
    def __init__(self, kind, value, pos):
        self.kind, self.value, self.pos = kind, value, pos
    def __repr__(self):
        return f'{self.kind}:{self.value!r}@{self.pos}'


def _tokenize(s):
    tokens, pos, n = [], 0, len(s)
    while pos < n:
        m = _TOKEN_RE.match(s, pos)
        if not m:
            raise SyntaxError(f'Unexpected character {s[pos]!r} at position {pos} in {s!r}')
        if m.lastgroup != 'SKIP':
            tokens.append(_Token(m.lastgroup, m.group(), m.start()))
        pos = m.end()
    return tokens


class _RecipeExprParser:
    def __init__(self, tokens, name_to_k, source, params : Optional[dict[str, VType]] = None):
        self._tokens, self._i, self._name_to_k, self._source = tokens, 0, name_to_k, source
        self._params = params if params is not None else {}

    def _peek(self):
        return self._tokens[self._i] if self._i < len(self._tokens) else None

    def _advance(self):
        tok = self._tokens[self._i]; self._i += 1; return tok

    def _expect(self, kind):
        tok = self._peek()
        if tok is None or tok.kind != kind:
            raise SyntaxError(f'Expected {kind} but found {tok!r} in {self._source!r}')
        return self._advance()

    def parse(self):
        node = self._parse_expr()
        if self._peek() is not None:
            raise SyntaxError(f'Unexpected trailing token {self._peek()!r} in {self._source!r}')
        return node

    # Precedence, lowest first: ||, &&, == !=, < <= > >=, + -, * / %, unary, **
    def _parse_expr(self):
        return self._parse_binary(('LOR',),  self._parse_logic_and)

    def _parse_logic_and(self):
        return self._parse_binary(('LAND',), self._parse_equality)

    def _parse_equality(self):
        return self._parse_binary(('EQ', 'NE'), self._parse_compare)

    def _parse_compare(self):
        return self._parse_binary(('LT', 'LE', 'GT', 'GE'), self._parse_add)

    def _parse_add(self):
        return self._parse_binary(('PLUS', 'MINUS'), self._parse_term)

    def _parse_term(self):
        return self._parse_binary(('MUL', 'DIV', 'MOD'), self._parse_factor)

    def _parse_binary(self, kinds : tuple[str, ...], parse_lower):
        node = parse_lower()
        while (tok := self._peek()) is not None and tok.kind in kinds:
            self._advance()
            node = make_resolvable_function(node, _BINARY_OP[tok.kind], parse_lower())
        return node

    def _parse_factor(self):
        tok = self._peek()
        if tok is not None and tok.kind == 'MINUS':
            self._advance()
            return make_resolvable_function(0, BultiInOperation.sub, self._parse_factor())
        if tok is not None and tok.kind == 'PLUS':
            self._advance()
            return self._parse_factor()
        if tok is not None and tok.kind == 'LNOT':
            self._advance()
            return ResolvableFunctionOperation(self._parse_factor(), BultiInOperation.lnot, None)
        return self._parse_power()

    def _parse_power(self):
        base = self._parse_atom()
        tok = self._peek()
        if tok is not None and tok.kind == 'POWER':
            self._advance()
            return make_resolvable_function(base, BultiInOperation.power, self._parse_factor())
        return base

    def _parse_atom(self):
        tok = self._peek()
        if tok is None:
            raise SyntaxError(f'Unexpected end of expression in {self._source!r}')

        if tok.kind == 'NUMBER':
            self._advance(); return int(tok.value)

        if tok.kind == 'NAME':
            self._advance()
            name = tok.value
            if name in self._params:
                return ResolvableValueParam(name, self._params[name])
            if name not in self._name_to_k:
                if self._params:
                    raise KeyError(f'Unknown recipe value {name} referenced in {self._source!r}'
                                   f', only {list(self._params)} and recipe k values are allowed')
                raise KeyError(f'Unknown recipe value {name} referenced in {self._source!r}')
            return self._name_to_k[name]

        if tok.kind == 'LPAREN':
            self._advance()
            node = self._parse_expr()
            self._expect('RPAREN')
            return node

        if tok.kind == 'FUNC':
            self._advance()
            func_name = tok.value[1:]
            if func_name not in _BUILTIN_FUNCTIONS:
                raise KeyError(f'Unknown built-in function {func_name!r} in {self._source!r}')
            func = _BUILTIN_FUNCTIONS[func_name]
            self._expect('LPAREN')
            params = [self._parse_expr()]
            while self._peek() is not None and self._peek().kind == 'COMMA': #type:ignore
                self._advance()
                params.append(self._parse_expr())
            self._expect('RPAREN')
            if len(params) != func.parameters:
                raise TypeError(f'${func_name} expects {func.parameters} argument(s), '
                                 f'got {len(params)} in {self._source!r}')
            return ResolvableFunctionBuiltIn(func, params)

        raise SyntaxError(f'Unexpected token {tok!r} in {self._source!r}')


def parse_resolvable(expr: Union[str, int], name_to_k: NameToKT, params : Optional[dict[str, VType]] = None) -> ResolvableT:
    """Parse a recipe expression ("{NAME}", "$func(...)", + - * / % ** == !=
    < <= > >= && || !, parens) into a ResolvableT tree. Constant
    sub-expressions fold to plain ints automatically via
    make_resolvable_function. `params` maps a parameter name to its VType,
    those names resolve to a ResolvableValueParam leaf instead of a recipe k
    value."""
    if isinstance(expr, int):
        return expr
    tokens = _tokenize(expr)
    return _RecipeExprParser(tokens, name_to_k, expr, params).parse()

# The register value is the only parameter a v_check / v_convert_wr /
# v_convert_rd expression can use (besides the ipkg / k constants of the recipe)
V_CHECK_PARAM = 'v'

class NotInvertibleError(Exception):
    """A v_convert_wr / v_convert_rd expression cannot be reversed into the
    conversion of the other side."""


def strip_recipe_expr(expr : Union[str, int]) -> Union[str, int]:
    """Remove the {} a recipe expression is written in, "{ v }" -> "v"."""
    if not isinstance(expr, str):
        return expr
    inner = expr.strip()
    if inner.startswith('{') and inner.endswith('}'):
        inner = inner[1:-1].strip()
    return inner


def parse_resolvable_v_check(expr : Union[str, int], name_to_k : NameToKT, v_type : VType = VType.s) -> tuple[ResolvableT, str]:
    """Parse a recipe `v_check` option, eg "{ (v % RW_MULT) == 0}".

    Returns the resolvable tree and the printable source text (names resolved to
    values, see resolvable_print_source). The tree must resolve to a boolean and
    may only reference the value parameter `v` and recipe k / ipkg values.
    """
    inner = strip_recipe_expr(expr)
    tree = parse_resolvable(inner, name_to_k, params={V_CHECK_PARAM : v_type})
    assert is_bool_expr(tree), \
        f'recipe v_check {expr!r} must resolve to a boolean, use == != < <= > >= && || !'
    return tree, resolvable_print_source(tree)


def parse_resolvable_v_convert_wr(expr : Union[str, int], name_to_k : NameToKT, v_type : VType = VType.s) -> tuple[ResolvableT, str, ResolvableT, str]:
    """Parse a recipe `v_convert_wr` option (value convert write side), eg "{ v * 8 }".

    Returns (write tree, write text, read tree, read text) in the canonical
    order (the write side converts user value -> register value, the read side
    register value -> user value). The read side is the inverse of the write
    side, derived with invert_resolvable().

    The inverse is verified against the forward expression for a few sample
    values, so an expression that does not round trip (an integer scale that
    loses values, for example) fails while parsing the recipe.
    """
    inner = strip_recipe_expr(expr)
    wr_tree = parse_resolvable(inner, name_to_k, params={V_CHECK_PARAM : v_type})
    assert not is_bool_expr(wr_tree), \
        f'recipe v_convert_wr {expr!r} must resolve to a value, not a boolean'
    rd_tree = invert_resolvable(wr_tree, expr)
    # The read side takes the raw register value, for a float v_type that is an
    # integer, the division below then has to be a float division
    rd_tree = retype_value_params(rd_tree, VType.f if v_type.is_float else v_type)
    assert rd_tree is not None
    _verify_inverse(wr_tree, rd_tree, expr)
    return wr_tree, resolvable_print_source(wr_tree), rd_tree, resolvable_print_source(rd_tree)

def parse_resolvable_v_convert_rd(expr : Union[str, int], name_to_k : NameToKT, v_type : VType = VType.s) -> tuple[ResolvableT, str, ResolvableT, str]:
    """Parse a recipe `v_convert_rd` option (value convert read side), eg "{ v / 16 }".

    The read side converts the raw register value into the user value, it is
    the inverse of `v_convert_wr`, which is derived here. Returns the same
    (write tree, write text, read tree, read text) as
    parse_resolvable_v_convert_wr(), so both options generate the same code.
    """
    inner = strip_recipe_expr(expr)
    # The read side takes the raw register value (always an int), for a float
    # v_type its divisions have to be float ones
    rd_v_type = VType.f if v_type.is_float else v_type
    rd_tree = parse_resolvable(inner, name_to_k, params={V_CHECK_PARAM : rd_v_type})
    assert not is_bool_expr(rd_tree), \
        f'recipe v_convert_rd {expr!r} must resolve to a value, not a boolean'
    wr_tree = invert_resolvable(rd_tree, expr)
    # The write side takes the user value, which follows the recipe v_type
    wr_tree = retype_value_params(wr_tree, v_type)
    assert wr_tree is not None
    _verify_inverse(wr_tree, rd_tree, expr)
    return wr_tree, resolvable_print_source(wr_tree), rd_tree, resolvable_print_source(rd_tree)


def is_bool_expr(node : ResolvableT) -> bool:
    """True if a tree is a boolean expression (or the value itself).

    Arithmetic on its own ({ v + 1 }) is rejected as a v_check so a typo fails
    while parsing the recipe instead of silently relying on an int to bool
    conversion.
    """
    if isinstance(node, ResolvableValueParam):
        return True # the value itself, none zero is true
    if isinstance(node, ResolvableFunctionOperation):
        if node.op == BultiInOperation.lnot:
            return True
        return node.op.is_comparision or node.op in (BultiInOperation.land, BultiInOperation.lor)
    return False # int, recipe k / ipkg leaf, $clog2 / $cdiv ...


def contains_float_value(node : ResolvableT) -> bool:
    """True if the expression evaluates as a float, it uses a float `v`.

    The recipe `/` is an integer division, a float expression needs a float one,
    see the python code generator (c++ divides as a float_t by itself).
    """
    if is_value_param(node):
        return node.v_type.is_float
    if isinstance(node, ResolvableFunctionOperation):
        if contains_float_value(node.lhs):
            return True
        return node.rhs is not None and contains_float_value(node.rhs)
    if isinstance(node, ResolvableFunctionBuiltIn):
        return any(contains_float_value(p) for p in node.params)
    return False


def is_value_param(node : ResolvableT) -> bool:
    return isinstance(node, ResolvableValueParam)


def contains_value_param(node : ResolvableT) -> bool:
    """True if the tree references the value parameter `v` somewhere."""
    if is_value_param(node):
        return True
    if isinstance(node, ResolvableFunctionOperation):
        if contains_value_param(node.lhs):
            return True
        return node.rhs is not None and contains_value_param(node.rhs)
    if isinstance(node, ResolvableFunctionBuiltIn):
        return any(contains_value_param(p) for p in node.params)
    return False


def retype_value_params(node : ResolvableT, v_type : VType) -> ResolvableT:
    """Copy of `node` with every `v` leaf retyped to `v_type`."""
    if is_value_param(node):
        return ResolvableValueParam(node.name, v_type)
    if isinstance(node, ResolvableFunctionOperation):
        return ResolvableFunctionOperation(retype_value_params(node.lhs, v_type), node.op,
                                           None if node.rhs is None else retype_value_params(node.rhs, v_type))
    if isinstance(node, ResolvableFunctionBuiltIn):
        return ResolvableFunctionBuiltIn(node.func, [retype_value_params(p, v_type) for p in node.params])
    return node


def ceil_div(l : int, r : int) -> int:
    """Ceiling division, matches $cdiv and the vhdl / c++ recipe functions."""
    return -((-l)//r)

def resolvable_to_int(node : ResolvableT) -> Union[int, float]:
    """Evaluate a tree that has no value parameter, recipe k / ipkg leaves are
    evaluated through their own (resolvable) value."""
    if isinstance(node, bool):
        return int(node)
    if isinstance(node, int):
        return node
    if isinstance(node, Fraction):
        return node
    if is_value_param(node):
        raise ValueError(f'register value is not known here: {resolvable_print_source(node)}')
    if isinstance(node, ResolvableFunctionBuiltIn):
        args = [resolvable_to_int(p) for p in node.params]
        match node.func.enum:
            case BuiltInFunctionEnum.clog2:
                v = args[0]
                return 0 if v <= 1 else (v-1).bit_length()
            case BuiltInFunctionEnum.cdiv:
                return ceil_div(args[0], args[1])
        raise ValueError(f'Cannot evaluate built-in {node.func.name}')
    if isinstance(node, ResolvableFunctionOperation):
        lhs = resolvable_to_int(node.lhs)
        rhs = None if node.rhs is None else resolvable_to_int(node.rhs)
        match node.op:
            case BultiInOperation.add : return lhs + rhs
            case BultiInOperation.sub : return lhs - rhs
            case BultiInOperation.mult: return lhs * rhs
            case BultiInOperation.div : return ceil_div(lhs, rhs) if isinstance(lhs, int) else lhs/rhs
            case BultiInOperation.power: return lhs ** rhs
            case BultiInOperation.mod : return lhs % rhs
            case BultiInOperation.eq  : return int(lhs == rhs)
            case BultiInOperation.ne  : return int(lhs != rhs)
            case BultiInOperation.lt  : return int(lhs <  rhs)
            case BultiInOperation.le  : return int(lhs <= rhs)
            case BultiInOperation.gt  : return int(lhs >  rhs)
            case BultiInOperation.ge  : return int(lhs >= rhs)
            case BultiInOperation.land: return int(bool(lhs) and bool(rhs))
            case BultiInOperation.lor : return int(bool(lhs) or  bool(rhs))
            case BultiInOperation.lnot: return int(not bool(lhs))
        raise ValueError(f'Cannot evaluate operation {node.op}')
    if hasattr(node, 'value'): # RecipeK / RecipeIpkg leaf
        return resolvable_to_int(node.value)
    raise TypeError(f'Cannot evaluate {node!r}')


def resolvable_print_source(node : ResolvableT) -> str:
    """Print a tree for humans: every parameter is resolved to its value.

    Used for the `v_check` / `v_convert_wr` / `v_convert_rd` text that the
    register prints and puts in error messages, eg "{ (v % RW_MULT) == 0}"
    prints as '(v % 2) == 0'. The `ipkg` values resolve to their number here.
    A `k` register has its value only at runtime (it is reported by the
    firmware), it keeps its name in the text and the runtime resolves it when
    printing, see Reg.resolve_expr_names in the python and c++ libraries.
    The value parameter `v` is never simplified, it is the only parameter
    that stays in every printed expression.
    The operators print with their c / c++ spelling, which is what both
    generated languages show, so the value strings match between python and c++.
    """
    if isinstance(node, bool):
        return str(int(node))
    if isinstance(node, int):
        return str(node)
    if isinstance(node, Fraction):
        return str(node)
    if is_value_param(node):
        return node.name
    if isinstance(node, ResolvableFunctionOperation):
        if node.op.is_unary:
            return f'({node.op}{resolvable_print_source(node.lhs)})'
        return f'({resolvable_print_source(node.lhs)} {node.op} {resolvable_print_source(node.rhs)})'
    if isinstance(node, ResolvableFunctionBuiltIn):
        args = ', '.join(resolvable_print_source(p) for p in node.params)
        return f'${node.func.name}({args})'
    if isinstance(node, str):
        return node
    if hasattr(node, 'name') and hasattr(node, 'value'):
        # recipe k / ipkg leaf, print the value it resolves to
        try:
            return str(resolvable_to_int(node))
        except Exception:
            return node.name
    if hasattr(node, 'name'):
        return node.name
    raise TypeError(f'Cannot print {node!r}')


# ---------------------------------------------------------------------------
# v_convert_wr / v_convert_rd inversion
#
# Only an expression that is affine in `v` (coef * v + offset, with coef and
# offset not using `v`) can be reversed for any v, so that is what the value
# conversions support. The inverse of `coef * v + offset` is
# `v -> (v - offset) / coef`, computed with exact rational coefficients so a
# `v_convert_rd` like "{ v / 16 }" reverses into "v * 16".
# ---------------------------------------------------------------------------

def _is_int(node : ResolvableT, value : int) -> bool:
    return isinstance(node, int) and node == value

def _is_num(node) -> bool:
    """True for the numeric affine coefficients (an int or an exact fraction)."""
    return isinstance(node, (int, Fraction)) and not isinstance(node, bool)

def _norm_num(num):
    """A Fraction with denominator 1 is an int (keeps the printed text plain)."""
    if isinstance(num, Fraction) and num.denominator == 1:
        return int(num)
    return num

def _try_int(node : ResolvableT) -> ResolvableT:
    """Numeric value of a constant tree (ipkg / k names resolved), the node
    itself when it does not resolve to a number."""
    if _is_num(node):
        return node
    try:
        value = resolvable_to_int(node)
    except Exception:
        return node
    return value if _is_num(value) else node

def _no_fraction_inside(node : ResolvableT) -> bool:
    """A Fraction is an affine coefficient only, it never lives in a tree (the
    generated languages have no fraction literal)."""
    if isinstance(node, Fraction):
        return False
    if isinstance(node, ResolvableFunctionOperation):
        if not _no_fraction_inside(node.lhs):
            return False
        return node.rhs is None or _no_fraction_inside(node.rhs)
    if isinstance(node, ResolvableFunctionBuiltIn):
        return all(_no_fraction_inside(p) for p in node.params)
    return True

def _expr_add(lhs : ResolvableT, rhs : ResolvableT) -> ResolvableT:
    if _is_int(lhs, 0): return rhs
    if _is_int(rhs, 0): return lhs
    if _is_num(lhs) and _is_num(rhs): return _norm_num(lhs + rhs)
    if _is_num(rhs) and rhs < 0:  # v + -8 is spelled v - 8
        return _expr_sub(lhs, _norm_num(-rhs))
    return ResolvableFunctionOperation(lhs, BultiInOperation.add, rhs)

def _expr_sub(lhs : ResolvableT, rhs : ResolvableT) -> ResolvableT:
    if _is_int(rhs, 0): return lhs
    if _is_num(lhs) and _is_num(rhs): return _norm_num(lhs - rhs)
    if _is_num(rhs) and rhs < 0:  # v - -8 is spelled v + 8
        return _expr_add(lhs, _norm_num(-rhs))
    return ResolvableFunctionOperation(lhs, BultiInOperation.sub, rhs)

def _expr_mult(lhs : ResolvableT, rhs : ResolvableT) -> ResolvableT:
    if _is_int(lhs, 0) or _is_int(rhs, 0): return 0
    if _is_int(lhs, 1): return rhs
    if _is_int(rhs, 1): return lhs
    if _is_num(lhs) and _is_num(rhs): return _norm_num(lhs * rhs)
    return ResolvableFunctionOperation(lhs, BultiInOperation.mult, rhs)

def _expr_div(lhs : ResolvableT, rhs : ResolvableT) -> ResolvableT:
    if _is_int(lhs, 0): return 0
    if _is_int(rhs, 1): return lhs
    if _is_num(lhs) and _is_num(rhs):
        # an exact division stays an int, the rest keeps its value as an exact
        # fraction (1 / 16 is not 0 here, the divisor of a conversion is
        # evaluated exactly and not as the truncated recipe `/`)
        return _norm_num(Fraction(lhs) / Fraction(rhs))
    return ResolvableFunctionOperation(lhs, BultiInOperation.div, rhs)


def affine_in_v(node : ResolvableT) -> tuple[ResolvableT, ResolvableT]:
    """Coefficients of `node` as `coef * v + offset`, both without `v`.

    Raises NotInvertibleError for anything else (v * v, v % 2, a comparison ...).
    """
    if is_value_param(node):
        return 1, 0
    if not contains_value_param(node):
        return 0, node
    if isinstance(node, ResolvableFunctionOperation):
        c_l, o_l = affine_in_v(node.lhs)
        # Everything but + and - keeps the value in one place only
        if node.op == BultiInOperation.add:
            c_r, o_r = affine_in_v(node.rhs)
            return _expr_add(c_l, c_r), _expr_add(o_l, o_r)
        if node.op == BultiInOperation.sub:
            c_r, o_r = affine_in_v(node.rhs)
            return _expr_sub(c_l, c_r), _expr_sub(o_l, o_r)
        if node.op == BultiInOperation.mult:
            # (cl*v + ol) * rhs, rhs must not use v
            c_r, o_r = affine_in_v(node.rhs)
            if not _is_int(c_r, 0):
                raise NotInvertibleError(f'both sides of "{resolvable_print_source(node)}" use the value')
            return _expr_mult(c_l, node.rhs), _expr_mult(o_l, node.rhs)
        if node.op == BultiInOperation.div:
            # (cl*v + ol) / rhs, rhs must not use v. The divisor is a recipe
            # constant, resolved to a number so the coefficients stay exact
            # fractions ({ v / 16 } is v * (1/16), not v * 0)
            c_r, o_r = affine_in_v(node.rhs)
            if not _is_int(c_r, 0):
                raise NotInvertibleError(f'cannot divide by the value in "{resolvable_print_source(node)}"')
            rhs_num = _try_int(node.rhs)
            return _expr_div(c_l, rhs_num), _expr_div(o_l, rhs_num)
    raise NotInvertibleError(f'cannot reverse "{resolvable_print_source(node)}" '
                             f'into a value conversion, only + - * / by a constant is supported')


def _inverse_affine(coef : ResolvableT, offset : ResolvableT, expr : Union[str, int]) -> ResolvableT:
    """Tree of `v -> (v - offset) / coef` with exact rational coefficients.

    With a numeric coef / offset the result is `(v * b*d - a*d) / (b*n)` for
    `coef = n/d` and `offset = a/b`, reduced by the greatest common divisor, so
    the derived side prints and generates without fractions (the read side of
    `{ v * 16 }` is `(v / 16)`, the write side of `{ v / 16 }` is `(v * 16)`).
    A coef / offset that is a recipe expression which does not resolve to a
    number keeps the unscaled form, it evaluates at run time.
    """
    v = ResolvableValueParam(V_CHECK_PARAM)
    coef = _try_int(coef)
    offset = _try_int(offset)
    if _is_num(coef) and _is_num(offset):
        coef_f = Fraction(coef)
        off_f  = Fraction(offset)
        # (v - a/b) / (n/d) = (v * b*d - a*d) / (b*n)
        t_lhs  = off_f.denominator * coef_f.denominator
        t_off  = off_f.numerator   * coef_f.denominator
        t_rhs  = off_f.denominator * coef_f.numerator
        g = gcd(gcd(abs(t_lhs), abs(t_off)), abs(t_rhs))
        t_lhs, t_off, t_rhs = t_lhs // g, t_off // g, t_rhs // g
        if t_rhs < 0:
            t_lhs, t_off, t_rhs = -t_lhs, -t_off, -t_rhs
        tree = _expr_mult(v, t_lhs)
        tree = _expr_sub(tree, t_off)
        return _expr_div(tree, t_rhs)
    if not _no_fraction_inside(coef) or not _no_fraction_inside(offset):
        raise NotInvertibleError(f'recipe v_convert_wr / v_convert_rd {expr!r} mixes a fraction with '
                                 f'a recipe value that does not resolve to a number')
    return _expr_div(_expr_sub(v, offset), coef)


def invert_resolvable(node : ResolvableT, expr : Union[str, int] = '') -> ResolvableT:
    """Inverse of an affine `v` expression: v -> (v - offset) / coef."""
    try:
        coef, offset = affine_in_v(node)
    except NotInvertibleError as e:
        raise NotInvertibleError(f'recipe v_convert_wr / v_convert_rd {expr!r}: {e}') from None
    if _is_int(coef, 0) or (isinstance(coef, Fraction) and coef == 0):
        raise NotInvertibleError(f'recipe v_convert_wr / v_convert_rd {expr!r} does not use the value, it cannot be reversed')
    return _inverse_affine(coef, offset, expr)


def _round_to_int(value : Union[int, float]) -> int:
    """Round half away from zero, the same way the runtime turns a float
    v_convert_wr result into the raw register value."""
    if isinstance(value, int):
        return value
    return int((value + 0.5)//1) if value >= 0 else -int((-value + 0.5)//1)

def _verify_inverse(node : ResolvableT, inv : ResolvableT, expr : Union[str, int]):
    """Check convert(inverse(raw)) == raw for a few raw values.

    Only possible when every name resolves to a constant, which is always the
    case for a parsed recipe. Catches conversions that are not reversible, eg an
    integer scale which drops the raw values in between.
    """
    for raw in (0, 1, 3, -3, 100, -100):
        # The inverse takes a raw value of the register, feeding it back into
        # the convert expression must give the same raw value. A `k` register
        # is only known at run time, a conversion using one can not be
        # verified here (resolvable_to_int raises) and is taken as given
        try:
            user = _eval_with(inv, raw)
            back = _round_to_int(_eval_with(node, user))
        except (ValueError, TypeError, ZeroDivisionError):
            return
        if back != raw:
            raise NotInvertibleError(
                f'recipe v_convert_wr / v_convert_rd {expr!r} cannot be reversed, register value {raw} '
                f'converts back to {back}, an integer scale drops the values in between, '
                'use v_type="f" or a v_check for the multiples you allow')

def _eval_with(node : ResolvableT, value : Union[int, float]) -> Union[int, float]:
    """Evaluate a tree with the value parameter bound to `value`."""
    if is_value_param(node):
        # A float register evaluates its expressions as a float
        return float(value) if node.v_type.is_float else value
    if isinstance(node, ResolvableFunctionOperation):
        lhs = _eval_with(node.lhs, value)
        rhs = None if node.rhs is None else _eval_with(node.rhs, value)
        match node.op:
            case BultiInOperation.add : return lhs + rhs
            case BultiInOperation.sub : return lhs - rhs
            case BultiInOperation.mult: return lhs * rhs
            # A recipe `/` is an int division when both sides are ints, a float
            # conversion (v_type 'f') divides as a float
            case BultiInOperation.div : return ceil_div(lhs, rhs) if isinstance(lhs, int) and isinstance(rhs, int) else lhs/rhs
            case BultiInOperation.power: return lhs ** rhs
            case BultiInOperation.mod : return lhs % rhs
            case _: raise ValueError(f'Cannot evaluate operation {node.op} with a value')
    if isinstance(node, ResolvableFunctionBuiltIn):
        return resolvable_to_int(ResolvableFunctionBuiltIn(node.func, [_const_tree(p, value) for p in node.params]))
    return resolvable_to_int(node)

def _const_tree(node : ResolvableT, value : Union[int, float]) -> ResolvableT:
    return _eval_with(node, value) if contains_value_param(node) else node



if __name__ == '__main__':
    # Run me with: python3 -m skmap.code_generator_parse_resolvable (from pip/skmap/src)
    def to_python_source(node: 'ResolvableT') -> str:
        """Render a ResolvableT tree back out as a Python source-code expression string."""
        if isinstance(node, bool):
            return str(int(node))
        if isinstance(node, int):
            return str(node)
        if isinstance(node, ResolvableFunctionOperation):
            if node.op.is_unary:
                return f'({node.op}{to_python_source(node.lhs)})'
            return f'({to_python_source(node.lhs)} {node.op} {to_python_source(node.rhs)})'
        if isinstance(node, ResolvableFunctionBuiltIn):
            args = ', '.join(to_python_source(p) for p in node.params)
            return f'{node.func.name}({args})'
        if isinstance(node, str):   # plain-string leaf (e.g. name_to_k[name] = name)
            return node
        if hasattr(node, 'name'):  # RecipeK / RecipeIpkg leaf
            return node.name #type:ignore
        raise TypeError(f'Cannot render {node!r} to python source')
    name_to_k = {}
    def add_k(name):
        name_to_k[name] = name
    add_k('DEPTH')
    add_k('RW_W')
    add_k('RO_W')
    add_k('WORD_W')
    add_k('DATA_W')
    # "$clog2({DEPTH})"                       -> ResolvableFunctionBuiltIn(function_clog2, [DEPTH])
    f = parse_resolvable("$clog2(DEPTH)", name_to_k)
    print(to_python_source(f))
    # "{RW_W}/({WORD_W}+4) + {RO_W}/(4*2)"    -> ((RW_W / (WORD_W + 4)) + (RO_W / 8))   # 4*2 folded to 8
    f = parse_resolvable("RW_W/(WORD_W+4) + RO_W/(4*2)", name_to_k)
    print(to_python_source(f))
    
    # "$cdiv({DATA_W},2**3)"                  -> ResolvableFunctionBuiltIn(function_cdiv, [DATA_W, 8])  # 2**3 folded to 8
    f = parse_resolvable("$cdiv(DATA_W,2**3)", name_to_k)
    print(to_python_source(f))
    # A `v_check` expression, the register value is the parameter v
    f, s = parse_resolvable_v_check("{ (v % RW_MULT) == 0}", {'RW_MULT' : 'RW_MULT'})
    print(to_python_source(f), '|', s)
    f, _ = parse_resolvable_v_check("!v && v != 3", {})
    print(to_python_source(f))
    try:
        parse_resolvable_v_check("{ v + 1 }", {})
    except AssertionError as e:
        print(f'expected failure: {e}')
    # A `v_convert_wr` expression and its derived read side, the printed text
    # has the
    # names resolved to values. A float register (v_type 'f') scales exactly.
    # A `v_convert_wr` expression and its derived read side, the printed text
    # has the names resolved to values. A float register (v_type 'f') scales
    # exactly.
    fwd, fwd_s, inv, inv_s = parse_resolvable_v_convert_wr("{ v * SCALE }", {'SCALE' : 8}, v_type=VType.f)
    print(f'convert {fwd_s} -> {to_python_source(fwd)}   inverse {inv_s} -> {to_python_source(inv)}')
    fwd, fwd_s, inv, inv_s = parse_resolvable_v_convert_wr("{ (v + OFFSET) * 4 }", {'OFFSET' : 2}, v_type=VType.f)
    print(f'convert {fwd_s}   inverse {inv_s}')
    # An integer register only reverses when the scale keeps every raw value
    fwd, fwd_s, inv, inv_s = parse_resolvable_v_convert_wr("{ v + OFFSET }", {'OFFSET' : 2})
    print(f'convert {fwd_s}   inverse {inv_s}')
    # The same conversion written from the read side, it derives the same pair
    fwd, fwd_s, inv, inv_s = parse_resolvable_v_convert_rd("{ v / SCALE }", {'SCALE' : 8}, v_type=VType.f)
    print(f'rd {inv_s} -> wr {fwd_s} -> {to_python_source(fwd)}')
    try:
        parse_resolvable_v_convert_wr("{ v * 2 }", {}, v_type=VType.s)
    except NotInvertibleError as e:
        print(f'expected failure: {e}')
    try:
        parse_resolvable_v_convert_wr("{ v * v }", {})
    except NotInvertibleError as e:
        print(f'expected failure: {e}')

