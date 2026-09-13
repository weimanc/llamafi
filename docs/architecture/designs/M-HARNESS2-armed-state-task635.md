# TASK-635 — armed device state, enumerated and asserted at every boundary (R14)

> Status: accepted
> Owner: @Developer (firmware + harness), reviewed against @Architect's R14/R15 amendments ·
> written 2026-09-13 · requirement: [R14](../../verification/M-HARNESS2-requirements.md) ·
> binds under [IFC-007](../interfaces/IFC-007.md) (additive only) and [ADR-066](../decisions/ADR-066.md)
> (the verdict enum stays at seven).

## 1. What R14 needs, and what it does not

R14 asks for two things. The firmware reports every debug injection that is currently armed, in one
observable. The harness reads that observable after every test and FAILs the test that ran if
anything is armed. The failure lands on the test that armed the injection, not on the ids that ran
after it. The inversion test named in R14's own *Verification* line is part of the task.

It does **not** ask the firmware to clear injectors in `resume()` (R15). The architect review
amended R15 to clear on `init()` only, plus one explicit `set injclear` the harness calls. Only that
half is taken here: `set injclear` exists so that a leak detected at a boundary does not also spoil
the tests after it.

## 2. Firmware — `get armed`, `set injclear`

**No bitmask and no new state.** Where the architect review estimated ~8 B for a bitmask, this is
**0 B of new `.dram0.bss` except one bool** (§2.3). `get armed` evaluates each injector's predicate
at query time, over the variable the injector already sets. A stored mask can drift from the state
it describes; a predicate over the real variable cannot.

### 2.1 The table — one X-macro, one file

`app/src/debug/armedInjectors.h` holds the one list, as
`X(name, armedExpr, clearStmt)`. `get armed` and `set injclear` both expand it, so neither can
list an injector the other misses. Each app exposes whatever small `dbg*` accessor the expression
needs (under `SERIAL_DEBUG`), and nothing else.

### 2.2 Membership rule

An injector is in the table when all three hold:

1. a console `set` (or other console command) arms it;
2. it changes behaviour away from the real path and **persists after the command returns**;
3. its armed state can be told apart from the real path's own state **without adding state**.

Clause 3 is why some sticky overrides are left out. `wrState`, `songDuration`, `wrBufPct` and
`wrIcy` are overwritten by the real path, and so is Stock `fetchFailed`, which a real failure also
sets. "Forced" and "real" cannot be separated for those without a flag, so they belong to
[R17](../../verification/M-HARNESS2-requirements.md) (restore discipline), not R14.

The rig and diagnostic instruments are **excluded by rule**, and named in the gate's exclusion list
with the reason:

- `bod*`, `bodmit`, `set fault bod`: the TASK-557/678 instruments, some held in RTC memory across
  resets on purpose;
- `logLevel`/`logKeep`, `wifiPs`, `beaconWatch`: they change observation or radio power, not an
  app's verdict path;
- `cooldown`: the harness sets it itself before almost every tap, and it expires by time;
- `nvsSsid`: it writes flash NVS. Clearing that is not a RAM operation, and an armed-set entry that
  `injclear` cannot clear would be a lie.

### 2.3 Initial members

