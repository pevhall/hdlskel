import copy
import re as _re
from enum import Enum, auto
from typing import Union, Optional
from dataclasses import dataclass

KObjT = object
NameToKT = dict[str, KObjT]


class BultiInOperation(Enum):
    add  = auto()
    sub = auto() 
    mult = auto()
    div = auto()
    power = auto()

    def __str__(self) -> str:
        return {
            BultiInOperation.add : "+",
            BultiInOperation.sub : "-",
            BultiInOperation.mult: "*",
            BultiInOperation.div: "/",
            BultiInOperation.power: "**",
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

ResolvableT = Union['ResolvableFunctionOperation', 'ResolvableFunctionBuiltIn', KObjT, int]
class ResolvableFunctionOperation():
    def __init__(self, lhs : ResolvableT, op : BultiInOperation, rhs : ResolvableT):
        self.lhs = lhs
        self.op  = op
        self.rhs = rhs

    def __repr__(self) -> str:
        return f'({self.lhs} {self.op} {self.rhs})' #type: ignore

class ResolvableFunctionBuiltIn:
    def __init__(self, func : BuiltInFunction, params : list[ResolvableT]):
        self.func = func
        self.params = params
    def __repr__(self) -> str:
        return f'${self.func.name}({', '.join([str(p) for p in self.params])})' #type: ignore

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
    ('PLUS',   r'\+'),
    ('MINUS',  r'-'),
    ('MUL',    r'\*'),
    ('DIV',    r'/'),
    ('LPAREN', r'\('),
    ('RPAREN', r'\)'),
    ('COMMA',  r','),
    ('SKIP',   r'[ \t\n\r]+'),
]
_TOKEN_RE = _re.compile('|'.join(f'(?P<{n}>{p})' for n, p in _TOKEN_SPEC))

_BINARY_OP = {
    'PLUS': BultiInOperation.add, 'MINUS': BultiInOperation.sub,
    'MUL': BultiInOperation.mult, 'DIV': BultiInOperation.div,
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
    def __init__(self, tokens, name_to_k, source):
        self._tokens, self._i, self._name_to_k, self._source = tokens, 0, name_to_k, source

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

    def _parse_expr(self):
        node = self._parse_term()
        while (tok := self._peek()) is not None and tok.kind in ('PLUS', 'MINUS'):
            self._advance()
            node = make_resolvable_function(node, _BINARY_OP[tok.kind], self._parse_term())
        return node

    def _parse_term(self):
        node = self._parse_factor()
        while (tok := self._peek()) is not None and tok.kind in ('MUL', 'DIV'):
            self._advance()
            node = make_resolvable_function(node, _BINARY_OP[tok.kind], self._parse_factor())
        return node

    def _parse_factor(self):
        tok = self._peek()
        if tok is not None and tok.kind == 'MINUS':
            self._advance()
            return make_resolvable_function(0, BultiInOperation.sub, self._parse_factor())
        if tok is not None and tok.kind == 'PLUS':
            self._advance()
            return self._parse_factor()
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
            if name not in self._name_to_k:
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


def parse_resolvable(expr: Union[str, int], name_to_k: NameToKT) -> ResolvableT:
    """Parse a recipe expression ("{NAME}", "$func(...)", + - * / **, parens)
    into a ResolvableT tree. Constant sub-expressions fold to plain ints
    automatically via make_resolvable_function."""
    if isinstance(expr, int):
        return expr
    tokens = _tokenize(expr)
    return _RecipeExprParser(tokens, name_to_k, expr).parse()


if __name__ == '__main__':
    def to_python_source(node: 'ResolvableT') -> str:
        """Render a ResolvableT tree back out as a Python source-code expression string."""
        if isinstance(node, bool):
            return str(int(node))
        if isinstance(node, int):
            return str(node)
        if isinstance(node, ResolvableFunctionOperation):
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
