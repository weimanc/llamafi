#!/usr/bin/env python3
"""lib/test_shuffle.py — negative/property suite for lib/shuffle.py. TASK-636.

M-HARNESS2-requirements R20 ("the harness MUST be able to run a class's ids in
a shuffled order") / R21 (a differing verdict is a comparison outcome, not a
verdict). This suite is host-only — pure functions, no DUT, no serial port —
and asserts the properties `runner.py --shuffle-family` and
`lib/artifact.py`'s `order_dependence()` both depend on:

  1. same seed -> same permutation, every call (reproducibility).
  2. family BLOCKS are preserved: the multiset of families visited, in their
     first-occurrence order, is identical before and after.
  3. a family of size >= 3 actually gets permuted for AT LEAST one seed (the
     shuffle is not accidentally an identity function) — checked by trying a
     handful of seeds, since any single seed has a 1/6 chance of landing on
     the identity permutation of a 3-element family.
  4. a malformed/absent meta record for an id degrades to a singleton family
     for that id alone, never a crash and never merging it into a real family.
  5. a different SEED changes at least one family's internal order (the
     mechanism is actually seed-dependent, not a fixed shuffle).

    python3 app/tools/lib/test_shuffle.py [-v]
"""

from __future__ import annotations

import os
import sys

_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from lib import shuffle as S                                     # noqa: E402

FAILURES: list = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'BAD '}{name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def _meta(spec: dict) -> dict:
    """{id: family} -> the {id: {"module": family}} shape shuffle_family reads."""
    return {tid: {"module": fam} for tid, fam in spec.items()}


# ── 1. reproducibility ───────────────────────────────────────────────────────
ids1 = ["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "C4"]
meta1 = _meta({"A1": "clock", "A2": "clock", "A3": "clock",
              "B1": "stock", "B2": "stock",
              "C1": "player", "C2": "player", "C3": "player", "C4": "player"})
out_a = S.shuffle_family(ids1, meta1, "seed-1")
out_b = S.shuffle_family(ids1, meta1, "seed-1")
check("same seed -> identical permutation, twice", out_a == out_b)
out_c = S.shuffle_family(list(reversed(ids1)), meta1, "seed-1")
check("input ORDER (not just membership) can change family first-occurrence "
     "order, and the result still reproduces",
     out_c == S.shuffle_family(list(reversed(ids1)), meta1, "seed-1"))

# ── 2. family blocks preserved ───────────────────────────────────────────────
check("family visiting order preserved (first-occurrence)",
     S.family_blocks(out_a, meta1) == ["clock", "stock", "player"])
check("every id from every family still present, none duplicated",
     sorted(out_a) == sorted(ids1))
# block CONTIGUITY: once a family's block starts, no other family interleaves
# — each family's ids occupy one contiguous span of the output.
fams_seen_in_order = [S.family_of(t, meta1) for t in out_a]
_spans = {}
for i, fam in enumerate(fams_seen_in_order):
    _spans.setdefault(fam, []).append(i)
_contiguous = all(span == list(range(span[0], span[0] + len(span)))
                  for span in _spans.values())
check("each family's ids occupy one contiguous span (no interleaving)",
     _contiguous)

# ── 3. a family of size >= 3 is actually permuted for some seed ─────────────
_any_moved = False
for seed in range(20):
    shuffled = S.shuffle_family(ids1, meta1, f"probe-{seed}")
    clock_block = [t for t in shuffled if S.family_of(t, meta1) == "clock"]
    if clock_block != ["A1", "A2", "A3"]:
        _any_moved = True
        break
check("a 3-id family is actually permuted for at least one of 20 seeds",
     _any_moved)

# ── 4. malformed/absent meta -> singleton family, no crash ──────────────────
ids4 = ["A1", "A2", "NOMETA", "A3"]
meta4 = _meta({"A1": "clock", "A2": "clock", "A3": "clock"})  # NOMETA absent
out4 = S.shuffle_family(ids4, meta4, "x")
check("an id with no meta record does not crash the shuffle",
     sorted(out4) == sorted(ids4))
check("an id with no meta record becomes its OWN singleton family "
     "(never silently merged into a real one)",
     S.family_of("NOMETA", meta4) == "NOMETA")
check("the singleton family's position is stable regardless of the 3 real "
     "clock ids' internal permutation (it is family 'NOMETA' at its own "
     "first-occurrence slot)",
     S.family_blocks(out4, meta4) == ["clock", "NOMETA"])

meta4b = {"A1": {"module": "clock"}, "A2": {}, "A3": {"module": "clock"}}
out4b = S.shuffle_family(["A1", "A2", "A3"], meta4b, "x")
check("a meta record present but missing the 'module' key also degrades to "
     "a singleton, not a crash",
     sorted(out4b) == ["A1", "A2", "A3"])
check("...and that singleton is keyed by the id itself",
     S.family_of("A2", meta4b) == "A2")

# ── 5. different seeds are not all mapped to the identical permutation ──────
_distinct_outputs = {tuple(S.shuffle_family(ids1, meta1, f"probe-{i}"))
                     for i in range(20)}
check("20 distinct seeds produce more than 1 distinct permutation "
     "(the seed actually drives the RNG, this isn't a fixed shuffle)",
     len(_distinct_outputs) > 1)

# ── 6. one family's permutation is independent of which OTHER ids/families
#      are also selected (per-family seeding, not one shared RNG stream) ────
solo_clock = S.shuffle_family(["A1", "A2", "A3"], meta1, "seed-1")
clock_inside_full = [t for t in S.shuffle_family(ids1, meta1, "seed-1")
                     if S.family_of(t, meta1) == "clock"]
check("a family's permutation under its own seed is identical whether it is "
     "shuffled alone or alongside other families (no shared-RNG leakage)",
     solo_clock == clock_inside_full)

if FAILURES:
    print(f"\nlib/test_shuffle.py: {len(FAILURES)} FAILED — {FAILURES}")
    sys.exit(1)
print("\nlib/test_shuffle.py: all checks passed")
