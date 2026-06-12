# M-CLOCK-STYLES — Clock style variants + MM position fix

> Owner: Architect  
> Status: design — not started  
> Date: 2026-06-12  
> Part of: [overview.md](M-MULTIAPP/overview.md)  
> See also: [clock.md](M-MULTIAPP/clock.md), [settings.md](M-MULTIAPP/settings.md), [M-SETTINGS-APP-WIRE.md](M-SETTINGS-APP-WIRE.md)

---

## Delivery phases

| Phase | What | Gating condition |
|-------|------|-----------------|
| **0 — Concept** | `preview_clock.py` host-side renderer; iterate all 4 styles interactively; record approved constants | Human sign-off: "looks right on screen" |
| **1 — Bug fix** | Fixed-position digit rendering in `drawDigital()` | Phase 0 not required; can ship independently |
| **2 — Storage + dispatch** | `ClockStyle` enum, `AppSettings.clockStyle`, style-dispatch shell in `ClockApp` | Phase 1 done |
| **3 — Renderers** | Implement Flip, Nixie, VFD using Phase 0 approved constants | Phase 0 sign-off + Phase 2 done |
| **4 — Settings wiring** | `appRegistry.h` configurable=1, `appsSection.h` Clock rows | Phase 2 done |
| **5 — VE** | T_CLK_01–14 | Phase 3 + 4 done |

---

## Phase 0 — Concept tool (`preview_clock.py`)

### Purpose

All colour values, glow radii, segment geometry, card dimensions, and flip
timing in this document are *initial proposals*. Phase 0 is the authoritative
design session: run `preview_clock.py`, iterate with keyboard shortcuts until
each style looks correct, and record the approved constants here before any
firmware is written.

This is the same pattern used for heatmap (`preview_heatmap.py`), vis atlas
(`preview_vis.py`), and layout (`preview_layout.py`). pygame + Pillow
iteration is an order of magnitude faster than reflash cycles for visual tuning.

### Tool specification

**File:** `app/tools/preview_clock.py`  
**Dependencies:** `pygame`, `Pillow`, `dut_fonts` (already in project venv)  
**Usage:**
```
python3 app/tools/preview_clock.py          # interactive
python3 app/tools/preview_clock.py --style flip   # start in flip style
python3 app/tools/preview_clock.py --screenshot gen/clock_concepts/   # dump PNGs
```

**Window geometry:** 320×240 (device pixels), default `--scale 3`.  
Taskbar strip rendered on the right (x=275..319) as in other preview tools —
gives honest impression of the available 275×240 canvas.

**Fake time:** seconds advance at real wall-clock rate so the colon blink and
flip animation run live. A `--freeze HH:MM:SS` flag stops time for screenshot
accuracy.

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `1`..`4` | Switch style (1=Digital, 2=Flip, 3=Nixie, 4=VFD) |
| `c` | (Nixie) cycle tube glow colour preset |
| `g` | (Nixie/VFD) step glow radius / intensity up |
| `G` | (Nixie/VFD) step glow radius / intensity down |
| `f` | (Flip) step animation speed faster |
| `F` | (Flip) step animation speed slower |
| `s` | (VFD) toggle active/inactive segment contrast |
| `b` | Cycle background darkness |
| `+` / `-` | Scale up / down (1–4) |
| `p` | Print current parameters as a Python dict (for pasting into design doc) |
| `S` | Save screenshot to `gen/clock_concepts/<style>_<timestamp>.png` |
| `q` | Quit |

### Concept session workflow

1. Run `preview_clock.py` with a colleague / async review.
2. For each style: tweak until "yes, that looks right."
3. Press `p` — copy the printed dict into the **Approved constants** section below.
4. Press `S` — screenshot goes to `gen/clock_concepts/`.
5. Human signs off on the screenshots; Phase 3 implementation begins using exactly those constants.

### Approved constants

> **Not yet filled in.** This section is populated during Phase 0.
> Delete the placeholder block and paste the `p`-key output here after sign-off.

```
# ── PLACEHOLDER — replace after Phase 0 sign-off ────────────────────────────
FLIP_CARD_W           = 46       # proposal only
FLIP_CARD_H           = 62
FLIP_ANIM_FRAME_MS    = 80
FLIP_BG               = 0x2945
FLIP_TEXT             = 0xFFF0
NIXIE_TUBE_W          = 52
NIXIE_TUBE_H          = 70
NIXIE_OUTER_GLOW      = 0x8000
NIXIE_INNER_GLOW      = 0xFC00
NIXIE_BORDER          = 0xFE60
VFD_BG                = 0x000C
VFD_SEG_ON            = 0x07FF
VFD_SEG_OFF           = 0x0290
# ─────────────────────────────────────────────────────────────────────────────
```

