# Design — M-SETTINGS-WIRE2: Global settings wiring gaps (audit remediation)

> Owner: Architect
> Status: draft
> Date: 2026-07-16
> Feeds: ADR-050 (accepted 2026-07-16)
> Tracked-as: — (PM to slice into TASKs after review)
> Registers: settings-001 / time-001 / weather-001 / disp-001 updates · X031–X033
> (reserved 2026-07-16; G2/G3 add no new interaction edge — formatting helpers are
> intra-render, no cross-feature state)
> Prior art: `M-SETTINGS-APP-WIRE.md` (2026-06, wired *per-app* settings to app behaviour).
> This doc is its sequel for the *global/system* settings that were left half-wired.

## 1. Context / pain points

A 2026-07-16 settings audit walked every field of `AppSettings` (`app/src/settingsStorage.h`)
through three checks: persisted (load/save), editable (Settings UI), and **consumed by a
downstream actor**. Persistence and UI are complete. Consumption is not — five settings are
edited, persisted, and then partially or entirely ignored at runtime:

| # | Setting(s) | Symptom | Root cause |
|---|-----------|---------|------------|
| G1 | `posixTz` | Timezone resets to UTC on every reboot; correct only after the user re-picks a city | Boot calls `configTime(0, 0, …)` (`app/src/main.cpp:2265`); the saved `posixTz` is applied only inside the city picker (`settings/timeSection.h:241`) |
| G2 | `fmt24h` | 12h/24h toggle does nothing | No consumer. All clock renderers hardcode 24h: `clockApp.h` (`%02d` on `tm_hour`, all 4 styles), weather TIME tile `strftime("%H:%M")` (`main.cpp:444`), aquarium clock overlay (`aquarium/aquariumApp.h:933`) |
| G3 | `dateFmt` | DMY/MDY/YMD cycle does nothing | No consumer. Both date render sites hardcode DMY (`clockApp.h:148`, `clockApp.h:352`) |
| G4 | `lat`, `lon` (+ `city` indirectly) | Weather always shows one hardcoded location regardless of the selected city | `WEATHER_URL` is a compile-time constant with `latitude=51.75&longitude=-0.47&timezone=Europe/London` baked in (`app/src/dataTaskStorage.cpp:121`). The city picker writes `g_settings.lat/lon` (`timeSection.h:239-240`) that nothing reads |
| G5 | `dispAuto`, `ldrLow`, `ldrHigh` | Auto-brightness only works while the Settings → Display screen is open; backlight freezes at the last duty on leaving; boot applies manual `dispLevel` even when `dispAuto=true` | The entire LDR sample + map + `ledcWrite` loop lives in `DisplaySection::tick()` (`settings/displaySection.h:24-42`), which only runs while that section is the active settings view. Boot path (`main.cpp:2127`) ignores `dispAuto` |

Common shape of all five: **the Settings section that edits the value is also the only actor
that applies it.** The correctly-wired settings (LED, stock, crypto, aquarium, matrix, life,
clock style, playerMode, teletext, webRadio, planeRadar) all have an applier *outside*
`settings/` — either a global flow object ticked from the main loop (`g_ledFlow`,
`main.cpp:2044`) or a pull-on-`resume()`/`init()` consumer in the owning app
(M-SETTINGS-APP-WIRE D1).

Out of scope (separate class of finding, not "broken wiring"; PM may file separately):

- WebRadio settings block (`country/autoplay/bitrateCap/autoSkip/hwMod/maxVolume`) has no
  on-device UI — serial `set` / spiffs push only. Consumption is correct.
- Stock ticker slot 8 consumed but not editable (Settings UI shows rows 0–6 only).
- `teletextCountry` / `teletextAutoAdvance` — documented reserved, intentionally dormant.

## 2. Goals

1. Every field in `AppSettings` that has a UI affordance visibly changes device behaviour,
   across reboot, with no re-visit to Settings required.
2. No new persistence schema — all five gaps are consumer-side; `settings.json` is untouched
   (zero migration).
3. Preserve the M-SETTINGS-APP-WIRE contracts: pull-on-resume for app-owned settings,
   snapshot-at-enqueue for dataTask-coupled settings.
