#!/usr/bin/env python3

import argparse
from enum import Enum, auto
from pathlib import Path
from datetime import datetime
from typing import Union
from abc import abstractmethod

from .code_generator_parse_recipe import ValueTypeUnresolved, parse_recipe_file, RecipeK, RecipeVar, RecipeReg, ResolvableFunction
# from basic import promote_to_sw_w, ceil_div
from .basic_types import Acc, Ass, ValueKind, ValueType, SKMAP_VER_STR

class Sw(Enum):
    py = auto()
    cpp = auto()

@abstractmethod
def name_to_reg_var(name : str) -> str:
    assert(False)

@abstractmethod
def name_to_reg_k(name : str) -> str:
    assert(False)

@abstractmethod
def resolve_k_value(v : RecipeK) -> str:
    assert(False)

def reg_to_inst_str(reg : RecipeReg) -> str:
    if isinstance(reg, RecipeK):
        return name_to_reg_k(reg.name)
    assert isinstance(reg, RecipeVar)
    return name_to_reg_var(reg.name)


def resolvable_str(v : Union[int, RecipeK, ResolvableFunction]) -> str:
    if isinstance(v, int):
        return str(v)
    if isinstance(v, RecipeK):
        return resolve_k_value(v)
    if isinstance(v, ResolvableFunction):
        return f'({v.lhs} {v.op} {v.rhs})' #type: ignore
    raise runtimeError(f"Unexpected {type(v)=}")

def resolvable_member_function(value : Union[ResolvableFunction, RecipeK, int]) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, RecipeK):
        return resolve_k_value(value)
    assert isinstance(value, ResolvableFunction), f"{type(value)=}"
    lhs = resolvable_member_function(value.lhs)
    rhs = resolvable_member_function(value.rhs)
    return f'({lhs} {value.op} {rhs})'


@abstractmethod
def value_type_str(value_type : Union[ValueType, ValueTypeUnresolved]):
    assert(False)

@abstractmethod
def value_ret_type_str(t : Union[ValueType, ValueTypeUnresolved]):
    assert(False)

def _value_kind_function_str(k : ValueKind) -> str:
    match k:
        case ValueKind.uint:
            return 'uint'
        case ValueKind.sint:
            return 'sint'
        case ValueKind.bits:
            return 'uint'
        case ValueKind.flag:
            return 'uint'
        case _:
            assert False

def _value_type_function_str(t : Union[ValueType, ValueTypeUnresolved], sw : Sw) -> str:
    f = ''
    if t.kind == ValueKind.char:
        if t.is_vec:
            f += 'str'
        else:
            f += 'char'
    else:
        if t.is_vec:
            assert isinstance(sw, Sw)
            match(sw):
                case(Sw.py ): f += 'list'
                case(Sw.cpp): f += 'vec'
            f += '_'
        f += _value_kind_function_str(t.kind)
    return f

def read_value_function_str(t : Union[ValueType, ValueTypeUnresolved], cached : bool, sw:Sw) -> str:
    f = 'read_'+_value_type_function_str(t, sw)
    if cached:
        f += '_cached'
    return f

def write_value_function_str(t : Union[ValueType, ValueTypeUnresolved], cached : bool, sw:Sw) -> str:
    f =  'write_'+_value_type_function_str(t, sw)
    if cached:
        f += '_cached'
    return f

@abstractmethod
def all_reg_value_functions_str_not_flag(reg : RecipeReg) -> str:
    assert False

@abstractmethod
def all_reg_value_functions_str_is_flag(reg : RecipeReg) -> str:
    assert False

def all_reg_value_functions_str(reg : RecipeReg) -> str:
    if reg.t.kind == ValueKind.flag:
        return all_reg_value_functions_str_is_flag(reg)
    else:
        return all_reg_value_functions_str_not_flag(reg)

