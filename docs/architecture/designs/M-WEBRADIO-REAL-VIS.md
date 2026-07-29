# Design — M-WEBRADIO-REAL-VIS: real audio-driven visualizer for WebRadio

> Owner: Architect
> Status: draft
> Date: 2026-07-29
> Feeds: ADR-056 (proposed — amends ADR-009 for the WebRadio case only)
> Tracked-as: — (not yet scheduled; PM schedules from PROP-007)
> Registers: vu-002 · X043
> Deps: M-WEBRADIO-WINAMP-UI item 4 (companion doc — this is that item's
> outcome), ADR-009 (synthetic VU decision), TASK-350 (caller-supplied
> `vu::tick()` seam), TASK-278 (pump-task decode-tail discipline),
> PROP-005/PROP-007, EXP-015/016/017/018
> Reviewed: Developer (implementability), VE (testability) — 2026-07-29,
> sequential review pass before this draft's Testing and Validation section
> was written; findings folded in throughout

## Context / pain points

ADR-009 chose a synthetic (decorative) VU envelope because the Spotify path
never has access to real audio on-device — the Web API endpoints that would
have supplied it (`audio-features`/`audio-analysis`) returned 403 for this
app's client. That constraint is specific to Spotify's data source; it does
not apply to WebRadio, which decodes real PCM locally on the audioI2S pump
task. M-WEBRADIO-WINAMP-UI item 4 registered PROP-005 to find out whether
real levels were *affordable* under the same decode-tail budget (TASK-278)
and the board's DRAM constraints, without an answer yet on whether they'd be
worth shipping.

That R&D is now done (EXP-015 through EXP-018). Findings that shape this
design:

- **Cost is a non-issue.** Real per-block peak envelope (rung 2) and real
  19-band Goertzel energy (rung 3) both measured identical `maxPumpMs`
  (42ms) to a no-op baseline, on real DUT hardware, across four independent
  measurements. Decode-tail regression — the R&D proposal's primary kill
  gate — never materialized at any rung.
- **Storage, not CPU, is the actual constraint**, and it's a hard one: this
  board's `SERIAL_DEBUG`-enabled builds link with **zero bytes of static-BSS
  headroom** (confirmed via the linker `.map` — `_bss_end` sits exactly at
  the segment boundary). This isn't specific to the debug env; it recurred
  identically on a production-plus-`SERIAL_DEBUG`-only base. The finding
  generalizes past "this one feature was tight" to: *any future change on
  this board that needs new persistent cross-task state must either reuse
  existing storage or it will not link*, independent of how small the
  addition is (a single 4-byte pointer alone overflowed).
- **Quality is validated for rung 2, unresolved for rung 3.** Rung 2's real
  envelope visibly animates with real audio (531/9800 changed px between
  screendumps 1.5s apart) and needs no further tuning. Rung 3's real bands
  also visibly animate but read under-driven relative to rung 2's broadband
  envelope — each band only sees its own narrow frequency slice — and would
  need per-band gain compensation before it looks as finished. A peak-vs-RMS
  A/B for rung 2 (EXP-017) was cost-neutral but inconclusive on feel; not a
  blocker, but not a closed question either.
- **Only `VIS_VU` (and the out-of-scope `VIS_SPECTRUM`) actually read the
  envelope** (VE review finding). `tickAtlas(originX, originY, mainBg,
  playing)` and `tickWaveAtlas(originX, originY, mainBg)` take no level
  argument at all — they gate frame-advance on `playing` only, identical
  before and after this change. `VIS_ATLAS_MODE` is also `vu::s_modeRef()`'s
  default and the tap-cycle's first stop. This matters for goals and exit
  criteria below: "ships a real envelope" must be read as "for VU mode
  specifically," not as atlas becoming audio-reactive, and any verification
  done at the default mode would observe nothing new.
