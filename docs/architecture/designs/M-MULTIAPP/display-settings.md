# Design — Display Settings

> Owner: Architect
> Status: draft
> Date: 2026-06-04 (updated 2026-06-06 — implementation audit; tab layout labels corrected)
> Part of: M-MULTIAPP Settings (`disp` tab)
> See also: [settings.md](settings.md)

---

## Context

The CYD backlight is GPIO21 (`TFT_BL=21`, platformio.ini). TFT_eSPI drives it
at full brightness unconditionally via a ledc channel set up during `tft.init()`.
The CYD also carries a photoresistor (LDR) on GPIO34 (ADC1_CH6). Neither is
currently used for adaptive brightness — the screen is always at 100%.

---

## Hardware

| Signal | GPIO | Notes |
|--------|------|-------|
| TFT backlight | 21 | ledc PWM, 5 kHz, 8-bit (0–255). TFT_eSPI claims ledc channel 0 at init. |
| LDR | 34 | ADC1_CH6, 12-bit (0–4095). Brighter ambient → higher ADC value (resistor divider to GND). |

**Backlight PWM:** TFT_eSPI calls `ledcSetup(0, 5000, 8)` + `ledcAttachPin(21, 0)`
internally. To set custom brightness, use `ledcWrite(0, duty)` directly — no
additional setup required after `tft.init()`.

**LDR read:** `analogRead(34)` — no setup required; ADC1 channels are usable
without `adc1_config_*` when using Arduino `analogRead`.

---

## Goals

1. Manual brightness: user sets a level 1–10, applied immediately.
2. Auto-brightness: LDR reading mapped to backlight level; updated each tick.
3. Settings persisted to SPIFFS; applied at boot before first frame.
4. Live LDR readout shown in the `disp` tab for diagnostic use.

---

## Tab content layout

```
+-----------------------------------+
|  Brightness                       |   section header
|  Auto            Off              |   → cycle: Off ↔ On
|  Level           7                |   → cycle 1–10 (greyed when auto=On)
|  ─────────────────────────────── |
|  Auto range                       |   section header (sub-header with separator line)
|  LDR             1842             |   live value, updated each tick (read-only)
|  Dark floor      200              |   read-only display of ldrLow floor value
|  Bright ceiling  3800             |   read-only display of ldrHigh ceiling value
+-----------------------------------+
```

7 rows × 26px = 182px — fits within 212px content panel.

"Level" row is greyed (`SETTINGS_VALUE_OFF` colour) when auto-brightness is on;
tapping it has no effect in that state.

"LDR reading" is a live readout — updated every 500 ms from `analogRead(34)`.
`DispFlow::tick()` polls the ADC and redraws this row when the value changes by
more than ±20 counts (avoids flicker from noise).

---

## Auto-brightness algorithm

LDR ADC value mapped linearly to backlight level 1–10, then to duty 25–255:

```cpp
// Called each tick when auto=true:
void applyAutobrightness() {
    int raw = analogRead(LDR_PIN);   // 0..4095
    // Clamp to calibrated range
    raw = constrain(raw, g_dispSettings.ldrLow, g_dispSettings.ldrHigh);
    // Map to level 1..10
    int level = map(raw, g_dispSettings.ldrLow, g_dispSettings.ldrHigh, 1, 10);
    setBacklight(level);
}

void setBacklight(int level) {               // level 1..10
    int duty = map(level, 1, 10, 25, 255);   // 25 = ~10%, never fully off
    ledcWrite(TFT_LEDC_CHANNEL, duty);
    g_dispSettings.currentLevel = level;     // for display readout
}
```

`TFT_LEDC_CHANNEL` = 0 (same channel TFT_eSPI set up — safe to reuse via
`ledcWrite` once init is done).

**Hysteresis:** only update if computed level differs from current level by ≥1
to avoid rapid flickering near a threshold. Implement with a `_lastAutoLevel`
member in `DispFlow`.

