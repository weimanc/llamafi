#pragma once
#include <Arduino.h>

// Persists all runtime app settings to /settings.json on SPIFFS.
//
// Excluded — own files / own owners:
//   WiFi + Spotify creds  → /spotify_diy_config.json  (configFile.h / WiFiManager)
//   Touch calibration     → /cal.json                 (TouchCalStorage — history ring-buffer)

#define SETTINGS_JSON "/settings.json"

// ---- Enums ----------------------------------------------------------------

enum class DateFmt       : uint8_t { DMY = 0, MDY = 1, YMD = 2 };
enum class LedMode       : uint8_t { Off = 0, Static = 1, Pulse = 2, Clock = 3 };
enum class AppSpeed      : uint8_t { Slow = 0, Normal = 1, Fast = 2 };
enum class StockViewMode : uint8_t { List = 0, Chart = 1, Heatmap = 2 };
enum class MatrixColor   : uint8_t { Green = 0, White = 1, Amber = 2 };
enum class LifeColors    : uint8_t { Rainbow = 0, Mono = 1 };
enum class ClockStyle    : uint8_t { Digital = 0, Flip = 1, Nixie = 2, VFD = 3 };
enum class PlayerMode    : uint8_t { Spotify = 0, WebRadio = 1 };   // M-PLAYER-STATE / TASK-260
// M-PLANERADAR / phase0-preview-ui.md Q2: tag-collision rule. (a) reference —
// always place at the centre-side position, never nudge/drop. (b) + vertical
// nudge (±10/±20px), place at the un-nudged position if all four still
// overlap (never drops). (c) default — same nudge ladder, DROP the tag (keep
// the symbol) if all four still overlap.
enum class PrTagRule     : uint8_t { A = 0, B = 1, C = 2, Count = 3 };
// M-PLANERADAR / phase0-preview-ui.md Q5: stale-data indicator style. Ring =
// default, ring-3 colour shift + the always-shown strip age-text fallback.
// Text/Dim are named per the design doc's candidate list but were never
// prototyped in the preview tool (Q5 caveat) — both currently render
// identically to the strip age-text fallback alone (no ring shift) until a
// dimming-sweep visual is designed and eyeballed.
enum class PrStaleStyle  : uint8_t { Ring = 0, Text = 1, Dim = 2, Count = 3 };

// M-PR-LOCATIONS (TASK-315..325): named location presets for PlaneRadar.
// label[6] pads to 8 for float alignment -> 16 B/slot x PR_NUM_LOCS = 112 B
// (M-PR-LOCATIONS design, "Heap / budget note").
static constexpr uint8_t PR_NUM_LOCS  = 7;   // Q1 amended 4 -> 7 (2026-07-18): AGE/ERR strip rows moved to the strip bottom, slot pitch 26 -> 22 px
static constexpr uint8_t PR_LABEL_MAX = 5;   // chars, excl. NUL — strip-width bound; Q2 resolved: 5

struct PrLocation {
    char  label[PR_LABEL_MAX + 1];  // "" = empty slot
    float lat, lon;
};

// M-HOME-LOCATION (H-7a): the compile-time default home (Amsterdam). One named
// constant, four users: applyDefaults(), the two load() fallbacks, and the D4
// migration's "slot 0 still the untouched default?" comparison — one drifted
// literal would break that heuristic silently. Deliberately distinct from the
// kCities Amsterdam entry (52.3667/4.9000), so a real city-pick of Amsterdam
// is distinguishable from this default.
static constexpr float PR_DEFAULT_LAT = 52.3676f;
static constexpr float PR_DEFAULT_LON = 4.9041f;

// M-PR-MOTION Item A (TASK-355): PlaneRadar poll-interval slider bounds +
// default seed. 10 == the old fixed PR_POLL_MS (10000 ms) cadence. Lives here
// (not planeRadarApp.h) because applyDefaults()/load() are its primary
// consumers and the Settings slider row needs the bounds too.
static constexpr uint8_t PR_POLL_MIN_SEC     = 1;
static constexpr uint8_t PR_POLL_MAX_SEC     = 30;
static constexpr uint8_t PR_POLL_DEFAULT_SEC = 10;

// ---- Settings struct -------------------------------------------------------

struct AppSettings {

