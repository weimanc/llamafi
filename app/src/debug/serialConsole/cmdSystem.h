#pragma once
// debug/serialConsole/cmdSystem.h — reboot / advance / help (M-SRCLAYOUT
// Stage E / TASK-471). SERIAL_DEBUG-only: declared unconditionally (harmless
// if unreferenced — see consoleShared.h), defined in cmdSystem.cpp only when
// SERIAL_DEBUG is set, same as the rest of the command surface.

void cmdReboot(const char *);
void cmdAdvance(const char *);
void cmdHelp(const char *);