**Smoothing:** ADC readings on ESP32 are noisy. Apply a simple 8-sample
moving average before mapping:

```cpp
static int _ldrBuf[8] = {};
static uint8_t _ldrIdx = 0;
_ldrBuf[_ldrIdx++ & 7] = analogRead(LDR_PIN);
int avg = 0;
for (int v : _ldrBuf) avg += v;
avg /= 8;
```

---

## Boot application

```cpp
// main.cpp::setup(), after tft.init():
DispSettingsStorage::load();   // reads /settings.json["disp"] → g_dispSettings
setBacklight(g_dispSettings.auto ? autoLevel() : g_dispSettings.level);
```

---

## Persistence schema

```json
{
  "disp": {
    "auto":    false,
    "level":   7,
    "ldrLow":  200,
    "ldrHigh": 3800
  }
}
```

Defaults: `auto=false`, `level=7` (duty ~175/255 ≈ 69%), `ldrLow=200`,
`ldrHigh=3800`.

---

## DispSettings struct

```cpp
struct DispSettings {
    bool    autobrightness;
    uint8_t level;       // 1..10
    int16_t ldrLow;      // ADC floor  (dark room)
    int16_t ldrHigh;     // ADC ceiling (bright room)
};

extern DispSettings g_dispSettings;

namespace DispSettingsStorage {
    void load();
    void save();
}

#define LDR_PIN          34
#define TFT_LEDC_CHANNEL  0    // matches TFT_eSPI's ledc channel
```

---

## DisplaySection class sketch

