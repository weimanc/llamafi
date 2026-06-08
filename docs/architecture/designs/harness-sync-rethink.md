# Design — Harness–DUT Synchronisation Rethink

> Owner: Architect
> Status: accepted
> Date: 2026-06-08
> Feeds: ADR-042 (decision to crystallise from this)
> Tracked-as: (pending PM task allocation)

---

## Context / pain points

The timeout audit (2026-06-08) produced a clear diagnosis: 8 of 10 recent fix commits
touch T-BUSY-*, T-CDWN-*, T169, or T_WX/CX — all network-dependent tests. Root causes
fall into three categories:

### P1 — UART line garbling (Core 0 / Core 1 race)

The ESP32 runs the HTTPClient on Core 0 and the serial command handler on Core 1.
Arduino's `Serial` object has an internal driver-level FIFO, but *application-level
multi-call sequences* are not atomic. A `Serial.printf` sequence from Core 0
(HTTPClient verbose log) can interleave byte-by-byte with a Core 1 JSON response,
producing lines the host cannot parse. Confirmed in T-BUSY-03 (line 2914–2939):

> "HTTPClient debug output from Core 0 races with the switchApp response from Core 1,
> splitting the JSON across two lines."

Recovery: flush buffer, sleep 3 s blind, retry. Unfixable at the harness level.

### P2 — Background Spotify poll races shared counters

`fetchOkCount` and `shellBusy` are global. The Spotify background poll task runs
concurrently with test operations. A background poll can:
- Advance `fetchOkCount` between the harness's pre-tap snapshot and the test's tap,
  making `_wait_chart_complete()` fire immediately on the wrong event.
- Briefly set then clear `shellBusy` between two successive 1 s harness polls,
  making `_wait_shell_not_busy()` never observe the true→false transition of the
  test-triggered operation.

### P3 — No synchronisation contract

There is no authoritative specification of *which mechanism owns which scenario*.
Tests evolved by trial-and-error, stacking `_wait_shell_not_busy()`, `_wait_chart_complete()`,
and `time.sleep()` defensively until locally stable. T-CDWN-02 calls
`_wait_shell_not_busy()` six times in a single test. The harness has no way to
distinguish "the fetch triggered by my tap" from "a background Spotify fetch".

---

## Goals

1. Eliminate UART line garbling — harness must be able to rely on complete, parseable
   JSON lines from the DUT at all times.
2. Eliminate background-poll contamination of per-test completion signals.
3. Establish a synchronisation contract: one mechanism per scenario, documented, no
   defensive stacking.
4. Reduce per-test sleep budget (target: no blind `time.sleep` > 0.5 s except at
   known firmware-side delays like TLS handshake).
5. Keep firmware changes surgical — no RTOS restructuring, no new tasks.

---

## Design space

### Option A — Suppress HTTPClient log output in debug build (partial fix, P1 only)

Add `-DCORE_DEBUG_LEVEL=1` (errors only) to `cyd2usb_winamp_debug` build flags, or
use per-tag suppression via `esp_log_level_set("HTTPClient", ESP_LOG_NONE)` in `setup()`.

- Eliminates Core 0 serial noise without touching synchronisation design.
- Doesn't address P2 or P3.
- Risk: loses HTTP-level debug visibility in the debug build. Mitigation: keep full
  logging on a second UART (U1/U2) or in a log ring buffer readable via `get log`.
- Effort: 1 build flag + 1 line in `setup()`. Low.

### Option B — Add `set bgPoll suspend/resume` command (P2 fix, surgical)

Expose `dbg_set("bgPoll", "0")` / `dbg_set("bgPoll", "1")` via `IDebugExportable`
in `spotifyTask`. When suspended, the task skips self-initiated polls (poll timer
never fires) but still processes explicit `ACT_FORCE_POLL` queue entries.

Harness protocol becomes:
```
set bgPoll 0          # isolate
<trigger operation>
<wait for completion signal>
set bgPoll 1          # resume
```

- Eliminates background-poll contamination of completion counters.
- Does not prevent the DUT state from drifting (Spotify may pause if not polled) —
  acceptable for short test windows.
