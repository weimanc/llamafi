# Design — RGB LED Settings

> Owner: Architect
> Status: draft
> Date: 2026-06-04 (updated 2026-06-05 — colour picker replaces predefined swatches; HSV storage)
> Part of: M-MULTIAPP Settings (`led` tab)
> See also: [settings.md](settings.md), [settingsSection.h](../../../app/src/settings/settingsSection.h)

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
2. Static/Pulse colour: full HSV colour picker — hue strip + saturation/value
   square (Photoshop-style). Replaces the previous 8-swatch cycle-on-tap.
3. Brightness is the V (value) axis of the HSV picker — no separate brightness
   row in the list view.
4. Pulse mode: soft breathing animation in the selected colour.
5. Clock mode: colour shifts by hour across the day (red→orange→yellow→green→blue→violet→red).
   Ignores stored HSV colour.
6. Settings persisted to SPIFFS; applied at boot.

---

## LED section list view

Entry point from Settings category list. Two rows only — Colour opens the
full-screen picker view.

```
+-----------------------------------+
|  <  LED                           |   header
+-----------------------------------+
|  Mode            Static        >  |   → cycle: Off → Static → Pulse → Clock → Off
|  Colour          ████             |   → opens colour picker (filled rect in stored colour)
+-----------------------------------+
```

The "Colour" row value column renders a small filled rectangle (`16×10 px`)
in the current stored HSV colour rather than text. This gives immediate visual
feedback on the list view without opening the picker.

Colour row is greyed when `mode == Off` or `mode == Clock` (clock ignores stored colour).

---

## Colour picker view

Accessed by tapping the "Colour" row. Replaces the content panel while active;
the `< back` zone returns to the LED list view (without saving). The Save
button commits to SPIFFS.

### Layout

Content area: x:0..274, y:28..239 (275×212 px — standard settings canvas).

```
x=0                                              x=274
y=28  +------------------------------------------------+
      | [OFF][ON]                        [SAVE]        |  ← button bar  h=28
y=56  +------------------------------------------------+
      |                                                |  ← gap         h=5
y=61  +------------------+        +------+             |
      |                  |        |      |             |
      |                  |        |  H   |             |
      |   S · V square   |        |  u   |  dark       |
      |   168 × 168 px   |        |  e   |  space      |
      |                  |        |      |             |
      |                  |        |strip |             |
      |                  |        | 24px |             |
y=229 +------------------+        +------+             |
      |                                                |  ← dark pad    h=10
y=239 +------------------------------------------------+
```

| Element | x | y | w | h |
|---------|---|---|---|---|
| Button bar | 0 | 28 | 275 | 28 |
| SV square | 8 | 61 | 168 | 168 |
| Hue strip | 184 | 61 | 24 | 168 |

### Button bar (y=28..55)

Two zones within the 28 px bar:

**On/Off toggle** — left side, two adjacent buttons:

```
  x=8..73   "OFF"  — active bg when mode=Off,    inactive bg otherwise
  x=77..142 "ON"   — active bg when mode≠Off,    inactive bg otherwise
```

- Active button: `S_VALUE_ON` (green) background, dark text.
- Inactive button: `S_SEP` (grey) background, grey text.
- Tapping ON restores last non-Off mode (Static if no prior mode recorded).
- Tapping OFF sets `mode = LedMode::Off` and applies immediately.
- Each button: 66×20 px, vertically centred in bar (y offset +4).

**Save button** — right side:

```
  x=200..267  "SAVE"  — S_VALUE_ON bg when settings modified; S_SEP bg when clean
```

- Tapping writes `g_settings` to SPIFFS via `SettingsStorage::save()`.
- Visual confirmation: button inverts colour for ~100 ms.
- 68×20 px, vertically centred in bar.

Rationale for explicit Save: the colour picker involves continuous drag
gestures. Auto-saving on every `onMove` would saturate SPIFFS write cycles.
Colour changes are applied to the LED immediately (live preview) but only
persisted when the user taps Save.

