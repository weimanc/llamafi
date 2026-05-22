# M-MULTIAPP — Clock App Design

> Owner: Architect
> Status: draft
> Date: 2026-05-22
> Part of: [overview.md](overview.md)
> See also: [app-lifecycle.md](app-lifecycle.md), [layout.md](layout.md)
> Source reference: `resource/5in1/5in1 cyberdeck CYD 2.8inch.txt` — `runClock()`

---

## Source algorithm

```cpp
void runClock() {
  if (modeChanged) {
    tft.drawRoundRect(5, 5, 230, 95, 10, 0xF81F);    // pink  — time box
    tft.drawRoundRect(5, 105, 230, 55, 10, 0x07FF);   // cyan  — seconds box
    tft.drawRoundRect(5, 165, 230, 150, 10, 0xFFE0);  // yellow — date box
    modeChanged = false;
  }
  struct tm ti; if(!getLocalTime(&ti)) return;
  static int lsec = -1;
  if (ti.tm_sec != lsec) {
    tft.setTextDatum(MC_DATUM); tft.setTextColor(0xFFFF, TFT_BLACK);
    char tB[10]; sprintf(tB, (ti.tm_sec % 2 == 0) ? "%02d:%02d" : "%02d %02d", ti.tm_hour, ti.tm_min);
    tft.drawString(tB, 120, 50, 6);   // HH:MM, centred in time box
    char dB[20], dyB[20];
    strftime(dB,  20, "%b %d, %Y", &ti);
    strftime(dyB, 20, "%A", &ti);
    tft.drawString(dyB, 120, 200, 4);                          // day name
    tft.setTextColor(0xFFE0, TFT_BLACK);
    tft.drawString(dB, 120, 240, 4);                           // date string
    if (ti.tm_sec == 0) tft.fillRect(10, 115, 220, 35, TFT_BLACK); // rollover clear
    for (int i = 0; i < 60; i++) {
      int xP = 10 + (i * 3.6);
      if (i <= ti.tm_sec) {
        uint8_t h = i * 4.25; uint8_t r,g,b;
        if(h<85){r=255-h*3;g=h*3;b=0;} else if(h<170){h-=85;r=0;g=255-h*3;b=h*3;} else{h-=170;r=h*3;g=0;b=255-h*3;}
        tft.fillRect(xP, 115, 2, 35, tft.color565(r,g,b));
      } else tft.fillRect(xP, 115, 2, 35, 0x2104);
    }
    int32_t rssi = WiFi.RSSI(); int bars = (rssi > -50) ? 4 : (rssi > -70) ? 3 : (rssi > -85) ? 2 : 1;
    for (int i = 0; i < 4; i++) {
      tft.fillRect(100 + (i * 8), 305 - ((i + 1) * 5), 6, (i + 1) * 5, (i < bars) ? 0x07E0 : 0x3186);
    }
    lsec = ti.tm_sec;
  }
}
```

Portrait layout (240×320):

| Element | y centre / range | notes |
|---------|-----------------|-------|
| Time box border | y:5..100 (h=95) | pink |
| HH:MM font 6 | y=50 | MC_DATUM centred x=120 |
| Seconds box border | y:105..160 (h=55) | cyan |
| Seconds bar (60 × 2px) | y=115, h=35 | `xP=10+(i*3.6)` |
| Date box border | y:165..315 (h=150) | yellow |
| Day name font 4 | y=200 | |
| Date string font 4 | y=240 | |
| RSSI bars (4) | x=100..124, y≈285..305 | portrait bottom |

---

## Landscape adaptation

Canvas: **full 275×240** — clock is visually distinct; same rationale as GoL / Matrix.

### Layout strategy

Portrait stacks three boxes in 315/320 px. Landscape has 240 px. Rather than
rearranging into columns, compress the three boxes vertically while keeping
the same structure — preserves source aesthetic with the least redesign.

