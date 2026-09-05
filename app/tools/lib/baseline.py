#!/usr/bin/env python3
"""lib/baseline.py — fold N run artifacts into one per-id baseline. TASK-566.

WHY A TOOL AND NOT A PASTED TABLE. EC-G9 asks for "a >=3-run pre-declared-flaky
baseline" before the runner's execution order changes, and @VE §18.6(a) then
asks for an INTERLEAVED A/B at one commit rather than a sequential 3+3. Both
need the same primitive: given several runs, say which ids gave the SAME answer
every time and which did not. A baseline quoted from one run is close to
worthless on this suite — TASK-553 (order-dependence), TASK-557 (a
non-stationary rig) and TASK-573 (a gate that misparsed a status) are three
independent demonstrations of that in the last week.

WHAT IT REFUSES TO DO. It does not adjudicate. An id that answered PASS twice
and SKIP once is reported as UNSTABLE with both answers and a run count, never
folded to "mostly passes". @VE §18.6(b) is explicit that flake candidates are
promoted or dismissed BEFORE run 1 and not read off the results, and a tool that
picked a majority answer would quietly do the thing that ruling forbids.

    python3 -m lib.baseline run1.json run2.json run3.json
    python3 -m lib.baseline --md run*.json        # markdown table

TASK-608: IT READS ARTIFACTS, NOT LOGS. This module used to carry its own copy
of `run/player-gate`'s summary-text regex — the SECOND of the three parsers of
an unspecified machine interface, and it was already one token behind (no
`UNMET`, added to results.py by TASK-624). That is the whole defect shape: a
verdict the producer can WRITE that a consumer cannot READ is dropped silently,
and here it would have dropped an id out of the fold entirely, turning an
unstable id into an `ABSENT-SOMETIMES` row or out of the table altogether. Under
ADR-066 D1 the artifact is the interface and a new verdict cannot be missed,
because the reader never enumerates the vocabulary at all.

The log parser is DELETED rather than kept as a fallback. R29's acceptance
number for summary parsers is zero, and a fallback path is a parser that stays
load-bearing exactly when the artifact is missing — i.e. in the case the
artifact exists to make loud. Folding runs that predate the artifact is
therefore no longer possible from their logs; that is a real, accepted loss of
retrospective reach, stated here rather than worked around.
"""

from __future__ import annotations

import collections
import os
import sys

from . import artifact as _artifact

STATUSES = ("PASS", "FLAKY-PASS", "SKIP", "FLAKE", "FAIL", "NOT-RUN", "UNMET")


def parse_run(path: str) -> dict:
    """-> {id: verdict token} for one run artifact.

    Raises on a missing or unreadable artifact. Deliberately: the old
    log-parsing version returned `{}` for a run that aborted before its summary,
    which is indistinguishable from a run in which nothing was selected, and
    both then read as ABSENT rows in the fold.
    """
    return _artifact.id_status(_artifact.load(path))


def fold(runs: list) -> dict:
    """[{id: status}, …] -> {id: [status per run, or None if absent]}."""
    ids = []
    seen = set()
    for r in runs:
        for tid in r:
            if tid not in seen:
                seen.add(tid)
                ids.append(tid)
    return {tid: [r.get(tid) for r in runs] for tid in ids}


def classify(statuses: list) -> str:
    """STABLE:<status> | UNSTABLE | ABSENT-SOMETIMES."""
    present = [s for s in statuses if s is not None]
    if not present:
        return "ABSENT"
    if len(present) != len(statuses):
        return "ABSENT-SOMETIMES"
    return f"STABLE:{present[0]}" if len(set(present)) == 1 else "UNSTABLE"


def report(paths: list, markdown: bool = False) -> str:
    runs = [parse_run(p) for p in paths]
    table = fold(runs)
    L = []
    A = L.append
    A(f"── baseline over {len(paths)} run(s) ──")
    for p, r in zip(paths, runs):
        A(f"  {os.path.basename(p)}: {len(r)} ids  "
          + "  ".join(f"{s}={sum(1 for v in r.values() if v == s)}"
                      for s in STATUSES if any(v == s for v in r.values())))
    A("")
    unstable = {t: v for t, v in table.items()
                if classify(v) in ("UNSTABLE", "ABSENT-SOMETIMES")}
    if markdown:
        A("| id | " + " | ".join(f"run{i+1}" for i in range(len(paths)))
          + " | verdict |")
        A("|---|" + "---|" * (len(paths) + 1))
        for tid, v in table.items():
            A(f"| `{tid}` | " + " | ".join(s or "—" for s in v)
              + f" | {classify(v)} |")
        A("")
    counts = collections.Counter(classify(v).split(":")[0] for v in table.values())
    A("verdicts: " + "  ".join(f"{k}={n}" for k, n in sorted(counts.items())))
    stable_by = collections.Counter(
        classify(v).split(":", 1)[1] for v in table.values()
        if classify(v).startswith("STABLE"))
    A("stable answers: " + "  ".join(f"{k}={n}" for k, n in stable_by.most_common()))
    A("")
    A(f"FLAKE EXPOSURE — {len(unstable)} of {len(table)} ids did NOT give the "
      f"same answer in every run:")
    for tid, v in sorted(unstable.items()):
        A(f"  {tid:<24} " + "  ".join(s or "ABSENT" for s in v))
    if not unstable:
        A("  (none)")
    A("")
    A("NOT adjudicated here, on purpose: @VE §18.6(b) requires flake candidates "
      "to be promoted into flaky.yaml or dismissed BEFORE run 1 of the A/B, not "
      "read off these results.")
    return "\n".join(L)


def main(argv):
    md = "--md" in argv
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        return ("usage: python3 -m lib.baseline [--md] <run artifact .json> …\n"
                "  (TASK-608: run artifacts, not runner logs — the summary text\n"
                "   is not a machine interface, ADR-066 D1 / IFC-008 I6)")
    print(report(paths, markdown=md))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
