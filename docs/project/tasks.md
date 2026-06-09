# Task Tracker

> Owner: Project Manager

Tasks ref feature IDs + git branches/commits for traceability. Agents report status changes to PM; keeps file current.

> **PM sync 2026-06-09 (end of session)** — Roadmap retrofitted (6 missing milestones added,
> 3 superseded proposal docs deleted). M-SETUP-WIZARD designed: `run/setup` wizard, SPIFFS
> primary WiFi path, PATCH-003 registered in upstream-patches.md (not yet applied).
> SPIFFS hygiene: live DUT dump confirmed partition layout + file inventory; TASK-160/161/162
> filed. TASK-161 (`run/spiffs` non-destructive manager) is P1 blocker for M-SETUP-WIZARD.
> DUT visual verify batch closed 2026-06-09: TASK-150 (backlight PWM) PASS, TASK-152 (LDR row
> rename) PASS, TASK-153 (city picker drag) PASS, TASK-154 (UTC offset column) PASS.
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
- **Design audit:** all 6 features strong-match spec

### TASK-155 — KB cancel `<` press-highlight
- **Commit:** `3962903`
- **Status:** done — input-bar repaint path fixed; `cancelPressed` check added to `repaintInputBar()`
- **Validation:** BLOCKED-PHASE2 (full visual confirm when keyboard reachable)

---

## Open Tasks — ADR-042 Harness & Firmware Follow-on

### TASK-156 — E3 harness refactor: wrap affected tests in `_bgpoll_suspended`, cut sleep budget
- **Related:** ADR-042 E3, `docs/process/harness_sync_contract.md`
- **Priority:** P1 — remaining ADR-042 exit criterion
- **Status:** done — 5/5 targeted runs, zero FAILs, no retry triggered
- **Opened:** 2026-06-08
- **VE results (2026-06-08, 5 runs):**

  | Test | R1 | R2 | R3 | R4 | R5 |
  |---|---|---|---|---|---|
  | T_WX_01 | PASS | PASS | PASS | PASS | PASS |
  | T_CX_01 | PASS | PASS | PASS | PASS | PASS |
  | T-BUSY-01b | SKIP | SKIP | PASS | SKIP | SKIP |
  | T-BUSY-05 | PASS | PASS | PASS | PASS | PASS |
  | T-CDWN-02 | SKIP | PASS | PASS | PASS | PASS |
  | T-CDWN-03 | PASS | PASS | PASS | PASS | PASS |

  T-BUSY-01b SKIPs: cold Yahoo Finance TLS >45 s (pre-existing network condition).
  T-CDWN-02 SKIP R1: warm connection cleared before tap2 (preserved skip path, correct).
  No retry branches triggered across all 5 runs.

- **Sleep budget (static grep, post-refactor):** T-BUSY-01 0.40 + T-BUSY-01b 0.70 + T-CDWN-02 1.30 + T169 3.00 = 5.40 s. Drops to 2.40 s after TASK-157 (T169 retry removal). ≤ 4 s criterion requires TASK-157.
- **Owner:** Developer (harness) / VE (verify run)

---

### TASK-157 — Remove E1-redundant retry loops: T169, T-BUSY-03
- **Related:** ADR-042 E1, commit bfe6320
- **Priority:** P2 — dead-code cleanup; E1 log suppression makes these loops unnecessary
- **Status:** done — retry loops removed; T-BUSY-03 PASS, T169 SKIP (no track, expected precondition)
- **Opened:** 2026-06-08
- **Root cause resolved:** E1 HTTPClient log suppression eliminates the Core 0/Core 1 UART race
  that caused garbled `switchApp` responses. Retry branches are dead code. Removed.
- **Changes:** T169 converted to single-attempt with `_bgpoll_suspended`; T-BUSY-03 inner loop
  simplified — blind 3 s sleep and retry removed, `_bgpoll_suspended` context used instead.

---

