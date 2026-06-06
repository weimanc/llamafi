# M-MULTIAPP — Settings App Design

> Owner: Architect
> Status: draft
> Date: 2026-05-25 (updated 2026-06-04 — class sketch; list-row pattern; list-navigation model replacing tab bar; updated 2026-06-06 — OQ4/OQ5 resolved; C8 persistence EC added; implementation audit 2026-06-06; cancel button design added 2026-06-06)
> Part of: [overview.md](overview.md)
> See also: [taskbar.md](taskbar.md), [app-lifecycle.md](app-lifecycle.md), [layout.md](layout.md), [stock.md](stock.md)

---

## Role

The Settings app is a configuration menu accessible from the multi-app shell.
It presents a **vertical category list** at the top level. Tapping a category
pushes into that category's settings rows. Back returns to the category list.

Navigation model: category list → section rows → (Applications only) per-app rows.
Maximum depth: 3 levels. All levels use the list-row rendering pattern.

---

## Canvas

Settings uses the **full 275×240 left canvas** (same as Clock, Matrix, GoL). The Winamp chrome region is overwritten while Settings is active; it is restored on switch-away.

```
x=0                              x=274  x=275
+--------------------------------+      +------+
|  header bar  (h=28)            |      |      |
+--------------------------------+      | TASK |
|                                |      |  BAR |
|        list area               |      |      |
|       275 × 212 px             |      |      |
|                                |      |      |
+--------------------------------+      +------+
                                  y=240
```

Header bar (y=0..27): shows `"< back"` on the left (returns to category list
or previous app) and the current view title on the right. Background
`SETTINGS_BG_RGB565`. Separator line at y=27.

---

## Category list

The top-level view is a vertical list of six category rows plus a Cancel row.
Category rows have a label on the left and a `>` chevron on the right indicating
they navigate deeper. The Cancel row has no chevron and uses a distinct muted red
colour to signal destructive intent.

```
+-----------------------------------+
|  ⚙  Settings                     |   header (h=28) — back = exit (keep changes)
+-----------------------------------+
|  WiFi              >              |
|  Time & Location   >              |
|  Touch Calibration >              |
|  Display           >              |
|  LED               >              |
|  Applications      >              |
|  ─────────────────────────────── |   separator (1 px, S_SEP colour)
|  Cancel                           |   muted red — discard all changes + exit
+-----------------------------------+
```

6 category rows × 26px = 156px. Separator (1px) + Cancel row (26px) = 183px total.
Remaining 29px is dark fill — fits within 212px content panel.

**Back (`< back`) from category list:** exits to `g_previousAppId` with all changes
saved (same as current behaviour — "keep changes and leave").

**Cancel row:** discards all changes made during this Settings session and exits.

| Index | Category label | Section doc |
|-------|---------------|-------------|
| 0 | WiFi | [wifi-settings.md](wifi-settings.md) |
| 1 | Time & Location | [time-settings.md](time-settings.md) |
| 2 | Touch Calibration | [touch-calibration.md](touch-calibration.md) |
| 3 | Display | [display-settings.md](display-settings.md) |
| 4 | LED | [led-settings.md](led-settings.md) |
| 5 | Applications | (submenu — see below) |

Tapping a row sets `_s.section = rowIdx` and renders that section's view.
The header `< back` zone (x < 60, y < 28) returns to the category list
(`_s.section = -1`) or, when already at the category list, calls
`switchApp(g_previousAppId)`.

### Applications section — menu of menus

Applications is the only section with a second level of depth.

**Level 1 — app list (`_s.appSubmenu == -1`):**

```
+-----------------------------------+
|  <  Applications                  |
+-----------------------------------+
|  Stock             >              |
|  Crypto            >              |
|  Aquarium          >              |
|  Matrix            >              |
|  Life              >              |
+-----------------------------------+
```

**Level 2 — per-app settings (`_s.appSubmenu >= 0`):**

```
+-----------------------------------+
|  <  Stock                         |
+-----------------------------------+
|  Ticker 1          AAPL           |
|  Ticker 2          AMD            |
|  ...                              |
|  Default view      list           |
+-----------------------------------+
```

| App | Settings rows |
|-----|--------------|
| Stock | Tickers ×8 (cycle from predefined list), default view (list/chart/heatmap) |
| Crypto | Coins ×6 (cycle from predefined list), currency (USD/EUR) |
| Aquarium | Fish count (4/8/12/16), speed (slow/normal/fast) |
| Matrix | Colour (green/white/amber), speed (slow/normal/fast) |
| Life | Speed (slow/normal/fast), colour scheme (rainbow/mono) |

