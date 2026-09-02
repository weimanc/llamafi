# M-TESTQUAL — the audit rubric

> Owner: **Verification Engineer**
> Status: fixed 2026-09-02 — do not amend mid-audit; amendments land as a dated §6 entry.
> Parent: [M-TESTQUAL index](M-TESTQUAL-index-review.md)

Every per-test audit package (WP-C…WP-H) grades against this document and nothing else.
A fixed rubric written before the first family is read is the only way eight family
audits produce comparable verdicts.

---

## 1. The one question

> **If the firmware behaviour this test claims to cover were broken, would this test
> fail?**

Everything below is a way of answering that mechanically. A test that cannot fail for
the reason it exists is worthless however much code it contains, and worse than absent,
because it is counted as coverage.

---

## 2. Verdict vocabulary — exactly four values

| Verdict | Meaning |
|---|---|
| **SOUND** | Asserts on device-observed state that the claimed behaviour actually produces. A regression in that behaviour fails this test. |
| **WEAK** | Asserts something real, but narrower than what it claims, or with an oracle that tolerates the failure mode (a default that swallows a missing field, a bound so loose it cannot be violated, only the ack and not the effect). Would catch *some* regressions. |
| **HOLLOW** | Reaches `pass_()` without proving the claimed behaviour at all: no assertion, an assertion on the harness's own input, a check that the command was accepted rather than that anything happened, or a pass whose detail string defers the actual verification to a human. **This is the "cheating" bucket.** |
| **BROKEN** | Cannot do its job as written: unreachable assertion, wrong id in the record, exception swallowed into a pass, a skip that hides a real failure, or a body that no longer matches the firmware surface it drives. |

No fifth value. "Fine, probably" is **WEAK** and must be evidenced like any other.

---

## 3. Smell codes — cite these, one or more per non-SOUND verdict

Detection is a code read, not a guess. Each code names what to grep for.