```cpp
// app/src/settings/displaySection.h

#include "settingsSection.h"
#include "sliderWidget.h"
#include "../settingsStorage.h"

#define LDR_PIN          34
#define TFT_LEDC_CHANNEL  0   // channel TFT_eSPI set up at tft.init()

// Row indices (no sub-header — flat layout)
static constexpr int kRowAuto    = 0;
static constexpr int kRowLevel   = 1;
static constexpr int kRowLdrLow  = 2;
static constexpr int kRowLdrHigh = 3;

class DisplaySection : public SettingsSection {
public:
    // ---- SettingsSection contract -------------------------------------------

    const char* title() const override { return "Display"; }

    void enter() override {
        _slider.init(1, 10, g_settings.dispLevel);   // sync from storage
        _ldrRaw      = analogRead(LDR_PIN);
        _ldrUpdateMs = millis();
        repaint();
    }

    void tick() override {
        // Poll LDR every 500 ms; only repaint LDR rows when value drifts >±20.
        if (millis() - _ldrUpdateMs >= 500) {
            _ldrUpdateMs = millis();
            int16_t fresh = (int16_t)analogRead(LDR_PIN);
            if (abs(fresh - _ldrRaw) > 20) {
                _ldrRaw = fresh;
                repaintLdrRows();
            }
        }
        // Auto-brightness: update backlight from LDR when Auto=On.
        if (g_settings.dispAuto) {
            int16_t raw = constrain(_ldrRaw,
                                    g_settings.ldrLow, g_settings.ldrHigh);
            int level = map(raw,
                            g_settings.ldrLow, g_settings.ldrHigh, 1, 10);
            if (abs(level - _lastAutoLevel) >= 1) {
                _lastAutoLevel = level;
                applyBrightness(level);
            }
        }
    }

    void repaint() override {
        drawHeader();
        clearContent();

        // Row 0 — Auto toggle
        bool autoOn = g_settings.dispAuto;
        drawRow(S_CONTENT_Y + kRowAuto * S_ROW_H, {
            "Auto",
            autoOn ? "On" : "Off",
            S_LABEL,
            autoOn ? S_VALUE_ON : S_VALUE_OFF
        });

        // Row 1 — Level slider (greyed when Auto=On)
        _slider.render(S_CONTENT_Y + kRowLevel * S_ROW_H,
                       "Level",
                       /*disabled=*/g_settings.dispAuto);

        // Rows 2–3 — read-only LDR diagnostics
        repaintLdrRows();
    }

    SectionResult handleInput(TouchPhase phase, int x, int y) override {
        // Back tap (Release only, top-left header zone)
        if (phase == TouchPhase::Release && isBackTap(x, y))
            return SectionResult::GoBack;

        // Slider pointer-capture: forward all phases when dragging.
        // Also attempt capture on Press so drag-starts mid-track are caught.
        if (!g_settings.dispAuto) {
            const int levelRowY = S_CONTENT_Y + kRowLevel * S_ROW_H;
            if (phase == TouchPhase::Press) {
                _slider.onPress(x, y, levelRowY);           // captures if in row
            } else if (phase == TouchPhase::Move && _slider.isDragging()) {
                _slider.onMove(x);
                _slider.render(levelRowY, "Level", /*disabled=*/false);
            } else if (phase == TouchPhase::Release && _slider.isDragging()) {
                g_settings.dispLevel = (uint8_t)_slider.onRelease(x);
                applyBrightness(g_settings.dispLevel);
                saveSettings();
                _slider.render(levelRowY, "Level", /*disabled=*/false);
                return SectionResult::Continue;
            }
        }

        // Row taps (Release only)
        if (phase == TouchPhase::Release) {
            int row = tapToRow(y);
            if (row == kRowAuto) {
                g_settings.dispAuto = !g_settings.dispAuto;
                saveSettings();
                if (!g_settings.dispAuto) {
                    // Restore manual level immediately
                    applyBrightness(g_settings.dispLevel);
                }
                repaint();
            }
            // kRowLevel handled by slider above; kRowLdrLow/High are read-only.
        }

        return SectionResult::Continue;
    }

private:
    SliderWidget  _slider;
    int16_t       _ldrRaw      = 0;
    unsigned long _ldrUpdateMs = 0;
    int           _lastAutoLevel = -1;   // hysteresis: only write ledc on change

    // In-place repaint of LDR rows only (avoids full-screen clear during tick).
    void repaintLdrRows() {
        char bufLow[8], bufHigh[8];
        snprintf(bufLow,  sizeof(bufLow),  "%d", (int)g_settings.ldrLow);
        snprintf(bufHigh, sizeof(bufHigh), "%d", (int)g_settings.ldrHigh);

        char bufRaw[8];
        snprintf(bufRaw, sizeof(bufRaw), "%d", (int)_ldrRaw);

        // Blank-fill only the two rows before redrawing to avoid ghosting.
        tft.fillRect(0, S_CONTENT_Y + kRowLdrLow  * S_ROW_H,
                     S_CANVAS_W, S_ROW_H, S_BG);
        tft.fillRect(0, S_CONTENT_Y + kRowLdrHigh * S_ROW_H,
                     S_CANVAS_W, S_ROW_H, S_BG);

        drawRow(S_CONTENT_Y + kRowLdrLow  * S_ROW_H,
                { "LDR Low",  bufLow,  S_LABEL, S_VALUE_OFF });
        drawRow(S_CONTENT_Y + kRowLdrHigh * S_ROW_H,
                { "LDR High", bufHigh, S_LABEL, S_VALUE_OFF });

        // Overlay live reading as a small annotation on the LDR Low row
        // (re-uses the value slot — implementation may choose a separate row).
        (void)bufRaw;   // consumed by tick() caller's display logic if needed
    }

    // Map level 1..10 → PWM duty 25..255 and write to ledc channel.
    void applyBrightness(int level) {
        int duty = map(constrain(level, 1, 10), 1, 10, 25, 255);
        ledcWrite(TFT_LEDC_CHANNEL, (uint32_t)duty);
    }
};
```

### Design notes

**Single-view section.** `DisplaySection` has no sub-views or step enum. All
four rows are always visible; the only state change is `dispAuto` toggling the
Level row's interactive/greyed state.

