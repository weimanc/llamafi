# M-MULTIAPP — Settings App Design

> Owner: Architect
> Status: draft (aesthetics TBD — pending preview pass)
> Date: 2026-05-23
> Part of: [overview.md](overview.md)
> See also: [taskbar.md](taskbar.md), [app-lifecycle.md](app-lifecycle.md), [layout.md](layout.md)

---

## Role

The Settings app is a configuration menu accessible from the multi-app shell. It presents five **tab sections** across the top of the canvas; tapping a tab switches the content panel below it. Tabs are navigational placeholders for now — content will be specified per-section in follow-up design passes.

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

Five equal-width tabs span the full canvas width:

| Tab | Label | Meaning | x range |
|-----|-------|---------|---------|
| 0 | `wifi` | Wi-Fi / network settings | 0..54 |
| 1 | `clk` | Clock / NTP / timezone | 55..109 |
| 2 | `loc` | Location (lat/lon for weather) | 110..164 |
| 3 | `cal` | Display calibration / brightness | 165..219 |
| 4 | `app` | Application-level settings | 220..274 |

Tab bar geometry:

```
x=0    x=55   x=110  x=165  x=220  x=275
+------+------+------+------+------+   y=0
| wifi |  clk |  loc |  cal |  app |   tab bar  h=28
+------+------+------+------+------+   y=28
|                                  |
|          content panel           |   h=212
|                                  |
+----------------------------------+   y=240
```

Pixel math: 5 × 55 = 275 ✓  
Tab bar + content = 28 + 212 = 240 ✓

**Tab label rendering** — use Winamp 5×6 bitmap glyphs from `SKIN_GLYPH` (same source as taskbar icons, baked from TEXT.BMP). Centre label in its 55×28 cell. Short label strings keep each glyph row legible at small sizes.

**Separator lines** — draw with `TASKBAR_SEP_COLOR` (same as taskbar) between tabs and between tab bar and content panel.

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

## App access — open question

The taskbar currently has exactly 6 slots (AppId 0–5, 40 px each × 6 = 240 px).
Settings must be accessible but doesn't need to occupy a permanent slot. Two options:

| Option | Mechanism | Taskbar impact |
|--------|-----------|----------------|
| **A** — Dedicated slot | Add Settings as AppId 6; slot height shrinks to 34 px (240/7); glyph stays 24×24 | Taskbar redesign needed; `TASKBAR_SLOT_COUNT=7` ripples to layout |
| **B** — Long-press | Long-press (≥600 ms) any taskbar cell launches Settings; short-tap switches app as normal | No taskbar geometry change; input dispatch gains press-duration logic |

Option B is lower-disruption for M-MULTIAPP. Resolve before filing implementation tasks.

---

## State struct

```cpp
struct SettingsAppState {
    uint8_t activeTab;   // 0..4
    bool    initialised;
};
```

No network fetches. No persistent writes yet — settings values are TBD per tab.

`activeTab` persists across app switches (user returns to the same tab they left).

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
#define SETTINGS_TAB_COUNT          5
#define SETTINGS_TAB_W             55    // canvas_w / TAB_COUNT = 275/5
#define SETTINGS_TAB_BAR_H         28
#define SETTINGS_CONTENT_Y         28
#define SETTINGS_CONTENT_H        212    // 240 - TAB_BAR_H

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

## Per-tab content (TBD — placeholders)

| Tab | ID | Content spec |
|-----|----|-------------|
| `wifi` | 0 | TBD |
| `clk` | 1 | TBD |
| `loc` | 2 | TBD |
| `cal` | 3 | TBD |
| `app` | 4 | TBD |

Each tab's content will be specified in a follow-up design pass. For now, `renderSettingsContent()` draws a blank panel with the tab index number centred (stub rendering for visual testing).

---

## Open questions

1. **App access mechanism** — slot 6 vs long-press. Resolve before implementation tasks filed. See §App access above.
2. **Tab label glyphs** — use `SKIN_GLYPH` bitmap chars or `tft.drawString` with a small font? SKIN_GLYPH chars are 5×6; at 1× scale they are very small in a 55×28 cell. `tft.drawString(..., 1)` (font 1, 8px) or font 2 may be more legible. Decide in preview pass.
3. **Per-tab content specs** — each of the five tabs is a stub. File separate design tasks as the settings surface is defined.
4. **Persistence** — settings values will eventually write to SPIFFS (`/settings.json` alongside `/spotify_diy_config.json`). Schema TBD once tab contents are defined.

---

## Exit criteria (draft — update once content is specified)

- **C1** — Tab bar renders within x:0..274, y:0..27. No pixel in taskbar strip (x≥275).
- **C2** — Tapping each tab updates `activeTab` and repaints the indicator. Five taps → five distinct states.
- **C3** — Content panel renders within x:0..274, y:28..239.
- **C4** — App switch: Spotify → Settings → Spotify. Winamp chrome pixel-correct after two `switchApp()` calls; no settings residue.
- **C5** — `activeTab` persists across switch-away / switch-back. User returns to the same tab.