    // --- Time & Location (time-settings.md) ---
    char    posixTz[48];    // POSIX tz rule, e.g. "GMT0BST,M3.5.0/1,M10.5.0"
    char    tzName[32];     // display name, e.g. "Europe/London"
    char    city[24];       // selected city name; "" = none
    // M-HOME-LOCATION (D1b): lat/lon are REPURPOSED as the HOME MIRROR —
    // write-through mirror of prLocs[0], derived on every load and refreshed
    // by SettingsStorage::prSlotWritten(). Weather (WIRE2-G4) reads them; the
    // city picker writes them only via slot 0 + the helper, never directly.
    float   lat;
    float   lon;
    bool    fmt24h;         // true = 24h; false = 12h AM/PM
    DateFmt dateFmt;        // DMY / MDY / YMD

    // --- Display (display-settings.md) ---
    bool    dispAuto;       // true = LDR auto-brightness
    uint8_t dispLevel;      // 1..10 (used when dispAuto = false)
    int16_t ldrLow;         // ADC floor  for auto-brightness mapping
    int16_t ldrHigh;        // ADC ceiling for auto-brightness mapping

    // --- LED (led-settings.md) ---
    LedMode ledMode;
    uint8_t ledHue;   // 0..255 — HSV hue (0=red, 85≈green, 170≈blue)
    uint8_t ledSat;   // 0..255 — HSV saturation
    uint8_t ledVal;   // 0..255 — HSV value (brightness)

    // --- Stock (settings.md §Applications) ---
    char          stockTickers[8][8];   // up to 7-char symbol + NUL
    StockViewMode stockMode;

    // --- Crypto ---
    char    cryptoCoins[6][16];
    char    cryptoCcy[4];               // "USD" | "EUR"

    // --- Aquarium ---
    uint8_t  aquariumFish;              // 4 / 8 / 12 / 16
    AppSpeed aquariumSpeed;

    // --- Matrix ---
    MatrixColor matrixColor;
    AppSpeed    matrixSpeed;

    // --- Life ---
    AppSpeed   lifeSpeed;
    LifeColors lifeColors;

    // --- Clock ---
    ClockStyle clockStyle;   // Digital / Flip / Nixie / VFD
    uint8_t    nixieTheme;   // 0=amber 1=red 2=green 3=blue (M-CLOCK-THEMES)
    uint8_t    vfdTheme;     // 0=teal 1=amber 2=blue 3=green (M-CLOCK-THEMES)

    // --- Player slot (M-PLAYER-STATE / TASK-260) ---
    // The Winamp "player" slot is one slot with two mutually-exclusive modes. Persisted
    // so the taskbar player-slot restore + Settings display + cold-boot survive a reboot.
    // Stored as uint8_t (PlayerMode). v2 (OQ-BOOT): boot enters the persisted mode.
    uint8_t playerMode;      // PlayerMode: Spotify=0 | WebRadio=1

    // --- Teletext (ADR-044) ---
    uint16_t teletextPage;        // starting page on resume (default 101)
    uint8_t  teletextPollSecs;    // refresh cadence: 30/60/120 s (default 60)
    uint8_t  teletextCountry;     // 0 = NOS/NL; reserved until multi-country lands
    bool     teletextAutoAdvance; // reserved; no UI until subpage auto-advance implemented

    // --- Web Radio (M-WEBRADIO) ---
    char    webRadioCountry[4];   // ISO 3166-1 alpha-2, e.g. "NL\0\0" (default NL)
    bool    webRadioAutoplay;     // reconnect last station on resume (default false)
    uint8_t webRadioBitrateCap;   // 0=off / 64 / 96 / 128 / 192 kbps. Applied as the radio-browser bitrateMax query filter (TASK-221)
    bool    webRadioAutoSkip;     // TASK-234/ADR-045: retry-once-then-advance past dead stations on ERROR_STALL/ERROR_UNREACHABLE, bounded to one list pass. Default ON (no-PSRAM decode failures are common; see TASK-233)
    bool    webRadioHwMod;        // SC8002B gain-reduction mod installed (M-WEBRADIO §HW Mod). Gates the anti-clipping ceiling: enforced by webRadioApp::wrEffectiveVolume() (TASK-209) — false → soft-cap 12, true → full 1–21
    uint8_t webRadioMaxVolume;    // 1–21 configured ceiling → setVolume(), clamped by wrEffectiveVolume() (TASK-209: stock soft-cap 12 / mod full range). Default 10 stock / 18 with HW mod. Exact stock clip point still needs DUT+ears calibration (T_WR_VOL_01/02)
    uint8_t webRadioLastStation;  // persisted last station index (default 0)
    uint8_t webRadioVolumePct;    // TASK-352: Winamp slider session volume, 0-100, scales *within* the
                                   // webRadioMaxVolume/wrEffectiveVolume() ceiling (default 100 = today's
                                   // full-ceiling behaviour). Coalesced-save on suspend (ADR-050 rule 3).

