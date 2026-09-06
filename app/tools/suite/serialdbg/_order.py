"""suite/serialdbg/_order.py — class ordering, the on-paper order diff, and the
0->1-edge enumeration. TASK-566, M-TESTARCH §4 / §6 R3 / EC-G9.

THREE THINGS, AND ONLY ONE OF THEM IS ALLOWED TO CHANGE A RUN.

  class_order()      the ordered id sequence classes-ascending. INERT by
                     default: nothing calls it unless --class-order is passed.
  order_diff()       what would change if it were switched on — computed with
                     ZERO DUT TIME, which is the whole argument for the inert
                     stage (design §6 R3: "the baseline then confirms a
                     prediction rather than discovering a surprise").
  edge_candidates()  which assertions CARE that the order changed.

WHY THE DIFF IS A DELIVERABLE AND NOT A DEBUG AID. This suite has measured
order-dependence: TASK-553's `T_PMT_04` failed behind `T_PLR_25` and passed
alone, because `mb_arena_acquire()` early-returns on `if (s_owned) return true;`
BEFORE it increments, so ANY test asserting a 0->1 edge is order-fragile by
construction — not just that one. Reordering by class is therefore not free and
cannot be verified by the suite it reorders (the verification paradox,
M-TESTARCH §9). The diff makes the blast radius predictable on paper before a
single test runs.

WITHIN A CLASS, ORDER IS TODAY'S ORDER. §4 rule 1: "within a class, order is
unspecified (today's family order is retained)". The sort is therefore STABLE
over the incoming sequence, and that is load-bearing — a sort that also
reshuffled inside a class would multiply the blast radius for no stated benefit.

THE SWITCH IS HELD (@PM, task row TASK-566; @VE §18.6). `class_order()` ships
here, tested, diffed and unused. Three preconditions bind its use and none is
this module's to satisfy: an interleaved A/B at one commit, the undeclared flake
candidates adjudicated BEFORE run 1, and this file's `edge_candidates()` output
delivered as a precondition rather than as an output.
"""

from __future__ import annotations

import inspect
import re

from suite.serialdbg import _meta

#: Ascending precedence. A class-N failure must never be reportable as a
#: class-N+1 failure (§4), and this is the only place the order is written down.
CLASS_RANK = {cls: i for i, cls in enumerate(_meta.CLASSES)}

#: Classes a CORE failure blocks (§4 rule 4). APP blocks nothing — rule 5 was
#: DROPPED (§4.2/§15), and the EC-G8 inversion test asserts the drop so it
#: cannot silently come back.
CORE_BLOCKS = ("APP", "FEATURE")


def rank(tid: str, meta: dict) -> int:
    """Unknown ids sort last, with FEATURE. An id with no record is exactly as
    unblocking as an undeclared one, which is the conservative default
    `_meta.resolve()` already chose."""
    rec = meta.get(tid)
    return CLASS_RANK.get((rec or {}).get("cls", _meta.DEFAULT_CLS),
                          CLASS_RANK[_meta.DEFAULT_CLS])


def class_order(ids, meta: dict) -> list:
    """Ids re-sequenced classes-ascending, STABLE within a class."""
    return sorted(ids, key=lambda t: rank(t, meta))


# ─────────────────────────────────────────────── the on-paper diff (EC-G9)

def inverted_pairs(before, after) -> list:
    """Every (a, b) whose relative order flips: a precedes b in `before` and
    follows it in `after`. Emitted in `before` order so the list reads as "what
    this id loses"."""
    pos = {t: i for i, t in enumerate(after)}
    out = []
    for i, a in enumerate(before):
        if a not in pos:
            continue
        for b in before[i + 1:]:
            if b in pos and pos[b] < pos[a]:
                out.append((a, b))
    return out


def moves(before, after) -> list:
    """(tid, old_index, new_index, delta) for every id whose index changes."""
    pos = {t: i for i, t in enumerate(after)}
    return [(t, i, pos[t], pos[t] - i)
            for i, t in enumerate(before) if t in pos and pos[t] != i]


# ───────────────────────────────────── the 0->1-edge enumeration (§6 R3)

#: A counter field whose ABSOLUTE value is asserted against 0 or 1 is an edge
#: assertion by another name: it is only true of a particular history.
_COUNTER_WORDS = (
    "acquires", "releases", "active", "arenaheld", "held", "owned", "fails",
    "hwm", "count", "switches", "trips", "disc", "drops", "resets", "n",
)