- **`VIS_SPECTRUM` is currently dead code from the user's perspective** —
  `vu::nextMode()`'s tap-cycle is Atlas → WaveAtlas → VU → Blank → Atlas;
  spectrum mode was dropped from the cycle at some prior point ("superseded
  by atlases," per the in-code comment) and is unreachable without a
  developer forcing it. Rung 3 would be the first production reason to
  revisit that — reviving it is a UX call this design does not make.

The open question this design resolves: **what, precisely, ships now, and
what does the resulting architecture decision say** — given the ADR-009
premise is now falsified for one of the two players sharing this render path
but not the other.

## Goals

1. Ship a real-audio-driven envelope for WebRadio's `VIS_VU` mode,
   replacing ADR-009's synthetic decoration for that path only. (Corrected
   from an earlier draft that also claimed "atlas gating" — per VE review,
   `tickAtlas`/`tickWaveAtlas` don't consume `lLevelRef()`/`rLevelRef()` at
   all; atlas frame-advance is gated on `playing` only, unchanged by this
   design. `VIS_ATLAS_MODE` is also the default mode and the tap-cycle's
   first stop, so this distinction is exit-criteria-relevant, not pedantic.)
2. Leave Spotify's synthetic path byte-for-byte unaffected — ADR-009's
   reasoning still holds there (no local audio, no plan to change that).
3. Keep the production change small and low-risk: no build-flag-gated
   experimental code should reach `main`; no new static storage should be
   required (matching the constraint above).
4. Establish the storage-reuse pattern (promote existing renderer state to
   namespace-scope accessors; single writer swaps between UI thread and
   pump task depending on active mode) as the sanctioned approach for this
   board, so future work in this area doesn't re-discover the DRAM wall from
   scratch.
5. Explicitly bound scope so the harder, still-open question (does
   `VIS_SPECTRUM` come back, and with what visual tuning) doesn't block
   landing the part that's ready.

## Design space (options + tradeoffs)

**Option A — Ship rung 2 only now; rung 3 stays R&D-documented, not
production-scheduled.**
- *For*: Matches PROP-007 exactly. Rung 2 has no open quality questions and
  no unresolved UX decision attached to it (VU + atlas modes are already
  in the tap-cycle, unlike spectrum). Smallest, cleanest PR — a Developer
  can implement it from PROP-007 without a design negotiation.
- *Against*: Leaves rung 3's proven-cheap result "on the shelf" — someone
  has to remember to come back to it.

**Option B — Ship rung 2 + rung 3 together, reviving `VIS_SPECTRUM` in the
tap-cycle in the same pass.**
- *For*: One integration pass instead of two; rung 3's cost story is already
  as strong as rung 2's.
- *Against*: Bundles a UX decision (does spectrum mode belong back in the
  cycle at all — it was deliberately removed once) and unfinished tuning
  work (per-band gain) into what would otherwise be a small, low-risk PR.
  Widens the diff surface (a second real-mode writer path, `updateSpectrumBar`
  promoted to a shared cross-task function) without a corresponding
  increase in confidence about the *result* looking good. Violates goal 5.

**Option C — Defer both; request further R&D on ballistics/gain feel before
any production commit.**
- *For*: Maximizes confidence before touching production code.
- *Against*: Rung 2 has no known open question left to resolve by more R&D
  — the remaining gap (human eyeball on ballistics feel) is a VE/human
  acceptance step, not an R&D question. Delaying it doesn't buy new
  information; it just delays a low-risk win.

## Lean / decision

