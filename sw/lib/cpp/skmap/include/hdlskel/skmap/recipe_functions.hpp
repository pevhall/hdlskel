#pragma once
// Recipe functions available to generated skmap modules.
// Mirrors pip/skmap/src/skmap/recipe_functions.py

namespace hdlskel::skmap::recipe_functions {

// Python int.bit_length() (also for negatives, where python uses the bit
// length of the absolute value).
inline int bit_length(long long value) {
    unsigned long long v = (value < 0)
        ? static_cast<unsigned long long>(-(value + 1)) + 1ULL
        : static_cast<unsigned long long>(value);
    int bits = 0;
    while (v != 0) {
        bits++;
        v >>= 1;
    }
    return bits;
}

// floor division, matching python's `//` (truncates towards negative
// infinity, unlike C++'s `/` which truncates towards zero).
inline int floor_div(int n, int d) {
    int q = n / d;
    if ((n % d) != 0 && ((n < 0) != (d < 0))) {
        q--;
    }
    return q;
}

// ceiling division (mirrors py: -(n // -d))
inline int cdiv(int n, int d) {
    return -floor_div(n, -d);
}

// ceiling log base 2 (mirrors py: (x - 1).bit_length())
// clog2(1)=0, clog2(2)=1, clog2(3)=2, clog2(5)=3, clog2(8)=3
inline int clog2(int x) {
    return bit_length(static_cast<long long>(x) - 1);
}

}
