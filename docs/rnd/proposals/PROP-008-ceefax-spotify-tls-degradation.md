# PROP-008 — [2026-07-30] — M-CEEFAX: accept, mitigate further, or defer the Spotify TLS-degradation trade-off

> Owner: R&D
> Origin: TASK-374 (M-CEEFAX DUT coexistence gate), ADR-057
> Branch: n/a — finding surfaced during production implementation on master (TASK-370..374), not a separate rnd/ branch
>
> **STATUS: REOPENED 2026-07-31 — acceptance withdrawn.** A functional DUT test
> (EXP-019 "Functional verification") showed Ceefax **does not connect on the
> device** (relay verified working from host) and **crashes it in ~18 s** under
> contention. The whole coexistence question below is moot until it connects —
> blocking bug is TASK-376 (P1). The no-leak finding still stands. The banner
> below reflects the (now-reversed) earlier close-out; read it as history.
>
> ~~**STATUS: CLOSED — Option A accepted 2026-07-31.**~~ Full A/B/C explored: (a) no
> upstream WebSockets fix exists; (b) EXP-019 out-of-band measurement proved
> **there is no leak** (the "permanent ~42.6 KB" was a metastable artifact —
> memory recovers on leaving Ceefax); (c) mechanism understood (transient DMA
> contention → self-recovering Spotify `SSL -32512`, bounded to the active-Ceefax
> window). Accepted as a documented limitation per ADR-057 "Acceptance decision
> 2026-07-31"; residual intermittent low-DMA crash carried openly with
> gate-tuning as the sanctioned future mitigation. TASK-375 closed moot; M-CEEFAX
> DONE. The body below is the (heavily self-correcting) investigation trail —
> read the EXP-019 "lead (b)" section and this banner as the settled truth.

## Summary

TASK-374's coexistence gate (M-CEEFAX close-out) found that Ceefax's
DMA-gated reconnect attempts still measurably degrade Spotify's independent
poller, even after two rounds of fixes. This is not a hypothetical — it is
a repeated, DUT-confirmed finding on the shipped implementation
(`teletextApp.h`, commit `ad94f60`), and it directly contradicts ADR-057
item 3's claim that the DMA gate "eliminates the crash and the cross-app
TLS degradation." The crash half of that claim now holds (see below); the
degradation half does not. PM/Architect needs to pick a path before M-CEEFAX
is considered fully closed.

## Prototype evidence

Baseline (`run/stress 8`, Ceefax off, 2026-07-30 network conditions): 6 hard
failures / 0 TLS-error lines over 8 min — matches EXP-006's own baseline
(6/1) closely enough to trust as "normal."

Two coexistence soaks, Ceefax parked in the foreground the whole time
(pump task actively attempting reconnects throughout):

| Soak | Duration | Crash | Spotify poll success | TLS-error lines |
|------|----------|-------|----------------------|------------------|
| 1 (pre tlsYield fix) | 8 min | **1 crash** (Guru Meditation, `start_ssl_client`/`strlen`, LoadProhibited) | 0/8 | 7 (`SSL -32512`) |
| 2 (post tlsYield fix, post attempt-cap) | 10 min | 0 crashes | 0/10 | 10 (`SSL -32512`) |

