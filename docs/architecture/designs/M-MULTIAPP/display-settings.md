# Design — Display Settings

> Owner: Architect
> Status: draft
> Date: 2026-06-04
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
|  Sensor                           |   section header
|  LDR reading     1842             |   live value, updated each tick (read-only)
|  LDR low         200              |   → cycle: dark-room floor (100–600, step 50)
|  LDR high        3800             |   → cycle: bright-room ceiling (2000–4000, step 100)
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

## Open questions

1. **LDR wiring polarity** — assumed brighter = higher ADC. Verify on DUT:
   `analogRead(34)` in bright light should exceed dark-room reading. If inverted,
   swap `map()` arguments: `map(raw, ldrLow, ldrHigh, 10, 1)`.
2. **Minimum duty** — level 1 → duty 25 (~10%). If the backlight dims too
   aggressively and becomes unreadable, raise the floor (e.g. duty 50 = ~20%).
   Adjust in implementation after visual testing.
3. **ledc channel conflict** — TFT_eSPI uses channel 0 for `TFT_BL`. Confirm
   no other ledc channel assignments clash. If a conflict exists, reconfigure
   TFT_eSPI to use a different channel via `TFT_BL_CHANNEL` build flag.

---

## Exit criteria

- **C1** — Manual level 1–10 cycles correctly; `ledcWrite` duty changes visibly.
- **C2** — Auto mode: covering LDR dims display; uncovering brightens it.
  Transition is smooth (no single-step jumps larger than 2 levels per poll).
- **C3** — LDR reading row updates live in the settings tab without full repaint.
- **C4** — Persisted level survives `ESP.restart()`; boot applies it before
  first frame render (no brightness flash at startup).
- **C5** — "Level" row visually greyed when auto=On; tap does nothing.