#: A baseline captured, then compared against — the TASK-553 shape exactly.
_BASELINE_ASSIGN = re.compile(
    r"^\s*(?:_)?(base\w*|before\w*|prev\w*|start\w*|b0)\s*=\s*[^=].*", re.M)
_BASELINE_USE = re.compile(
    r"(?:base\w*|before\w*|prev\w*|start\w*|b0)\s*(?:[<>!=]=|[<>+-])")

#: An absolute assertion on a counter word against 0 or 1.
_ABS_EDGE = re.compile(
    r"[\"']?(" + "|".join(_COUNTER_WORDS) + r")[\"']?\s*\)?\s*(?:[<>!=]=|[<>])\s*[01]\b",
    re.I)
_ABS_EDGE_REV = re.compile(
    r"\b[01]\s*(?:[<>!=]=|[<>])\s*[\"']?(" + "|".join(_COUNTER_WORDS) + r")[\"']?",
    re.I)


#: Triple-quoted blocks. A docstring is PROSE — `acquires > 0 AND active == 0`
#: in T_PMT_04's own docstring matched the absolute-edge pattern and reported the
#: test's description as its evidence. Stripping them cut the noise roughly in
#: half without losing a single real assertion.
_DOCSTRING = re.compile(r'("""|\'\'\')(?:.|\n)*?\1')


def _strip_docstrings(src: str) -> str:
    return _DOCSTRING.sub("", src)


def _lines_matching(src: str, *regexes) -> list:
    out = []
    for ln in src.splitlines():
        stripped = ln.strip()
        if stripped.startswith("#"):
            continue                       # a comment is not an assertion
        for rx in regexes:
            if rx.search(ln):
                out.append(stripped)
                break
    return out


def edge_shape(fn) -> dict:
    """-> {'delta': [lines], 'absolute': [lines]} for one test function.

    Deliberately OVER-reports and says so. This is a CANDIDATE list requiring
    adjudication, not a verdict: a scanner that under-reports here hands the
    order switch a false all-clear, and the switch is the riskiest change in
    the design. Comment lines are excluded — TASK-553's own explanation of the
    shape sits in a 20-line comment and would otherwise match itself.
    """
    if fn is None:
        return {"delta": [], "absolute": []}
    try:
        src = _meta._reachable_source(fn)
    except Exception:                                       # pragma: no cover
        return {"delta": [], "absolute": []}
    src = _strip_docstrings(src)
    delta = []
    if _BASELINE_ASSIGN.search(src) and _BASELINE_USE.search(src):
        delta = _lines_matching(src, _BASELINE_USE)
    absolute = _lines_matching(src, _ABS_EDGE, _ABS_EDGE_REV)
    return {"delta": delta, "absolute": absolute}


def edge_candidates(tests: dict) -> dict:
    """id -> edge_shape, for every id that matches either shape."""
    out = {}
    for tid, fn in tests.items():
        shape = edge_shape(fn)
        if shape["delta"] or shape["absolute"]:
            out[tid] = shape
    return out


# ─────────────────────────────────────── the adjudication (EC-G9, precondition)

#: Verdicts. Deliberately four, and the two that are NOT "dismissed" are split
#: by DIRECTION, because the direction is what decides whether the switch can
#: hide a defect or merely manufacture a red cell:
#:   EDGE             asserts a first-occurrence / at-rest state a predecessor
#:                    can consume or spoil -> FALSE RED (or a false green once
#:                    the assertion is spoilt). The TASK-553 shape.
#:   ORDER-SENSITIVE  needs a predecessor's state, or degrades to a SKIP when a
#:                    predecessor leaves the wrong state -> a silent NON-RESULT.
#:   VACUITY          an absolute assertion a predecessor can pre-satisfy ->
#:                    FALSE GREEN. Never a red, which is why it is the easiest
#:                    of the four to leave unnoticed.
#:   DISMISSED        establishes its own precondition inside the test body.
EDGE_VERDICTS = ("EDGE", "ORDER-SENSITIVE", "VACUITY", "DISMISSED")