### Hue strip (x=184..207, y=61..228, 24×168 px)

Vertical rainbow gradient: hue 0 (red) at top, cycling through the spectrum,
hue 255 (back to red) at bottom. Rendered as 168 horizontal `fillRect` calls,
one per pixel row:

```cpp
for (int row = 0; row < 168; row++) {
    uint8_t hue = (uint8_t)((row * 255) / 167);
    tft.fillRect(184, 61 + row, 24, 1, hsvToRgb565(hue, 255, 255));
}
```

**Cursor:** a 24×3 px bright white horizontal bar drawn over the strip at the
current hue row. White outline (1 px) for contrast against all hues.

Touch: full strip width (24 px) is the hit zone. Pointer-capture on Press;
Move tracks finger Y clamped to strip bounds. Release commits hue.

### SV square (x=8..175, y=61..228, 168×168 px)

X axis: saturation 0 (left, white) → 255 (right, full hue).
Y axis: value 255 (top, full brightness) → 0 (bottom, black).

Background updates whenever hue changes. Rendered as 168 scanlines:

```cpp
for (int row = 0; row < 168; row++) {
    uint8_t v = (uint8_t)(255 - (row * 255) / 167);   // V: 255 at top, 0 at bottom
    for (int col = 0; col < 168; col++) {
        uint8_t s = (uint8_t)((col * 255) / 167);     // S: 0 at left, 255 at right
        buf[col] = hsvToRgb565(currentHue, s, v);
    }
    tft.pushImage(8, 61 + row, 168, 1, buf);
}
```

168 × 168 = 28 224 pixels. Rendered once on enter and on each hue change.
With `pushImage` row-by-row this is ~50–80 ms — acceptable as a one-shot paint.

**Cursor:** 8×8 px hollow square (2 px border) centred on current (sat, val).
Border colour: white when val > 128, black when val ≤ 128 (contrast).

Touch: full square is the hit zone. Pointer-capture on Press; Move tracks
both X (saturation) and Y (value) clamped to square bounds.

### Live LED preview

On every `onMove` during either drag (hue or SV), call `applyLedColour()`
to write the current HSV immediately to the LED via `ledcWrite`. The physical
LED acts as a live preview at no extra render cost.

---

## Modes

### Off

All three channels set to duty 0. No `tick()` cost.

### Static

Colour set once from stored HSV; no animation. `tick()` is a no-op after
initial write.

```cpp
void applyStatic() {
    auto [r, g, b] = hsvToRgb(g_settings.ledHue, g_settings.ledSat, g_settings.ledVal);
    ledcWrite(LED_R_CH, r);
    ledcWrite(LED_G_CH, g);
    ledcWrite(LED_B_CH, b);
}
```

### Pulse (breathing)

Brightness cycles smoothly 0→val→0 using a sine envelope at ~0.5 Hz.
Hue and saturation stay fixed; only V (brightness) varies.

```cpp
// In LedFlow::tick(), called every frame (~30 Hz):
static float _phase = 0.0f;
_phase += 0.05f;
if (_phase > TWO_PI) _phase -= TWO_PI;
float env = (sinf(_phase) + 1.0f) * 0.5f;    // 0.0 .. 1.0
uint8_t val = (uint8_t)(g_settings.ledVal * env);
auto [r, g, b] = hsvToRgb(g_settings.ledHue, g_settings.ledSat, val);
ledcWrite(LED_R_CH, r);
ledcWrite(LED_G_CH, g);
ledcWrite(LED_B_CH, b);
```

`tick()` uses `lut_sin` (from `mathUtil.h`, ADR-038). Phase step is
`constexpr float`.

### Clock

Colour rotates through a 24-step hue wheel, one step per hour.
At midnight: red. Noon: cyan. 6 AM: yellow-green. 6 PM: blue-violet.
Stored HSV colour is ignored in this mode.