4. Give VE a *whole-of-settings* conformance suite so this class of defect (edited-but-ignored,
   persisted-but-not-restored) is caught structurally, not by ad-hoc discovery (§6).

Non-goals: new UI surfaces (WebRadio settings page, 8th ticker row); 12h/24h support in the
Winamp skin surface (it has no wall-clock display); changing the weather provider.

## 3. Cross-cutting principle (→ ADR-050, drafted 2026-07-16)

> **A persisted setting must have an owner outside `settings/`.** Settings sections render
> and edit state; they never *own* runtime behaviour. Every `AppSettings` field needs a
> named applier that (a) applies the value at boot after `SettingsStorage::load()`, and
> (b) reacts to changes — either a global flow object ticked from the main loop
> (LedFlow pattern) or a pull-on-resume consumer (M-SETTINGS-APP-WIRE D1 pattern).

G1–G5 are exactly the five fields that violate this today. The rule is checkable (§6, T-SETW
static gate) and should be added to `NEW-APP-CHECKLIST.md` once accepted.

## 4. Per-gap design

### G1 — Timezone at boot → configTzTime with the loaded posixTz

Boot ordering is already correct: `SettingsStorage::load()` runs at `main.cpp:2119`, NTP
init at `main.cpp:2265`. Replace:

```cpp
configTime(0, 0, "pool.ntp.org", "time.google.com", "time.cloudflare.com");
```

with:

```cpp
configTzTime(g_settings.posixTz, "pool.ntp.org", "time.google.com", "time.cloudflare.com");
```

Fresh device: `applyDefaults()` seeds `posixTz = "UTC0"` → behaviour identical to today.
The 5 s bounded epoch wait below it is TZ-independent (`time()` is epoch-based) — no change.
The city picker's live `configTzTime()` call stays as the change-time applier.

Options considered: none worth enumerating — this is the one-line canonical fix. Risk:
`posixTz` from a corrupt file is a garbage string; `configTzTime` passes it to `setenv(TZ)`,
which glibc/newlib treats as UTC on parse failure — acceptable, matches today's fallback.

### G2 / G3 — Time & date formatting → one shared helper, renderers consume

Three render surfaces (clockApp × 4 styles, weather TIME tile, aquarium overlay) currently
format independently. Options:

- **(a) Each renderer reads `g_settings.fmt24h`/`dateFmt` inline.** No new file; 6 call
  sites re-implement the same hour-conversion and 3-way date switch. Drift-prone — exactly
  how G2/G3 happened.
- **(b) Shared header `app/src/util/timeFmt.h`** with three pure helpers:

```cpp
// hour respecting g_settings.fmt24h; 12h maps 0→12, 13→1 …
uint8_t     clockHour(const struct tm& t);
// "AM"/"PM" in 12h mode, nullptr in 24h mode (caller may omit)
const char* clockAmPm(const struct tm& t);
// dd/mm/yyyy | mm/dd/yyyy | yyyy/mm/dd per g_settings.dateFmt; sep configurable
void        fmtDate(const struct tm& t, char* buf, size_t len, char sep = '/');
```

**Lean: (b).** Header-only, no state, no tick — this is formatting, not a flow object; the
ADR-050 "owner" here is the renderer set, and the helper keeps them convergent.

Per-surface application:

