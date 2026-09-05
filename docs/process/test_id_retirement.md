# Retiring a test id — the procedure

> Owner: **@VE** · Board row: [TASK-625](../project/tasks-harness2.md) · Written 2026-09-05
> Governs every removal of a test id from the executable corpus, whichever of the two
> dispositions applies. Machine-checked by `run/check-docs` (C6) and by
> `app/tools/gate/check_no_reachable_fail.py` (R34).

---

## 0. Why this file exists at all

Deleting a test looks like deleting a function. It is not. A test id is a **claim about the
product** that is asserted in five places at once, and only one of them is code:

| where the id lives | what it says there | what happens if you skip it |
|---|---|---|
| the family `TESTS` dict in `app/tools/suite/serialdbg/` | "this id has an executable body" | the id keeps running, or keeps costing suite time |
| the body itself | the assertion | a live body under a retirement record prints green — this is `H-2`'s exact mechanism |
| `docs/verification/test_plan.md` | the binding (`impl` / `resv` / `blocked`) and often a status | C6.3 fires (`impl` with no registry) — **or**, far worse, does not fire (see §0.1) |
| `docs/verification/test_plan-archive.md` and `regression_suite/*.md` | a **historical status**, frequently `pass` | the corpus keeps asserting a pass for a test that no longer exists |
| `docs/verification/id_binding_exceptions.md` | a C6 exemption for a finding about the id | the row goes stale, and a stale row is a blocking failure |

A retirement that touches only the first two is not a retirement. It is a **disappearance**, and
the corpus is left louder than before: fewer tests, same number of green claims.

### 0.1 The worked example — the failure mode that sets the order

`T136` is the case that produced this document. Its body is one unconditional
`skip("T136", "merged into T137 precondition — run T137")`. Deleting it is uncontroversial.

Now trace what C6 does if you delete the registry entry and the body, and nothing else.

* C6.1 (**orphan**) looks for registry ids with no doc entry. `T136` is no longer in a registry,
  so C6.1 never considers it. **Silent.**
* C6.2 (**undeclared**) looks for doc entries that declare no status. `T136`'s only surviving plan
  declaration is `docs/verification/test_plan-archive.md:1453`, and it declares one:
  `- **Status**: **pass** (2026-05-23); … **pass** (2026-05-24 re-run post-fix …)`. **Silent.**
* C6.3 (**mismatch**) is the one check that admits no exceptions — and it only acts on the three
  *binding* tokens `impl` / `resv` / `blocked`, matched at the **start** of the status text
  (`check_docs.py:563`, `check_docs.py:761-774`). `**pass**` is not one of them. **Silent.**
* `test_plan-archive.md` is **not** in `check_docs.EXEMPT_BASENAMES` (`check_docs.py:63`), so it is
  scanned like any other file under `docs/verification/` and its rows are full-weight status
  declarations, not history.

All three sub-checks pass. `run/check-docs` prints green. And the only surviving statement the
project makes about `T136` is that it **passed a re-run** — for a test that no longer exists and
cannot be re-run. That is `D-4` one layer down: not a body that cannot fail, but a *record* that
cannot fail.

**The order matters because the gate cannot see the mistake.** There is no check that will tell you
later. The archive row must be corrected in the same commit as the deletion, or it is never
corrected — which is why §2 makes it part of the definition of done rather than a follow-up.

---

## 1. The two dispositions, and how to choose

There is exactly one axis: **is the claim still true and still wanted?**

| | **DELETE** | **UNOBSERVABLE** |
|---|---|---|
| the claim | is not a claim the project holds — it was unrepresentable, a tautology, or it moved into another id | is real, is wanted, and **cannot be observed today** |
| the body | deleted | **deleted** — this is not optional, see §1.1 |
| the record | a row in [`retired_test_ids.md`](../verification/retired_test_ids.md), disposition `deleted` | a row in the same file, disposition `UNOBSERVABLE`, **with an owning task** |
| may a milestone criterion resting on it read PASS? | the criterion should not rest on it at all — re-word it | **no.** It reads `DEFERRED`, `open`, or `UNOBSERVABLE`; never PASS |
| what re-opens it | nothing. A new id, if the claim comes back | the owning task landing the observable, then a **new** body under the same id |

Two rules that are not obvious:

**1.1 An `UNOBSERVABLE` record with a live body is a gate failure, not a ledger row.** This is the
whole point of R4. A record that says "we cannot see this" sitting above a body that prints green
every run is the mechanism by which five M-CLOCK-STYLES exit criteria were booked as PASS. The R34
gate asserts the negative directly: no id in `build_all_tests()` may appear in the `UNOBSERVABLE`
half of the register.

**1.2 "Re-file as a new id" is not a disposition.** If the claim is real and a *different* test
would hold it, that is a DELETE plus a new id in a named task. Do not keep the old id alive as a
placeholder for the test somebody intends to write: the id is what the plan counts.

---

## 2. The procedure — DELETE

Do these in order. Steps 1–6 are one commit; a partial application is the defect this document
exists to prevent.

