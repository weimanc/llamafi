# Design — Touch Calibration Flow

> Owner: Architect
> Status: draft
> Date: 2026-06-04
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
by `SettingsApp`, activated when the user enters the `cal` tab. Pattern follows
the "keyboard is a widget" precedent from [settings.md §Keyboard is a widget](settings.md).

When `_calFlow.active()` is true, `SettingsApp::tick()` and
`SettingsApp::handleInput()` fully delegate to `_calFlow`. The taskbar is still
rendered; only the 275×240 left canvas is taken over.

```cpp
class CalibrationFlow {
public:
    void start();          // called when user enters cal tab
    bool active() const;   // true while calibration in progress
    void tick();           // called by SettingsApp::tick() when active
    bool handleInput(TouchPhase phase, int x, int y);
    // x/y here are RAW values, not scaled — see §Raw input during calibration
private:
    // ... state machine + rendering (see below)
};
```

`SettingsApp` holds `CalibrationFlow _calFlow;` as a member.

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

## Raw input during calibration

During the STEP_* states, `CalibrationFlow::handleInput()` must receive **raw**
XPT2046 values, not calibrated screen coordinates. The existing touch pipeline
delivers scaled values; calibration flow needs the unscaled path.

Option: add a `handleInputRaw(TouchPhase, int rawX, int rawY)` overload, called
by a separate poll in `SettingsApp::tick()` using `ts.getPointRaw()` when
`_calFlow.active()` is true. The normal `handleInput(phase, scaledX, scaledY)`
path is bypassed for the cal flow's STEP_* states.

IDLE and REVIEW states use scaled input normally (tapping UI buttons).

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

## State struct

```cpp
enum class CalStep : uint8_t { Idle, TL, TR, BR, BL, Review, Saving };

struct CalibrationFlowState {
    CalStep   step = CalStep::Idle;
    int16_t   rawX[4], rawY[4];   // measured raw values, indexed by corner (TL=0..BL=3)
    uint8_t   tapsDone;           // 0..4
    bool      sanityFailed;       // true if computed spans fail checks
    TouchCalData pending;         // computed values before accept
};
```

---

## Open questions

1. **PATCH-002 scope** — `setCalibration()` patch to `CYD28_TouchscreenR.h/cpp`
   needs to be filed in `upstream-patches.md` and tracked as a prerequisite task
   before any cal implementation begins.
2. **Timestamp source** — NTP-synced `time()` or `millis()`-based epoch? NTP may
   not be available on first boot. Use `time()` with fallback to 0 if not synced;
   display as "no clock" in the history view.
3. **Factory anchor** — should the factory `#define` values be pushed to history
   on first save so the user can always see the baseline? Recommended yes (see
   storage schema `src: "factory"`), but confirm when implementing.
4. **Per-unit variance** — resistive touch drift is per-unit. Consider prompting
   re-calibration if > N days since last cal (future enhancement; not in scope).
5. **Raw input plumbing** — `handleInputRaw()` call from `SettingsApp::tick()`
   using `ts.getPointRaw()` needs careful debouncing. XPT2046 raw reads are
   noisy; the existing `besttwoavg()` filter in `update()` handles averaging,
   but release detection (`zraw < threshold`) must still be checked to avoid
   double-registering a single tap.

---

## Exit criteria

- **C1** — 4-corner sequence completes without crash. All 4 steps reachable.
- **C2** — Computed xMin/xMax span > 1000 ADC counts for a valid calibration.
- **C3** — Accepted values written to `/cal.json`; file survives SPIFFS remount.
- **C4** — On next boot, `TouchCalStorage::load()` reads values and `ts.setCalibration()` is called before first touch event.
- **C5** — History shows up to 3 entries; 4th entry drops oldest non-factory entry.
- **C6** — Cancel at any step returns to Settings `cal` tab with no change to stored values.
- **C7** — Live feedback marker renders within 275×240 canvas; no pixel bleeds into taskbar strip.
