# PROP-008 — [2026-07-30] — M-CEEFAX: accept, mitigate further, or defer the Spotify TLS-degradation trade-off

> Owner: R&D
> Origin: TASK-374 (M-CEEFAX DUT coexistence gate), ADR-057
> Branch: n/a — finding surfaced during production implementation on master (TASK-370..374), not a separate rnd/ branch

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
Something in the connect-attempt path — most plausibly lwIP's TCP socket
teardown on a failed/timed-out connect, since the mbedTLS-level cleanup was
independently verified correct by reading the code — is not releasing
everything it allocates. This is consistent with, and a much larger-scale
version of, EXP-006's own smaller original observation on the narrower
spike (`39968→37000` after one failure).

**Concrete next step for whoever picks this up**: instrument (or find
existing ESP-IDF tooling for) the lwIP socket/PCB layer specifically —
confirm whether a failed/timed-out `lwip_connect()` leaves a TCP PCB or
associated buffers alive after `lwip_close()`. If confirmed, the fix would
be scoped to `ssl_client.cpp`'s socket-teardown path (a local patch to the
vendored `WiFiClientSecure`, same precedent as `PATCH-003`'s stale-fd-close
fix already in that file) rather than anything in `CeefaxTeletextSource`
itself.

## Recommended next step

Hand to PM for a scheduling decision among Options A/B/C above. This is a
product trade-off (how much Spotify unreliability is acceptable while a
user is on Ceefax), not a pure engineering question with one right answer
— R&D's job here was to characterize the finding accurately, not to decide
it. See `docs/project/tasks.md` TASK-374 and
`docs/architecture/decisions/ADR-057.md` item 3 (needs a correcting
amendment regardless of which option is chosen, since its current text
claims degradation is eliminated).
