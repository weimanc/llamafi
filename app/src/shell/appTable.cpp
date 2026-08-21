// shell/appTable.cpp — THE COMPOSITION ROOT, definitions (M-SRCLAYOUT Stage E / TASK-471).
// See appTable.h for the "why this is safe as a .cpp now" note.
#include "shell/appTable.h"

SpotifyApp g_SpotifyApp;
ClockApp g_ClockApp;

MatrixApp g_MatrixApp;
WeatherApp g_WeatherApp;
CryptoApp g_CryptoApp;
LifeApp g_LifeApp;

SettingsApp g_SettingsApp;
LedFlow      g_ledFlow;
BacklightFlow g_backlight;   // WIRE2-G5: backlight owner (ADR-050)
KeyboardWidget g_keyboard;
SPickerList g_countryPicker;   // M-COUNTRY-PICKER: shared modal country picker (settingsWidgets.h)
#ifdef SERIAL_DEBUG
bool settingsDbgGet(const char* v, char* b, int l) { return g_SettingsApp.dbgGet(v, b, l); }
#endif

StockApp g_StockApp;
bool stockDbgGet(const char* v, char* b, int l) { return g_StockApp.dbgGet(v, b, l); }
bool stockDbgSet(const char* v, const char* val) { return g_StockApp.dbgSet(v, val); }

AquariumApp g_AquariumApp;

TeletextApp g_TeletextApp;
bool teletextDbgGet(const char* v, char* b, int l) { return g_TeletextApp.dbgGet(v, b, l); }
bool teletextDbgSet(const char* v, const char* val) { return g_TeletextApp.dbgSet(v, val); }

PlaneRadarApp g_PlaneRadarApp;
bool planeRadarDbgGet(const char* v, char* b, int l) { return g_PlaneRadarApp.dbgGet(v, b, l); }
bool planeRadarDbgSet(const char* v, const char* val) { return g_PlaneRadarApp.dbgSet(v, val); }

WebRadioApp g_WebRadioApp;
bool webRadioDbgGet(const char* v, char* b, int l) { return g_WebRadioApp.dbgGet(v, b, l); }
bool webRadioDbgSet(const char* v, const char* val) { return g_WebRadioApp.dbgSet(v, val); }

LocalPlayerApp g_LocalPlayerApp;   // TASK-413: placeholder, real UI is TASK-415+

#ifdef SERIAL_DEBUG
bool matrixDbgGet(const char* v, char* b, int l)   { return g_MatrixApp.dbgGet(v, b, l); }
bool lifeDbgGet(const char* v, char* b, int l)     { return g_LifeApp.dbgGet(v, b, l); }
bool cryptoDbgGet(const char* v, char* b, int l)   { return g_CryptoApp.dbgGet(v, b, l); }
bool aquariumDbgGet(const char* v, char* b, int l) { return g_AquariumApp.dbgGet(v, b, l); }
#endif

// TASK-496/467: WINAMP_DISPLAY is unconditionally defined (every buildable
// env, ADR-061 D8); the {} else-branch (populated by no buildable env) is
// removed.
App* g_apps[(int)AppId::COUNT] = {
#define APP_X(Name, icon, cfg, disp) &g_##Name##App,
#include "appRegistry.h"
#undef APP_X
};