- Harness gains deterministic per-test isolation.
- Effort: ~20 lines of firmware + harness refactor to wrap affected tests.

### Option C — Serial output mutex (P1 fix, correct)

Add a `static SemaphoreHandle_t s_serialMux` (binary, created once in `setup()`).
Wrap all application-level Serial writes with it:

```cpp
// dbg_serial_write.h
void dbgSerialWriteln(const char* buf);  // takes mutex, println, releases
```

Hook `esp_log_set_vprintf` to acquire the same mutex before writing log output.
This makes every complete JSON line atomic at the application layer — Core 0 log
lines can no longer split Core 1 responses.

- Correct fix for P1.
- The `esp_log_set_vprintf` hook runs on whichever core called `ESP_LOGI` etc., so
  the mutex must be a FreeRTOS `SemaphoreHandle_t` (safe across cores), not a
  `portMUX_TYPE` (Core-local spinlock only).
- Timeout risk: if Core 0 holds the mutex during a slow UART drain, Core 1 command
  handler stalls. Mitigate with a short mutex timeout (e.g., 50 ms) — fail the
  write rather than deadlock.
- Effort: ~40 lines of firmware (new file + hook). Medium.

### Option D — Async completion events, replacing polling (P2+P3, structural)

When the DUT completes an async operation triggered by a serial command, it emits a
completion event line:

```json
{"event":"done","seq":7,"ok":true,"cmd":"tap"}
```

The `seq` field is provided by the harness in the triggering command:

```
tap 72 97 seq=7
```

Background Spotify polls use `seq:0` (no harness token) and their completion events
are ignored by the harness. The harness's reader loop discards events until it sees
the matching `seq`.

This replaces `_wait_shell_not_busy()` and `_wait_chart_complete()` with a simple
`_wait_event(seq=N)` readline loop — no polling, no sleep, deterministic latency.

- Eliminates P2 and P3 entirely.
- Requires: (a) seq field threaded through the tap/switchApp command path into the
  async operation, (b) completion hook at the end of every async operation, (c) harness
  reader refactor.
- Non-trivial firmware change — seq must survive async dispatch (queue entry carries it).
- The `shellBusy` flag becomes redundant and can be deprecated.
- Effort: significant (firmware + harness). High.

### Option E — Lean combination: A + B + contract (recommended)

Apply Options A and B together, plus write a synchronisation contract document.
Defer Option D to a future milestone if residual flakiness persists.

Rationale:
- A alone fixes P1 without architectural risk.
- B alone fixes P2 (the dominant source of non-determinism in recent failures).
- A+B together reduce the combined failure space to near zero for known cases.
- The contract (P3) makes the harness maintainable without Option D's firmware scope.
- Option D remains the long-term ideal and can be phased in incrementally (one
  operation at a time) without invalidating A+B work.

---

## Lean / decision

**Adopt Option E.** Three-part delivery:

### E1 — Firmware: suppress HTTPClient log in debug build

In `platformio.ini`, `[env:cyd2usb_winamp_debug]`:
```ini
build_flags =
    ${env:cyd2usb_winamp.build_flags}
    -DSERIAL_DEBUG
    -DCORE_DEBUG_LEVEL=1
```

And in `setup()` (debug guard):
```cpp
#ifdef SERIAL_DEBUG
  esp_log_level_set("HTTPClient",  ESP_LOG_NONE);
  esp_log_level_set("HTTP_CLIENT", ESP_LOG_NONE);
#endif
```

`CORE_DEBUG_LEVEL=1` sets the Arduino log level to errors-only, which suppresses the
verbose `[HTTPClient]` trace that garbles responses. The two `esp_log_level_set` calls
are belt-and-suspenders for esp-idf's own HTTP client subsystem.

### E2 — Firmware: `set bgPoll 0/1` debug command

In `spotifyTask` (`spotifyTaskStorage.cpp`), add:

```cpp
// SERIAL_DEBUG only
static volatile uint8_t s_bgPollEnabled = 1;  // 1 = normal, 0 = suspended
```

