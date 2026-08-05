# VE Review — M-WEBRADIO-POSBAR-SMOOTH

> Owner: VE · Date: 2026-08-05 · Reviewed at commit 437e4e2 (doc Status: draft)
> Scope: TESTABILITY review, same convention as `sys-reboot-wifi-multi-VE-review.md`.
> Doc: `docs/architecture/designs/M-WEBRADIO-POSBAR-SMOOTH.md`
> Every code claim was independently re-verified against the tree, not taken on the design
> doc's word. Findings labelled VE-n, classified blocker / major / minor, each with a proposed
> resolution. Architect disposition to follow.

---

## Code-claim verification

Verified true in tree (independent re-check, not just trusting the design doc's own citations):

- `_bufPct` computation (`webRadioApp.h:950-953`) and the redraw gate (`webRadioApp.h:976-981`)
  match the doc exactly. `loop()` (`main.cpp:4072-4164`) has no `delay()` call in its body —
  confirmed by direct read of the function, not re-derived from the doc's claim alone.
- `drawBufferBar()` (`winampDisplay.h:170-184`) does unconditionally re-blit the full 248×10
  groove every call; `blitSprite()` (`winampDisplay.h:871-876`) is one `pushImage()` per row.
  Spotify's `updateSeekThumb()` (`winampDisplay.h:306-322`) does only blit the old/new thumb
  regions — the ~4.8× cost comparison holds.
- TASK-220/TASK-253 history (`tasks-archive.md:4668-4707`, `6105-6117`) confirmed: 15-point
  hysteresis → cut to 2-point specifically to fix visible thumb jumps. Doc's framing of this as
  "the same tension, opposite direction" is accurate, not overstated.
- `perf.h`'s `MAX_PATHS = 10` (`perf.h:34`) and its 10 current call sites match the doc's count.
  **One thing the doc did not surface, found on independent re-read**: `record()`'s slot match is
  `s[i].name == name` (`perf.h:52`) — **pointer equality, not `strcmp`** (confirmed by the file's
  own comment at `perf.h:37`: "pointer-compared (always a string literal at call sites)"). This is
  the basis for VE-2 below.
- `set wrBufPct` (`webRadioApp.h:1573-1580`) does force-write `_bufPct` and call `_drawPosbar()`
  unconditionally, exactly as the doc describes — but the doc never follows this claim to its
  testability consequence (VE-1 below).

---

## Findings

### VE-1 (major) — the design doesn't say what happens to the one existing DUT-verification hook for this exact code path

`set wrBufPct` (`webRadioApp.h:1571-1580`) exists specifically so the buffer bar's thumb position
is "visually checkable on DUT" without real playback (its own TASK-253 comment). It force-writes
`_bufPct` directly and calls `_drawPosbar()` **immediately and unconditionally** — bypassing any
gate. This design adds two new gates in front of the draw (an EMA on the value, a time-based
minimum redraw interval) but never states whether `set wrBufPct` should keep forcing an immediate,
ungated draw (in which case it becomes useless for testing the *new* smoothing/rate-limit
behavior specifically, since it always routes around both) or should instead feed the raw
pre-EMA input and go through the normal gated path (in which case a test issuing `set wrBufPct 50`
can no longer assume an immediate visual update, which several of this project's other DUT tests
implicitly assume of `set`-driven debug hooks). Either answer is fine — but the doc's own exit
criteria ("thumb position visually checkable on DUT," implicitly relying on this exact hook) don't
work without picking one. **Resolution:** specify explicitly — recommend `set wrBufPct` continues
to force an *immediate* draw (bypass both new gates, same as today), documented as "debug-forced,
does not exercise the smoothing/rate-limit path" — and add a **separate** debug hook (or reuse the
new `get wrPosbar` getter's raw-value field) if DUT verification of the gated path itself is
needed.

### VE-2 (major) — perf-path instrumentation as specced risks silently fragmenting into multiple slots

`perf::record()` matches by **pointer identity** on `name`, not string content (`perf.h:37,52`,
confirmed above). The design's Lean step 1 says instrument "around `_drawPosbar()`'s **call
site**" (singular) — but `_drawPosbar()` actually has **three** call sites today: `tick()`'s gated
redraw (`webRadioApp.h:980`), `_drawFull()`'s unconditional full-repaint call
(`webRadioApp.h:1988`), and `dbgSet`'s debug-forced call (`webRadioApp.h:1578`, see VE-1). If a
Developer instruments at each of these three call sites rather than once inside `_drawPosbar()`'s
own body, three independently-written `"wr.posbar"` string literals are not guaranteed by the
language to intern to the same address — worst case, this silently fragments one logical path
into up to three `perf.h` slots. Given `MAX_PATHS` is only being bumped to 11 (one slot of
headroom over today's 10), this could immediately re-overflow — and `perf::record()`'s overflow
behavior is a **silent drop** (`perf.h:57`), so the failure wouldn't announce itself; it would
just make the exit criterion "wr.posbar path present and non-dropped" quietly false. **Resolution:**
instrument exactly once, inside `_drawPosbar()`'s own body (wrapping the two `blitSprite()` calls),
not at any of its three callers — resolves the ambiguity and the pointer-identity risk together.

### VE-3 (major) — before/after redraw-count comparison isn't specified as multi-trial, despite this project's own repeated history of single-shot DUT measurements being unreliable

The exit criteria's baseline/post comparison ("5 min real-playback window," example) reads as a
single trial each side. This project has been burned by exactly this class of measurement before:
the `touch-ux-panel-VE-review.md`'s own VE-2-1 finding ("single-shot in an RF environment...one
outage burst in either window flips the verdict either way") and `M-HEAP-FRAGMENTATION.md`'s OQ4
spike (needed 3 repeats after a first single-sample result proved non-reproducible). A WiFi hiccup
or a slow/fast station mirror during either window would change the buffer's real fill/drain
behavior independent of anything this design changes, confounding a single-sample comparison.
**Resolution:** require ≥3 trials each side (same station, comparable conditions), or explicitly
correlate against `[wifi-ev]` per the established M-WIFI-DIAG attribution protocol and exclude/
re-run outage-affected windows, before scoring the comparison.

### VE-4 (major) — the new getter doesn't expose which gate is currently binding, undermining the tuning methodology OQ1/OQ2 themselves call for

OQ1 and OQ2 explicitly punt the EMA-alpha and minimum-redraw-interval constants to "a DUT tuning
pass using the new `get wrPosbar` getter" — but the getter as specced (Lean step 1: "redraws,
lastIntervalMs, bufPctRaw, bufPctSmoothed") reports outcomes, not which of the two independent
gates (value-delta vs. time-interval) most recently *blocked* a redraw. Tuning two interacting
thresholds without visibility into which one is the binding constraint at any given moment is
trial-and-error in the dark — exactly the ambiguity this project's own house convention pushes
against elsewhere (e.g. `wifiDiag`'s `[wifi-sup]` log line reports `downMs` alongside the kick,
not just "kicked"). **Resolution:** getter (or a paired log line) reports which gate is currently
binding — e.g. a `lastSkipReason: delta|interval|none` field — so OQ1/OQ2's own DUT tuning pass has
something to actually reason from.

### VE-5 (minor) — "human eyeball, no visible jumps" doesn't say how a *live* observation is made, given this project's own established DUT-capture constraint

Same underlying constraint this session's earlier VE review already established
(`sys-reboot-wifi-multi-VE-review.md`'s VE-1-2): connecting `run/screendump` (or any fresh
`Dut`-based tool) resets the DUT via CH340 DTR-on-open (`best_practices.md`, LL-051). Unlike the
Settings-navigation case, WebRadio doesn't need prior navigation to reach (it can be the
boot-resting app) — but the reset-on-connect problem still applies to *capturing* live behavior:
attaching a screenshot tool mid-observation would reboot the device, restarting WiFi and the
stream from scratch, perturbing exactly the continuous-playback buffer behavior being observed.
**Resolution:** state explicitly this is a live-eyeball-on-the-physical-LCD (or phone-camera video)
check, not a tool-assisted capture — same resolution pattern as the prior review's VE-1-2.

### VE-6 (minor) — confirm the `MAX_PATHS` 10→11 bump is actually forced in the build variant that will be tested, not just safe to make regardless

The "exactly 10 used" arithmetic (`perf.h:28-34`) counts `wr.pump` (`SERIAL_DEBUG`-gated) and
`screenlog.tick` (`SCREEN_LOG`-gated) as simultaneously present — true only in a build compiling
**both** flags at once. If the actual DUT-test build (`cyd2usb_winamp_debug`, needed anyway for
the `SERIAL_DEBUG`-gated `get wrPosbar`) doesn't also define `SCREEN_LOG`, the real per-build
worst case today might be 9, not 10, and the bump — while always cheap and safe to make — may not
be strictly forced by adding one more unconditional path in that specific variant. Not blocking;
bumping regardless is harmless. **Resolution:** worth a one-line confirmation in the doc, not a
design change.

### VE-7 (informational, confirmed-safe) — change is scoped away from playback/state logic

Confirmed by reading the surrounding code: every change this design proposes is confined to
`webRadioApp.h`'s `PLAYING`-branch buffer-bar block and `winampDisplay.h`'s `drawBufferBar()` —
none of it touches `_state` transitions, auto-skip, stream-death detection, or ICY title logic.
The doc's own "regression: existing WebRadio DUT suite unaffected" exit criterion is plausible by
scope alone. No resolution needed — recorded so it isn't re-litigated.

---

## Verdict

**Approve-with-changes.** No blockers — the design's core lean (EMA + time-gate + partial-diff
blit + instrumentation-first) is sound and correctly avoids re-litigating TASK-253's own prior
fix. Four majors (VE-1 through VE-4) are all real testability gaps that would undermine the
design's own exit criteria or tuning methodology if left unaddressed, but none argue against the
design itself — all are additive clarifications/instrumentation-precision fixes, the same
character as the majors found in this session's prior VE reviews.

| Doc | Verdict | Blockers | Majors |
|---|---|---|---|
| M-WEBRADIO-POSBAR-SMOOTH | **approve-with-changes** | — | VE-1, VE-2, VE-3, VE-4 |

Recommend Architect fold the four majors into the design doc (Lean/decision or Exit criteria
sections, matching this session's established pattern) before scheduling; minors/informational
can be picked up at implementation time.
