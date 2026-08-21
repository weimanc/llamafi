#pragma once
// shell/appTable.h — THE COMPOSITION ROOT (M-SRCLAYOUT Stage D, D0c / ADR-060 D2).
//
// The one place all thirteen App instances are constructed. Everything below this
// header comment was moved VERBATIM out of app/src/main.cpp (M-SRCLAYOUT Stage D,
// TASK-456) — not one line of the body was edited, in the same order, at the same
// point in the same translation unit. Symbol identity across cyd2usb_winamp,
// cyd2usb_winamp_debug and cyd2usb_player is the proof; see the commit message.
//
// WHY THIS IS A HEADER AND NOT appTable.cpp, which is what D0c/ADR-060 D2 sketch:
// making it a second translation unit is NOT safe before Stage E, and the reason is
// stronger than the one ADR-060 D2 recorded (the WINAMP_DISPLAY conditional gap,
// closed since by TASK-496/467). Two mechanisms, both verified in the source:
//
//   1. audio/audioEngine.h defines three EXTERNAL-LINKAGE function bodies —
//      audio_showstreamtitle, audio_info, audio_process_extern (:83, :94, :209),
//      and :82 says so in as many words. webRadioApp.h and localPlayerApp.h both
//      include it, so a second TU that constructs those two apps duplicates all
//      three at link time.
//   2. Worse, and silent: those app headers carry file-scope statics that hold live
//      engine state (audioEngine.h's s_icyTitleQueue, s_wr_audio, the aeXxx flags).
//      Their class members are implicitly inline, so the linker keeps ONE copy of
//      each method — but each TU compiled its own copy of the statics. main.cpp's
//      loop() (aeDrainEof) and an appTable.cpp-constructed WebRadioApp would then
//      be reading and writing DIFFERENT objects, with no diagnostic.
//
// Splitting those statics out is exactly what Stage E (TASK-471) is for. Converting
// this file to a .cpp now would drag that work into a stage contracted as a pure
// move — the identical judgement, for the identical reason, that Stage C recorded
// when it left boot/boot.h a header (8cb5578).
//
// Reached from main.cpp only, at the point the instances used to sit.

// ── SpotifyApp (TASK-090d) ─────────────────────────────────────────────
// TASK-496/467: WINAMP_DISPLAY is defined by every buildable env
// (ADR-061 D8 demoted the one env that didn't, [env:cyd2usb], to a
// non-building base section) — the #ifdef here was unconditionally
// true and has been removed.
#include "apps/spotifyApp.h"
static SpotifyApp g_SpotifyApp;

// ── ClockApp (M-CLOCK-STYLES) ─────────────────────────────────────────
#include "clockApp.h"
static ClockApp g_ClockApp;

// ── VE instrumentation statics (consumed by SERIAL_DEBUG cmdGet) ─────────────
// s_wxDataReady/s_cxDataReady retired (TASK-471): WeatherApp/CryptoApp are now
// separate translation units, so cmdGet.h reads g_WeatherApp.dataReady() /
// g_CryptoApp.dataReady() directly instead of a composition-root static.
static int  s_golAliveCount = -1;      // -1 = GoL never ticked; ≥0 = last alive count

#include "apps/matrixApp.h"
static MatrixApp g_MatrixApp;

#include "apps/weatherApp.h"
static WeatherApp g_WeatherApp;

#include "apps/cryptoApp.h"
static CryptoApp g_CryptoApp;

#include "apps/lifeApp.h"
static LifeApp g_LifeApp;

#include "apps/settingsApp.h"
static SettingsApp g_SettingsApp;
LedFlow      g_ledFlow;
BacklightFlow g_backlight;   // WIRE2-G5: backlight owner (ADR-050)
KeyboardWidget g_keyboard;
SPickerList g_countryPicker;   // M-COUNTRY-PICKER: shared modal country picker (settingsWidgets.h)
#ifdef SERIAL_DEBUG
static bool settingsDbgGet(const char* v, char* b, int l) { return g_SettingsApp.dbgGet(v, b, l); }
#endif

#include "apps/stockApp.h"
static StockApp g_StockApp;
static bool stockDbgGet(const char* v, char* b, int l) { return g_StockApp.dbgGet(v, b, l); }
static bool stockDbgSet(const char* v, const char* val) { return g_StockApp.dbgSet(v, val); }

#include "aquarium/aquariumApp.h"
static AquariumApp g_AquariumApp;

#include "teletextApp.h"
static TeletextApp g_TeletextApp;
static bool teletextDbgGet(const char* v, char* b, int l) { return g_TeletextApp.dbgGet(v, b, l); }
static bool teletextDbgSet(const char* v, const char* val) { return g_TeletextApp.dbgSet(v, val); }

#include "planeRadarApp.h"
static PlaneRadarApp g_PlaneRadarApp;
static bool planeRadarDbgGet(const char* v, char* b, int l) { return g_PlaneRadarApp.dbgGet(v, b, l); }
static bool planeRadarDbgSet(const char* v, const char* val) { return g_PlaneRadarApp.dbgSet(v, val); }

// TASK-496/467: WINAMP_DISPLAY is unconditionally defined (see note above); #ifdef removed.
#include "webRadioApp.h"
static WebRadioApp g_WebRadioApp;
static bool webRadioDbgGet(const char* v, char* b, int l) { return g_WebRadioApp.dbgGet(v, b, l); }
static bool webRadioDbgSet(const char* v, const char* val) { return g_WebRadioApp.dbgSet(v, val); }

#include "localPlayerApp.h"
static LocalPlayerApp g_LocalPlayerApp;   // TASK-413: placeholder, real UI is TASK-415+

#ifdef SERIAL_DEBUG
static bool matrixDbgGet(const char* v, char* b, int l)   { return g_MatrixApp.dbgGet(v, b, l); }
static bool lifeDbgGet(const char* v, char* b, int l)     { return g_LifeApp.dbgGet(v, b, l); }
static bool cryptoDbgGet(const char* v, char* b, int l)   { return g_CryptoApp.dbgGet(v, b, l); }
static bool aquariumDbgGet(const char* v, char* b, int l) { return g_AquariumApp.dbgGet(v, b, l); }
#endif

// ── App registry + shell gesture state (TASK-090f) ────────────────────

// TASK-496/467: WINAMP_DISPLAY is unconditionally defined (see note above);
// the {} else-branch (populated by no buildable env) is removed.
App* g_apps[(int)AppId::COUNT] = {
#define APP_X(Name, icon, cfg, disp) &g_##Name##App,
#include "appRegistry.h"
#undef APP_X
};
