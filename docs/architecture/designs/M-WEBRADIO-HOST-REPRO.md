# Design — M-WEBRADIO-HOST-REPRO: host-side network reproduction harness for WebRadio connectivity

> Owner: Architect
> Status: draft
> Date: 2026-08-03
> Feeds: TASK-390 (informs, does not replace — this is a diagnostic sub-investigation)
> Tracked-as: TASK-391 (filed alongside this doc)
> Registers: none (diagnostic tooling, not a shipping feature — no feature_inventory/
> cross_feature_matrix entries)
> Deps: TASK-390 (WebRadio marquee-freeze investigation, paused, filed 2026-08-03)

## Context / pain points

TASK-390's soak attempt (same session) did not reproduce the originally-reported symptom
(marquee frozen on stale real content), but it did surface a second, real, DUT-observed signal:
WebRadio parked in `ERROR_UNREACHABLE` for 4+ minutes with no visible recovery while playing a
real station (SLAM! DANCE CLASSICS), immediately followed by three consecutive station-list-fetch
failures against radio-browser.info on retry. Both happened in a session where Spotify's
background poll was also failing continuously (`HTTPC_CONNECTION_REFUSED` / `403`).

Three independent external hosts (the stream server, radio-browser.info, Spotify's API) all
failing from the same device in the same window is stronger evidence of a shared network-level
cause than three unrelated app bugs — but "the whole network is down" doesn't fit either, since
the human is presumably still getting normal internet use elsewhere on the same network. The
open question is *what specifically* is failing: DNS, TCP connect latency, TLS, or something
ESP32/WiFi-hardware-specific, and whether it's reproducible independent of the DUT.

**A concrete, high-value lead found while reading the code for this doc, not yet tested:**
`ESP32-audioI2S`'s `Audio::connecttohost()` (`app/lib/ESP32-audioI2S/src/Audio.h:530-531`) defaults
`m_timeout_ms = 250` (plain HTTP) and `m_timeout_ms_ssl = 2700` (HTTPS) — the TCP-connect timeout
budget. `webRadioApp.h` never calls `setConnectionTimeout()` to raise these; the library ships
with them as-is. **250 ms is an extremely tight budget for a real TCP handshake to a remote
icecast/shoutcast host over real consumer internet** — DNS resolution + TCP SYN/ACK to a distant
server can easily exceed that under any WiFi contention (Spotify's concurrent TLS churn is a
candidate contender) or ordinary internet latency variance, with zero relation to whether the
station is actually up. A connect that would succeed in 300-400ms reads identically, from the
app's perspective, to a station that's genuinely dead: `_client->connect(...)` returns false,
`_onPlaybackFailed(connectFail=true)` fires, and auto-skip burns to the next station — which can
just as easily also "fail" the same way for the same reason, explaining an entire list looking
dead without an actual outage. `TASK-295`'s existing timeout bump (`10000ms`, `Audio.cpp:518-519`)
is scoped narrowly to raw-IP hosts hitting a different upstream bug — it doesn't touch the
hostname-based default path this investigation is about.

This doc is *not* proposing the fix (raising the timeout) yet — that's a code change with its own
risk (a longer timeout also means a longer stall on a truly dead host, TWDT-adjacent territory per
TASK-295's own history at the extreme end). It's proposing the measurement that would confirm or
rule out this hypothesis before anyone changes a timeout constant on a guess.

## Goals

1. Determine whether WebRadio's connectivity failures are reproducible from a host machine on the
   same WiFi SSID as the DUT — same router/ISP path, different hardware — to separate "network/
   station/CDN-side problem" from "DUT-specific" (WiFi hardware, ESP32 TLS stack, or app logic).
2. Specifically measure real-world TCP-connect latency to the actual stream hosts WebRadio uses,
   to directly test the 250ms/2700ms-timeout hypothesis above — this is the cheapest, fastest test
   in this doc and should run first, independent of the longer soak.
3. Provide a breadth check (5 stations) and a depth check (1 station, SLAM!, sustained soak) as
   the human requested — the breadth check calibrates "is this widespread," the depth check is
   the closest host-side analog to TASK-390's original sustained-playback question (does
   metadata/connection health degrade over a long single session).
4. Mirror the DUT's actual request shape closely enough that a difference in outcome is
   meaningful — not so closely that building it becomes its own multi-day project. See Design
   space below for exactly where the line is drawn.

## Design space (options + tradeoffs)

**Option A — Raw connect-latency probe only (no ICY parsing, no sustained read).**
- *For*: Directly tests the leading timeout hypothesis in the cheapest possible tool — a handful
  of TCP(+TLS) connects with precise timing, matching `connecttohost()`'s exact request bytes.
  Minutes to build and run, not hours.
- *Against*: Doesn't touch the *sustained* half of the ask (SLAM! soak) or give any signal on
  TASK-390's original ICY-metadata-stall hypothesis — a station that connects fine but stops
  delivering metadata mid-session (the original report's shape) needs a longer-lived connection to
  observe at all.

**Option B — Full protocol-faithful client (buffering ring, MP3 decode, simulated underrun
detection matching `ESP32-audioI2S`'s InBuff semantics).**
- *For*: Highest fidelity — could in principle reproduce decode-side stalls too, not just
  connect-side ones.
- *Against*: Large, uncertain-value engineering effort for a diagnostic tool. The symptom actually
  in evidence so far (`ERROR_UNREACHABLE` = connect-level failure; the original report's frozen
  marquee is a metadata-pipeline question, not a decode-buffer one per TASK-390's own hypothesis
  ranking) doesn't need audio decode fidelity to investigate. Risks becoming a second, unmaintained
  half-implementation of `ESP32-audioI2S` for no evidence-backed reason.

**Option C — Lightweight HTTP + ICY-metadata-aware streaming client, no audio decode.**
Replicates `connecttohost()`'s exact request (GET path, `Host`, `Icy-MetaData:1`,
`Accept-Encoding: identity;q=1,*;q=0`, `Connection: keep-alive`, no `User-Agent` — matching
`Audio.cpp:495-507` verbatim, since some icecast/shoutcast servers behave differently based on
these headers) against the real stream URL, reads the `icy-metaint` response header, and parses
the periodic in-band metadata blocks per the standard ICY protocol to track `StreamTitle` changes
over time — without decoding or playing any audio. Runs both the connect-latency probe (Option A,
folded in as the first phase) and a sustained read-loop that logs: bytes/sec throughput, any
socket drops/reconnects, and every `StreamTitle` change with a timestamp.
- *For*: Covers both the connect-latency hypothesis *and* gives direct, comparable evidence for
  the original metadata-stall hypothesis (a host-side title tracker going quiet while bytes keep
  flowing is the same signature TASK-390 flagged as its lead suspect) — without building an MP3
  decoder. ICY metadata parsing is a small, well-specified, well-understood protocol (metadata
  interval from `icy-metaint`, then one length-prefixed block every N bytes of audio) — bounded,
  known effort.
- *Against*: Still meaningfully more code than Option A. Doesn't test the DUT's actual decode
  path, so a decode-specific bug (unlikely given TASK-390's ranking, but not zero) stays out of
  scope either way.

## Lean / decision

**Option C.** It's the smallest tool that can speak to both open threads (the new connect-timeout
lead and TASK-390's original metadata-stall lead) without taking on decode-fidelity work that
nothing observed so far justifies. Phase 1 (connect-latency, effectively Option A) should be run
and reported on its own before committing to the longer Phase 2 soak — if it already shows
sub-1-second successful connects clustering near or past 250ms, that's strong enough evidence to
go straight to a human decision on raising `setConnectionTimeout()`, without needing the full
75-minute SLAM! soak to make the case.

### Station selection

- **Breadth (5 stations):** query radio-browser directly, replicating the app's own request
  exactly (`dataTaskStorage.cpp:1002-1010`:
  `https://<mirror>/json/stations/search?countrycode=NL&codec=MP3&hidebroken=true&order=votes&reverse=true&limit=<N>&offset=0&bitrateMax=<cap>`,
  mirrors `all.api.radio-browser.info` / `de1.api.radio-browser.info`, `bitrateCap` matching
  `g_settings.webRadioBitrateCap`'s default of 128) — take the top 5 by vote count, same ordering
  the app uses, so the host tool isn't hand-picking easy stations. Do this as its own one-shot
  query, decoupled from the DUT session (don't depend on the DUT's own fetch succeeding — it may
  not, per this session's own 3-failure run).
- **Depth (1 station):** SLAM! — matching the human's original report. If radio-browser's list
  contains multiple SLAM!-branded entries (this session's DUT fetch saw four: `SLAM!`, `SLAM!
  Non Stop`, `Slam! Mixmarathon`, `SLAM! DANCE CLASSICS`), use whichever the DUT most recently
  attempted (`SLAM! DANCE CLASSICS` this session) for direct comparability, not the plain `SLAM!`
  entry, unless a future DUT run changes which one's in play.
- Resolve actual stream URLs (not just names) via the same radio-browser query's `url_resolved`
  field — do not hand-type or guess a stream URL.

### Protocol fidelity (what's replicated, what's deliberately not)

Replicated: HTTP/1.1 GET request line + headers verbatim (per `Audio.cpp:495-507`), redirect
following (radio-browser entries and shoutcast/icecast hosts commonly redirect), ICY metadata
block parsing, connect-latency timing split into DNS-resolve / TCP-connect / (TLS handshake if
`https://`) phases so a slow phase is attributable, not just a slow total.

Not replicated (deliberate, Option C boundary): MP3/AAC decode, I2S output, `InBuff` ring-buffer
sizing/underrun semantics, the ESP32 TLS stack's specific cipher/negotiation behavior (a host
Python/OpenSSL TLS stack is not byte-identical to mbedTLS on the ESP32 — if a TLS-stack-specific
incompatibility is ever suspected, that needs a different tool, not this one).

### Correlation with DUT runs

Run the host probe **at the same time as, or immediately adjacent to,** a DUT attempt on the same
station set, and log wall-clock timestamps on both sides so the two can be lined up after the
fact. This doc does not mandate literal simultaneity (the DUT's own station-fetch flakiness may
not cooperate on a schedule) — same-session, best-effort correlation is sufficient; exact-timestamp
correlation is a nice-to-have, not a gate.

## Testing and Validation

**Tool self-check (must pass before trusting any "station X is down" result):** run the same
probe against a station or host known-good at test time (e.g. the NPO relay
`icecast.omroep.nl/radio1-bb-mp3` already used elsewhere this session as a reliable fallback) —
if the tool itself can't connect to a station that's independently known to work, the tool is
broken, not the network.

**Disposition matrix (how to read the results once gathered):**
- Host successfully connects to the same stations DUT reports as `ERROR_UNREACHABLE`, with
  connect latency comfortably under 250ms → the timeout-too-short hypothesis is weakened, look
  elsewhere (DUT-specific WiFi/TLS behavior).
- Host successfully connects, but latency clusters near or above 250ms (even occasionally) →
  strong support for the timeout hypothesis — bring to human as a candidate one-line fix
  (`setConnectionTimeout()` with a more realistic value), gated on a DUT-side confirmation that
  raising it actually reduces `ERROR_UNREACHABLE` incidence, not applied speculatively.
- Host also fails to connect (matching DUT's failure) → real station/CDN/network-path outage
  independent of the DUT — not a firmware bug, nothing to fix in this codebase, disposition is
  "wait and retry" same as any other external-service flakiness this project already tracks
  (TASK-284's radio-browser class).
- Host connects fine and stays healthy for the full SLAM! soak while a concurrent DUT run (once
  runnable — station-fetch dependent) shows a metadata stall → points at something DUT-specific in
  the metadata pipeline (TASK-390's original hypothesis 1/2), not the network.

**Exit criteria:** at least one of the four dispositions above reached with logged evidence
(connect-latency numbers or a title-tracking timeline), written back into TASK-390 (or a new
follow-up task if the finding warrants code changes) rather than left only in this doc.

**VE note (self-applied, since this doc folds in its own test plan):** the four-way disposition
matrix above only works if Phase 1's connect-latency numbers are captured with per-phase timing
(DNS/TCP/TLS split), not just a single pass/fail — a fast DNS + slow TCP looks identical to a slow
DNS + fast TCP in a single aggregate number, and those point at different fixes (DNS server choice
vs. router/ISP routing). Don't skip the phase split to save implementation time; it's the
difference between an actionable finding and another "something's slow" shrug.

## VE Review (2026-08-03)

Independent pass, not a rubber stamp — six real gaps found. None block starting implementation,
but Developer should resolve or explicitly accept each before the tool's output is trusted for a
disposition call, especially #1 and #2 (the doc's central hypothesis test is weaker than it needs
to be as currently specified).

1. **The core hypothesis test is indirect and should be direct.** As written, Phase 1 measures
   absolute host connect latency and eyeballs it against "near or above 250ms" — but a host
   Python/OS TCP stack's absolute timing isn't guaranteed comparable to the ESP32's, so a latency
   number close to 250ms is suggestive, not conclusive, and "clusters near" is not a falsifiable
   threshold (nobody has said what number that means in advance). **Stronger, cheap alternative:
   run each connect attempt twice — once with an artificially imposed 250ms client-side timeout
   (matching `m_timeout_ms` exactly), once with a generous one (e.g. 5s)** — same host, same
   network, same code path, only the timeout value differs. If the 250ms-capped attempt fails
   materially more often than the generous one to the *same* hosts, that's a controlled,
   same-machine, same-moment causal result — not an absolute-number comparison across two
   different TCP stacks. This should replace or supplement the current latency-vs-threshold
   framing as the primary test.
2. **Single attempt per station (breadth test) is too thin to trust.** One connect attempt can't
   distinguish "this station is reliably unreachable" from "one packet got lost." Require N≥3
   attempts per station (spaced a few seconds apart, matching `WR_SKIP_PACE_MS`'s own 2s pacing
   for rough fidelity) and report a per-station success rate, not a single pass/fail bit.
3. **DNS resolver mismatch is an unaddressed confound.** The design doesn't say what DNS server
   the host tool resolves through — if it's the host OS's default resolver (which may be a VPN,
   DoH, `1.1.1.1`, or a cached `systemd-resolved` entry) rather than whatever the router hands out
   via DHCP, the host isn't actually testing "the same network path" the DUT gets. Either
   explicitly resolve against the LAN router's DNS IP (matching DHCP-assigned behavior), or — if
   that's not practical — log which resolver was used and flag it as a known limitation in the
   report, don't silently assume equivalence.
4. **Re-querying radio-browser for station selection repeats the exact flaky call already under
   suspicion.** The design says "do this as its own one-shot query" but doesn't say to cache the
   result. Require: resolve the 5+1 station URLs *once*, persist them (a small committed or
   session-local file), and reuse across repeat tool invocations — don't let every re-run of this
   diagnostic tool re-hit the same rate-limit-sensitive endpoint TASK-284 already flags as
   sensitive to repeated hammering.
5. **No validation of the ICY-metadata parser itself before trusting a "title went quiet"
   finding.** The tool self-check (§Testing and Validation) only verifies connectivity, not that
   the metadata parser correctly detects title changes. A parser bug (off-by-one on
   `icy-metaint`, wrong block-length byte, etc.) would silently masquerade as "metadata stalled" —
   exactly the class of false-positive this investigation has already hit twice this session
   (TASK-385's over-confident isolated rerun; this session's own missing-`wrIdx` gap). Require a
   parser-correctness check against a station with independently-observable title changes (or a
   small synthetic ICY server) before the Phase 2 soak's title-tracking timeline is trusted as
   evidence.
6. **Correlation timing is left too loose given this session's own evidence.** "Same session,
   best-effort" undersells how fast conditions changed today — radio-browser worked, then failed
   3× within roughly the same hour. Tighten to: log wall-clock timestamps on both host and DUT
   sides, and report elapsed time between the two runs alongside any disposition — a 45-minute gap
   between "host tested fine" and "DUT failed" should visibly weaken confidence in that
   comparison, not be silently treated as equivalent to a simultaneous run.

**Minor:** Goals section has two items numbered "3." — cosmetic, but worth fixing before this doc
is treated as a build reference.

**Testability sign-off:** with #1 and #2 addressed, the exit criteria become genuinely falsifiable
(a specific percentage/count threshold, decided in advance, rather than a post-hoc "looks close").
Without them, a Developer could run this tool, get an ambiguous result, and talk themselves into
whichever disposition they expected going in — which is the one outcome this entire document
exists to prevent.

## Open questions

- Should Phase 2 (SLAM! soak) run with or without a concurrent Spotify-poll-equivalent load on the
  host side? The DUT's own soak deliberately leaves Spotify's poll running for fidelity; the host
  has no equivalent unless one is synthesized (e.g. a second process hammering api.spotify.com
  concurrently) — probably not worth building; flagged for whoever implements this to make an
  explicit call rather than silently omitting the variable.
- Exact host machine / network position: "same SSID as DUT" was specified; worth confirming
  whether that means the same physical host used for this session's `run/*` scripts (already on
  that network, per this session's tooling) or a different machine — assumed the former unless
  told otherwise.