Fixes applied between soak 1 and soak 2, in order:
1. DMA gate widened from free-bytes-only to free-bytes **and**
   `heap_caps_get_largest_free_block()` (fragmentation-aware, matching
   webRadioApp.h/EXP-010's precedent) — soak 1's crash occurred at
   freeDma=66288 (well above the ported byte threshold), i.e. plenty of
   free bytes but not contiguous. This alone still let a crash recur once
   more at lfbDma=27636 (*higher* than a prior clean 5-min run at 21492),
   so it is a mitigant, not a proof.
2. Hard cap of `kMaxConsecutiveAttempts = 5` reconnect attempts per
   activation — bounds crash exposure to a fixed number of attempts per
   session rather than retrying forever. Crash-free across both the 5-min
   re-verify and the 10-min soak in the table above.
3. Ceefax's reconnect attempts wrapped in the project's existing
   `tlsYield()`/`tlsResume()` protocol (the same one every `dataTask` HTTPS
   fetch already uses — architecture.md "TLS coexistence"), throttled to
   one real attempt per `kRetryIntervalMs` (15s) rather than wrapping every
   20ms pump tick (which would yield Spotify continuously for as long as
   the gate stays open, a worse regression in a different direction).

**Result: (1)+(2) closed the crash.** Soak 2, 10 minutes, zero crashes,
matching the "must not crash" bar. **(3) reduced but did not eliminate**
the SSL -32512 failures — soak 2 still shows 0/10 Spotify poll success,
essentially unchanged from soak 1's 0/8. The failure mode is consistently
`SSL - Memory allocation failed` at the TLS layer — Spotify's client never
even completes a handshake, as opposed to the pre-existing, already-known,
out-of-scope TASK-243 403 (which is a normal HTTPS response, just an auth
rejection — TLS itself works fine there).

## Suggested scope (three options, not a recommendation — PM/Architect call)

**Option A — Accept as documented limitation.** Ship as-is: Ceefax never
crashes the device, never affects NOS or any other app, and the degradation
is bounded strictly to the window a user is actively on the Ceefax source
with Spotify's own connection failing to establish during that time. Add
this explicitly to ADR-057's consequences section (the current text's claim
that degradation is eliminated needs correcting either way). Lowest effort;
matches the milestone's existing "accept best-effort connectivity" posture
for connection *reliability* — this would extend that same posture to
Spotify's coexistence, not introduce a new kind of trade-off.

**Option B — Further mitigate without a framework rebuild.** Untried this
session, each independently testable:
- Lower `kMaxConsecutiveAttempts` further (currently 5) or lengthen
  `kRetryIntervalMs` (currently 15s) — fewer/rarer attempts means fewer
  windows where Spotify's own poll can race one, at the cost of Ceefax
  connecting even less reliably (already accepted as background risk).
- Investigate whether `spotifyTask`'s own poll cadence could be told to
  skip/delay a cycle while `tlsYield()` is held, rather than attempting a
  handshake it can't currently win — right now `tlsYield()` stops Spotify's
  *current* client but doesn't stop `spotifyTask` from immediately trying to
  reconnect until it also observes the yield is released; whether this is
  the actual proximate cause of the -32512 failures (vs. a residual DMA
  hangover from the reconnect attempt itself) wasn't isolated this session.
- Raise the DMA thresholds substantially higher than the current
  38000/20000 — untested whether a much higher bar (e.g. requiring near-idle
  freeDma) reduces the actual race window enough to matter, at the cost of
  Ceefax essentially never getting to attempt at all on this board.
- **Or the opposite — lower `kMinFreeDmaForConnect`.** See the follow-up
  isolation below: this build's idle baseline (~36-37K) sits at or below
  the ported 38000 threshold most of the time regardless of Spotify, so the
  gate mostly never opens at all today. `lfbDma` stayed healthy (30708) in
  that same window, so it may be specifically the free-byte number, not
  fragmentation, that's over-conservative for this build. Lowering it would
  let more attempts through (more chances to actually connect, but also
  more exposure to whatever causes the -32512 degradation) — needs a fresh
  multi-minute soak before trusting, not a quick check.

**Option C — Send back to R&D for a deeper isolation pass.** The mbedTLS/
WiFiClientSecure internal-state theory (from finding #2 above — same crash
site recurring at a *higher* largest-free-block reading) was never
confirmed, only inferred from the pattern not fitting a pure memory-size
story. A short, timeboxed R&D spike specifically isolating whether repeated
`connect()` calls on the *same* `WebSocketsClient`/`WiFiClientSecure` object
accumulate state (vs. a fresh object each attempt) would either explain
finding #2 or rule it out — which also bears on how confident Option A/B's
numbers should be trusted going forward.

## Follow-up isolation (2026-07-30, same session, human-requested)

Ran the same live-diagnostic check (`get ceefaxStatus` polled every ~8s over
60s, Ceefax parked in foreground) on `cyd2usb_winamp_debug_noSpotify`
(`-DDISABLE_SPOTIFY`, skips `spotifyTask::begin()` entirely — Spotify not
merely idle, not running at all) — the same isolation EXP-006 ran for the
original spike, re-verified against the real production build.

