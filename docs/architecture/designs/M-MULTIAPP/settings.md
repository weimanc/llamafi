# M-MULTIAPP — Settings App Design

> Owner: Architect
> Status: draft (aesthetics TBD — pending preview pass; UX for value selection open)
> Date: 2026-05-25 (updated 2026-06-04 — SettingsApp class sketch + list-row pattern; 4-tab layout; Option A content distribution)
> Part of: [overview.md](overview.md)
> See also: [taskbar.md](taskbar.md), [app-lifecycle.md](app-lifecycle.md), [layout.md](layout.md), [stock.md](stock.md)

---

## Role

The Settings app is a configuration menu accessible from the multi-app shell. It presents four **tab sections** across the top of the canvas; tapping a tab switches the content panel below it.

The visual language inherits from the taskbar: same background tone, same separator style, same active-indicator idiom — so the shell feels coherent.

---

## Canvas

Settings uses the **full 275×240 left canvas** (same as Clock, Matrix, GoL). The Winamp chrome region is overwritten while Settings is active; it is restored on switch-away.

```
x=0                              x=274  x=275
+--------------------------------+      +------+
|  [ tab bar — full width, h=28 ]|      |      |
+--------------------------------+      | TASK |
|                                |      |  BAR |
|        content panel           |      |      |
|       275 × 212 px             |      |      |
|                                |      |      |
+--------------------------------+      +------+
                                  y=240
```

---

## Tab layout

Four tabs span the full canvas width:

| Tab | Label | Content | x range |
|-----|-------|---------|---------|
| 0 | `wifi` | Wi-Fi / network settings | 0..68 |
| 1 | `time` | Clock, NTP, timezone + weather location (lat/lon) | 69..137 |
| 2 | `cal` | Touch calibration | 138..206 |
| 3 | `app` | Per-app settings (secondary menu per app) | 207..274 |

Tab bar geometry:

```
x=0      x=69     x=138    x=207    x=275
+--------+--------+--------+--------+   y=0
|  wifi  |  time  |  cal   |  app   |   tab bar  h=28
+--------+--------+--------+--------+   y=28
|                                   |
|           content panel           |   h=212
|                                   |
+-----------------------------------+   y=240
```

Pixel math: 69 + 69 + 69 + 68 = 275 ✓ (tabs 0–2 = 69 px, tab 3 = 68 px)
Tab bar + content = 28 + 212 = 240 ✓

**Tab label rendering** — `tft.drawString` with font 2 (16px) centred in each cell.
Short 4-char labels fit cleanly at this width. SKIN_GLYPH (5×6) is too small at 1× scale.

**Separator lines** — draw with `TASKBAR_SEP_COLOR` (same as taskbar) between tabs and between tab bar and content panel.

### Content distribution — Option A

Clock and Weather configuration live in the tab whose label telegraphs the content
(`time`). They do **not** appear in the `app` tab. The `app` tab covers only apps
whose config has no natural home in the other three tabs.

| Tab | Configurable items |
|-----|--------------------|
| `wifi` | SSID, password status, DNS override toggle |
| `time` | Timezone, NTP server, 12/24h toggle, weather location (lat/lon) |
| `cal` | Touch calibration (X/Y offset + scale) |
| `app` | Secondary menus for: Stock, Crypto, Aquarium, Matrix, Life |

### `app` tab — menu of menus

The `app` tab renders a list of app names. Tapping an entry pushes into that
app's own row-list. Back returns to the app-name list.

```
+-----------------------------------+
|  Stock              >             |
|  Crypto             >             |
|  Aquarium           >             |
|  Matrix             >             |
|  Life               >             |
+-----------------------------------+
```

Navigation state added to `SettingsAppState`:

```cpp
struct SettingsAppState {
    uint8_t activeTab;       // 0..3
    int8_t  appSubmenu;      // -1 = app list; 0..N = index into app submenu list
    bool    initialised;
};
```

