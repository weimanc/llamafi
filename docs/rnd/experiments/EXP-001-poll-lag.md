> Owner: R&D

### EXP-001 — 2026-05-18 — DUT Spotify poll-lag characterisation

**Hypothesis**: The 6–8.5 s lag observed in the sync-001 VE harness is not purely
a network artifact (AT&T cellular NAT). The DUT is now on LAN (same PC network). If
lag persists above the spec 5.5 s, it is a firmware or polling-strategy issue. If it
sits under 5.5 s, the prior run's bound relaxation to 8500 ms can be tightened back.

**Motivation**: The VE harness raised `LAG_BOUND_MS` from 5500 ms to 8500 ms and
attributed excess lag to AT&T cellular NAT closing stale TLS connections. The DUT is
now confirmed on the same LAN as the development PC. The harness bound should reflect
the real baseline, not the worst-case cellular environment.

---

## Experiment plan

### Step 1 — PC-side baseline (mock DUT)

Build a minimal Python mock that measures the round-trip latency of the Spotify Web
API `/me/player` endpoint, as the DUT would see it from this network:

```
t0 = time.monotonic()
GET https://api.spotify.com/v1/me/player (fresh access token, same creds as DUT)
t1 = time.monotonic()
round_trip_ms = (t1 - t0) * 1000
```

Run 10× at ~5 s intervals (matching DUT poll cadence). Record p50/p95/max.
This gives the irreducible network floor — TLS + HTTP RTT from this machine.

### Step 2 — DUT poll-completion timestamp

Use the serial heartbeat + `get snapshot` to measure how long the DUT actually
spends on each poll:

- Parse `[I][hb]` lines for `last_poll_age_ms` immediately after each successful poll.
- Subtract `last_poll_age_ms` from `next_poll_in_ms+last_poll_age_ms` to get total
  poll cycle. Compare against Step 1 PC baseline.
- Watch for TLS-reset lines (`[I][spotify.tls] hard reset`) — indicates stale
  connection even on LAN (possible if DUT's keep-alive window < 5 s).

### Step 3 — Harness lag re-measure on LAN

Re-run `run_sync_tests.py T097 T098 T099` on LAN with the DUT. Record actual elapsed
times. Compare against 5500 ms spec and 8500 ms cellular bound.

### Step 4 — Isolate: TLS reconnect cost on LAN

If DUT still shows TLS hard reset on LAN, measure the cost:
- Record time from `reconnect` command to `[spotify.poll] ok 200` arrival.
- Compare against Step 1 PC-side TLS-included RTT.
- If DUT TLS cost >> PC: firmware issue (cipher suite, mbedtls config, heap pressure).
- If DUT TLS cost ≈ PC + ~500 ms: normal ESP32 overhead, spec bound just needs to
  be 6 s not 5.5 s.

---

## Success criteria

| Outcome | Conclusion |
|---------|-----------|
| LAN lag ≤ 5500 ms for T097–T099 | Spec bound correct; 8500 ms was cellular only → tighten harness |
| LAN lag 5500–6500 ms, no TLS resets | ESP32 HTTP stack ~1 s slower than PC; update spec bound to 6500 ms |
| LAN lag 5500–6500 ms, TLS resets present | DUT re-connecting every poll even on LAN; investigate keep-alive / connection reuse |
| LAN lag > 6500 ms | Unexpected — escalate, check for heap pressure, mbedtls config |

---

## Tooling to build

`tools/poll_latency_mock.py` — minimal script:
- Loads `data/spotify_diy_config.json` for creds
- Refreshes access token once
- Calls `GET /me/player` in a loop (N times, 1 s interval)
- Prints per-call RTT + summary stats (p50/p95/max)
- No serial dependency — pure PC-side baseline

```
python3 tools/poll_latency_mock.py --count 20 --interval 5
```

**Branch**: `rnd/poll-lag`
**Status**: planned — awaiting human operator go-ahead to run experiments
