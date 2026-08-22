#pragma once
// sd/sdMount.h — the boot-time SD mount, PRODUCTION code (M-SRCLAYOUT
// Stage E / TASK-471). Gated on SD_BOOT_MOUNT, not SERIAL_DEBUG — this is
// deliberately NOT under debug/ despite sitting adjacent to the SD probes in
// the old main.cpp (ADR-061 D4). Definitions in sdMount.cpp.
//
// TASK-408 (M-SDFS phase-0): own VSPI bus — SCK18/MISO19/MOSI23/CS5 — entirely
// free of the HSPI TFT bus and the touch controller's own SPI (see
// M-SDFS-sd-card-exploration.md §2). The mount is established once in
// bootSequence() and held — see sdProbeBootMount()'s call site for why a
// lazy per-mode-entry mount cannot be relied on here.
//
// TASK-427: this block — the statics, `sdMountAttempt()`, `sdProbeBootMount()`,
// and `sdReady()` — is gated on SD_BOOT_MOUNT, not SERIAL_DEBUG, so it compiles
// into any variant that wants the boot mount without pulling in the rest of
// the SERIAL_DEBUG command surface (`cyd2usb_player`). `cyd2usb_winamp_debug`
// defines both, so every existing T_PLR/T_SD gate is unaffected.
// `cyd2usb_winamp` (production) defines neither — no mount, sdReady() stubs
// to false, Player mode degrades to "No SD card". That remains deliberate: an
// unconditional boot mount costs ~13 KB of permanently-held contiguous
// internal heap (FATFS window + max_files × FIL), which TASK-425 measured
// does not fit alongside the Spotify TLS working set and the Helix arena —
// see TASK-431. The interactive bring-up probes (`sdmem`, `sdmount`/
// `sdumount`, `sdcycle`, `sdls`, `sdread`, `sdwrite`, `sdclean`, `sdprobe` —
// the full T_SD_01-09 sweep, in debug/serialConsole/cmdSd.cpp) stay
// SERIAL_DEBUG-only and reference the statics/functions declared here.

#include <Arduino.h>

#ifdef SD_BOOT_MOUNT
#include <SD.h>
#include <SPI.h>

extern const int kSdCsPin;
extern const int kSdSckPin;
extern const int kSdMisoPin;
extern const int kSdMosiPin;
extern uint32_t s_sdFreqHz;
extern const uint8_t kSdMaxFiles;
extern SPIClass s_sdSPI;
extern bool s_sdReady;
extern bool s_sdSpiUp;
extern size_t s_sdBootFreeIntBefore, s_sdBootFreeIntAfter;
extern size_t s_sdBootLfbIntBefore, s_sdBootLfbIntAfter;

// One mount attempt with full before/after heap accounting, usable from
// bootSequence() and from a live serial command. `tag` names the call site
// in the JSON line.
bool sdMountAttempt(const char *tag, uint8_t maxFiles);

// Called from bootSequence() (boot/boot.h). Non-static — boot.h is still
// textually #include'd into main.cpp's translation unit (Stage E has not
// converted it yet), so this needs external linkage to be called from there
// once sdMount becomes its own TU.
void sdProbeBootMount();
#endif // SD_BOOT_MOUNT

// TASK-415: the boot mount's outcome, for code outside this file (LocalPlayerApp
// must degrade to "No SD card" rather than opening files against a dead mount).
// A function, not an extern on s_sdReady, so the mount state stays owned here.
// Declared unconditionally — defined either way (real answer under
// SD_BOOT_MOUNT, permanent false otherwise), same convention as the rest of
// this codebase's build-variant stubs.
bool sdReady();