```
x=5                              x=270    x=275
┌────────────────────────────────┐  y=5
│                                │
│    HH:MM  (font 6, MC_DATUM)  │  time box h=80
│                                │
└────────────────────────────────┘  y=85
                                     y=88  (3 px gap)
┌────────────────────────────────┐
│  [████░░░░░░░░░░░░░░░░░░░░░░] │  seconds box h=47
└────────────────────────────────┘  y=135
                                     y=138  (3 px gap)
┌────────────────────────────────┐
│                                │
│  MONDAY          (font 4)      │  date box h=97
│  May 22, 2026    (font 4)      │
│                       [RSSI]   │
└────────────────────────────────┘  y=235
                                     y=240
```

Verification: 5 + 80 + 3 + 47 + 3 + 97 + 5 = **240** ✓  
All boxes: x=5, w=265 → right edge x=270 (4 px from canvas edge) ✓

### Box `drawRoundRect` calls (landscape)

```cpp
tft.drawRoundRect(5,   5, 265, 80, 10, 0xF81F);  // time box
tft.drawRoundRect(5,  88, 265, 47, 10, 0x07FF);  // seconds box
tft.drawRoundRect(5, 138, 265, 97, 10, 0xFFE0);  // date box
```

### Time string

```cpp
tft.setTextDatum(MC_DATUM);
tft.drawString(tB, 137, 45, 6);   // centred at x=137 (mid-275), y=45 (mid of y:5..85)
```

Font 6 "HH:MM" is ~160 px wide — fits in 265 px box. Height ~48 px — fits in 80 px box.

### Seconds bar

Source: `xP = 10 + (i * 3.6)` spans x=10..222 in a 230 px box.  
Landscape: span x=8..263 in a 265 px box:

```cpp
// Rollover clear
if (ti.tm_sec == 0) tft.fillRect(8, 100, 256, 25, TFT_BLACK);

// 60 segments — rainbow hue formula unchanged from source
for (int i = 0; i < 60; i++) {
    int xP = 8 + (int)(i * 4.3f);   // i=59 → x=261; rect ends at 263
    if (i <= ti.tm_sec) {
        uint8_t h = i * 4.25; uint8_t r, g, b;
        if (h < 85)       { r = 255-h*3; g = h*3;       b = 0; }
        else if (h < 170) { h -= 85; r = 0; g = 255-h*3; b = h*3; }
        else               { h -= 170; r = h*3; g = 0;   b = 255-h*3; }
        tft.fillRect(xP, 100, 2, 25, tft.color565(r, g, b));
    } else {
        tft.fillRect(xP, 100, 2, 25, 0x2104);
    }
}
```

Bar top y=100 (12 px below seconds box top at y=88). Height=25 px (source: 35 px in 55 px box; ours: 25 px in 47 px box — same proportional margin).

### Date strings

```cpp
tft.setTextDatum(MC_DATUM);
tft.setTextColor(0xFFFF, TFT_BLACK);
tft.drawString(dyB, 137, 170, 4);   // day name
tft.setTextColor(0xFFE0, TFT_BLACK);
tft.drawString(dB,  137, 200, 4);   // date string
```

### RSSI bars

Source places bars at portrait bottom (y≈285..305). Landscape: date box
bottom is y=235. Relocate to bottom-right of date box:

```cpp
int32_t rssi = WiFi.RSSI();
int bars = (rssi > -50) ? 4 : (rssi > -70) ? 3 : (rssi > -85) ? 2 : 1;
for (int i = 0; i < 4; i++) {
    tft.fillRect(240 + (i * 8), 228 - ((i + 1) * 5), 6, (i + 1) * 5,
                 (i < bars) ? 0x07E0 : 0x3186);
}
// Bars: x=240,248,256,264. Heights 5,10,15,20 px. Bottom y=228.
// Tallest bar top: 228-20=208. All within date box (y=138..235). ✓
```

---

## State