---

## App access — resolved (2026-05-25)

Settings occupies **AppId slot 6** — a dedicated gear icon in the taskbar.
Long-press was considered (Option B below) but rejected: discoverability on a
device with no screen labels is poor.

Taskbar cell height stays **40 px** (6 visible slots × 40 px = 240 px). Settings at
slot 6 is reached by scrolling the taskbar strip (see [taskbar.md §Scroll model](taskbar.md)
and M-TASKBAR-SCROLL in `roadmap.md`). No geometry change to the taskbar is required.

```
  visible at scrollOffset=0:        visible at scrollOffset=1:
  y=0   |  [S]  | Spotify  ← 0     y=0   |  [C]  | Clock    ← 1
  y=40  |  [C]  | Clock    ← 1     y=40  |  [W]  | Weather  ← 2
  y=80  |  [W]  | Weather  ← 2     y=80  |  [€]  | Crypto   ← 3
  y=120 |  [€]  | Crypto   ← 3     y=120 |  [M]  | Matrix   ← 4
  y=160 |  [M]  | Matrix   ← 4     y=160 |  [G]  | Life     ← 5
  y=200 |  [G]  | Life     ← 5     y=200 |  [⚙]  | Settings ← 6
```

Impact on taskbar.md: none — `TASKBAR_SLOT_H = 40` and slot rendering loop already
parameterised for `scrollOffset` per M-TASKBAR-SCROLL design. Hit-test resolves
`appIdx = (scrollOffset + slot) % totalApps`.

Impact on `gen/shell_layout.h`: `TASKBAR_SLOT_COUNT` must reflect visible slots (6);
`AppId::COUNT` grows from 6 → 7 when Settings is registered.

Gear glyph for slot 6: Winamp TEXT.BMP may not contain a gear symbol. If absent,
use a nearest-available Winamp glyph as placeholder until a custom 24×24 px
bitmap is baked into the skin atlas.

---

## previousAppId

Settings must return to the app the user came from, not default to Spotify.

Add to `appShell.h`:

```cpp
AppId g_previousAppId = AppId::Spotify;   // fallback if Settings opened first
```

In `switchApp()`, before updating `currentAppId`:

```cpp
if (next == AppId::Settings) {
    g_previousAppId = currentAppId;
}
```

Settings' back action (tapping gear again, or a designated touch zone) calls
`switchApp(g_previousAppId)`.

---

## Keyboard is a widget, not an AppId

If text input is needed (e.g. entering a custom stock ticker), an on-screen
keyboard is rendered as a **widget owned by SettingsApp**, not as a separate
AppId entry. A `KeyboardWidget` would:

- Render in the full 275×240 app canvas while active.
- Receive touch events forwarded by `SettingsApp::handleInput()`.
- Callback with the completed string, then be dismissed.

It does NOT appear in the App enum, the taskbar, or `switchApp()`.

**Caution:** the CYD touch panel is resistive. Small QWERTY keys have high
fat-finger error rates. A predefined scrollable list is preferred for ticker
and city selection. See §Open questions and [stock.md](stock.md) for UX options.

---

## SettingsApp class sketch

`SettingsApp` subclasses `App` directly (no shared base class — see ADR-039).

```cpp
class SettingsApp : public App {
public:
    void init()    override;      // one-time setup; no persisted state needed
    void resume()  override { _snapshot = g_settings; repaint(); }
    void suspend() override { _s.section = -1; _s.appSubmenu = -1; }
    void tick()    override;      // delegates to active flow (wifi/cal) when running
    bool handleInput(TouchPhase phase, int x, int y) override;

private:
    struct State {
        int8_t section   = -1;   // -1 = category list; 0..5 = section index
        int8_t appSubmenu = -1;  // -1 = app list; ≥0 = per-app rows (section 5 only)
    } _s;

    AppSettings _snapshot;   // g_settings captured on resume(); restored by cancel()

    void repaint();
    void repaintHeader(const char* title);
    void repaintCategoryList();
    void repaintSection();             // dispatches on _s.section
    void repaintSectionApps();
    void repaintSectionAppSubmenu();
    // wifi, cal, disp sections delegate to their respective Flow objects

    void onCategoryTap(int idx);
    void onRowTap(int row);
    void goBack();
    void cancel();           // restore snapshot + save + exit
};
```

