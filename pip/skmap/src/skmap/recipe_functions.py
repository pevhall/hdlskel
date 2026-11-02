import math

def cdiv(n, d):
    return - (n // -d)

def clog2(x):
    return (x - 1).bit_length()

def round(value):
    """Round a value to the nearest integer, halves away from zero.

    The recipe `$round` of a v_check / v_convert_wr / v_convert_rd, it is the
    rounding the runtime uses to turn a float value into a register value and
    it matches std::round of the c++ library (the python built-in round()
    rounds half to even, that is not what a register wants).
    """
    if isinstance(value, int):
        return value
    return int((value + 0.5)//1) if value >= 0 else -int((-value + 0.5)//1)

def ceil(value):
    """Ceiling of a value, the nearest integer above it (recipe `$ceil`).

    $ceil(10.1) = 11, $ceil(-10.1) = -10, matches std::ceil of the c++
    library.
    """
    return math.ceil(value)
