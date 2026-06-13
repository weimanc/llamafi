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
| **1 — Bug fix** | Fixed-position digit rendering in `drawDigital()` ✓ done 77de8d6 | Phase 0 not required; can ship independently |
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

> Partially approved. VFD date rendering signed off 2026-06-13.
> Time digit geometry and glyph designs still under iteration.

```python
# ── VFD date — APPROVED 2026-06-13 ───────────────────────────────────────────
# Font: Font1 (5×7 GLCD bitmap, exact TFT_eSPI Font1 bitmaps from dut_fonts.py)
# Rendering: each character on its own 5×7 dot grid; cells are 2×2 px; gaps 1 px
# Inter-char advance: CHAR_W (6) × DS (3) = 18 px per character (includes 1-dot spacing)
# Two lines centred on 275 px canvas, below time digits

VFD_DATE_DC           = 2        # date dot cell size (px)
VFD_DATE_DG           = 1        # date dot gap (px)
VFD_DATE_DS           = 3        # date stride DC+DG
VFD_DATE_FONT         = "Font1"  # 5×7 GLCD — exact TFT_eSPI Font1
VFD_DATE_BLOCK_TOP_Y  = 141      # DIGIT_TOP_Y(10) + DIGIT_H(119) + gap(12)
VFD_DATE_LINE_GAP     = 10       # px between day and date lines

# ── VFD time digits — PENDING sign-off ───────────────────────────────────────
# Geometry locked; glyph designs still under iteration.
VFD_TIME_TC           = 4        # time dot cell size (px)
VFD_TIME_TG           = 1        # time dot gap (px)
VFD_TIME_TS           = 5        # time stride TC+TG
VFD_TIME_T_COLS       = 13       # dot columns per digit
VFD_TIME_T_ROWS       = 24       # dot rows per digit
VFD_TIME_DIGIT_W      = 64       # px  (13×4 + 12×1)
VFD_TIME_DIGIT_H      = 119      # px  (24×4 + 23×1)
VFD_TIME_DIGIT_TOP_Y  = 10       # px from canvas top

# ── VFD bloom — PENDING sign-off ─────────────────────────────────────────────
VFD_BLOOM_R           = 4.0      # GaussianBlur radius (px)
VFD_BLOOM_SCALE       = 1.2      # additive bloom layer multiplier

# ── VFD palette — PENDING sign-off ───────────────────────────────────────────
VFD_BG                = (0,   5,  18)
VFD_C_ON              = (0, 210, 230)   # teal theme
VFD_C_OFF_FRAC        = 0.06           # off-dot brightness relative to C_ON
VFD_C_DATE_FRAC       = 0.68           # date brightness relative to C_ON
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

Classic VFD calculator / cassette deck display (think Pioneer stereo, Denon
deck). Dark navy background. Teal-green phosphor dot-matrix digits. All dots
visible at all times — active dots emit strongly, inactive dots show faint
ambient phosphor. Light from emitting dots bleeds softly onto neighbours:
adjacent active dots produce *stronger* combined glow at their shared boundary
(additive accumulation), not competing independent halos.

---

### Rendering model — the fundamental constraint

> **The display is a continuous rasterized phosphor surface, not a set of
> isolated glowing dots.** Every rendering decision follows from this.

The wrong approach (what the previous `_clock_vfd.py` did): draw each active
dot with its own per-dot glow halo. This creates halos that overwrite each
other, produces non-uniform brightness at adjacent active dots, and looks
artificial.

The correct approach: **rasterize first, blur second, composite additively.**

```
Frame render pipeline:

  Step 1 — Grid pass (rasterize)
    Allocate sharp_buf (RGBA or RGB, canvas size).
    Fill with C_BG.
    For every dot cell (col, row) in every digit:
      if active:  paint C_ON  flat rectangle  (no glow yet)
      if inactive: paint C_OFF flat rectangle
    → sharp_buf is a clean, sharp dot grid.  No glow.

  Step 2 — Bloom pass
    bloom_src = copy of sharp_buf
    bloom_layer = GaussianBlur(bloom_src, radius=BLOOM_R)
    bloom_layer = bloom_layer scaled by BLOOM_SCALE  (0.0 .. 1.0)

  Step 3 — Composite (additive)
    output = ImageChops.add(sharp_buf, bloom_layer)
    → bright clusters accumulate MORE glow than isolated dots  ✓
    → off-dot areas receive spill from adjacent on-dots        ✓
    → sharp dot cores remain visible above the bloom           ✓
