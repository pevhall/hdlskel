#pragma once
// Recipe functions available to generated skmap modules.
// Mirrors pip/skmap/src/skmap/recipe_functions.py

namespace hdlskel::skmap::recipe_functions {

// ceiling division (for positive divisor)
inline int cdiv(int n, int d) {
    return -((-n) / d);
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