**Lifecycle notes:**

- `resume()` snapshots `g_settings` into `_snapshot` before any sections run.
- `suspend()` resets to category list — user always re-enters at the top level.
- `tick()` delegates to `g_wifiFlow` / `g_calFlow` when those are active
  (they need ticking for scan spinner / connecting spinner).
- All other sections are purely reactive; `tick()` is a no-op for them.
- `hasPendingAsync()` not overridden (defaults `false`) — correct.

---

## State struct

```cpp
struct SettingsAppState {
    int8_t section    = -1;   // -1 = category list; 0..5 = section index
    int8_t appSubmenu = -1;   // used only when section == 5 (Applications)
};
```

No network fetches. No persistent writes in this struct — individual section
values are persisted to SPIFFS by their respective storage helpers on change.

State resets to `{-1, -1}` on `suspend()` — user always re-enters at the
category list, never mid-submenu.

---

## Touch input

All taps are point hits — no drag zones.

```cpp
bool SettingsApp::handleInput(TouchPhase phase, int x, int y) {
    if (phase != TouchPhase::Release) return false;

    // Header back zone (x < 60, y < 28)
    if (y < SETTINGS_HEADER_H && x < 60) { goBack(); return true; }

    // List area row index
    int row = (y - SETTINGS_HEADER_H) / SETTINGS_ROW_H;
    if (row < 0) return false;

    if (_s.section == -1) {
        // Cancel row is one row below the 6 category rows (after 1px separator)
        int cancelRowTop = SETTINGS_CONTENT_Y + SETTINGS_CAT_COUNT * SETTINGS_ROW_H + 1;
        if (y >= cancelRowTop && y < cancelRowTop + SETTINGS_ROW_H) {
            cancel();
            return true;
        }
        onCategoryTap(row);   // category list
    } else {
        onRowTap(row);        // section content or app submenu
    }
    return true;
}

void SettingsApp::goBack() {
    if (_s.appSubmenu >= 0)  { _s.appSubmenu = -1; repaintSectionApps(); }
    else if (_s.section >= 0){ _s.section    = -1; repaintCategoryList(); }
    else                       switchApp(g_previousAppId);  // exits — keeps all saved changes
}

void SettingsApp::cancel() {
    g_settings = _snapshot;    // restore all AppSettings to state at resume()
    saveSettings();            // write the restored values back to SPIFFS
    switchApp(g_previousAppId);
}
```

---

## Constants

```c
// Settings app geometry
#define SETTINGS_HEADER_H          28    // header bar height (same as taskbar)
#define SETTINGS_CONTENT_Y         28
#define SETTINGS_CONTENT_H        212    // 240 - HEADER_H
#define SETTINGS_CAT_COUNT          6    // number of top-level categories

// Colours
#define SETTINGS_BG_RGB565        0x2104
#define SETTINGS_SEP_COLOR        0x4208
#define SETTINGS_HEADER_COLOR     0xFFFF
#define SETTINGS_CAT_COLOR        0xFFFF  // category label colour
#define SETTINGS_CHEVRON_COLOR    0x4208  // > glyph colour
#define SETTINGS_CANCEL_COLOR     0xC8A0  // muted red — RGB565 ~(199,17,0)
```

---

## Rendering