---

## Problem statement

### Bug — MM position jump on colon blink

`ClockApp::drawTime()` renders the time string as:

```cpp
snprintf(tBuf, …, (t.tm_sec % 2 == 0) ? "%02d:%02d" : "%02d %02d",
         t.tm_hour, t.tm_min);
tft.setTextDatum(MC_DATUM);
tft.drawString(tBuf, 137, 45, 6);
```

`MC_DATUM` centres the full string. In TFT_eSPI font 6 the colon `:` and the
ASCII space ` ` have different pixel widths, so the centred string shifts
horizontally on every tick — the MM digits appear to jump left/right each second.

### Enhancement — single style feels limited

The clock is a primary use-case app (it's the device's screen saver equivalent).
Three additional styles are proposed: Flip Clock, Nixie Tube, VFD.

---

## Fix — fixed-position digit rendering

Draw HH, colon, and MM as independent strings at anchored x positions instead of
one centred composite string.

```
Canvas centre x = 137
Half-colon gap  =   8  px  (half the width of ":" in font 6, measured ~16 px)

HH: MR_DATUM  x = 129   → digits right-edge at x=129, never moves
:   MC_DATUM  x = 137   → drawn white or erased black to blink
MM: ML_DATUM  x = 145   → digits left-edge at x=145, never moves
```

Implementation (replaces current `drawTime()`):

```cpp
void drawDigital() {
    struct tm t;
    if (!getLocalTime(&t)) return;
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    char hBuf[4], mBuf[4];
    snprintf(hBuf, sizeof(hBuf), "%02d", t.tm_hour);
    snprintf(mBuf, sizeof(mBuf), "%02d", t.tm_min);

    tft.setTextDatum(MR_DATUM);
    tft.drawString(hBuf, 129, 45, 6);

    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(
        (t.tm_sec % 2 == 0) ? TFT_WHITE : TFT_BLACK,
        TFT_BLACK);
    tft.drawString(":", 137, 45, 6);

    tft.setTextDatum(ML_DATUM);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    tft.drawString(mBuf, 145, 45, 6);

    tft.setTextDatum(TL_DATUM);
}
```

Colon x=137 may need ±2 px tuning on DUT; measure with `tft.textWidth(":", 6) / 2`.

---

## Style system

### `ClockStyle` enum (add to `settingsStorage.h`)

```cpp
enum class ClockStyle : uint8_t { Digital = 0, Flip = 1, Nixie = 2, VFD = 3 };
```

Add to `AppSettings`:

```cpp
ClockStyle clockStyle;   // after lifeColors field
```

Default in `SettingsStorage::load()`:

```cpp
if (!doc.containsKey("clockStyle")) g_settings.clockStyle = ClockStyle::Digital;
else g_settings.clockStyle = (ClockStyle)(uint8_t)doc["clockStyle"];
```

Save: `doc["clockStyle"] = (uint8_t)g_settings.clockStyle;`

### Dispatch in `ClockApp`

```cpp
void drawTime() {
    switch (g_settings.clockStyle) {
        case ClockStyle::Flip:  drawFlip();   break;
        case ClockStyle::Nixie: drawNixie();  break;
        case ClockStyle::VFD:   drawVFD();    break;
        default:                drawDigital();
    }
}
```

---

## Style 0 — Digital (current, with fix)

See Fix section above. Box chrome and seconds bar unchanged.

Palette: `TFT_BLACK` bg, `TFT_WHITE` digits, `0xF81F` pink box, `0x07FF` cyan box, `0xFFE0` yellow box.

---

## Style 1 — Flip Clock

### Visual concept

Mechanical split-flap display. Each digit rendered as two rectangular "cards"
(top half, bottom half) with a thin dark gap at the split line. On digit change the
outgoing card rotates "over" the incoming card via a 5-frame animation.

### Layout

The time box is repurposed (no box border in this style). Two digit groups
(HH and MM) with a static colon spacer.

```
Canvas:   x: 0..274,  y: 5..85  (80 px)
Cards per digit: w=46 px, h=62 px (top=30 px + gap=2 px + bottom=30 px)
Digit positions (left edge):
  H1: x=10   H2: x=60   colon: x=110   M1: x=130   M2: x=180
  (colon = two 5×5 dots at y=25 and y=55, static)
All four cards centred vertically: top-of-card y = (80-62)/2 + 5 = 14
```

Digit occupies 10..56, 60..106, 130..176, 180..226 — total span 10..226, centred in 275 px.

### Per-digit state (`FlipDigit` struct)

