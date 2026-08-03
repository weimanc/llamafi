# Design — M-WEBRADIO-REAL-VIS-SPECTRUM: graduate real per-band spectrum energy for WebRadio

> Owner: Architect
> Status: implemented (2026-08-03, TASK-387 — see ADR-056's amendment)
> Date: 2026-08-02
> Feeds: ADR-056 (amended 2026-08-03 — see that doc's Amendment section)
> Tracked-as: TASK-387 (DONE 2026-08-03)
> Registers: vu-003 · X044
> Deps: M-WEBRADIO-REAL-VIS.md (rung 2, shipped — this is rung 3 of the same
> PROP-005 ladder), ADR-056 (accepted, amends ADR-009 for WebRadio VU only —
> this doc proposes widening that amendment), PROP-005/EXP-018 (the R&D that
> already validated this rung), TASK-278 (decode-tail discipline)

## Context / pain points

PROP-005's rung 3 (EXP-018, 2026-07-29, branch `rnd/webradio-vis`) already
built and DUT-measured a real 19-band Goertzel spectrum analyzer for
WebRadio: one resonator per band, log-spaced 80 Hz–14 kHz, computed per
decoded PCM block on the pump task. It was deliberately **not** included in
rung 2's production graduation (`M-WEBRADIO-REAL-VIS.md`, Option A) to keep
that PR small and because rung 3 carries two unresolved items rung 2 didn't
have:

1. **`VIS_SPECTRUM` is unreachable in production.** `vu::nextMode()`'s
   tap-cycle is Atlas → WaveAtlas → VU → Blank → Atlas. Spectrum mode was
   pulled from the cycle at some prior point ("superseded by atlases," per
   the in-code comment in `vuMeter.h`) and needs a developer to force
   `vu::s_modeRef()` directly to even render. Reviving it is a UX call, not
   an engineering one.
2. **Visual quality is validated as animating, not as finished.** EXP-018's
   screendump diff (100/9800 changed px) confirms real per-band content —
   less dramatic than rung 2's 531/9800 because each band only sees its own
   narrow slice, vs. rung 2's one broadband number driving every bar. The
   report explicitly flags per-band levels as "under-driven" relative to
   rung 2 and recommends gain compensation before shipping.

Everything else is already de-risked: cost is proven free (`maxPumpMs`
identical across all four PROP-005 rungs, 42 ms, on real DUT hardware), and
the storage problem — this board's `SERIAL_DEBUG`-enabled builds link with
zero bytes of static-BSS headroom, where even one new 4-byte pointer
overflows the link — is already solved by promoting `tickSpectrum`'s
existing `specPeak`/`specH`/`specVel` arrays to namespace-scope accessors
(same pattern as `lLevelRef()`/`rLevelRef()`) and extracting the shared
`vu::updateSpectrumBar(i, lvl)` the pump task calls directly. Net new
static bytes measured at zero.

This design exists to resolve items 1–2 so the already-built rung 3 code
can graduate the same way rung 2 did.

## Goals

1. Make `VIS_SPECTRUM` reachable by users in WebRadio mode without
   resurrecting it in Spotify's synthetic path (ADR-009's Spotify reasoning
   is untouched — same boundary rung 2 drew).
2. Ship real per-band energy (EXP-018's `updateSpectrumBar` mechanism)
   as WebRadio's data source for that mode, mirroring rung 2's `realAudio`
   seam pattern (`vu::tick(..., realAudio)` already exists; extend its
   scope from VU-only to VU+Spectrum, or add a narrower flag — see Design
   space).
3. Resolve the gain question with a decision, not a deferral: either ship
   a per-band makeup curve (EXP-018's suggestion) or accept the subdued
   look as-is with a stated reason. Silence on this in the graduation PR
   would repeat rung 2's original mistake of shipping an unresolved
   quality question (it didn't have one; this rung does).
4. Keep the change WebRadio-scoped: Spotify's tap-cycle, if `VIS_SPECTRUM`
   re-enters it, must not suddenly show a mode that silently does nothing
   (or reverts to a stale synthetic pattern) under Spotify — the mode's
   *availability* per active app needs an explicit answer, not an implicit
   one.
5. No new static storage beyond what EXP-018 already measured at zero.

## Design space (options + tradeoffs)

**Option A — Revive `VIS_SPECTRUM` in the tap-cycle for both apps; real
data under WebRadio, synthetic (existing `tickSpectrum` math) under
Spotify.**
- *For*: One tap-cycle everywhere; no per-app cycle divergence to reason
  about; Spotify users get the spectrum mode back (a UX reversal of the
  original removal, but presumably not why it was pulled — worth
  confirming with human before assuming this is wanted).
- *Against*: Reopens a UX decision ("superseded by atlases") that predates
  this design and wasn't made for technical reasons captured anywhere
  found in this repo — reviving it for Spotify is a product call this
  design doc cannot make unilaterally. Widens the diff (Spotify's call
  site would need the synthetic `tickSpectrum` path re-verified against
  current atlas-cycle expectations, which nobody has touched in a while).

**Option B — Revive `VIS_SPECTRUM` in WebRadio's tap-cycle only; Spotify's
cycle stays Atlas → WaveAtlas → VU → Blank (unchanged, spectrum absent).**
- *For*: Matches rung 2's precedent exactly (WebRadio-scoped change, zero
  behavioral diff for Spotify). Doesn't require resolving why Spectrum was
  pulled originally — it stays pulled for the app it was pulled from,
  and is added fresh for the app that now has a reason to have it (real
  data, not the same decorative one that arguably justified removal).
  `vu::nextMode()` already needs no change if the tap-cycle can branch by
  active app the same way `realAudio` already branches by caller (a
  per-app cycle table or an `appHasSpectrum` bool gating whether `nextMode`
  ever lands on `VIS_SPECTRUM`).
- *Against*: Two different tap-cycles for the same widget across apps is
  a small ongoing cognitive cost for whoever touches `vuMeter.h` next —
  needs a clear comment anchoring *why* (real-data availability, not
  arbitrary), same discipline rung 2 used for the `realAudio` flag.

**Option C — Ship rung 3's engine but keep `VIS_SPECTRUM` reachable only
via serial debug (`set visMode spectrum` or equivalent), not the tap-cycle,
pending a human product decision on whether it belongs in the cycle at
all.**
- *For*: Fully de-risks the UX question by not deciding it — ships the
  proven-cheap real data path immediately, defers only the reachability
  UX call.
- *Against*: Ships a feature real users can't reach without a debug build.
  Contradicts PROP-005's original purpose (a *visible* upgrade over
  ADR-009's synthetic decoration) if nobody can see it. Only defensible as
  a stopgap, not an end state.

## Lean / decision

**Option B**, with the per-band gain question resolved inline (not
deferred to a third pass): apply a flat per-band makeup gain — a small
`constexpr` table (log-spaced, mirroring the existing center-frequency
table already in flash/`.rodata` from EXP-018, zero new DRAM) chosen to
roughly flatten pink-noise-shaped program material to the same visual
energy rung 2's broadband envelope showed — as part of this graduation,
not a follow-up. This keeps the two open items rung 2 deliberately parked
from turning into a third open-ended round; either it looks acceptably
close to rung 2's liveliness after one gain pass, or VE's human eyeball
gate (below) sends it back for one more gain iteration, same discipline
`M-WEBRADIO-REAL-VIS.md`'s VU rollout already used.

Reachability: WebRadio's tap-cycle becomes Atlas → WaveAtlas → VU →
**Wave** → **Spectrum** → Blank → Atlas (human decision 2026-08-02: ship
both this design and the sibling Wave design's Option A together, keep
`VIS_WAVE_ATLAS` rather than dropping it — see that doc's Open Questions
for the joint framing). Spotify's cycle is untouched (Atlas → WaveAtlas →
VU → Blank). The branch point is `nextMode()` gaining an `appHasSpectrum`
(or equivalent per-caller) parameter — same shape as `vu::tick()`'s
existing `realAudio` parameter, not a new abstraction.

This crystallizes as an **amendment to ADR-056** (or a new ADR if the
human/QM prefers a fresh record over re-opening an accepted one — Architect
default is to amend, since the reasoning ADR-056 already captured for VU
extends unchanged to Spectrum: "for WebRadio specifically, when real PCM is
available, use real data instead of synthesis").

## Open questions

- ~~Tap-cycle length~~ **Resolved 2026-08-02** (human decision, joint with
  the sibling Wave design): ship both Spectrum (this doc) and Wave
  (`M-WEBRADIO-REAL-VIS-WAVE.md` Option A) together, keep `VIS_WAVE_ATLAS`
  rather than dropping it. WebRadio's tap-cycle becomes the 6-stop
  Atlas → WaveAtlas → VU → Wave → Spectrum → Blank → Atlas.
- **Was `VIS_SPECTRUM`'s original removal purely a UX preference
  ("superseded by atlases") or was there a technical reason (cost,
  storage, something else) that this design should re-verify doesn't
  still apply to Spotify's synthetic path?** Nothing found in this repo's
  history explains the *why* beyond the in-code comment. Doesn't block
  Option B (Spotify is untouched either way), but the human should confirm
  they're fine with Spotify staying spectrum-less if Option B ships this
  as WebRadio-only, since it does leave the platforms visibly inconsistent.
- **Gain table derivation**: EXP-018 suggests a "pink-noise-style makeup
  curve" but didn't derive one. This design proposes deriving it
  empirically against 1–2 live WebRadio stations during the DUT gate
  below, not analytically in advance — matching how the color/geometry
  constants in `vuMeter.h` were already derived (measured from reference
  material, not computed from theory).
- **Does peak-vs-RMS matter here the way EXP-016 flagged it for rung 2?**
  Rung 3 reuses `updateSpectrumBar`'s existing spring-damper smoothing
  (already tuned for the synthetic mode's feel), so this is lower-risk
  than rung 2's raw peak-only question was — but worth the same quick A/B
  if the gain-tuning eyeball pass reveals jumpiness.

## Exit criteria

- `updateSpectrumBar` real-data path lands with zero new static bytes
  (linker `.map` diff against the pre-change build, same verification
  EXP-018 already did on the RnD branch — must hold on `main` too).
- Decode-tail (`get wrPump`, `maxPumpMs`) unchanged vs. the TASK-278/rung-2
  baseline (42 ms) — same kill gate as every prior rung.
- WebRadio tap-cycle reaches Spectrum; Spotify tap-cycle does not (VE
  regression test on both).
- Human eyeball gate (BP-048-style, per rung 2's precedent): spectrum mode
  visibly tracks real program material and reads acceptably close to VU
  mode's liveliness after the gain pass — not identical, but not
  "obviously broken" either.
- New VE test ids added to `run_serialdbg_tests.py` for spectrum-mode
  reachability + a screendump-diff liveliness check (mirrors
  T_WR_VIS_01/02/03's shape for rung 2).