**Result: the DMA gate never opened once in 60s** — `freeDma=36784` at
switch-in, gate log line printed once ("CLOSED (low DMA)") and never again
for the rest of the window; `ceefaxStatus.connected` stayed `false` the
whole time, `hasError` latched at ~34s — visually and numerically
indistinguishable from the with-Spotify runs above.

**This changes the read on the finding.** With Spotify entirely removed,
the connection still never got a chance to attempt at all, because this
build's baseline idle free-DMA (~36-37K) sits at or below
`kMinFreeDmaForConnect` (38000) most of the time — not because Spotify is
competing for it. In the with-Spotify soaks, the gate *did* occasionally
open (freeDma spiking to 63-66K); the working theory now is that this
was Spotify's own connection cycling transiently freeing memory, giving
Ceefax its only windows to attempt anything — take Spotify away and that
periodic freeing event disappears too, so the gate just stays shut.
`lfbDma=30708` in this run — comfortably above the 20000 contiguous-block
floor — so it's specifically the raw free-byte threshold, not
fragmentation, blocking attempts here.

This resolves the "isolate whether Spotify contention causes the *failure
to attempt*" unknown below with a clear answer (no), and turns Option B's
"raise the DMA thresholds" lever into a more specific, concrete one:
**`kMinFreeDmaForConnect` (38000) was tuned against `ceefaxWsSpike.h`'s
narrower harness (~40-45K idle free-DMA); this build's real idle headroom
is lower (~36-37K)** — the threshold may simply need lowering (with the
contiguous-block check retained) to let more attempts through on this
board, rather than raising it. Not yet tried — the risk is exactly the
crash class TASK-370 already fought (a lower byte threshold with an
already-healthy contiguous block might be fine, but should be re-soaked
before trusting it, per [[persistent-conn-dma-gate-pattern]]).

## Risks / unknowns

- Today's network conditions (WiFi RSSI, upstream relay behavior) were not
  independently varied — both TLS-degradation soaks ran back-to-back on the
  same evening. Per this project's own WiFi-flakiness history
  (`project_wifi_flapping_ap_side` memory), day-to-day network variance is
  real; the 0/8 → 0/10 consistency is suggestive but not a multi-day-confirmed
  number the way EXP-006's own 4×/11× baseline comparison was.