```cpp
// In LedFlow::tick(), updated once per minute:
struct tm t;
if (!getLocalTime(&t)) return;
uint8_t hue = (uint8_t)((t.tm_hour * 256) / 24);
auto [r,g,b] = hsvToRgb(hue, 255, 255);
ledcWrite(LED_R_CH, r);
ledcWrite(LED_G_CH, g);
ledcWrite(LED_B_CH, b);
```

---

## Colour storage (HSV)

Colour is stored as three `uint8_t` HSV components. The previous `colourIdx`
(0..7 predefined swatches) and `brightness` (1..10 scale) fields are removed.

| Field | Range | Default | Notes |
|-------|-------|---------|-------|
| `ledHue` | 0..255 | 85 | 85 ≈ hue 120° = green (prior default colour) |
| `ledSat` | 0..255 | 255 | full saturation |
| `ledVal` | 0..255 | 200 | ~78% brightness |

`hsvToRgb(h, s, v)` maps 0..255 hue to 0..360° internally.

---

## Persistence schema

```json
{
  "led": {
    "mode": "static",
    "hue":  85,
    "sat":  255,
    "val":  200
  }
}
```

`mode` values: `"off"` | `"static"` | `"pulse"` | `"clock"`.

Defaults: `mode="off"`, `hue=85` (green), `sat=255`, `val=200`.

---

## AppSettings struct (LED fields)

Replaces the previous `ledColourIdx` + `ledBrightness` fields in
`settingsStorage.h`:

```cpp
// --- LED ---
LedMode ledMode;
uint8_t ledHue;   // 0..255
uint8_t ledSat;   // 0..255
uint8_t ledVal;   // 0..255 — brightness encoded in V channel
```

---

## Boot application

```cpp
// main.cpp::setup(), after tft.init():
// (SettingsStorage::load() already called earlier — g_settings populated)
ledcSetup(LED_R_CH, 5000, 8); ledcAttachPin(LED_R_PIN, LED_R_CH);
ledcSetup(LED_G_CH, 5000, 8); ledcAttachPin(LED_G_PIN, LED_G_CH);
ledcSetup(LED_B_CH, 5000, 8); ledcAttachPin(LED_B_PIN, LED_B_CH);
g_ledFlow.applyMode();   // applies persisted mode at startup
```

Constants (append to `gen/shell_layout.h` or define in led section header):

```c
#define LED_R_PIN  4
#define LED_G_PIN 16
#define LED_B_PIN 17
#define LED_R_CH   1    // ledc channels (0 = TFT_BL, reserved)
#define LED_G_CH   2
#define LED_B_CH   3
```

---

## LedSection class sketch

