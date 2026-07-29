# PROP-007 — Graduate WebRadio's real peak envelope (PROP-005 rung 2)

> Owner: R&D Engineer
> Status: proposed 2026-07-29
> Origin: PROP-005 (TASK-351), rungs 1–2 — EXP-015, EXP-016, EXP-017
> Branch: `rnd/webradio-vis` (reference implementation; per AGENTS.md, R&D branches are never merged to main directly — Developer designs the production PR from this proposal, borrowing at discretion)

## Summary

Replace ADR-009's synthetic (decorative, fake) VU/atlas envelope with a real
per-block peak envelope **for WebRadio only** — Spotify's synthetic path is
untouched, since Spotify never touches audio on-device and ADR-009's premise
still holds there. WebRadio does decode real PCM locally (the audioI2S pump
task), so its vis can now track the actual audio stream instead of dancing to
a fake swell/beat/noise recipe.

Scope is deliberately narrow: **rung 2 only** (VU meter + atlas gating).
Rung 3 (real spectrum-band energy, EXP-018) is cost-cleared but visually
unfinished — see "Explicitly out of scope" below; hand off separately, don't
bundle it into this PR.

## Prototype evidence

- **Tap point exists and is free** (EXP-015): `ESP32-audioI2S`'s weak-linked
  `audio_process_extern(int16_t* buff, uint16_t len, bool* continueI2S)`
  fires once per decoded PCM block, pre-gain/filter/volume, on the wrAudio
  pump task (`Audio.cpp:4215-4221`). `get wrPump` `maxPumpMs` measured
  identical (42ms) with the hook doing nothing vs. touching every sample —
  no decode-tail cost from the tap point itself.
- **Real peak envelope, same cost** (EXP-016): computing per-block peak
  L/R and feeding it into `vu::lLevelRef()`/`rLevelRef()` (via a new
  `realAudio` parameter on `vu::tick()`, default `false` — Spotify's call
  site needs zero changes) still measured `maxPumpMs=42ms`, identical to
  the no-op baseline. DUT-verified visually: two screendumps 1.5s apart
  during live playback showed 531/9800 changed pixels in the vis region,
  confirming it tracks real audio rather than sitting flat.
- **Zero new persistent storage** — the change reuses `vu::lLevelRef()`/
  `rLevelRef()`, the exact same statics the synthetic path already writes;
  it does not add any new global/static state. This mattered structurally:
  any `SERIAL_DEBUG`-enabled build on this board has ~0 bytes of static-BSS
  headroom (confirmed via the linker `.map` — `_bss_end` sits exactly at
  the segment boundary), so a naive "just add an L/R snapshot" approach
  would not have linked.
- **Peak vs. RMS A/B, inconclusive but not a blocker** (EXP-017): a
  running-RMS variant costs the same (42ms, confirmed after ruling out a
  confounded first measurement — see EXP-017 for the methodology note).
  RMS reads visually duller than peak without a compensating gain factor,
  which wasn't implemented; not a fair comparison as tried. Recommend
  shipping peak un-tuned; RMS+gain is a future refinement, not a
  prerequisite.

## Suggested scope

**Include:**
- `vu::tick()`'s optional `realAudio` parameter (default `false`) — already
  proven not to require any Spotify-side change.
- A per-block peak-envelope hook (`audio_process_extern`) wired
  permanently into WebRadio's build (not behind a scratch flag) — i.e.
  promote from this session's `WR_VIS_ENVELOPE`-gated experimental code to
  the WebRadio app's normal, always-compiled-in behavior.
- WebRadio's `tick()` call site passing `realAudio=true` unconditionally
  (no build flag needed in production).

**Explicitly out of scope for this PR:**
- Rung 3 (real spectrum-band energy for `VIS_SPECTRUM`, EXP-018) — cost is
  clear (also 42ms) but the visual isn't tuned (per-band levels read
  under-driven vs. rung 2's broadband envelope, likely needs per-band gain)
  and it touches `VIS_SPECTRUM`, a mode currently unreachable via
  `vu::nextMode()`'s tap-cycle (superseded by the atlas modes) — reviving
  it is a separate product decision, not a byproduct of this change.
- The RMS variant (`WR_VIS_RMS`) — not gain-compensated, not recommended.
- All scratch `platformio.ini` envs from this R&D branch
  (`cyd2usb_winamp_debug_vistap`, `_vistap2`, `_envelope`, `_envelope_rms`,
  `_bands`) — delete, don't carry into production `platformio.ini`.

## Risks / unknowns

- **Ballistics feel**: peak detection can read as "jumpier" than classic VU
  ballistics on some program material (noted, not resolved, in EXP-016).
  Recommend a human-eyeball pass across a few different stations before
  closing out the production task — this project's established acceptance
  pattern for visual changes (cf. BP-048) is a better gate here than pixel
  diffs alone.
- **Signature change surface**: `vu::tick()` gained a parameter. Verified
  both call sites (Spotify's in `main.cpp`, WebRadio's in `webRadioApp.h`)
  compile clean on this branch; re-verify after rebasing onto current
  `main`, since it may have moved since this branch was cut.
- **DRAM margin re-check**: the zero-headroom finding (EXP-015) was
  measured against `cyd2usb_winamp_debug` at a specific point in `main`'s
  history. `run/check`'s `golden.sha256` + mem-layout budget gates should
  be re-run post-rebase in case other work has since consumed the
  remaining slack — this change adds no new bytes itself, but the margin
  it depends on could have moved.

## Recommended next step

Hand to PM for scheduling (new production task, e.g. `TASK-36x`); Developer
designs the production implementation from this proposal, referencing
`rnd/webradio-vis` (commits `7324912`, `17d560f`, `a11ea97`) at their
discretion — that branch is reference material, not something to merge
directly.

## Branch

`rnd/webradio-vis`