- Whether the -32512 failures are caused by DMA contention *during* the
  handshake attempt itself, or by a lingering effect from a *previous*
  attempt (per finding #2's residual-headroom theory), still wasn't directly
  isolated — the no-Spotify run above answers "is Spotify the *cause* of the
  gate never opening" (no), but not "what exactly makes an attempt that does
  fire degrade Spotify's own poll" — this still matters for judging Option
  B's tlsYield-based levers.
- The no-Spotify run's 60s window never saw the gate open at all, so it
  couldn't test whether an actual connect *attempt* still crashes or
  degrades anything in the no-Spotify configuration — only that attempts
  are rarer there. A longer no-Spotify soak (waiting for a natural DMA dip
  to force one open, or temporarily lowering the threshold) would close
  this gap.

## Second follow-up: lowered-threshold soak reveals the more important lead

Tried the "lower `kMinFreeDmaForConnect`" lever from above: 38000 → 30000
(kept `kMinLargestFreeBlockForConnect`/`kMaxConsecutiveAttempts` unchanged),
10-min soak with Ceefax parked, Spotify running.

**Result: crash-free (10 min), but Spotify degradation unchanged** — still
0/9→0/11 poll success, 10 `SSL -32512` lines, indistinguishable from every
prior soak. The threshold change itself turned out to barely matter here,
for a specific, more interesting reason: **the gate opened exactly once**
(`freeDma=66160` — an early post-boot spike, above even the *old* 38000
threshold, so lowering it didn't cause this particular open), one attempt
fired, and DMA then dropped to `freeDma=19532` — **below even the new,
lower 30000 threshold** — and the gate log shows **zero further OPEN
transitions for the remaining ~9.5 minutes**. One attempt appears to
permanently cost **~46KB** of DMA-capable headroom that never recovers for
the rest of the session.

**This reframes the whole threshold-tuning question as secondary.** Whatever
threshold is picked, one real attempt seems to consume enough DMA that the
gate very plausibly never opens again afterward regardless — matching (at
much larger magnitude) EXP-006's own smaller observation for the original
spike ("39968→37000 bytes after one failure"). The live, more valuable
question this raises: **is `WiFiClientSecure`/mbedTLS failing to fully
release its allocation after a failed `connect()`** (a real, if
upstream/library-side, leak) **or legitimately holding a large cache/buffer
after failure that a proper `stop()`/cleanup call should release but isn't
being made**? If it's the latter, there may be a missed API call
(`WiFiClientSecure::stop()` or similar) somewhere in `CeefaxTeletextSource`'s
attempt path that would recover the memory — that's a concrete, scoped,
worth-trying next step, more promising than further threshold tuning.
Not confirmed this session — flagging as the lead for whoever picks this up
next, whether that's Option B (try adding an explicit `stop()`/cleanup after
each failed attempt, re-soak) or Option C (R&D isolation, now with a
sharper hypothesis to test).

## Third follow-up: instrumented soak confirms a real per-attempt leak

Added temporary diagnostics (removed after this test, not shipped): logged
`heap_caps_get_info(MALLOC_CAP_DMA)` immediately before/after each reconnect
attempt (`free_bytes`, `free_blocks`, `largest_free_block`), and exposed the
same fields on `get ceefaxStatus` for continuous polling. 5-minute soak,
polled every 3s.

**Code-level check first (ruled out one theory):** read
`WiFiClientSecure`'s destructor and `stop_ssl_socket()` — both look
structurally correct. `WebSocketsClient::loop()` `delete`s and `new`s a
fresh `WiFiClientSecure` object on every reconnect attempt (not reusing
one); the destructor calls `stop()`, which unconditionally frees
`entropy_ctx`/`drbg_ctx`/`ssl_ctx`/`ssl_conf` and conditionally frees the
CA cert. No missing free() call found by reading the code. **But the
instrumented soak shows a real leak anyway** — the cleanup that looks
correct on paper isn't accounting for everything that actually got
allocated during a failed attempt (most likely something at the lwIP
TCP-socket layer, underneath the mbedTLS-level cleanup that was checked).

**The data**: attempt #2's before/after snapshot —
`before(free=66180, blocks=12, largest=45044)` →
`after(free=18808, blocks=16, largest=10228)` — one attempt cost **~47KB**,
added **4 heap blocks that were never freed**, and dropped the largest
contiguous block by more than 4×. For the remaining **~4.5 minutes** of the
soak, `largest_free_block` sat at **exactly 10228 bytes, unchanged, every
single poll** — a static number that never moved is a strong leak signal
(ordinary WiFi/lwIP/other-task churn would show at least *some* fluctuation
as those subsystems do their own normal alloc/free cycles). `free_blocks`
also never dropped back below its post-attempt level for the rest of the
soak.

**This confirms it's a genuine leak, not fragmentation from other tasks
occupying freed space** (the theory floated in the second follow-up above).
This is consistent with, and a much larger-scale version of, EXP-006's own
smaller original observation on the narrower spike (`39968→37000` after one
failure).

## Fourth follow-up: `heap_caps_dump` narrows it to a specific, patchable candidate

Added a full `heap_caps_dump(MALLOC_CAP_DMA)` right after a leaking attempt
(temporary, kept in place alongside the other diagnostics). Sorted every
block across all DMA heap regions by size; the top of the list:

```
20492 bytes  0x3ffb0318  Free: No
16732 bytes  0x3ffeb1b4  Free: No
16732 bytes  0x3ffe7054  Free: No
```

**Two identical 16732-byte blocks is a strong, specific match** for a single
`mbedtls_ssl_context`'s `in_buf`/`out_buf` I/O buffers
(`CONFIG_MBEDTLS_SSL_MAX_CONTENT_LEN=16384` + mbedTLS's per-buffer record
overhead ≈ 16732) — this earlier follow-up's "lwIP socket layer" guess is
superseded by this more specific evidence; it looks like an mbedTLS session
object after all, just not the code path this proposal's earlier code
reading covered.

**Why the earlier code reading (WiFiClientSecure's destructor/`stop_ssl_socket()`
— both structurally correct) didn't catch this**: those are called on the
`connect()`-failure path. But this build never once logs a
`WStype_CONNECTED` *or* a `WStype_DISCONNECTED` event across every soak run
this session — the raw TLS handshake may be *succeeding* (a real session,
with real buffers, gets established), with the failure happening one layer
up, in the WebSocket protocol's own HTTP-Upgrade exchange on top of that
already-open TLS session. Read `WebSocketsClient::clientDisconnect()`
(the library's own teardown-on-failure path, called from e.g. a header-
response-timeout) and found a real asymmetry there:

```cpp
if (client->isSSL && client->ssl) {
    if (client->ssl->connected()) {   // only stop() if this reads true
        client->ssl->flush();
        client->ssl->stop();
    }
    delete client->ssl;               // deleted either way
    ...
}
```

`WiFiClientSecure::connected()` performs a `read(&dummy, 0)` and returns a
cached `_connected` flag — plausible for this to read `false` at exactly
the moment a peer has already reset/closed its side (a very ordinary
outcome for "we opened a connection and nothing sensible ever came back"),
skipping the explicit `stop()` call here. `~WiFiClientSecure()`'s own
destructor (invoked by the `delete client->ssl` right after) *does*
unconditionally call `stop()` again as a safety net — reading that
destructor path alone, cleanup still looks like it should happen. Did not
get further than this via static reading: confirming whether the
destructor's safety net is actually skipped, or bypassed, or whether the
object simply never reaches a `delete` at all in this specific failure
branch, needs live stepping with a debugger attached — a bigger jump in
tooling than fits this session.

**Concrete next step for whoever picks this up**: attach a debugger (or add
further targeted logging inside the vendored `WebSocketsClient.cpp`/
`WiFiClientSecure.cpp`) around `clientDisconnect()`'s SSL branch and
`WiFiClientSecure::connected()`'s `read()` call, specifically for the
"header response timeout" / "no WStype event ever fires" case this
project's real relay traffic reproduces reliably. If confirmed, the fix is
a small local patch to the vendored `WebSocketsClient` and/or
`WiFiClientSecure` (this project already has precedent for exactly this —
`PATCH-003`'s stale-fd-close fix lives in the same `ssl_client.cpp`), not
anything in `CeefaxTeletextSource` itself.

## Review (2026-07-30) — one material gap before the A/B/C decision

An independent review of this proposal against the code, commits, and
ADR-057 confirmed the evidence trail holds up (constants match
`teletextApp.h`, the commit trail `a6b057d`/`08601c7`/`82022fa` maps to the
follow-ups, and ADR-057's "eliminates the degradation" claim is genuinely
contradicted — now amended). It also surfaced one material gap and two minor
inaccuracies:

**Material gap — Option A's core premise is untested and probably false.**
Option A accepts the degradation as "bounded strictly to the window a user is
actively on the Ceefax source." But this proposal's own fourth-follow-up
theory (orphaned mbedTLS `in_buf`/`out_buf` buffers, leaked when
`WebSocketsClient` deletes an inner `WiFiClientSecure` without freeing them)
predicts the **opposite**: buffers already orphaned from prior deleted clients
cannot be reclaimed when the *current* `_ws` is deleted on
`onSuspend()`/`_teardownPumpTask()` (`teletextApp.h:630-632`). And each
activation resets `_consecutiveAttempts = 0` (`:625`), granting a fresh budget
of up to 5 leaking attempts **per visit**. If the leak is orphaned, the
degradation is not window-bounded — it is a session-lifetime, device-wide
regression, and Option A as written is not a legitimate option. This is the
single fact that most changes the decision, and it was stated as a bound
without being measured. The DMA-recovery test below settles it — confirming
the leak persists across teardown (Option A's premise is false), while
correcting this concern's initial fear that it compounds per-visit: the DMA
gate self-limits further attempts, so the true cost is a one-time ~42.6 KB
per-session loss, not an unbounded accumulation.

**Minor — diagnostics doc inaccuracy.** The third follow-up says the
diagnostics were "removed after this test, not shipped." They are still
present in `teletextApp.h` (the `get ceefaxStatus` DMA fields at `:270-284`,
unconditional; the per-attempt before/after `DIAG` log at `:686-713`, behind
`SERIAL_DEBUG`), committed in `08601c7`/`82022fa`. "Not shipped" is true
(debug-only for the `DIAG` line; the status fields ship but are read-only);
"removed" is not — and the fourth follow-up explicitly *keeps* the dump, so
the two sections contradict each other on whether instrumentation remains.

**Minor — baseline is not strictly apples-to-apples.** The baseline is given
as "6 hard failures / 0 TLS lines" with no poll-success count; the coexistence
rows are "0/N poll success / 7–10 TLS lines." The clean signal (0 → 7–10
TLS-error lines) carries the argument, but the table implies a symmetry the
underlying metrics don't have.

## DMA-recovery test (2026-07-30) — does the leak survive leaving Ceefax?

Ran on `cyd2usb_winamp_debug`, ttyUSB1. Driver drives `switchApp` over serial
and reads global DMA heap via `get heap` (`freeDma`/`lfbDma`, app-independent —
unlike `get ceefaxStatus`, which only answers while Teletext is foreground).
Baseline on Spotify (before any Ceefax visit), then 3 visits of `switchApp 8`
(Teletext, park 60s) → `switchApp 0` (Spotify, `onSuspend()` →
`_teardownPumpTask()` → `delete _ws`) → read free-DMA on Spotify after teardown.

| Point | freeDma | lfbDma |
|-------|---------|--------|
| **Baseline** (Spotify, pre-Ceefax) | **76684** | **40948** |
| Visit 1 — entered Teletext, pre-attempt | 66412 | 40948 |
| Visit 1 — after 1st reconnect attempt | 20780 → 24968 | 16372 |
| **Recovery after visit 1** (Spotify, pump torn down) | **34052** | **24564** |
| Recovery after visit 2 | 34052 | 24564 |
| Recovery after visit 3 | 34052 | 24564 |

**Answer: the leak is NOT reclaimed on teardown — the "window-bounded" premise
is false, definitively.** After the very first Ceefax visit, free-DMA
never returns to its 76684 baseline. It plateaus at **34052 for the rest of
the session** — a permanent **~42.6 KB** DMA-capable-heap loss that survives
full pump-task teardown and persists while the user is back on Spotify (or any
other app). Deleting `_ws` on `onSuspend()` does not free the leaked buffers,
exactly as the orphaned-mbedTLS-buffer theory predicted.

**Sharpest single confirmation**: `lfbDma` drops from 40948 to a permanent
24564 — a loss of **exactly 16384 bytes** = `CONFIG_MBEDTLS_SSL_MAX_CONTENT_LEN`,
one mbedTLS content buffer, gone from the largest contiguous block and never
returned. This is the same buffer the fourth follow-up's `heap_caps_dump`
fingerprinted, now confirmed as permanently orphaned rather than transiently held.

**One correction to this review's own earlier wording**: it does **not**
compound unboundedly per visit. The plateau at 34052 across all three visits
shows the cost is bounded at roughly *one* attempt's worth. The reason is
self-limiting: once free-DMA is depressed, entering Teletext (its own ~10 KB
app footprint) pushes free-DMA below `kMinFreeDmaForConnect`, so the gate
never reopens and no further attempts fire (visits 2–3 leaked little/nothing
more). So the accurate characterization is: **a one-time ~42.6 KB device-wide
DMA loss triggered by the first Ceefax visit that fires an attempt, lasting
until reboot** — not transient/window-bounded (as Option A claims), but also
not an unbounded per-visit accumulation (as this review first feared).

**Bearing on the options:**
- **Option A** must be re-described honestly: not "degradation bounded to the
  active-Ceefax window," but "the first Ceefax visit permanently costs the
  device ~42.6 KB DMA / one mbedTLS content buffer of contiguous headroom for
  the rest of the session, measurably degrading Spotify TLS even after the
  user leaves Ceefax, until the next reboot." That is a materially different
  product claim than the current Option A text; whether it is acceptable is
  still PM's call, but it should be made against the true cost.
- **Option B/C** are strengthened: because the cost is a permanent per-session
  loss (not a transient one that clears when the user navigates away), the
  explicit-`stop()`/cleanup fix (Option B's last bullet / Option C's vendored-
  `WebSocketsClient` patch) now recovers ~42.6 KB that otherwise stays gone
  for the whole session — a concrete, measurable win, not a marginal one.

Raw log + per-poll series: scratch `dma_recovery.py` / `.json` (not committed).

### Correction (EXP-019, 2026-07-30) — the "permanent deterministic leak" model does not hold

An Option-C isolation pass (instrumenting the **vendored**
`app/lib/WiFiClientSecure/src/ssl_client.cpp` — *not* the framework copy;
this project compiles its own, where `PATCH-001/003` live) walked back the
confident wording above. Directly observed on-device:
- **`stop_ssl_socket()` (which frees the mbedTLS I/O buffers) IS called
  constantly** — cleanup is not skipped. The "cleanup never runs" mechanism
  (this proposal's synthesis of upstream `#864`) is not what the instrumented
  run shows.
- **TLS handshakes SUCCEED then get torn down repeatedly** — the failure is
  post-TLS (WebSocket-upgrade layer), and `freeDma` **oscillates** (66240 →
  6152 → 74856 → …), hitting **6152** once (that transient low is the real
  crash risk, not a permanent loss). End state was **variable** (one visit
  ended depressed, the next recovered).
- The earlier uninstrumented "stuck at 34052 forever" was one **metastable**
  regime (gate latches closed after a heap dip, so no further churn fires the
  recovering cleanup), **not** a hard unfreed allocation.

**Two confounds** (blocking-`ets_printf` observer effect + genuine
network/handshake-success variance between sessions) mean this is
**inconclusive**, not a clean opposite verdict. Net: treat the ~42.6 KB figure
as *one observed metastable session outcome*, not a fixed per-visit cost, and
treat the `#864` root cause as a **candidate hypothesis, not settled**. The
robust facts are narrower: per-attempt transient DMA allocation, dangerous
`freeDma` dips under churn (gate-bounded), and variable network-dependent end
state. Full detail + next steps: `docs/rnd/reports/EXP-019-ceefax-tls-leak-isolation.md`.

**FINAL RESOLUTION (EXP-019 lead b, 2026-07-31): no leak.** The out-of-band
measurement (inline `setup`/`stop` counters, no hot-path prints) settled it:
`setup − stop` stays **≤ 0** (every SSL context freed) and `freeDma` at rest
**recovers to ≥ baseline** across visits. The ~42.6 KB "permanent leak" is
**retired** as a metastable artifact — memory recovers on leaving Ceefax, so the
degradation **is** bounded to the active-Ceefax window (Option A's framing was
right). The real mechanism is transient DMA contention (Ceefax churn → Spotify
`SSL -32512`, self-recovering), with an intermittent low-DMA crash as the only
non-cosmetic residual. This retires the `#864` "cleanup-skipped" theory too
(`stop` demonstrably runs). See EXP-019 lead(b) for data.

## Fifth follow-up: this is a known, documented upstream bug class, not a novel finding

User asked directly: is mbedTLS open source, and can we check whether this
is an existing/known issue? Yes to both — and it is. Three layers are in
play here, all open source, all checkable:

- **mbedTLS itself** (Apache-2.0/GPL-2.0 dual-licensed, maintained by the
  Trusted Firmware project) — the actual TLS engine. Not directly
  implicated by this search; its own `mbedtls_ssl_free()` is called
  unconditionally by `stop_ssl_socket()` in our vendored copy (already
  read, looked correct).
- **`WiFiClientSecure`** (`espressif/arduino-esp32`, part of the Arduino
  core, wraps mbedTLS) — **has a well-documented history of exactly this
  bug class**:
  [Issue #5781](https://github.com/espressif/arduino-esp32/issues/5781) /
  [#3808](https://github.com/espressif/arduino-esp32/issues/3808) /
  [#5480](https://github.com/espressif/arduino-esp32/issues/5480) all
  describe `start_ssl_client()` failing (handshake/verification error)
  without freeing CA-cert/client-cert/key structures.
  [PR #5945](https://github.com/espressif/arduino-esp32/pull/5945) fixed
  this (merged 2021-12-14) by adding the conditional frees inside
  `stop_ssl_socket()` — **this is the exact code we already read and
  confirmed present** in our vendored copy (the "avoid memory leak if ssl
  connection attempt failed" comment). Confirmed: **our pinned Arduino-ESP32
  2.0.17 (`platform = espressif32@6.9.0`) already includes this fix** — the
  PR's regression ([Issue #6077](https://github.com/espressif/arduino-esp32/issues/6077),
  handshake_timeout zeroed) was itself reported fixed by 2.0.3, well before
  our 2.0.17. **So the specific historical CA/cert-leak bug is already
  patched here — that's not what we're hitting.**
- **`WebSocketsClient`** (`Links2004/arduinoWebSockets`, the WebSocket
  protocol layer on top of `WiFiClientSecure`) — **has a separate,
  long-standing, still-open class of issues where `WStype_DISCONNECTED`
  never fires** in certain failure scenarios:
  [#297](https://github.com/Links2004/arduinoWebSockets/issues/297),
  [#373](https://github.com/Links2004/arduinoWebSockets/issues/373),
  [#84](https://github.com/Links2004/arduinoWebSockets/issues/84),
  [#864](https://github.com/Links2004/arduinoWebSockets/issues/864) (open),
  [#706](https://github.com/Links2004/arduinoWebSockets/issues/706) (open),
  [#290](https://github.com/Links2004/arduinoWebSockets/issues/290),
  [#271](https://github.com/Links2004/arduinoWebSockets/issues/271).
  **Issue #864 in particular describes almost exactly our scenario**: the
  remote side becomes unreachable/unresponsive mid-session, and the
  client-side library never reaches `WStype_DISCONNECTED` — the reporter's
  own workaround is an application-level ping/staleness timer, which is
  structurally the same shape as this project's own `hasError()`
  sustained-failure latch (TASK-372).

**Conclusion: this is not a bug we introduced or need to root-cause from
scratch.** It's a known, still-open gap in `Links2004/arduinoWebSockets`'s
disconnect detection, on a still-current version (2.7.3, our pinned
version). Because that detection gap is what's supposed to trigger
`clientDisconnect()` → `stop()` → the mbedTLS buffer free, a connection
that the library never recognizes as "disconnected" plausibly never gets
its ~16732 B I/O buffers freed either — consistent with everything
observed in the fourth follow-up above. No open upstream issue was found
that connects the disconnect-detection gap to this specific memory-leak
consequence explicitly; that connection is this project's own synthesis,
not something confirmed by an upstream maintainer.

**This changes Option C's shape**: rather than an from-scratch R&D
isolation spike, the scoped next step is to check whether upstream has
since fixed disconnect-detection for this scenario in a version newer
than 2.7.3 (not checked this session), and/or to file a new upstream issue
connecting "WStype_DISCONNECTED never fires on X" to "the underlying
WiFiClientSecure object's mbedTLS buffers are never freed as a
consequence" — since that specific causal link doesn't appear to be
documented anywhere upstream yet.

## Recommended next step

Hand to PM for a scheduling decision among Options A/B/C above. This is a
product trade-off (how much Spotify unreliability is acceptable while a
user is on Ceefax), not a pure engineering question with one right answer
— R&D's job here was to characterize the finding accurately, not to decide
it. See `docs/project/tasks.md` TASK-374 and
`docs/architecture/decisions/ADR-057.md` item 3 (needs a correcting
amendment regardless of which option is chosen, since its current text
claims degradation is eliminated).

## PM disposition (2026-07-30)

Actioned. The DMA-recovery finding shifted the balance: this is no longer a
windowed cosmetic trade-off but a quantified ~42.6 KB/session leak with a
specific patchable candidate site. PM decision:
- **Option B scheduled as TASK-375** — the targeted `stop()`/cleanup patch on
  the vendored WebSocket/`WiFiClientSecure` failure branch (`PATCH-003`
  precedent). Cheapest highest-information action; if it lands the trade-off
  dissolves. This session's `dma_recovery.py` becomes the regression gate.
- **Option C** = fallback only if TASK-375 needs debugger-depth isolation.
- **Option A** (accept the permanent cost) = **escalated to human**, not taken
  unilaterally — the 2026-07-29 "accept best-effort connectivity" lock covered
  reliability, not this newly-quantified device-wide DMA cost.

Full disposition + TASK-375 scope: `docs/project/tasks.md` (TASK-374 →
TASK-375). Roadmap M-CEEFAX status moved to **blocked** pending TASK-375.
