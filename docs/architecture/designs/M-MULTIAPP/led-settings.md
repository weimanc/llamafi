# Design — RGB LED Settings

> Owner: Architect
> Status: draft
> Date: 2026-06-04
> Part of: M-MULTIAPP Settings (`led` tab)
> See also: [settings.md](settings.md)

---

## Hardware

The CYD (ESP32-2432S028R) has an onboard RGB LED wired as a common-cathode
device on three GPIO pins:

| Channel | GPIO | ledc channel |
|---------|------|-------------|
| Red | 4 | 1 |
| Green | 16 | 2 |
| Blue | 17 | 3 |

**Active low (common cathode):** the cathode is tied to GND. Writing a PWM
duty of 255 drives the anode high — LED ON at full brightness. Duty 0 = LED OFF.

Verify polarity on the DUT: `digitalWrite(4, HIGH)` should light the red
channel. If the LED is instead common-anode (anode tied to 3.3 V), invert:
duty 0 = ON, duty 255 = OFF. See §Open questions.

Each channel: `ledcSetup(ch, 5000, 8)` + `ledcAttachPin(gpio, ch)` during
`setup()`. Write colour with `ledcWrite(ch, duty)`.

---

## Goals

1. Four LED modes: Off, Static, Pulse, Clock.
2. Static colour: 8 predefined colours, cycle-on-tap.
3. Brightness: 1–10, scales all three channels proportionally.
4. Pulse mode: soft breathing animation in the selected colour.
5. Clock mode: colour shifts by hour across the day (red→orange→yellow→green→blue→violet→red).
6. Settings persisted to SPIFFS; applied at boot.

---

## Tab content layout

```
+-----------------------------------+
|  LED                              |   section header
|  Mode            Static           |   → cycle: Off → Static → Pulse → Clock → Off
|  Colour          Green            |   → cycle 8 colours (greyed when mode=Off)
|  Brightness      5                |   → cycle 1–10 (greyed when mode=Off)
+-----------------------------------+
```

3 rows × 26px = 78px — content panel is mostly empty; may add a live LED
preview swatch (filled rectangle showing the current colour at full brightness)
centred in the remaining space.

---

## Modes

### Off
All three channels set to duty 0. No tick() cost.

### Static
Colour and brightness set once; no animation. `tick()` is a no-op after the
initial write.

```cpp
void applyStatic() {
    auto [r, g, b] = scaledRGB();
    ledcWrite(LED_R_CH, r);
    ledcWrite(LED_G_CH, g);
    ledcWrite(LED_B_CH, b);
}
```

### Pulse (breathing)
Brightness cycles smoothly 0→max→0 using a sine envelope at ~0.5 Hz.
Colour stays fixed; only intensity varies.

```cpp
// In LedFlow::tick(), called every frame (~30 Hz):
static float _phase = 0.0f;
_phase += 0.05f;                              // ~0.5 Hz at 30 fps
if (_phase > TWO_PI) _phase -= TWO_PI;
float env = (sinf(_phase) + 1.0f) * 0.5f;    // 0.0 .. 1.0
auto [r, g, b] = baseRGB();
ledcWrite(LED_R_CH, (uint8_t)(r * env));
ledcWrite(LED_G_CH, (uint8_t)(g * env));
ledcWrite(LED_B_CH, (uint8_t)(b * env));
```

`tick()` uses `lut_sin` (from `mathUtil.h`, ADR-038) rather than `sinf` to
avoid trig cost. Phase step is pre-computed as a `constexpr float`.

### Clock
Colour rotates through a 24-step hue wheel, one step per hour.
At midnight: red. Noon: cyan. 6 AM: yellow-green. 6 PM: blue-violet.

```cpp
// In LedFlow::tick(), updated once per minute:
struct tm t;
if (!getLocalTime(&t)) return;
int hour = t.tm_hour;     // 0..23
// Map hour → hue (0..255 in HSV space), convert to RGB, scale by brightness
uint8_t hue  = (uint8_t)((hour * 256) / 24);
auto [r,g,b] = hsvToRgb(hue, 255, brightnessScaled());
ledcWrite(LED_R_CH, r);
ledcWrite(LED_G_CH, g);
ledcWrite(LED_B_CH, b);
```

`hsvToRgb` is a small pure function (~20 lines). No extra dependencies.

---

## Predefined colours

8 colours cycle on tap. Stored as an index 0–7.