```cpp
void SettingsApp::repaintHeader(const char* title) {
    tft.fillRect(0, 0, 275, SETTINGS_HEADER_H, SETTINGS_BG_RGB565);
    tft.setTextDatum(ML_DATUM);
    tft.setTextColor(SETTINGS_HEADER_COLOR);
    tft.drawString("< back", 4, 14, 2);
    tft.setTextDatum(MR_DATUM);
    tft.drawString(title, 271, 14, 2);
    tft.drawFastHLine(0, SETTINGS_HEADER_H - 1, 275, SETTINGS_SEP_COLOR);
    tft.setTextDatum(TL_DATUM);
}

void SettingsApp::repaintCategoryList() {
    static const char* kLabels[] = {
        "WiFi", "Time & Location", "Touch Calibration",
        "Display", "LED", "Applications"
    };
    repaintHeader("Settings");
    tft.fillRect(0, SETTINGS_CONTENT_Y, 275, SETTINGS_CONTENT_H, SETTINGS_BG_RGB565);
    for (int i = 0; i < SETTINGS_CAT_COUNT; i++) {
        int y = SETTINGS_CONTENT_Y + i * SETTINGS_ROW_H;
        int mid = y + SETTINGS_ROW_H / 2;
        tft.setTextDatum(ML_DATUM);
        tft.setTextColor(SETTINGS_CAT_COLOR);
        tft.drawString(kLabels[i], SETTINGS_ROW_COL_LABEL, mid, 2);
        tft.setTextDatum(MR_DATUM);
        tft.setTextColor(SETTINGS_CHEVRON_COLOR);
        tft.drawString(">", SETTINGS_ROW_COL_VALUE, mid, 2);
    }
    // Separator + Cancel row
    int sepY    = SETTINGS_CONTENT_Y + SETTINGS_CAT_COUNT * SETTINGS_ROW_H;
    int cancelY = sepY + 1;
    int cancelMid = cancelY + SETTINGS_ROW_H / 2;
    tft.drawFastHLine(0, sepY, 275, SETTINGS_SEP_COLOR);
    tft.setTextDatum(ML_DATUM);
    tft.setTextColor(SETTINGS_CANCEL_COLOR);
    tft.drawString("Cancel", SETTINGS_ROW_COL_LABEL, cancelMid, 2);
    tft.setTextDatum(TL_DATUM);
}
```

---

## Cancel — discard all changes

### Semantics

All sections currently call `saveSettings()` immediately on each change (live
persistence). Cancel does not intercept those writes — it works by **restoring a
snapshot** taken at `resume()` time and writing that snapshot back to SPIFFS.

```
User enters Settings → resume() snapshots g_settings
  → makes changes (each calls saveSettings() live)
  → taps Cancel
      → g_settings = _snapshot
      → saveSettings()           ← writes original values back
      → switchApp(g_previousAppId)
```

**Net effect:** SPIFFS ends up with the values that were there before Settings was
opened. Sections see `g_settings` restored the next time they `enter()`.

### What is and is not covered

| Area | Covered by cancel? | Notes |
|------|--------------------|-------|
| LED mode/HSV, display brightness | ✅ yes | Part of `AppSettings` struct |
| Clock format, date format, city/timezone | ✅ yes | Part of `AppSettings` struct |
| App preferences (Stock, Crypto, etc.) | ✅ yes | Part of `AppSettings` struct |
| WiFi Phase 1 (read-only) | ✅ yes (no-op) | Phase 1 makes no writes |
| Touch calibration (`/cal.json`) | ❌ excluded | CalibrationFlow has its own Accept/Cancel; a completed calibration is deliberate. Cancel from Settings does not undo it. |
| WiFi Phase 2 (connect/NVS) | ❌ TBD | Phase 2 not yet designed; its cancel semantics are a Phase 2 concern |

### UX contract

- `< back` from the category list **keeps all changes** and exits (same as today).
- Tapping **Cancel** from the category list **discards all changes** and exits.
- Cancel is only reachable from the category list — not from inside any section.
  Users must navigate back to the category list first.
- There is no confirmation dialog — the resistive-touch tap target is small and
  distinct enough that accidental taps are unlikely.

---

## Per-section content

| Section | Index | Content |
|---------|-------|---------|
| WiFi | 0 | WiFi scan + connect flow (see [wifi-settings.md](wifi-settings.md)) |
| Time & Location | 1 | City/location, timezone (auto-DST), 12/24h, date format (see [time-settings.md](time-settings.md)) |
| Touch Calibration | 2 | 4-corner calibration — launches `CalibrationFlow` (see [touch-calibration.md](touch-calibration.md)) |
| Display | 3 | Screen brightness, LDR auto-brightness (see [display-settings.md](display-settings.md)) |
| LED | 4 | RGB LED mode, colour, brightness (see [led-settings.md](led-settings.md)) |
| Applications | 5 | Secondary menus for: Stock, Crypto, Aquarium, Matrix, Life |

### Per-app submenu content (Applications section)

| App | Settings rows |
|-----|--------------|
| Stock | Tickers ×8 (cycle from predefined list), default view (list/chart/heatmap) |
| Crypto | Coins ×6 (cycle from predefined list), currency (USD/EUR) |
| Aquarium | Fish count (4/8/12/16), speed (slow/normal/fast) |
| Matrix | Color (green/white/amber), speed (slow/normal/fast) |
| Life | Speed (slow/normal/fast), color scheme (rainbow/mono) |

