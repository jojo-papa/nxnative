#include <stdbool.h>

// The Windows cross-build compiles no Swift, so Launcher.swift (which defines
// dm_show_launcher) is absent. The fork's ObjC DmLaunchSettings screen is the
// launcher there; returning false starts the game after it applies its settings.
bool dm_show_launcher(void *view_controller, void (*done)(void)) {
    (void)view_controller;
    (void)done;
    return false;
}
