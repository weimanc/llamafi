# Design — Taskbar tap feedback + switch latency (M-TASKBAR-FEEDBACK)

> Owner: Architect
> Status: draft
> Date: 2026-07-02
> Feeds: — (ADR when the lean is accepted)
> Tracked-as: TASK-279

## Context / pain points

Operator report (2026-07-02): taskbar app-switching feels sluggish; "I'm not sure if my
click has landed, or if an app is busy."

### Anatomy of a taskbar tap today

1. **Press** — `appHandleInput()` (`main.cpp:1860`) sees `p.x >= TASKBAR_X` and calls
   `winampDisplay.tbGesturePress(p.y)` (`winampDisplay.h:63`). **Zero pixels change.**
2. **Release** — the `!touched` branch calls `tbGestureEnd()`; if the dead zone was never
   exceeded (`!_tbIsScrolling`) it resolves the slot and calls `switchApp()`
   (`main.cpp:1909-1919`).
3. **`switchApp()`** (`main.cpp:1819`) — `suspend()` old app → `setBusy(false)` (3 px
   indicator repaint) → **275×240 black `fillRect` canvas wipe** → target `init()` or
   `resume()` → full `renderTaskbar()`.

The first pixel the user can attribute to their tap is the black canvas wipe — *after*
release, *after* the old app's `suspend()`. Everything before that is invisible.

### Why this reads as "sluggish"

- **No pressed state.** The taskbar never got the press-feedback treatment the Winamp
  transport buttons have had all along: `handleWinampInput()` draws the pressed sprite
  immediately in the Press phase (`winampDisplay.h:414-415`, `drawTransportButtons(pressed)`)
  and restores on release. Precedent exists; the taskbar predates it.
- **Switch cost is paid before any paint.** `resume()` is a full-canvas repaint for every
  app class — Spotify `repaintChrome()` (composite skin blit, `winampDisplay.h:117`) +
  `invalidatePlaylist()`; Matrix/Aquarium repaint + state re-init. None of it is
  instrumented — `perf::record` covers `spotify.poll`, `display.bar`, `display.input`,
  `app.tick`, `vu.tick`, but **not** `switchApp`. We do not currently know where the
  milliseconds go; only the `[shell] leaving/entered` SERIAL_DEBUG lines bracket it.
- **Sampled-touch tap loss.** Touch is polled once per `loop()` iteration
  (`ts.touched()`, `main.cpp:1861`). A tap shorter than one loop period lands entirely
  between two samples and is **never seen** — no gesture, no feedback, nothing. Loop
  iterations inflate badly while WebRadio plays (`s_wr_audio->loop()` decode runs inline
  in `tick()` — see M-WR-AUDIO-TASK); the `>50 ms` perf warning fires routinely there.
  This is the strongest candidate for the literal "click didn't land" experience and is
  **owned by M-WR-AUDIO-TASK**; this design only measures it.
- **Cooldown correction (for the record).** The roadmap/task framing said cooldowns
  "silently drop rapid follow-up taps" at the taskbar. Reading the dispatch order: the
  taskbar zone is handled **before** the `s_cooldownMs`/`g_shellBusy` gate
  (`main.cpp:1865` vs `:1884`), so taskbar presses are *never* cooldown- or busy-gated.
  The 300 ms cooldown set after a taskbar gesture (`:1919`) gates the next **app-canvas**
  press only. Taskbar→taskbar rapid taps are dropped by *sampling loss*, not by cooldown.

### Constraints

- Tap-vs-scroll share the zone: a press is ambiguous until the 3 px dead zone
  (`TB_SCROLL_DEAD_ZONE_PX`) is exceeded or the finger lifts. Feedback must not corrupt
  scroll UX (M-TASKBAR-SCROLL, `M-MULTIAPP/taskbar.md §Scroll model`).
- Golden-hash gate: new colour constants go in `taskbar.h` as firmware-only `#define`s,
  NOT in generated `shell_layout.h` (same rule as `TASKBAR_BUSY_COLOR`, ADR-046).
- Indicator precedence error > busy|connecting > idle (ADR-046) must be preserved; a
  pressed state is a *slot background* treatment, not a fourth indicator colour.
- ADR-035 already rejected canvas spinners and indicator animation; this design stays
  within "cheap static paint at transition" territory.

## Goals

1. A taskbar press produces a visible response within one loop iteration of the Press
   sample (press-slot highlight).
