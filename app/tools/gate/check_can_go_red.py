#!/usr/bin/env python3
"""check_can_go_red.py — R34 at runtime: every recorded id can be MADE to go red.

TASK-671. The executable complement of `check_no_reachable_fail.py`.

WHY A SECOND GATE FOR THE SAME REQUIREMENT. The static gate proves a NECESSARY
condition — a `fail()` is reachable in the body's source — and says so in its
docstring. It cannot prove the sufficient one, because "this guard can be true
at runtime" is a program-analysis question over 196 bodies with helper
indirection, and a static answer to it would be wrong in the direction that
matters: it would clear a body that cannot go red. Four of the corpus's audited
defect shapes live exactly in that gap — `C-1`'s inverted guard, `D-2`'s
skip-on-regression residue, a `fail()` in a helper no path calls, a guard over
two reads of one key. This gate does not analyse; it executes. For every id that
has a recorded transcript, `lib/canfail.sweep` poisons the recording at every
position with four poisons and runs the real body through the real `Dut` and the
runner's real dispatch arms, and reports the first ASSERTION-grade FAIL it
observes — or that there was none.

WHAT IT ASSERTS. For every id in `build_all_tests()` that has a transcript under
`suite/serialdbg/transcripts/<id>.json`, exactly one of:

  1. the sweep's outcome is `RED` — an assertion FAIL was observed; or
  2. the outcome is `INCONCLUSIVE` / `BASELINE-NOT-PASS` — the RECORDING is not
     usable for this body (it missed, or its healthy path is not a PASS). Noted
     with a re-record instruction, never a failure: a stale fixture is not a
     failing test (`lib/replay.py`'s rule); or
  3. the outcome is one of the blocking two — `NEVER-RED`, or
     `RED-WITHOUT-ASSERTION` (red only through the contract, crash or flake
     arms) — and the id has a row in the dated, owned, shrink-only ledger
     `docs/verification/can_go_red_ledger.md`.

Ids with no transcript are `UNRECORDED`: counted, printed, not a failure. The
recorded set is a ratchet owned by TASK-641/642/643 (`lib/replay.py` names them);
this gate does not pretend a board session can be demanded by a host gate.

WHAT IT DOES NOT ASSERT. It does not grade the assertion (R2/R9: a tautology is
perfectly falsifiable), and it does not say the FIRMWARE would still produce the
recorded replies (R10: that is the ELF-stamped falsification job). Both are
stated in `lib/canfail.py`'s docstring; read that before widening this gate.

CROSS-CHECK WITH THE STATIC GATE. Where both gates have an answer, they are
compared. Static "no reachable fail()" with a runtime `RED` is a contradiction
that names a bug in one of them and is printed as such. Static "reachable" with a
runtime `NEVER-RED` is not a contradiction; it is the gap, measured.

BLOCKING, with a dated shrink-only ledger whose stale rows are themselves
blocking failures — the standing form. Today the transcript directory is empty
(a TASK-557 observation window was live when this landed; recording costs a
reset), so the gate's finding count is zero BY ABSENCE and the census line says
so in those words. The mechanism is proven by `test_check_can_go_red.py`, which
records synthetic bodies through the real recorder and sweeps them — including a
mutation arm that breaks the poisons and asserts the RED body stops being RED.

Import discipline: `build_all_tests` is the ONLY thing imported from the suite.
No DUT, no build, no network.

    python3 app/tools/gate/check_can_go_red.py [--verbose] [--dir DIR]
"""

from __future__ import annotations

import os
import pathlib
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))
sys.path.insert(0, TOOLS)

from lib import canfail as CF                                   # noqa: E402
from lib import replay as RP                                    # noqa: E402

LEDGER_REL = "docs/verification/can_go_red_ledger.md"
TRANSCRIPTS_REL = "app/tools/suite/serialdbg/transcripts"

TASK_RE = re.compile(r"\bTASK-(\d+)")
SEP_CELL_RE = re.compile(r":?-{2,}:?")
TEST_ID_RE = re.compile(r"T\d{3}[a-z]?"
                        r"|T_[A-Z0-9]+(?:_[A-Z0-9]+)*_\d+[a-z]?"
                        r"|T-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d+[a-z]?")


