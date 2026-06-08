# Harness–DUT Synchronisation Contract

> Owner: Verification Engineer
> Established: ADR-042 (2026-06-08)
> Status: normative

This document is the authoritative specification for how the test harness synchronises
with DUT state. All harness tests must follow these rules. When in doubt, re-read this
document — do not invent new patterns.

---

## Core primitive: `_bgpoll_suspended(dut)`

```python
with _bgpoll_suspended(dut):
    # background Spotify polls are suspended here
    # pre-conditions and completion signals are the caller's responsibility
```

Use this context manager whenever a test triggers an async operation that could be
contaminated by a concurrent background Spotify poll. The `finally` block guarantees
resume even on test failure.

---

## Synchronisation table

| Scenario | Pre-condition (explicit at call site) | Trigger | Completion signal | bgPoll |
|---|---|---|---|---|
| Network fetch triggered by tap | `_wait_shell_not_busy(dut, 10.0)` | `tap` or `switchApp` | `_wait_chart_complete(dut, before)` counter advance | suspend |
| Transport / volume action (no fetch) | `_wait_shell_not_busy(dut, 10.0)` | `tap` | `_wait_shell_not_busy(dut)` clears | suspend |
| Cooldown / FSM state check (no async) | `dut.cmd("set cooldown <ms>")` | `tap` | JSON response field only | suspend (optional) |
| App switch without fetch | — | `switchApp` | `time.sleep(0.3)` only | optional |

---

## Sleep budget rule

`time.sleep(N)` with N > 0.5 is **prohibited** in test bodies, with two exceptions:

1. `BOOT_WAIT` — post-flash boot settle at harness entry (controlled by env var).
2. Documented firmware-side delays — must have an inline comment citing the specific
   firmware behaviour and its measured duration. Example:
   ```python
   time.sleep(0.3)  # repaintChrome ~60 ms + 240 ms headroom (ADR-042)
   ```

Any `time.sleep` without a comment in a test body is a bug to be removed.

---

## Mechanism ownership

| Mechanism | What it proves | When it is unreliable |
|---|---|---|
| `_wait_shell_not_busy(dut)` | No async operation is in flight | Background Spotify polls can briefly set then clear the flag between 1 s polls; warm-TLS fetches may complete before the first poll fires |
| `_wait_chart_complete(dut, before)` | An HTTP fetch completed and `fetchOkCount` advanced | Background polls can advance the counter between snapshot and triggering tap — always suspend bgPoll before snapshotting |
| `_bgpoll_suspended(dut)` | Background polls will not fire during the block | Nothing — the firmware suspends the self-poll cadence while the flag is 0 |
| `time.sleep(N)` | Elapsed wall time | Non-deterministic under load; never use as a completion signal |

**Rule**: `_wait_shell_not_busy` is a **pre-condition check only** (verify no prior work is in flight before issuing a new command). It is NOT a completion signal for a network fetch — use `_wait_chart_complete` for that.

---

## Harness entry guard

At harness startup, `_verify_debug_firmware()` must confirm:
1. `SERIAL_DEBUG` firmware is loaded (`get heap` succeeds).
2. Elf hash matches the local build artifact (ADR-042 E1 gate).
3. bgPoll is enabled: issue `get bgPoll`; if `enabled:0`, issue `set bgPoll 1` before
   any tests run (leaked suspend from a prior crash).

---

## New-mechanism protocol

When adding a new harness synchronisation mechanism (poll, counter, flag):

1. Write a two-sentence contract: "this mechanism proves X; it is unreliable when Y."
2. Add a row to the mechanism ownership table above.
3. Commit the contract update alongside the first test that uses it.

Failure to follow this protocol repeats the pattern documented in LL-059.