| name | armed when | cleared by `injclear` via |
|---|---|---|
| `nowFrozen` | `set now … freeze` holds | `dbgTimeThaw()` |
| `aeDmaFloor` | override ≠ `AE_I2S_DMA_FLOOR_BYTES` | reset to the default |
| `aeNoArena` | `s_aeNoArenaInject` | `= false` |
| `aeFailAudio` | `s_aeFailAudioInject` | `= false` |
| `arenaHold` | the console holds the arena — **new 1 B `s_consoleArenaHold`**, because `mb_arena_active()` is also true during real playback | `mb_arena_release()` + clear |
| `casRetryOff` | cookie valid && off | cookie cleared (RTC) |
| `certbreak` | `s_certBreakTarget >= 0` | `= -1` |
| `prForceParseFail` | count > 0 | `= 0` |
| `geocode` | `s_geoInjected` (unconsumed) | `= false` |
| `wrDeadUrls` | `_debugForceConnFail` | the `set wrDeadUrls 0` path |
| `wrPosbarSimDrain` | `_posbarSimDrainActive` | the `… 0` path |
| `prInject` | `_injected` | the `set prClearInject 1` path |
| `teletextContent` | `_injectedContent` | `= false` |
| `ldrRaw` | injected LDR ≠ -1 | `injectLdr(-1)` |
| `spotifyWedge` | `s_dbgWedgeMs > 0` (unconsumed) | `dbg_set("spotifyWedge","0")` |
| `bgPollOff` | `s_bgPollEnabled == 0` — the real path only sets it to 1 (reconnect) | `dbg_set("bgPoll","1")` |

The last two rows were added after the completeness gate (§2.5) ran for the first time. It flagged
`spotifyWedge` as a candidate. `bgPoll` it had classified as an operational toggle, which was wrong:
B-6 is exactly a leaked `bgPoll 0` starving 94 successors.

### 2.4 Wire shape (IFC-007, additive)

```
get armed    → {"ok":true,"cmd":"get","var":"armed","n":2,"armed":["wrDeadUrls","nowFrozen"],"last":true}
set injclear 1 → {"ok":true,"cmd":"set","var":"injclear","n":2,"cleared":["wrDeadUrls","nowFrozen"]}
```

`n` is the list length. The order is table order. The console parser requires a value, so a bare
`set injclear` answers `bad args`. The `1` is ignored; this was found on the DUT, not by the host arms.

### 2.5 The completeness gate

"No declaration ships without a mechanical check." `gate/check_armed_injectors.py` extracts every
console `set` key from `cmdSet.cpp` and every `dbgSet` body. It then asserts that each key is
either an injector in `armedInjectors.h` or is named in the gate's own `NOT_INJECTORS` table with a
one-line reason. A new `set` key that is in neither fails `run/check`. The gate lands **at zero**,
with a negative suite.

## 3. Harness — the boundary check

`_gate.run_suite` gains `boundary=None`, a callable run **after every `dispatch(tid)`**, after the
flake retry has settled. It returns the armed list, or `None` if the key is unsupported. The
decision is a pure function in `lib/armed.py`, so the host inversion test drives it with no device:

- **empty** → nothing;
- **non-empty** → the id that just ran gets a **FAIL**, whatever it recorded. The reason names the
  injectors, and if the id already had a FAIL or UNMET, its original record is kept inside the new
  reason. The harness then sends `set injclear`, so the next id starts clean. Because of the clear,
  the successor's verdict is its own;
- **`None`** (older firmware: `unknown var`) → tolerated, announced once per run. This is the stub
  the DEV review's Day 8 asked for, so the harness does not wait on a flash.

A **session-start** read runs before the first id. Anything armed there cannot be attributed to a
test in this run, so it is cleared and printed as a rig note, not assigned to any id.

**No `@meta(arms=…)` declaration is added.** R14 says "non-empty and *undeclared*", but no test
today is meant to leave an injector armed for its successor. That would be the order dependence
R20 forbids. Declaring it becomes justified the first time a real case appears, and not before.

**The verdict enum is untouched** (ADR-066 D2a). A leak is a FAIL with a reason.

## 4. Acceptance

1. Host: the inversion test (the arming test FAILs, its successor keeps its own PASS), a
   session-start leak attributed to nobody, and tolerance of `None`. All blocking in `run/check`.
2. Host: the completeness gate at zero, with a negative suite.
3. Build: every env builds, with `.dram0.bss` headroom re-derived from the debug `.map`.
4. DUT: `set wrDeadUrls 3` → `get armed` names `wrDeadUrls` → `set injclear` → `get armed` is
   empty. Then one full `run/test`, whose boundary FAILs are the finding. **The count of ids R14
   newly fails is the measurement this task exists to produce.**
