"""lib/shuffle.py — per-family shuffle for order-independence auditing.

TASK-636 / M-HARNESS2-requirements R20-R21 / ADR-066 D2a.

WHAT THIS IS FOR. R20 (MUST): the harness must be able to run a class's ids in
a shuffled order and report any verdict that differs from the canonical
order's. The architect review (M-HARNESS2-architect-review.md ~line 512)
amended R20's MUST to the CAPABILITY plus its verdict-diff report, with the
campaign itself scheduled — and answered §17 OQ5 with "per-family shuffle
first, cross-FEATURE only after a family-level run comes back clean". This
module is that capability's pure core: given the ids a run selected and their
`(cls, scope, effect, module)` metadata record (suite/serialdbg/_meta.py's
`resolve()` shape), produce a permutation that:

  * keeps FAMILY BLOCKS in their canonical order — canonical here means the
    order families first appear in the input `ids` list, which for a normal
    run is registry order (suite/serialdbg/__init__.py's build_all_tests()
    merges `_FAMILY_MODULES` in that order, and a --scope/--tests selection
    only narrows within it — it never interleaves families that weren't
    already interleaved);
  * permutes the order WITHIN each family block by a SEEDED, per-family RNG,
    so the shuffle is deterministic and reproducible from the seed alone, and
    one family's permutation never depends on which OTHER families are in the
    selection (a --scope run that only ever sees one family shuffles exactly
    as it would inside a full run).

FAMILY IS `module`, NOT `scope`. `_meta.resolve()`'s `scope` axis is an
APP_ORDER name (or shell/boot/taskbar/spotify-chrome/rig) and exists for
SELECTION (M-TESTARCH §13). `module` is the family module basename
(clock/teletext/planeradar/stock/webradio/player/shell/health) the id's TESTS
dict lives in, and that is the axis R20's "per-family shuffle" means — several
scopes can share one family module (shell.py covers shell/boot/taskbar/
spotify-chrome) and this shuffle must not conflate the two or a "per-family"
run would silently become a "per-scope" one.

WHY A SEPARATE MODULE, NOT `suite/serialdbg/_order.py`. `_order.py` implements
M-TESTARCH §4's CLASS ordering (RIG < HEALTH < CORE < APP < FEATURE) and its
own EDGE_ADJUDICATION/ORDER-SENSITIVE vocabulary (ADR-066 D2a's third row) —
a different axis (class, not family) with its own held switch (TASK-566) and
concurrent in-flight work. This module never imports it and is never imported
by it; `--shuffle-family` and `--class-order` are mutually exclusive at the
runner.py CLI (see runner.py's refusal) precisely so the two axes are never
asked to compose silently.
"""

from __future__ import annotations

import random

#: The meta record's family key (suite/serialdbg/_meta.py `resolve()`'s
#: `"module"` field). An id with no meta record, or a record missing this key,
#: becomes its OWN singleton family (keyed by the id itself) rather than
#: raising or being dropped — a malformed record then costs that one id a
#: shuffle, not the whole run.
_FAMILY_KEY = "module"


def family_of(tid: str, meta: dict) -> str:
    """The family an id shuffles within. Never raises."""
    rec = meta.get(tid) if meta else None
    fam = (rec or {}).get(_FAMILY_KEY)
    return fam if fam else tid


def shuffle_family(ids, meta: dict, seed) -> list:
    """Return `ids` regrouped into family blocks (canonical, first-occurrence
    order) with each block's internal order permuted by a seeded RNG.

    `seed`: any value `str()` cleanly — the CLI passes a string. Two calls
    with the same `ids`, `meta` and `seed` always return the same list
    (`random.Random` seeded from a `str`/`bytes` argument uses a fixed hash —
    SHA-512 under the hood — not the process's randomised `hash()`, so this is
    reproducible across processes and PYTHONHASHSEED values, not just within
    one).

    Each family's `random.Random` is seeded from `(seed, family)` jointly, not
    from a single `Random(seed)` shared across the whole call: sharing one RNG
    draws a different number of random values per family (proportional to
    family size) before reaching the next family, so adding or removing ids in
    an EARLIER family would silently perturb a LATER family's permutation. A
    per-family seed makes each family's shuffle depend only on its own
    membership and the run seed — never on which other families/ids are also
    selected.

    Pure: no I/O, no global state, safe to call host-only.
    """
    ids = list(ids)
    order: list = []          # families, in first-occurrence order
    buckets: dict = {}
    for tid in ids:
        fam = family_of(tid, meta or {})
        if fam not in buckets:
            order.append(fam)
            buckets[fam] = []
        buckets[fam].append(tid)

    out: list = []
    for fam in order:
        bucket = list(buckets[fam])
        rng = random.Random(f"{seed}\x00{fam}")
        rng.shuffle(bucket)
        out.extend(bucket)
    return out


def family_blocks(ids, meta: dict) -> list:
    """-> the family names `ids` visits, in first-occurrence order, with no
    duplicates. Used by tests (and available to any caller) to assert that a
    shuffle preserved block order without re-deriving the grouping by hand."""
    seen: list = []
    have = set()
    for tid in ids:
        fam = family_of(tid, meta or {})
        if fam not in have:
            have.add(fam)
            seen.append(fam)
    return seen