| Surface | Change |
|---|---|
| clockApp Digital | `clockHour()` for the hour pair; AM/PM drawn small next to the minute block when non-null; `fmtDate()` for the date line (`:148`) |
| clockApp Flip / Nixie / VFD | Digit-pair styles: convert via `clockHour()` only. AM/PM indicator **omitted for v1** — these faces have no natural glyph slot; a 2-px indicator dot is a polish follow-up (OQ2). Date line at `:352` → `fmtDate(…, '-')` (keeps that style's existing `-` separator) |
| Weather TIME tile | Replace `strftime("%H:%M")` with `clockHour()`/minute + optional AM/PM at font-2 under the tile label |
| Aquarium overlay | `clockHour()` in the `snprintf` at `:933`; AM/PM omitted (10-px overlay, no room) — hour conversion alone is the user-visible contract |

12h hour rendering: no leading zero (`%d`, "9:41" not "09:41") in Digital/weather; digit-pair
styles keep two digits ("09") because the face is fixed-width — consistent with real flip
clocks.

### G4 — Weather coordinates → snapshot-at-enqueue from settings (enqueuePlaneRadar pattern)

`WEATHER_URL` becomes a format template; coordinates travel with the enqueue, mirroring
`enqueuePlaneRadar(float lat, float lon, …)` (`dataTask.h:217`) — snapshot into a
config slot under spinlock, URL built task-side at fetch time. Options:

- **(a) dataTask reads `g_settings.lat/lon` directly at fetch time.** Cross-core read of a
  non-atomic float pair mid-edit; violates the established snapshot discipline (ADR-045
  amendment lineage). Rejected.
- **(b) `enqueueWeather(float lat, float lon)`** — caller (WeatherApp `init()`/`resume()`
  and its stale-poll tick) passes `g_settings.lat/lon`. Snapshot under mux like
  `enqueueWebRadioStations()`'s country snapshot. **Lean.**

Fallback when no city was ever selected (`city == ""`, lat/lon = 0.0): keep today's
behaviour — the current hardcoded coordinates become `WX_DEFAULT_LAT/LON` compile
constants used iff `city[0] == '\0'`. (0,0 is a real location — Gulf of Guinea — so the
sentinel must be the empty city string, not the floats.)

URL details: `&timezone=Europe/London` is dropped — the app consumes only
`current=temperature_2m,relative_humidity_2m,wind_speed_10m`, none of which are
timezone-shaped. (If a daily forecast is ever added, use `timezone=auto`.)

Change-time application: WeatherApp `resume()` compares a lat/lon snapshot the same way
StockApp diffs tickers (`main.cpp:1080-1090`) and forces a refetch on mismatch, so
Settings → city change → return to Weather shows the new location without waiting out the
poll interval. Log the full fetch URL at LOG_D (WebRadio full-URL precedent) — VE hooks on it.

Polish option (cheap, recommended): WeatherApp chrome titles the TIME tile with
`g_settings.city` when set — gives the user visible confirmation the coordinate wiring works.

### G5 — Auto-brightness → global BacklightFlow (LedFlow pattern)

Move the LDR sample → map → `ledcWrite` loop out of `DisplaySection::tick()` into a global
flow object, exactly parallel to `g_ledFlow`:

```cpp
// app/src/backlightFlow.h — background backlight controller (ticked from main loop)
class BacklightFlow {
public:
    void applyMode();  // boot + on toggle: auto → sample once & map; manual → dispLevel duty
    void tick();       // 500 ms LDR cadence, ±20 ADC hysteresis, ≥3-duty-step write filter
                       //   (constants and mapping transcribed from displaySection.h:24-42)
    void pause();      // Settings/Display owns the backlight while previewing the slider
    void resume();     //   (mirrors g_ledFlow pause/resume, ledSection.h:117/122)
    int16_t ldrRaw() const;             // shared reading for the section's live LDR row
#ifdef SERIAL_DEBUG
    void injectLdr(int16_t raw);        // T-SETW harness: override the ADC (VE, §6)
#endif
};
extern BacklightFlow g_backlight;
```

- **Boot**: `main.cpp:2126-2129` block becomes `g_backlight.applyMode()` — honours
  `dispAuto` instead of unconditionally applying `dispLevel`.
- **Main loop**: `g_backlight.tick()` next to `g_ledFlow.tick()` (`main.cpp:2044`).
- **DisplaySection** becomes a pure editor: renders `g_backlight.ldrRaw()` in its LDR rows,
  calls `pause()/resume()` around manual-slider drags, `applyMode()` after toggling
  `dispAuto` or committing a slider value. Its `tick()` keeps only the row-repaint cadence.
- Cost: one `analogRead` (ADC1, GPIO34 — no WiFi/ADC2 conflict) per 500 ms in the main
  loop; duty writes already hysteresis-filtered. No flash writes.

Alternative considered: leave the loop in DisplaySection and *also* tick it globally —
rejected; two tickers, one owner ambiguity, and DisplaySection would still own hardware it
shouldn't (ADR-050 violation persists).

## 5. Lean / decision — summary

| Gap | Decision | Size |
|---|---|---|
| G1 | `configTzTime(g_settings.posixTz, …)` at boot | 1 line |
| G2+G3 | `util/timeFmt.h` helpers; 6 render sites consume | S |
| G4 | `enqueueWeather(lat, lon)` snapshot + resume-diff refetch + empty-city fallback | M |
| G5 | `BacklightFlow` global (LedFlow clone); DisplaySection demoted to editor | M |
| Principle | Candidate ADR-050 "settings must have an owner outside settings/" | doc |

Suggested implementation order: G1 (independent, ship immediately) → G5 → G2/G3 → G4.
No inter-gap dependencies; each is independently testable and committable.

## 6. VE — whole-of-settings validation

The audit found gaps no existing test family (T-SET/T-TIME/T-DISP/T-APPS) was shaped to
catch: those suites verify the *Settings UI* (rows render, taps cycle, values persist), not
that the persisted value *does* anything. VE to add a **T-SETW** (settings wiring) family to
`docs/verification/test_plan.md`, plus per-gap acceptance tests. VE challenges the following
before finalising (per protocol):

### 6a. Structural round-trip (host + DUT, automated)

- **T-SETW-01 — full-field round-trip.** Host generates a `settings.json` with a
  *non-default* value for every key (script-derived from `settingsStorage.cpp`'s save()
  key set), `run/spiffs push` → reboot → `run/spiffs pull settings.json` → key-by-key diff.
  Catches load/save asymmetry and silent key drops for every future field, not just today's.
- **T-SETW-02 — defaults matrix.** `run/spiffs rm settings.json` → reboot → pull → assert
  every key equals `applyDefaults()`. Catches divergence like the existing
  `applyDefaults()` (ldrLow=0/ldrHigh=120) vs `load()` fallbacks (`|200`/`|3800`,
  `settingsStorage.cpp:159-160`) — align these values as part of this work.

### 6b. Per-gap wiring acceptance (DUT, agent-driven)

- **T-SETW-10 (G1)**: push settings with `posixTz` = Asia/Tokyo rule → reboot → Clock app
  shows UTC+9 (compare against host clock via serial timestamp), *without* touching
  Settings. The reboot is the test — T-TIME-01 already covers live city-pick.
- **T-SETW-11 (G2)**: `set` fmt24h=false → Clock Digital shows 12h + AM/PM; weather TIME
  tile and aquarium overlay show converted hour. Repeat across all 4 clock styles
  (digit faces: hour pair converted, no AM/PM v1).
- **T-SETW-12 (G3)**: cycle dateFmt through MDY/YMD → date line reorders at both clockApp
  sites.
- **T-SETW-13 (G4)**: `set` city/lat/lon (new debug var or pushed file) → trigger weather
  fetch → assert LOG_D fetch URL carries the configured lat/lon; empty city → asserts
  `WX_DEFAULT_*`. Resume-diff: change coords while in another app → switch to Weather →
  refetch fires without waiting the poll interval.
- **T-SETW-14 (G5)**: needs the `injectLdr()` debug hook (§4-G5) since the harness cannot
  darken the room: inject low/high LDR values with `dispAuto=on` while **outside** Settings
  → `get` duty (new debug var) tracks the mapping; toggle `dispAuto=off` → duty pins to
  `dispLevel`. Reboot with `dispAuto=on` → boot duty derives from LDR, not `dispLevel`.
- **T-SETW-15 (regression)**: T-DISP/T-TIME/T-APPS existing suites re-run — DisplaySection
  demotion (G5) touches the screens they exercise.

### 6c. Static coverage gate (host, cheap, catches the *next* G-gap)

Small host script (`app/tools/check_settings_wiring.py`): parse `AppSettings` field names
from `settingsStorage.h`; assert each appears in (a) `load()`, (b) `save()`, and (c) ≥1
consumer file outside `app/src/settings/` + `settingsStorage.*` — with an explicit
allowlist for documented-reserved fields (`teletextCountry`, `teletextAutoAdvance`).
Wire as a warn-only step of `run/check` initially (cert-preflight precedent); promote to a
failing gate once green. This automates the audit that produced this document.

### 6d. Testability notes for VE challenge

- G2/G3 assertions are visual on DUT; propose `get clockRender` debug var emitting the
  formatted strings (hour/ampm/date) so the harness asserts text, not pixels — mirrors
  the `get wrStation` diagnosis pattern.
- G5's `injectLdr` must survive the 500 ms cadence (sticky override, cleared with
  `injectLdr -1`), else the next real sample immediately overwrites the injected value.