```cpp
// app/src/settings/ledSection.h

enum class LedView : uint8_t { List, Picker };

class LedSection : public SettingsSection {
public:
    // SettingsSection contract
    const char*   title()  const override { return "LED"; }   // same in both views
    void          enter()        override;   // reset to List; mirror g_settings HSV
    void          tick()         override;   // Pulse breathing advance; no-op otherwise
    void          repaint()      override;   // dispatch to repaintList() / repaintPicker()
    SectionResult handleInput(TouchPhase phase, int x, int y) override;

private:
    // ---- View state -------------------------------------------------------------
    LedView _view = LedView::List;

    // ---- Mirrored settings (working copies; not committed until Save) -----------
    LedMode _mode = LedMode::Off;
    uint8_t _hue  = 85;
    uint8_t _sat  = 255;
    uint8_t _val  = 200;

    // ---- Picker drag capture ----------------------------------------------------
    bool _svDragging  = false;   // pointer captured by SV square
    bool _hueDragging = false;   // pointer captured by hue strip
    bool _dirty       = false;   // true when working copy differs from g_settings

    // ---- Picker geometry (mirrors layout table in §Colour picker view) ----------
    static constexpr int16_t kBarY   = 28;   // button bar top y (content-relative)
    static constexpr int16_t kPickY  = 61;   // SV square + hue strip top y
    static constexpr int16_t kPickH  = 168;  // square / strip height

    static constexpr int16_t kSvX    =   8;  static constexpr int16_t kSvW = 168;
    static constexpr int16_t kHueX   = 184;  static constexpr int16_t kHueW =  24;

    // ---- Private helpers --------------------------------------------------------
    void repaintList();
    void repaintPicker();

    // Draw the coloured swatch on the list Colour row (16×10 px filled rect).
    void drawColourSwatch(int rowY) const;

    // Draw SV square (168×168 scanlines) for current _hue.
    void drawSvSquare() const;
    // Draw hue strip (24×168 rainbow).
    void drawHueStrip() const;
    // Draw the SV cursor (8×8 hollow square) at (_sat, _val).
    void drawSvCursor() const;
    // Draw the hue cursor (24×3 white bar) at _hue.
    void drawHueCursor() const;
    // Draw the button bar (OFF/ON toggle + SAVE).
    void drawPickerButtons() const;

    // Write current _hue/_sat/_val to LED hardware immediately (live preview).
    void applyLed() const;

    // Clamp a raw touch x/y to SV square bounds and update _sat/_val.
    void svFromTouch(int px, int py);
    // Clamp a raw touch y to hue strip bounds and update _hue.
    void hueFromTouch(int py);
};

// ---------------------------------------------------------------------------

inline void LedSection::enter() {
    _view        = LedView::List;
    _mode        = g_settings.ledMode;
    _hue         = g_settings.ledHue;
    _sat         = g_settings.ledSat;
    _val         = g_settings.ledVal;
    _svDragging  = false;
    _hueDragging = false;
    _dirty       = false;
}

inline void LedSection::tick() {
    // Drive Pulse breathing animation when in picker or list view.
    // The LedFlow singleton also drives it outside settings; here we only need
    // to advance the live preview during an open picker session.
    // Delegated to LedFlow::tick() — no duplicate logic here.
}

inline void LedSection::repaint() {
    drawHeader();
    clearContent();
    if (_view == LedView::List) repaintList();
    else                        repaintPicker();
}

inline void LedSection::repaintList() {
    bool colourActive = (_mode == LedMode::Static || _mode == LedMode::Pulse);

    const char* modeStr = "Off";
    if      (_mode == LedMode::Static) modeStr = "Static";
    else if (_mode == LedMode::Pulse)  modeStr = "Pulse";
    else if (_mode == LedMode::Clock)  modeStr = "Clock";

    // Row 0: Mode  Static >
    int y0 = S_CONTENT_Y;
    drawRow(y0, { "Mode", modeStr, S_LABEL, S_VALUE });

    // Row 1: Colour  [swatch] — greyed when Off or Clock
    int y1 = y0 + S_ROW_H;
    uint16_t swatchCol = colourActive ? S_CHEVRON : S_VALUE_OFF;
    drawRow(y1, { "Colour", "", S_LABEL, swatchCol });
    if (colourActive) drawColourSwatch(y1);

    // Chevron on Colour row (right side indicator)
    tft.setTextDatum(MR_DATUM);
    tft.setTextColor(S_CHEVRON);
    tft.drawString(">", S_COL_VALUE, y1 + S_ROW_H / 2, 2);
    tft.setTextDatum(TL_DATUM);
}

inline void LedSection::repaintPicker() {
    drawPickerButtons();
    drawSvSquare();     // ~50–80 ms one-shot
    drawHueStrip();
    drawSvCursor();
    drawHueCursor();
}

inline SectionResult LedSection::handleInput(TouchPhase phase, int x, int y) {
    // ---- List view input -------------------------------------------------------
    if (_view == LedView::List) {
        if (phase != TouchPhase::Release) return SectionResult::Continue;
        if (isBackTap(x, y)) return SectionResult::GoBack;

        int row = tapToRow(y);
        if (row == 0) {
            // Cycle mode: Off → Static → Pulse → Clock → Off
            _mode = static_cast<LedMode>((static_cast<uint8_t>(_mode) + 1) % 4);
            g_settings.ledMode = _mode;
            saveSettings();
            applyLed();
            clearContent();
            repaintList();
        } else if (row == 1) {
            // Open picker (only useful when colour is active, but always navigable)
            _view  = LedView::Picker;
            _dirty = false;
            clearContent();
            repaintPicker();
        }
        return SectionResult::Continue;
    }

    // ---- Picker view input -----------------------------------------------------

    // SV square — pointer capture
    if (_svDragging) {
        if (phase == TouchPhase::Move) {
            svFromTouch(x, y);
            drawSvCursor();
            applyLed();
        } else if (phase == TouchPhase::Release) {
            svFromTouch(x, y);
            _svDragging = false;
            drawSvCursor();
            applyLed();
            _dirty = true;
        }
        return SectionResult::Continue;
    }

    // Hue strip — pointer capture
    if (_hueDragging) {
        if (phase == TouchPhase::Move) {
            hueFromTouch(y);
            drawHueStrip();
            drawHueCursor();
            drawSvSquare();   // SV background updates on hue change
            drawSvCursor();
            applyLed();
        } else if (phase == TouchPhase::Release) {
            hueFromTouch(y);
            _hueDragging = false;
            drawHueStrip();
            drawHueCursor();
            drawSvSquare();
            drawSvCursor();
            applyLed();
            _dirty = true;
        }
        return SectionResult::Continue;
    }

    // Fresh press — hit test for capture
    if (phase == TouchPhase::Press) {
        Rect svRect  = { kSvX,  kPickY, kSvW,  kPickH };
        Rect hueRect = { kHueX, kPickY, kHueW, kPickH };
        if (hitTest(svRect, x, y)) {
            _svDragging = true;
            svFromTouch(x, y);
            drawSvCursor();
            applyLed();
        } else if (hitTest(hueRect, x, y)) {
            _hueDragging = true;
            hueFromTouch(y);
            drawHueStrip();
            drawHueCursor();
            drawSvSquare();
            drawSvCursor();
            applyLed();
        }
        return SectionResult::Continue;
    }

    if (phase != TouchPhase::Release) return SectionResult::Continue;

    // Release — button bar and back zone
    if (isBackTap(x, y)) {
        // Discard working copy; restore from g_settings
        _hue  = g_settings.ledHue;
        _sat  = g_settings.ledSat;
        _val  = g_settings.ledVal;
        _mode = g_settings.ledMode;
        applyLed();
        _view = LedView::List;
        clearContent();
        repaintList();
        return SectionResult::Continue;   // NOT GoBack — just return to list
    }

    // Button bar hit-test (y: kBarY..kBarY+28)
    Rect barRect = { 0, (int16_t)kBarY, S_CANVAS_W, (int16_t)28 };
    if (!hitTest(barRect, x, y)) return SectionResult::Continue;

    if (x >= 8 && x <= 73) {
        // OFF button
        _mode = LedMode::Off;
        g_settings.ledMode = _mode;
        applyLed();
        _dirty = true;
        drawPickerButtons();
    } else if (x >= 77 && x <= 142) {
        // ON button — restore Static if currently Off
        if (_mode == LedMode::Off) _mode = LedMode::Static;
        g_settings.ledMode = _mode;
        applyLed();
        _dirty = true;
        drawPickerButtons();
    } else if (x >= 200 && x <= 267) {
        // SAVE button — commit HSV + mode to g_settings and persist
        g_settings.ledHue = _hue;
        g_settings.ledSat = _sat;
        g_settings.ledVal = _val;
        g_settings.ledMode = _mode;
        saveSettings();
        _dirty = false;
        // Brief visual confirmation: invert Save button ~100 ms
        tft.fillRect(200, kBarY + 4, 68, 20, S_HDR_TXT);
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(S_BG);
        tft.drawString("SAVE", 234, kBarY + 14, 2);
        tft.setTextDatum(TL_DATUM);
        delay(100);
        drawPickerButtons();
    }

    return SectionResult::Continue;
}

inline void LedSection::svFromTouch(int px, int py) {
    int cx = constrain(px, (int)kSvX, (int)(kSvX + kSvW - 1));
    int cy = constrain(py, (int)kPickY, (int)(kPickY + kPickH - 1));
    _sat = (uint8_t)((cx - kSvX) * 255 / (kSvW - 1));
    _val = (uint8_t)(255 - (cy - kPickY) * 255 / (kPickH - 1));
}

inline void LedSection::hueFromTouch(int py) {
    int cy = constrain(py, (int)kPickY, (int)(kPickY + kPickH - 1));
    _hue = (uint8_t)((cy - kPickY) * 255 / (kPickH - 1));
}

inline void LedSection::applyLed() const {
    // Convert working HSV to RGB and write to ledc channels.
    // Off mode: all channels to 0 regardless of colour.
    if (_mode == LedMode::Off) {
        ledcWrite(LED_R_CH, 0);
        ledcWrite(LED_G_CH, 0);
        ledcWrite(LED_B_CH, 0);
        return;
    }
    auto [r, g, b] = hsvToRgb(_hue, _sat, _val);
    ledcWrite(LED_R_CH, r);
    ledcWrite(LED_G_CH, g);
    ledcWrite(LED_B_CH, b);
}
```