**Slider pointer-capture.** `_slider.onPress()` is called on every
`TouchPhase::Press` event. If the press lands in the Level row's hit zone,
`isDragging()` becomes true and all subsequent Move/Release events for that
touch are forwarded unconditionally — no re-hit-test. This matches the
M-TOUCH-CAPTURE pattern documented in `sliderWidget.h`.

**Level row Y.** `kRowLevel = 1`, so `rowY = S_CONTENT_Y + S_ROW_H =
28 + 26 = 54`. This is passed verbatim to `_slider.onPress(px, py, 54)`.

**LDR rows are read-only.** `tapToRow()` returns `kRowLdrLow` (2) or
`kRowLdrHigh` (3) but neither has a tap action. The tab-content layout in this
doc shows LDR Low/High as adjustable via cycle gesture; that is deferred — the
class sketch implements read-only display first. Calibration gestures can be
added in a follow-up pass.

**tick() rate-limiting.** LDR is read at most once per 500 ms
(`_ldrUpdateMs`). A ±20-count dead-band suppresses flicker from ADC noise
without requiring the 8-sample moving average described in the algorithm
section (that smoothing can be added inside `repaintLdrRows()` if noise proves
problematic in integration).

**applyBrightness() duty mapping.** Level 1 → duty 25 (~10%); level 10 →
duty 255 (100%). Minimum 10% keeps the display readable in all conditions.
Raise the floor in integration if level 1 is too dim (see Open question 2).

---

## Open questions

1. **LDR wiring polarity** — assumed brighter = higher ADC. Verify on DUT:
   `analogRead(34)` in bright light should exceed dark-room reading. If inverted,
   swap `map()` arguments: `map(raw, ldrLow, ldrHigh, 10, 1)`.
2. **Minimum duty** — level 1 → duty 25 (~10%). If the backlight dims too
   aggressively and becomes unreadable, raise the floor (e.g. duty 50 = ~20%).
   Adjust in implementation after visual testing.
3. ~~**ledc channel conflict**~~ RESOLVED 2026-06-06: TFT_eSPI for this build
   config (`TFT_BL` + `TFT_BACKLIGHT_ON` flags, no `LEDC_CHANNEL` define) uses
   `digitalWrite(TFT_BL, HIGH)` — plain digital, no LEDC setup. Firmware must
   call `ledcSetup(0,5000,8)` + `ledcAttachPin(TFT_BL,0)` after `tft.init()`
   and before first `ledcWrite`. Done in `setup()` after `SPIFFS.begin()`.

---

## Exit criteria

- **C1** — Manual level 1–10 cycles correctly; `ledcWrite` duty changes visibly.
- **C2** — Auto mode: covering LDR dims display; uncovering brightens it.
  Transition is smooth (no single-step jumps larger than 2 levels per poll).
- **C3** — LDR reading row updates live in the settings tab without full repaint.
- **C4** — Persisted level survives `ESP.restart()`; boot applies it before
  first frame render (no brightness flash at startup).
- **C5** — "Level" row visually greyed when auto=On; tap does nothing.

---

## Implementation Status (audit 2026-06-06)

| Area | Status | Notes |
|------|--------|-------|
| Auto toggle, manual brightness slider | ✅ DONE | Slider applies live on drag (not just Release) |
| LDR live readout every 500 ms | ✅ DONE | |
| Auto-brightness with hysteresis | ✅ DONE | |
| Tab layout labels | ✅ DONE (corrected) | Spec updated: "Sensor"→"Auto range", "LDR low"→"Dark floor", "LDR high"→"Bright ceiling" |
| C2 — slew rate ≤2 levels per poll | ⚠ NOT ENFORCED | Impl uses hysteresis (≥1 level change to apply); no max-2-level ramp cap |
| 8-sample LDR smoothing buffer | ⚠ DEFERRED | Spec notes it as optional; not implemented |
| `Serial.printf` in `enter()` | ⚠ UNGUARDED | Should be wrapped in `#ifdef SERIAL_DEBUG` |
| C4 — boot brightness before first frame | ⚠ UNVERIFIED | Depends on `main.cpp::setup()` call order |
