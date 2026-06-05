# Task Tracker

> Owner: Project Manager

Tasks ref feature IDs + git branches/commits for traceability. Agents report status changes to PM; keeps file current.


### TASK-141 — M-SETTINGS: SettingsApp navigation stub
**Owner**: Developer
**Feature**: settings-001 (new)
**Status**: implemented — check_build.sh 4/4; DUT smoke pending (TASK-141d)
**Milestone**: M-SETTINGS-STUB
**Design**: `docs/architecture/designs/M-MULTIAPP/settings.md`
**Blocks**: TASK-142 (VE can't execute without stub), all per-section implementation tasks

Implements the navigation shell only — category list, header, back logic, and stub section
content. No live section implementations (WiFi flow, display settings, etc.). Exit criteria
C1–C6 from settings.md. C7 (WifiFlow / CalibrationFlow take-over) deferred to per-section tasks.

Sub-tasks (implement in order; each must compile before proceeding):

- **TASK-141a** — Constants + `g_previousAppId`:
  - Add settings constants directly in `main.cpp` above `SettingsApp` (same pattern as
    StockApp's `ST_*` constants — do NOT add to `gen/shell_layout.h`, would invalidate golden hash):
    ```c
    #define SETTINGS_HEADER_H         28
    #define SETTINGS_CONTENT_Y        28
    #define SETTINGS_CONTENT_H       212    // 240 - SETTINGS_HEADER_H
    #define SETTINGS_CAT_COUNT         6
    #define SETTINGS_ROW_H            26    // matches ST_LIST_ROW_H
    #define SETTINGS_ROW_COL_LABEL     8
    #define SETTINGS_ROW_COL_VALUE   268
    #define SETTINGS_ROW_MAX           8
    #define SETTINGS_BG_RGB565      0x2104
    #define SETTINGS_SEP_COLOR      0x4208
    #define SETTINGS_HEADER_TXT     0xFFFF
    #define SETTINGS_LABEL_COLOR    0xFFFF
    #define SETTINGS_VALUE_COLOR    0x07FF  // cyan
    #define SETTINGS_CHEVRON_COLOR  0x4208
    ```
  - Add `static AppId g_previousAppId = AppId::Spotify;` (after `currentAppId` declaration).
  - In `switchApp()`, before `currentAppId = next`:
    `if (next == AppId::Settings) g_previousAppId = currentAppId;`

- **TASK-141b** — Expand `SettingsApp` class (replace the current placeholder):
  - Private `struct State { int8_t section = -1; int8_t appSubmenu = -1; } _s;`
  - `repaintHeader(const char* title)` — fills header row, `"< back"` left, title right,
    separator at y=SETTINGS_HEADER_H-1. Reset to `TL_DATUM` on exit.
  - `repaintCategoryList()` — calls `repaintHeader("Settings")`; fills content panel;
    6 rows with label (ML_DATUM) + `">"` chevron (MR_DATUM); reset to `TL_DATUM` on exit.
  - `repaintSection()` — dispatches on `_s.section`:
    - section 5 → `repaintSectionApps()`;
    - sections 0–4 → stub: `repaintHeader(sectionLabel)` + centred `"(not implemented)"` grey text.
  - `repaintSectionApps()` — Level 1 when `_s.appSubmenu == -1`: header `"Applications"`;
    5 app rows (`"Stock"`, `"Crypto"`, `"Aquarium"`, `"Matrix"`, `"Life"`) with `">"` chevrons.
    Level 2 when `_s.appSubmenu >= 0`: `repaintSectionAppSubmenu()`.
  - `repaintSectionAppSubmenu()` — header = app name; stub rows: `"(stub)"` label, `"coming soon"` value.
  - `handleInput(TouchPhase, int x, int y)` — Release only:
    back zone `(y < SETTINGS_HEADER_H && x < 60)` → `goBack()`;
    list area → `row = (y - SETTINGS_HEADER_H) / SETTINGS_ROW_H`; if section==-1 → `onCategoryTap(row)`;
    else → `onRowTap(row)`.
  - `goBack()` — 3 levels: `appSubmenu>=0` → reset appSubmenu; `section>=0` → reset section;
    else → `switchApp(g_previousAppId)`.
  - `onCategoryTap(int idx)` — bounds-check; `_s.section = idx; repaintSection();`
  - `onRowTap(int row)` — section 5 only (Applications): if `_s.appSubmenu==-1` and row<5 →
    `_s.appSubmenu = row; repaintSectionApps();`; else no-op (stub sections are read-only).
  - `resume()` → `repaint()` (full repaint from current state).
  - `suspend()` → `_s.section = -1; _s.appSubmenu = -1;`
  - `tick()` → no-op (no sub-flows active yet).

- **TASK-141c** — SERIAL_DEBUG deliverables (gates VE):
  - `get settingsSection` → `{"ok":true,"cmd":"get","var":"settingsSection","section":<int>,"last":true}` (returns `_s.section`, -1..5)
  - `get settingsAppSubmenu` → `{"ok":true,"cmd":"get","var":"settingsAppSubmenu","submenu":<int>,"last":true}` (returns `_s.appSubmenu`, -1..4)
  - Both valid in SERIAL_DEBUG build only; guard with `#ifdef SERIAL_DEBUG`.

- **TASK-141d** — Build + DUT smoke:
  - `check_build.sh` 4/4 pass.
  - Flash `cyd2usb_winamp`. Verify:
    1. Taskbar scroll to Settings slot → Settings opens to category list (6 rows visible).
    2. Tap each category row → section stub renders with correct header title.
    3. `< back` from section → category list; `< back` from category list → previous app.
    4. Applications → `"Stock"` row → app submenu stub → back → app list → back → category list.
    5. Spotify → Settings → Spotify: Winamp chrome pixel-correct.
    6. Re-enter Settings: always lands on category list (suspend reset confirmed).

Exit criterion: TASK-141d smoke items all pass; `check_build.sh` 4/4 green; TASK-142 VE suite written and executed.

---

### TASK-142 — VE: SettingsApp navigation stub test suite (T-SET-01..08)
**Owner**: VE
**Feature**: settings-001
**Status**: written — T-SET-01..08 in test_plan.md; DUT execution pending
**Blocked by**: TASK-141 (requires `get settingsSection` and `get settingsAppSubmenu` serial deliverables)
**Milestone**: M-SETTINGS-STUB
**Design**: `docs/architecture/designs/M-MULTIAPP/settings.md` exit criteria C1–C6

All tests require `cyd2usb_winamp_debug` firmware + serial debug interface.

Serial debug additions required from TASK-141c:
- `get settingsSection` → int (-1..5); -1 = category list
- `get settingsAppSubmenu` → int (-1..4); -1 = app list level, ≥0 = per-app level

**Test suite T-SET-01..08:**

- **T-SET-01** (C1) — Category list bounds: `switchApp(Settings)`;
  `get settingsSection == -1` (at category list); verify no pixel overflow above y=0 or
  into taskbar strip (x≥275). 6 tappable rows present within y:28..239. *(Pixel check:
  manual / visual; section check: automated via `get settingsSection`.)*

- **T-SET-02** (C2a) — Section navigation: for each category index 0..4 (`tap <row_x> <row_y>`);
  assert `get settingsSection == idx`; assert header text correct via manual visual;
  `tap <back_x> <back_y>` (x=30, y=14); assert `get settingsSection == -1`.
  Repeat for all 5 stub sections.

- **T-SET-03** (C2b) — Applications section drill: `switchApp(Settings)`;
  tap row 5 (Applications); `get settingsSection == 5`; `get settingsAppSubmenu == -1`;
  tap row 0 (Stock); `get settingsAppSubmenu == 0`;
  back → `get settingsAppSubmenu == -1`;
  back → `get settingsSection == -1`.

- **T-SET-04** (C3) — Content bounds: for each section 0..5 → verify content panel renders
  within x:0..274, y:28..239 (manual / visual; no pixel outside these bounds).
  *(Paired with T-SET-01 as a single visual pass.)*

- **T-SET-05** (C4) — App-switch residue: `switchApp(Spotify)`; `switchApp(Settings)`;
  `switchApp(Spotify)`. Winamp chrome pixel-correct; no settings residue on canvas.
  *(Visual / manual.)*

- **T-SET-06** (C5) — Suspend reset: `switchApp(Settings)`; tap into Applications → Stock submenu;
  `get settingsAppSubmenu == 0`; `switchApp(Spotify)`; `switchApp(Settings)`;
  `get settingsSection == -1`; `get settingsAppSubmenu == -1` — confirms `suspend()` reset.

- **T-SET-07** (C6 depth) — Double-back from Applications Level 2:
  `switchApp(Settings)`; tap Applications (row 5); tap Aquarium (row 2);
  `get settingsSection == 5`; `get settingsAppSubmenu == 2`;
  back → `get settingsAppSubmenu == -1` (at app list);
  back → `get settingsSection == -1` (at category list).

- **T-SET-08** (back-to-previous-app) — `switchApp(Crypto)`; `switchApp(Settings)`;
  back from category list → `get appId == Crypto`.
  *(Verifies `g_previousAppId` tracking in `switchApp()`.)*

Execute via `run_serialdbg_tests.py --tests T-SET-01,T-SET-02,...,T-SET-08`.
All 8 must pass before TASK-141 can be marked done.

---

### TASK-078 — Design: PLEDIT content-area drag UX improvements
**Owner**: Architect (whiteboard), then Developer
**Feature**: playlist-002, touch-002
**Status**: open (2026-05-23) — points 1 and 3 remain; point 2 resolved by TASK-101
**Blocked by**: nothing — T149/T150/T151/T153/T154 PASS (2026-06-05); capture verified
**Notes**: Current Zone 1 swipe is functional but unsatisfying. Three discussion points:

1. **Click vs gesture discrimination**: Current threshold (|dy| < 4px → tap, ≥4px →
   scroll) is crude. A proper discriminator would consider gesture velocity and/or
   total travel time: short fast → tap; slow long → scroll. Avoids mis-fires when
   the user intends a firm tap but moves slightly.
   **Blocked by T149–T154 pass**: velocity = dy/elapsed_ms; both values are only accurate
   after capture is verified. A leaky sample stream (finger drifts outside hitbox mid-swipe
   → Move samples dropped → artificially small dy) misclassifies deliberate swipes as
   taps. Also requires `_dragStartMs` timestamp added at `D_PLEDIT_SCROLL` Press entry
   (one-liner; can be included in TASK-101 or as a follow-up).

2. ~~**Full-screen gesture capture**~~ — **RESOLVED by TASK-101** (M-TOUCH-CAPTURE
   DragState-first dispatch covers all four sliders including PLEDIT content swipe).
   No separate implementation needed here.

3. **Acceleration / momentum**: A single swipe increments scrollOffset by ±1
   regardless of gesture speed or length. A fast or long swipe should scroll 2–3
   rows. Simple model: `delta = max(1, abs(dy) / ROW_H)` — proportional to travel in
   row-heights. Cap at PLEDIT_ROW_COUNT to avoid jumping past all visible rows.
   **Blocked by T149–T154 pass**: `abs(dy)` must measure full gesture travel. Without capture
   verified, dropped Move samples could make dy artificially small.

Points 1 and 3 blocked on T149–T154 pass. Implement and verify only after TASK-102 completes.

---

> Completed and closed tasks are in [tasks-archive.md](tasks-archive.md).