## 7. Feature inventory & cross-feature matrix

Asked explicitly by the operator: **do these artifacts help this work? Yes — and the audit
shows exactly where they were under-maintained:**

- **Diagnosis**: all five gaps are *missing edges* in `cross_feature_matrix.yaml`. The
  matrix's job is recording "feature A's behaviour depends on feature B's state" — that is
  literally what settings-consumption is. `settings-001 ↔ time-001` (TZ must be applied at
  boot, not just at edit), `settings-001 ↔ weather-001` (coords), `settings-001 ↔ disp-001`
  (backlight owner) were never entered, so no VE test was ever derived from them and the
  gaps sat invisible. X001 (time-001↔auth-001) proves the mechanism works when the edge is
  recorded.
- **Update 2026-07-16**: the three edges below are now RESERVED as X031 (tz-at-boot),
  X032 (weather coords), X033 (backlight owner) under the Architect design-time
  registry remit (architect.md responsibility 10) — Developer completes them at
  implementation instead of creating them.
- **Actions with this work** (Developer owns both files, updates on implementation):
  - `feature_inventory.yaml`: update `settings-001` (status/notes — G-gaps closed, T-SETW
    ids appended to `test_ids`), `time-001` (boot path now TZ-aware, files list gains
    nothing), `weather-001` (files gain `dataTask.h`, cross_features gains `settings-001`),
    new/updated entry for the backlight owner (either extend `disp-001` or a
    `backlight-001` entry pointing at `backlightFlow.h`).
  - `cross_feature_matrix.yaml`: add X-entries for the three edges above (risk: medium;
    `test_coverage`: the corresponding T-SETW ids), so the wiring stays visible to future
    QM audits.
