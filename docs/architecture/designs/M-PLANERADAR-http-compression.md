# Design — PlaneRadar fetch: HTTP response compression feasibility

> Owner: Architect
> Status: draft
> Date: 2026-08-06
> Feeds: — (no ADR yet; this doc is the feasibility gate TASK-403 requires before any
>   implementation)
> Tracked-as: TASK-403
> Registers: — (no new feature-id, no new cross-feature interaction — same conclusion TASK-361's
>   own fetch-cascade change reached; this stays internal to `planeradar-001`'s existing fetch path)

## Context / pain points

TASK-361's candidate-scoping pass (2026-07-25) found `opendata.adsb.fi` supports response
compression — `curl -H "Accept-Encoding: br"` returned a 9.2 KB body vs. 56.9 KB uncompressed at
the same busy-JFK query, a 6.15x reduction — and flagged it as "probably the single highest-impact
lever available" against the size-scaling truncation failure TASK-361 was chasing, explicitly out
of that task's scope. TASK-403 filed it as the follow-up. Gate: design/feasibility pass first, no
implementation without one, given the DRAM-budget risk flagged at filing time.

**Load-bearing fact that changes the urgency calculus:** TASK-361 did not stop at the candidate
scoping. It shipped a radius-capped 2nd retry (`fetchPlaneRadar()` cascade: full-radius attempt →
full-radius retry → radius-capped retry at `min(distNm/2, 10nm)`, gated on both priors failing)
and DUT-proved it fires correctly end-to-end via a fault-injection hook
(`prForceParseFail`/`debugForcePlaneRadarParseFail`) after multiple live soaks at JFK-scale
(50-66 KB, matching-or-exceeding the original regression's regime) failed to reproduce the "both
attempts fail" condition organically. Net: the mitigation this design doc might obsolete or
complement is not a stopgap awaiting a real fix — it is a code-reviewed, fault-injection-verified
fix already carrying production traffic, currently absorbing whatever residual truncation rate
exists. See `docs/project/tasks.md` TASK-361 (full soak-by-soak record) and the memory note
`[[project_planeradar_state]]`.

## Goals

Determine whether HTTP response compression for the PlaneRadar fetch is:
1. **Technically feasible** on this board's DRAM budget (the stated gate concern) — without
   redoing the WebRadio arena/reclaim saga.
2. **Mechanically feasible** given the vendored Arduino-ESP32 `HTTPClient.cpp`'s unconditional
   `Accept-Encoding: identity` header, with no user override point as vendored.
3. **Worth scheduling now**, given TASK-361's mitigation is confirmed working and not currently
   failing organically.

This doc answers all three; it does not implement anything.

## Design space (options + tradeoffs)

### A. Codec choice: brotli vs. gzip/deflate

TASK-361's only real measurement was `Accept-Encoding: br` (brotli). Brotli was not chosen
deliberately — it was the first codec tried. For an embedded target the two codecs are not
equivalent:

| | Brotli | gzip/deflate |
|---|---|---|
| Decoder code size | Large (reference decoder is C but the window/context-modeling machinery is substantially heavier than deflate); no existing footprint in this codebase | Small — `miniz`/`tinfl` is a few hundred lines, a well-worn embedded/OTA path |
| Window size | Up to 16 MB (`WBITS` up to 24 declared by encoder); decoder must honor whatever the stream declares, not something the client can just cap | Hard RFC1951 ceiling of 32 KB, decoder-side allocation is a known, bounded quantity |
| Embedded precedent in this project | None | None yet, but the *pattern* (vendor a framework-shadowing lib, transient scratch buffer freed after use) is already used repeatedly (see RAM section) |
| Server support on `opendata.adsb.fi` | Confirmed (`curl -H "Accept-Encoding: br"` tested directly) | **Unconfirmed — not tested.** Cloudflare-fronted origins almost always serve gzip (it's the most universally-supported HTTP encoding), but this project's own discipline (BP-044: confirm, don't assume) says verify before relying on it |

**Lean: gzip/deflate, not brotli.** The DRAM-budget risk the gate exists to catch is almost
entirely a brotli-shaped risk (uncertain decoder footprint, uncertain window ceiling). Deflate's
window is capped at 32 KB by spec — a known, bounded number this doc can actually clear against
the manifest (see below) instead of gesturing at "brotli decode is heavier." Reduction ratio on
gzip is unmeasured for this specific payload but JSON of this shape (repetitive keys, similar
numeric fields per record) typically compresses well under either codec; brotli usually edges out
gzip by some margin, not an order of magnitude — there's no reason to assume gzip would fail to
meaningfully help the size-scaling truncation problem TASK-361 characterized.

### B. Header-override mechanism: patch the toolchain vs. vendor a shadow library

The gate's own framing ("this project already has a `LOCAL_PATCHES.md` precedent for
SpotifyArduino — same mechanism") undersold how directly applicable the precedent is. Checked
`app/lib/` directly: this project **already vendors `WiFiClientSecure`** — a framework-supplied
library, not a third-party one — specifically to shadow the Arduino-ESP32 core's own copy via
PlatformIO's LDF project-lib-precedence (`app/platformio.ini`'s `lib_ldf_mode = deep+` +
`app/lib/` auto-scan). PATCH-001/PATCH-003 live there today (see ADR-057, LL-095's memory note,
`docs/rnd/reports/EXP-019-ceefax-tls-leak-isolation.md`) and are exercised in production every TLS
connection this firmware makes. **The exact mechanism TASK-403 needs for `HTTPClient.cpp` is not
hypothetical — it's a load-bearing pattern already running on this board.**

**Lean: vendor `app/lib/HTTPClient/`** (mirroring the `WiFiClientSecure` and `SpotifyArduino`
precedents), patch the single `Accept-Encoding` send site to be overridable (e.g. an optional
`setAcceptEncoding()` setter defaulting to today's `identity` string, so every other caller is
unaffected), and document it `LOCAL_PATCHES.md`-style. Patching the PlatformIO package cache
directly (the alternative floated implicitly by "no user override point as vendored") is rejected
— not reproducible across machines/re-installs, and this project has explicitly moved away from
exactly that failure mode before (this is the same class of problem TASK-404 just closed: a
config source that isn't actually part of the committed, buildable tree).

### C. Decompression integration point

`prParseStream()` (`dataTaskStorage.cpp:1192`) already takes `Stream&`, and every other fetch path
already calls `http.getStream()` and hands it straight to a parser (`deserializeJson(doc,
http.getStream(), ...)`). A decompressing adapter that implements `Stream` and wraps
`http.getStream()` slots into this exact call site with **zero change to `prParseStream()`
itself** — it just receives an already-inflated byte stream. This is the cleanest of the options
considered; no parser-side branching on `content-encoding` is needed once the adapter is chosen at
the call site based on the response header.

### D. Do nothing (stay on TASK-361's mitigation)

Real option, not a strawman. TASK-361's radius-capped retry2 is code-reviewed and
fault-injection-verified to fire correctly, and three separate follow-up soaks at JFK-scale
traffic (the exact regime that produced the original ~35% failure rate) found the underlying
Cloudflare-edge condition itself not reproducing organically anymore — final failure rate has sat
at 0% in every post-fix soak run, including ones that never needed retry2 at all. There is no
currently-open user-visible symptom this design doc's implementation would fix. Compression would
be a *margin* improvement (fewer retries, lower latency, lower risk if the edge condition
resurfaces at a worse rate) — valuable, not urgent.

## RAM feasibility (the gate's actual concern)

`app/mem_manifest.yaml` today: `ceiling.INTERNAL = 290000`, `headroom.INTERNAL = 60000` (reserved
for the per-fetch mbedTLS working set — already accounts for a `WiFiClientSecure` handshake
in-flight), registered buffer tenants sum to `44464`. That leaves **~185,536 B of nominal
unallocated headroom** in the planner's INTERNAL ceiling as things stand today (re-derive at
implementation time per `[[project_webradio_headroom_finding]]` — this number moves; never trust a
remembered figure over a fresh grep).

A gzip/deflate inflate window is bounded at **32 KB by spec**, allocated only for the duration of
the PlaneRadar fetch and freed the instant the parse completes — the exact same lifecycle
`planeradar_doc` (4096 B), `heatmap_doc` (2560 B), and `crypto_doc` (2048 B) already use, all
justified by the same argument: dataTask is strictly serial, so this scratch buffer is never live
at the same time as any other app's scratch buffer. That argument already carries three registered
tenants in the manifest today; a fourth, larger one is not a new kind of risk, just a bigger
number against the same well-understood budget line.

This is a materially easier problem than WebRadio's audio-path arena (`M-MEMBUDGET`): no
DMA-capable-contiguous requirement (WebRadio's actual wall), no long-lived residency across an
active session, no auto-skip-driven realloc churn requiring a fixed-slot allocator. It's a
one-shot alloc → inflate → parse → free inside a function that's already mutually exclusive with
every other dataTask consumer. **Verdict: feasible without any arena/reclaim design work.**

Flash cost is not zero (miniz/tinfl adds a few KB of code) but is not evaluated here in detail —
worth checking whether esp-idf/newlib already links an inflate implementation for its own OTA
image handling before assuming a new one must be vendored (Open Question below).

## Lean / decision

**Feasible, scoped narrower than the original framing, not urgent.**

1. Target **gzip, not brotli** — lighter decoder, bounded 32 KB window, matches this project's
   existing embedded-scratch-buffer patterns. Brotli is rejected as the implementation target (it
   was never a deliberate choice, just the first thing TASK-361 happened to `curl` with).
2. **Vendor `app/lib/HTTPClient/`**, shadowing the framework copy exactly as `WiFiClientSecure`
   already does — this is a proven mechanism on this exact board, not new ground.
3. Implement as a **decompressing `Stream` adapter** feeding the existing
   `prParseStream(Stream&, ...)` — no parser changes.
4. RAM: a 32 KB transient scratch buffer, registered in `app/mem_manifest.yaml` alongside the
   other dataTask scratch tenants, comfortably clears the current ~185 K nominal headroom. No
   arena/reclaim design needed.
5. **Priority: concur with P3.** TASK-361's mitigation is confirmed working, not currently
   failing in production, and this doc finds no technical blocker that would change that
   calculus. Recommend PM leave this scheduled behind higher-priority work; revisit if either (a)
   the original truncation symptom recurs live (watch for `radius-capped`/`retry2` log lines
   becoming frequent again — see TASK-361's wrap-up), or (b) a future need to shrink fetch
   size/latency emerges for an unrelated reason (e.g. a lower `prPollSec` cadence).

## Open questions

- **OQ1 (blocks implementation start):** does `opendata.adsb.fi` actually serve `gzip` (not just
  the `br` TASK-361 tested)? Verify with `curl -H "Accept-Encoding: gzip"` before writing any
  code — don't assume from the brotli result.
- **OQ2:** actual gzip compression ratio on this JSON shape is unmeasured; re-confirm once OQ1
  lands rather than assuming TASK-361's 6.15x brotli figure carries over.
- **OQ3:** specific embedded inflate implementation — lean `miniz`/`tinfl` (small, permissive
  license, common in ESP-IDF-adjacent OTA tooling) over full `zlib`.
- **OQ4:** does esp-idf/the Arduino-ESP32 core already link an inflate implementation (used for
  compressed OTA images or similar) that could be reused at near-zero added flash cost? Check
  before vendoring a new dependency.
- **OQ5:** the on-the-wire response includes a `Content-Length` for the *compressed* body;
  `prFetchOnce()`'s existing truncation-detection logic (TASK-361's `size=`/`scanned=`
  instrumentation) compares declared vs. received bytes — confirm this still holds sensibly
  against a compressed length, or whether the truncation-detection math needs to move to
  post-inflate byte counts instead.

## Exit criteria

Not implementation criteria for this doc (which does none), but the bar for a future
implementation task to close against:

- `app/lib/HTTPClient/` vendored, `Accept-Encoding` override point added and documented
  `LOCAL_PATCHES.md`-style (mirroring `SpotifyArduino`'s and `WiFiClientSecure`'s existing files).
- gzip round-trip verified against real `adsb.fi` traffic: `content-encoding: gzip` observed,
  inflated body parses to the same aircraft data as the uncompressed path.
- `app/mem_manifest.yaml` gets a new transient-scratch entry for the inflate window, sized to the
  actual measured peak (not assumed 32 KB if the real figure is smaller).
- DUT soak at a JFK-class hub (50 KB+ regime, the size bucket TASK-361 characterized as
  highest-risk) shows first-attempt failure rate improved over TASK-361's post-fix baseline.
- `./run/check` 6/6 green, no DRAM regression on either `cyd2usb_winamp` or the debug env.