---

## Open questions

1. **Common-cathode vs common-anode** — assumed common-cathode (duty 255 = ON).
   Verify with `ledcWrite(LED_R_CH, 255)` on DUT. If the LED doesn't light,
   the board is common-anode; flip all `ledcWrite` values to `255 - duty`.
   If confirmed common-anode, add `#define LED_ACTIVE_LOW 1` and invert in
   `applyStatic()`.
2. **SV square render cost** — 168×168 px scanline loop is ~50–80 ms as a
   one-shot paint on enter and on hue change. Acceptable. If too slow, cache
   the square as a 16-bit sprite (168×168 × 2 bytes = 56 KB) — likely too
   large for ESP32 SRAM; stick with per-paint.
3. **Pulse sine cost** — `lut_sin` once per frame (~30 Hz). Negligible. If
   `mathUtil.h` unavailable (ADR-038 pending), use triangle wave fallback.
4. **Clock mode update frequency** — gate update: compare `t.tm_hour` to
   `_lastHour`; skip `ledcWrite` if unchanged.
5. **Interaction with NFC** — `nfc.h` may use GPIO16 (LED green channel) for
   PN532 HSPI MISO. Check pin assignment when `NFC_ENABLED` is defined.
6. **Hue strip cursor contrast** — white 3 px bar is visible against all hues
   except near-white (hue=any, low saturation is not on the strip since strip
   is always S=255, V=255). No contrast issue on the strip itself.