**Option A.** Rung 2 ships as its own scoped production task; rung 3 stays
documented (EXP-018, this doc) as a validated-but-not-scheduled follow-on.
This keeps the UX question (spectrum mode's tap-cycle reachability) and the
unfinished tuning work (per-band gain) from gating something that's already
clean.

This crystallizes as **ADR-056**, scoped narrowly: it amends ADR-009 by
adding "for WebRadio specifically, when real PCM is available on the pump
task, use a real per-block peak envelope instead of synthesis" — Spotify's
synthetic path and ADR-009's original reasoning are otherwise untouched. The
ADR should also record the storage-reuse pattern as the sanctioned technique
for this class of problem on this board (existing-storage-reuse over
new-allocation), since it will recur the next time anyone wants to move
state across the pump-task/UI-thread boundary here.

## Open questions

1. **Does `VIS_SPECTRUM` return to the tap-cycle?** Independent of rung 3's
   technical readiness, this is a product/UX call (a mode was deliberately
   removed once) that this design does not make. Needs a human decision
   before rung 3 is scheduled, not just an Architect feasibility read.
2. **Rung 3 follow-up ownership**: does it get its own design doc once (1)
   is answered and gain-tuning is done, or fold into an ADR-056 amendment
   later? Lean: separate design doc when it's actually scheduled — don't
   pre-write it against an unresolved UX question.
3. **RMS-with-gain**: worth a small dedicated R&D follow-up, or shelve
   indefinitely? No architectural blocker either way; PM/human call.
4. **DRAM margin monitoring**: given the zero-headroom finding is a
   structural property of this board's `SERIAL_DEBUG` builds, not a one-off,
   should `run/check` gain a gate that fails loudly the moment *any* new
   static byte is added to a `SERIAL_DEBUG` build, rather than relying on
   each future change to independently rediscover this via a failed link?
   (Candidate BP/QM item, not resolved here.)

## Testing and Validation

Written jointly with VE input (sequential review pass, 2026-07-29) — this
is VE's domain, not something the Architect should specify unilaterally.

**Two separate build targets, not one ambiguous "production build"**
(Developer + VE both flagged the original draft's phrasing as unrunnable
literally): `cyd2usb_winamp` (true production) never defines
`SERIAL_DEBUG` and cannot execute any `get`/`set` serial command —
`run_serialdbg_tests.py` itself is pinned to `cyd2usb_winamp_debug`. So:

- **Artifact correctness** (no scratch flags, no static-BSS growth) is
  `run/check` against `cyd2usb_winamp` — build-and-link succeeding *is* the
  BSS-budget proof (EXP-015/016/018 all hit this as a hard link failure,
  not a soft warning, so there is no silent-regression risk here).
- **Behavioral/decode-tail verification** (serial-driven) runs against the
  standing `cyd2usb_winamp_debug` env — the only env that can run `get
  wrPump`/`get visMode`/`switchApp` at all.

**New regression tests (VE to add, IDs reserved here):**

- **T_WR_VIS_01** — decode-tail regression, isolated measurement. Enter
  WebRadio, play a station ≥45s, then `get wrPump` **alone** — no
  concurrent screendump or tap traffic in the same window. This isolation
  requirement is not optional: EXP-017 measured a false 272ms regression
  (vs. the true 42ms) specifically because its first pass bundled a
  screendump-diff probe into the same window as the `wrPump` read, and CPU
  contention from that traffic — not the audio math — produced the spike.
  **Pass/fail: `maxPumpMs <= 50`** (TASK-278's fought-down decode-tail
  ceiling; EXP-015/016/017/018 measured 42ms with zero variance across four
  independent rungs, so 50ms leaves noise margin without masking a real
  regression).
- **T_WR_VIS_02** — real envelope animates, and *only* in the mode that
  reads it (this is the test that catches "shipped the feature, defaulted
  to a mode that can't show it," per the Goal-1 correction above). At the
  default mode (`VIS_ATLAS_MODE`, confirm via `get visMode`), two
  screendumps of the vis region 1.5s apart should show near-zero pixel
  delta (Atlas doesn't read the envelope — this is a negative control, not
  a bug). Tap the vis zone twice to reach `VIS_VU` (confirm via `get
  visMode`), repeat the screendump pair — expect a materially nonzero delta
  (EXP-016 measured 531/9800; treat >100/9800 as "clearly animating," the
  low end EXP-018 still called a pass).
- **T_WR_VIS_03** — Spotify's synthetic path is unaffected (Goal 2
  regression guard). Same two-screendump-1.5s-apart check in `VIS_VU`
  mode, on the Spotify app, confirms the pre-existing synthetic animation
  is unchanged.
- Register `test_ids: [T_WR_VIS_01, T_WR_VIS_02, T_WR_VIS_03]` on `vu-002`
  and `test_coverage:` the same three IDs on `X043` once written (both
  currently `[]` — design-time reservation only).

**Human-only gate (BP-048), explicitly not a DUT/serial substitute:**

- Eyeball pass across ≥2-3 different WebRadio stations, **explicitly in
  `VIS_VU` mode** (state this requirement to whoever runs the check — it
  is not automatic, there is no `set visMode` command, only `get`), on both
  a loud/dynamic station and a quiet/talk station — peak detection's
  "jumpiness" concern (EXP-016) is program-material-dependent, so a single
  easy station passing eyeball doesn't clear the gate.
- Also eyeball the **eject transition** (WebRadio → Spotify) while a
  station is playing loud. The synthetic branch does not zero `lLvl`/`rLvl`
  on entry — only `!playing` does — so whatever value the real path last
  wrote becomes the synthetic path's starting point, decaying via the same
  shared `ATTACK`/`RELEASE` constants rather than snapping to a fresh
  baseline. This is a new transition shape that didn't exist when both
  sides were synthetic; confirm it reads as an acceptable decay, not a
  visible jump, immediately after eject.

**Interface note carried forward from VE review**: the single-writer
guarantee `X043` describes is not just convention — it's mechanically
enforced by `switchApp()` calling the outgoing app's `suspend()`
synchronously before the incoming app's `init()`/`resume()` (no tick
window for both to be active), and `WebRadioApp::suspend()`'s
`_stopAudio()` blocking on `s_wrAudioMutex` (the same mutex the pump task
holds around every `Audio::loop()` call) until any in-flight write has
completed. Developer/VE should cite this mechanism in `X043`'s notes
rather than leaving the invariant as an unexplained assertion.

