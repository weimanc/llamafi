# Design — Touch Calibration Flow

> Owner: Architect
> Status: draft
> Date: 2026-06-04 (updated 2026-06-05 — full class sketch; constants; rendering sketches; SettingsApp integration; resolved OQ1/OQ2/OQ3; active()/stepping() split; header overlap fix)
> Part of: M-MULTIAPP Settings (`cal` tab)
> See also: [settings.md](settings.md), [upstream-patches.md](upstream-patches.md)

---

## Context / pain points

The CYD28 uses a resistive XPT2046 touch controller. Calibration is currently
baked in as compile-time `#define` constants in the upstream library:

```c
// CYD28_TouchscreenR.h  (upstream — do not edit without a named patch)
#define CYD28_TouchR_CAL_XMIN 185
#define CYD28_TouchR_CAL_XMAX 3700
#define CYD28_TouchR_CAL_YMIN 280
#define CYD28_TouchR_CAL_YMAX 3850
```

`convertRawXY()` (private) references these directly. There is no runtime
override path. Every unit that drifts from these values ships with a mis-mapped
touch surface and can only be corrected by reflashing.

---

## Goals

1. 4-corner calibration flow accessible from Settings → `cal` tab.
2. Visual target crosshairs guide the user to each corner.
3. Live feedback shows where the tap actually landed vs the target.
4. Previous calibration summary visible before starting (and in history view).
5. Up to 3 historical calibration sessions stored in SPIFFS.
6. Computed calibration applied at runtime without reflash.
7. Values survive reboot (loaded from SPIFFS on boot).

---

## Integration prerequisite — PATCH-002

`convertRawXY()` must accept runtime values. Required change to upstream:

**`CYD28_TouchscreenR.h`** — add public setter + private runtime fields:

```cpp
// New public method
void setCalibration(int16_t xMin, int16_t xMax,
                    int16_t yMin, int16_t yMax) {
    _calXMin = xMin; _calXMax = xMax;
    _calYMin = yMin; _calYMax = yMax;
}

// New private members (initialised to compile-time defaults)
private:
    int16_t _calXMin = CYD28_TouchR_CAL_XMIN;
    int16_t _calXMax = CYD28_TouchR_CAL_XMAX;
    int16_t _calYMin = CYD28_TouchR_CAL_YMIN;
    int16_t _calYMax = CYD28_TouchR_CAL_YMAX;
```

**`CYD28_TouchscreenR.cpp`** — replace all `CYD28_TouchR_CAL_*` references in
`convertRawXY()` with the corresponding `_cal*` member.

This is a backward-compatible patch: if `setCalibration()` is never called,
the `#define` defaults remain in effect. Document as PATCH-002 in
`upstream-patches.md`.

Boot sequence addition in `main.cpp::setup()`:

```cpp
// After ts.begin() + ts.setRotation():
TouchCalStorage::load();   // loads /cal.json into g_calData
if (g_calData.valid)
    ts.setCalibration(g_calData.xMin, g_calData.xMax,
                      g_calData.yMin, g_calData.yMax);
```

---

## Architecture — CalibrationFlow as a SettingsApp component

Calibration is **not** a separate `AppId`. It is a full-canvas component owned
by `SettingsApp`, activated when the user enters the Touch Calibration category.
Pattern follows the "keyboard is a widget" precedent from
[settings.md §Keyboard is a widget](settings.md).

When `_calFlow.active()` is true, `SettingsApp::tick()` and
`SettingsApp::handleInput()` fully delegate to `_calFlow`. The taskbar is still
rendered; only the 275×240 left canvas is taken over.

`SettingsApp` holds `CalibrationFlow _calFlow;` and `int16_t _lastCalZ = 0;`
as members.

---

## CalibrationFlow class sketch

