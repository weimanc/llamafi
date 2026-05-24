#pragma once
// appShell.h — app registry and dispatch (M-MULTIAPP skeleton, TASK-083 step 3).
// Stubs only; wired up in step 4 (main.cpp rewrite).

#include <Arduino.h>

enum class AppId : uint8_t {
    Spotify  = 0,
    Clock    = 1,
    Weather  = 2,
    Crypto   = 3,
    Matrix   = 4,
    Life     = 5,
    COUNT    = 6,
};

extern AppId currentAppId;

// Dispatch stubs — implemented in main.cpp.
void appTick(AppId id);
void appHandleInput(AppId id);
void switchApp(AppId next);
