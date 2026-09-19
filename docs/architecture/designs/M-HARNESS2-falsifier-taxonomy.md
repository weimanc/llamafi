# M-HARNESS2 — what a falsifier means per test (TASK-641/642/643 design)

> Owner: **@Architect**
> Status: accepted
> Filed 2026-09-08 under TASK-671's session, for TASK-641/642/643 (Phase 5, blocked on the Phase 3
> entry). **RULED 2026-09-09 by the human: all eight decision points accepted** (confirmed = every arm
> in its cell; role + shape; contract reds do not count; POLL = freeze + dilation; freeze total on the
> mutated key only; undeclared = incidental; physical expiry enforced; LocalPlayer + Clock first). The
> rows execute as amended in §8. Substrate: `lib/replay.py` (TASK-628), `lib/canfail.py` + `lib/dispatch.py`
> (TASK-671, [runtime-gates design](M-HARNESS2-runtime-gates.md)).
> Sources: [R9/R10/R10a/R12](../../verification/M-HARNESS2-requirements.md), [DEV review §4](M-HARNESS2-DEV-review.md),
> [PM review §4.1](../../project/M-HARNESS2-PM-review.md) (R1 prose reason cut; R11 campaign → enforced expiry).

## 1. The problem

R9 says every id declares a falsifier; R10 says a host job confirms it by mutating a recorded
transcript; AC4 wants ≥ 90 % confirmed. The plan treats "falsifier" as one thing — *a field in a
reply, mutated* — and the replay engine's own negative suite already found a test that this cannot
touch: `T_MA_03`'s oracle is a **polled** counter (`lastPlaylistDraw` must advance within 3 s), and
freezing it makes the body poll past the end of a healthy recording. The miss is correctly a void
(`test_replay.py` N4d), so the id is unfalsifiable by the mechanism as specified — and it is one of
the *good* tests. A taxonomy that cannot confirm the corpus's sound polled oracles, or that confirms
a tautology as readily as a real oracle, produces a 100 % figure that means nothing. That is the
failure this project keeps finding, one layer up, and this document exists to not repeat it.

Two axes are needed, not one, and both are closed enums the author declares against a **generated**
read-key set. The gate checks the declaration against the set; the driver checks the declaration
against the body's behaviour under mutation, per a fixed expected-verdict matrix.

## 2. Axis 1 — the ROLE of each key the body reads

Generated: the set of `get <key>` / `set <key>` / `log:<pattern>` reads a body issues — **from its
transcript when one exists** (exact: the commands the body actually sent on its healthy path), else
from a static walk over the body's reachable source marked `APPROX` (f-string keys unresolved,
listed). Declared: each key's role, from a closed enum of three.

| role | meaning | expected verdict when THIS key is mutated |
|---|---|---|
| `ORACLE` | the read the claim is about | **FAIL, grade ASSERTION** (`lib/canfail.Grade`) |
| `PREMISE` | a precondition the body establishes before asserting | **UNMET or FAIL** — never PASS/SKIP |
| `INCIDENTAL` | read, but the verdict must not depend on it (the R10a control) | **PASS** |

An undeclared key defaults to `INCIDENTAL`, so a forgotten oracle key is caught by the control arm
going FAIL (`OVER-DEPENDENT`), not silently accepted. Every generated key that is not declared is a
census line; a declared key that is not in the generated set is a gate failure (the record names a
read the body does not make).

## 3. Axis 2 — the SHAPE of the oracle, which fixes the mutation operator

The shape is declared **per ORACLE key**. Each shape names exactly one operator and the constraint
that makes the operator necessary; the constraint column is what the plan did not have.

