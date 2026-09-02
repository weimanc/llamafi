#pragma once
// debug/serialConsole/cmdMisc.h — switchapp / info / screendump / colorprobe
// (M-SRCLAYOUT Stage E / TASK-471). Declarations only — bodies in
// cmdMisc.cpp, defined unconditionally there under SERIAL_DEBUG same as the
// rest of the command surface (harmless if unreferenced in a production
// build, see consoleShared.h).

void cmdSwitchApp(const char *);
void cmdInfo(const char *);
void cmdScreenDump(const char *);
void cmdColorProbe(const char *);
void cmdSerialBurst(const char *);
