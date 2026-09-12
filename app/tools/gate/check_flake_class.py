#!/usr/bin/env python3
"""check_flake_class.py — a gating-class id may not carry a flake declaration,
and the registry must agree with its call sites. TASK-623 / M-HARNESS2 R37,
extended by TASK-595 / R-C7 (F6/F7/F8 below).

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

  F6  every DECLARED flake (`flaky:`, not `candidates:`) has at least one real
      `flake(<its own id>, ...)` call site somewhere under `suite/serialdbg/`.
      A declaration with no call site does nothing: the id can only ever go
      PASS or FAIL, `run_with_flake_retry` is never invoked for it, and the
      owner/task/`review_by` bookkeeping is dead weight. Reference cases
      (TASK-595 / C-7): `T_PLR_17`, `T_PMT_04`, `T_WR_COEX_01` were declared
      while their bodies used a plain `fail()`.

  F7  every real `flake(<id>, ...)` call site names an id that is DECLARED.
      `lib/results.flake()` already fails closed on this at runtime (`FAIL:
      UNDECLARED flake — no entry for <id> in flaky.yaml`) — this is that same
      rule caught at review time instead of on a DUT, host-side, before the
      real symptom the call site meant to report gets buried behind a
      bookkeeping message. Reference cases (TASK-595 / C-7, hardware-confirmed
      on two separate M-TESTQUAL sessions): `T084`, `T092`, `T_PLR_07`,
      `T_WR_EJECT_01`.

  F8  no DECLARED entry's `review_by` has passed. flaky.yaml's own rule 3: "an
      entry past its review date is a FAIL until re-justified" — `lib/flaky.py`
      enforces this at the individual `flake()` call (EXPIRED behaves exactly
      like UNDECLARED), but nothing previously caught a stale date at review
      time, before a DUT run was needed to surface it.

WHAT F6/F7 DELIBERATELY DO NOT ASSERT. Presence, not reachability. F6/F7 are a
literal `ast.Call` scan for `flake("SOME_ID", ...)` across the suite source —
they answer "does a real call site for this id exist anywhere", not "is every
exit of this id's body accounted for" or "can this body ever reach a
`fail()`". The latter is a full reachability/swallowing-fixpoint analysis that
already exists, over the same kind of AST, in `check_no_reachable_fail.py`
(TASK-603 / R34) — duplicating it here would give two gates a shared, drifting
notion of what a body contains. A docstring or a `cls_reason` string that
merely *mentions* `flake()` in prose is not a call site: F6/F7 only count an
`ast.Call` node whose callee is literally named `flake`, so comment text can
never produce a false match.

No DUT, no build, no network. Sub-second.

    python3 app/tools/gate/check_flake_class.py [--verbose]
"""

from __future__ import annotations

import ast
import datetime
import glob
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

#: F1 and F7 are exemptable. F2/F3/F6/F8 are at zero today (F6 fixed outright
#: by TASK-595's sweep; F8 has no expired entry today), so there is nothing to
#: grandfather for them, and an exemption kind with no rows is an invitation.
EXEMPTABLE = ("gating-flake", "undeclared-flake-call")

SUITE_DIR_REL = "app/tools/suite/serialdbg"


def flake_call_sites(suite_dir: str = None) -> dict:
    """-> {tid: ["rel/path.py:line", ...]}, one entry per literal-string id
    passed as the first argument of a real `flake(...)` call, scanned across
    every `*.py` under `suite/serialdbg/`.

    AST-based, not text/regex: only an `ast.Call` node whose callee is the bare
    name `flake` counts, and only when its first argument is a string
    constant. A `cls_reason` paragraph that writes "the body calls `flake()`"
    in prose is not a `Call` node and can never match. A file that fails to
    parse is skipped, not fatal — `check_test_meta.py`/`build_all_meta()` will
    already have failed loudly on a syntax error elsewhere in `run/check`.
    """
    suite_dir = suite_dir or os.path.join(ROOT, SUITE_DIR_REL)
    sites: dict = {}
    for path in sorted(glob.glob(os.path.join(suite_dir, "*.py"))):
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        try:
            src = open(path, encoding="utf-8").read()
            tree = ast.parse(src, filename=path)
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else None
            if name != "flake":
                continue
            if not node.args:
                continue
            arg0 = node.args[0]
            if not (isinstance(arg0, ast.Constant) and isinstance(arg0.value, str)):
                continue
            sites.setdefault(arg0.value, []).append(f"{rel}:{node.lineno}")
    return sites

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