Poll-initiation check (inside the task loop where the periodic poll timer fires):
```cpp
if (!s_bgPollEnabled) goto skip_poll;
```

`dbg_set("bgPoll", val)` sets `s_bgPollEnabled = (atoi(val) != 0)`.
`dbg_get("bgPoll", ...)` returns `{"var":"bgPoll","enabled":N}`.

Explicit `ACT_FORCE_POLL` queue entries bypass the flag — the harness can still
trigger a deliberate poll during a test if needed.

### E3 — Harness: synchronisation contract

A new helper `_isolated_op(dut, fn)` encapsulates the contract:

```python
def _isolated_op(dut: Dut, fn: callable, wait_fn: callable = None,
                 timeout_s: float = 45.0):
    """
    Execute fn() with background polls suspended and wait for completion.
    Pre: _wait_shell_not_busy(dut) — ensure no prior async work in flight.
    fn: callable that issues the triggering command(s).
    wait_fn: callable(dut) → bool that confirms completion. If None, uses
             _wait_shell_not_busy.
    """
    _wait_shell_not_busy(dut, timeout_s=10.0)
    dut.cmd("set bgPoll 0", timeout=2.0)
    try:
        fn()
        if wait_fn:
            return wait_fn(dut)
        return _wait_shell_not_busy(dut, timeout_s=timeout_s)
    finally:
        dut.cmd("set bgPoll 1", timeout=2.0)
```

**Contract (normative — all harness tests must follow this)**:

| Scenario | Pre-condition | Trigger | Completion signal | bgPoll |
|----------|--------------|---------|-------------------|--------|
| Network fetch triggered by tap | `_wait_shell_not_busy` | `tap` or `switchApp` | `_wait_chart_complete()` counter advance | suspend |
| Transport/volume action (no fetch) | `_wait_shell_not_busy` | `tap` | `_wait_shell_not_busy` clears | suspend |
| Cooldown / FSM state check (no async) | `set cooldown 0` | `tap` | JSON response only | optional |
| App switch without fetch | — | `switchApp` | JSON response + 0.3 s stabilise | optional |

Blind `time.sleep(N)` is only permitted for:
- Post-flash boot wait (fixed at `BOOT_WAIT` seconds, harness entry only)
- Known firmware-side delays (TLS handshake, display redraw < 0.3 s, documented)

All other sleeps are removed during the refactor pass in E3.

---

## Open questions

| # | Question | Owner | Resolution needed by |
|---|----------|-------|----------------------|
| OQ-1 | Does `CORE_DEBUG_LEVEL=1` suppress ALL relevant Core 0 noise, or only HTTPClient? Are there other verbose log tags that interleave? | Developer (verify on DUT) | Before E1 merges |
| OQ-2 | **Resolved** — `ACT_RECONNECT` path is `s_resetTlsPending`, checked before `xQueueReceive`, independent of `s_bgPollEnabled`. Confirmed by reading `spotifyTaskStorage.cpp:257–299`. `resetTls()` is checked at the top of the task loop before `xQueueReceive`. The `s_bgPollEnabled` flag only gates the `got == pdFALSE` (cadence self-poll) branch. They are completely separate code paths — `reconnect` is unaffected by bgPoll state. The VE-C1 invariant (`resetTls` resets `s_bgPollEnabled = 1`) is belt-and-suspenders, not a dependency. | Developer | Resolved |
| OQ-3 | Should `bgPoll` state be reset to `1` on reboot / test harness entry? Currently it would be reset by a reflash but not by a `reconnect` command. | VE to flag testability concern | Before E3 lands |
| OQ-4 | Is Option D (seq-tagged events) worth scheduling as a follow-on milestone? Depends on residual flakiness after E1+E2. | PM (post-E1+E2 burn-in) | After E3 stabilises |

---

## Exit criteria