```cpp
struct ClockAppState {
    bool initialised;   // triggers chrome repaint on first launch
};
```

Stateless beyond `initialised` — `getLocalTime()` always returns current time.
`restoreAppState` is a full repaint (same as `initAppState` minus the chrome draw if already painted — but since switchApp clears the canvas, always draw chrome).

---

## clockDrawChrome() / repaintApp(Clock)

```cpp
void clockDrawChrome() {
    tft.drawRoundRect(5,   5, 265, 80, 10, 0xF81F);
    tft.drawRoundRect(5,  88, 265, 47, 10, 0x07FF);
    tft.drawRoundRect(5, 138, 265, 97, 10, 0xFFE0);
}

void repaintClock(ClockAppState &s) {
    tft.fillRect(0, 0, 275, 240, TFT_BLACK);  // redundant after switchApp but safe
    clockDrawChrome();
    struct tm ti;
    if (getLocalTime(&ti)) repaintClockContent(ti);
}
```

`repaintClockContent(ti)` is the per-second update block above (time string,
seconds bar, date strings, RSSI).

---

## appTick integration

```cpp
void clockTick() {
    struct tm ti;
    if (!getLocalTime(&ti)) return;
    static int lsec = -1;
    if (ti.tm_sec == lsec) return;
    lsec = ti.tm_sec;
    repaintClockContent(ti);
}
```

`lsec` retains its value across app switches. On restore, if the second has
changed (always true after >1 s away), the first tick fires immediately and
repaints. Desired — same pattern as Matrix's `lastMs`.

---

## Touch input

No clock-specific touch response. Taps on the clock canvas (x < `TASKBAR_X`)
fall through without action — taskbar already handles app switching.

Clock is informational; no interaction is natural.

---

## Constants

```cpp
#define CLOCK_TIME_BOX_Y      5
#define CLOCK_TIME_BOX_H     80
#define CLOCK_TIME_STR_X    137    // MC_DATUM centre x
#define CLOCK_TIME_STR_Y     45    // MC_DATUM centre y
#define CLOCK_SEC_BOX_Y      88
#define CLOCK_SEC_BOX_H      47
#define CLOCK_BAR_Y         100    // seconds bar top
#define CLOCK_BAR_H          25    // seconds bar height
#define CLOCK_BAR_X0          8    // first segment x
#define CLOCK_BAR_STRIDE    4.3f   // pixels per segment (float)
#define CLOCK_DATE_BOX_Y    138
#define CLOCK_DATE_BOX_H     97
#define CLOCK_DAY_STR_Y     170
#define CLOCK_DATE_STR_Y    200
#define CLOCK_RSSI_X0       240    // leftmost RSSI bar x
#define CLOCK_RSSI_BOTTOM   228    // RSSI bar bottom y
#define CLOCK_BOX_W         265    // all three boxes share this width
#define CLOCK_BOX_X           5    // all three boxes share this x
```

---

## Open questions

None. All layout dimensions calculated. Source algorithm ports verbatim with
coordinate substitutions only.

---

## Exit criteria

- **C1** — Chrome boxes rendered without pixel outside x:0..274, y:0..239.
  Rightmost box edge: x=5+265=270. Bottom box edge: y=138+97=235. Both within canvas.
- **C2** — Seconds bar segments confined within seconds box (y=88..135).
  Bar bottom: y=100+25=125 < 135. Bar rightmost: x=261+2=263 < 270. ✓
- **C3** — Blinking colon: `%02d:%02d` on even seconds, `%02d %02d` on odd.
  Confirmed over 60-second observation.
- **C4** — Bar rollover: at `tm_sec==0` all 60 segments draw dark before
  refilling on subsequent seconds.
- **C5** — App switch: Spotify → Clock → Spotify. Winamp chrome pixel-correct
  after two `switchApp()` calls; no clock box residue.
- **C6** — Restore: correct current time displayed within one tick of switch-in.
