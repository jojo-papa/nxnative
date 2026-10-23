#pragma once
#include <string.h>

// Output policy only; never changes guest render targets or the drawable.
static inline unsigned dm_spatial_height(const char *value) {
    if (!value) return 0;
    if (!strcmp(value, "720")) return 720;
    if (!strcmp(value, "900")) return 900;
    if (!strcmp(value, "1080")) return 1080;
    if (!strcmp(value, "1440")) return 1440;
    return 0;
}
static inline void dm_spatial_output_size(unsigned sw, unsigned sh, unsigned dw, unsigned dh,
                                          unsigned height, unsigned *ow, unsigned *oh) {
    *ow = dw; *oh = dh;
    if (!height || !sw || !sh) return;
    // A lower target is not an internal resolution reduction. Preserve input.
    if (height <= sh) { *ow = sw; *oh = sh; return; }
    unsigned long long width = ((unsigned long long)sw * height + sh) / (2ull * sh) * 2;
    if (!width || width > 8192) return;
    *ow = (unsigned)width; *oh = height;
}
