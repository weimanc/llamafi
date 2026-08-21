#pragma once
// debug/serialConsole/cmdSet.h — `set` — debug variable writes (M-SRCLAYOUT
// Stage E / TASK-471). Declaration only — body in cmdSet.cpp, defined
// unconditionally there under SERIAL_DEBUG same as the rest of the command
// surface (harmless if unreferenced in a production build, see
// consoleShared.h).

void cmdSet(const char *);
