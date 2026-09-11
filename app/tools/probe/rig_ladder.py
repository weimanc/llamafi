#!/usr/bin/env python3
"""probe/rig_ladder.py — PROP-011 X-P2 bare-rig load-ladder orchestration
(TASK-677 H-1).

BLOCKED ON F-4 (PROP-011-runbook.md §1 F-4: bodWatch ported into the bare
rig, `~/proj/webradio-bare/`). F-4 is not landed — this file exists so the
argument shape is settled and reviewable now, but `main()` REFUSES to do
anything until F-4's marker (a `bodWatch.h` in the bare rig checkout) is
present. Nothing beyond the parser and the refusal is implemented; adding
the real flash/monitor/parse loop without F-4 would be exactly the kind of
half-finished implementation this project's conventions avoid — there is
nothing on the other end of `pio run -e bare -t upload` to drive yet.

Once F-4 lands: for each rung 1-4 (PROP-011-runbook.md §3 X-P2 table), for
each level 7,5,3,2,1,0 (stop at the first no-trip level), 3 boots: flash
`~/proj/webradio-bare` with that rung's `-DBARE_*` flags via
`pio run -e bare -t upload` (its own port open is allowed there — a
different, disposable board, not the CYD under a TASK-557 window), read
`[bod]` lines from a short bounded `pio device monitor` capture, record
trip/no-trip, move on. Scheduled after the CYD's debug window has been
deliberately ended (PROP-011-runbook.md §3 X-P2's ordering).

    python3 probe/rig_ladder.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys

BARE_RIG_DIR = os.environ.get("BARE_RIG_DIR",
                              os.path.expanduser("~/proj/webradio-bare"))

#: F-4's own deliverable — bodWatch ported into the bare rig. Its presence is
#: this driver's only readiness check; it deliberately does not try to be
#: cleverer than that (e.g. grepping for a specific symbol) since F-4's exact
#: shape is still open (PROP-011-runbook.md §1 F-4).
F4_MARKER = os.path.join(BARE_RIG_DIR, "src", "bodWatch.h")


def f4_landed(marker_path: str = F4_MARKER) -> bool:
    return os.path.exists(marker_path)


LEVELS = (7, 5, 3, 2, 1, 0)
RUNGS = (1, 2, 3, 4)
REPS = 3


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rungs", default=",".join(str(r) for r in RUNGS),
                    help="comma-separated bare-rig rungs (1-4; PROP-011-runbook §3 X-P2 table)")
    ap.add_argument("--levels", default=",".join(str(l) for l in LEVELS))
    ap.add_argument("--reps", type=int, default=REPS)
    ap.add_argument("--bare-rig-dir", default=BARE_RIG_DIR)
    ap.add_argument("--dry-run", action="store_true")
    return ap


def _dry_run(rungs: list, levels: list, reps: int, bare_rig_dir: str) -> None:
    print(f"[dry-run] bare rig: {bare_rig_dir}")
    for rung in rungs:
        for level in levels:
            for rep in range(reps):
                print(f"[dry-run] rung={rung} level={level} rep={rep}: "
                     f"pio run -e bare -t upload (rung's -DBARE_* flags), "
                     f"bounded pio device monitor capture, look for [bod] TRIP")


def main(argv: list) -> int:
    ap = build_arg_parser()
    a = ap.parse_args(argv)

    rungs = [int(x) for x in a.rungs.split(",") if x.strip()]
    levels = [int(x) for x in a.levels.split(",") if x.strip()]

    if a.dry_run:
        _dry_run(rungs, levels, a.reps, a.bare_rig_dir)
        return 0

    if not f4_landed(os.path.join(a.bare_rig_dir, "src", "bodWatch.h")):
        print("REFUSED: F-4 (bodWatch ported into the bare rig) is not landed "
             f"— no {os.path.join(a.bare_rig_dir, 'src', 'bodWatch.h')} found. "
             "See PROP-011-runbook.md §1 F-4 and §3 X-P2. rig_ladder.py has "
             "only its argument parser and this refusal until F-4 lands.",
             file=sys.stderr)
        return 3

    # Unreachable until F-4 lands and the check above passes — intentionally
    # not implemented (see module docstring).
    print("F-4 marker found, but rig_ladder.py's flash/monitor/parse loop is "
         "not yet implemented — this is as far as H-1 could take X-P2's "
         "orchestration without F-4 to drive.", file=sys.stderr)
    return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