# ── transcripts ──────────────────────────────────────────────────────────────

def load_transcripts(directory) -> tuple:
    """({id: Transcript}, [errors]) for every `<id>.json` in `directory`."""
    out, errors = {}, []
    d = pathlib.Path(directory)
    if not d.is_dir():
        return out, errors
    for p in sorted(d.glob("*.json")):
        try:
            t = RP.Transcript.load(p)
        except (OSError, ValueError, RP.ReplayError) as e:
            errors.append(f"{p}: unreadable transcript ({type(e).__name__}: {e}); "
                          f"re-record it or delete it")
            continue
        tid = t.tid or p.stem
        if tid != p.stem:
            errors.append(f"{p}: file is named {p.stem!r} but records id {tid!r}")
            continue
        out[tid] = t
    return out, errors


# ── the ledger ───────────────────────────────────────────────────────────────

def _rows(path):
    if not os.path.exists(path):
        return
    header = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            s = line.strip()
            if not s.startswith("|"):
                header = None
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(SEP_CELL_RE.fullmatch(x) for x in cells if x):
                continue
            if header is None:
                header = cells
                continue
            yield i, cells


def archived_tasks(root: str) -> set:
    p = os.path.join(root, "docs", "project", "tasks-archive.md")
    if not os.path.exists(p):
        return set()
    with open(p, encoding="utf-8", errors="replace") as fh:
        return set(TASK_RE.findall(fh.read()))


_OUTCOME_TOKENS = {o.value: o for o in CF.BLOCKING}


def parse_ledger(root: str) -> tuple:
    """({id: (outcome, where)}, [errors]). Rows: id | outcome | why | owner | since."""
    ledger, errors = {}, []
    path = os.path.join(root, LEDGER_REL)
    archived = archived_tasks(root)
    for ln, cells in _rows(path):
        tid = cells[0].strip("`* ")
        if not TEST_ID_RE.fullmatch(tid):
            continue
        where = f"{LEDGER_REL}:{ln}"
        tok = cells[1].strip("`* ") if len(cells) > 1 else ""
        owner = cells[3] if len(cells) > 3 else ""
        since = cells[4].strip() if len(cells) > 4 else ""
        outcome = _OUTCOME_TOKENS.get(tok)
        if outcome is None:
            errors.append(f"{where}: {tid} -> outcome {tok!r} is not one of "
                          f"{sorted(_OUTCOME_TOKENS)}")
        m = TASK_RE.search(owner)
        if not m:
            errors.append(f"{where}: {tid} -> ledger row has no owning TASK- id")
        elif m.group(1) in archived:
            errors.append(f"{where}: {tid} -> owner TASK-{m.group(1)} is ARCHIVED; a "
                          f"row cannot outlive its owner")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", since):
            errors.append(f"{where}: {tid} -> ledger row has no ISO date in 'since'")
        ledger[tid] = (outcome, where)
    return ledger, errors


# ── the static cross-check ───────────────────────────────────────────────────

def static_shapes(tid, fn) -> set:
    """Shapes `check_no_reachable_fail.analyse` reports for this id, or an empty
    set if that gate is unavailable. Kept optional so this gate cannot be taken
    down by its sibling's import."""
    try:
        from gate import check_no_reachable_fail as S           # noqa: WPS433
    except Exception:                                           # noqa: BLE001
        try:
            sys.path.insert(0, HERE)
            import check_no_reachable_fail as S                 # noqa: WPS433
        except Exception:                                       # noqa: BLE001
            return set()
    try:
        return {shape for shape, _msg in S.analyse(tid, fn)}
    except Exception:                                           # noqa: BLE001
        return set()


# ── main evaluation ──────────────────────────────────────────────────────────

