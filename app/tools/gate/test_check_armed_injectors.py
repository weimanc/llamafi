#!/usr/bin/env python3
"""Negative tests for check_armed_injectors.py — BP-068. TASK-635 §2.5.

Modeled on `test_check_get_keys.py`: each finding shape (F1-F4) gets a case
proving it fires, plus positive controls proving the live tree is clean and
the extractor's counts match reality. All driven through `evaluate()`, which
is pure — no real source is touched except by the positive controls.

No DUT, no build, no network.
Run: python3 app/tools/gate/test_check_armed_injectors.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "gen"))
import _case_runner  # noqa: E402

import check_armed_injectors as C   # noqa: E402
import gen_set_keys as G            # noqa: E402


def one(fs, needle):
    hits = [f for f in fs if needle in f]
    assert hits, f"expected a finding containing {needle!r}, got {fs}"
    return hits


def none(fs):
    assert not fs, f"expected no findings, got {fs}"


# ── F1: an extracted key accounted for nowhere ──────────────────────────────

def case_f1_undeclared_key():
    fs = C.evaluate({"newDebugKnob"}, set())
    one(fs, "F1")
    one(fs, "newDebugKnob")


def case_f1_not_raised_for_accounted_keys():
    # A key that's in ARMED_BY's values (via the real ARMED_BY dict) must not
    # also be flagged F1 even though it's the only key passed.
    fs = C.evaluate({"aeDmaFloor"}, {"aeDmaFloor"})
    assert not [f for f in fs if f.startswith("F1")], fs


# ── F2: a ledger row naming a key no longer in source ───────────────────────

def case_f2_stale_not_injectors_row():
    # Every real NOT_INJECTORS key except one is present; the missing one
    # must be reported stale.
    missing = next(iter(C.NOT_INJECTORS))
    present = set(C.NOT_INJECTORS) - {missing}
    present |= {kk for v in C.ARMED_BY.values() for kk in v}
    fs = C.evaluate(present, set(C.ARMED_BY))
    one(fs, "F2")
    one(fs, repr(missing))


def case_f2_stale_armed_by_key():
    # Drop one ARMED_BY arming key from the extracted set — its row is stale.
    all_keys = set(C.NOT_INJECTORS) | {kk for v in C.ARMED_BY.values() for kk in v}
    victim = C.ARMED_BY["nowFrozen"][0]
    fs = C.evaluate(all_keys - {victim}, set(C.ARMED_BY))
    one(fs, "F2")
    one(fs, repr(victim))


# ── F3: a header injector with no ARMED_BY entry ────────────────────────────

def case_f3_injector_missing_armed_by():
    all_keys = set(C.NOT_INJECTORS) | {kk for v in C.ARMED_BY.values() for kk in v}
    fs = C.evaluate(all_keys, set(C.ARMED_BY) | {"phantomInjector"})
    one(fs, "F3")
    one(fs, "phantomInjector")


# ── F4: an ARMED_BY entry naming an injector not in the header ──────────────

def case_f4_armed_by_names_missing_injector():
    all_keys = set(C.NOT_INJECTORS) | {kk for v in C.ARMED_BY.values() for kk in v}
    header = set(C.ARMED_BY) - {"nowFrozen"}
    fs = C.evaluate(all_keys, header)
    one(fs, "F4")
    one(fs, "nowFrozen")


# ── positive controls ────────────────────────────────────────────────────────

def case_live_tree_is_clean():
    keys = G.collect()
    header = C.injectors_in_header()
    none(C.evaluate(keys, header))


def case_header_extraction_matches_design():
    """The design doc (§2.3) lists 16 members (14 initial + spotifyWedge, bgPollOff), plus
    `shellBusy` added by TASK-617 (M-HARNESS2-armed-state-task635.md §2.2 clause 3 — the
    `busyForced` bit is exactly the one new bool the clause allows); the header's own X-macro
    parse must find exactly that many, independent of ARMED_BY."""
    header = C.injectors_in_header()
    assert len(header) == 17, f"expected 17 injectors in armedInjectors.h, got {len(header)}: {header}"


def case_every_armed_by_value_is_a_real_extracted_key():
    """Each ARMED_BY arming key must actually be a `set` key the generator
    finds — otherwise ARMED_BY is asserting something about a command that
    doesn't exist."""
    keys = set(G.collect())
    for inj, arming_keys in C.ARMED_BY.items():
        for k in arming_keys:
            assert k in keys, f"ARMED_BY[{inj!r}] names {k!r}, not a real set key"


def case_no_key_in_both_tables():
    """A key cannot simultaneously be an arming key and a NOT_INJECTORS
    exclusion — that would be a self-contradiction in the ledger."""
    armed_by_keys = {kk for v in C.ARMED_BY.values() for kk in v}
    overlap = armed_by_keys & set(C.NOT_INJECTORS)
    assert not overlap, f"keys in both ARMED_BY and NOT_INJECTORS: {overlap}"


def case_candidate_rows_are_flagged():
    """Any NOT_INJECTORS reason that concedes the three membership clauses
    hold (TASK-635 prompt §5) must carry the CANDIDATE marker so it stays
    visible as a follow-up rather than reading as a normal exclusion."""
    for key, why in C.NOT_INJECTORS.items():
        if "satisfies §2.2" in why:
            assert why.startswith("CANDIDATE — TASK-635 follow-up:"), key


CASES = [
    ("F1  an undeclared key",                    case_f1_undeclared_key),
    ("F1  accounted keys are not flagged",       case_f1_not_raised_for_accounted_keys),
    ("F2  a stale NOT_INJECTORS row",            case_f2_stale_not_injectors_row),
    ("F2  a stale ARMED_BY row",                 case_f2_stale_armed_by_key),
    ("F3  an injector with no ARMED_BY entry",   case_f3_injector_missing_armed_by),
    ("F4  an ARMED_BY entry naming a ghost",     case_f4_armed_by_names_missing_injector),
    ("P1  the live tree is clean",               case_live_tree_is_clean),
    ("P2  header extraction finds 17",           case_header_extraction_matches_design),
    ("P3  every ARMED_BY key is real",           case_every_armed_by_value_is_a_real_extracted_key),
    ("P4  no key in both tables",                case_no_key_in_both_tables),
    ("P5  CANDIDATE rows are marked",            case_candidate_rows_are_flagged),
]


def main() -> int:
    return _case_runner.run_cases("test_check_armed_injectors", CASES)


if __name__ == "__main__":
    sys.exit(main())