### TASK-158 — Firmware: taskbar scroll failures (T163, T165)
- **Priority:** P1
- **Status:** done — T162–T166 all PASS (1 DUT run, 5/5)
- **Opened:** 2026-06-08
- **Root causes:**
  1. `drainInjectionQueue` was routing all injected touch samples through `handleWinampInput`
     instead of the taskbar gesture API (`tbGesturePress/Continue/End`). Fixed: samples with
     `sx >= TASKBAR_X` now route to the gesture API.
  2. `appHandleInput` fired `tbGestureEnd` on the physical `!touched` branch even during an
     active serial drag injection, cancelling the gesture early. Fixed: guard with
     `!winampDisplay._injectingDrag` (`#ifdef SERIAL_DEBUG` only).
  3. `_TB_N` in the test harness was stale (`APP_COUNT - 1 = 8`) from when there were 8 apps.
     All 9 apps are in the taskbar; firmware correctly uses `AppId::COUNT = 9`. Fixed:
     `_TB_N = APP_COUNT` (= 9).
- **VE results (2026-06-08, 1 DUT run):** T162 PASS, T163 PASS, T164 PASS, T165 PASS, T166 PASS.

---

### TASK-159 — Firmware: settings navigation failures (T-SET-03, T-SET-07)
- **Priority:** P1
- **Status:** done — T-SET-03 PASS, T-SET-07 PASS
- **Opened:** 2026-06-08
- **Root cause:** `SettingsApp::dbgGet` did not handle `settingsAppSubmenu` query — the harness
  could not read the `AppsSection` submenu depth. Added handler returning `_apps.submenu()`.
  Added `submenu()` accessor to `AppsSection`.
- **VE results (2026-06-08):** T-SET-03 PASS, T-SET-07 PASS.

---

## Open Tasks — settings-001 DUT Bugs & Polish

### TASK-150 — Fix backlight PWM: LEDC channel setup
- **Feature:** settings-001 / display-settings
- **Priority:** P1
- **Status:** done — T-DISP-01 PASS (2026-06-09 DUT). Slider controls brightness ✓.
- **Opened:** 2026-06-06 (DUT feedback)
- **VE results (2026-06-09):**
  - T-DISP-01: slider drag changes backlight duty — PASS
  - T-DISP-04 (boot persistence): deferred — requires physical reset sit
  - Auto-brightness (T-DISP-02/03): confirmed functional on DUT ✓ (see additional fixes below)
- **Additional fixes applied 2026-06-09 during DUT session:**
  1. LDR polarity inverted — this hardware reads low ADC in ambient, high ADC when covered.
     `map(..., 1, 10)` changed to `map(..., 10, 1)` in auto tick.
  2. Hardware-correct defaults: `ldrLow=0`, `ldrHigh=120` (was 200/3800 — wrong for this device).
  3. Settings migration: old saves with `ldrHigh==0` reset to 120 on load.
  4. Auto-brightness now maps LDR directly to 8-bit PWM duty (25–255), bypassing
     the 10-step slider abstraction. Hysteresis threshold: 3 PWM units.
  5. Cal rows changed from read-only to tap-to-capture:
     `Cal: bright` (tap in ambient) → stores ldrLow; `Cal: dark` (tap while covering) → stores ldrHigh.
     Guard prevents Cal: dark storing an invalid low reading.
- **Owner:** Developer

---

### TASK-151 — Investigate LDR: always reads 0 on DUT
- **Feature:** settings-001 / display-settings
- **Priority:** P2
- **Status:** closed — resolved in TASK-150 DUT session (2026-06-09)
- **Resolution (corrected 2026-06-09):** Previous note (2026-06-07: "1018/1404, no inversion")
  was wrong — likely measured under different firmware/conditions. Actual hardware behaviour:
  ambient light → ADC ≈ 0; fully covered → ADC ≈ 140+. Polarity IS inverted (low ADC = bright).
  All fixes applied in TASK-150.

---

### TASK-152 — Rename LDR calibration rows; clarify purpose
- **Feature:** settings-001 / display-settings
- **Priority:** P3 (UX clarity)
- **Status:** done — DUT confirmed 2026-06-09. Labels "Cal: bright" / "Cal: dark", sub-header "Calibration" visible. Rows are tap-to-capture (implemented as part of TASK-150 LDR fixes).
- **Opened:** 2026-06-06 (DUT feedback — "what is LDR Low High for?")

---

### TASK-153 — City picker: scrollbar drag gesture
- **Feature:** settings-001 / time-settings
- **Priority:** P2 (UX — 78 cities, 13 pages via button-only is slow)
- **Status:** done — T-CITY-DRAG-01 PASS (2026-06-09 DUT). Scrollbar drag scrolls city list proportionally ✓.
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
- **Status:** done — T-CITY-OFFSET-01 PASS (2026-06-09 DUT). UTC offset column + group separators visible ✓.
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