| shape | the body consumes the key by… | operator (host) | constraint it answers |
|---|---|---|---|
| `SNAPSHOT` | one read, compared | `perturb` one field, one occurrence at a time (`Extent.AT`) | a guard over two reads of one key is only moved by perturbing one of them |
| `POLL` | repeated reads until a predicate or a deadline | `freeze` the field at its first recorded value on **every** occurrence, **and run at time dilation ∈ {10, 100, 1000}** — the first dilation at which the control arm still PASSes and the frozen arm FAILs within the recording is the confirmation | **measured 2026-09-08 on the real `T_MA_03`**: freeze alone → miss at occurrence #2 of 2 (void) at dilation 1, 5 and 50; freeze + dilation 100 → **FAIL, 12/12 exchanges, no miss**; healthy control at dilation 100 → PASS. Dilation is the *window elapsing*; no reply is invented |
| `TRANSITION` | read before and after a command; assert a change | `freeze` the after-read(s) to the before value | the second read must not simply be perturbed — a perturbed "after" still differs from "before" |
| `EVENT` | `drain_log_lines(pattern)` must match within a timeout | `delete` matching non-JSON lines from every exchange, plus dilation as for `POLL` | log lines are unkeyed; `Transcript.mutate` rewrites JSON only — a line-level operator is a small addition |
| `ABSENCE` | pass = the pattern does **not** appear (R12) | `insert` one matching line after the body's first command | R12's liveness precondition must also be declared (`PREMISE` on the positive marker) or the id is `UNFALSIFIABLE-ABSENCE` |
| `PHYSICAL` | not reproducible on the host (SD eject, audible output, a real fetch) | none; the record carries the physical perturbation and an **expiry date** enforced like `flaky.yaml`'s `review_by` | PM §4.1 replaced R11's campaign with the expiry; an expired physical falsifier is a gate failure |
| `NONE` | the claim has no observable (R4 `UNOBSERVABLE`) | none; the id may not carry a PASS on any exit criterion | already enforced by `check_no_reachable_fail`'s register check |
| `THRESHOLD` *(TASK-714, 2026-09-19)* | a derived numeric delta between two reads of one key, bounded (`earlier - later [> or abs(...) >] N`) | `perturb_threshold(v, bound)` (`lib/falsify_ops.py`) — moves the LATER occurrence DOWN by more than the declared `bounds[key]` | `SNAPSHOT`'s fixed `+1` cannot cross an arbitrary `N`; `TRANSITION`'s freeze-to-before forces the delta to exactly 0, the tightest possible PASS — the opposite of falsification. `THRESHOLD` is declared **with a bound** (`meta(..., bounds={key: N})`) because no fixed step crosses every possible `N` — see amendment note below |
| `SUBSTRING` *(TASK-714, 2026-09-19)* | one read, tested by prefix/containment (`.startswith(...)`, `x in y`), not bare equality | `scramble_string(v)` (`lib/falsify_ops.py`) — a deterministic character-substitution cipher over the whole string | `SNAPSHOT`'s `perturb_value` appends `"~"`, which changes equality but preserves every prefix and every substring not touching the tail — measured: `"./x".startswith("./")` and `"y" in "y~"` are both still `True` after it |

