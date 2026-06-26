# Design — M-WEBRADIO-NOPSRAM: No-PSRAM playback viability via a Spotify-disabled build

> Owner: Architect
> Status: **sketch / proposed** (2026-06-26) — not implemented; PM to schedule (R&D-flavoured, runs on a branch)
> Tracked-as: M-WEBRADIO-NOPSRAM (roadmap); feeds TASK-241 / TASK-233 / ADR-045; unblocks around TASK-243
> Deps: M-WEBRADIO (firmware complete), TASK-239/240 (prior reclaim), EXP-007 (heap spike)

## Problem

WebRadio MP3 playback is unstable on the production no-PSRAM CYD. Per EXP-007 / TASK-233
the wall is **not total free RAM** but the **largest contiguous DMA-capable block**: the
Helix decoder needs ~22.7 KB across 9 buffers, effective audio heap ≈ `free − 38.9 KB`
(a caps-restricted dead region), leaving ~5 KB margin → intermittent
`MP3Decoder_AllocateBuffers` failures, and the input-buffer ⟷ decoder being zero-sum
makes the underrun fix (a bigger input buffer) impossible. ADR-045 concluded "stable
no-PSRAM playback = NO-GO." TASK-239/240 reclaimed ~11 KB and TASK-241 got a *provisional*
pass before being blocked on TASK-243 (Premium) for a valid tight-heap baseline.

## Hypothesis

Removing `spotifyTask` from the build frees materially more — and of the right kind:

| Reclaimed | Size | Notes |
|-----------|------|-------|
| `spotifyTask` stack | **~10 KB** | Heap-resident for life. **`tlsYield` does NOT free it** — it frees the TLS *session* and *suspends* the task. Unreclaimable in the multi-app build; never created here. |
| TLS-session fragmentation | ~50 KB churn | The session is alloc'd/freed repeatedly; never allocating it gives a **cleaner, less-fragmented heap from boot** → larger contiguous block (the actual wall). |
| Album-art / metadata / queue snapshots | a few KB | Spotify-side resident buffers. |

This is a bigger, contiguity-targeted reclaim than TASK-239/240. **It also needs no
Spotify auth**, so the TASK-241 viability test — stalled on TASK-243 — becomes runnable.

## Approach (minimal, reversible — no `AppId` surgery)

A dedicated PlatformIO env so the multi-app production build is untouched:

```ini
[env:cyd2usb_webradio]
extends = env:cyd2usb_winamp
build_flags = ${env:cyd2usb_winamp.build_flags} -DDISABLE_SPOTIFY
```

Two guarded sites under `-DDISABLE_SPOTIFY`:
1. **`main.cpp:~2092`** — skip `spotifyTask::begin(&spotify)` → the FreeRTOS task (stack +
   TLS) is never created.
2. **`spotifyTaskStorage.cpp` `tlsYield()` / `tlsResume()`** — early-return (no task/session
   to yield). This neutralises all 34 call sites (WebRadio `_play`, the dataTask fetchers,
   main) without editing them.

The Spotify **app object** stays registered and compiles (so `AppId::Spotify`, the boot
default, and WebRadio's eject target keep working) — it simply renders a dormant
"disconnected" UI because nothing polls. Entry to WebRadio is unchanged (eject).

> Open question (A): keep the dormant Spotify stub, or also boot directly into WebRadio +
> make eject a no-op? Stub is lower-risk for the experiment; direct-boot is cleaner for a
> shipped variant. Decide after the heap measurement.

## Measurement / decision gate

1. Flash `cyd2usb_webradio`; record `get heap` + `get stacks` at boot and at WebRadio entry;
   compare `free` / `maxAlloc` against the multi-app build. Confirm the **contiguous block**
   (`maxAlloc`) — not just nominal free — actually rose.
2. Re-run the TASK-241 input-buffer experiment (`setBufsize` ~16 KB) under the reclaimed
   budget; play across stations.
3. **Exit criterion:** stable PLAYING ≥ 60 s within ≤ 6 auto-skips on ≥ 90 % of cold entries
   AND underruns measurably drop with the larger input buffer.
   - **PASS** → supersede ADR-045 ("stable via Spotify-disabled build"); promote a shipped
     WebRadio-focused variant (resolve Open A) and an ADR for the build-time split.
   - **FAIL** → the 38.9 KB caps-restricted block is the hard wall; ADR-045 stands; this
     variant is shelved.

## Risks / open questions

- **(B) Contiguity, not total free.** If the freed RAM lands outside the decoder's
  caps-class, `free` rises but `maxAlloc` doesn't → no help. The boot/entry measurement is
  the cheap gate before any playback testing.
- **(C) Scope creep to a real product split.** This is an *experiment* first. A shipped
  Spotify-or-WebRadio build matrix (registry-level disable + boot default + eject behaviour
  + settings) is a follow-on milestone only if the gate passes.
- **(D) Regression surface.** The two guards must be `#ifdef`-isolated so the default
  multi-app build is byte-unchanged; `./run/check` must still pass for `cyd2usb_winamp`.

## Out of scope

Runtime (non-build) Spotify toggle; removing the Spotify app from the registry; any
production build-matrix changes. Those are downstream of a PASS.
