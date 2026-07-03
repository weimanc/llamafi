# VE Panel Review — Touch-UX design trio (TASK-277 / TASK-278 / TASK-279)

> Owner: VE · Date: 2026-07-02 · Reviewed at commit a1cf11c (all three docs Status: draft)
> Scope: TESTABILITY review per the M-WIFI-DIAG panel precedent (that doc §7-8).
> Docs: 1 = M-WR-PLEDIT-SCROLL.md · 2 = M-WR-AUDIO-TASK.md · 3 = M-TASKBAR-FEEDBACK.md
> Every code claim in the docs was verified against the tree, not taken on faith. Claims that
> checked out are listed per doc; findings are labelled VE-<doc>-<n>, classified
> blocker / major / minor, each with a one-line proposed resolution. Architect dispositions.

---

## Code-claim verification (all three docs)

Verified true in tree:

- Doc 1: `WebRadioApp::handleInput` discards Press/Move (`webRadioApp.h:390-391`); auto-follow
  clamp lives in `_play()` (`webRadioApp.h:727-732`); generic-vs-Spotify-coupled audit of
  `winampDisplay.h:302-553` is accurate (tickScroll `:532-553`, updateScrollDirect `:693-707`,
  constants `:621-624` match the values quoted); `drainInjectionQueue` hardwires non-taskbar
  samples to `winampDisplay.handleWinampInput` (`main.cpp:2322-2327`); `SpotifyApp::handleInput`
  is a thin forward (`main.cpp:254-262`); `cmdTick` only drives `winampDisplay.tickScroll`
  (`main.cpp:2513-2530`).
- Doc 2: `s_wr_audio->loop()` runs on loopTask (`webRadioApp.h:310`); spotifyTask prio 1 /
  core 1 (`spotifyTaskStorage.cpp:38-40`), dataTask prio 1 / core 1 (`dataTaskStorage.cpp:104-105`);
  TWDT 15 s with loopTask + CPU0-idle subscribed, core-1 idle not (`main.cpp:1946-1948`); ICY
  queue is `xQueueOverwrite` from the audio callback (`webRadioApp.h:87-92`); TASK-263
  underrun metrics exist behind `MEMBUDGET_PHASE1` (`webRadioApp.h:332-341, 513-522`).
- Doc 3: taskbar zone dispatch precedes the cooldown/busy gate (`main.cpp:1865` vs `:1884`) —
  the doc's cooldown correction is **right** and worth preserving; press paints zero pixels
  (`tbGesturePress`, `winampDisplay.h:63-69`); switch anatomy (suspend → setBusy(false) →
  275×240 wipe → init/resume → renderTaskbar) matches `main.cpp:1819-1858`; transport
  pressed-sprite precedent at `winampDisplay.h:414-415`; injected taskbar samples route to the
  real gesture handlers (`main.cpp:2312-2321`) and the injected **release** does go through
  `resolvePlayerSlot` (`main.cpp:2294-2296`); `cmdTap`'s taskbar branch skips
  `resolvePlayerSlot` (`main.cpp:2388-2390` vs `:1916`) — OQ4's side-finding is real.

Claims found inaccurate or incomplete are covered by findings below.

---

## Doc 1 — M-WR-PLEDIT-SCROLL (TASK-277)

### VE-1-1 (blocker) — injection reroute covers Press/Move but not Release; end-to-end injected drag cannot complete

