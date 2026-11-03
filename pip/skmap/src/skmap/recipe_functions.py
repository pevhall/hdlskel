import math

_float = float    # the built-in, kept under a name the float() below does not shadow

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

def floor(value):
    """Floor of a value, the nearest integer below it (recipe `$floor`).

    $floor(10.9) = 10, $floor(-10.1) = -11, matches std::floor of the c++
    library.
    """
    return math.floor(value)

def float(value):
    """Convert a value to a float (recipe `$float`).

    $float(8) = 8.0, it takes an int (eg an ipkg / k value) and gives a
    float, so an expression becomes a float one. The c++ runtime function is
    named to_float, `float` is a keyword there.
    """
    return _float(value)