Persistence: each app's values written to SPIFFS on change under `/settings.json`.
Example schema:

```json
{
  "stockTickers": ["AAPL", "AMD", "AMZN", "ARM", "GOOG", "META", "MSFT", "NVDA"],
  "stockMode":    "list",
  "cryptoCoins":  ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"],
  "cryptoCcy":    "USD",
  "aquariumFish": 8,
  "aquariumSpeed": "normal",
  "matrixColor":  "green",
  "matrixSpeed":  "normal",
  "lifeSpeed":    "normal",
  "lifeColors":   "rainbow"
}
```

---

## List-row content pattern

Each settings section that presents configurable items uses a **header + fixed-height
rows** layout. The pattern is structurally identical to `StockApp::repaintList()`
but adapted for 2-column label/value pairs with interactive cycling.

No shared base class is extracted — see ADR-039 for the rationale.

### Row data model

```cpp
struct SettingsRow {
    const char* label;        // left column — setting name
    const char* value;        // right column — current value string
    uint16_t    labelColor;   // usually SETTINGS_LABEL_COLOR
    uint16_t    valueColor;   // changes per state: ON/OFF/neutral
};
```

### Row renderer

```cpp
static void drawSettingsRows(const SettingsRow* rows, int count,
                             const char* header = nullptr) {
    int y = SETTINGS_CONTENT_Y;

    // Optional section header line
    if (header) {
        tft.setTextDatum(TL_DATUM);
        tft.setTextColor(SETTINGS_HEADER_COLOR);
        tft.drawString(header, SETTINGS_ROW_COL_LABEL, y + 4, 2);
        tft.drawFastHLine(SETTINGS_ROW_COL_LABEL,
                          y + SETTINGS_ROW_HEADER_H - 1,
                          274 - SETTINGS_ROW_COL_LABEL, SETTINGS_SEP_COLOR);
        y += SETTINGS_ROW_HEADER_H;
    }

    for (int i = 0; i < count; i++) {
        int mid = y + SETTINGS_ROW_H / 2;
        tft.setTextDatum(ML_DATUM);
        tft.setTextColor(rows[i].labelColor);
        tft.drawString(rows[i].label, SETTINGS_ROW_COL_LABEL, mid, 2);
        tft.setTextDatum(MR_DATUM);
        tft.setTextColor(rows[i].valueColor);
        tft.drawString(rows[i].value, SETTINGS_ROW_COL_VALUE, mid, 2);
        y += SETTINGS_ROW_H;
    }
    tft.setTextDatum(TL_DATUM);
}
```

### Touch — row index from y

```cpp
// Inside onRowTap() / content-area branch of handleInput():
int firstRowY = SETTINGS_CONTENT_Y + (header ? SETTINGS_ROW_HEADER_H : 0);
int rowIdx    = (y - firstRowY) / SETTINGS_ROW_H;
if (rowIdx < 0 || rowIdx >= count) return false;
// cycle the value at rowIdx, re-render that row
```

### Geometry constants (append to `gen/shell_layout.h` after preview export)

```c
#define SETTINGS_ROW_H              26     // matches ST_LIST_ROW_H in StockApp
#define SETTINGS_ROW_HEADER_H       22     // tab section header height
#define SETTINGS_ROW_COL_LABEL       8     // left edge of label text
#define SETTINGS_ROW_COL_VALUE     268     // right-aligned terminus
#define SETTINGS_ROW_MAX             8     // max rows visible in 212px panel (212/26)
```

### Colour constants

```c
#define SETTINGS_LABEL_COLOR      0xFFFF   // white
#define SETTINGS_HEADER_COLOR     0xFFE0   // yellow — section header text
#define SETTINGS_VALUE_COLOR      0x07FF   // cyan — neutral value
#define SETTINGS_VALUE_ON         0x07E0   // green — enabled / active
#define SETTINGS_VALUE_OFF        0x7BEF   // grey — disabled / inactive
```

### Comparison with StockApp list

| Aspect | StockApp list | SettingsApp rows |
|--------|--------------|-----------------|
| Columns | 3 (symbol / price / pct) | 2 (label / value) |
| Alignment | L / L / R | L / R |
| Content type | Read-only fetched data | Interactive — cycle on tap |
| Tap action | Drill to chart sub-view | Cycle value in place |
| Row height | 26 px (`ST_LIST_ROW_H`) | 26 px (`SETTINGS_ROW_H`) |
| Section header | Title + rule above rows | Optional per-section header |