**Step 1 — record it first.** Add the row to `docs/verification/retired_test_ids.md` *before*
touching any code. The register is the thing that survives; if the run is interrupted after the
body is gone and before the record is written, the id has vanished with no trace. Row fields: id,
disposition, date, the reason in one line, the evidence line that makes the reason checkable, and
what coverage is lost — stated concretely, `none` where that is the honest answer.

**Step 2 — delete the body**, and any helper that becomes unreferenced by its deletion. Check for
helpers shared with surviving ids before removing one (`grep` the family module).

**Step 3 — delete the registry entry** from the family module's `TESTS` dict (and its
`META_OVERRIDES` entry, if any — `check_test_meta.py` fails on a `META_OVERRIDES` key that is not in
`TESTS`).

**Step 4 — sweep the machine-read satellites.** Each of these is keyed by test id and each fails
its own gate on a dangling key:

* `app/tools/suite/serialdbg/_order.py` — `EDGE_ADJUDICATION`. A deleted id's adjudication row must
  go. `test_class_order.py` stays green as `unadjudicated()` shrinks; the row itself is dead data.
* `docs/verification/flaky.yaml` — a flake declaration for a deleted id is checked by
  `check_flake_class.py`.
* `docs/verification/gating_class_declarations.md` — R35's ledger; a row for a deleted id is stale.
* `docs/verification/id_binding_exceptions.md` — C6's ledger. **A stale row here is a blocking
  failure by design**, so this one will announce itself; it is listed so it is not a surprise.
* `run/` scripts and `regression_suite/*.md` re-run command lines that name the id explicitly.

**Step 5 — correct every plan declaration.** This is the step §0.1 is about. Enumerate them
mechanically, do not rely on memory:

```sh
grep -rn '\bT_ID_HERE\b' docs/verification/
```

For each hit, apply the rule for its kind:

| the declaration | what it must become |
|---|---|
| a `test_plan.md` table row with binding `impl` | binding **`resv`** is wrong (it means "specified, not built"). Replace the binding cell with `retired` and point at the register. `retired` matches none of C6.3's three tokens, so it binds cleanly and reads honestly. |
| a `### T_ID — …` entry with `- **Status**: pass` | `- **Status**: retired 2026-MM-DD (TASK-NNN) — see [retired_test_ids.md](…)`. **Never leave a pass.** |
| an archive row with a historical status | the same. The archive is scanned, not exempt. Keep the history; append the retirement so the *last* thing said is the true one. |
| a `regression_suite/*.md` coverage table cell reading `PASS` | `retired` (DELETE) or `UNOBSERVABLE` (§3). A `-review.md` file is exempt from scanning and may be left alone. |
| a milestone exit-criterion row whose evidence is this id | re-word the criterion, or mark it `DEFERRED` with the owning task. Never leave a criterion whose only support has been deleted. |

**Step 6 — run both gates.** `./run/check-docs` and `./run/check`. C6's summary line prints
`N registry ids, M doc ids, K bound` — the registry count must have dropped by exactly the number
of ids deleted, and `unexcepted` must still read 0.

**Step 7 — report the id count.** `len(build_all_tests())` before and after. One number, so the
deletion is auditable without reading the diff.

---

## 3. The procedure — UNOBSERVABLE

Identical to §2 with three differences:

* **Step 1's row** carries disposition `UNOBSERVABLE`, an **owning TASK- id that is not archived**,
  and a one-line statement of *what would make it observable*. A row with no owner is not a
  deferral, it is a deletion with better manners.
* **Step 5's plan rows** become `UNOBSERVABLE (since 2026-MM-DD, TASK-NNN)`, not `retired`. Any
  milestone criterion resting on the id is re-recorded `DEFERRED` in the same commit — the criterion
  is the thing that was reading PASS, and it is the reason this disposition exists.
* **The body is still deleted** (§1.1). The register row is the coverage record; the body is not.

---

## 4. What the two gates enforce, and what neither can

| | enforced by | not enforced |
|---|---|---|
| a deleted id does not keep running | trivially — it is not in `TESTS` | — |
| an `UNOBSERVABLE` id has no live body | **R34**, `check_no_reachable_fail.py` | — |
| the register's rows are dated and task-owned | **R34** (its own rows) and review | — |
| an `impl` binding with no registry entry | **C6.3**, no exceptions | — |
| **a stale `pass` left behind by a deletion** | *nothing* | **§0.1 — this is the hole.** No gate can distinguish a historical pass from an abandoned one, because both are true statements about the past. The only defence is Step 5 in the same commit. |

That last row is the reason this is a procedure and not a checker. Everything mechanically
checkable is already checked; what remains is an ordering discipline, and ordering disciplines live
in `docs/process/`.

---

## 5. Cross-references

* [`docs/verification/retired_test_ids.md`](../verification/retired_test_ids.md) — the register.
* [`docs/verification/no_reachable_fail_ledger.md`](../verification/no_reachable_fail_ledger.md) —
  R34's own shrink-only exception ledger.
* [`docs/verification/M-HARNESS2-task603-disposition.md`](../verification/M-HARNESS2-task603-disposition.md)
  — the disposition of the first 35 ids this procedure was applied to.
* [`docs/verification/id_binding_exceptions.md`](../verification/id_binding_exceptions.md) — C6's ledger.
