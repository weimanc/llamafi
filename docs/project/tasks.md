# Task Tracker

> Owner: Project Manager

Tasks ref feature IDs + git branches/commits for traceability. Agents report status changes to PM; keeps file current.

> **PM sync 2026-06-06** — 5 open tasks from settings-001 DUT feedback (T150–T154).
> Completed and closed tasks are in [tasks-archive.md](tasks-archive.md).

---

## Open Tasks — settings-001 DUT Bugs & Polish

### TASK-150 — Fix backlight PWM: LEDC channel setup
- **Feature:** settings-001 / display-settings
- **Priority:** P1 — blocker (Level slider completely non-functional)
- **Status:** open
- **Opened:** 2026-06-06 (DUT feedback)
- **Root cause:** Design spec assumed TFT_eSPI sets up LEDC channel 0 for GPIO21
  (TFT_BL). Actual TFT_eSPI build (`TFT_BL + TFT_BACKLIGHT_ON` flags, no `LEDC_CHANNEL`
  define) uses `digitalWrite(TFT_BL, HIGH)` — plain digital, no LEDC setup.
  `ledcWrite(0, duty)` in `DisplaySection::_applyBrightness()` writes to an
  unattached channel → no effect on display brightness.
- **Fix:** In `main.cpp::setup()`, after `tft.init()` and before first `_applyBrightness`
  call, add:
  ```cpp
  ledcSetup(0, 5000, 8);          // 5 kHz, 8-bit PWM
  ledcAttachPin(TFT_BL, 0);       // take over GPIO21 from TFT_eSPI digital hold
  ```
  This is idempotent if called once. Consider a named constant `BACKLIGHT_LEDC_CH = 0`.
  Also apply stored brightness immediately after:
  ```cpp
  ledcWrite(0, map(constrain(g_settings.dispLevel,1,10),1,10,25,255));
  ```
- **Spec update:** Close open question 3 in `display-settings.md`; correct the
  "TFT_eSPI claims ledc channel 0 at init" assumption.
- **Validation:** T-DISP-01 (drag slider → visible brightness change), T-DISP-04
  (persisted level applied at boot — no startup flash).
- **Owner:** Developer

---

### TASK-151 — Investigate LDR: always reads 0 on DUT
- **Feature:** settings-001 / display-settings
- **Priority:** P2
- **Status:** partial — probe implemented; root cause unresolved
- **Opened:** 2026-06-06 (DUT feedback)
- **Symptoms:** Display section "LDR" row always shows 0. Covering/uncovering the
  sensor has no effect on the displayed value.
- **Investigation steps:**
  1. Add `Serial.printf("[disp] analogRead(34) = %d\n", analogRead(34));` temporarily
     in `DisplaySection::enter()` to confirm raw hardware value.
  2. If 0: check whether GPIO34 needs `pinMode(34, INPUT)` before `analogRead` on
     this board/framework version. Also check `analogReadResolution(12)` in setup().
  3. Check CYD hardware: GPIO34 is LDR on ESP32-2432S028R variants. Confirm 2-USB
     variant uses same pin (not relocated vs single-USB variant).
  4. Verify `tick()` updates display: `_repaintLdrRows()` is only called when
     `|fresh - _ldrRaw| > 20`. On entry, `_ldrRaw` is set from `analogRead(34)`.
     If ADC always returns 0, the dead-band condition never triggers → display shows
     whatever was painted in `enter()`.
- **Note:** Design open question 1 ("LDR wiring polarity") is still open — if brighter
  ambient produces LOWER ADC value, the auto-brightness mapping is inverted.
- **Validation:** T-DISP-02 (covering LDR dims display), T-DISP-03 (live row updates).
- **Owner:** Developer

---