```cpp
struct FlipDigit {
    uint8_t  shown;     // currently displayed digit (0..9)
    uint8_t  next;      // digit to flip to
    uint8_t  frame;     // 0 = stable; 1..5 = animating
};
FlipDigit _fd[4];       // H1, H2, M1, M2
```

### Frame rendering

Split line at y = card_top + 30 + 1 (the 2 px gap).

| frame | top card height | bottom card height | content |
|-------|----------------|-------------------|---------|
| 0     | 30 px (full)   | 30 px (full)       | `shown` on both halves |
| 1     | 22 px          | 30 px              | `shown` top, `shown` bottom |
| 2     | 14 px          | 30 px              | `shown` top (squished), `next` bottom |
| 3     | 7 px           | 30 px              | `shown` top (squished), `next` bottom |
| 4     | 30 px          | 22 px              | `next` top, `next` bottom (squished) |
| 5 → 0 | (stable)       |                    | advance `shown = next`, `frame = 0` |

"Squished" = same digit drawn clipped to the reduced rect height (TFT `setClipRect`
or manual `fillRect` + redraw).

Top card background: `0x2945` (warm dark brown).  
Bottom card background: `0x18C3` (slightly darker for depth illusion).  
Text: `0xFFF0` (warm cream white), `MC_DATUM` centred on each half.  
Gap line: `TFT_BLACK` 2 px.  
Card border: 1 px `0x4208` grey.

Use font 4 (not font 6) for the digit — font 6 is too tall for the 30 px half-card.

### Sub-second tick

The flip animation needs ~100 ms granularity. The existing 1 000 ms gate is too slow.

```cpp
void tick() override {
    unsigned long now   = millis();
    bool anyFlipping    = _anyFlipActive();
    unsigned long gate  = anyFlipping ? 100 : 1000;
    if (now - s_lastTickMs < gate) return;
    s_lastTickMs = now;
    drawTime();
    if (!anyFlipping) {
        drawSecondsBar();
        drawDate();
        drawRssi();
    }
}
```

`_anyFlipActive()` returns true if any `_fd[i].frame > 0`.

When `drawFlip()` detects a digit change, it sets `fd.next = newDigit` and `fd.frame = 1`.
Each call to `drawFlip()` advances each active `fd.frame` by 1, renders the frame, and
clears `fd.frame` back to 0 when it reaches 5.

### Colon (flip style)

Two filled squares `5×5` at fixed positions — static, no blink:

```cpp
tft.fillRect(118, 26, 5, 5, 0xFFF0);
tft.fillRect(118, 50, 5, 5, 0xFFF0);
```

---

## Style 2 — Nixie Tube

### Visual concept

Vacuum-tube Nixie display. Each digit lives inside an oval "tube" with a warm
orange/amber glow. Background black. No seconds box chrome; small dot arc instead.

### Layout

Four tubes + colon dots, all inside the time box area (y:5..85).

```
Tube dimensions: w=52 px, h=70 px, corner radius 26 (oval-ish)
Tube positions (left edge, top y = (80-70)/2 + 5 = 10):
  H1: x=6    H2: x=62   colon gap: x=118  M1: x=128  M2: x=184
Total span: 6..236, centred in 275 px
```

### Per-tube rendering

```
1. Black fill inside tube rect             (erase)
2. Outer glow: drawRoundRect at offset ±2, colour 0x8000 (dim red-orange)
3. Inner glow: drawRoundRect at offset ±1, colour 0xFC00 (orange)
4. Tube border: drawRoundRect,             colour 0xFE60 (amber yellow)
5. Digit: MC_DATUM font 4, colour 0xFFFF (white), centred in tube
6. Subtle pin shadows: two 1×4 px dark rects at tube bottom
```

Colon: two 4×4 filled squares at x=119..122 (tube gap centre), y=28 and y=50.
Colour: `0xFE60` (amber). No blink — Nixie tubes do not blink.

Seconds indicator: 60 small dots in an arc below the tube row (y=82, r=3 px),
drawn within seconds box area. Lit dots: `0xFC60`. Unlit: `0x4000`.

### Chrome

No box borders in this style. Background: `TFT_BLACK`.
Date box and seconds box borders suppressed; date text and seconds dot arc render directly.

---

## Style 3 — VFD (Vacuum Fluorescent Display)

### Visual concept

Classic VFD calculator / cassette deck display. Dark navy background,
teal-green 7-segment digits with visible inactive segments.

### Palette

```cpp
constexpr uint16_t VFD_BG        = 0x000C;  // very dark navy
constexpr uint16_t VFD_SEG_ON    = 0x07FF;  // bright teal (full segment)
constexpr uint16_t VFD_SEG_GLOW  = 0x03DF;  // mid teal (segment body)
constexpr uint16_t VFD_SEG_OFF   = 0x0290;  // dark teal (inactive segment)
```