- T-BUSY-01/01b/02/03 pass 10 consecutive runs without `_wait_shell_not_busy` stacking.
- T-CDWN-02/03 pass 5 consecutive runs.
- T169 passes 5 consecutive runs without retry loop (or retry loop is removed).
- No `time.sleep(N)` with N > 0.5 in any test body except documented exceptions.
- `get bgPoll` returns `{"enabled":1}` at harness entry for every test.
- Harness sync contract document committed to `docs/process/harness_sync_contract.md`.

---

## VE Review — 2026-06-08

> Reviewer: Verification Engineer
> Status: **Challenges raised — not approved yet. Architect must address before proposed→accepted.**

Overall: the diagnosis is sound and the three-part E1+E2+E3 split is sensible. The
design correctly identifies the dominant failure modes. The following challenges must
be resolved before implementation begins.

---

### VE-C1 — E2 firmware state is untestable without a harness-entry guard (OQ-3 is blocking)

The design notes that a leaked `bgPoll 0` (e.g., harness crash mid-test) leaves the
DUT silently frozen for subsequent tests. The design proposes a `get bgPoll` → `set bgPoll 1`
entry guard but doesn't specify:

1. **Where in the harness is it checked?** Must be at harness startup AND at the start
   of every test that uses `_isolated_op`, not just at process entry (a single-test
   targeted run skips process-level init).
2. **Is `bgPoll` state reset on DUT reboot?** `s_bgPollEnabled` initialises to 1, so a
   hard reset clears it — but `reconnect` does not reset it (reconnect only sets
   `s_resetTlsPending`, which is checked before `xQueueReceive` on the spotify task).
   A `reconnect` during a suspended window would execute TLS reset but leave
   `s_bgPollEnabled = 0` — the task would never self-poll again.

**Resolution required**: Specify that `reconnect` always resets `s_bgPollEnabled = 1`
as a side effect. Add this invariant to ADR-042. Write a test case (new T-BGPOLL-01)
that suspends bgPoll, issues `reconnect`, and verifies `get bgPoll` returns `enabled:1`.

---

### VE-C2 — E1 log suppression is not verifiable by the harness

`CORE_DEBUG_LEVEL=1` and `esp_log_level_set` are set at compile/runtime but the harness
has no way to confirm they took effect. The DUT could ship with the wrong build flags
and the harness would have no diagnostic signal before tests start garbling.

**Resolution required**: The `info` command response (ADR-021 Feature 5) already emits
`git` + `elf` but not build flags. Either:
- (a) Add a `debugLevel` field to `info` output (e.g., `"logLevel":1`) so the harness
  can assert `info.logLevel == 1` at startup; or
- (b) Accept the existing elf-hash check as sufficient (wrong firmware = different elf).

Option (b) is acceptable IF the harness startup procedure always verifies the elf hash
before running tests. Confirm this is already enforced. If not, add it.

---

### VE-C3 — `_isolated_op` wrapper hides test-specific pre-conditions

The design proposes a single `_isolated_op()` that calls `_wait_shell_not_busy` as
the generic pre-condition. But the sync contract table lists four scenarios with
different pre-conditions:

| Scenario | Pre-condition |
|----------|--------------|
| Network fetch by tap | `_wait_shell_not_busy` |
| Transport/volume (no fetch) | `_wait_shell_not_busy` |
| Cooldown/FSM check | `set cooldown 0` |
| App switch without fetch | none |

A single `_isolated_op()` that always calls `_wait_shell_not_busy` will add 10 s
timeouts to tests that don't need it (cooldown tests, app-switch-only tests).
More importantly, tests that need `set cooldown 0` *before* the bgPoll suspend won't
get it from the generic wrapper.

**Resolution required**: Either (a) parameterise `_isolated_op(pre_fn=...)` so callers
pass their own pre-condition callable; or (b) keep `_isolated_op` minimal (only
bgPoll suspend/resume) and leave pre-conditions explicit at call site. Option (b) is
preferable — it preserves test readability. Document this in the contract.

---

### VE-C4 — Exit criteria are pass/fail counts, not specification assertions

"T-BUSY-01/01b pass 10 consecutive runs" is a reliability target, not a specification
check. If the tests pass 10 times because sleeps were *increased* rather than removed,
the exit criterion is satisfied but the design goal is not.