### TASK-152 — Rename LDR calibration rows; clarify purpose
- **Feature:** settings-001 / display-settings
- **Priority:** P3 (UX clarity)
- **Status:** implemented — check_build.sh PASS; visual DUT check pending
- **Opened:** 2026-06-06 (DUT feedback — "what is LDR Low High for?")
- **Change:** In `_repaintLdrRows()`:
  - Add an "Auto range" sub-section header above the two calibration rows
    (draw at `S_CONTENT_Y + 2*S_ROW_H` using `tft.drawString(S_SUBHDR)` + rule).
  - Rename "LDR Low" → "Dark floor" and "LDR High" → "Bright ceiling".
  - Move LDR live reading to a row labelled "LDR" under its own line, visible
    always (current impl already has this row; just ensure it's labelled clearly).
  - Adjust row-count math: sub-header adds S_ROW_HDR_H (22px) above the two
    calibration rows — total height is still within 212px panel
    (row0 26 + row1 26 + ldr_live 26 + subhdr 22 + dark 26 + bright 26 = 152px ✓).
- **Validation:** Visual — DUT Display section clearly communicates row purpose.
  No serial test needed; check_build.sh must pass.
- **Owner:** Developer

---

### TASK-153 — City picker: scrollbar drag gesture
- **Feature:** settings-001 / time-settings
- **Priority:** P2 (UX — 78 cities, 13 pages via button-only is slow)
- **Status:** open
- **Opened:** 2026-06-06 (DUT feedback)
- **Scope:** Phase 1 design explicitly deferred drag (open question 4 in
  `time-settings.md`). Promote to in-scope based on DUT feedback.
- **Design:** Pointer-capture pattern (same as SliderWidget):
  - `handleInput` now handles `TouchPhase::Press/Move/Release` (not just Release).
  - On Press in `px >= kSbX` (scrollbar zone), above `kSbUpY1` and below `kSbDnY0`
    (thumb track): record `_sbDragAnchorY = py` and `_sbDragAnchorOffset = _cityOffset`.
    Set `_sbDragging = true`.
  - On Move with `_sbDragging`: compute delta = `(py - _sbDragAnchorY)` mapped to
    city-index delta using track height and city count. Update `_cityOffset`.
    Repaint picker (full or scrollbar-only).
  - On Release: commit `_cityOffset`; clear `_sbDragging`.
  - On Press in ▲/▼ button zones: existing tap logic (only on Release still fine —
    or change to Press for snappier response).
- **Member additions to TimeSection:**
  ```cpp
  bool    _sbDragging        = false;
  int16_t _sbDragAnchorY     = 0;
  uint8_t _sbDragAnchorOffset = 0;
  ```
- **Spec update:** Close open question 4 in `time-settings.md`.
- **Validation:** T-CITY-DRAG-01 (new test): drag scrollbar thumb moves city list
  proportionally; release commits. VE to add to settings-sections-001 suite.
- **Owner:** Developer

---

### TASK-154 — City picker: UTC offset prefix column + group separators
- **Feature:** settings-001 / time-settings
- **Priority:** P2 (UX — user can't tell offset at a glance)
- **Status:** implemented — check_build.sh PASS; serial navigation PASS (ad7d104); T-CITY-OFFSET-01 visual DUT check pending
- **Opened:** 2026-06-06 (DUT feedback)
- **Design changes required:**

  **1. CityEntry struct** (`cities.h`): Add offset fields:
  ```cpp
  struct CityEntry {
      const char* city;
      const char* country;
      float       lat;
      float       lon;
      const char* posixTz;
      const char* tzName;
      int8_t      utcHours;    // e.g. +9, -5, 0  (signed, whole hours part)
      uint8_t     utcMins;     // 0, 30, or 45
      bool        groupBreak;  // true = first city in a new UTC offset group
  };
  ```
  Populate all 78 rows. Reference: current cities.h comments already group by
  UTC offset, so `groupBreak` is a mechanical annotation.

  **2. UTC offset display string** — helper in `timeSection.h`:
  ```cpp
  // Fills buf with e.g. "+12", " +9", "+9:30", " -5", " +0"
  // Right-aligns the hours digit at a fixed column position.
  static void fmtUtcOffset(char* buf, int len, int8_t h, uint8_t m) {
      if (m == 0)
          snprintf(buf, len, "%+3d", (int)h);      // "+12" or " -5" or " +0"
      else
          snprintf(buf, len, "%+d:%02d", (int)h, (int)m);  // "+9:30"
  }
  ```
  Note: `½` not used — `:30`/`:45` is clear and ASCII-safe.

  **3. City picker row layout** — revise `_repaintPicker()`:
  ```
  x=8      x=52    x=60          x=246   x=250..256
  |UTC off |  sep  | City name   | CC     |
  " +9"        "  Tokyo         JP"
  "+9:30"      "  Adelaide      AU"    ← first in UTC+9:30 group
  ```
  - UTC offset column: x=8..50, MR_DATUM, font 2 (small)
  - Vertical separator line: x=54, height of row, colour S_SEP
  - City name: x=58, ML_DATUM, font 2
  - Country: x=246 (before scrollbar at 257), MR_DATUM, font 2

  **4. Group separator** — before rendering a `groupBreak=true` city row, draw a
  1px horizontal line at the top of that row (colour S_SEP, x=8..256). This
  signals a UTC offset transition visually without requiring a header row.

  **5. Row width** — all city text stays within x<257 (scrollbar at x=257).

- **Spec update:** Update `time-settings.md` §City picker, §CityEntry struct.
- **Validation:** T-CITY-OFFSET-01 (new): picker shows UTC offset for each row;
  group breaks visible. T-TIME-01 unblocked (city selection unchanged). VE to
  add to settings-sections-001 suite.
- **Owner:** Architect (spec update for CityEntry) + Developer (implementation).