`handleInput()` for the `app` tab:
- `appSubmenu == -1` + row tap → set `appSubmenu = rowIdx`, repaint submenu
- `appSubmenu >= 0` + back zone (y < SETTINGS_CONTENT_Y + SETTINGS_ROW_HEADER_H) → set `appSubmenu = -1`, repaint app list

Per-app submenu content:

| App | Settings rows |
|-----|--------------|
| Stock | Tickers ×8 (cycle from predefined list), default view (list/chart/heatmap) |
| Crypto | Coins ×6 (cycle from predefined list), currency (USD/EUR) |
| Aquarium | Fish count (4/8/12/16), speed (slow/normal/fast) |
| Matrix | Color (green/white/amber), speed (slow/normal/fast) |
| Life | Speed (slow/normal/fast), color scheme (rainbow/mono) |

---

## Aesthetics — preview pass required

The three aesthetic choices below mirror the options explored for the taskbar active indicator. Run `preview_layout.py` in settings mode to compare them on-device before locking any values.

### Tab active-indicator options

**Option A — bottom-bar (recommended starting point)**

3 px bar on the *bottom* edge of the active tab cell. Mirrors the taskbar's `ACTIVE_STYLE='A'` left-bar, rotated 90°. Subtle, consistent with shell idiom.

```
 wifi    clk     loc     cal     app
+------+------+------+------+------+
|      |      |      |      |      |
|      |      |      |      |      |
+======+------+------+------+------+
  ^^^
  3 px bottom bar, TASKBAR_ACTIVE_COLOR (0x07E0, Spotify green)
```

**Option B — full-cell highlight**

Active tab cell filled with a lighter grey. High visibility; feels more "button-pressed".

```
 wifi    clk     loc     cal     app
+------+▓▓▓▓▓▓+------+------+------+
|      |▓ clk▓|      |      |      |
|      |▓▓▓▓▓▓|      |      |      |
+------+------+------+------+------+
  ▓▓▓ = SETTINGS_TAB_ACTIVE_BG (e.g. 0x4208 mid-grey or lighter)
```

**Option C — top-bar**

3 px bar on the *top* edge of the active tab. Same weight as A; top-anchored indicator reads as "open/selected" rather than "underlined".

```
 wifi    clk     loc     cal     app
+======+------+------+------+------+
|      |      |      |      |      |
| wifi |  clk |      |      |      |
+------+------+------+------+------+
  ^^^
  3 px top bar, TASKBAR_ACTIVE_COLOR
```

### Background and text tones

Start with taskbar values; adjust in preview:

| Constant | Candidate | Notes |
|----------|-----------|-------|
| `SETTINGS_BG_RGB565` | `0x2104` | Match taskbar background |
| `SETTINGS_TAB_ACTIVE_COLOR` | `0x07E0` | Match `TASKBAR_ACTIVE_COLOR` |
| `SETTINGS_SEP_COLOR` | `0x4208` | Match `TASKBAR_SEP_COLOR` |
| `SETTINGS_TAB_LABEL_COLOR` | `0xFFFF` | White for inactive |
| `SETTINGS_TAB_ACTIVE_LABEL` | `0x07E0` | Active label tinted green |

These are **draft candidates** — override via preview export before implementation.

### Preview tooling integration

Add a `--mode settings` (or `--settings`) flag to `preview_layout.py` that:

1. Renders the 275×240 canvas with the tab bar and a placeholder content panel.
2. Iterates active-indicator style (A / B / C) and active-tab colours with
   keyboard controls (same pattern as taskbar preview pass).
3. Exports approved values as `SETTINGS_*` defines appended to `gen/shell_layout.h`
   via the same `--export` path.

