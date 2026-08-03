# Design — M-WEBRADIO-REAL-VIS-WAVE: real audio for WebRadio's "wave" mode

> Owner: Architect
> Status: implemented (2026-08-03, TASK-388 — see ADR-056's Amendment 2)
> Date: 2026-08-02 (amended 2026-08-02, same day, post-PROP-009)
> Feeds: ADR-056 (amended 2026-08-03 — see that doc's Amendment 2)
> Tracked-as: TASK-388 (DONE 2026-08-03; rescoped 2026-08-02 — see amendment)
> Registers: vu-004 · X045
> Deps: M-WEBRADIO-REAL-VIS.md (rung 2 precedent, the `realAudio` seam),
> M-WAVE-ATLAS-wave-atlas.md / M-WAVE-ATLAS-firmware-playback.md (what
> "wave" currently means in the shipped tap-cycle), PROP-005 (does **not**
> cover this mode — see Context)

## Context / pain points

Unlike Spectrum, **no PROP-005 rung ever touched a "wave" mode.** EXP-015
through EXP-018 are entirely VU/spectrum work. Before this doc, there is no
R&D groundwork to graduate — this is new design space, not a graduation.

It's also worth being precise about what "wave" *means* in the current
firmware, because there are two unrelated things that name could refer to,
and only one of them is even reachable today:

- **`VIS_WAVE_ATLAS`** (`tickWaveAtlas()`) — what WebRadio's tap-cycle
  actually shows today (Atlas → **WaveAtlas** → VU → Blank → Atlas). This
  plays back a pre-baked atlas of waveform rows captured from real Winamp
  footage (`gen/wave_atlas.h`, flash-resident), advancing one frame every
  50 ms **unconditionally** — it doesn't even gate on `playing`, let alone
  read any live level. It is canned animation, same category as
  `VIS_ATLAS_MODE`'s bar playback, and structurally cannot become "real
  audio driven" without becoming a different mode — there's no live input
  seam in it at all today, not even the one `tickAtlas()`/`tickWaveAtlas()`
  explicitly lack per the rung-2 design doc's VE finding.
- **`VIS_WAVE`** (`tickWave()`) — a *different*, currently-dormant mode:
  a synthetic phase-advancing sine, vertical-filled between samples,
  amplitude-scaled by `lLvl` (one of the same statics rung 2 already
  writes real data into). It was pulled from the tap-cycle at the same
  time Spectrum was ("superseded by atlases") and is dead code from the
  user's perspective today, exactly like `VIS_SPECTRUM`.

So "real audio-driven wave" splits into two genuinely different asks:

1. **Feed real amplitude into the dormant synthetic sine (`VIS_WAVE`).**
   Same shape as rung 2 (VU) and the sibling Spectrum design: reuses an
   existing writer (`lLevelRef()`), needs the same kind of tap-cycle
   reachability decision Spectrum needs, zero new storage. Cheap, but
   honest caveat: it still draws a fake sine, just one whose amplitude
   now tracks real audio. It does not show the actual waveform shape —
   nothing about the signal's frequency content or transient shape reaches
   the display, only its instantaneous peak level (already true of VU).
2. **Render an actual oscilloscope trace of real decoded samples** — the
   thing a user would probably picture on hearing "real audio wave." This
   needs the pump task to hand the UI thread a small buffer of recent
   (decimated) sample values, one per horizontal pixel column (76 px wide
   per the vis area geometry), refreshed at the render tick rate. That is
   new mutable cross-task state with no existing same-shaped storage to
   reuse-swap into — unlike every PROP-005 rung, which specifically
   succeeded by finding storage already sized right (`lLevelRef()`/
   `rLevelRef()` for rung 2; `specPeak`/`specH`/`specVel` for rung 3).
   EXP-018 already found that **even one new 4-byte pointer, alone,
   overflows this board's `SERIAL_DEBUG`-enabled link** — a genuinely new
   ~76-byte (minimum, single-buffered, `int8_t`) sample array is a much
   harder version of a problem that was already at the wall.

## Goals

*(Original goals below predate the amendment and are kept for history —
goal 1's "decide explicitly" was satisfied by the amendment; goal 3's
"not a production PR" premise held right up until PROP-009 cleared it the
same session.)*

1. Decide, explicitly, which of the two asks above this design commits to
   now — don't let "real wave" quietly become whichever one is easier to
   build. **Satisfied by the amendment: Option B (19-column), decided
   after both were on the table.**
2. ~~If (1) ships an amplitude-only sine (Option A below): keep it
   WebRadio-scoped and follow the exact reachability pattern the sibling
   Spectrum design proposes.~~ Superseded — Option A does not ship.
3. If a true oscilloscope trace (Option B) is wanted, this design must
   *not* pretend it can be scoped as a small production PR the way rung 2
   was — the storage wall makes it a research question first. **This held
   until PROP-009 (EXP-021/022) actually cleared that research question,
   same session — the amendment reflects the *result* of that gate, not a
   decision to skip it.**
4. No new static storage for whichever option ships. **Amended: the
   shipped option (19-column trace) needs exactly 19 new bytes — EXP-021
   confirmed this fits within measured headroom (40B). Not zero, but
   measured and cleared, same rigor every PROP-005 rung applied.**

## Design space (options + tradeoffs)

**Option A — Real amplitude into the dormant synthetic sine (`VIS_WAVE`),
revived into WebRadio's tap-cycle only.**
- *For*: Directly mirrors rung 2's already-proven mechanism —
  `tickWave(originX, originY, mainBg, lLvl)` already takes an `lLvl`
  parameter; the caller just needs to pass the real value instead of the
  synthetic one when `realAudio` is set, same branch shape `vu::tick()`
  already has for VU. Zero new storage, zero new R&D needed, ships on the
  same footing as the sibling Spectrum design. Low risk, immediately
  buildable.
- *Against*: It's a modest, honestly-marginal upgrade — the sine's *shape*
  stays fake, only its *height* becomes real (identical caveat to VU
  becoming "real" in rung 2, but wave's fake shape is more visually
  obvious than a bar's height ever was, since a viewer's mental model of
  "wave" implies waveform shape, not just amplitude). Risks looking like
  a half-measure if shipped without setting that expectation.
- Also reopens the same reachability question as Spectrum: `VIS_WAVE` was
  pulled from the cycle for the same "superseded by atlases" reason, with
  the same unclear technical-vs-UX-preference history. If both this doc
  and the Spectrum sibling ship Option B(ish)/Option B(equivalent)
  simultaneously, WebRadio's tap-cycle grows by two stops in one pass
  (Atlas → WaveAtlas → VU → **Wave** → **Spectrum** → Blank → Atlas) —
  worth a single combined UX sign-off rather than two separate ones, since
  a 6-stop cycle is a different product feel than today's 4-stop one.

**Option B — True oscilloscope trace from real decoded samples, replacing
or sitting alongside `VIS_WAVE_ATLAS` in WebRadio mode.**
- *For*: The actual thing "real audio wave" evokes — visibly different
  per station/track, not just louder/quieter.
- *Against*: Needs new cross-task storage this board has already proven
  it cannot casually afford (EXP-018's single-pointer overflow finding).
  No existing rung or spike de-risked the storage shape, the decimation
  scheme (how do you turn a ~44.1kHz block into 76 representative points
  per ~50ms tick without cheap-but-ugly aliasing), or the decode-tail cost
  of building that buffer (untested — unlike rungs 1-3, which all measured
  identical to a no-op). Committing to a production design here would
  repeat the mistake PROP-005's own ladder was structured to avoid:
  building before the cheap-kill-first spike says it's affordable.
- Candidate storage-reuse angles worth an R&D spike, none yet verified:
  (a) can the trace buffer overlay `tickSpectrum`'s now-promoted
  `specPeak`/`specH`/`specVel` namespace-scope arrays when Wave and
  Spectrum modes are mutually exclusive at any given tick (same
  single-active-mode argument that lets VU and Spectrum already coexist
  without doubling storage)? (b) does a coarser trace (fewer than 76
  columns, e.g. reusing `SPEC_BARS`'s 19-wide granularity blown up
  visually) sidestep needing new byte-count entirely by riding the
  spectrum arrays directly? Both are spike questions, not answered here.

**Option C — Ship nothing for wave; leave `VIS_WAVE_ATLAS` as the sole
wave-shaped mode in WebRadio, same as Spotify.**
- *For*: Zero risk, zero storage question, honestly reflects that this
  mode has no R&D groundwork yet unlike Spectrum.
- *Against*: Answers the user's actual question ("can we get wave driven
  by real audio") with "not yet," which may be a perfectly fine answer,
  but shouldn't be reached by default — it should be a chosen scope, with
  Option A's cheap win still on the table if wanted.

## Lean / decision

**Superseded 2026-08-02 — amendment below. Original Lean (Option A now,
Option B deferred) is kept as struck-through history, not current
guidance.**

~~Option A now, Option B deferred behind a new R&D proposal. Ship the
amplitude-real synthetic sine as a small, low-risk WebRadio-scoped change,
using the exact mechanism and reachability pattern the sibling Spectrum
design already lays out. Option B is not ready for a production Lean — it
needs a PROP-005-style ladder of its own first. Recommend PM register a
new proposal (PROP-009) scoped narrowly to the cheap-kill-first storage
question.~~

**Amendment (2026-08-02, same day): PROP-009 ran to completion (EXP-021,
EXP-022) faster than this doc anticipated — same DUT session, not a later
one — and validated a 19-column Option B variant on all three of its own
kill gates: storage (fits today's measured 40-byte headroom directly, no
reuse-overlay needed), decode-tail (44ms, noise vs. the 42ms baseline),
and visual quality (screendump pairs show the trace changing *shape*, not
just amplitude, between a jagged speech passage and a quiet pause — the
exact property Option A structurally cannot produce, per this doc's own
Option A "Against" bullet above). Human decision, presented with both
validated options: **replace Option A with the validated 19-column real
trace.** TASK-388 now ships Option B (19-column variant), not Option A.
Option A's design and code (none written) are abandoned, not deferred —
this is a replacement, not a "ship A, keep B in reserve."

Rationale for replace-over-both: Option A's entire value proposition was
"cheap and low-risk since B wasn't proven affordable yet." Once B is
proven equally cheap (same decode-tail, comparable storage cost — 19B vs.
0B) and produces a strictly better result on the actual ask ("real
audio-driven wave" meaning shape, not just height), shipping A alongside
it would mean maintaining two "wave-shaped" modes where one is objectively
worse at the same cost — not a meaningful choice for a user tap-cycling
through, just cycle-length bloat. WebRadio's tap-cycle stays the
previously-decided 6 stops (Atlas → WaveAtlas → VU → **Wave** → Spectrum
→ Blank → Atlas) — "Wave" now means the 19-column trace, not the sine.

## Open questions

- ~~Tap-cycle length~~ **Resolved 2026-08-02** (human decision, joint with
  the Spectrum sibling): ship both Wave (this doc, Option A) and Spectrum
  together; keep `VIS_WAVE_ATLAS` rather than dropping it despite the
  conceptual overlap with a real-audio Wave mode. WebRadio's tap-cycle
  becomes the 6-stop Atlas → WaveAtlas → VU → Wave → Spectrum → Blank →
  Atlas. The resulting platform asymmetry vs. Spotify (which keeps the
  4-stop Atlas/WaveAtlas/VU/Blank cycle) is accepted, not an oversight.
- Whether `VIS_WAVE`'s original removal was a technical constraint or a
  UX preference is still unconfirmed, but no longer blocking — it doesn't
  change the above decision either way.
- Should PROP-009 (if commissioned) evaluate peak-only vs. a smarter
  decimation (e.g. min/max envelope per column, closer to how a real
  oscilloscope or Winamp's own waveform display would compress samples)
  from the start, given EXP-016 already found peak-only "jumpy" for the
  VU case and a raw-sample trace is more exposed to the same problem?

## Exit criteria

**~~Option A~~ — does not ship, exit criteria moot, kept for history:**
- ~~`tickWave()`'s amplitude source branches on `realAudio`...~~

**Option B, 19-column variant (current production scope, per the
amendment) — production implementation still needs to do the following;
EXP-021/022 proved feasibility on a throwaway spike branch, not shipped
production code:**
- Port `vu::waveTraceRef()` (19-byte namespace-scope static) and
  `vu::tickWaveTrace()` from `rnd/webradio-wave-spike` (commits `bcd2d0c`,
  `b698a2f`) into production code — the spike's renderer was a
  full-redraw-per-call implementation for observability, not tuned for
  production (no dirty-diff; acceptable starting point, optimize only if
  a real cost problem shows up).
- Wire `VIS_WAVE`'s tap-cycle slot to call the real trace path instead of
  the old synthetic sine when WebRadio is active (mirrors the sibling
  Spectrum design's per-caller branch shape) — Spotify's cycle stays
  Atlas/WaveAtlas/VU/Blank, unaffected, same as every prior rung's
  non-negotiable.
- Re-verify storage headroom fresh at implementation time, don't trust
  EXP-021's 40-byte snapshot as still current (explicit warning in that
  report) — re-run the `.map` check before merging.
- Decode-tail (`get wrPump`) confirmed unchanged vs. TASK-278/42ms
  baseline on the production build (EXP-022 measured 44ms on the spike
  build specifically — re-confirm on the real integration).
- WebRadio tap-cycle reaches Wave with the real trace visibly animating
  in *shape* (not just amplitude) — screendump-diff liveliness check,
  same shape as T_WR_VIS_01/02/03, extended to assert shape variance
  (e.g. comparing trace point-spread/variance across two captures), not
  just a raw pixel-delta threshold, since shape-vs-amplitude is the whole
  point of this mode existing.
- Human eyeball gate: confirm the trace reads as a real waveform on
  live program material, ideally across more than one station (this
  session's evidence was one station, an NPO news/talk relay — worth
  spot-checking a music station too, since speech's silence-vs-speech
  contrast may look more dramatic than continuous music would).