2. The user can distinguish "tap registered, switch in progress" from "tap missed".
3. `switchApp()` cost becomes a measured quantity (per-phase), so any future latency work
   is evidence-driven, not guessed.
4. No regression to tap-vs-scroll discrimination, indicator precedence, or the
   `run/check` golden hash.
5. Every acceptance point is drivable from serialdbg (injected gestures + logs), no
   logic analyser or human eyeball required for the latency numbers.

## Design space (options + tradeoffs)

### Sub-problem A — feedback

**F-a. Pressed-slot highlight on Press.**
`tbGesturePress()` already computes nothing visual; shell computes
`slot = y / TASKBAR_SLOT_H` and repaints that one slot with a pressed treatment —
brightened background (`#define TASKBAR_PRESSED_BG` ≈ separator grey `0x4208`) + re-blit
of the icon, i.e. a parameterised single-slot variant of the `renderTaskbar()` loop body.
Cost: one 45×40 `fillRect` + one 24×24 `pushImage` — single-digit ms of SPI, once per
press. Restore triggers: (1) dead zone exceeded → scroll starts (highlight cancels,
matching mobile-list convention), (2) release. Flicker risk on scroll-start is one
cancel repaint — acceptable.
*Tradeoff:* touches the gesture state machine's shell side only; `WinampDisplay` keeps
zero switch/render responsibility (same separation `cmdTap` respects, `main.cpp:2386`).

**F-b. Post-release "switching…" affordance.**
At tap resolution in the release path, *before* `switchApp()` does its heavy work, paint
the **target** slot's 3 px bar amber (`TASKBAR_BUSY_COLOR`). `switchApp()`'s final full
`renderTaskbar()` then overwrites it with the real active/green state. Cost ≈ zero (one
3 px `fillRect`); it reuses the existing busy colour without touching ADR-046 semantics
(it is a transient paint, not a new indicator state).
*Tradeoff:* only visible for the duration of the switch (~tens to a few hundred ms); on a
fast switch it is subliminal — which is fine, it only needs to be visible when the switch
is *slow*, which is exactly when reassurance is needed.

**F-c. Both (F-a + F-b).** Press-highlight answers "did my finger register"; the amber
commit bar answers "is it doing something". Combined cost is still two small blits.

**F-d. Audible click.** Rejected: no speaker in the shell's scope (DAC is WebRadio-only,
GPIO26), and it drags in cross-app audio ownership for a UX ping.

### Sub-problem B — latency

**L-a. Keep switch-on-release.** Switch-on-press is **not possible** without breaking the
taskbar: press is ambiguous between tap and scroll until the dead zone resolves, and
committing a switch on press would misfire at every scroll start. This is a hard
consequence of the shared zone (M-TASKBAR-SCROLL), not a tuning choice. Release semantics
stay; feedback (sub-problem A) closes the *perception* gap instead.

**L-b. Shave `switchApp()` cost.** Candidates, all currently unmeasured:
- The 275×240 black wipe is a double paint for apps whose `init()/resume()` repaints the
  full canvas anyway (all of them, today — full-screen canvas rule). Could become
  conditional via an `App::paintsFullCanvas()` default-true endpoint. Saves one full-canvas
  SPI fill (~10-20 ms estimated); loses the guard against a future app that doesn't repaint
  fully.
- Defer non-critical `resume()` work (e.g. Spotify `invalidatePlaylist()` → next tick).
- **Position:** instrument first (L-d), optimise only what the numbers convict. Blind
  restructuring of eight apps' resume paths for an unquantified win is how regressions
  happen.

**L-c. Cooldown audit.** Findings from the code read:
- Taskbar presses are never cooldown-gated (see Context correction) — nothing to fix.
- The 300 ms post-taskbar-gesture cooldown (`:1919`) gates the next app-canvas press.
  Load-bearing candidate: finger-lift bounce from a taskbar scroll bleeding into the
  canvas as a phantom tap (resistive digitizer). Aligning it to 200 ms (the tap value) is
  plausible but low-value; verify bounce rate on DUT with `set cooldown 0` before touching.
- The `g_shellBusy` canvas-press gate is ADR-035 Decision 2b — out of scope here.