| Code | Smell | How it shows up |
|---|---|---|
| **S1** | Unconditional pass | `pass_()` on a path with no preceding comparison against device data. |
| **S2** | Ack-not-effect | Asserts only `r.get("ok")` / that a command parsed, never that the device changed. |
| **S3** | Tautology | Asserts a value the harness itself just sent, or re-reads the same debug field it wrote through the same code path. |
| **S4** | Deferred to a human | Pass detail contains "verify manually", "eyeball", "check by ear", or similar. The test asserts the *precondition* and calls it a pass. |
| **S5** | Swallowed failure | `except: pass`, `except Exception: pass`, a bare `continue` on a read error, or a helper returning `True` on timeout/ambiguity. |
| **S6** | Defaulting oracle | `r.get("field", <value that passes>)` — a missing or renamed firmware field reads as success. The single highest-yield grep in this audit. |
| **S7** | Skip-as-pass | `skip()` on a condition that is a genuine failure (feature absent, DUT unconfigured, fetch failed), so the suite reads green while covering nothing. |
| **S8** | Vacuous bound | A threshold that no realistic regression can violate (`heap > 0`, `len(lines) >= 0`, a 200 s timeout on a 2 s operation used as the assertion). |
| **S9** | Fixed-sleep synchronisation | `time.sleep(n)` used as the oracle rather than waiting on an event/marker (M-TESTARCH §3b). Flake source and a silent pass source. |
| **S10** | Magic value | A literal threshold/coordinate/timeout with no cited origin — neither a firmware constant nor a documented measurement. |
| **S11** | Double bookkeeping | A firmware constant, enum value, pin, coordinate or app-slot re-declared in the suite instead of imported from `app/gen/` or parsed from the header (LL-114: parse, don't mirror). Drifts silently. |
| **S12** | Wrong-id / mis-scoped record | `pass_("T0xx")` inside the body of a different test, or an id whose `(cls, scope)` record contradicts what the body drives. |
| **S13** | Overlap | Two ids whose assertions are the same assertion; or one id asserting several unrelated behaviours so a failure cannot be localised. |
| **S14** | State leakage | Mutates DUT state (app, settings, playback, queue) without restoring it, so a neighbour's result depends on run order. |

---

## 4. What each family audit must produce

A single document, structured exactly like this, so WP-Z can merge them mechanically.

1. **Scope line** — module, id count, how the count was measured (command).
2. **Per-test table**, one row per id, in registry order. **The first cell is the body
   location, never the bare id** — see the §6 amendment; a bare id in column 1 binds as a
   `check_docs` C6 doc entry and can silently clear a real orphan:

   | Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
   |---|---|---|---|---|---|---|
   | `player.py:456` | T123 | what the test says it covers | the specific device-observed value it compares | SOUND | — | `player.py:470` compares `pos` against … |

   * **Claim** comes from the docstring/`test_plan.md` entry — what it *promises*.
   * **Oracle** is the actual comparison. If you cannot name one, the verdict is HOLLOW.
   * **Evidence** cites lines. A row without a line cite is not accepted.
3. **Family findings** — the non-SOUND rows grouped by smell, with severity
   (**P1** the test is counted as coverage but provides none; **P2** materially weaker
   than claimed; **P3** hygiene) and a one-line proposed fix each.
4. **Counts** — SOUND/WEAK/HOLLOW/BROKEN totals, and the smell histogram.
5. **NEEDS-DUT list** — anything that cannot be settled statically. Do not guess.

---

## 5. Rules of engagement

* **Read the body. All of it.** Verdicts from grep alone are not accepted; grep locates
  candidates, the read decides.
* **Check the firmware side when the oracle names a field.** If a test greps for a log
  marker or reads a `get` field, confirm that marker/field exists in `app/src/`. A test
  waiting on a string the firmware no longer prints is BROKEN, not WEAK — and its
  failure mode is usually a timeout that some helper converts to `True`.
* **Do not run the suite. Do not flash. Do not touch the DUT.** Board is pinned to the
  `-DBOD_WATCH` debug build (TASK-557).
* **Never `import` a module under `app/tools/` to inspect it — read it.** Six modules
  (`prloc_smoke.py`, `prloc_ve_smoke.py`, `prloc_manual_smoke.py`, `prloc_editor_smoke.py`,
  `settings_kit_smoke.py`, `clock_tap_smoke.py`) open the serial port and run their whole
  DUT suite at *import* time — no `__main__` guard. Importing them resets the board. This
  is WP-A finding A-12, discovered the hard way; it cost one board reset and one
  contaminated observation window. The only imports permitted are
  `suite.serialdbg.build_all_tests/build_all_meta` and `app/gen/*.py`.
* **Do not edit the suite.** This is an audit. Fixes are separate, scheduled work.
* **Do not soften.** The purpose of this exercise is to find the tests that lie. A
  family audit reporting 100 % SOUND will be re-run by another auditor.
* **Uncertain is a verdict too** — record it as NEEDS-DUT with the exact question that
  hardware would settle, never as a silent SOUND.

---

## 6. Amendments

**A1 — 2026-09-02, after WP-A.** §5 gained the ban on importing anything under
`app/tools/`: six modules open the serial port and run their DUT suite at import time
(WP-A finding A-12). One such import reset the board mid-audit.

**A2 — 2026-09-02, after WP-B.** The `-review.md` exemption is **weaker than the index
first claimed**, and every remaining package must write its tables accordingly.
`is_exempt()` suppresses *status* scanning only. `doc_test_entries()`
(`app/tools/gate/check_docs.py:665`) still binds any table row whose first cell —
after `strip("`* ")` — is a bare test id, and any `### T123` heading, in *every*
file under `docs/verification/`, exempt or not. A bound entry **resolves C6.1**, which
means an audit table can silently clear a genuine orphan and turn its
`id_binding_exceptions.md` row into a stale exception, which is itself a blocking
failure. WP-B hit exactly this with `T_PRM_01`.

Therefore, binding on every package from WP-C onward:

* the per-test table's **first column is the body location**, the id goes in column two;
* **never** open a section with `### T123` / `### \`T_CC_01\`` — write `### T123 — …`
  as prose inside the row, or head the section with the module and line;
* run `./run/check-docs` once before you hand the document over, and if C6 moves at all,
  fix your table rather than the ledger.