- **Limit**: the inventory records *features*, keyed by intent — it cannot mechanically
  prove a struct field has a consumer. That is what the §6c static gate adds. The two are
  complementary: matrix = designed dependencies for humans/VE, static gate = mechanical
  floor for every field including future ones.

## 8. Open questions

- **OQ1 (G4)**: should the city picker's coordinates also feed PlaneRadar's location
  presets (offer "use Time&Location city" as a slot source)? Out of scope here; note for
  M-PR-LOCATIONS follow-up. Registered as cross-feature overlap **X030** (2026-07-16
  Architect pass) — three independent location stores (city lat/lon, prLocs,
  webRadioCountry) that can silently disagree; any fourth store goes through Architect.
- **OQ2 (G2)**: AM/PM affordance on the digit-face clock styles (Flip/Nixie/VFD) — v1 ships
  hour conversion only. Needs an eyeballed design (BP-048 gate) if pursued.
- **OQ3 (G5)**: LDR hysteresis constants (±20 ADC, ≥3 duty steps, 500 ms) were tuned inside
  the Settings screen where flicker is tolerable; a full-time controller may want slower
  cadence / stronger smoothing to avoid visible pumping during video-like content (VU
  meters). DUT eyeball during T-SETW-14.
- **OQ4** — RESOLVED 2026-07-16: standalone ADR-050 drafted (proposed), including the
  save-policy corollary (no RAM-drift fields; `webRadioLastStation` coalesces on
  suspend/eject). ADR-050 ACCEPTED 2026-07-16 (human sign-off).

## 9. Exit criteria

1. Reboot with a saved non-UTC city → Clock, Weather TIME tile, aquarium overlay all show
   local time with zero Settings interaction (G1).
2. `fmt24h=false` visibly changes every time-rendering surface; `dateFmt` reorders both
   date lines (G2/G3).
3. Weather reflects the selected city's coordinates; empty-city fallback preserves today's
   behaviour; URL visible at LOG_D (G4).
4. Auto-brightness tracks ambient light in any app and across reboot; manual mode
   unaffected; T-DISP suite still green (G5).
5. T-SETW-01/02 pass; T-SETW-10..15 pass on DUT; §6c gate green in `run/check` (warn-only).
6. `feature_inventory.yaml` + `cross_feature_matrix.yaml` updated per §7; candidate ADR-050
   submitted for human sign-off.
