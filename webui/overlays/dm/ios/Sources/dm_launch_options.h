#pragma once
#include <stddef.h>
#include <string.h>

static inline const char *dm_launch_resolve(unsigned row, const char *saved, const char *env, const char *bundle) {
    static const char *const choices[8][6] = {
        {"system", "zh-Hans", "zh-Hant", "en-US", "ja", NULL},
        {"0", "1", NULL}, {"0", "1", NULL}, {"0", "1", NULL}, {"0", "1", NULL},
        {"auto", "720", "900", "1080", "1440", NULL}, {"0", "1", NULL}, {"0", "1", NULL}
    };
    static const char *const defaults[8] = {"system", "0", "1", "1", "0", "auto", "0", "0"};
    if (row >= 8) return NULL;
    const char *candidates[3] = {saved, env, bundle};
    for (unsigned source = 0; source < 3; source++) {
        if (!candidates[source]) continue;
        for (unsigned i = 0; choices[row][i]; i++)
            if (!strcmp(candidates[source], choices[row][i])) return choices[row][i];
    }
    return defaults[row];
}

static inline const char *dm_launch_choice(unsigned row, const char *saved, const char *env) {
    return dm_launch_resolve(row, saved, env, NULL);
}
