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
void readbackSignature(const char *);      // ADR-064 D1: `get sig <x> <y> <w> <h>` (TASK-638)
void cmdSerialBurst(const char *);
void cmdBod(const char *);
void cmdBodMit(const char *);
void cmdMark(const char *);          // TASK-678 F-1: `mark <label>` — esp_timer stamp only
void cmdSerialSink(const char *);    // TASK-678 F-3
void cmdSerialEcho(const char *);    // TASK-678 F-3
