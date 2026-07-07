# Design — Taskbar tap feedback + switch latency (M-TASKBAR-FEEDBACK)

> Owner: Architect
> Status: accepted — human-approved 2026-07-03 (panel: VE/DEV/QM approve-with-changes ×3, dispositions applied)
> Date: 2026-07-02 (dispositions applied 2026-07-03)
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
of the icon. **Index math + painter, pinned [QM-3-2]:** the app/icon index is
`(tbScrollOffset() + slot) % TASKBAR_APP_COUNT` — the exact mapping `renderTaskbar` and
`cmdTap` use — and the pressed-slot painter **reuses (not reimplements) the guarded
`renderTaskbar()` slot body** behind the TASK-242 null-guard/`static_assert` defenses
(LL-085: implied index math on the taskbar is what rotted into a crash). The single-slot
repaint reproduces the full slot body: separator line and — when the pressed slot is the
active slot — the 3 px indicator with ADR-046 precedence, or pressing the active slot
visibly eats the indicator for the press duration [DEV-3-3].
**Press-anchored commit [DEV-3-2]:** the slot captured at `tbGesturePress()` is also the
slot the tap *commits* — today `tbGestureEnd(s_lastTouchY, …)` re-resolves from release-y,
so within the 3 px dead zone the finger can cross a slot boundary: highlight slot A,
switch slot B, on a resistive panel that jitters by design. Resolving the tap from the
press-anchored slot fixes the latent production quirk and guarantees highlight == commit.
(Touches T162–T166's assumptions — VE owns the re-check.)
Cost: one 45×40 `fillRect` + one 24×24 `pushImage` — single-digit ms of SPI *(estimate —
superseded by the §Measurement-plan tables [QM-3-3])*, once per press. Restore triggers:
(1) dead zone exceeded → scroll starts (highlight cancels, matching mobile-list
convention), (2) release. Flicker risk on scroll-start is one cancel repaint — acceptable.
**Scroll-start needs a signal [DEV-3-1]:** `_tbIsScrolling` is private and
`tbGestureContinue()` returns true only on ≥1-slot steps — dead-zone-exceeded with
sub-slot travel produces no observable event, so the cancel trigger cannot be implemented
against the current interface. Add a `tbIsScrolling()` accessor to `WinampDisplay`
(interface change, one line; alternative: `tbGestureContinue` returns
{none, scrollStarted, stepped}).
**Single shared helper [VE-3-1 + DEV-3-6]:** the paint + its stable-prefix log live in one
shell helper set — `shellTbPress(y)` (`[shell] tb-press slot=N`), `shellTbCancel()`
(`[shell] tb-press-cancel`), `shellTbCommit(slot)` (`[shell] tb-commit slot=N`) — invoked
from **both** dispatch sites (`appHandleInput` and `drainInjectionQueue`), for press,
cancel, and the F-b commit paint alike; otherwise the injected path the measurement plan
depends on drifts from production.
*Tradeoff:* touches the gesture state machine's shell side only; `WinampDisplay` keeps
zero switch/render responsibility (same separation `cmdTap` respects, `main.cpp:2386`).

**F-b. Post-release "switching…" affordance.**
At tap resolution in the release path, *before* `switchApp()` does its heavy work, paint
the **tapped slot's** 3 px bar amber (`TASKBAR_BUSY_COLOR`) — **the press-anchored slot
index, never a reverse app→slot lookup [QM-3-1]**: `resolvePlayerSlot()` runs after this
paint and can return WebRadio, which deliberately has no taskbar slot
(`TASKBAR_APP_COUNT = (int)AppId::WebRadio`, LL-085/TASK-242) — an app→slot reverse
lookup is undefined exactly there. The WebRadio-player-mode case goes into T-TBFB-03's
test notes. `switchApp()`'s final full `renderTaskbar()` then overwrites the amber with
the real active/green state. Cost ≈ zero (one 3 px `fillRect`) *(estimate — superseded by
the §Measurement-plan tables [QM-3-3])*; it reuses the existing busy colour without
touching ADR-046 semantics (it is a transient paint, not a new indicator state). Painted
via `shellTbCommit(slot)` with its `[shell] tb-commit slot=N` line — the transient is
otherwise unobservable on fast switches [VE-3-3].
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
(`[shell] switch 1→4 suspend=Xms wipe=Xms init=Xms taskbar=Xms`). Perf slot budget
[VE-3-5 correction]: production paths used today are **5**, not 6 (`screenlog.tick` is
SCREEN_LOG-gated) — `shell.switch` alone fits, but the touch-UX trio combined
(`wr.pump` + `wr.connect` + `shell.switch`) lands at `MAX_PATHS=8` exactly and overflows
silently under SCREEN_LOG; **`MAX_PATHS` goes 8 → 10 in whichever trio task lands first**
(budget table lives in M-WR-AUDIO-TASK §perf instrumentation) [VE-2-3]. The existing
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
   Spotify active, **WebRadio PLAYING** (the loop-starvation case) — **N≥5 injected taps
   per state, reported as median + max** (single-shot timing assertions are what made
   T-CDWN-01/T169 flaky) [VE-3-2].
3. Record heartbeat `loopMax` per state alongside — this is the M-WR-AUDIO-TASK
   cross-reference number, and doubles as the missed-tap-rate explanation.
4. **Shared-baseline + sequencing rule [VE-3-2 + QM-2-2 + DEV-X-1]:** the baseline matrix
   is taken in **one DUT session with M-WR-AUDIO-TASK's E0** (same quantities), on current
   master, before either TASK-278 or TASK-279 implementation merges. Before/after tables
   are only comparable at the same TASK-278 state — if TASK-278 lands in between,
   re-baseline. Land order (pinned in roadmap): shared E0 baseline → TASK-278 → TASK-277
   → TASK-279 feedback blits.
5. Repeat post-implementation; both tables land in this doc.

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
   **Bake constraint [DEV-3-4]:** icons are opaque 24×24 RGB565 baked over `TASKBAR_BG` —
   re-blitting one onto a brightened slot leaves a dark icon-sized square inside the
   highlight. Edge-bar/white-frame treatments are free; a full-slot tint needs re-baked
   pressed icons (separate gen artifact, no golden-hash impact, but a bake step).
2. Should the press highlight *persist* through the switch (press → release → target
   painted) instead of cancel-then-amber? Slightly calmer visually; decide on DUT.
3. Is the 300 ms post-taskbar cooldown load-bearing against release bounce on this
   resistive panel? Testable: `set cooldown 0`, scroll taskbar, count phantom canvas taps.
4. `cmdTap`'s taskbar branch calls `switchApp(appIdx)` directly and **skips
   `resolvePlayerSlot()`** (`main.cpp:2390` vs `:1916`) — injected taps on the player slot
   land on Spotify even when the persisted mode is WebRadio (TASK-259/260 divergence from
   production path). A second divergence [VE-3-6]: the injected taskbar release never sets
   the 300 ms post-gesture cooldown that production sets (`main.cpp:1919`). **Filed as
   TASK-280** (align injection with production dispatch) [QM-3-4].

## Exit criteria

- DUT: pressing a taskbar slot visibly highlights it in the same loop iteration; the
  highlight cancels when a scroll starts; a committed tap shows the amber bar on the
  **tapped (press-anchored)** slot until the target app's paint completes.
- serialdbg: injected taskbar drag-tap produces the `[shell] tb-press` line in the same
  iteration as the Press sample (via the shared helper — injection and production hit the
  same code [VE-3-1]); `[shell] tb-commit slot=N` ordered before `[shell] entered N`
  [VE-3-3]; `[shell] tb-press-cancel` on an injected drag exceeding
  `TB_SCROLL_DEAD_ZONE_PX` [VE-3-4]; before/after latency tables (3 device states ×
  per-phase switch cost, N≥5 median+max) recorded in this doc.
- Tap-vs-scroll discrimination unchanged (existing T162–T166 still pass — re-checked
  against the press-anchored commit change [DEV-3-2]).
- `run/check` 5 gates pass; `gen/golden.sha256` untouched.
- VE additions: T-TBFB-01 press-highlight paint, T-TBFB-02 cancel-on-scroll (asserts the
  cancel line), T-TBFB-03 commit-amber transient (asserts the commit line + the
  WebRadio-player-mode case), T-TBFB-04 app-canvas cooldown behaviour unchanged (asserted
  via `get cooldown` around a production-path-equivalent injected gesture; the injected
  release skips the production cooldown — documented divergence, see OQ4/TASK-280).

---

## Panel dispositions (2026-07-03)

VE / DEV / QM returned **approve-with-changes**; every blocker/major applied in place above.
Reviews: [touch-ux-panel-VE-review.md](touch-ux-panel-VE-review.md) ·
[touch-ux-panel-DEV-review.md](touch-ux-panel-DEV-review.md) ·
[touch-ux-panel-QM-review.md](touch-ux-panel-QM-review.md).

- **VE-3-1 (major) + DEV-3-6** (injected Press bypasses the shell paint site) → F-a/F-b:
  single shared helper set `shellTbPress/shellTbCancel/shellTbCommit` (paint + stable log)
  called from both dispatch sites.
- **VE-3-2 (major) + QM-2-2 + DEV-X-1** (single-shot baseline; TASK-278 sequencing
  unpinned) → §Measurement plan: N≥5 median+max per state; shared E0 session with
  M-WR-AUDIO-TASK; re-baseline rule; land order pinned in roadmap.
- **DEV-3-1 (major)** (no shell-visible scroll-start signal) → F-a: `tbIsScrolling()`
  accessor added to the interface spec.
- **DEV-3-2 (major)** (highlight from press-y, commit from release-y — can differ inside
  the dead zone) → F-a: press-anchored slot is the committed slot; T162–T166 re-check
  assigned to VE.
- **QM-3-1 (major)** (F-b said "target slot"; `resolvePlayerSlot()` can return slotless
  WebRadio — LL-085 class) → F-b: amber paints the tapped slot index, never a reverse
  app→slot lookup; WebRadio-player-mode case in T-TBFB-03.
- **QM-3-2 (major)** (slot→app index math + TASK-242 guards implicit) → F-a: formula
  pinned, painter reuses the guarded `renderTaskbar` slot body.
- **VE-3-3/3-4** (commit/cancel paints unobservable) → `[shell] tb-commit` /
  `tb-press-cancel` lines + T-TBFB assertions.
- **VE-3-5 + DEV-3-5** (perf path count wrong; trio hits `MAX_PATHS`) → L-d corrected
  (5 production paths); `MAX_PATHS` 8→10 per VE-2-3, budget table in M-WR-AUDIO-TASK.
- **DEV-3-3/3-4** (slot-body completeness; icon bake constraint) → F-a paint spec + OQ1.
- **QM-3-3** (unlabelled estimates) → tagged, superseded by measurement tables.
- **QM-3-4 + VE-3-6** (OQ4 floating; second injection divergence) → TASK-280 filed; OQ4
  references it; T-TBFB-04 documents the divergence.

## VE dbg-surface sign-off (BP-024) — 2026-07-07

Reviewed the observables the lean requires; signed off as follows. All lines are
SERIAL_DEBUG-gated, single-`printf` (VE-8 no-tearing rule), stable-prefix `[shell] `.

1. `[shell] tb-press slot=N` — emitted by `shellTbPress()` in the **same loop iteration**
   as the taskbar Press sample, *after* the pressed-slot repaint completes (the line
   timestamp is the "first pixel done" mark for press-to-first-pixel). `N` = visible slot
   index 0..5, not app index.
2. `[shell] tb-press-cancel` — emitted by `shellTbCancel()` after the slot-restore repaint.
   Primary trigger: scroll-start (dead zone exceeded, DEV-3-1 accessor). Secondary
   trigger (documented, asserted tolerant): a tap that resolves to the already-active app
   (no switch fires; the highlight must still be restored). Idempotent — no line when no
   highlight is live.
3. `[shell] tb-commit slot=N` — emitted by `shellTbCommit()` after the amber-bar paint,
   **strictly before** `[shell] entered M` [VE-3-3]. `N` is the **press-anchored** slot
   index [QM-3-1/DEV-3-2]. Emitted only when the tap commits an actual switch
   (target != current).
4. `[shell] switch F->T suspend=Xms wipe=Xms init=Xms taskbar=Xms total=Xms` — end of
   `switchApp()`, after the final `renderTaskbar`. The pre-existing `[shell] entered T`
   line keeps its position (between init/resume and renderTaskbar) so E0/E1
   tap-to-switch-committed clocks stay comparable — extend-don't-move honoured.
5. perf path `shell.switch` (production, not SERIAL_DEBUG-gated) — whole-body switch
   duration; surfaces via the heartbeat `slow=` field. Budget: `MAX_PATHS` is already 10
   (TASK-278 landed the VE-2-3 bump); `shell.switch` is the 10th slot — **no headroom
   left; bump before adding an 11th path.**
6. No new `get`/`set` variables. `get cooldown` (WinampDisplay canvas cooldown) is the
   T-TBFB-04 assertion surface as-is.

Assertion style: T-TBFB tests assert presence + relative order of the lines within one
injected-gesture drain window; phase numbers in line 4 are recorded, never
threshold-asserted single-shot (VE-3-2 flakiness rule — medians over N≥5 in the
measurement tables only).

Gate satisfied: implementation may start.

---

## Baseline attempts (2026-07-03)

Valid network-idle rows (reproduced across 3 runs 2026-07-03, N=5, spread <3 ms):

| state | tap-to-switch-committed (median) | injection drain | quiet `loop_max` |
|---|---|---|---|
| idle_clock | 97.8 ms | ≈113 ms | 23 ms |
| spotify | 83.5 ms | ≈99 ms | 23 ms |
| wr_stopped | 84.4 ms | ≈100 ms | 23 ms |

Measured via the corrected injection-ordering parser (`e0_baseline.py`: `[shell] entered` precedes
the drag JSON in `drainInjectionQueue` — the tap-to-committed clock runs from command send, not
from the JSON). The earlier "both link-dead" attempts were the **router**, now root-caused and
fixed (see M-WR-AUDIO-TASK §E0 resolution: MX5600 2.4 GHz auto-channel, pinned via JNAP).

**WebRadio-PLAYING tap row still owed.** The decode-loaded loop measurement (M-WR-AUDIO-TASK) had
to run on the `cyd2usb_webradio` (DISABLE_SPOTIFY) build — the prod build's Spotify-403 tlsYield
starvation blocks the station fetch, so nothing plays. That build is WEBRADIO_ONLY (no taskbar to
tap), so the *tap-to-switch-under-decode* row cannot be taken there. It needs the multi-app build
with a live PLAYING WebRadio — which needs Spotify not-403 (owner Premium re-auth) OR a
WEBRADIO-in-multi-app variant. **Deferred to TASK-279 implementation time** (re-baseline rule
already applies).

**Decode-tail context (from M-WR-AUDIO-TASK E0).** Under PLAYING, `loop_max` median holds at 24 ms
but the tail hits 141 ms with 6 >50 ms iterations / 10 min (worst path `app.tick` = the
`Audio::loop()` site). That tail is the sampled-touch-loss mechanism this design calls out as
out-of-scope (§6, owned by M-WR-AUDIO-TASK): a tap landing in a 141 ms iteration is simply never
sampled. So the taskbar-feedback blits (this design) and the audio-task move (TASK-278) are
complementary — feedback makes a *landed* tap feel instant; the audio task stops taps being
*dropped* during playback. Neither alone fixes the WebRadio-PLAYING case.

---

## Implementation results (2026-07-07) — exit criteria

Landed as `d13817d` (firmware) + `cc92355`/`2e92f01` (harness) after the BP-024 sign-off
(`1d07433`). All DUT checks on `cyd2usb_winamp_debug` via `run/test-targeted`; latency
matrix via `app/tools/e0_baseline.py` (extended to record `press_ms`/`commit_ms`/switch
phases per tap — additive, the entered/drain clocks untouched). Re-baseline rule honoured:
the BEFORE column is the TASK-278 E1 rerun (2026-07-07, same firmware lineage), not the
2026-07-03 E0.

| Exit criterion | Result |
|---|---|
| Press highlights slot in the same loop iteration | PASS (serialdbg: `tb-press` emitted in the Press-sample drain iteration, T_TBFB_01; **visual confirm is manual** — see disposition D1) |
| Highlight cancels on scroll-start [VE-3-4] | PASS (T_TBFB_02: `tb-press` → `tb-press-cancel`, no commit, offset stepped 0→1) |
| Amber bar on press-anchored slot until target paint [VE-3-3/QM-3-1] | PASS (T_TBFB_01: `tb-commit slot=N` strictly before `[shell] entered`; T_TBFB_03: player-slot tap with persisted WebRadio mode paints tapped slot 0, redirect lands, no reverse lookup) |
| Injection and production share the paint/commit code [VE-3-1] | PASS (single `shellTbPress/Cancel/Commit/Release` set called from both dispatch sites) |
| Tap-vs-scroll discrimination unchanged, T162–T166 re-checked [DEV-3-2] | PASS 5/5 + T242 (full wrap cycle, WebRadio never reachable) |
| T-TBFB-04 canvas cooldown unchanged; injection divergence documented | PASS (taskbar gesture leaves canvas cooldown 0; VIS tap arms 278 ms; injected release still skips the production 300 ms shell cooldown — TASK-280 stays open as filed) |
| `run/check` gates + golden hash | PASS 6/6 before every commit (gate count grew 5→6 since design text; `gen/golden.sha256` untouched — `TASKBAR_PRESSED_BG` is firmware-only per ADR-046 rule) |
| Before/after latency tables (3+ states, N≥5 median+max) | Done — below; WebRadio-PLAYING row (owed since E0) taken |

### Latency tables (AFTER: 2026-07-07, N=5/state, 2-min quiet windows, 0 in-window `[wifi-ev]`)

New quantities (did not exist before — the feature/instrumentation creates them):

| state | press-to-first-pixel (med/max) | commit paint (med/max) | switch phases suspend/wipe/init/taskbar (med) | switch total (med/max) |
|---|---|---|---|---|
| idle_clock | **14.3 / 14.8 ms** | 22.8 / 23.8 ms | 11 / 27 / 51 / 9 | 98 / 102 ms |
| spotify | **14.2 / 14.8 ms** | 22.5 / 23.0 ms | 11 / 27 / 38 / 8 | 84 / 98 ms |
| wr_stopped | **13.9 / 14.4 ms** | 22.3 / 22.3 ms | 11 / 27 / 38 / 8 | 84 / 84 ms |
| wr_playing | **33.2 / 40.0 ms** | 61.4 / 81.8 ms | **44** / 27 / 38 / 9 | 117 / 119 ms |

(`press_ms` is measured from command send, so it includes ~1 loop iteration of command
parse + queue pop; the paint itself lands in the same iteration as the Press sample —
the design's target. Under PLAYING, iterations are longer, hence 33 ms.)

Before/after on the pre-existing clocks:

| state | tap-to-switch-committed BEFORE → AFTER (med) | drain BEFORE → AFTER (med) |
|---|---|---|
| idle_clock | 97.8/97.9 → 109.2 ms | ~113 → 124.1 ms |
| spotify | 83.5 → 96.5 ms | ~99 → 112.0 ms |
| wr_stopped | 84.4 → 95.5 ms | ~100 → 110.9 ms |
| wr_playing | 112.7 (E1) → 174.3 ms | 128.8 (E1) → 189.7 ms |

**Attribution of the +11–13 ms (idle states):** the three new SERIAL_DEBUG lines per tap
(`tb-press` ~25 B, `tb-commit` ~26 B, `switch` breakdown ~75 B) add ~126 bytes to a
115200-baud stream whose TX buffer the existing leaving/entered heap lines already
saturate during a switch — ≈11 ms of wire time, matching the delta. The production build
compiles none of these lines; its only added cost is the two blits (pressed-slot repaint
+ 3 px amber bar, single-digit ms — consistent with `press_ms` − one iteration).
`switch total` (internal clock, med 84–98 ms) is in line with the BEFORE
tap-to-switch-committed medians (83.5–97.8 ms), i.e. **switch cost itself is unchanged**.

**wr_playing row context:** this state's larger deltas are (a) the same serial artifact
on longer iterations, and (b) `suspend=44 ms` — the audio-pump teardown ack when leaving
a *playing* WebRadio, now measured for the first time (was invisible pre-L-d). The
session's in-window `loop_max` (median 44.5, max 50, **0 iterations >50 ms**) holds the
TASK-278 E1 tail bar (max ≤50, 0 >50 ms); the 44.5 median vs E1's 24 is a 4-hb-sample
window on a different live station, not a regression signal — tail is the gating
statistic per the E0 amendment.

**L-b now has numbers (no action, recorded for the future):** the 275×240 black wipe is a
constant 27 ms in every switch (~30% of an idle switch); init/resume 38–51 ms; suspend
11 ms (44 ms leaving playing WebRadio). If switch latency ever needs shaving, the wipe's
double-paint (`App::paintsFullCanvas()` idea) is the best-value candidate. Deferred as
designed.

### Dispositions (for human sign-off)

- **D1 — visual confirmation is manual.** "Visibly highlights" cannot be asserted over
  serial (T168 precedent). Compensating evidence: the paint call is in the asserted code
  path (same helper emits the log line after the blit), and the slot painter is the same
  `renderTaskbarSlot` body `renderTaskbar` uses. **Owed: a human glance** at the pressed
  highlight/amber bar; treatment is 1-define cheap to change (`TASKBAR_PRESSED_BG`,
  OQ1 halo choice — full-slot tint would need re-baked pressed icons per DEV-3-4).
  **RATIFIED (human, 2026-07-07): highlight + amber bar confirmed visible on device.**
  OQ1's halo treatment stands; the visual exit criterion is closed.
- **D2 — AFTER windows are 2 min, not E0/E1's 10 min.** The tap clocks are
  window-length-independent (taps run after the passive window); the 10-min tail numbers
  remain owned by TASK-278 E1, which this session's window does not supersede.
- **D3 — T_TBFB_04 first-run false-FAIL (fixed in-run):** the canvas half tapped PLEDIT,
  which only arms the cooldown when playlist rows exist — empty under TASK-243's 403.
  Re-pointed at the VIS window (data-independent +300 ms, T-CDWN-01 precedent); PASS
  remainingMs=278. Test defect, not firmware — no task filed.

### Open-question outcomes

- **OQ1 (pressed treatment):** brightened-bg halo (`0x4208`, = separator grey) around the
  opaque icon — the zero-bake option; dark icon square inside the halo accepted (DEV-3-4).
  Revisit only if the human glance (D1) finds it too subtle.
- **OQ2 (persist vs cancel-then-amber):** highlight **persists** through the switch — the
  release path paints the amber bar over the still-highlighted slot and `switchApp()`'s
  final `renderTaskbar` clears both. Calmer option, no extra paint.
- **OQ3 (300 ms canvas cooldown load-bearing?):** untouched, still parked.
- **OQ4 (cmdTap divergence):** unchanged — TASK-280 remains open; T_TBFB_04 documents the
  release-cooldown half of the divergence in an assertion.