### 7-segment geometry

Each segment character occupies a 40×60 px cell.

```
Segment layout (classic 7-seg):
   aaa
  f   b
  f   b
   ggg
  e   c
  e   c
   ddd

a: (x+5, y+2,  w=30, h=5)   top horizontal
b: (x+35, y+5, w=5,  h=24)  top-right vertical
c: (x+35, y+31,w=5,  h=24)  bot-right vertical
d: (x+5, y+53, w=30, h=5)   bot horizontal
e: (x+0, y+31, w=5,  h=24)  bot-left vertical
f: (x+0, y+5,  w=5,  h=24)  top-left vertical
g: (x+5, y+27, w=30, h=5)   middle horizontal

SEGMENTS_ON[10] = bitmask per digit (0..9):
  0: a b c d e f     = 0b0111111
  1:     b c         = 0b0000110
  2: a b   d e   g   = 0b1011011
  3: a b c d     g   = 0b1001111
  4:   b c   f g     = 0b1100110
  5: a   c d f   g   = 0b1101101
  6: a   c d e f g   = 0b1111101
  7: a b c           = 0b0000111
  8: a b c d e f g   = 0b1111111
  9: a b c d f   g   = 0b1101111
```

Draw each segment: if bit set → `VFD_SEG_ON` fill + 1 px centre highlight (`VFD_SEG_GLOW`);
if bit clear → `VFD_SEG_OFF` fill.

### Layout

```
Digit cell 40×60. Positions (left x, top y=10 inside time box area):
  H1: x=10   H2: x=54   colon: x=98   M1: x=108  M2: x=152
Total span: 10..192; slight left-of-centre (intentional retro asymmetry)
```

Colon: two 5×5 filled squares in `VFD_SEG_ON` at x=100, y=24 and y=44.

Seconds strip (replaces coloured bar): 60 dots, 3 px dia, across y=82.
Lit: `VFD_SEG_ON`. Unlit: `VFD_SEG_OFF`. No coloured rainbow — green only.

Background fill on `repaint()`: `tft.fillRect(0, 0, TASKBAR_X, 240, VFD_BG)`.

---

## Settings wiring

### `appRegistry.h` change

```
APP_X( Clock,     'C',   1 )   // was 0
```

Re-run `gen_app_registry.py` → regenerates `gen/configurable_apps.h`
(adds `{ "Clock", AppId::Clock }` entry).

### `appsSection.h` additions

Add cases in `_repaintAppRows()` and `_handleAppTap()`:

```cpp
case AppId::Clock:    _repaintClock();    break;
case AppId::Clock:    _cycleClock(row);   break;
```

```cpp
void _repaintClock() {
    static const char* kS[] = { "digital","flip","nixie","vfd" };
    uint8_t cs = (uint8_t)settings().clockStyle % 4;
    drawRow(S_CONTENT_Y, { "Style", kS[cs], S_LABEL, S_VALUE });
}

void _cycleClock(int row) {
    if (row != 0) return;
    settings().clockStyle =
        (ClockStyle)(((uint8_t)settings().clockStyle + 1) % 4);
    saveSettings();
    repaint();
}
```

---

## Repaint on style change

`ClockApp::resume()` already calls `repaint()`. The settings save triggers a repaint
the next time the user navigates back to the Clock app via taskbar tap (`switchApp`).
No explicit callback needed — pull-on-resume model matches M-SETTINGS-APP-WIRE.

---

## RAM budget

No new static allocations:
- `FlipDigit _fd[4]` — 12 bytes, class member
- VFD segment table — 10 bytes, `static const` in `.rodata`
- Nixie/VFD have no per-pixel caches (paint on the fly)

---

## Open questions

None.

---

## Exit criteria

| ID | Criterion |
|----|-----------|
| C1 | MM stays at the same x position across 10 colon blink cycles (±2 px, DUT measure) |
| C2 | Settings > Applications > Clock shows "Style" row cycling Digital→Flip→Nixie→VFD→Digital on tap |
| C3 | Style persists across app switch and power cycle (read back from `settings.json`) |
| C4 | Flip: animation completes in ≤500 ms; no pixel residue outside card rects |
| C5 | Nixie: all four tubes render within time box (y:5..85); no glyph overflow |
| C6 | VFD: all active segments render in `VFD_SEG_ON`; inactive segments visible in `VFD_SEG_OFF` |
| C7 | Non-Flip styles: tick gate remains 1 000 ms (`_anyFlipActive()` returns false) |
| C8 | App switch Spotify → Clock → Spotify: no residual clock pixels in Winamp canvas |