## Exit criteria

**Developer:**
- `vu::tick()`'s `realAudio` parameter and the peak-envelope hook promoted
  from `WR_VIS_ENVELOPE`-flag-gated experimental code to permanent,
  always-on WebRadio behavior.
- All five scratch `platformio.ini` envs from `rnd/webradio-vis`
  (`cyd2usb_winamp_debug_vistap`, `_vistap2`, `_envelope`, `_envelope_rms`,
  `_bands`) deleted.
- **The other three `#ifdef` branches in `audio_process_extern` deleted
  outright** (`WR_VIS_BANDS`, `WR_VIS_RMS`, `WR_VIS_TAP_SPIKE`), not just
  their envs — per Developer review, only the peak-envelope body should
  remain, unconditionally compiled. Deleting envs alone would satisfy the
  letter of "no scratch flags reach main" while leaving three dead
  preprocessor branches behind; no other exit criterion catches that.
- `vu-002`'s feature_inventory entry completed with real `git_ref`/`files`.

**Automated (`run/check`, `cyd2usb_winamp`):**
- All 6 gates pass, including build-and-link succeeding at all (the actual
  BSS-budget proof — see Testing and Validation above).

**VE (`cyd2usb_winamp_debug`, serial-driven):**
- T_WR_VIS_01/02/03 pass per the thresholds above, T_WR_VIS_01 run in
  isolation from any concurrent screendump/tap traffic.

**Human (BP-048, not delegable to Developer or VE alone):**
- Eyeball pass, explicitly in `VIS_VU` mode, across ≥2-3 stations
  (loud + quiet) plus the eject-transition check, per Testing and
  Validation above.
- ADR-056 moves `proposed` → `accepted` with human sign-off.

**Architect:**
- `architecture.md` synchronized with the accepted decision post-VE
  sign-off, per standard practice.