**Resolution required**: Add a measurable specification assertion to the exit criteria:

> "After E3, the total `time.sleep()` budget across T-BUSY-01, T-BUSY-01b, T-CDWN-02,
> and T169 combined must be ≤ 4 s (excluding `BOOT_WAIT`)."

This is falsifiable. The current budget for those four tests combined is approximately
18–25 s based on the audit data. The 4 s target reflects post-refactor expectations
(app-switch stabilise overhead only).

---

### VE-C5 — No coverage specified for new `bgPoll` commands

E2 adds `get bgPoll` and `set bgPoll` to the debug command surface. These are new
serial commands with no test coverage specified. Per team protocol, new debug surface
requires ≥ 1 test case.

**Resolution required**: Add the following to the exit criteria:

> New test suite **T-BGPOLL-01 through T-BGPOLL-03** covering:
> - T-BGPOLL-01: `set bgPoll 0` → DUT self-polls suspended (no `shellBusy` transitions
>   for ≥ 5 s with no harness commands); `get bgPoll` returns `enabled:0`.
> - T-BGPOLL-02: `set bgPoll 0` + `reconnect` → `get bgPoll` returns `enabled:1`
>   (VE-C1 regression guard).
> - T-BGPOLL-03: `set bgPoll 0` + `ACT_FORCE_POLL` tap → fetch completes (force poll
>   bypasses the flag); `get bgPoll` still `enabled:0` (not self-resumed).

---

### VE-C6 — OQ-1 (Core 0 noise sources) must be answered before E1 merges, not after

OQ-1 is marked "resolve before E1 merges" but is assigned to Developer to "verify on
DUT". There is no test procedure specified. If Developer verifies informally, there is
no regression guard.

**Resolution required**: Developer must produce a test procedure:
1. Flash `cyd2usb_winamp_debug` with E1 changes.
2. Trigger a stock/weather chart fetch (known HTTPClient activity).
3. Issue a serial command simultaneously and capture 100 lines.
4. Assert: zero lines that fail `json.loads()` (excluding the boot line and known
   non-JSON lines).

This procedure becomes **T-UART-01** (new, integration) and gates E1 merge.

---

### VE-C7 — Deferred Option D creates a testability cliff

The design defers seq-tagged completion events to "after E1+E2 burn-in". This is
reasonable, but the deferred design has a testability implication that should be
captured now: if Option D is implemented later, the `shellBusy` polling mechanism
must be deprecated simultaneously (not in parallel), or tests will use both
mechanisms and the contract will revert to ambiguity.

**Recommendation** (non-blocking for ADR approval): Add to ADR-042 Consequences:
> "If Option D (seq-tagged events) is adopted in a future ADR, `get shellBusy` must
> be removed from the debug command surface in the same ADR — not deprecated separately."

---

### VE summary

| Challenge | Blocking for ADR approval? | Action |
|-----------|---------------------------|--------|
| VE-C1 (`reconnect` resets bgPoll) | **Yes** | Add invariant to ADR + T-BGPOLL-02 |
| VE-C2 (log suppression verifiable) | **Yes** | Decide (a) or (b) + document |
| VE-C3 (`_isolated_op` pre-condition) | **Yes** | Revise to option (b) |
| VE-C4 (sleep budget assertion) | **Yes** | Add measurable exit criterion |
| VE-C5 (bgPoll test coverage) | **Yes** | Add T-BGPOLL-01/02/03 |
| VE-C6 (OQ-1 test procedure) | **Yes** | Add T-UART-01 procedure |
| VE-C7 (Option D deprecation note) | No (recommendation) | **Adopted** — added to ADR-042 Consequences 2026-06-08 |

All six blocking challenges must be resolved before ADR-042 moves to `accepted`.

---

## Architect responses to VE review — 2026-06-08

### Response to VE-C1 — `reconnect` resets `bgPoll`

**Resolved.** E2 firmware spec updated: `resetTls()` in `spotifyTaskStorage.cpp` will
also unconditionally set `s_bgPollEnabled = 1`. Rationale: `reconnect` is a recovery
operation and should restore the task to its fully operational default state. The flag
is therefore a reset-on-recovery invariant, not just an initialisation-time default.