```cpp
enum class CalStep : uint8_t { Idle, TL, TR, BR, BL, Review, Saving };

struct CalibrationFlowState {
    CalStep  step      = CalStep::Idle;
    int16_t  rawX[4], rawY[4];   // measured raw values — corners TL=0..BL=3
    uint8_t  tapsDone  = 0;      // 0..4
    bool     sanityFailed = false;
    TouchCalData pending;        // computed values waiting for Accept
};

class CalibrationFlow {
public:
    // Called by SettingsApp::onCategoryTap(2) — enters the cal section, shows Idle view.
    void start();

    // True whenever the cal section owns the screen (including Idle).
    // SettingsApp delegates handleInput() here while active().
    bool active() const { return _open; }

    // True only while collecting corner taps (STEP_TL..STEP_BL).
    // SettingsApp::tick() uses this — not active() — to guard the raw poll.
    bool stepping() const {
        return _s.step >= CalStep::TL && _s.step <= CalStep::BL;
    }

    // Called every tick by SettingsApp::tick() when active().
    // Handles the Saving state (writes to SPIFFS, then resets).
    void tick();

    // Scaled touch input — Idle and Review button taps.
    // Returns true if the event was consumed.
    bool handleInput(TouchPhase phase, int scaledX, int scaledY);

    // Raw XPT2046 input — STEP_* states only.
    // Called from SettingsApp::tick() via ts.getPointRaw() when stepping().
    // Accumulates samples while pressed; latches averaged values on Release.
    // Returns true when a tap is recorded (step advances).
    bool handleInputRaw(TouchPhase phase, int16_t rawX, int16_t rawY);

private:
    CalibrationFlowState _s;
    bool    _open    = false;  // true from start() until reset()

    // Running-average accumulators for raw tap (OQ5)
    int32_t _rawSumX = 0, _rawSumY = 0;
    int16_t _rawCount = 0;

    // Rendering
    void repaintIdle();
    void repaintStep();     // renders current corner target + completed dots
    void repaintReview();
    void repaintHeader(const char* title);
    void drawCrosshair(int x, int y, uint16_t color);
    void drawTapMarker(int cornerIdx);  // expected dot + actual dot + offset vector

    // Logic
    bool computeCalibration();  // fills _s.pending; returns false on sanity fail
    void doSave();              // writes _s.pending to TouchCalStorage + g_calData
    void reset();               // clears _open + _s; called on cancel or post-save
};
```

---

## Canvas

Full 275×240 left canvas, same as other full-screen apps. Taskbar strip
(x ≥ 275) untouched.

```
x=0                              x=274  x=275
+--------------------------------+      +------+
|  [status bar — step / title ]  |      |      |
+--------------------------------+      | TASK |
|                                |      |  BAR |
|   calibration content area     |      |      |
|   275 × 212 px                 |      |      |
|                                |      |      |
+--------------------------------+      +------+
                                  y=240
```

Status bar (y=0..27, h=28) mirrors Settings tab bar height — shows current step
label and a `< back` / `cancel` zone on the left.

---

## State machine

```
IDLE ──tap "Start"──► STEP_TL
                           │
                        (tap)
                           ▼
                       STEP_TR
                           │
                        (tap)
                           ▼
                       STEP_BR
                           │
                        (tap)
                           ▼
                       STEP_BL
                           │
                        (tap)
                           ▼
                        REVIEW ──"Accept"──► SAVING ──► IDLE (updated)
                           │
                        "Retry"──► STEP_TL
                           │
                        "Cancel"──► IDLE (unchanged)
```

`IDLE` also reachable from any step via the `< back` zone in the status bar
(cancels without saving).

---

## Target geometry

Targets are inset 20 px from each edge to ensure the crosshair is fully visible
and reliably tappable on resistive touch:

| Step | Corner | Screen target (px) |
|------|--------|--------------------|
| STEP_TL | Top-left     | (20, 48)  — below status bar |
| STEP_TR | Top-right    | (255, 48) |
| STEP_BR | Bottom-right | (255, 220) |
| STEP_BL | Bottom-left  | (20, 220) |

```c
#define CAL_INSET_X   20
#define CAL_INSET_Y   48    // status bar h=28 + 20px margin
#define CAL_TARGET_W  (274 - 2 * CAL_INSET_X)   // 234
#define CAL_TARGET_H  (239 - CAL_INSET_Y - 20)  // 171
```

Crosshair: 24 px horizontal arm + 24 px vertical arm, centre dot 4×4 px.
Color: `0x07E0` (Spotify green) for the active target; `0x4208` for completed
dots (greyed).

