# TASK-637 — skeptical review (2026-09-26)

> Reviewer: @PM, at the human's request. **Documentation only — TASK-637 was not executed, no
> firmware or test was changed, and nothing was run on hardware.** Method: read
> [ADR-063](../../architecture/decisions/ADR-063.md), [IFC-003](../../architecture/interfaces/IFC-003.md)
> I11/D3, commits `92066925`, `60f98004`, `70f049fe`, `0cc990e1`, `a80fa2ef`, the guard in
> `app/src/appShell.cpp` and its call sites, and grepped `app/tools` for a test.
> Limit: the "no test covers it" claim comes from grepping `app/tools` for `appTicks` and
> `inactiveApp`; a test that reaches the guard indirectly through another key would have escaped it.

## Verdict

**PARTIAL is an honest label, but "DUT-verified" is weaker than it reads, and the task does not yet
deliver its goal.** The goal (ADR-063 D3) is that a `switchApp` which silently stopped switching
fails an assertion somewhere (finding A-8). Nothing asserts it.

## What landed

- Guard: `dbgAppIsActive()` / `dbgRefuseInactive()` (`appShell.cpp`), hand-inserted at each per-app
  key's existing delegation site in `cmdGet.cpp` (and, via TASK-703 `a80fa2ef`, some of `cmdSet.cpp`).
- Tick counter: `g_appTicks[]`, bumped around the shell's own `appTick()`.
- Three named exceptions in `dbgKeyReachableInactive()`: `weatherReady`, `cryptoReady`, `prPollSec`.
- 10 of 13 apps guarded. Spotify, WebRadio, LocalPlayer deliberately not.

## Findings

1. **`T_APPKEY_01` does not exist.** It was the replacement for the four `_02` ids deleted by
   TASK-598 on the understanding that it would follow. It has a `test_plan.md` entry still marked
   "blocked", no body, no registry entry, no generated row; `shell.py:1392` is a comment pointing at
   it. The gap TASK-598 opened — no id asserts a per-app key is refused when inactive — is still
   open, and this is the task meant to close it.
2. **"DUT-verified" rests on a commit message.** `0cc990e1` says the guard refused foreign keys and
   `appTicks` advanced only for the active app. No committed test asserts either. Under BP-075 a
   criterion closes against the oracle it names; the named oracle is an automated test. The claim is
   an observation by the author of the guard.
3. **The exception list is empirical, not derived.** "The whole observed blast radius" means one
   full run. A test that reads another app's key by design and was skipped in that run (TASK-697
   costs ~22 Stock ids when it fires) would surface later as an `inactiveApp` refusal.
4. **The design was substituted.**
   - D2 (delegate through `g_apps[]`, delete the typed instance names) was not built: 31 references
     to `g_ClockApp`, `g_WeatherApp` etc. remain in the console; the levelization violation stands.
   - ADR-063 D3 asked for **one shared guard in the delegation path**. What shipped is a per-call-site
     guard. A new key added without one silently reintroduces A-8, and nothing detects it. This is
     the "convention, not a generated enumeration" shape the ADR's own alternatives table rejects.
   - IFC-003 records both deviations honestly. ADR-063's `As-built` field still says "not yet".
5. **Three apps unguarded on purpose** (the player-slot family), justified by a pre-existing
   always-reachable contract (TASK-415 / ADR-059 D12). Plausibly right, but with no conformance row
   naming them, "10 of 13" is a claim in prose only.
6. **Repaint counter unbuilt.** The first attempt (`get appRepaints`) counted ticks under a repaint
   name and was correctly removed (`60f98004`). D4's second half is missing (now TASK-702). The row
   title still says "tick/repaint counters".
7. **Downstream dependency.** TASK-593 and `T_APPKEY_01` are BLOCKED on 637. The board's "needs
   nothing but hands" is true only for the test body; the D1/D2 question needs a ruling first.

## Recommendations (not scheduled, not executed)

| # | Recommendation | Est. |
|---|---|---|
| R-1 | Write `T_APPKEY_01` as a generated test over `APP_ORDER` × declared keys, with the 3 unguarded apps and the 3 exceptions as explicit named rows (ADR-063 *Consequences*: generate over declared keys, never over presence of an override). Turns finding 2 into evidence. | ~1 d, DUT for the first run |
| R-2 | Add a host gate: every per-app key in `cmdGet.cpp`/`cmdSet.cpp` has a guard call or a named exemption. Replaces the convention with a check (finding 4). Negative suite per BP-068. | ~0.5 d, host only |
| R-3 | Human/@Architect ruling: is D1/D2 (`App::dbgGet`/`dbgSet`, delegate via `g_apps[]`) still wanted? If not, amend ADR-063 so it stops describing something that will not be built; if yes, it belongs in TASK-593's one-app-per-commit sequence. | ruling |
| R-4 | Retitle the row to what is true: "identity guard (10/13 apps, per-site) + tick counter; no conformance test". | doc |
| R-5 | Derive the exception list: scan the suite for ids that read a per-app key while another app is active, rather than trusting one run's refusals. | ~0.5 d, host only |

**Suggested order:** R-3 first (it decides R-1's shape), then R-2 and R-5 (host-only), then R-1.