Row height is a shared convention (26 px), not enforced by a base class.

---

## Open questions

1. ~~**App access mechanism**~~ — **resolved 2026-05-25**: slot 6, taskbar scrolls (40 px cells preserved, M-TASKBAR-SCROLL).
2. ~~**Shared base class with StockApp list view**~~ — **resolved 2026-06-04**: no base class. See ADR-039.
3. ~~**Navigation model**~~ — **resolved 2026-06-04**: vertical category list (6 entries), no tab bar. `section` index drives content panel. Tab-based model rejected.
4. ~~**Persistence**~~ — **resolved 2026-06-06.** `/settings.json` on SPIFFS
   alongside `/spotify_diy_config.json`. Schema finalised per section: LED
   fields in [led-settings.md §Persistence schema](led-settings.md); cal values
   in `/cal.json` (separate file per [touch-calibration.md §Storage](touch-calibration.md));
   all other section values (display, app prefs) under `/settings.json`.
5. ~~**UX for value selection**~~ — **resolved 2026-06-06.** Cycle-on-tap
   confirmed for all enum/list values (resistive-touch friendly). `KeyboardWidget`
   used only where free text is unavoidable: WiFi password, custom ticker/coin entry.
6. **Category list scroll** — 6 entries × 26 px = 156 px; fits within 212 px content panel. No scroll needed at current count. If entries grow beyond 8 (208 px), add scroll arrows.

---

## Exit criteria

- **C1** — Category list renders 6 rows within y:28..239 (content panel). No pixel overflows into taskbar strip (x≥275).
- **C2** — Tapping each category row opens the correct section; header shows the category name; back chevron (`< back`) returns to category list.
- **C3** — Content panel renders within x:0..274, y:28..239 for all sections.
- **C4** — App switch: Spotify → Settings → Spotify. Winamp chrome pixel-correct after two `switchApp()` calls; no settings residue.
- **C5** — `suspend()` resets `section=-1`, `appSubmenu=-1`; returning to Settings always lands on the category list.
- **C6** — Applications section: tapping an app name opens its per-app row list; back returns to Applications list; back again returns to category list.
- **C7** — `WifiFlow` and `CalibrationFlow` take over full content panel when active; returning from them via back restores the parent section.
- **C8** — All settings values (LED mode/HSV, display brightness, app prefs) survive `ESP.restart()`; loaded from `/settings.json` at boot before first `tick()` runs.
- **C9** — Cancel row visible in category list with `SETTINGS_CANCEL_COLOR`. Tapping it restores all `AppSettings` to the values present when Settings was entered, writes them to SPIFFS, and returns to the previous app. Calibration data (`/cal.json`) is unaffected.
- **C10** — `< back` from the category list exits without restoring the snapshot; all in-session changes are kept.

---

## Implementation Status (audit 2026-06-06)

| Area | Status | Notes |
|------|--------|-------|
| Category list (6 rows, colours, geometry) | ✅ DONE | |
| SettingsSection base class + storage | ✅ DONE | |
| All 6 sections wired (`_sections[]`) | ✅ DONE | |
| C5 — `suspend()` resets to category list | ✅ DONE | `appSubmenu` reset delegated to `AppsSection::leave()`; functionally equivalent |
| C6 — Applications 3-level navigation | ✅ DONE | |
| C8 — persistence survives restart | ✅ DONE | |
| C9 — Cancel button (snapshot-restore) | ❌ NOT IMPLEMENTED | Designed 2026-06-06 |
| C10 — back keeps changes | ❌ NOT IMPLEMENTED | Dependent on C9 |
| Stock tickers: 8 stored, 7 displayed | ⚠ DIVERGED | `stockTickers[7]` (NVDA) stored and saved but invisible in Settings UI; loop is `i < 7`. Spec says ×8. Silent overflow resolution for `S_MAX_ROWS=8`. |
| Applications submenu row order | ⚠ DIVERGED | Spec: Stock/Crypto/Aquarium/Matrix/Life. Impl (`configurable_apps.h`): Crypto/Matrix/Life/Stock/Aquarium |
| `g_previousAppId` placement | ⚠ DIVERGED | Spec says `appShell.h`. Impl: `static` in `main.cpp` only; not accessible to other TUs |
| `State.appSubmenu` field | ⚠ DIVERGED | Not in `SettingsApp::_s`; tracked as `AppsSection::_sub` |