Updated E2 spec:

```cpp
void resetTls() {
  s_resetTlsPending = true;
#ifdef SERIAL_DEBUG
  s_bgPollEnabled = 1;   // recover from any leaked suspend
#endif
}
```

ADR-042 Consequences updated to capture this invariant explicitly.
T-BGPOLL-02 added to exit criteria (see VE-C5 response).

---

### Response to VE-C2 — Log suppression is not harness-observable

**Resolved — adopting option (b).** The elf-hash check provides sufficient firmware
identity verification without adding a `debugLevel` field to `info` output (which
would require a firmware change and add ongoing maintenance burden to the `info`
command format).

`_verify_debug_firmware()` currently only checks `get heap`. It must be extended to
also verify the elf prefix:

1. At harness startup, read the expected elf prefix from the build artifact:
   ```python
   import struct, pathlib
   fw = pathlib.Path(".pio/build/cyd2usb_winamp_debug/firmware.bin").read_bytes()
   expected_elf = fw[0x20 + 144 : 0x20 + 148].hex()
   ```
2. Issue `info` and parse `elf` field from the response.
3. Assert `info["elf"] == expected_elf`. Failure raises `RuntimeError` with the same
   reflash instructions as the existing production-firmware guard.

This check gates every harness run against the exact binary that was compiled with
E1's log-suppression flags. A build without `-DCORE_DEBUG_LEVEL=1` produces a different
elf hash and fails fast.

OQ-1 is partially answered: `CORE_DEBUG_LEVEL=1` suppresses the Arduino-layer log
macros (`log_d`, `log_v`) which cover the HTTPClient verbose path. The esp-idf
`esp_log_level_set` calls in `setup()` cover the IDF-native HTTP client tag. T-UART-01
(see VE-C6 response) provides the empirical confirmation that no other verbose Core 0
sources remain.

---

### Response to VE-C3 — `_isolated_op` pre-condition design

**Resolved — adopting option (b).** `_isolated_op` is reduced to a pure bgPoll
isolation wrapper. Pre-conditions remain explicit at call site.

Revised E3 design:

```python
from contextlib import contextmanager

@contextmanager
def _bgpoll_suspended(dut: Dut):
    """Context manager: suspend background Spotify polls for the duration."""
    dut.cmd("set bgPoll 0", timeout=2.0)
    try:
        yield
    finally:
        dut.cmd("set bgPoll 1", timeout=2.0)
```

Usage pattern — each test spells out its own pre-condition before entering the context:

```python
# Network-fetch test (T-BUSY-01 style):
_wait_shell_not_busy(dut, timeout_s=10.0)           # pre-condition: explicit
with _bgpoll_suspended(dut):
    before = _stock_ok_count(dut)
    dut.cmd("tap 162 120", timeout=3.0)             # trigger
    ok = _wait_chart_complete(dut, before)           # completion: explicit

# Cooldown/FSM test (T079 style):
dut.cmd("set cooldown 500", timeout=2.0)            # pre-condition: explicit
with _bgpoll_suspended(dut):
    r = dut.cmd("tap 72 97", timeout=2.0)           # trigger
    assert r.get("skipped") is True                 # completion: synchronous response

# App-switch without fetch (T169 style):
with _bgpoll_suspended(dut):
    dut.cmd("switchApp Spotify", timeout=3.0)
    time.sleep(0.3)                                 # display stabilise only
```

The sync contract table in the Lean section is updated to reflect this separation.

---

### Response to VE-C4 — Sleep budget as a measurable exit criterion

**Resolved.** The following measurable criterion replaces the pass-count-only wording
in the exit criteria section:

> After E3, the combined `time.sleep()` budget across the test bodies of T-BUSY-01,
> T-BUSY-01b, T-CDWN-02, and T169 must total ≤ 4 s (excluding `BOOT_WAIT` and
> `_bgpoll_suspended` context entry/exit). Current estimated budget: 18–25 s.
> Verified by static grep on the refactored harness before merge.

