#!/usr/bin/env python3
"""check_flake_class.py — a gating-class id may not carry a flake declaration.
TASK-623 / M-HARNESS2 R37.

THE CONTRADICTION. RIG, HEALTH and CORE exist to stop a run: a failure in one of
them says nothing above it is trustworthy. The flake policy exists to absorb a
non-deterministic result: a declared flake is retried once and, if the retry
passes, is recorded `FLAKY-PASS` — its own bucket, which `lib/results.py` is
careful to make neither a PASS nor a FAIL.

Put those two together on one id and the id gates nothing. WP-C found the live
instance: **T091** routes every exit through `flake()` and is declared in
`flaky.yaml`, so its best case is `FLAKY-PASS` and its worst case is a FAIL that
only appears if the flake reproduces. It resolves to CORE (seeded from its
`spotify-chrome` scope), which means that under the class-order switch it holds a
veto over 167 FEATURE ids that it can essentially never exercise.

The rule is therefore: **an id whose class can block is either reliable or it is
demoted.** It is never both blocking and excused.

WHAT IT ASSERTS

  F1  no DECLARED flake resolves to RIG, HEALTH or CORE.
      **At zero since 2026-09-04 (TASK-591).** It landed BLOCKING with a dated,
      shrink-only ledger holding exactly one row — T091 — on the reasoning that
      an advisory finding is scrolled past (`check_docs` C3 is this repo's
      standing proof). TASK-591 then declared T091's class: no CORE sentence
      could honestly be written for it, so it is FEATURE, the contradiction is
      gone, and `docs/verification/flake_class_exceptions.md` was DELETED per
      its own retirement rule. The gate is now blocking at zero with no ledger
      at all, which is the state F2 and F3 have always been in.

  F5  no exemption ledger exists holding zero rows. The ledger's own rule is
      that the file is deleted when its last row is; a file left behind with an
      empty table is a retirement somebody stopped halfway, and it is the shape
      an amnesty grows back from — an empty exemption list is an invitation to
      open a row. **Zero today, because the file is gone.**

  F2  no flake CANDIDATE resolves to a gating class. A candidate is a proposal
      to create the contradiction, and promoting one is how F1 would grow.
      **Zero today**, so it is blocking at zero with no ledger.

  F3  every declared flake and candidate names an id that some registry
      actually contains. An entry for an id nothing dispatches can never be
      honoured — and it fails silently, because `lib/results.py` consults the
      registry only when `flake()` is called. **Zero today.**

  F4  no ledger row is stale. When an exempted id stops producing its finding
      the row must go; that is what makes the list shrink-only.

WHAT IT DELIBERATELY DOES NOT ASSERT. WP-C's finding has a second half — that
T091's *body* routes every exit through `flake()`, so it can never reach a
`pass_()`. That is a body-shape question, it is the same AST walk as "no
reachable `fail()`", and it belongs to TASK-603 / R34. Duplicating half of it
here would give two gates a shared, drifting notion of what a body contains.

No DUT, no build, no network. Sub-second.

    python3 app/tools/gate/check_flake_class.py [--verbose]
"""

from __future__ import annotations

import datetime
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))
sys.path.insert(0, TOOLS)

from lib import flaky as _flaky                          # noqa: E402
import suite.serialdbg as _suite                         # noqa: E402

from suite.serialdbg import _meta, _order                # noqa: E402

#: The classes that can block, DERIVED from the shipped dispatch constants
#: rather than typed here (LL-114 / R42: no firmware or harness fact is
#: mirrored). `_order.CORE_BLOCKS` names what a CORE failure invalidates, so its
#: complement over `_meta.CLASSES` is the set of classes that hold a veto:
#: today RIG, HEALTH, CORE — exactly R37's wording. APP is in CORE_BLOCKS and
#: is empty besides (`B-12`), so it is correctly not gating.
#:
#: `test_check_flake_class.py` pins this to the expected triple, so if the
#: ladder ever gains a blocking class the derivation fails loudly here instead
#: of silently narrowing what this gate covers.
GATING = tuple(c for c in _meta.CLASSES if c not in _order.CORE_BLOCKS)

LEDGER_REL = "docs/verification/flake_class_exceptions.md"

#: Only F1 is exemptable. F2 and F3 are at zero today, so there is nothing to
#: grandfather, and an exemption kind with no rows is an invitation.
EXEMPTABLE = ("gating-flake",)

_TASK_RE = re.compile(r"^TASK-\d+$")
_SEP_RE = re.compile(r":?-{2,}:?")


