# Task Tracker

> Owner: Project Manager

Tasks ref feature IDs + git branches/commits for traceability. Agents report status changes to PM; keeps file current.

> **PM sync 2026-06-07** — settings-001 new-items feature set complete (fd93679, c07c903).
> VE DUT run complete: 8 PASS, physical/visual deferred, BLOCKED-PHASE2 KB tests pending Phase 2.
> TASK-151 closed (LDR confirmed working). TASK-155 opened (KB symbol-page highlight bug).
> Open: TASK-150, TASK-152 (visual confirm pending), TASK-153, TASK-154 (visual confirm pending), TASK-155.
> Completed and closed tasks are in [tasks-archive.md](tasks-archive.md).

---

## Closed This Cycle

### settings-001 new-items — Cancel button, cal history, KB ESC, TouchDebugOverlay
- **Commits:** `fd93679` (feat), `c07c903` (bug fix + VE results)
- **Status:** done — all 6 new-items features implemented and design-audited
- **VE suite:** `docs/verification/regression_suite/settings-001-new-items.md`
  - 8 serial-driven tests: PASS
  - Physical (cal corner taps) + visual (TDBG, cal history): deferred — require person at screen
  - KB cancel: BLOCKED-PHASE2 (keyboard not reachable until WiFi Phase 2)
  - Bug found and fixed during VE: `DisplaySection::tick()` map() crash when `ldrLow==ldrHigh`
- **Design audit:** all 6 features strong-match spec; one medium gap: KB symbol-page press-highlight bug (TASK-155)

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
- **Status:** ~~closed~~ — LDR confirmed working on 2026-06-07 DUT run
- **Resolution:** Serial probe (`[disp] analogRead(34) raw = 1018` / `raw = 1404`) confirmed
  LDR reads non-zero values. Original "always 0" symptom was pre-Serial-guard (values not
  visible). Polarity open question: higher ambient → higher ADC (1018–1404 range observed
  in normal indoor light). No inversion. T-DISP-02/03 (covering LDR, live row update) remain
  as deferred visual DUT checks but are no longer blocking.
- **Remaining:** `ldrLow/ldrHigh` defaults (200/3800) are appropriate for this device; no fix needed.

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

---

### TASK-155 — KeyboardWidget symbol-page (row 3) press-highlight broken
- **Feature:** settings-001 / keyboard-widget
- **Priority:** P3 (visual feedback only — functional cancel still works)
- **Status:** open
- **Opened:** 2026-06-07 (design-vs-impl audit)
- **Root cause:** `_pressColForXY()` returns wrong column index for symbol-page row 3 action
  keys (SYM/NEXT/SPACE/OK area). Keys are never highlighted on Press — only on Release after
  the action fires. This means the Cancel `<` label and action-row keys show no press feedback
  on symbol pages.
- **Scope:** Visual feedback only. `ACT_CANCEL` routes correctly and `onCancel` fires correctly
  on all pages. No regression to functional behaviour.
- **Fix:** Audit `_pressColForXY()` for symbol page layout constants; ensure row 3 returns
  the correct column offset so `_pressHighlight` is set before rendering.
- **Note:** Documented in `docs/architecture/designs/M-MULTIAPP/keyboard-widget.md` as a
  known press-highlight bug. Full testing gated on Phase 2 (WiFi keyboard reachable from UI).
- **Validation:** T-KB-CANCEL-01..06 (BLOCKED-PHASE2); visual confirm when Phase 2 lands.
- **Owner:** Developer