---

## Constants

```c
// Geometry
#define CAL_HEADER_H        28     // mirrors SETTINGS_HEADER_H
#define CAL_CONTENT_Y       28
#define CAL_INSET_X         20
#define CAL_INSET_Y         48     // CAL_HEADER_H + 20 px margin
#define CAL_CROSSHAIR_ARM   24     // arm half-length (px)
#define CAL_Z_THRESHOLD    400     // raw Z pressure threshold — tap vs lift

// Review-state button geometry (bottom of content area)
#define CAL_BTN_Y          210     // vertical centre of button row
#define CAL_BTN_H           26
#define CAL_BTN_W           78
#define CAL_BTN_ACCEPT_X     4     // left-edge x for Accept box
#define CAL_BTN_RETRY_X     95     // left-edge x for Retry box
#define CAL_BTN_CANCEL_X   186     // left-edge x for Cancel box

// Colours
#define CAL_BG_COLOR          0x2104  // same as SETTINGS_BG_RGB565
#define CAL_SEP_COLOR         0x4208
#define CAL_HEADER_COLOR      0xFFFF
#define CAL_SECTION_COLOR     0xFFE0  // yellow — section headers
#define CAL_VALUE_COLOR       0x07FF  // cyan — calibration values
#define CAL_DIM_COLOR         0x7BEF  // grey — source / history labels
#define CAL_CROSSHAIR_ACTIVE  0x07E0  // Spotify green — active target
#define CAL_CROSSHAIR_DONE    0x4208  // grey — completed corner dot
#define CAL_MARKER_OK         0x07E0  // actual tap ≤4 px from expected
#define CAL_MARKER_NEAR       0xFFE0  // 4–8 px offset
#define CAL_MARKER_FAR        0xF800  // >8 px offset
#define CAL_BTN_COLOR         0x07E0  // button label colour
#define CAL_ERROR_COLOR       0xF800  // sanity-fail error text
```

---

## SettingsApp integration

Two separate input paths keep scaled and raw coordinate spaces clean:

| State | Input path | Guard | Called from |
|-------|-----------|-------|-------------|
| Idle, Review | `handleInput(phase, scaledX, scaledY)` | `active()` | `SettingsApp::handleInput()` |
| STEP_TL..STEP_BL | `handleInputRaw(phase, rawX, rawY)` | `stepping()` | `SettingsApp::tick()` |

`_calFlow.start()` is called from `SettingsApp::onCategoryTap(2)` (the Touch
Calibration row). It sets `_open = true` and renders the Idle view.

### SettingsApp::tick() delegation

```cpp
void SettingsApp::tick() {
    if (_calFlow.active()) {
        _calFlow.tick();  // handles Saving state

        // Raw poll — only during corner-tap steps
        if (_calFlow.stepping()) {
            CYD28_TS_Point raw = ts.getPointRaw();
            bool pressed    = (raw.z > CAL_Z_THRESHOLD);
            bool wasPressed = (_lastCalZ > CAL_Z_THRESHOLD);
            _lastCalZ = raw.z;

            TouchPhase phase = pressed    ? TouchPhase::Press
                             : wasPressed ? TouchPhase::Release
                             :              TouchPhase::None;
            if (phase != TouchPhase::None)
                _calFlow.handleInputRaw(phase, raw.x, raw.y);
        }
    }
}
```

`ts.getPointRaw()` is available in the existing driver without PATCH-002.
`besttwoavg()` averaging is not available on the raw path; `handleInputRaw()`
accumulates samples while pressed and latches the average on Release.

### SettingsApp::handleInput() delegation

```cpp
bool SettingsApp::handleInput(TouchPhase phase, int x, int y) {
    if (_calFlow.active())
        return _calFlow.handleInput(phase, x, y);
    // ... existing category-list / section dispatch
}
```

`CalibrationFlow::handleInput()` returns `false` when step is `TL..BL` —
those taps are handled exclusively by the raw path. Idle and Review consume
their button taps and return `true`.

---

## Live feedback — tap landing marker

