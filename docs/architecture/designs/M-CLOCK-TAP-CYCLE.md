# Design — In-app clock face/theme cycling via tap zones

> Owner: Architect
> Status: accepted — Q1–Q4 resolved by human 2026-07-18, all as proposed
> Date: 2026-07-18
> Tracked-as: TASK-346
> Depends on: M-CLOCK-THEMES.md (TASK-345, implemented — `nixieTheme`/`vfdTheme` fields + runtime tint), ADR-050

## Context / request

Human request (2026-07-18): change clock face and colour from inside the
Clock app itself, without the Settings round-trip. Split the clock canvas
into two hit boxes — top = cycle colour theme (where applicable), bottom =
cycle clock face. Changes persist, but the SPIFFS write is deferred to app
exit.

Current state: `ClockApp::handleInput()` is a stub (`return false`) — the
clock consumes no touch at all. Four faces exist (`ClockStyle`:
Digital/Flip/Nixie/VFD) and, since M-CLOCK-THEMES, Nixie and VFD each have
4 colour themes (`g_settings.nixieTheme`/`vfdTheme`), editable in
`Settings > Applications > Clock` and via serial (`set clockStyle`,
`set nixieTheme`, `set vfdTheme`).

## Design

### D1 — Hit boxes

Clock canvas is the full 275×240 app canvas (full-screen canvas rule;
x≥275 is the taskbar, shell-owned, never reaches `handleInput`).

| Zone | Rect | Action |
|---|---|---|
| Top | y 0..119 | cycle colour theme of the active face (if it has themes) |
| Bottom | y 120..239 | cycle face: Digital → Flip → Nixie → VFD → wrap |

Named constants (`CLK_TAP_SPLIT_Y = 120`), not magic numbers — hit-test,
render and VE tests all reference the constant (settings-nav
coordinate-drift lesson; same rule as `PR_STRIP_ROW_LOC_Y`).

Input idiom copied from `teletextApp.h::handleInput`: act on
`TouchPhase::Release` only, 300 ms debounce, record every outcome in a
`_lastAction` observable.

### D2 — Face cycle (bottom zone)

`clockStyle = (clockStyle + 1) % 4` in enum order — same order Settings'
cycle-row and the serial command's name table (`kSN`) use, so all three
surfaces agree. Apply = full `repaint()`, the exact path `set clockStyle`
already takes when the clock is foreground (Flip mid-animation state is
reset by that path today; no new machinery).

### D3 — Theme cycle (top zone)

Only defined for faces with themes:

| Face | Top-zone action |
|---|---|
| Nixie | `nixieTheme = (nixieTheme + 1) % 4` (amber/red/green/blue), repaint |
| VFD | `vfdTheme = (vfdTheme + 1) % 4` (teal/amber/blue/green), repaint |
| Digital, Flip | no-op (consumed, `_lastAction = "TAP_THEME_NA"`, no repaint) — Q1 |

Theme application is already pure runtime (M-CLOCK-THEMES option B tint /
VFD colour table) — cycling is an index bump + repaint, no bake, no flash
cost.

### D4 — Persistence: coalesced save-on-suspend (ADR-050 rule 3)

Verbatim the WebRadio `lastStation` idiom (`webRadioApp.h suspend()`):

- Tap handlers mutate `g_settings` in RAM only and set `_styleDirty`.
- `ClockApp::suspend()` compares `{clockStyle, nixieTheme, vfdTheme}`
  against a snapshot taken at `init()`/`resume()`; calls
  `SettingsStorage::save()` **iff different**, then refreshes the snapshot.
- Full-circle cycling back to the loaded value costs zero flash writes
  (wear guard); N taps in one session cost at most one write.

Sequencing makes the two-writer problem a non-issue: `switchApp()` runs
old-app `suspend()` before the next app resumes, so by the time Settings
(or anything else) opens, the clock's pending change is already persisted.
Serial `set clockStyle`/`set *Theme` keep their existing immediate-save
behaviour — unchanged surface.

Accepted loss window: power-cut/reboot while the Clock app is still
foreground loses un-flushed taps (identical trade-off ADR-050 rule 3
already accepted for WebRadio station churn). Not worth a timer-flush — Q4.

### D5 — Observability / VE surface

- `_lastAction` values: `TAP_FACE`, `TAP_THEME`, `TAP_THEME_NA`,
  `DEBOUNCE` — exposed via `get clockLastAction` (mirror of
  `prLastAction`).
- `get clockStyle` extended to also report `nixieTheme`, `vfdTheme`, and
  `dirty` (the un-flushed-change flag) — the dirty flag is what makes the
  deferred-write behaviour testable without pulling settings.json.
- Serial `tap x y` drives both zones; suggested suite:
  - T_CLK_TAP_01 bottom tap cycles face, ×4 wraps to start
  - T_CLK_TAP_02 top tap cycles theme on Nixie and VFD
  - T_CLK_TAP_03 top tap on Digital/Flip = no-op (style, themes, screen all unchanged)
  - T_CLK_TAP_04 dirty stays true / settings.json unchanged until `switchApp`, then flushed (one write)
  - T_CLK_TAP_05 full-circle session → `suspend()` writes nothing (wear guard)
  - T_CLK_TAP_06 debounce: two taps <300 ms apart advance once
  - Screendump eyeball: one shot per face + one theme-cycled shot (BP-048: render change must be seen, not inferred)

### D6 — Explicitly out of scope

- Themes for Digital/Flip faces (top zone reserved for them if ever added).
- Any on-screen affordance/chrome for the tap zones (Q2).
- Gestures (swipe/long-press) — Release-tap only.

## Resolved questions (human review 2026-07-18 — all as proposed)

- **Q1 — top tap on Digital/Flip: strict no-op.**
- **Q2 — discoverability: none** (clean face wins; the feature is
  documented, and Settings still exists as the discoverable path).
- **Q3 — cycle order: enum order** (matches Settings + serial name
  table). No user-curated ordering.
- **Q4 — flush policy: suspend-only** (ADR-050 rule 3 idiom). No
  idle-timer flush.

## Cost note

No new resident RAM beyond the 3-byte snapshot + flags; no flash assets;
touch path is a two-branch if. Implementation is small — the bulk of the
task is the VE suite and registry/docs bookkeeping (feature_inventory,
NEW-APP-CHECKLIST does not apply — existing app, but the dbgGet/tap-busy
checklist rows do).
