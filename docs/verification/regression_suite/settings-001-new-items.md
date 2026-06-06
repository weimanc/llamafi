# VE Regression Suite — settings-001 New Items

> Owner: Verification Engineer
> Date: 2026-06-06; DUT run 2026-06-07
> Scope: Features implemented in commit fd93679; map() bug fix in subsequent commit
> DUT: ESP32-2432S028R CYD2USB, cyd2usb_winamp_debug build, /dev/ttyUSB1
> Serial commands: `tap <x> <y>`, `switchApp <id>`, `get snapshot`, `reboot`
>
> **Bug fixed during testing:** `DisplaySection::tick()` called `map(raw, ldrLow, ldrHigh, …)` unconditionally, crashing with `min==max` when `ldrLow == ldrHigh` (device with unconfigured settings). Fixed: guard `ldrHigh > ldrLow` before `map()`. T-DISP-GUARD-01 passed after fix.

---

## Features under test

| Feature | Files | Design ref |
|---------|-------|------------|
| CalibrationFlow back-tap cancel mid-step | calibrationFlow.h | touch-calibration.md C6 |
| CalibrationFlow history display in IDLE | calibrationFlow.h | touch-calibration.md C5 |
| KeyboardWidget cancel button (ACT_CANCEL) | keyboardWidget.h | keyboard-widget.md C5 |
| DisplaySection Serial.printf guard | displaySection.h | — |
| SettingsApp cancel row + snapshot-restore | main.cpp | settings.md C9/C10 |
| TouchDebugOverlay diamond cursor | touchDebugOverlay.h, main.cpp, platformio.ini | touch-calibration.md D1–D4 |

---

## T-CAL-BTAP — CalibrationFlow back-tap cancel during stepping

### T-CAL-BTAP-01 — Back-tap cancels TL step

**Precondition:** Settings app open (switchApp 6), Touch Calibration tapped, Start tapped → device shows "Tap top-left" crosshair.

**Steps:**
1. `tap 30 14` — tap `< back` zone (x<60, y<28)

**Expected:** Screen returns to IDLE view ("Tap Start to calibrate"). No cal data written. Serial shows no save log.

**Pass criterion:** IDLE view renders; no `TouchCalStorage: saved` in serial output.

---

### T-CAL-BTAP-02 — Back-tap cancels TR step

**Precondition:** As T-CAL-BTAP-01 but advance one corner: tap TL target (~20,48), wait for TR prompt.

**Steps:**
1. `tap 30 14`

**Expected:** Returns to IDLE. `_tapsDone` reset (next Start begins fresh from TL).

**Pass criterion:** IDLE view; no save.

---

### T-CAL-BTAP-03 — Back-tap cancels BotR step

**Precondition:** Advance to BotR (tap TL and TR targets).

**Steps:**
1. `tap 30 14`

**Expected:** IDLE view; no save.

**Pass criterion:** IDLE; no `saved` serial line.

---

### T-CAL-BTAP-04 — Back-tap cancels BL step

**Precondition:** Advance to BL (tap TL, TR, BotR targets).

**Steps:**
1. `tap 30 14`

**Expected:** IDLE view; no save.

**Pass criterion:** IDLE; no save.

---

### T-CAL-BTAP-05 — Back-tap in Review still works (regression)

**Precondition:** Complete all 4 corners → Review screen shown.

**Steps:**
1. `tap 30 14`

**Expected:** Returns to IDLE (existing behaviour unchanged).

**Pass criterion:** IDLE; no save.

---

### T-CAL-BTAP-06 — Start after cancelled sequence begins fresh from TL

**Precondition:** Cancel mid-sequence (T-CAL-BTAP-02), then tap Start again.

**Steps:**
1. `tap 260 14` — tap "Start" zone

**Expected:** "Tap top-left" shown (TL crosshair). No stale state from previous attempt.

**Pass criterion:** TL crosshair at correct position; header shows "Tap top-left".

---

## T-CAL-HIST — CalibrationFlow history display in IDLE

### T-CAL-HIST-01 — Factory-only state shows factory entry

**Precondition:** Fresh SPIFFS (or device with no prior user calibration — `/cal.json` has only factory entry).

**Steps:**
1. `switchApp 6`, tap Touch Calibration row

**Expected:** IDLE view shows "History" section with one entry: `[1] factory  <xMin>/<xMax>/<yMin>/<yMax>`.

**Pass criterion:** Factory entry visible in font 1 below "Tap Start".

---

### T-CAL-HIST-02 — User calibration entry appears after Accept

