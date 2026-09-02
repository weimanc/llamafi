#!/usr/bin/env python3
"""lib/baseline.py — fold N runner logs into one per-id baseline. TASK-566.

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

    python3 -m lib.baseline run1.log run2.log run3.log
    python3 -m lib.baseline --md run*.log        # markdown table
"""

from __future__ import annotations

import collections
import os
import re
import sys

#: The same alternation `run/player-gate:_parse_runner_log` uses, longest-first
#: so the captured token is whole. `FLAKE` != `FLAKY` was TASK-573's live defect;
#: it is not repeated here by construction, not by care.
ROW_RE = re.compile(
    r"^  ([A-Za-z0-9_-]+): (FLAKY-PASS|NOT-RUN|PASS|FAIL|SKIP|FLAKE)")

STATUSES = ("PASS", "FLAKY-PASS", "SKIP", "FLAKE", "FAIL", "NOT-RUN")


def parse_log(path: str) -> dict:
    """-> {id: status}. Reads the whole file: the summary block is the only
    place these rows appear, and anchoring on the '── Results ──' header would
    silently yield {} for a run that aborted before printing it — which is a
    fact worth keeping, not an error to hide."""
    out = {}
    with open(path, errors="replace") as fh:
        for line in fh:
            m = ROW_RE.match(line.rstrip("\n"))
            if m:
                out[m.group(1)] = m.group(2)
    return out


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
    runs = [parse_log(p) for p in paths]
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
        return "usage: python3 -m lib.baseline [--md] <runner log> …"
    print(report(paths, markdown=md))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