Until that pass runs, all `SETTINGS_*` defines in `gen/shell_layout.h` are
placeholders copied from the taskbar values above.

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
    void init()    override;           // load persisted activeTab from SPIFFS (default 0)
    void resume()  override { repaint(); }
    void suspend() override {}         // no inflight work to cancel
    void tick()    override {}         // purely reactive — no polling or async
    bool handleInput(TouchPhase phase, int x, int y) override;

private:
    struct State {
        uint8_t activeTab = 0;
    } _s;

    void repaint();                    // full canvas: repaintTabBar() + repaintContent()
    void repaintTabBar();
    void repaintContent();             // dispatches to per-tab method

    void repaintTabApp();              // tab 3 — app list or submenu
    void repaintTabAppList();          // app-name list (appSubmenu == -1)
    void repaintTabAppSubmenu();       // per-app row list (appSubmenu >= 0)
    // repaintTabWifi/Time/Cal: stub until per-tab design passes run

    void onTabTap(int tab);
    void onRowTap(int tab, int row);
};
```

**Lifecycle notes:**

- `tick()` is a no-op. Settings has no background fetches. Repaint happens on
  `resume()` and in response to tap events only.
- `init()` runs once at first `switchApp(AppId::Settings)`. Loads `activeTab`
  from SPIFFS if a `/settings.json` entry exists; otherwise stays at 0.
- `suspend()` is empty — no FreeRTOS tasks to cancel, no pending async.
- `hasPendingAsync()` not overridden (defaults `false`) — correct.

---

## State struct

```cpp
struct SettingsAppState {
    uint8_t activeTab;    // 0..3
    int8_t  appSubmenu;   // -1 = app list; 0..4 = index into app submenu list
    bool    initialised;
};
```

No network fetches. No persistent writes in this struct — settings values for each
app are persisted to SPIFFS separately on change.

`activeTab` persists across app switches (user returns to the same tab they left).
`appSubmenu` resets to -1 on suspend — user always re-enters the app list, not mid-submenu.

---

## Touch input

```cpp
void settingsHandleInput(SettingsAppState &s, TouchPoint p) {
    if (p.y < SETTINGS_TAB_BAR_H) {
        // Tab bar hit — identify slot
        int tab = p.x / SETTINGS_TAB_W;   // 0..4
        if (tab < SETTINGS_TAB_COUNT && tab != s.activeTab) {
            s.activeTab = tab;
            renderSettingsTabBar(s);
            renderSettingsContent(s);
        }
        return;
    }
    // Content-area taps: delegated to per-tab handler (TBD)
}
```

No Spotify-style drag zones. All taps are point hits.

---

## Constants (draft — pending preview pass)

```c
// Settings app geometry (to be added to gen/shell_layout.h after preview export)
#define SETTINGS_TAB_COUNT          4
#define SETTINGS_TAB_W             69    // tabs 0..2; tab 3 = 275 - 3*69 = 68
#define SETTINGS_TAB_BAR_H         28
#define SETTINGS_CONTENT_Y         28
#define SETTINGS_CONTENT_H        212    // 240 - TAB_BAR_H

// Inline helper — tab 3 is 1px narrower to reach exactly 275
// int tabW(int i) { return (i < 3) ? SETTINGS_TAB_W : 275 - 3 * SETTINGS_TAB_W; }

