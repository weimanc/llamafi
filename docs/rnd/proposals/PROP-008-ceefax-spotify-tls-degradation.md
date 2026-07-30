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

**Option C — Send back to R&D for a deeper isolation pass.** The mbedTLS/
WiFiClientSecure internal-state theory (from finding #2 above — same crash
site recurring at a *higher* largest-free-block reading) was never
confirmed, only inferred from the pattern not fitting a pure memory-size
story. A short, timeboxed R&D spike specifically isolating whether repeated
`connect()` calls on the *same* `WebSocketsClient`/`WiFiClientSecure` object
accumulate state (vs. a fresh object each attempt) would either explain
finding #2 or rule it out — which also bears on how confident Option A/B's
numbers should be trusted going forward.

## Risks / unknowns

- Today's network conditions (WiFi RSSI, upstream relay behavior) were not
  independently varied — both soaks ran back-to-back on the same evening.
  Per this project's own WiFi-flakiness history (`project_wifi_flapping_ap_side`
  memory), day-to-day network variance is real; the 0/8 → 0/10 consistency
  is suggestive but not a multi-day-confirmed number the way EXP-006's own
  4×/11× baseline comparison was.
- Whether the -32512 failures are caused by DMA contention *during* the
  handshake attempt itself, or by a lingering effect from a *previous*
  attempt (per finding #2's residual-headroom theory), wasn't isolated —
  this matters for which of Option B's levers would actually help.
- No isolation test was run with Ceefax's pump task active but the gate
  permanently CLOSED (i.e., attempting nothing) — that would cleanly
  separate "does merely running the pump task at all (even doing nothing)
  cost anything" from "does an actual attempt cost something," and wasn't
  done due to session time constraints.

## Recommended next step

Hand to PM for a scheduling decision among Options A/B/C above. This is a
product trade-off (how much Spotify unreliability is acceptable while a
user is on Ceefax), not a pure engineering question with one right answer
— R&D's job here was to characterize the finding accurately, not to decide
it. See `docs/project/tasks.md` TASK-374 and
`docs/architecture/decisions/ADR-057.md` item 3 (needs a correcting
amendment regardless of which option is chosen, since its current text
claims degradation is eliminated).