| Index | Name | R | G | B |
|-------|------|---|---|---|
| 0 | White | 255 | 255 | 255 |
| 1 | Red | 255 | 0 | 0 |
| 2 | Green | 0 | 255 | 0 |
| 3 | Blue | 0 | 0 | 255 |
| 4 | Cyan | 0 | 255 | 255 |
| 5 | Magenta | 255 | 0 | 255 |
| 6 | Yellow | 255 | 255 | 0 |
| 7 | Orange | 255 | 100 | 0 |

In Clock mode, colour index is ignored (hue derived from time).
In Pulse mode, colour index sets the base hue.

---

## Brightness scaling

```cpp
// Scales [R,G,B] by brightness level 1..10
std::tuple<uint8_t,uint8_t,uint8_t> LedFlow::scaledRGB() const {
    float scale = g_ledSettings.brightness / 10.0f;
    auto& c = kColours[g_ledSettings.colourIdx];
    return { (uint8_t)(c.r * scale),
             (uint8_t)(c.g * scale),
             (uint8_t)(c.b * scale) };
}
```

Brightness 1 = 10%, brightness 10 = 100%.

---

## Persistence schema

```json
{
  "led": {
    "mode":       "static",
    "colourIdx":  2,
    "brightness": 5
  }
}
```

`mode` values: `"off"` | `"static"` | `"pulse"` | `"clock"`.

Defaults: `mode="off"`, `colourIdx=2` (green), `brightness=5`.

---

## LedSettings struct

```cpp
enum class LedMode : uint8_t { Off = 0, Static = 1, Pulse = 2, Clock = 3 };

struct LedSettings {
    LedMode mode;
    uint8_t colourIdx;   // 0..7
    uint8_t brightness;  // 1..10
};

extern LedSettings g_ledSettings;

namespace LedSettingsStorage {
    void load();
    void save();
}

#define LED_R_PIN  4
#define LED_G_PIN 16
#define LED_B_PIN 17
#define LED_R_CH   1    // ledc channels (0 = TFT_BL, reserved)
#define LED_G_CH   2
#define LED_B_CH   3
```

---

## Boot application

```cpp
// main.cpp::setup(), after tft.init():
LedSettingsStorage::load();
ledcSetup(LED_R_CH, 5000, 8); ledcAttachPin(LED_R_PIN, LED_R_CH);
ledcSetup(LED_G_CH, 5000, 8); ledcAttachPin(LED_G_PIN, LED_G_CH);
ledcSetup(LED_B_CH, 5000, 8); ledcAttachPin(LED_B_PIN, LED_B_CH);
g_ledFlow.applyMode();   // applies persisted mode at startup
```

`LedFlow::tick()` is called from the main app loop (same cadence as `appTick()`).
In Off and Static modes `tick()` returns immediately after a one-shot write.

---

## Open questions

1. **Common-cathode vs common-anode** — assumed common-cathode (duty 255 = ON).
   Verify with `ledcWrite(LED_R_CH, 255)` on DUT. If the LED doesn't light,
   the board is common-anode; flip all `ledcWrite` values to `255 - duty`.
   If confirmed common-anode, add `#define LED_ACTIVE_LOW 1` and invert in
   `scaledRGB()`.
2. **Pulse sine cost** — `tick()` calls `lut_sin` once per frame (~30 Hz).
   Negligible. If `mathUtil.h` is not yet available (ADR-038 pending), fall
   back to a pre-computed triangle wave (`_phase += step; if >1 step = -step`).
3. **Clock mode update frequency** — colour only changes once per hour; polling
   `getLocalTime()` every frame is wasteful. Gate the update: compare
   `t.tm_hour` to `_lastHour`; skip `ledcWrite` if unchanged.
4. **Interaction with NFC** — `nfc.h` uses GPIO16 for PN532 HSPI MISO on some
   configurations. If NFC is enabled and shares GPIO16, LED green channel
   conflicts. Check pin assignment when `NFC_ENABLED` is defined.

---

## Exit criteria

- **C1** — Off mode: all three channels at duty 0; no CPU cost in tick().
- **C2** — Static + colour cycle: each of 8 colours lights the LED in the
  expected hue at full brightness.
- **C3** — Brightness 1 visibly dimmer than brightness 10 on all channels.
- **C4** — Pulse: LED breathes smoothly with no visible stepping; completes
  one full cycle in approximately 2 seconds.
- **C5** — Clock: colour matches expected hue for the current hour; updates
  within 1 minute of hour boundary.
- **C6** — Settings survive `ESP.restart()`; mode applied before first frame.
- **C7** — ledc channel assignments do not conflict with TFT backlight
  (channel 0) or any other peripheral.
