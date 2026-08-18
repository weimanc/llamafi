#!/usr/bin/env python3
"""Negative tests for check_app_conformance.py — BP-068.

A gate that has never been seen to fail is not a gate. Each case below MUTATES
the source (or the ledger) the way the checker is meant to catch, in memory, and
asserts the finding appears. Two positive controls guard the other direction: an
excepted finding must be suppressed, and an unmutated corpus must not produce the
mutation's finding.

Every mutation is anchored on an exact source string and asserts the anchor's
occurrence count first, so a refactor that moves the code makes these tests FAIL
rather than silently no-op — the failure mode that makes mutation suites rot.

No DUT, no build, no network. Run: python3 app/tools/test_check_app_conformance.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_app_conformance as C  # noqa: E402

DATA = "app/src/dataTaskStorage.cpp"
CMDGET = "app/src/debug/serialConsole/cmdGet.h"
LEDGER_ROW = {"why": "test fixture", "owner": "TASK-483",
              "since": "2026-08-18", "line": 0}

_BASE: dict[str, str] | None = None


def base_srcs() -> dict[str, str]:
    global _BASE
    if _BASE is None:
        _BASE = C.sources()
    return dict(_BASE)


def edit(srcs, rel, needle, repl, expect=1):
    n = srcs[rel].count(needle)
    if n != expect:
        raise AssertionError(
            f"anchor moved: {rel} contains {n} copies of {needle!r}, expected "
            f"{expect}. Re-anchor this mutation — do not delete it.")
    srcs[rel] = srcs[rel].replace(needle, repl)
    return srcs


def findings(srcs, ledger=None, apps=None):
    old = C.APP_ORDER
    if apps is not None:
        C.APP_ORDER = apps
    try:
        return C.evaluate(srcs, ledger or {})
    finally:
        C.APP_ORDER = old


def has(res, frag) -> bool:
    return any(frag in f for f in res["failures"])


# ── cases ─────────────────────────────────────────────────────────────────────

def case_a5_yield_removed():
    """A5: drop the tlsYield() that brackets the Teletext fetch."""
    s = edit(base_srcs(), DATA,
             'spotifyTask::tlsYield();\n    LOG_HEAP("dataTask.teletext");',
             'LOG_HEAP("dataTask.teletext");')
    r = findings(s)
    assert has(r, "A5/Teletext"), r["failures"]
    assert r["a5_cells"]["Teletext"] == "FAIL", r["a5_cells"]
    # control: the untouched corpus does not report it
    assert not has(findings(base_srcs()), "A5/Teletext")


def case_a5_resume_removed():
    """A5: drop the tlsResume() at the end of the Weather fetch."""
    s = edit(base_srcs(), DATA,
             "s_weatherFetchPhase = -1;\n    spotifyTask::tlsResume();",
             "s_weatherFetchPhase = -1;")
    r = findings(s)
    assert has(r, "A5/Weather"), r["failures"]
    assert r["a5_cells"]["Weather"] == "FAIL", r["a5_cells"]


def case_a5_caller_bracket_removed():
    """A5: prFetchOnce() never brackets itself — its CALLER does. Remove the
    caller's yield and the site must fail, or the caller-level analysis is a
    rubber stamp that passes anything a helper is called from."""
    s = edit(base_srcs(), DATA,
             'spotifyTask::tlsYield();   // BP-031: free Spotify TLS before our own handshake\n'
             '    LOG_HEAP("dataTask.planeradar");',
             'LOG_HEAP("dataTask.planeradar");')
    r = findings(s)
    assert has(r, "A5/PlaneRadar"), r["failures"]
    assert r["a5_cells"]["PlaneRadar"] == "FAIL", r["a5_cells"]


def case_a6_defined_but_unwired():
    """A6: AquariumApp keeps its dbgGet(), but cmdGet.h stops calling it. This
    is NEW-APP-CHECKLIST item 3's second bullet — the surface exists and is
    unreachable, which a `grep dbgGet` over the app header cannot see."""
    s = edit(base_srcs(), CMDGET,
             "if (aquariumDbgGet(args, buf, sizeof(buf))) {",
             "if (false) {")
    r = findings(s)
    assert has(r, "A6/Aquarium"), r["failures"]
    assert r["a6_cells"]["Aquarium"] == "FAIL", r["a6_cells"]


def case_a6_new_app_is_visible_not_absent():
    """The Aquarium lesson (M-TESTARCH §2.1): a newly registered app with no
    coverage must produce a FAILING cell, never a missing one. Simulates the
    next APP_X row landing in appRegistry.h."""
    apps = list(C.APP_ORDER) + ["Fizz"]
    r = findings(base_srcs(), apps=apps)
    assert "Fizz" in r["a6_cells"], r["a6_cells"]
    assert r["a6_cells"]["Fizz"] == "FAIL", r["a6_cells"]
    assert r["a5_cells"]["Fizz"] == "n/a", r["a5_cells"]
    assert has(r, "A6/Fizz"), r["failures"]


def case_stale_ledger_row():
    """A row whose finding no longer exists is itself a failure — the rule that
    makes the list shrink instead of calcify (C6 ledger rule 2)."""
    r = findings(base_srcs(), ledger={("A6", "Teletext"): dict(LEDGER_ROW)})
    assert has(r, "stale exception A6/Teletext"), r["failures"]
    assert has(r, "delete this row"), r["failures"]


def case_stale_a5_row():
    """Same rule on the A5 side: an exception for a site that brackets fine."""
    key = ("A5", f"{DATA}:fetchTeletext")
    r = findings(base_srcs(), ledger={key: dict(LEDGER_ROW)})
    assert has(r, "stale exception A5/"), r["failures"]


def case_exception_suppresses():
    """Positive control: an excepted finding is suppressed AND consumes its row
    (so it is not also reported stale)."""
    s = edit(base_srcs(), CMDGET,
             "if (aquariumDbgGet(args, buf, sizeof(buf))) {",
             "if (false) {")
    r = findings(s, ledger={("A6", "Aquarium"): dict(LEDGER_ROW)})
    assert not has(r, "A6/Aquarium"), r["failures"]
    assert not has(r, "stale"), r["failures"]
    assert r["a6_cells"]["Aquarium"] == "EXCEPT", r["a6_cells"]


def case_ledger_row_needs_task_and_date():
    """A ledger row missing its owning TASK or ISO date must not parse."""
    import tempfile
    good = ("## Ledger\n\n| row | subject | why | owner | since |\n|---|---|---|---|---|\n"
            "| `A6` | `Weather` | reason | TASK-483 | 2026-08-18 |\n")
    bad = ("## Ledger\n\n| row | subject | why | owner | since |\n|---|---|---|---|---|\n"
           "| `A6` | `Weather` | reason | | |\n")
    with tempfile.TemporaryDirectory() as d:
        for text, want_rows, want_err in ((good, 1, 0), (bad, 0, 1)):
            p = Path(d) / "led.md"
            p.write_text(text)
            old, C.LEDGER = C.LEDGER, p
            try:
                rows, errs = C.load_ledger()
            finally:
                C.LEDGER = old
            assert len(rows) == want_rows, (text, rows)
            assert len(errs) == want_err, (text, errs)


def case_app_list_is_never_typed():
    """M-TESTARCH §2.4 item 2: the domain comes from the generated registry, so
    the checker must contain no app name of its own. A typed list is how the app
    order got hardcoded into the suite in the first place."""
    src = Path(C.__file__).read_text()
    typed = [a for a in C.APP_ORDER if f'"{a}"' in src or f"'{a}'" in src]
    assert not typed, f"app name(s) typed into the checker: {typed}"


CASES = [
    ("N1 A5 yield removed",            case_a5_yield_removed),
    ("N2 A5 resume removed",           case_a5_resume_removed),
    ("N3 A5 caller bracket removed",   case_a5_caller_bracket_removed),
    ("N4 A6 defined but unwired",      case_a6_defined_but_unwired),
    ("N5 A6 new app visible not absent", case_a6_new_app_is_visible_not_absent),
    ("N6 stale A6 ledger row",         case_stale_ledger_row),
    ("N7 stale A5 ledger row",         case_stale_a5_row),
    ("N8 exception suppresses (control)", case_exception_suppresses),
    ("N9 ledger row needs TASK + date", case_ledger_row_needs_task_and_date),
    ("N10 app list is never typed",     case_app_list_is_never_typed),
]


def main() -> int:
    failed = 0
    for name, fn in CASES:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
    print(f"test_check_app_conformance: {len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