The design's prerequisite fix reroutes "non-taskbar **samples**" to
`g_apps[currentAppId]->handleInput`, but the release sentinel is a separate branch hardwired to
`winampDisplay.handleWinampInput(TouchPhase::Release, 0, 0)` (`main.cpp:2300-2302`) — with
**(0,0) coordinates**. As specced, an injected WebRadio drag delivers Press/Move to the new
gesture machine and then hands Release to *Spotify's* machine: the WebRadio gesture never ends,
`wrScroll.drag` never returns to idle, and the headline exit criterion ("`drag …` exercises the
WebRadio path") is unimplementable. Two sub-gaps: (a) the Release branch must also reroute to
the active app, passing the **last-sample** coordinates, not (0,0); (b) the design must state
that Release with an active gesture is **captured** by the gesture (anchored-state drag-end
before any eject/transport hit-test) — today `WebRadioApp::handleInput` hit-tests eject and
transport first on every Release (`webRadioApp.h:394-411`), so an injected Release at stale/zero
coordinates could mis-hit or fall through.
**Resolution:** extend the reroute to the release step (app dispatch, last-sample coords) and
add a capture rule to the gesture spec: active gesture consumes Release before hit-tests.

### VE-1-2 (major) — Release-only `cmdTap` dispatch breaks against a Press-anchored machine; existing T_WR_* suite exposed

`cmdTap`'s WebRadio branch calls `handleInput(TouchPhase::Release, x, y)` with **no prior
Press** (`main.cpp:2427-2435`). Today that is exactly how the whole DUT-validated T_WR_* tap
surface (eject, transport, PLEDIT tap-to-play) is driven. A gesture machine whose Release
semantics depend on a press anchor (`_dragStartRow`, dead zone, elapsed) must define what a
Release with no anchor does — if it becomes a no-op, every T_WR_* tap test silently breaks.
**Resolution:** spec a no-anchor fallback — Release in `WRS_IDLE` behaves as today's
tap-at-(x,y) path — and add "T_WR_* tap suite passes unchanged" to the exit criteria alongside
T155-T161.

### VE-1-3 (major) — "auto-skip mid-gesture cancels cleanly" is not agent-executable with current injection primitives

`cmdDrag` always appends a release sentinel (`main.cpp:2504`); the only "held finger" window is
the ≤62 queued samples draining one per loop iteration — sub-second in wall time, and the
watchlist already records T157-T159 as needing redesign for exactly this class of timing
dependence. Auto-skip fires on a ≥2 s pace (`WR_SKIP_PACE_MS`), so gesture-active and
skip-firing cannot be overlapped deterministically. As written this exit criterion needs human
hands.
**Resolution:** add a held-gesture primitive (e.g. `drag … hold` + explicit `release` command),
or a deterministic synchronous trigger (a `set` hook that invokes the cancel path while
`wrScroll.drag != 0`), and write the test protocol into the doc before implementation.

### VE-1-4 (minor) — "deterministically with `tick n dtMs`" overclaims

While a gesture is held, the app's own `tick()` calls `_tickScroll(real dt)` concurrently with
synthetic ticks — same double-integration that forced T158's "≥1 row" tolerance band. The
WebRadio copies inherit it; during PLAYING the inflated loop period makes real-dt contributions
larger, not smaller.
**Resolution:** replace "deterministically" with tolerance-banded assertions per T157-T161
precedent (or add a debug gate that pauses real-tick integration during harness runs).

### VE-1-5 (minor) — `cmdTick` response JSON also needs rerouting

The response reads `winampDisplay.dbgGet("scrollOffset")` (`main.cpp:2521-2523`); the proposed
dispatch change must also swap the reported offset source when WebRadio is active, or the
harness asserts against the wrong machine's state.
**Resolution:** report the active app's offset in the `tick` reply (or have tests use
`get wrScroll` exclusively and note the reply field is Spotify-only).

### VE-1-6 (minor) — reroute changes injected-drag dispatch for *all* apps, not just WebRadio

`g_apps[(int)currentAppId]->handleInput` sends canvas drags to Stock/Settings/Teletext/etc.
handlers that previously never saw injected Press/Move (everything went to `handleWinampInput`).
No known test injects canvas drags with a non-player app active, but that is an assumption.
**Resolution:** grep the harness for `drag` usage per app before landing; T155-T161 re-run is
the Spotify gate (already in exit criteria) — extend the regression sweep to one drag per
non-player app as a smoke.

**Doc 1 verdict: approve-with-changes** — VE-1-1 must be dispositioned before implementation;
the option analysis (C over A/B) is sound and the untouchable-Spotify-path stance is exactly
right for T155-T161 preservation.

---

## Doc 2 — M-WR-AUDIO-TASK (TASK-278)

### VE-2-1 (major) — E0/E2 baseline windows are mismatched, single-shot, and WiFi-confounded

E0 records a **10-min** underrun window; E2 compares a **30-min** soak against it with an
absolute bound (`wrUnderruns ≤ baseline + 1`) — a count metric compared across unequal
durations. Worse, both runs are single-shot in an RF environment with documented AP-side link
flapping (15 disc/min storms; the exact confound that blocked the ADR-045 gate and spawned
M-WIFI-DIAG). One outage burst in either window flips the verdict either way.
**Resolution:** same-length windows (or per-10-min rates), and require `get wifi` /
`[wifi-ev]` capture during both runs with outage windows excluded/annotated per the
M-WIFI-DIAG §3.4 attribution classes before the comparison is scored.