After each corner tap, render:
- A filled circle (r=4) at the **expected** target position (green).
- A filled circle (r=4) at the **actual** tap position as mapped by the current
  calibration (red if offset > 8 px, yellow if 4–8 px, green if ≤ 4 px).
- A short line connecting expected → actual (offset vector).
- Raw ADC values printed in small text below the marker: `x:2041 y:1920`.

This gives the user immediate visual evidence of how far the current cal is off
before the new values are computed.

---

## Algorithm — 4-corner linear calibration

Rotation = 1 (LANDSC0). In this rotation, `convertRawXY` maps:
- `rawX → screenX` (left-right axis)
- `rawY → screenY` (top-bottom axis)

From the 4 measured raw samples and known target screen positions, solve a
2-point linear fit per axis, extrapolated to the screen edges:

```
Let:
  rx_L = (raw_TL.x + raw_BL.x) / 2   // average raw X for left-side taps
  rx_R = (raw_TR.x + raw_BR.x) / 2   // average raw X for right-side taps
  ry_T = (raw_TL.y + raw_TR.y) / 2   // average raw Y for top-side taps
  ry_B = (raw_BL.y + raw_BR.y) / 2   // average raw Y for bottom-side taps

  // Extrapolate to screen edges (accounting for CAL_INSET):
  float xSlope = (rx_R - rx_L) / (float)(275 - 2 * CAL_INSET_X)
  float ySlope = (ry_B - ry_T) / (float)(240 - CAL_INSET_Y - 20)

  xMin_new = (int16_t)(rx_L - CAL_INSET_X * xSlope)
  xMax_new = (int16_t)(rx_R + CAL_INSET_X * xSlope)
  yMin_new = (int16_t)(ry_T - 20 * ySlope)          // 20 = bottom inset
  yMax_new = (int16_t)(ry_B + (CAL_INSET_Y - 28) * ySlope)
```

Sanity checks before accepting:
- `xMax_new - xMin_new > 1000` (ADC span must be reasonable)
- `yMax_new - yMin_new > 1000`
- All values within 0..4095

If any check fails, REVIEW state shows an error and offers Retry only.

---

## IDLE / history view

IDLE state renders a summary of the current calibration and up to 3 history
entries:

```
+-----------------------------------+
|  Touch Calibration          Start |   ← status bar; "Start" is a button
+-----------------------------------+
|  Current cal                      |
|  xMin  185   xMax  3700           |
|  yMin  280   yMax  3850           |
|  Source: factory default          |
|  ─────────────────────────────────|
|  History                          |
|  [1] 2026-06-04  185/3690/275/3840|
|  [2] 2026-05-30  200/3710/290/3850|
+-----------------------------------+
```

"Current cal" pulls from `g_calData` (runtime struct, loaded from SPIFFS or
defaulting to compile-time values). "Source" shows `factory default`,
`SPIFFS session N`, or `unsaved (pending reboot)`.

---

## REVIEW state

After STEP_BL tap, render:
- Four corner dots (expected green, actual coloured by error)
- Summary table: computed xMin/xMax/yMin/yMax vs current values
- Three touch buttons: `Accept`, `Retry`, `Cancel`

```
+-----------------------------------+
|  Review — tap Accept to save      |
+-----------------------------------+
|  · · · · (scatter of taps) · · · |
|                                   |
|  New:  xMin 192  xMax 3695        |
|        yMin 285  yMax 3845        |
|  Δ:    xMin +7   xMax -5          |
|        yMin +5   yMax -5          |
|  ───────────────────────────────  |
|  [  Accept  ]  [ Retry ]  [Cancel]|
+-----------------------------------+
```

---

## Storage — `/cal.json`

Schema:

```json
{
  "current": {
    "xMin": 192, "xMax": 3695, "yMin": 285, "yMax": 3845,
    "raw": { "TL": [192, 285], "TR": [3695, 285],
             "BR": [3695, 3845], "BL": [192, 3845] },
    "ts": 1748950000
  },
  "history": [
    { "xMin": 185, "xMax": 3700, "yMin": 280, "yMax": 3850, "ts": 0, "src": "factory" },
    { "xMin": 200, "xMax": 3710, "yMin": 290, "yMax": 3850, "ts": 1748800000 }
  ]
}
```

