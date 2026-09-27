#pragma once
// Recipe functions available to generated skmap modules.
// Mirrors pip/skmap/src/skmap/recipe_functions.py

namespace hdlskel::skmap::recipe_functions {

// ceiling division (mirrors py: -(n // -d); for the positive values used in
// recipes this is the usual ceiling division)
inline int cdiv(int n, int d) {
    return (n + d - 1) / d;
}
// ceiling log base 2 (of a positive value)
inline int clog2(int x) {
    int r = 0;
    while (x > 1) {
        x >>= 1;
        r++;
    }
    return r;
}

}