def evaluate(tests: dict, transcripts: dict, root: str, *,
             sweep=CF.sweep, cross_check: bool = True) -> tuple:
    """([failures], [notes], {Outcome: [Sweep]}) — the whole gate.

    `sweep` is injectable so the negative suite can break it (R10's own
    verification clause: a driver that is never broken cannot be shown to be
    doing anything).
    """
    census = {o: [] for o in CF.Outcome}
    ledger, failures = parse_ledger(root)
    notes = []
    used = set()

    for tid, fn in sorted(tests.items()):
        t = transcripts.get(tid)
        if t is None or fn is None:
            census[CF.Outcome.UNRECORDED].append(
                CF.Sweep(tid, CF.Outcome.UNRECORDED,
                         "no transcript" if t is None else "registry entry is not a function"))
            continue
        s = sweep(tid, fn, t)
        census[s.outcome].append(s)

        if s.outcome in CF.BLOCKING:
            if tid in ledger:
                used.add(tid)
                want, where = ledger[tid]
                if want is not None and want is not s.outcome:
                    failures.append(
                        f"{where}: {tid} -> ledger row says {want.value}, the sweep "
                        f"finds {s.outcome.value}; the row must name what is true")
            else:
                failures.append(f"{tid} -> {s.outcome.value}: {s.detail} "
                                f"[{s.replays} replays over {s.n_exchanges} "
                                f"exchanges]. Make the body assert, or carry a "
                                f"ledger row saying why not")
        elif s.outcome in (CF.Outcome.INCONCLUSIVE, CF.Outcome.BASELINE_NOT_PASS):
            notes.append(f"{tid} {s.outcome.value}: {s.detail} — re-record "
                         f"(RECORD_DIR={TRANSCRIPTS_REL} ./run/test-targeted {tid})")

        if cross_check and s.outcome is CF.Outcome.RED and 1 in static_shapes(tid, fn):
            notes.append(f"CONTRADICTION {tid}: static gate finds no reachable fail() "
                         f"but the sweep observed an assertion FAIL ({s.evidence}); "
                         f"one of the two gates is wrong about this body")

    for tid, (_o, where) in sorted(ledger.items()):
        if tid not in used:
            if tid in transcripts:
                failures.append(f"{where}: {tid} -> stale ledger row, the sweep no "
                                f"longer finds a blocking outcome; delete this row. "
                                f"The list can only shrink.")
            else:
                notes.append(f"{where}: {tid} carries a ledger row but has no "
                             f"transcript; the row is unverifiable until it is "
                             f"recorded")
    return failures, notes, census


def main() -> int:
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    directory = os.path.join(ROOT, TRANSCRIPTS_REL)
    if "--dir" in sys.argv:
        directory = sys.argv[sys.argv.index("--dir") + 1]

    from suite.serialdbg import build_all_tests                 # noqa: E402
    tests = build_all_tests()
    transcripts, t_errors = load_transcripts(directory)

    t0 = time.monotonic()
    failures, notes, census = evaluate(tests, transcripts, ROOT)
    failures = t_errors + failures
    ledger, _ = parse_ledger(ROOT)
    dt = time.monotonic() - t0

    print("=== check_can_go_red.py — R34 at runtime: every recorded id can be made "
          "to go red (TASK-671) ===")
    print(f"  ids: {len(tests)}   transcripts: {len(transcripts)} in {TRANSCRIPTS_REL}"
          f"   sweep wall: {dt:.1f}s")
    for o in CF.Outcome:
        print(f"  {o.value:18s} {len(census[o])}")
    print(f"  ledger: {len(ledger)} row(s) in {LEDGER_REL}")
    if not transcripts:
        print("  [note] ZERO transcripts: the finding count is zero BY ABSENCE, not "
              "by evidence. Record with RECORD_DIR=<dir> ./run/test (costs a board "
              "reset — check ./run/monitor-read for a TASK-557 window first).")
    for n in notes:
        print(f"  [note] {n}")
    if verbose:
        print()
        for o in CF.Outcome:
            for s in census[o]:
                if o is not CF.Outcome.UNRECORDED:
                    print(s.line())

    if failures:
        print()
        for f in failures:
            print(f"  FAIL: {f}")
        print(f"\n=== {len(failures)} unexcepted finding(s) ===")
        return 1
    n_red = len(census[CF.Outcome.RED])
    print(f"\n=== every recorded id goes red under poison ({n_red} of "
          f"{len(transcripts)} RED), or carries a dated ledger row ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