```

**Why additive, not alpha-composite?**
Real phosphor emits light. Emission adds. `ImageChops.add` (capped at 255) is
the correct blend mode. Alpha-composite would darken the source; screen blend
is acceptable but add is cleaner for a dark-background emissive display.

**Why blur the whole grid, not just active dots?**
Off-dots are `C_OFF` (very dim). Their blur contribution is negligible (< 5
counts at the fringe). Blurring the full grid is simpler and slightly warmer —
even inactive dots emit a faint ambient glow, which is correct for phosphor.

**Tunable parameters** (to be approved in Phase 0 concept session):

| Param | Meaning | Start value |
|-------|---------|-------------|
| `BLOOM_R` | Gaussian blur radius (px) | 2.0 |
| `BLOOM_SCALE` | Bloom layer intensity (0..1) | 0.55 |
| `C_BG` | Background colour | `(0, 5, 18)` |
| `C_ON` | Active dot colour | `(0, 210, 230)` teal |
| `C_OFF` | Inactive dot colour | `(0, 35, 39)` dim teal |

The `g`/`G` keys in the concept tool control `BLOOM_SCALE`. A separate key
controls `BLOOM_R`. Approved values go into the Approved Constants block above.

---

### Dot-matrix geometry

Each digit is a 13-column × 24-row grid of 4×4 px dots with 1 px gaps.

```
TC = 4   (dot cell size, px)
TG = 1   (gap between dots, px)
TS = 5   (stride = TC + TG)

Digit width  = 13 × TC + 12 × TG = 52 + 12 = 64 px
Digit height = 24 × TC + 23 × TG = 96 + 23 = 119 px

Canvas layout (275 px):
  3 | H1(64) | H2(64) | colon-col(13) | M1(64) | M2(64) | 3
  3 + 64 + 64 + 13 + 64 + 64 + 3 = 275  ✓

Digit top y = 10 px.
```

Glyph content occupies an 11-col × 16-row inner region within each 13×24 cell:
- 1-dot left/right margin (col 0, col 12 = always off)
- 2-dot top/bottom margin (rows 0–1, rows 20–23 = always off, rows 16–19 = spacer)

The 10 digit glyphs (0–9) are defined as 11-col × 16-row bitmaps. See
`_clock_vfd.py` `_GLYPHS` for the current bitmaps; refine in Phase 0 as needed.

**Colon:** two 8×8 px filled dots centred in the 13-px colon column, at
y = DIGIT_TOP_Y + 32 and y = DIGIT_TOP_Y + 79. Blinks at 0.5 Hz with seconds.
Because the colon dots are large relative to the grid dots they are drawn as
plain rectangles into sharp_buf before the bloom pass — the blur will naturally
spread them.

**Date line:** two lines of Font1 (5×7 GLCD) rendered as 2×2 px dot cells at
3 px stride, centred below the digit block (y ≈ 141, 171). These are also
rasterised into sharp_buf before the bloom pass.

---

### Rendering implementation (host / PIL)

```python
from PIL import Image, ImageDraw, ImageChops, ImageFilter

def render(img, t):
    # Step 1 — sharp grid
    sharp = Image.new("RGB", (CANVAS_W, CANVAS_H), C_BG)
    d = ImageDraw.Draw(sharp)
    _rasterize_digits(d, t)   # paint all dot cells, no glow
    _rasterize_colon(d, t)
    _rasterize_date(d, t)

    # Step 2 — bloom
    bloom = sharp.filter(ImageFilter.GaussianBlur(radius=BLOOM_R))
    bloom = bloom.point(lambda x: min(255, int(x * BLOOM_SCALE)))

    # Step 3 — additive composite
    out = ImageChops.add(sharp, bloom)
    img.paste(out, (0, 0))
```

`_rasterize_digits` iterates each digit's 13×24 matrix and paints `C_ON` or
`C_OFF` rectangles — nothing else. No glow rectangles, no fringe, no halos.

---

### Firmware note (Phase 3)

TFT_eSPI has no Gaussian blur. Options for firmware VFD:

1. **Pre-bake glow**: for each of the 10 glyphs, pre-compute a `uint16_t[]`
   sprite (64×119) with the bloom already burned in. Store in flash, `pushImage`
   to screen. One sprite per digit, ~15 KB for all 10. Feasible with PSRAM.
2. **Approximate per-row halo**: after drawing the sharp grid, iterate only the
   rows adjacent to each active dot and paint a dim neighbour rectangle. One
   pass, O(rows × cols). Cheaper but less accurate.
3. **Accept no bloom**: ship the VFD style on firmware with sharp dots only
   (still authentic — some real VFDs have minimal bloom). The concept tool
   shows the ideal; firmware is a budget approximation.

Decision deferred to Phase 3. The concept tool (Phase 0) uses the full PIL
pipeline without compromise.

---

### Palette

```python
C_BG   = (0,   5,  18)   # dark navy
C_ON   = (0, 210, 230)   # bright teal
C_OFF  = (0,  35,  39)   # dim teal  (~17% of C_ON)
C_DATE = (0, 142, 156)   # date text (~68% of C_ON, slightly dimmer)
```

Four colour themes for concept exploration: teal (default), amber, blue, green.

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