// Aesthetics — DRAFT, override via preview export
#define SETTINGS_BG_RGB565        0x2104
#define SETTINGS_TAB_ACTIVE_STYLE 'A'    // A=bottom-bar, B=fill, C=top-bar
#define SETTINGS_TAB_ACTIVE_COLOR 0x07E0
#define SETTINGS_SEP_COLOR        0x4208
#define SETTINGS_TAB_LABEL_COLOR  0xFFFF
#define SETTINGS_TAB_ACTIVE_LABEL 0x07E0
```

---

## Rendering

```cpp
void renderSettingsTabBar(SettingsAppState &s) {
    // Fill tab bar background
    tft.fillRect(0, 0, 275, SETTINGS_TAB_BAR_H, SETTINGS_BG_RGB565);

    for (int i = 0; i < SETTINGS_TAB_COUNT; i++) {
        int x0 = i * SETTINGS_TAB_W;

        // Separator line between tabs
        if (i > 0)
            tft.drawFastVLine(x0, 0, SETTINGS_TAB_BAR_H, SETTINGS_SEP_COLOR);

        // Tab label glyph (TBD — placeholder for now)
        uint16_t labelColor = (i == s.activeTab)
            ? SETTINGS_TAB_ACTIVE_LABEL : SETTINGS_TAB_LABEL_COLOR;
        // tft.drawString(tabLabels[i], x0 + SETTINGS_TAB_W/2, 14, 1); // centred

        // Active indicator (style A — bottom bar)
        if (i == s.activeTab)
            tft.fillRect(x0, SETTINGS_TAB_BAR_H - 3, SETTINGS_TAB_W, 3,
                         SETTINGS_TAB_ACTIVE_COLOR);
    }

    // Separator between tab bar and content
    tft.drawFastHLine(0, SETTINGS_TAB_BAR_H, 275, SETTINGS_SEP_COLOR);
}

void renderSettingsContent(SettingsAppState &s) {
    tft.fillRect(0, SETTINGS_CONTENT_Y, 275, SETTINGS_CONTENT_H, SETTINGS_BG_RGB565);
    // Tab-specific content: TBD per section
}
```

---

## Per-tab content

| Tab | ID | Content |
|-----|----|---------|
| `wifi` | 0 | WiFi scan + connect flow (see [wifi-settings.md](wifi-settings.md)) |
| `time` | 1 | Timezone, NTP server, 12/24h toggle, weather location (lat/lon) |
| `cal` | 2 | Touch calibration — launches `CalibrationFlow` (see [touch-calibration.md](touch-calibration.md)) |
| `app` | 3 | Secondary menus for: Stock, Crypto, Aquarium, Matrix, Life |

Each tab's content will be specified in a follow-up design pass. For now,
`renderSettingsContent()` draws a blank panel with the tab index centred
(stub rendering for visual testing).

### Per-app submenu content (tab 3)

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

Each settings tab that presents configurable items uses a **header + fixed-height
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
3. ~~**Tab count and content distribution**~~ — **resolved 2026-06-04**: 4 tabs (wifi/time/cal/app). Clock+location merged into `time`. Option A adopted — each tab owns its natural content; `app` tab is menu-of-menus for app-specific config.
4. **Tab label glyphs** — `tft.drawString` font 2 (16px) decided over SKIN_GLYPH (5×6 too small). Exact label strings: `wifi`, `time`, `cal`, `app`. Confirm legibility in preview pass.
5. **Pixel math** — tabs 0..2 = 69 px, tab 3 = 68 px (275 − 3×69). 1 px asymmetry on last tab — confirm acceptable in preview pass.
6. **Per-tab content specs** — `wifi`, `time`, `cal` tabs are stubs. File separate design tasks per tab as implementation proceeds.
7. **Persistence** — `/settings.json` on SPIFFS alongside `/spotify_diy_config.json`. Schema draft in §Per-tab content; finalise per tab as implemented.
8. **UX for value selection** — predefined cycle-on-tap (resistive touch friendly) chosen as default. Text entry deferred; not needed for any currently-planned setting.

---

## Exit criteria (draft — update once content is specified)

- **C1** — Tab bar renders within x:0..274, y:0..27. No pixel in taskbar strip (x≥275).
- **C2** — Tapping each tab updates `activeTab` and repaints the indicator. Five taps → five distinct states.
- **C3** — Content panel renders within x:0..274, y:28..239.
- **C4** — App switch: Spotify → Settings → Spotify. Winamp chrome pixel-correct after two `switchApp()` calls; no settings residue.
- **C5** — `activeTab` persists across switch-away / switch-back. User returns to the same tab.