#: The EC-G9 enumeration, adjudicated 2026-09-02 against the scanner's 20
#: candidates. @VE §18.6(c) requires this as a PRECONDITION of the order switch,
#: not as an output of the runs that switch produces — so it lives in the tree,
#: it is regenerable (`runner.py --order-diff`), and `test_class_order.py`
#: asserts that NO candidate is missing from it. A new order-fragile test cannot
#: be added without someone adjudicating it.
EDGE_ADJUDICATION = {
    "T_PMT_04": ("EDGE",
                 "THE reference case (TASK-553). mb_arena_acquire() early-returns "
                 "on `if (s_owned) return true;` BEFORE incrementing, so the 0->1 "
                 "acquire edge is invisible once anything else holds the arena. "
                 "Already carries a precondition SKIP for a held arena at "
                 "baseline. Leg B only."),
    # "T178" held the highest-risk EDGE row in the reorder. The id was
    # RETIRED 2026-09-05 (TASK-603): its oracle read back two fields its own
    # `set triggerFetch 1` had written, so the order risk it carried was risk
    # of a false result on an assertion that could not be true or false.
    # docs/verification/retired_test_ids.md.
    "T-BUSY-01": ("ORDER-SENSITIVE",
                  "Its own TASK-386 comment records the 'chartLen never exceeded "
                  "0' failure as suite-accumulated-state-dependent. TASK-626 "
                  "(2026-09-06) demoted it to FEATURE, so it no longer moves to "
                  "the front under class order — it stays at ~180 and its "
                  "exposure is UNCHANGED by the switch, where before the "
                  "demotion the switch decreased it. Still listed: the order "
                  "sensitivity is a property of the body, not of the class."),
    "T165": ("ORDER-SENSITIVE",
             "Requires tbScrollOffset==0 and SKIPs when a predecessor left it "
             "non-zero. A silent non-result, never a red — the failure mode "
             "TASK-574 is cataloguing elsewhere."),
    "T173": ("ORDER-SENSITIVE",
             "Needs lastQuoteFetch != 0, i.e. a predecessor must ALREADY have "
             "fetched; SKIPs otherwise. The inverse dependency to T178's, and it "
             "moves in the opposite direction to its benefit."),
    "T196": ("VACUITY",
             "heatmapCount > 0 is absolute, so a predecessor's screener fetch "
             "pre-satisfies it and the cell goes green without asserting the "
             "trigger it names."),
    "T193": ("VACUITY",
             "chart_len > 0 absolute, and enterHeatmap() deliberately re-uses "
             "cached data when lastHeatmapFetch != 0 — so predecessor state can "
             "carry the assertion."),
    "T-CDWN-02": ("DISMISSED",
                  "Was: compares against `n = _stock_ok_count(dut)` read "
                  "in-test, a delta and not an edge. TASK-626 (2026-09-06) split "
                  "the fetch-count assertion out to `T-CDWN-04`, so this id now "
                  "reads no counter at all — DISMISSED a fortiori. It is still "
                  "CORE and still moves to the front, where its TLS connection "
                  "is colder; the 'warm connection completed before tap2' exit "
                  "is therefore LESS likely, and it is now a `fail()` behind a "
                  "`shellBusy` guard rather than a green skip."),
    # @VE ruling 2026-09-04 (TASK-584 sweep). TASK-596's author filed this
    # DISMISSED and asked for confirmation. The DIAGNOSIS is confirmed exactly,
    # mechanically: `edge_shape(T176)` reports one line and only one — the
    # `dut_int(q, "yieldCount") == 0` inside `_drain_data_pipeline`, reached
    # transitively — and re-adding the `, 1` removes the match, so the defaulted
    # read was indeed all that kept the row out. It is not a re-grading of T176,
    # whose oracle is `_wait_chart_complete`'s fetchOkCount DELTA.
    #
    # The VERDICT is CORRECTED, DISMISSED -> ORDER-SENSITIVE. DISMISSED is
    # defined above as "establishes its own precondition inside the test body",
    # and T176 does not establish this one: it WAITS for shared pipeline state to
    # go quiet and `skip()`s after 200 s if it never does (`stock.py`, the
    # `_drain_data_pipeline` guard). That is ORDER-SENSITIVE's definition
    # verbatim — "degrades to a SKIP when a predecessor leaves the wrong state ->
    # a silent NON-RESULT" — and it is exactly the readiness-flag-SKIP shape WP-B
    # `B-4` says this enumeration under-reports, in the direction that grants a
    # false all-clear. The body's own comment documents the dependence ("in
    # full-suite order the drill-in's chart fetch serializes behind an in-flight
    # Spotify poll"), and T1's three armed injectors are live candidates for
    # leaving the pipeline non-quiet. Dismissing the row closes it; this verdict
    # keeps it in the A/B, which is the conservative direction and costs nothing
    # while the switch is HELD. TASK-592 owns adding the scanner that would have
    # found this shape without a defaulted read being deleted first.
    "T176": ("ORDER-SENSITIVE",
             "Surfaced 2026-09-04 by TASK-596, and it is a SCANNER artefact, not "
             "a new risk: `_drain_data_pipeline`'s quiet test read "
             "`q.get(\"yieldCount\", 1) == 0` and now reads "
             "`dut_int(q, \"yieldCount\") == 0`, which is the same condition with "
             "the defaulted read removed — the `, 1` was all that kept it out of "
             "_ABS_EDGE. The line is a PRECONDITION on shared pipeline state that "
             "the helper polls until true, not T176's assertion; T176's oracle is "
             "`_wait_chart_complete`'s fetchOkCount DELTA, which the scanner does "
             "not flag. T178, T-BUSY-01 and T_WR_TLS_01 call the same helper and "
             "already carry rows. @VE 2026-09-04: diagnosis CONFIRMED "
             "mechanically (edge_shape reports that one line and no other); "
             "verdict CORRECTED to ORDER-SENSITIVE, because the helper WAITS "
             "for this precondition and skips at 200 s rather than establishing "
             "it, which is a readiness-flag SKIP (WP-B `B-4`), not a dismissal. "
             "Still not a re-grading of T176's oracle. See the comment above."),
    "T_DTP_02": ("ORDER-SENSITIVE",
                 "Filed 2026-09-06 with the id (TASK-657, oracle sweep A-6). Same "
                 "shape as T176 above and for the same single reason: it calls "
                 "`_drain_data_pipeline`, whose quiet test is the absolute read "
                 "`dut_int(q, \"yieldCount\") == 0`. That line is a PRECONDITION on "
                 "shared pipeline state which the helper polls until true, not "
                 "T_DTP_02's assertion — the assertion is that `stockChartProgress` "
                 "leaves its -1 sentinel across a fetch whose completion is decided "
                 "by a fetchOkCount DELTA. ORDER-SENSITIVE and not DISMISSED for "
                 "T176's stated reason: the helper WAITS for the precondition and "
                 "gives up at 200 s rather than establishing it, which is a "
                 "readiness SKIP (WP-B `B-4`) — here routed to UNMET rather than "
                 "SKIP, since a window with no fetch in it is a premise failure, "
                 "not a configuration statement. Sibling T_DTP_01 is not a "
                 "candidate: it drives the quote fetch the app's own switch-in "
                 "enqueues and reads no shared-state precondition."),
    "T163": ("DISMISSED", "expected = (baseline + 1) % N against a baseline read "
                          "immediately before the drag."),
    "T164": ("DISMISSED", "Sets tbScrollOffset=1 itself before measuring."),
    "T_GOL_04": ("DISMISSED", "Switches to Life and waits for its own ticks."),
    "T_PLR_11": ("DISMISSED", "Absolute counts derived from an on-card fixture."),
    "T_PLR_16": ("DISMISSED", "Absolute counts derived from an on-card fixture."),
    "T_WR_COEX_01": ("DISMISSED", "Station count from the test's own fetch."),
    "T_WR_SPOTIFY_RESUME_01": ("DISMISSED", "Station count from its own fetch."),
    "T_WR_TLS_01": ("DISMISSED", "Station count from its own fetch."),
    "T_WR_VIS_01": ("DISMISSED", "Station count from its own fetch."),
    "T_WR_VIS_02": ("DISMISSED", "Station count from its own fetch."),
    "T_WR_VIS_04": ("DISMISSED", "Station count from its own fetch."),
    # "T_WR_VOL_03" retired UNOBSERVABLE 2026-09-05 (TASK-603).
}