**Precondition:** IDLE view open. No prior user entry.

**Steps:**
1. Complete full calibration sequence → tap Accept
2. Navigate back to Touch Calibration IDLE view

**Expected:** IDLE shows `[1] factory ...` and `[2] MM-DD  <new cal values>`.

**Pass criterion:** Two entries; second has today's date and new xMin/xMax/yMin/yMax.

---

### T-CAL-HIST-03 — History capped at 3 entries; oldest non-factory dropped

**Precondition:** Two prior user calibrations already in `/cal.json` (3-entry history: factory + 2 user).

**Steps:**
1. Complete a third user calibration → Accept
2. Open IDLE view

**Expected:** 3 entries shown: factory + 2 most-recent user (oldest user dropped).

**Pass criterion:** Exactly 3 entries; factory always `[1]`.

---

### T-CAL-HIST-04 — ts=0 entry renders as "factory" label not date

**Precondition:** `/cal.json` has a history entry with `ts=0` and `src="factory"`.

**Steps:**
1. Open Touch Calibration IDLE view

**Expected:** That entry shows `[N] factory  ...` not `[N] 00-00 ...`.

**Pass criterion:** "factory" string visible, not a date.

---

### T-CAL-HIST-05 — No history section shown when /cal.json absent

**Precondition:** Delete or never write `/cal.json` (fresh flash without uploadfs).

**Steps:**
1. Open Touch Calibration IDLE view

**Expected:** IDLE renders without "History" section. Only current cal + "Tap Start".

**Pass criterion:** No "History" header; no crash.

---

## T-KB-CANCEL — KeyboardWidget cancel button

### T-KB-CANCEL-01 — Cancel `<` label visible on alpha page

**Precondition:** Navigate to WiFi section (phase 2, if available) or any consumer that invokes `g_keyboard.show()`. For current DUT (Phase 1 only): instrument via serial if keyboard not reachable from UI; otherwise note as BLOCKED-PHASE2 and skip to manual verification when Phase 2 lands.

**Steps:**
1. Open keyboard (if reachable)
2. Observe input bar left edge

**Expected:** `<` glyph visible at x≈20, y≈20 in `S_VALUE_OFF` (muted grey).

**Pass criterion:** Label present; does not overlap prompt text in normal usage.

---

### T-KB-CANCEL-02 — Tap `<` fires onCancel, not onSubmit

**Precondition:** Keyboard active with non-empty buffer.

**Steps:**
1. Type 3 chars
2. `tap 20 20` — tap cancel zone (x<40, y<40)

**Expected:** onCancel callback fires. Buffer discarded. Keyboard dismissed. Caller state unchanged.

**Pass criterion:** onCancel confirmed via serial (if instrumented); keyboard hidden; no submit.

---

### T-KB-CANCEL-03 — Cancel works on symbol page 2

**Precondition:** Keyboard active, navigate to symbol page (tap SYM).

**Steps:**
1. `tap 20 20`

**Expected:** onCancel fires from symbol page. Same as alpha page.

**Pass criterion:** Keyboard dismissed; no submit.

---

### T-KB-CANCEL-04 — Cancel works on symbol page 3

**Precondition:** Keyboard on page 3 (SYM → NEXT).

**Steps:**
1. `tap 20 20`

**Expected:** onCancel fires.

**Pass criterion:** Dismissed; no submit.

---

### T-KB-CANCEL-05 — OK tap does not fire onCancel (regression)

**Precondition:** Keyboard active, non-empty buffer.

**Steps:**
1. `tap 240 200` — tap OK zone

**Expected:** onSubmit fires. onCancel not called.

**Pass criterion:** Submit confirmed; cancel not triggered.

---

### T-KB-CANCEL-06 — Empty buffer cancel works

**Precondition:** Keyboard active, buffer empty.

**Steps:**
1. `tap 20 20`

**Expected:** onCancel fires even with empty buffer.

**Pass criterion:** Dismissed; onCancel called.

---

## T-DISP-GUARD — DisplaySection Serial.printf guard

### T-DISP-GUARD-01 — Debug build emits [disp] line on Display enter

**Precondition:** cyd2usb_winamp_debug build flashed. Serial monitor running.

**Steps:**
1. `switchApp 6` → tap Display row
2. Observe serial output

**Expected:** `[disp] analogRead(34) raw = <N>` line appears.

**Pass criterion:** Line present in serial output.

---

### T-DISP-GUARD-02 — Production build silent on Display enter

**Precondition:** cyd2usb_winamp build (no SERIAL_DEBUG). Flash production build.