- `history` is a ring buffer capped at 3 entries. On accept, current is pushed
  to history[0], older entries shift down, oldest (index 2) dropped.
- `ts: 0` with `src: "factory"` marks the compile-time default — always kept as
  the oldest anchor entry (not shifted out).
- File lives alongside `/spotify_diy_config.json` and `/settings.json`.

`TouchCalStorage` class (thin SPIFFS wrapper):

```cpp
struct TouchCalData {
    int16_t xMin, xMax, yMin, yMax;
    int16_t rawTL[2], rawTR[2], rawBR[2], rawBL[2];
    uint32_t ts;
    bool    valid;   // false = no SPIFFS entry; use #define defaults
};

extern TouchCalData g_calData;

namespace TouchCalStorage {
    void load();    // reads /cal.json → g_calData
    void save(const TouchCalData& d);  // writes + rotates history
}
```

---

## Rendering sketches

Screen coordinates for corner targets (indexed TL=0..BL=3):

```cpp
static const int16_t kTX[4] = { CAL_INSET_X, 274 - CAL_INSET_X,
                                 274 - CAL_INSET_X, CAL_INSET_X };
static const int16_t kTY[4] = { CAL_INSET_Y, CAL_INSET_Y,
                                 239 - 20, 239 - 20 };
```

### repaintHeader

```cpp
void CalibrationFlow::repaintHeader(const char* title) {
    tft.fillRect(0, 0, 275, CAL_HEADER_H, CAL_BG_COLOR);
    tft.setTextDatum(ML_DATUM);
    tft.setTextColor(CAL_HEADER_COLOR);
    tft.drawString("< back", 4, CAL_HEADER_H / 2, 2);
    tft.setTextDatum(MR_DATUM);
    tft.drawString(title, 271, CAL_HEADER_H / 2, 2);
    tft.drawFastHLine(0, CAL_HEADER_H - 1, 275, CAL_SEP_COLOR);
    tft.setTextDatum(TL_DATUM);
}
```

### repaintIdle

The Idle header is a special case: `"< back"` on the left, `"Start"` button
on the right. There is no centre title — the section is identified by the
category list that brought the user here. Do **not** call `repaintHeader()`
from `repaintIdle()`; draw the header inline.

`"Start"` tap zone: `x > 220 && y < CAL_HEADER_H`.

```cpp
void CalibrationFlow::repaintIdle() {
    // Custom header — back left, Start right (no centre title)
    tft.fillRect(0, 0, 275, CAL_HEADER_H, CAL_BG_COLOR);
    tft.setTextDatum(ML_DATUM);
    tft.setTextColor(CAL_HEADER_COLOR);
    tft.drawString("< back", 4, CAL_HEADER_H / 2, 2);
    tft.setTextDatum(MR_DATUM);
    tft.setTextColor(CAL_BTN_COLOR);
    tft.drawString("Start", 271, CAL_HEADER_H / 2, 2);
    tft.drawFastHLine(0, CAL_HEADER_H - 1, 275, CAL_SEP_COLOR);
    tft.setTextDatum(TL_DATUM);

    tft.fillRect(0, CAL_CONTENT_Y, 275, 240 - CAL_CONTENT_Y, CAL_BG_COLOR);

    int y = CAL_CONTENT_Y + 6;
    char buf[48];

    tft.setTextColor(CAL_SECTION_COLOR);
    tft.drawString("Current cal", 8, y, 2); y += 20;

    tft.setTextColor(CAL_VALUE_COLOR);
    snprintf(buf, sizeof(buf), "xMin %4d   xMax %4d", g_calData.xMin, g_calData.xMax);
    tft.drawString(buf, 8, y, 2); y += 16;
    snprintf(buf, sizeof(buf), "yMin %4d   yMax %4d", g_calData.yMin, g_calData.yMax);
    tft.drawString(buf, 8, y, 2); y += 16;

    tft.setTextColor(CAL_DIM_COLOR);
    const char* src = g_calData.valid ? "SPIFFS" : "factory default";
    snprintf(buf, sizeof(buf), "Source: %s", src);
    tft.drawString(buf, 8, y, 2); y += 20;

    tft.drawFastHLine(8, y, 259, CAL_SEP_COLOR); y += 8;

    tft.setTextColor(CAL_SECTION_COLOR);
    tft.drawString("History", 8, y, 2); y += 18;
    // iterate history loaded from /cal.json in start(); format: "[N] date  x/x/y/y"
}
```