The 4 s ceiling accounts for one 0.3 s display-stabilise sleep per app switch (up to
~4 app switches across the four tests). Any sleep above this threshold in a test body
must have a code comment citing the specific firmware-side delay it covers.

---

### Response to VE-C5 — bgPoll test coverage

**Resolved.** Three new test cases added to exit criteria:

**T-BGPOLL-01** — `set bgPoll 0` suspends self-polls
- Pre: DUT in Spotify app, `get bgPoll` → `enabled:1`.
- Steps: `set bgPoll 0`; issue `get bgPoll` → assert `enabled:0`; monitor serial for
  5 s; confirm no `shellBusy` transitions occur (no self-initiated poll fired).
- Expected: `get shellBusy` returns `busy:false` throughout the 5 s window.

**T-BGPOLL-02** — `reconnect` resets suspended bgPoll (VE-C1 regression guard)
- Pre: `set bgPoll 0`; confirm `get bgPoll` → `enabled:0`.
- Steps: issue `reconnect`; issue `get bgPoll`.
- Expected: `get bgPoll` → `enabled:1`. DUT self-polls resume within next cadence window.

**T-BGPOLL-03** — `ACT_FORCE_POLL` bypasses suspension
- Pre: `set bgPoll 0`; confirm `enabled:0`.
- Steps: tap DEADZONE (triggers `ACT_FORCE_POLL`); wait for `shellBusy` to cycle
  true→false (or `fetchOkCount` advance if in Stock app); issue `get bgPoll`.
- Expected: fetch completes; `get bgPoll` still returns `enabled:0` (flag not
  self-resumed by the force-poll path).

---

### Response to VE-C6 — OQ-1 needs a test procedure

**Resolved.** OQ-1 is promoted to a gating sub-task with a defined procedure:

**T-UART-01** — No JSON-garbling under concurrent Core 0 / Core 1 serial activity
- Pre: DUT flashed with E1 build (`-DCORE_DEBUG_LEVEL=1` + `esp_log_level_set` calls
  confirmed by elf-hash check per VE-C2 resolution).
- Steps:
  1. Switch to Stock app (triggers a chart fetch — known HTTPClient activity on Core 0).
  2. While the fetch is in flight (immediately after the triggering tap), send 20
     `get heap` commands in rapid succession (10 ms apart) from the harness.
  3. Capture all response lines for 10 s.
  4. Pass every non-boot line through `json.loads()`.
- Expected: zero `json.JSONDecodeError` exceptions across all 20+ responses. Any
  garbled line is a failure.
- Gates: E1 merge. Must pass before E2 or E3 work begins.

OQ-1 is marked **resolved pending T-UART-01 pass** (empirical confirmation that
`CORE_DEBUG_LEVEL=1` + `esp_log_level_set` suppresses all interleaving Core 0 sources,
not just HTTPClient). If T-UART-01 reveals residual noise from another log tag,
Option C (serial mutex) must be reconsidered.

---

### Updated sync contract table (post VE-C3)

| Scenario | Pre-condition (explicit at call site) | Trigger | Completion signal | bgPoll |
|----------|---------------------------------------|---------|-------------------|--------|
| Network fetch by tap | `_wait_shell_not_busy(10 s)` | `tap` / `switchApp` | `_wait_chart_complete()` | suspend |
| Transport/volume (no fetch) | `_wait_shell_not_busy(10 s)` | `tap` | `_wait_shell_not_busy` clears | suspend |
| Cooldown / FSM state check | `set cooldown <ms>` | `tap` | JSON response field | suspend (optional) |
| App switch without fetch | — | `switchApp` | `time.sleep(0.3)` only | suspend |

Blind `time.sleep(N > 0.5)` prohibited in test bodies except `BOOT_WAIT` and
documented firmware-side delays with inline comment.

---

### Design doc status update

All six blocking VE challenges resolved. ADR-042 updated accordingly. Design doc
status: **draft → ready for human review**. ADR-042 may move to `accepted` on human
sign-off.