    // --- Plane Radar (M-PLANERADAR, ADR-048/049, TASK-305) ---
    // lat/lon: D4 (v1) — compile-time default, edited via `run/spiffs push`;
    // no numeric-entry UI (shown greyed-out/read-only in Settings, like
    // Teletext's Country row).
    float        prLat, prLon;
    uint8_t      prUnits;         // 0 = km, 1 = mi
    bool         prRunwayOverlay; // show runway overlay when on (density=all, Q4)
    uint8_t      prRangeIdx;      // 0..3 -> 5/10/15/25 km preset, persists across reboot
    PrTagRule    prTagRule;       // Q2, default C
    PrStaleStyle prStaleStyle;    // Q5, default Ring
    // M-PR-MOTION Item A (TASK-355): poll cadence in seconds, 1–30, default
    // PR_POLL_DEFAULT_SEC (10 == the old fixed PR_POLL_MS). Read LIVE by
    // planeRadarApp's tick gate (prPollSec * 1000UL) — a Settings edit
    // applies on the next tick, no resume-diff. Deliberately NO hidden clamp
    // below ~5 s: the app's _pendingFetch gate serializes fetches and the
    // device GET itself walls at ~4.3 s (Cloudflare edge pacing, TASK-313),
    // so low settings degrade to fetch-completion pacing (~4–5 s effective)
    // — self-limiting, no request pile-up, still inside adsb.fi's 1 req/s
    // courtesy limit. load() clamps only OUT-OF-RANGE values (0 / >30).
    uint8_t      prPollSec;
    // M-PR-LOCATIONS: named presets. prLat/prLon above are now the
    // write-through mirror of prLocs[prActiveLoc] (design "Settings storage")
    // — every existing prLat/prLon consumer keeps working unmodified; the
    // mirror is derived FROM the active slot, not the other way round.
    PrLocation   prLocs[PR_NUM_LOCS];  // slot 0 always defined; "" label = empty slot
    uint8_t      prActiveLoc;          // index into prLocs, 0..PR_NUM_LOCS-1
};

extern AppSettings g_settings;

// ---- Storage API -----------------------------------------------------------

namespace SettingsStorage {
    void load();   // SPIFFS → g_settings; per-key defaults applied for missing entries
    void save();   // g_settings → SPIFFS

    // M-HOME-LOCATION (H-1/H-3): the writer×mirror matrix lives HERE and only
    // here (BP-047 — one shared sequence, never a second inline copy). Two
    // mirrors exist; "the mirror" unqualified is banned:
    //   home mirror   lat/lon     = prLocs[0]           — refreshed iff slot == 0
    //   active mirror prLat/prLon = prLocs[prActiveLoc] — refreshed iff slot == prActiveLoc
    // Call after ANY write to g_settings.prLocs[slot] (city picker,
    // _prSaveCoords, delete-fallback, `set prloc <i> ...`). Does NOT persist —
    // callers own the save() they already do. SWITCHING the active slot
    // (_setActiveLoc / `set prloc active`) is not a slot write and never
    // touches home — it keeps its own prLat/prLon copy.
    void prSlotWritten(uint8_t slot);

#ifdef SERIAL_DEBUG
    // T-WRSET-04: completed-write counter for save() — increments once per
    // actual SPIFFS write. The doc.overflowed() abort path (TASK-329) and a
    // failed SPIFFS.open()/serializeJson() do NOT count, so this can't be
    // fooled by a save that never reached flash. Lets VE prove ADR-050 rule 3
    // coalesced-save discipline (one save per suspend/eject, not one per
    // station-index change) with a hard counter instead of parsing
    // "SettingsStorage: saved" log lines. Debug-only; `get settingsSaveCount`.
    uint32_t debugSaveCount();
#endif
}