def unadjudicated(tests: dict) -> list:
    """Candidate ids with no EDGE_ADJUDICATION row. Must be empty before the
    order switch runs (@VE §18.6(c))."""
    return sorted(set(edge_candidates(tests)) - set(EDGE_ADJUDICATION))


# ──────────────────────────────────────────────────────── the report (EC-G9)

def order_diff_report(selected, meta: dict, tests: dict = None,
                      full_pairs: bool = False) -> str:
    """The whole of EC-G9's on-paper half, as text. No DUT, no port, no build."""
    before = list(selected)
    after = class_order(before, meta)
    mv = moves(before, after)
    pairs = inverted_pairs(before, after)
    cand = edge_candidates(tests or {})
    moved = {t for t, _, _, _ in mv}

    L = []
    A = L.append
    A("── TASK-566 order diff — class order vs today's registry order ──")
    A(f"ids: {len(before)}   moved: {len(mv)}   inverted pairs: {len(pairs)}")
    A("")
    A("class census (ascending; this IS the execution order under the switch):")
    for cls in _meta.CLASSES:
        ids = [t for t in after if (meta.get(t) or {}).get("cls") == cls]
        A(f"  {cls:<8} {len(ids):>4}"
          + (f"   {ids[0]} … {ids[-1]}" if ids else ""))
    unknown = [t for t in after if t not in meta]
    if unknown:
        A(f"  (no record) {len(unknown)}  -> sorted with FEATURE: {unknown}")
    A("")
    if not mv:
        A("NO id changes position. The switch is a no-op for this selection.")
    else:
        A(f"ids that MOVE ({len(mv)}) — old -> new (delta):")
        for tid, i, j, d in mv:
            rec = meta.get(tid) or {}
            A(f"  {tid:<22} {i:>4} -> {j:<4} ({d:+d})  "
              f"{rec.get('cls', '?'):<8} {rec.get('scope', '?')}")
    A("")
    A(f"0->1-EDGE CANDIDATES ({len(cand)}) — assertions that CARE about order")
    A("  (enumerated over the WHOLE registry, not just this selection.")
    A("  (§6 R3: mb_arena_acquire() early-returns before incrementing, so any")
    A("   test asserting an acquire edge is order-fragile BY CONSTRUCTION.")
    A("   Over-reports on purpose — this is a list to adjudicate, not a verdict.)")
    order = {v: i for i, v in enumerate(EDGE_VERDICTS)}
    for tid in sorted(cand, key=lambda t: (order.get(
            EDGE_ADJUDICATION.get(t, ("",))[0], 99), t)):
        rec = meta.get(tid) or {}
        # Three states, not two: the candidate list is enumerated over the
        # WHOLE registry (R3 asks which assertions have the shape, not which
        # happen to be selected today), so an id outside this selection must not
        # be reported as "stays" — that reads as "checked, unaffected".
        flag = ("MOVES" if tid in moved
                else "stays" if tid in before else "not-sel")
        verdict, why = EDGE_ADJUDICATION.get(tid, ("!! UNADJUDICATED", ""))
        A(f"  [{flag:^7}] {tid:<22} {rec.get('cls', '?'):<8} "
          f"{rec.get('scope', '?'):<12} {verdict}")
        if why:
            A(f"           {why}")
        for kind in ("delta", "absolute"):
            for ln in cand[tid][kind][:3]:
                A(f"           {kind}: {ln[:96]}")
    missing = sorted(set(cand) - set(EDGE_ADJUDICATION))
    A("")
    tally = {v: 0 for v in EDGE_VERDICTS}
    for tid in cand:
        v = EDGE_ADJUDICATION.get(tid, ("",))[0]
        if v in tally:
            tally[v] += 1
    A("adjudication: " + "  ".join(f"{v}={tally[v]}" for v in EDGE_VERDICTS))
    if missing:
        A(f"!! {len(missing)} UNADJUDICATED: {missing}")
        A("!! @VE §18.6(c): the enumeration is a PRECONDITION of the order "
          "switch, not an output. The switch must not run until this is empty.")
    A("")
    risky = [(a, b) for a, b in pairs if a in cand or b in cand]
    A(f"INVERTED PAIRS TOUCHING AN EDGE CANDIDATE: {len(risky)} of {len(pairs)}")
    for a, b in (risky if full_pairs else risky[:60]):
        A(f"  {a} now runs AFTER {b}")
    if not full_pairs and len(risky) > 60:
        A(f"  … {len(risky) - 60} more (--full)")
    if full_pairs:
        A("")
        A(f"ALL INVERTED PAIRS ({len(pairs)}):")
        for a, b in pairs:
            A(f"  {a} now runs AFTER {b}")
    return "\n".join(L)
