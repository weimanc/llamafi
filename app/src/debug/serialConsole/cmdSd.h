#pragma once
// debug/serialConsole/cmdSd.h — SD bring-up probes (TASK-408 et al),
// M-SRCLAYOUT Stage E / TASK-471. Declarations only — bodies in cmdSd.cpp,
// defined unconditionally there under SERIAL_DEBUG same as the rest of the
// command surface (harmless if unreferenced in a production build, see
// consoleShared.h).

void cmdSdMem(const char *);
void cmdSdMount(const char *);
void cmdSdUmount(const char *);
void cmdSdCycle(const char *);
void cmdSdMkdir(const char *);
void cmdSdPut(const char *);
void cmdSdMbr(const char *);
void cmdSdOpenDir(const char *);
void cmdSdSlots(const char *);
void cmdSdLs(const char *);
void cmdSdRead(const char *);
void cmdSdWrite(const char *);
void cmdSdClean(const char *);
void cmdSdProbe(const char *);