---

## Exit criteria

**List view:**
- **C1** — Mode row cycles Off→Static→Pulse→Clock→Off; LED responds immediately.
- **C2** — Colour row shows filled rect in stored colour; greyed when mode=Off or Clock.
- **C3** — Tapping Colour row opens picker; tapping `< back` returns to list without saving.

**Colour picker:**
- **C4** — Hue strip renders full rainbow top-to-bottom; cursor bar tracks drag position.
- **C5** — SV square background updates to reflect selected hue within one repaint cycle.
- **C6** — SV cursor tracks finger during drag; stays within square bounds.
- **C7** — Live preview: LED colour updates during drag (both hue and SV gestures).
- **C8** — On/Off toggle: OFF sets mode=Off and kills LED immediately; ON restores Static.
- **C9** — Save button writes to SPIFFS; button confirms with brief colour inversion (~100 ms).
- **C10** — Unsaved changes are discarded on `< back` (picker re-enters with stored values).

**Persistence:**
- **C11** — Stored HSV survives `ESP.restart()`; mode applied before first frame.
- **C12** — Off mode: all three channels at duty 0; no `tick()` CPU cost.
- **C13** — Pulse: LED breathes smoothly; peak brightness matches stored `ledVal`.
- **C14** — Clock: colour matches expected hue for current hour; updates within 1 minute of boundary.
