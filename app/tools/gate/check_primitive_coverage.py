#!/usr/bin/env python3
"""check_primitive_coverage.py — every op in the OPS vocabulary is exercised by
a PRIMITIVE test, or is on a dated, owned, shrink-only ledger. TASK-705.

WHY THIS EXISTS. TASK-697's reboot/inject/Stock wedge investigation
(docs/verification/regression_suite/task697-reboot-inject-stock.md) produced a
read-only coverage inventory of nine PRIMITIVE OPERATIONS along the failing
composite's causal chain — a reboot, Spotify's backoff schedule, its token
refresh, dataTask's TLS yield hand-off (idle and busy), a PlaneRadar injection
and its clear, dataTask's cross-app queue, and a Stock quote fetch. Several of
those operations had no id that tested them ALONE: a composite FAILing said
nothing about which of its several operations broke. `suite/serialdbg/_meta.py`
carries the vocabulary (`OPS`) and an opt-in `ops` declaration
(`@meta(ops=(...))`); this gate is what keeps the declaration honest.

WHAT IT ASSERTS, over `suite.serialdbg.build_all_meta()`'s `ops` field:

  P1  an op in `OPS` with no id declaring EXACTLY that one op (a PRIMITIVE —
      `ops == (that_op,)`), unless the op has a row on the dated,
      owned, shrink-only ledger `docs/verification/primitive_coverage_exceptions.md`.
      A row whose finding no longer fires is itself a failure (the ledger only
      shrinks) — same rule as `gate/check_gating_offline.py`'s R36 ledger.
  P2  an id declares an op NOT in `OPS` (a typo, or a vocabulary the id's
      author invented instead of adding a row to `_meta.OPS`).
  P3  a COMPOSITE (an id declaring 2+ ops) uses an op that has neither a
      primitive nor a ledger row — the composite's own coverage does not
      excuse the primitive gap; if anything it is the reason the gap was
      found in the first place (TASK-697's own case).

Undeclared ids (ops == ()) are counted and printed, never a finding — `ops` is
opt-in and most ids exercise nothing in the closed vocabulary.

LEDGER SHAPE. Unlike `gating_offline_exceptions.md` (keyed on `(kind, id)`) this
ledger is keyed on the OP ALONE — an op is either drivable today or it is not,
and that is not a per-id fact. Each row: `op | why | owner (TASK-NNN) | since
(ISO date)`. TASK-705 opened it with exactly one row: `spotify_token_refresh_fail`
(NOT DRIVABLE — `cmdSet.cpp`'s certbreak table excludes spotifyTask), owner
TASK-675 (the live cert-pin-rot instance of the failure).

No DUT, no build, no network. Run directly, or via app/tools/smoke_test.sh.

    python3 app/tools/gate/check_primitive_coverage.py [--verbose]
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))
sys.path.insert(0, TOOLS)

from suite.serialdbg import _meta                     # noqa: E402

LEDGER_REL = "docs/verification/primitive_coverage_exceptions.md"

#: Ops whose primitive assertion is the HARNESS ITSELF, not a suite id.
#: `reboot_ready` is the one case (TASK-705): every DUT session — not just a
#: [REBOOT] test's post-reboot reconnect — blocks in `Dut._wait_for_ready()`
#: until the board reaches WiFi-up + first successful Spotify poll + queue
#: fetch, retrying once via `reconnect` on failure, and refuses (elf-mismatch,
#: boot-not-observed) if it does not. A suite id CANNOT run at all unless this
#: already held, so a dedicated "does reboot work" test would assert something
#: the harness already enforces on every single run — the vacuous test the
#: TASK-705 brief explicitly asks NOT to write. `T_PR_04`/`T_PRM_01` still
#: declare `ops=("reboot_ready",)` as composites (their [REBOOT] precondition
#: plus a persistence assertion that is not itself in `OPS`), which is
#: legitimate coverage but not what makes this op's P1 read clean — this map
#: entry is. Same treatment is NOT extended to any other op: this is a one-off
#: for the one op whose primitive IS the harness contract.
HARNESS_PRIMITIVES = {
    "reboot_ready":
        "lib/dut.py:851 Dut._wait_for_ready() — every DUT session blocks here "
        "until WiFi is up and the first successful Spotify poll + queue fetch "
        "is observed (retrying once via `reconnect`), and refuses "
        "(elf-mismatch / boot-not-observed) if the board never gets there. "
        "The readiness check IS the primitive assertion; no suite id runs "
        "without it having already held.",
}

_TASK_RE_SRC = r"^TASK-\d+$"
_SEP_RE_SRC = r":?-{2,}:?"

import re                                              # noqa: E402
_TASK_RE = re.compile(_TASK_RE_SRC)
_SEP_RE = re.compile(_SEP_RE_SRC)


def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_ledger(path: str = None) -> tuple:
    """-> ({op: 'rel:line'}, [malformed-row errors]).

    Row shape: `| op | why | owner (TASK-NNN) | since (ISO date) |` — one row
    per op, keyed on the op alone (not `(kind, id)` — an op's drivability is
    not a per-id fact).
    """
    path = path or os.path.join(ROOT, LEDGER_REL)
    rows: dict = {}
    errors: list = []
    if not os.path.exists(path):
        return rows, errors
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
        if len(cells) < 4:
            continue
        op, _why, owner, since = (cells[0].strip("`* "), cells[1],
                                   cells[2].strip("`* "), cells[3].strip("`* "))
        if op not in _meta.OPS:
            errors.append(f"{rel}:{i}: op {op!r} is not in _meta.OPS")
            continue
        if not _TASK_RE.match(owner):
            errors.append(f"{rel}:{i}: owner {owner!r} must be a TASK-NNN id")
            continue
        try:
            datetime.date.fromisoformat(since)
        except ValueError:
            errors.append(f"{rel}:{i}: since {since!r} is not an ISO YYYY-MM-DD date")
            continue
        rows[op] = f"{rel}:{i}"
    return rows, errors


def evaluate(records: dict, ledger: dict = None) -> tuple:
    """Pure: (records, ledger) -> (findings, census). `records` is
    build_all_meta()'s dict; each value carries `ops`/`ops_declared`."""
    ledger = dict(ledger or {})
    findings: list = []
    used: set = set()

    # P2 — every declared op is in the vocabulary.
    for tid in sorted(records):
        r = records[tid]
        for op in r.get("ops", ()):
            if op not in _meta.OPS:
                findings.append(
                    f"P2 {tid}: declares op {op!r}, not in _meta.OPS "
                    f"({', '.join(sorted(_meta.OPS))})")

    # Who declares what, restricted to ops actually in the vocabulary (a P2
    # finding above already flags the rest, and folding an invented op into
    # the primitive/composite counts below would hide the P2 under a P1).
    primitives: dict = {}   # op -> [id, ...] declaring EXACTLY that op
    composite_users: dict = {}   # op -> [id, ...] declaring it as part of 2+ ops
    n_undeclared = 0
    n_primitive_ids = 0
    n_composite_ids = 0
    for tid in sorted(records):
        ops = tuple(op for op in records[tid].get("ops", ()) if op in _meta.OPS)
        if not ops:
            n_undeclared += 1
            continue
        if len(ops) == 1:
            n_primitive_ids += 1
            primitives.setdefault(ops[0], []).append(tid)
        else:
            n_composite_ids += 1
            for op in ops:
                composite_users.setdefault(op, []).append(tid)

    # P1 — every op has a primitive, a harness-level primitive, or a ledger row.
    for op in _meta.OPS_ORDER:
        if op in primitives:
            continue
        if op in HARNESS_PRIMITIVES:
            continue
        if op in ledger:
            used.add(op)
            continue
        findings.append(
            f"P1 {op}: no id declares this op ALONE (a PRIMITIVE) — "
            f"{_meta.OPS[op]} Write one (see `./run/new-test`), or add a dated "
            f"row to {LEDGER_REL} if it is genuinely not drivable today")

    # P3 — a composite's op has neither a primitive nor a ledger row (the
    # composite's own coverage does not excuse the gap).
    for op, ids in sorted(composite_users.items()):
        if op in primitives or op in HARNESS_PRIMITIVES or op in ledger:
            continue
        findings.append(
            f"P3 {op}: used by composite id(s) {', '.join(ids)} but has "
            f"neither a primitive nor a ledger row — a composite FAILing here "
            f"says nothing about which of its ops broke")

    # Stale ledger rows — an op that now has a primitive no longer needs one.
    for op, where in sorted(ledger.items()):
        if op in primitives:
            findings.append(
                f"STALE {where}: {op!r} now has a primitive — delete the row. "
                f"This ledger only shrinks")

    census = {
        "declared_ids": n_primitive_ids + n_composite_ids,
        "primitives": n_primitive_ids,
        "composites": n_composite_ids,
        "undeclared": n_undeclared,
        "ops_total": len(_meta.OPS),
        "ops_with_primitive": len(primitives),
        "ops_with_harness_primitive": len(HARNESS_PRIMITIVES),
    }
    return findings, census


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    import suite.serialdbg as _suite          # noqa: PLC0415
    records = _suite.build_all_meta()

    ledger, lerrs = parse_ledger()
    findings, census = evaluate(records, ledger)
    findings = lerrs + findings

    print("=== check_primitive_coverage.py — the ops/OPS record (TASK-705) ===")
    print(f"  ids: declared={census['declared_ids']} "
          f"(primitives={census['primitives']}, composites={census['composites']}), "
          f"undeclared={census['undeclared']}")
    print(f"  ops: {census['ops_with_primitive']}/{census['ops_total']} have a "
          f"primitive id, {census['ops_with_harness_primitive']} a harness "
          f"primitive, {len(ledger)} on the ledger ({LEDGER_REL})")
    if args.verbose:
        for op in _meta.OPS_ORDER:
            print(f"    {op}: {_meta.OPS[op]}")

    if findings:
        print()
        for f in findings:
            print(f"  FAIL: {f}")
        print(f"\n=== {len(findings)} primitive coverage check(s) failed ===")
        return 1
    print("\n=== every op has a primitive or a ledger row; no stray ops ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
