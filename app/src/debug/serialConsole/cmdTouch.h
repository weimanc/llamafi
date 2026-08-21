#pragma once
// debug/serialConsole/cmdTouch.h — touch injection — cmdTap / cmdDrag /
// cmdRelease / cmdTick (M-SRCLAYOUT Stage E / TASK-471). Declarations only —
// bodies in cmdTouch.cpp, defined unconditionally there under SERIAL_DEBUG
// same as the rest of the command surface (harmless if unreferenced in a
// production build, see consoleShared.h).

void cmdTap(const char *);
void cmdDrag(const char *);
void cmdRelease(const char *);
void cmdTick(const char *);