### repaintStep

```cpp
void CalibrationFlow::repaintStep() {
    static const char* kLabels[4] = {
        "Tap top-left", "Tap top-right", "Tap bottom-right", "Tap bottom-left"
    };
    int cornerIdx = (int)_s.step - (int)CalStep::TL;
    repaintHeader(kLabels[cornerIdx]);
    tft.fillRect(0, CAL_CONTENT_Y, 275, 240 - CAL_CONTENT_Y, CAL_BG_COLOR);

    // Completed corners: grey crosshair + tap-marker
    for (int i = 0; i < cornerIdx; i++) {
        drawCrosshair(kTX[i], kTY[i], CAL_CROSSHAIR_DONE);
        drawTapMarker(i);
    }
    // Active corner: green crosshair
    drawCrosshair(kTX[cornerIdx], kTY[cornerIdx], CAL_CROSSHAIR_ACTIVE);
}
```

### drawCrosshair

```cpp
void CalibrationFlow::drawCrosshair(int x, int y, uint16_t color) {
    tft.drawFastHLine(x - CAL_CROSSHAIR_ARM, y, CAL_CROSSHAIR_ARM * 2, color);
    tft.drawFastVLine(x, y - CAL_CROSSHAIR_ARM, CAL_CROSSHAIR_ARM * 2, color);
    tft.fillRect(x - 2, y - 2, 4, 4, color);
}
```

### drawTapMarker

Maps recorded raw values through the **current** calibration to screen
coordinates, computes the pixel offset from the target, colours accordingly.

```cpp
void CalibrationFlow::drawTapMarker(int i) {
    // Expected screen position
    int ex = kTX[i], ey = kTY[i];
    // Map raw sample through current calibration
    int ax = map(_s.rawX[i], g_calData.xMin, g_calData.xMax, 0, 274);
    int ay = map(_s.rawY[i], g_calData.yMin, g_calData.yMax, 0, 239);
    ax = constrain(ax, 0, 274);
    ay = constrain(ay, 0, 239);

    int dist = (int)sqrtf((ax-ex)*(ax-ex) + (ay-ey)*(ay-ey));
    uint16_t markerColor = (dist <= 4) ? CAL_MARKER_OK
                         : (dist <= 8) ? CAL_MARKER_NEAR
                         :               CAL_MARKER_FAR;

    tft.fillCircle(ex, ey, 4, CAL_CROSSHAIR_DONE);  // expected (grey)
    if (ax != ex || ay != ey)
        tft.drawLine(ex, ey, ax, ay, markerColor);
    tft.fillCircle(ax, ay, 4, markerColor);           // actual

    char buf[16];
    snprintf(buf, sizeof(buf), "x:%d y:%d", _s.rawX[i], _s.rawY[i]);
    tft.setTextColor(CAL_DIM_COLOR);
    tft.drawString(buf, constrain(ax - 12, 0, 210), ay + 6, 1);
}
```

### repaintReview