**L-d. Instrument `switchApp()`.** Add `perf::record("shell.switch", ...)` around the
whole body plus a one-line SERIAL_DEBUG phase breakdown
(`[shell] switch 1→4 suspend=Xms wipe=Xms init=Xms taskbar=Xms`). `perf.h` `MAX_PATHS=8`
with 6 production paths used — one slot free (SCREEN_LOG builds use 7). The existing
`[shell] leaving/entered` heap lines already bracket the region; this refines them.

### Measurement plan (baseline before any implementation)

**Definition — "press-to-first-pixel":** time from the loop iteration that samples the
taskbar Press (injected: `drainInjectionQueue` routes `sx >= TASKBAR_X` samples to
`tbGesturePress`, `main.cpp:2312-2321`) to completion of the pressed-slot repaint (new
timestamped log line). Target: same loop iteration.

**Definition — "tap-to-switch-committed":** injected release → `[shell] entered N` line.

Procedure (debug build, `./run/monitor-read` + timestamped logs):
1. `drag <tbX> <y> <tbX> <y±1> 2` = taskbar tap through the *real* gesture path (note:
   `tap <x≥TASKBAR_X> <y>` bypasses the gesture machine and calls `switchApp()` directly —
   useful for isolating switch cost, useless for press-feedback timing).
2. Capture per-phase switch numbers for three device states: idle non-player app,
   Spotify active, **WebRadio PLAYING** (the loop-starvation case).
3. Record heartbeat `loopMax` per state alongside — this is the M-WR-AUDIO-TASK
   cross-reference number, and doubles as the missed-tap-rate explanation.
4. Repeat post-implementation; both tables land in this doc.

## Lean / decision

**F-c + L-a + L-d now; L-b/L-c deferred pending numbers.**

1. Pressed-slot highlight on Press, cancelled on scroll-start or release (F-a), colour as
   firmware-only `#define TASKBAR_PRESSED_BG` in `taskbar.h`.
2. Transient amber bar on the target slot at tap-commit, before `switchApp()` work (F-b).
3. Switch stays on release (L-a — forced by tap-vs-scroll ambiguity; recorded as a
   constraint, not a preference).
4. Instrument `switchApp()` phases + `shell.switch` perf path (L-d); run the baseline
   matrix above **before** the feedback change lands so before/after is honest.
5. Cooldowns untouched; the "taskbar taps are cooldown-dropped" belief is corrected in
   this doc (they never were). Canvas-side 300 ms audit parked as an open question.
6. Sampling-loss during WebRadio playback is explicitly **out of scope** — owned by
   M-WR-AUDIO-TASK; this design contributes the measurement (step 3) that sizes it.

Rationale: the complaint is perceptual, and the two cheapest changes (two small blits)
attack perception directly using an in-codebase precedent (transport pressed sprites).
Everything speed-related is gated behind instrumentation because nothing in the switch
path is measured today.

## Open questions

1. Pressed visual treatment: brightened slot bg vs icon-active-variant vs white edge bar —
   pick on DUT (or `preview_layout.py` mock) at implementation time. Cheap to change.
2. Should the press highlight *persist* through the switch (press → release → target
   painted) instead of cancel-then-amber? Slightly calmer visually; decide on DUT.
3. Is the 300 ms post-taskbar cooldown load-bearing against release bounce on this
   resistive panel? Testable: `set cooldown 0`, scroll taskbar, count phantom canvas taps.
4. `cmdTap`'s taskbar branch calls `switchApp(appIdx)` directly and **skips
   `resolvePlayerSlot()`** (`main.cpp:2390` vs `:1916`) — injected taps on the player slot
   land on Spotify even when the persisted mode is WebRadio (TASK-259/260 divergence from
   production path). Side-finding, out of scope; flag to PM/VE for a small follow-up task.

## Exit criteria

- DUT: pressing a taskbar slot visibly highlights it in the same loop iteration; the
  highlight cancels when a scroll starts; a committed tap shows the amber bar on the
  target slot until the target app's paint completes.
- serialdbg: injected taskbar drag-tap produces the press-feedback log line in the same
  iteration as the Press sample; before/after latency tables (3 device states × per-phase
  switch cost) recorded in this doc.
- Tap-vs-scroll discrimination unchanged (existing T162–T166 still pass).
- `run/check` 5 gates pass; `gen/golden.sha256` untouched.
- VE additions: T-TBFB-01 press-highlight paint, T-TBFB-02 cancel-on-scroll,
  T-TBFB-03 commit-amber transient, T-TBFB-04 app-canvas cooldown behaviour unchanged.