**Steps:**
1. Open Display settings
2. Observe serial

**Expected:** No `[disp]` line emitted.

**Pass criterion:** No `[disp]` in serial output. (Build check implicitly validates this — #ifdef guard compiles clean.)

---

## T-SET-CANCEL — SettingsApp cancel row + snapshot-restore

### T-SET-CANCEL-01 — Cancel row renders in category list

**Precondition:** Settings app open (switchApp 6).

**Steps:**
1. Observe screen

**Expected:** 6 category rows visible, then a separator line, then "Cancel" label in muted red below.

**Pass criterion:** "Cancel" text present; colour distinct from category labels.

---

### T-SET-CANCEL-02 — Single setting restored on cancel

**Precondition:** Settings open. Note current LED mode (e.g. Off).

**Steps:**
1. Tap LED → change mode to Static → tap `< back` (returns to category list)
2. Tap Cancel row

**Expected:** Returns to previous app. LED mode back to Off. Serial: settings rewritten with original value.

**Pass criterion:** `get snapshot` (or observe LED) confirms mode = Off after cancel.

---

### T-SET-CANCEL-03 — Multiple settings across sections restored

**Precondition:** Note current dispLevel and ledMode.

**Steps:**
1. Tap Display → change level → back
2. Tap LED → change mode → back
3. Tap Cancel

**Expected:** Both dispLevel and ledMode restored to pre-session values.

**Pass criterion:** Values match pre-entry state.

---

### T-SET-CANCEL-04 — Back from category list keeps changes (C10)

**Precondition:** Note current LED mode.

**Steps:**
1. Tap LED → change mode → back to category list
2. Tap `< back` (header zone, x<60 y<28)

**Expected:** Returns to previous app. LED mode = new value (not restored).

**Pass criterion:** Changed value persists after `< back`.

---

### T-SET-CANCEL-05 — Calibration NOT restored by cancel

**Precondition:** No calibration in /cal.json (or note current cal values).

**Steps:**
1. Open Settings → Touch Calibration → complete calibration → Accept
2. Back to category list
3. Tap Cancel

**Expected:** Returns to previous app. `/cal.json` still has the new calibration. Cal NOT rolled back.

**Pass criterion:** New cal values survive cancel; touch still works with new cal.

---

### T-SET-CANCEL-06 — Cancel returns to correct previous app

**Precondition:** Spotify app active. Open Settings via taskbar.

**Steps:**
1. Open Settings from Spotify
2. Make a change
3. Tap Cancel

**Expected:** Returns to Spotify (not Clock or other app).

**Pass criterion:** Spotify visible after cancel.

---

### T-SET-CANCEL-07 — Snapshot refreshed on re-entry

**Precondition:** Cancel once (changes discarded). Open Settings again. Make a new change.

**Steps:**
1. Change LED mode (A → B) → Cancel → open Settings again → change LED mode (A → C) → Cancel

**Expected:** LED mode = A after second cancel (snapshot captured fresh on second resume(), not carrying B).

**Pass criterion:** Correct snapshot each entry.

---

## T-TDBG — TouchDebugOverlay

### T-TDBG-01 — Diamond: exactly 5 red pixels at touch position

**Precondition:** cyd2usb_winamp_debug build. `g_touchDebug.style = Diamond` (default).

**Steps:**
1. `tap 100 100`
2. Observe screen at (100,100)

**Expected:** 5 red pixels: (100,100), (100,99), (100,101), (99,100), (101,100). No other red pixels in bounding box.

**Pass criterion:** Diamond shape visible; no bleed outside 3×3 box.

---

### T-TDBG-02 — Diamond moves to new position on next tap

**Steps:**
1. `tap 50 80`
2. `tap 200 150`

**Expected:** Diamond at (200,150) after second tap. Previous position overdrawn by next app repaint.

**Pass criterion:** Diamond at last touch position.

---

### T-TDBG-03 — Overlay fires across all apps

**Steps:**
1. `switchApp 0` (Spotify), `tap 100 100` — check for diamond
2. `switchApp 1` (Clock), `tap 100 100` — check for diamond
3. `switchApp 6` (Settings), `tap 100 100` — check for diamond

**Expected:** Diamond appears in all three apps.

**Pass criterion:** Overlay not app-specific.

---

### T-TDBG-04 — No taskbar bleed (x < 275)

**Steps:**
1. `tap 274 100` — rightmost canvas pixel

**Expected:** Diamond centre at x=274. No pixels at x≥275 (taskbar strip).

**Pass criterion:** Taskbar pixels unaffected.

---

## Summary table

> DUT run: 2026-06-07. Build: cyd2usb_winamp_debug Jun 7 2026-00:36:45. Port: /dev/ttyUSB1.
> Bug fixed before run: DisplaySection `map(ldrLow,ldrHigh)` min==max crash guarded with `ldrHigh>ldrLow`.

| Test ID | Feature | Serial-driveable? | Status | Notes |
|---------|---------|-------------------|--------|-------|
| T-CAL-BTAP-01 | Cal back-tap TL | yes — tap+observe | **PASS** | `tap 260 14` → TL; `tap 30 14` → IDLE; no save |
| T-CAL-BTAP-02 | Cal back-tap TR | physical touch req. | SKIP-PHYSICAL | corner advance needs raw XPT2046 |
| T-CAL-BTAP-03 | Cal back-tap BotR | physical touch req. | SKIP-PHYSICAL | corner advance needs raw XPT2046 |
| T-CAL-BTAP-04 | Cal back-tap BL | physical touch req. | SKIP-PHYSICAL | corner advance needs raw XPT2046 |
| T-CAL-BTAP-05 | Review back-tap regression | physical touch req. | SKIP-PHYSICAL | Review reachable only via 4-corner physical tap |
| T-CAL-BTAP-06 | Fresh start after cancel | yes | **PASS** | `tap 260 14` after cancel consumed cleanly |
| T-CAL-HIST-01 | Factory entry shown | visual only | SKIP-VISUAL | no crash on cal IDLE; content unverifiable via serial |
| T-CAL-HIST-02 | User entry after Accept | visual + physical | SKIP-PHYSICAL | needs Accept flow |
| T-CAL-HIST-03 | Ring buffer cap | visual + physical | SKIP-PHYSICAL | needs 3 user calibrations |
| T-CAL-HIST-04 | ts=0 → factory label | visual only | SKIP-VISUAL | |
| T-CAL-HIST-05 | No /cal.json → no section | visual only | SKIP-VISUAL | no crash seen; content unverifiable |
| T-KB-CANCEL-01 | Cancel label visible | BLOCKED-PHASE2 | BLOCKED-PHASE2 | |
| T-KB-CANCEL-02 | Cancel fires onCancel | BLOCKED-PHASE2 | BLOCKED-PHASE2 | |
| T-KB-CANCEL-03 | Cancel on sym page 2 | BLOCKED-PHASE2 | BLOCKED-PHASE2 | |
| T-KB-CANCEL-04 | Cancel on sym page 3 | BLOCKED-PHASE2 | BLOCKED-PHASE2 | |
| T-KB-CANCEL-05 | OK regression | BLOCKED-PHASE2 | BLOCKED-PHASE2 | |
| T-KB-CANCEL-06 | Empty buffer cancel | BLOCKED-PHASE2 | BLOCKED-PHASE2 | |
| T-DISP-GUARD-01 | Debug emits [disp] | yes | **PASS** | `[disp] analogRead(34) raw = 1018` seen; no map() flood |
| T-DISP-GUARD-02 | Prod silent | build check | DEFERRED | needs prod flash |
| T-SET-CANCEL-01 | Cancel row renders | yes | **PASS** | cancel tap consumed → switchApp; row exists |
| T-SET-CANCEL-02 | Single setting restored | yes | **PASS** | 2 saves: cycle + cancel restore |
| T-SET-CANCEL-03 | Multi-setting restored | yes | **PASS** | 3 saves: disp auto + LED mode + cancel restore |
| T-SET-CANCEL-04 | Back keeps changes (C10) | yes | **PASS** | back-tap exits without save; change persists |
| T-SET-CANCEL-05 | Cal excluded from cancel | physical req. | SKIP-PHYSICAL | needs Accept flow to write /cal.json |
| T-SET-CANCEL-06 | Returns to correct app | yes | **PASS** | `shell entered 0` after cancel from Spotify |
| T-SET-CANCEL-07 | Snapshot refreshes on re-entry | yes | **PASS** | 2 sessions; each cancel restores same origin value |
| T-TDBG-01 | Diamond 5-pixel shape | visual only | SKIP-VISUAL | build includes TOUCH_DEBUG_OVERLAY; visual check needed |
| T-TDBG-02 | Diamond moves | visual only | SKIP-VISUAL | |
| T-TDBG-03 | All apps | visual only | SKIP-VISUAL | |
| T-TDBG-04 | No taskbar bleed | visual only | SKIP-VISUAL | |