```cpp
void CalibrationFlow::repaintReview() {
    repaintHeader(_s.sanityFailed ? "Bad reading" : "Review calibration");
    tft.fillRect(0, CAL_CONTENT_Y, 275, 240 - CAL_CONTENT_Y, CAL_BG_COLOR);

    for (int i = 0; i < 4; i++) drawTapMarker(i);

    if (_s.sanityFailed) {
        tft.setTextColor(CAL_ERROR_COLOR);
        tft.drawString("Span too small — tap Retry", 8, 150, 2);
    } else {
        char buf[48];
        int y = 120;
        tft.setTextColor(CAL_SECTION_COLOR);
        tft.drawString("New:", 8, y, 2);
        tft.setTextColor(CAL_VALUE_COLOR);
        snprintf(buf, sizeof(buf), "xMin %4d  xMax %4d",
                 _s.pending.xMin, _s.pending.xMax);
        tft.drawString(buf, 48, y, 2); y += 16;
        snprintf(buf, sizeof(buf), "yMin %4d  yMax %4d",
                 _s.pending.yMin, _s.pending.yMax);
        tft.drawString(buf, 48, y, 2); y += 16;

        tft.setTextColor(CAL_DIM_COLOR);
        snprintf(buf, sizeof(buf), "\xce\x94 xMin%+d  xMax%+d",
                 _s.pending.xMin - g_calData.xMin,
                 _s.pending.xMax - g_calData.xMax);
        tft.drawString(buf, 48, y, 2); y += 16;
        snprintf(buf, sizeof(buf), "  yMin%+d  yMax%+d",
                 _s.pending.yMin - g_calData.yMin,
                 _s.pending.yMax - g_calData.yMax);
        tft.drawString(buf, 48, y, 2);
    }

    tft.drawFastHLine(0, CAL_BTN_Y - 4, 275, CAL_SEP_COLOR);

    // Buttons
    auto drawBtn = [](int lx, const char* label, bool enabled) {
        uint16_t c = enabled ? CAL_BTN_COLOR : CAL_DIM_COLOR;
        tft.drawRect(lx, CAL_BTN_Y - CAL_BTN_H / 2, CAL_BTN_W, CAL_BTN_H, c);
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(c);
        tft.drawString(label, lx + CAL_BTN_W / 2, CAL_BTN_Y, 2);
        tft.setTextDatum(TL_DATUM);
    };
    drawBtn(CAL_BTN_ACCEPT_X, "Accept", !_s.sanityFailed);
    drawBtn(CAL_BTN_RETRY_X,  "Retry",  true);
    drawBtn(CAL_BTN_CANCEL_X, "Cancel", true);
}
```

---

## Open questions

1. **PATCH-002 scope** — `setCalibration()` patch to `CYD28_TouchscreenR.h/cpp`
   needs to be filed in `upstream-patches.md` and tracked as a prerequisite task
   before any cal implementation begins. (`ts.getPointRaw()` already exists in
   the driver — confirmed 2026-06-05; no driver change needed for the raw read
   path.)
2. ~~**Timestamp source**~~ — **resolved**: use `time()` with fallback to `0`
   if NTP not yet synced. Display as `"no clock"` in the history view when
   `ts == 0` and `src != "factory"`.
3. ~~**Factory anchor**~~ — **resolved yes**: on first `doSave()`, push the
   compile-time `#define` defaults as `{ts:0, src:"factory"}` into `history[0]`
   before inserting the new session. This ensures the baseline is always visible.
   Already reflected in the storage schema above.
4. **Per-unit variance** — resistive touch drift is per-unit. Consider prompting
   re-calibration if > N days since last cal (future enhancement; not in scope).
5. **Raw tap debounce** — `handleInputRaw()` latches on `Release` only (pen-up
   transition: `wasPressed && !pressed`). Raw XPT2046 values while pressed are
   accumulated in a running average (`rawSumX`, `rawSumY`, `rawCount`) and the
   average is recorded on release. This avoids reliance on `besttwoavg()` and
   prevents double-registering a single tap.

---

## Exit criteria

- **C1** — 4-corner sequence completes without crash. All 4 steps reachable.
- **C2** — Computed xMin/xMax span > 1000 ADC counts for a valid calibration.
- **C3** — Accepted values written to `/cal.json`; file survives SPIFFS remount.
- **C4** — On next boot, `TouchCalStorage::load()` reads values and `ts.setCalibration()` is called before first touch event.
- **C5** — History shows up to 3 entries; 4th entry drops oldest non-factory entry.
- **C6** — Cancel at any step returns to Settings `cal` tab with no change to stored values.
- **C7** — Live feedback marker renders within 275×240 canvas; no pixel bleeds into taskbar strip.
- **C8** — `_calFlow.active()` returns true for all states Idle→Saving; `_calFlow.stepping()` returns true only for TL→BL. `SettingsApp::tick()` raw poll fires only when `stepping()`; `SettingsApp::handleInput()` delegates scaled coords only when `active()`. Neither path fires outside these guards.