### VE-2-2 (major) — the pump task is invisible to the harness; E4 is unmeasurable as written

`get stacks` enumerates only dataTask and spotifyTask (`main.cpp:2599-2612`). The design names
`uxTaskGetStackHighWaterMark` but no serial surface for it, and there is no
aliveness/cadence/lock observability at all: E1's "paints no longer block the pump" and the
teardown-handshake invariant ("never destroyed while the pump could be inside an Audio
method") have nothing to assert against.
**Resolution:** add `get wrPump` → `{alive, cycles, maxPumpMs, maxMutexWaitMs, stackHwm,
last}` (BP-036 surface), include the pump in `get stacks`, and log a stable-prefix line on
task create/handshake/destroy so E3/E4 teardown checks are grep-able.

### VE-2-3 (major, cross-doc) — perf path budget hits MAX_PATHS exactly and overflows silently in SCREEN_LOG builds

Current named paths: `spotify.poll`, `display.bar`, `display.input`, `app.tick`, `vu.tick`
(5 production) + `screenlog.tick` (SCREEN_LOG). This design adds `wr.pump` + `wr.connect`;
doc 3 adds `shell.switch`. Total: 8 production = `MAX_PATHS` exactly (`perf.h:28`), 9 with
SCREEN_LOG — and `perf::record` **silently drops** on overflow (`perf.h:51`), i.e. the
measurement infrastructure lies precisely in the builds used for measuring.
**Resolution:** bump `MAX_PATHS` to 10 (trivial RAM) in whichever task lands first and record
the slot budget in one place; doc 3's "6 production paths used" count is also wrong (see VE-3-5).

### VE-2-4 (minor) — E1's `display.input` cross-check rests on an unverified premise

`display.input` times `appHandleInput` itself (`main.cpp:2915-2916`), which does no decode
work; the sluggishness mechanism is loop *period* (touch sampled once per iteration), which
`loopMax` already captures. If E0 shows `display.input` is not in fact inflated during
playback, the criterion is vacuous and will "pass" while proving nothing.
**Resolution:** have E0 confirm or drop the `display.input` clause; keep `loopMax` + the
injected-drag drain-rate as the latency evidence.

### VE-2-5 (minor) — E1 aggregation undefined and CONNECTING windows will pollute it

`loopMax` is a per-heartbeat-window max; "≤1.5× baseline over a 10-min window" doesn't say
max-of-maxes vs median-of-windows. And Phase 1 deliberately leaves `connecttohost` blocking
for seconds under the mutex — every auto-skip mid-window produces a legitimate multi-second
loopMax spike that is *out of scope* for this design.
**Resolution:** define the statistic (recommend: median of hb-window loopMax, spikes during
CONNECTING state excluded via `wrState` correlation) in E1 before the baseline run.

### VE-2-6 (minor) — E3's ADR-045 gate re-run inherits the evening-outage environment risk

The gate was blocked 7/10 by unattributed outages until TASK-275; a 10/10 bar without an
attribution rule re-creates that trap.
**Resolution:** state that E3 runs under the `run/wr-gate` `[wifi-ev]` correlation and that
link-attributed failures trigger re-run per the M-WIFI-DIAG §3.4 protocol, not FAIL.

### VE-2-7 (minor) — OQ2 (logSink third writer) and OQ3 (torn perf writes) need a concrete check, not just a question

M-WIFI-DIAG VE-8 already established that cross-task serial writers tear lines.
**Resolution:** add to the soak procedure: grep the soak log for interleaved/torn lines with
the pump alive; if found, the OQ2 fallback (queue `audio_info` like ICY) becomes mandatory.

**Doc 2 verdict: approve-with-changes** — the phased structure (E0 baseline first, Phase 2
explicitly severed from the freshly validated ADR-045/TASK-276 machine) is the right shape;
the gaps are all in measurement rigor and observability surface, all fixable in the doc.

---

## Doc 3 — M-TASKBAR-FEEDBACK (TASK-279)

### VE-3-1 (major) — the injected Press bypasses the shell site where the highlight will be painted

Production press feedback will hang off `appHandleInput`'s taskbar branch (`main.cpp:1880`),
but `drainInjectionQueue` calls `winampDisplay.tbGesturePress` directly (`main.cpp:2315-2316`)
— it never passes through `appHandleInput`. Unless the pressed-slot paint + its timestamped
log line live in one shared shell helper called from **both** dispatch sites, the serialdbg
exit criterion ("injected taskbar drag-tap produces the press-feedback log line in the same
iteration") tests nothing, or worse, requires duplicating the feedback logic in the injection
path where it can drift.
**Resolution:** spec a single shell helper (e.g. `shellTbPress(y)` → highlight paint +
`[shell] tb-press slot=N` log) invoked from `appHandleInput` and `drainInjectionQueue`; same
for the continue/cancel path.

### VE-3-2 (major) — baseline matrix is single-shot per state and sequencing vs TASK-278 is unpinned

Three device states × one measurement each, in a system whose loop period jitters by design
and whose "WebRadio PLAYING" row is precisely what TASK-278 will rewrite. If TASK-278 lands
between this doc's baseline and post-implementation tables, the before/after comparison the
doc calls "honest" is confounded — and the flaky-test history (T-CDWN-01, T169) shows what
single-shot timing assertions cost this project.
**Resolution:** N≥5 injected taps per state reporting median + max, and an explicit sequencing
rule: baseline and post tables are only comparable at the same TASK-278 state — re-baseline if
it lands in between.

### VE-3-3 (minor) — T-TBFB-03 (commit-amber) has no named observable

The amber bar is transient and subliminal on fast switches by design; without a stable log
line for the commit paint the test is human-eye-only on slow switches and impossible on fast
ones.
**Resolution:** add `[shell] tb-commit slot=N` (stable prefix) at the amber paint; T-TBFB-03
asserts the line's presence and its ordering before `[shell] entered N`.

### VE-3-4 (minor) — T-TBFB-02 (cancel-on-scroll) likewise needs a cancel log line

Highlight-cancel at dead-zone exceed is a paint with no observable side effect.
**Resolution:** `[shell] tb-press-cancel` log at the cancel repaint; assert via injected drag
that exceeds `TB_SCROLL_DEAD_ZONE_PX`.

### VE-3-5 (minor) — perf slot count in L-d is wrong; see cross-doc budget VE-2-3

Actual production paths are 5 (`spotify.poll`, `display.bar`, `display.input`, `app.tick`,
`vu.tick`), not 6; `screenlog.tick` is SCREEN_LOG-only. `shell.switch` alone fits, but the
trio's combined additions land exactly at `MAX_PATHS=8` and overflow silently under
SCREEN_LOG.
**Resolution:** correct the count; adopt VE-2-3's `MAX_PATHS` bump.

### VE-3-6 (minor) — endorse OQ4 as a filed task; note one more injection divergence

The `cmdTap` `resolvePlayerSlot` skip (`main.cpp:2388-2390`) is confirmed — T162's `tap`-based
switch never exercises the TASK-259/260 player-slot redirect; the drag-injection release path
*does* (`main.cpp:2295`). Additionally, the injected taskbar release does not set the 300 ms
post-gesture cooldown that production sets (`main.cpp:1919` has no counterpart in
`drainInjectionQueue`), which T-TBFB-04 should be aware of when asserting "cooldown behaviour
unchanged".
**Resolution:** PM files the cmdTap/resolvePlayerSlot follow-up; T-TBFB-* use drag-taps (the
doc already mandates this — keep it normative); T-TBFB-04 asserts via `get cooldown` around a
*production-path-equivalent* injected gesture and documents the injection divergence.

**Doc 3 verdict: approve-with-changes** — the perception-first lean is well-argued, the
cooldown correction is verified and valuable, and the press-to-first-pixel definition is an
honest camera-free proxy; the fixes needed are observability hooks and measurement discipline,
not design changes.

---

## Verdict summary

| Doc | Verdict | Blockers | Majors |
|---|---|---|---|
| 1 — M-WR-PLEDIT-SCROLL | **approve-with-changes** | VE-1-1 | VE-1-2, VE-1-3 |
| 2 — M-WR-AUDIO-TASK | **approve-with-changes** | — | VE-2-1, VE-2-2, VE-2-3 |
| 3 — M-TASKBAR-FEEDBACK | **approve-with-changes** | — | VE-3-1, VE-3-2 |

Cross-doc: VE-2-3 (perf slot budget) binds all three designs — disposition once, apply to the
first-landing task. Regression gates confirmed adequate where stated: T155-T161 (doc 1, must
also add T_WR_* per VE-1-2), T162-T166 (doc 3), ADR-045 gate + wr-soak (doc 2, with VE-2-6's
attribution rule).