**Amendment, TASK-714 (2026-09-19).** Declaring the LocalPlayer cohort surfaced three claim shapes
no operator in the (then-)enum could falsify — `T_CLK_11`'s heap-cycle leak and `T_PLR_12`'s
`d_load`/`d_free` budget checks (numeric-threshold), and `T_PLR_08`/`T_PLR_10`/`T_PLR_11`'s
prefix/containment string checks. The two rows above close the first two; the third
(`T_PLR_08`/10/11) is now falsifiable by `SUBSTRING` but was **not declared** by TASK-714 — out of
that task's scope, left for whoever next works the LocalPlayer cohort. Both operators live in a
**new module, `lib/falsify_ops.py`**, not in `lib/canfail.py`: `canfail.perturb_value`/`poison_reply`
are the R34 sweep's shared poison, consumed by two blocking gates
(`check_can_go_red.py`, `check_restore_manager.py`'s runtime arm) whose counts are a ratchet, and
widening them to reach a falsifier-record shape would move both gates' numbers as an unrelated side
effect. `THRESHOLD`'s bound is declared data (`meta(bounds={...})`), checked by
`check_test_meta.py` the same way an `ops` name is checked against `OPS`: an undeclared or
non-positive bound is a gate finding, and so is a `bounds` entry with no matching `THRESHOLD` key.

**A fourth shape, named but deliberately NOT given an operator (TASK-714).** A body whose only
assertion is "the reply said `ok`" cannot be falsified by any reply-field mutation: `ok` is in
`canfail.FRAMING` and is never poisoned, on purpose — poisoning it collapses every poison into
REFUSE, which already exists. This is a **known, deliberate non-target**, not a gap to re-derive:
the failure mode for a `.ok`-only claim is a transport-level "refuse everything" condition, not a
`Transcript.mutate`-shaped reply edit, and it is out of scope for this taxonomy by construction (the
same reasoning `FRAMING`'s own comment in `lib/canfail.py` already gives for why `ok` is excluded).

`freeze` is a **total function**: it defines the reply for every occurrence of the key, including
ones beyond the recording, because "the counter stopped" means every later read says the same
thing. That is the *falsifier's* definition, written in the record and reviewable — not the driver
inventing a reply. **No other key is ever extended.** A miss on an unmutated key stays a void.

## 4. The expected-verdict matrix, and what "confirmed" means

For each id the driver runs: **baseline** (unmutated, must PASS, no miss), then one arm per declared
key. An id is **CONFIRMED** iff every arm lands in its expected cell. Anything else is one of the
named outcomes below — none of which is counted, and all of which are printed with the id.

| arm | expected | PASS | FAIL (assertion) | FAIL (contract/accident/policy) | UNMET/SKIP | miss/void |
|---|---|---|---|---|---|---|
| baseline | PASS | ✓ | `BASELINE-NOT-PASS` | `BASELINE-NOT-PASS` | `BASELINE-NOT-PASS` | `INCONCLUSIVE` |
| ORACLE key | FAIL/assertion | `HOLLOW-ON-KEY` — the verdict ignores its declared oracle | ✓ | `RED-WITHOUT-ASSERTION` | `MISDECLARED` — it is a premise, not the oracle | `INCONCLUSIVE` (§5) |
| PREMISE key | UNMET or FAIL | `PREMISE-IGNORED` | ✓ | ✓ (a crash on a broken premise is still not green) | ✓ | `INCONCLUSIVE` |
| INCIDENTAL key | PASS | ✓ | `OVER-DEPENDENT` (R10a) | `OVER-DEPENDENT` | `OVER-DEPENDENT` | `INCONCLUSIVE` |

The FAIL grade comes from `lib/canfail`'s witness (suite `fail()` vs `BadField` vs crash vs `flake()`
policy) — the same grading the can-go-red gate uses, for the same reason: every body with a typed
read FAILs under a dropped field through `BadField`, and that is not the oracle being falsified.

**AC4's number is the CONFIRMED share over ids with a replayable shape.** `PHYSICAL` ids are counted
separately with their expiry status. `INCONCLUSIVE` is printed with its reason and is never in either
numerator (DEV §4.1 point 2 — the whole reason the engine has `Status`).

## 5. The constraints on host falsification, enumerated

The polled oracle was the first found; these are the rest of its kind, each with its disposition.
**Every one is a property of the body that the driver can only report, not fix.**

| # | constraint | how it shows | disposition |
|---|---|---|---|
| C1 | deadline-bounded poll outruns the recording | miss on the oracle key before any verdict | **solved**: `POLL` shape = freeze + dilation (§3, measured) |
| C2 | count-bounded poll (`for _ in range(N)`) outruns the recording | same, and dilation cannot help — the loop counts, it does not time | `freeze` is total on the mutated key, so the poll is answered; **other** keys inside the loop still miss → `INCONCLUSIVE(re-shape: count-bounded poll)`. The fix is in the body (bound by time, or poll one key) |
| C3 | diagnostics read BEFORE the verdict on the fail path (`_diag_snapshot`: `get heap`/`backoff`/`dataq` folded into the fail reason — T193's shape) | miss before verdict on keys the healthy run never issued | `INCONCLUSIVE(diagnostic-before-verdict)`, printed by name. Fix: record the verdict, then gather diagnostics (the TASK-631 fail ring already carries the last 20 exchanges — the body no longer needs to) |
| C4 | a retrying premise helper (`_switch_to` → `_appid_is`) re-taps when the app is wrong | mutating a PREMISE key makes the body issue more taps than recorded → miss | accepted `INCONCLUSIVE` on the PREMISE arm only; the ORACLE and INCIDENTAL arms still run. Reported as `premise-arm-void`, not as confirmation |
| C5 | the verdict depends on host elapsed time (an oracle that reads `time.monotonic()`, or a bound measured in host seconds) | `INCONCLUSIVE(time-dependent)` from the engine's dilation-0 probe | R1 violation — the claim about time must read a device timestamp. The id is a finding, not a falsification candidate |
| C6 | teardown after the verdict is path-dependent (restore on the FAIL branch) | tail miss | already handled: `tail_miss` flag, `strict_tail` for a driver that wants full coverage |
| C7 | the body records verdicts for more than one id, or a helper records for the caller | witness grades the wrong id | the witness filters by id (`canfail._grade`); a body that never records for its own id is `NO_VERDICT` (engine) |
| C8 | the oracle is a derived quantity of several keys (`a != b` across two keys) | perturbing all at once cancels | `Extent.AT` per key; each ORACLE key must falsify on its own or the record names the pair as one oracle with a `pair` operator (perturb one side) |
| C9 | interactive ids (`input()`) | `INCONCLUSIVE(interactive)` | `PHYSICAL` by construction (T093/T094/T095, already registry `None`s) |

## 6. What this deliberately does not claim

* **It does not grade the oracle.** `set x 5; get x == 5` declares `x: ORACLE/SNAPSHOT`, falsifies
  cleanly and is CONFIRMED. R2's gate (`set X … get X` with no interposed command) owns that
  shape; R1's vocabulary judgement stays by-review and uncounted (PM §4.1). Falsifiability is
  necessary, not sufficient — the requirements say so and this design does not pretend otherwise.
* **It does not say the firmware would produce the recorded replies.** The ELF-stamp refusal in
  `replay_test` stays ON for the falsification job (unlike the can-go-red gate, and for the reason
  written in [runtime-gates §2.3](M-HARNESS2-runtime-gates.md)).
* **Dilation is not free of assumptions.** It asserts the body's *timing* logic is what it says
  (deadline-bounded). A body whose predicate is satisfied by the *passage of time itself* would PASS
  under dilation for the wrong reason — that is C5, and the engine's own probe flags it.

## 7. Declaration form

Extends `_meta.meta()` (TASK-570); everything else in the record is unchanged.

```python
@meta(oracle={"lastPlaylistDraw.ms": "POLL"},          # key[.field] -> shape
      premise={"appId", "shellCooldown", "tbScrollOffset"})
      # no falsifier= — this oracle's only shape is POLL, which has a host
      # operator (§3), so check_test_meta.py DERIVES falsifier="replay".
      # falsifier= is typed ONLY for "physical: <what>; expires 2026-12-01" —
      # see the TASK-642 amendment below.
def t_ma_03(dut): ...
```

`gate/check_test_meta.py` gains three arms: the shape and role vocabularies are closed; every
`ORACLE` key exists in the generated read set; a `physical` falsifier carries an unexpired ISO date.
The generated set is `gen/gen_read_keys.py` → `app/gen/read_keys.py`, transcript-first, static
`APPROX` fallback — the same staleness-gated shape as `gen_app_registry.py`.

**Amendment, TASK-642 (2026-09-19).** `falsifier="replay"` is no longer typed by the author — it is
DERIVED from the id's declared oracle shapes, in `suite/serialdbg/_meta.py`'s `derive_falsifier()`.

> **Derivation rule.** An id with at least one declared `ORACLE` key, none of whose shapes is
> `PHYSICAL` or `NONE`, is replay-falsifiable: `_meta.resolve()` sets its `falsifier` to `"replay"`
> with no author action. An id with no oracle at all, or with any oracle key shaped `PHYSICAL` or
> `NONE`, derives nothing — `falsifier` stays whatever was hand-typed (a `"physical: <what>;
> expires <ISO date>"` string), or `None`.
>
> The rule follows directly from §3's own table: every shape but two — `SNAPSHOT`, `POLL`,
> `TRANSITION`, `EVENT`, `ABSENCE`, `THRESHOLD`, `SUBSTRING` — already names a host mutation
> operator, which is the entire content of "replay-falsifiable". `PHYSICAL` (not reproducible on the
> host) and `NONE` (no PASS to falsify) are the two shapes with no operator, so they are the two
> exclusions. A hand-typed `falsifier="replay"` can therefore only ever DISAGREE with what the
> shapes already say (typed on an id the shapes say isn't replayable) or RESTATE it (typed on an id
> that was going to derive it anyway) — never add information a reader could not already get from
> the shapes. `gate/check_test_meta.py`'s `evaluate_falsifiers()` now rejects a hand-typed `"replay"`
> outright, in both directions, via the record's own `falsifier_typed` field (what the author wrote,
> `None` when nothing was) — kept distinct from `falsifier` (the effective value: typed, or derived)
> and `falsifier_derived` (whether this id's value came from the rule above), so a reader of
> `build_all_meta()` can tell a derived value from a typed one without re-deriving it by hand.
>
> `physical: <what>; expires <ISO date>` is unaffected: still hand-typed (there is no shape data
> that could derive an expiry date), still checked against `_PHYSICAL_RE` and the expiry rule
> exactly as filed, and never reported as the "replay" redundancy above.
>
> The 33 ids declared under TASK-641 (11 in Clock, 22 in LocalPlayer including `T_PMT_03`) were
> migrated: their
> `falsifier="replay"` argument was removed and the shapes now speak for themselves. `check_test_meta.py`'s
> census line still counts 33 ids with a falsifier — now split into "derived" vs. "hand-typed
> physical" so the count's provenance is visible in the run log, not just the total.

## 8. What changes in the three rows

| row | as filed | amended scope |
|---|---|---|
| TASK-641 | generate the read-key set; author declares a claim class from a closed enum | the key set is transcript-first (exact) with a static `APPROX` fallback; **two** closed enums, role (§2) and shape (§3), not one |
| TASK-642 | two-field falsifier: executable replay, and physical with enforced expiry | **done, 2026-09-19.** Unchanged in intent; the replay half is *derived* from the declared shapes (`_meta.derive_falsifier()`, boxed rule above), never typed as a field — a hand-typed `"replay"` is now a `check_test_meta.py` finding in both directions (disagrees with the shapes, or merely restates them); `physical: ...` stays typed and its expiry enforced exactly as filed. The 33 TASK-641 declarations were migrated; `gate/test_check_test_meta.py` gained 5 arms (F20-F24) pinning both directions |
| TASK-643 | mutation driver with the control arm; a miss is inconclusive | the driver runs the §4 matrix (baseline + one arm per declared key), needs a `dilation` parameter on `replay_test` and a line-level operator for `EVENT`/`ABSENCE`, and prints the §5 constraint by name on every `INCONCLUSIVE`. The recorded set is its ratchet (as `lib/replay.py` already says) |

Start with LocalPlayer and Clock (DEV §4.4's ~35 ids) once transcripts exist; the first recording
is TASK-671's owed step and both efforts share it.

## 9. Evidence

`app/tools/spike/task641_poll_dilation.py` reproduces the §3 measurement host-only, from the
`test_replay.py` fixture, in about a second. It is the one number in this document that was run
rather than reasoned, and it is the one that changes the taxonomy.
