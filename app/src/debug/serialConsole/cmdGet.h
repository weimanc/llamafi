#pragma once
// debug/serialConsole/cmdGet.h — `get` — debug variable reads (M-SRCLAYOUT
// Stage E / TASK-471). Declaration only — body in cmdGet.cpp, defined
// unconditionally there under SERIAL_DEBUG same as the rest of the command
// surface (harmless if unreferenced in a production build, see
// consoleShared.h).

void cmdGet(const char *);
