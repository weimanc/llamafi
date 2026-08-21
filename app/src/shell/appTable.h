#pragma once
// shell/appTable.h — THE COMPOSITION ROOT (M-SRCLAYOUT Stage D, D0c / ADR-060 D2).
//
// The one place all thirteen App instances are constructed. Declarations only —
// definitions live in appTable.cpp (M-SRCLAYOUT Stage E / TASK-471).
//
// WHY THIS WAS A HEADER-ONLY FILE UNTIL NOW: making it a second translation
// unit was not safe before Stage E finished the audio engine's own split.
// audio/audioEngine.h used to define three EXTERNAL-LINKAGE function bodies
// (audio_showstreamtitle, audio_info, audio_process_extern) plus file-scope
// statics holding live engine state (s_icyTitleQueue, s_wr_audio, the aeXxx
// flags) directly in the header — both webRadioApp.h and localPlayerApp.h
// include it, so a second TU constructing those two apps would have
// duplicate-defined the functions at link time and silently forked the
// statics (two "the Audio object"s, main.cpp's loop() reading one,
// appTable.cpp-constructed apps writing the other, no diagnostic). That
// split landed first in this stage — see audio/audioEngine.h's own header
// comment — which is what makes this file safe to convert now.
//
// Reached from main.cpp (and now the debug console's own .cpp files) via
// the extern declarations below.

// ── SpotifyApp (TASK-090d) ─────────────────────────────────────────────
#include "apps/spotifyApp.h"
extern SpotifyApp g_SpotifyApp;

// ── ClockApp (M-CLOCK-STYLES) ─────────────────────────────────────────
#include "clockApp.h"
extern ClockApp g_ClockApp;

#include "apps/matrixApp.h"
extern MatrixApp g_MatrixApp;

#include "apps/weatherApp.h"
extern WeatherApp g_WeatherApp;

#include "apps/cryptoApp.h"
extern CryptoApp g_CryptoApp;

#include "apps/lifeApp.h"
extern LifeApp g_LifeApp;

#include "apps/settingsApp.h"
extern SettingsApp g_SettingsApp;
extern LedFlow      g_ledFlow;
extern BacklightFlow g_backlight;   // WIRE2-G5: backlight owner (ADR-050)
extern KeyboardWidget g_keyboard;
extern SPickerList g_countryPicker;   // M-COUNTRY-PICKER: shared modal country picker (settingsWidgets.h)
#ifdef SERIAL_DEBUG
bool settingsDbgGet(const char* v, char* b, int l);
#endif

#include "apps/stockApp.h"
extern StockApp g_StockApp;
bool stockDbgGet(const char* v, char* b, int l);
bool stockDbgSet(const char* v, const char* val);

#include "aquarium/aquariumApp.h"
extern AquariumApp g_AquariumApp;

#include "teletextApp.h"
extern TeletextApp g_TeletextApp;
bool teletextDbgGet(const char* v, char* b, int l);
bool teletextDbgSet(const char* v, const char* val);

#include "planeRadarApp.h"
extern PlaneRadarApp g_PlaneRadarApp;
bool planeRadarDbgGet(const char* v, char* b, int l);
bool planeRadarDbgSet(const char* v, const char* val);

#include "webRadioApp.h"
extern WebRadioApp g_WebRadioApp;
bool webRadioDbgGet(const char* v, char* b, int l);
bool webRadioDbgSet(const char* v, const char* val);

#include "localPlayerApp.h"
extern LocalPlayerApp g_LocalPlayerApp;   // TASK-413: placeholder, real UI is TASK-415+

#ifdef SERIAL_DEBUG
bool matrixDbgGet(const char* v, char* b, int l);
bool lifeDbgGet(const char* v, char* b, int l);
bool cryptoDbgGet(const char* v, char* b, int l);
bool aquariumDbgGet(const char* v, char* b, int l);
#endif

// ── App registry + shell gesture state (TASK-090f) ────────────────────

extern App* g_apps[(int)AppId::COUNT];