## Open Tasks — SPIFFS hygiene

### TASK-160 — Retire `host_overrides.json` DNS-override path

`dnsOverride.h` + `host_overrides.json` was a one-off field hack (AT&T cellular tether, Marriott portal, 2026-05-05/06). It was never regression-tested; the VE backlog item was never closed. The IPs in the current SPIFFS dump are stale (CDN GSLB rotates every few hours/days). The path is dev-only and has no place in a production or published project.

- Remove `dnsOverride.h` from `app/src/` and its `#include` from `main.cpp`.
- Remove `tools/refresh_host_overrides.sh`.
- Remove `app/data/host_overrides.json` (gitignored, but document removal).
- Update `.gitignore`: drop `app/data/host_overrides.json` entry (will be covered by `app/data/*` wildcard once TASK-161 lands).
- Update `CLAUDE.md` §DNS override section — replace with a brief note: removed, was dev-only hack.
- VE: confirm build clean; DUT boots and connects normally without the file.

**Priority:** P2  
**Status:** not started  
**Opened:** 2026-06-09  
**Owner:** Developer  

---

### TASK-161 — `run/spiffs`: non-destructive SPIFFS file manager

Current `run/flash-fs` formats the entire SPIFFS partition before writing, silently wiping runtime-written files (`/settings.json`, `/cal.json`, `/drd.dat`). This is unacceptable once users have configured settings or performed touch calibration.

Replace the blanket-upload model with a read–inspect–selective-write workflow using `esptool.py` (already in PlatformIO) and `mkspiffs_espressif32_arduino` (already in PlatformIO).

Confirmed working via live DUT dump (2026-06-09):
- Partition: `spiffs` at `0x290000`, size `0x160000`
- `mkspiffs` default params match the device (no `-b`/`-p` flags needed)
- 5 files on device: `spotify_diy_config.json`, `host_overrides.json`, `cal.json`, `settings.json`, `drd.dat`

**Subcommands:**

```sh
./run/spiffs ls               # list all files on device with sizes
./run/spiffs pull             # extract all files → app/data/spiffs-dump/ (read-only, non-destructive)
./run/spiffs pull <file>      # extract single file → stdout or app/data/spiffs-dump/<file>
./run/spiffs push <file>      # read-modify-write: update single file, all others preserved
./run/spiffs push             # merge app/data/ into live SPIFFS (read-modify-write, no format)
./run/spiffs rm <file>        # remove single file from SPIFFS (read-modify-write)
```

**Implementation:** shell script wrapping `esptool.py read_flash` → `mkspiffs -u` → modify → `mkspiffs -c` → `esptool.py write_flash`. Resolves port via `run/lib.sh`. Kills/restores monitor.

**`run/flash-fs` fate:** deprecate in favour of `run/spiffs push`; keep as escape hatch for corrupted filesystem (add a `--format` flag or separate `run/spiffs format`).

**Docs to update:** `project_run_scripts.md`, `CLAUDE.md`, `dut_workflow.md`, `README.md`.

**Priority:** P1 — blocks M-SETUP-WIZARD implementation (setup wizard must not wipe cal/settings)  
**Status:** not started  
**Opened:** 2026-06-09  
**Deps:** TASK-160 (retire host_overrides path before designing the managed file set)  
**Owner:** Developer  

---

### TASK-162 — Update `.gitignore`: `app/data/*` wildcard + `.gitkeep`

Currently `.gitignore` names credential files individually (`app/data/spotify_diy_config.json`, `app/data/host_overrides.json`). Any new credential or runtime file needs a manual entry — a silent footgun.

Replace with a directory-level wildcard:
```gitignore
# app/data/ — runtime credentials and data; never commit
app/data/*
!app/data/.gitkeep
```

Add `app/data/.gitkeep` to keep the directory tracked on a clean clone.
Remove the now-redundant named entries.

**Priority:** P2  
**Status:** not started  
**Opened:** 2026-06-09  
**Deps:** TASK-160 (retire host_overrides so we're not gitignoring a removed file)  
**Owner:** Developer  