def evaluate(declared, candidates, meta, ledger=None, call_sites=None, today=None) -> list:
    """Pure: the findings, so the negative suite can drive it with fixtures.

    `declared` / `candidates` are id -> anything; `meta` is id -> record;
    `ledger` is the parsed `{(kind, id): where}` mapping.

    `call_sites` (id -> [site, ...]) and `today` are both OPT-IN: passing
    `None` (the default) skips F6/F7/F8 entirely, so every pre-existing
    fixture that drives `declared`/`candidates` with a bare sentinel (no
    `review_by`, no call-site fixture) keeps working unmodified — this method
    was extended in place (TASK-595), not forked. F8 additionally only fires
    for a `declared` value that actually carries `.review_by` (a real
    `FlakyEntry`, via `is_expired()`); a fixture sentinel without one is
    silently exempt from F8, never a crash.
    """
    ledger = dict(ledger or {})
    out: list = []
    used: set = set()

    for tid in sorted(declared):
        entry = declared[tid]
        if today is not None and hasattr(entry, "is_expired") and entry.is_expired(today):
            days = (today - entry.review_by).days
            out.append(
                f"F8 {tid}: review_by {entry.review_by} passed {days} day(s) ago "
                f"(owner {entry.owner}, {entry.task}) — rule 3: an entry past its "
                f"review date is a FAIL until re-justified. Bump review_by with a "
                f"fresh justification or DELETE the entry")
        if call_sites is not None and tid not in call_sites:
            out.append(
                f"F6 {tid}: declared in flaky.yaml but no `flake({tid!r}, ...)` "
                f"call site exists anywhere under {SUITE_DIR_REL}/ — the "
                f"declaration does nothing (run_with_flake_retry is never invoked "
                f"for it); REMOVE the entry, or make the body call flake() where "
                f"the claimed symptom actually occurs")
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

    if call_sites is not None:
        for tid in sorted(call_sites):
            if tid in declared:
                continue
            key = ("undeclared-flake-call", tid)
            if key in ledger:
                used.add(key)
                continue
            sites = ", ".join(call_sites[tid])
            out.append(
                f"F7 {tid}: flake() called at {sites} for an id not declared in "
                f"flaky.yaml — lib/results.flake() already converts every one of "
                f"these calls to 'FAIL: UNDECLARED flake', which reports a "
                f"bookkeeping problem instead of the real symptom the call site "
                f"names. ADD a declaration (owner + task + review_by), or stop "
                f"calling flake() there and let the id fail() properly")

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
    call_sites = flake_call_sites()
    today = datetime.date.today()
    findings = evaluate(reg.entries, reg.candidates, meta, ledger,
                        call_sites=call_sites, today=today) + ledger_errors

    gating_ids = sorted(t for t, r in meta.items() if r.get("cls") in GATING)
    print(f"check_flake_class: {len(reg.entries)} declared flake(s), "
          f"{len(reg.candidates)} candidate(s), against {len(gating_ids)} gating "
          f"ids ({'/'.join(GATING)}) in a {len(meta)}-id registry; "
          f"{len(ledger)} ledger row(s); {len(call_sites)} distinct id(s) with a "
          f"real flake() call site under {SUITE_DIR_REL}/"
          + ("" if os.path.exists(os.path.join(ROOT, LEDGER_REL))
             else f" (no ledger file — retired 2026-09-04, TASK-591)"))
    if verbose:
        for tid in sorted(reg.entries):
            rec = meta.get(tid) or {}
            print(f"    {tid}: cls={rec.get('cls', '<not registered>')} "
                  f"call_sites={call_sites.get(tid, [])}")

    if findings:
        print(f"\nFAIL: {len(findings)} finding(s)")
        for f in findings:
            print(f"  {f}")
        return 1
    print("  PASS  no gating-class id is excused, and the registry agrees with "
          "its call sites in both directions, with no expired entry")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