def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_ledger(path: str = None) -> tuple:
    """-> ({(kind, id): 'rel:line'}, [errors]).

    Same shape and same rules as the C6 ledger (`check_docs.py:_parse_ledger`):
    keyed on `(kind, id)`, an owning TASK id and an ISO `since` date required,
    no wildcards of any sort.

    AN ABSENT FILE IS THE STEADY STATE, AND IT FAILS CLOSED (TASK-591). Since
    T091's demotion there is nothing to exempt, so the file is gone. Absent
    parses to zero rows, which grandfathers nothing: if a gating flake is ever
    declared again, `evaluate` finds it unexempted and the gate goes red. That
    is the whole safety property — the check does not need its ledger to be
    strict, only to be lenient, so losing the file can only make it stricter.

    An EXISTING file holding zero rows is different, and is F5: the ledger's own
    retirement rule says the file is deleted when its last row is, so an empty
    table is a half-finished retirement and the shape an amnesty regrows from.
    """
    path = path or os.path.join(ROOT, LEDGER_REL)
    rows: dict = {}
    errors: list = []
    if not os.path.exists(path):
        return rows, errors
    exists = True
    rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
    header = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().split("\n")
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if not s.startswith("|"):
            header = None
            continue
        cells = _cells(s)
        if all(_SEP_RE.fullmatch(x) for x in cells if x):
            continue
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if len(cells) < 5:
            continue
        tid, kind, _why, owner, since = cells[0].strip("`* "), cells[1], cells[2], cells[3], cells[4]
        if kind not in EXEMPTABLE:
            errors.append(f"{rel}:{i}: kind {kind!r} is not exemptable "
                          f"(allowed: {', '.join(EXEMPTABLE)})")
            continue
        if not _TASK_RE.match(owner.strip("`* ")):
            errors.append(f"{rel}:{i}: owner {owner!r} must be a TASK-NNN id")
            continue
        try:
            datetime.date.fromisoformat(since.strip("`* "))
        except ValueError:
            errors.append(f"{rel}:{i}: since {since!r} is not an ISO YYYY-MM-DD date")
            continue
        rows[(kind, tid)] = f"{rel}:{i}"
    if exists and not rows and not errors:
        errors.append(
            f"F5 {rel}: the exemption ledger exists but holds no rows — its own "
            f"retirement rule is that the file is deleted when its last row is. "
            f"An empty exemption list is where the next amnesty starts. Delete "
            f"the file")
    return rows, errors


def evaluate(declared, candidates, meta, ledger=None) -> list:
    """Pure: the findings, so the negative suite can drive it with fixtures.

    `declared` / `candidates` are id -> anything; `meta` is id -> record;
    `ledger` is the parsed `{(kind, id): where}` mapping.
    """
    ledger = dict(ledger or {})
    out: list = []
    used: set = set()

    for tid in sorted(declared):
        rec = meta.get(tid)
        if rec is None:
            out.append(f"F3 {tid}: declared flaky but no registry contains it — the "
                       f"declaration can never be honoured and fails silently, "
                       f"because results.flake() only reads the registry when a "
                       f"body calls it")
            continue
        cls = rec.get("cls")
        if cls in GATING:
            key = ("gating-flake", tid)
            if key in ledger:
                used.add(key)
                continue
            how = "declared" if rec.get("cls_declared") else "seeded"
            out.append(
                f"F1 {tid}: class {cls} ({how}) carries a flake declaration — a "
                f"gating id whose retry resolves FLAKY-PASS is neither a PASS nor "
                f"a FAIL, so it can never set the blocker its class exists to set. "
                f"Fix it or demote it out of {cls}; do not exempt it twice")

    for tid in sorted(candidates):
        rec = meta.get(tid)
        if rec is None:
            out.append(f"F3 {tid}: listed as a flake candidate but no registry "
                       f"contains it")
            continue
        if rec.get("cls") in GATING:
            out.append(f"F2 {tid}: a flake candidate on gating class "
                       f"{rec['cls']} — promoting it would create the F1 "
                       f"contradiction; measure it and fix it, or demote it first")

    for key, where in sorted(ledger.items()):
        if key not in used:
            out.append(f"F4 {where}: stale exception for {key[1]} ({key[0]}) — the "
                       f"finding it suppresses no longer occurs; delete this row. "
                       f"The ledger can only shrink")
    return out


def main(argv) -> int:
    verbose = "--verbose" in argv
    reg, err = _flaky.get_registry()
    if err is not None:
        print(f"FAIL: the declared flaky set is unreadable ({err}) — failing "
              f"closed, exactly as lib/results.flake() does")
        return 1
    meta = _suite.build_all_meta()
    ledger, ledger_errors = parse_ledger()
    findings = evaluate(reg.entries, reg.candidates, meta, ledger) + ledger_errors

    gating_ids = sorted(t for t, r in meta.items() if r.get("cls") in GATING)
    print(f"check_flake_class: {len(reg.entries)} declared flake(s), "
          f"{len(reg.candidates)} candidate(s), against {len(gating_ids)} gating "
          f"ids ({'/'.join(GATING)}) in a {len(meta)}-id registry; "
          f"{len(ledger)} ledger row(s)"
          + ("" if os.path.exists(os.path.join(ROOT, LEDGER_REL))
             else f" (no ledger file — retired 2026-09-04, TASK-591)"))
    if verbose:
        for tid in sorted(reg.entries):
            rec = meta.get(tid) or {}
            print(f"    {tid}: cls={rec.get('cls', '<not registered>')}")

    if findings:
        print(f"\nFAIL: {len(findings)} finding(s)")
        for f in findings:
            print(f"  {f}")
        return 1
    print("  PASS  no gating-class id is excused by the flake policy")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
