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

import ast
import inspect
import re

from suite.serialdbg import _meta
from suite.serialdbg import _restore_scan as _rs

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


# ────────────────────────── the two TASK-592 shapes (B-4(a) and B-4(b)) ─────
#
# WP-B §5.4 found the counter-word/baseline scanner above under-reports two
# shapes, in the direction that hands the class-order switch a false
# all-clear: a readiness-flag precondition SKIP (`T_WX_04`/`T_CX_04`, §5.3),
# and an in-RAM setting a test or its reachable helper writes and no exit path
# restores (`stockMode`/`bgPoll`/injected error state, §5.2 clusters C1/C2/C5).
# B-4's own proposal names both; this is that scanner, added rather than
# forked into a second tool (feedback_extend_dont_fork_tools.md).

#: `get <field>` — the literal command-string form of a device read.
_GET_FIELD_RE = re.compile(r"^\s*get\s+([A-Za-z_][A-Za-z0-9_]*)\b")

#: Dut accessor methods that read one named field directly (`lib/dut.py`).
_READ_METHODS = frozenset({"get_int", "get_bool", "get_str"})


def _read_field(call: ast.AST):
    """-> field name if this Call reads one named device field, else None.

    Deliberately loose about WHICH json key the reply answers under (firmware
    is free to echo `get weatherReady` as `{"ready": ...}`), because nothing
    here needs that mapping: the shape below ties the READ CALL to the guard
    that follows it by dataflow (the variable it was assigned to, or the call
    used inline), never by matching key names.
    """
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
        return None
    attr = call.func.attr
    if attr in _READ_METHODS and call.args:
        t = _rs._leading_text(call.args[0])
        return t if t and t.isidentifier() else None
    if attr in _rs.WIRE_METHODS and call.args:
        t = _rs._leading_text(call.args[0])
        if t:
            m = _GET_FIELD_RE.match(t)
            if m:
                return m.group(1)
    return None


#: TASK-635 armed injectors (`app/src/debug/armedInjectors.h` — the ONE table
#: `get armed`/`set injclear` both expand). A leak in one of these fields is
#: now caught at RUNTIME by that mechanism regardless of suite order (design
#: doc §2, `get armed` reads the firmware's own state directly), so it is not
#: this scanner's job to re-report it as an order-dependence candidate. Named
#: by the DEVICE-FACING key the suite writes, not the C++ variable: `wrDeadUrls`
#: and `prClearInject` are literal `X(name, …)` table entries; `prInjectAircraft`
#: is the arm-side key for the `prInject` row (`dbgArmedInjected()` reads what
#: `set prInjectAircraft` writes). Kept to the fields actually seen in the
#: suite; the table itself has more rows the suite does not touch.
_TASK635_INJECTOR_FIELDS = frozenset({
    "wrDeadUrls", "wrPosbarSimDrain", "prInjectAircraft", "prClearInject",
})

#: A reboot/restart wipes ALL RAM state, so any mutation earlier in the same
#: function cannot leak to a successor id through the mechanism this shape
#: is about (an in-RAM value read by a later test). `_meta._RESET_VERBS`
#: already names the two verbs the suite's own `effect` axis keys off.
_REBOOT_VERBS = _meta._RESET_VERBS


def _own_source(fn):
    """The test's OWN body only — NOT `_meta._reachable_source`'s transitive
    walk into shared helpers.

    TASK-592 measured the transitive form first and it over-reports by two
    orders of magnitude for these two shapes specifically: `_restore_spotify`
    (called by ~130 ids) and `_switch_to_stock` (~40) each contribute ONE
    write, attributed to every caller, which buries the handful of ids that
    actually carry the risk (B-6/B-7's direct, in-body, one-way writes) under
    hundreds of ids that merely call a shared normalising helper. Those
    helpers' OWN leaks are not rediscovered here — they are already the
    named findings B-5 (`stockMode`) and the `_restore_spotify`/C3 note in
    §5.2 of the taxonomy review — so nothing is lost, only mis-attributed
    volume. `delta`/`absolute` above are unaffected; they still use the full
    reachable source, unchanged.
    """
    try:
        return inspect.getsource(fn)
    except (OSError, TypeError):                              # pragma: no cover
        return ""


def _written_fields(tree: ast.AST) -> set:
    """Every field this source writes with `set <field>`/`set_val` — the
    operationalisation of "a field the test does not itself write" (B-4(a)'s
    own wording). Reused, not re-derived: this is exactly
    `_restore_scan._mutation_var`'s notion of a device write."""
    out: set = set()
    for node in ast.walk(tree):
        is_mut, var = _rs._mutation_var(node)
        if is_mut and var:
            out.add(var)
    return out


def _has_reboot(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        is_mut, var = _rs._mutation_var(node)
        # A bare `reboot`/`restart` command is a WIRE_METHODS call whose
        # text is the verb itself, not a `set` — _mutation_var only matches
        # `set`-shaped writes, so check the raw command text directly here.
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in _rs.WIRE_METHODS and node.args:
            t = _rs._leading_text(node.args[0])
            if t and t.strip().split()[0:1] and \
                    t.strip().split()[0].lower() in _REBOOT_VERBS:
                return True
    return False


def _readiness_hits(tree: ast.AST, src: str, written: set) -> list:
    """B-4(a) — 'any `skip(...)` whose guard reads a device field the test
    does not itself write.'

    Tracks a read call (`get_bool("weatherReady")`, `dut.cmd("get X")`, …) to
    the `if` that guards a `skip(...)` two ways: through a simple
    `var = <read>()` assignment (T_WX_04's `r_pre = dut.cmd(...)` then
    `if r_pre.get("ready") is True:`), and inline (the read call sitting
    directly in the `if`'s test). Both are OVER-reporting on purpose — a
    guard that also happens to reference an unrelated read is a candidate
    too, same philosophy as the two shapes above. A field the test itself
    `set`s anywhere in its reachable source is excluded: that is
    DISMISSED-shaped (it establishes its own precondition), not this shape.
    """
    var_field: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            f = _read_field(node.value)
            if f:
                var_field[node.targets[0].id] = f

    hits: list = []
    seen: set = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        fields_here: set = set()
        for n in ast.walk(node.test):
            if isinstance(n, ast.Name) and n.id in var_field:
                fields_here.add(var_field[n.id])
            elif isinstance(n, ast.Call):
                f = _read_field(n)
                if f:
                    fields_here.add(f)
        if not fields_here:
            continue
        has_skip = any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "skip"
            for n in ast.walk(node))
        if not has_skip:
            continue
        for f in sorted(fields_here):
            if f in written or f in seen:
                continue
            seen.add(f)
            seg = ast.get_source_segment(src, node) or ""
            first_line = seg.strip().splitlines()[0] if seg.strip() else "if …"
            hits.append(f"readiness: guard reads {f!r} (never set here) -> "
                        f"skip(): {first_line[:90]}")
    return hits


def _unrestored_hits(tree: ast.AST, src: str) -> list:
    """B-4(b) — 'any `set <key>` in a test or reachable helper with no
    matching restore on all exit paths.'

    Not a second implementation: `gate/check_restore_manager.py`'s own
    per-module ratchet is built on exactly this function
    (`_restore_scan.unrestored_mutations`), moved there-from so both callers
    share it (TASK-592). Run here over the test's OWN body (see
    `_own_source`) and then narrowed twice more:

    * a REBOOT anywhere in the body clears every mutation earlier in it —
      there is no RAM state left for a successor to inherit;
    * a field written TWICE in the same body is treated as locally
      compensated (a plain `try/finally`, or a sequential set-then-reset).
      `check_restore_manager.py` is right not to credit this for R17 — a
      `finally` can restore the wrong variable, or a guessed default, or
      never get acknowledged — but that gate asks "is the mechanism used",
      and this scanner asks a narrower question, "is a value plausibly left
      behind for the NEXT test". A field this body touches twice is not
      abandoned to a successor on the path that matters most (the common
      one); a field touched ONCE with no second write is exactly the
      one-way leak B-6/B-7 describe.
    """
    if _has_reboot(tree):
        return []
    try:
        sites = _rs.unrestored_mutations(src)
    except SyntaxError:                                       # pragma: no cover
        return []
    by_field: dict = {}
    for ln, var in sites:
        by_field.setdefault(var, []).append(ln)
    hits: list = []
    for var, lines in sorted(by_field.items(), key=lambda kv: (kv[0] or "", kv[1])):
        if var in _TASK635_INJECTOR_FIELDS:
            continue          # TASK-635 (app/src/debug/armedInjectors.h): caught
                               # at runtime by `get armed`, regardless of order
        if var is not None and len(lines) >= 2:
            continue          # written more than once in this body — treated as
                               # locally compensated, see docstring above
        label = var or "<dynamic>"
        hits.append(f"unrestored: set {label} (line {lines[0]})")
    return hits


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


#: The four shapes, in report/tally order. TASK-592 adds the last two.
EDGE_SHAPES = ("delta", "absolute", "readiness", "unrestored")

_EMPTY_SHAPE = {k: [] for k in EDGE_SHAPES}


def edge_shape(fn) -> dict:
    """-> {'delta': [...], 'absolute': [...], 'readiness': [...],
    'unrestored': [...]} for one test function.

    Deliberately OVER-reports and says so. This is a CANDIDATE list requiring
    adjudication, not a verdict: a scanner that under-reports here hands the
    order switch a false all-clear, and the switch is the riskiest change in
    the design. Comment lines are excluded from `delta`/`absolute` —
    TASK-553's own explanation of the shape sits in a 20-line comment and
    would otherwise match itself. `readiness` and `unrestored` (TASK-592,
    WP-B finding B-4) are AST-based instead of line-regex, so a docstring
    never matches them in the first place — nothing to strip.
    """
    if fn is None:
        return dict(_EMPTY_SHAPE)
    try:
        raw = _meta._reachable_source(fn)
    except Exception:                                       # pragma: no cover
        return dict(_EMPTY_SHAPE)
    stripped = _strip_docstrings(raw)
    delta = []
    if _BASELINE_ASSIGN.search(stripped) and _BASELINE_USE.search(stripped):
        delta = _lines_matching(stripped, _BASELINE_USE)
    absolute = _lines_matching(stripped, _ABS_EDGE, _ABS_EDGE_REV)
    readiness: list = []
    unrestored: list = []
    # TASK-592: `readiness`/`unrestored` scan the test's OWN body only, not
    # the transitive `raw` above — see `_own_source`'s docstring for why.
    own = _own_source(fn)
    if own:
        try:
            tree = ast.parse(own)
        except SyntaxError:                                 # pragma: no cover
            tree = None
        if tree is not None:
            written = _written_fields(tree)
            readiness = _readiness_hits(tree, own, written)
            unrestored = _unrestored_hits(tree, own)
    return {"delta": delta, "absolute": absolute,
            "readiness": readiness, "unrestored": unrestored}


def edge_candidates(tests: dict) -> dict:
    """id -> edge_shape, for every id that matches at least one shape."""
    out = {}
    for tid, fn in tests.items():
        shape = edge_shape(fn)
        if any(shape[k] for k in EDGE_SHAPES):
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
    "T165": ("DISMISSED",
             "C-19 correction (was ORDER-SENSITIVE): `_tb_precondition` "
             "(_helpers.py:849) itself calls `_tb_set_offset(dut, 0)` before "
             "the body's own `baseline != 0` check ever runs, so the body "
             "establishes its own precondition — the cited `skip()` at "
             "shell.py:2628-2633 for a predecessor-left-nonzero offset is "
             "unreachable in registry order. See t165's own cls_reason "
             "(shell.py) for the same correction."),
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
                  "reads no counter at all — DISMISSED a fortiori. TASK-617 "
                  "(2026-09-13) went further: it no longer touches StockApp, "
                  "TLS or the network AT ALL — the precondition is the "
                  "`shellBusy` armed injector (`set shellBusy 1`), restored via "
                  "`Dut.injected()` on every exit path. There is no warm/cold "
                  "connection state left to share with a predecessor; DISMISSED "
                  "for a second, independent reason now. Still CORE — the "
                  "ORACLE is the shell's own tap gate."),
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

    # ── TASK-592 (WP-B B-4(a)/(b)) — the readiness/unrestored shapes ────────
    #
    # Every row below was read, not generated: each candidate's OWN function
    # body (not the transitive helper chain — see `_own_source`) was opened
    # and the field's firmware handler checked where the verdict depends on
    # it. Two recurring, evidence-backed patterns account for most of the
    # DISMISSED rows and are named once here instead of per row:
    #
    #   TRIGGER-VERB FIELDS. `triggerFetch`/`triggerHeatmap`/
    #   `triggerPlaneRadarFetch`/`triggerTeletextFetch` have no backing field
    #   in firmware at all — `stockApp.cpp:222 "triggerFetch"` and its three
    #   siblings (`stockApp.cpp:246`, `planeRadarApp.cpp:229`,
    #   `teletextApp.cpp:229`) are all `strcmp(val,"1")==0`-guarded ACTIONS
    #   that fire once and return; there is nothing named `triggerFetch` left
    #   armed for a successor to inherit. `fetchErrCount` is the same shape
    #   one step removed: `stockApp.cpp:234-235` resets it to 0 on ANY write,
    #   so "leaving it changed" converges to the one value every future
    #   reader expects anyway.
    #
    #   SELF-CHECKING appId. `dut.cmd("get appId")` immediately after THIS
    #   body's own `switchApp`/`_switch_to`/tap-to-enter call, used only to
    #   confirm that action landed, is not a precondition on session history
    #   — it is the test reading back what it just did. Distinguished per row
    #   from the genuine cases (`T147`, `T_BI_02`, `T_BI_04`, `T078`) where
    #   the SAME shape is the very FIRST statement in the body, before it has
    #   taken any action of its own to confirm.
    #
    # New leaks this pass surfaced that are NOT in B-5/B-6/B-7 or anywhere
    # else in this file (reported to @VE/@PM as findings, bodies untouched
    # per TASK-592's scope): `T270` (teletext subpage injection AND the app
    # switch itself, restored nowhere), `T149/150/153/154` (a synthetic
    # `songDuration` fixture), `T_PLR_21/22/24` (`plCursor`/`plPlay` — real
    # playback-cursor state `_leave_player` does not touch).
    "T-BUSY-01b": ("DISMISSED",
                   "`set triggerFetch 1` (stock.py) is a fire-once action "
                   "(stockApp.cpp:222-231: resets lastQuoteFetch/lastChartFetch/"
                   "chartLen and returns; no persisted `triggerFetch` field "
                   "exists to leak)."),
    "T-BUSY-05": ("DISMISSED",
                  "Same `triggerFetch` action-verb shape as T-BUSY-01b "
                  "(stockApp.cpp:222-231) — nothing is left armed."),
    "T-CDWN-03": ("DISMISSED",
                  "`set triggerFetch 1` (shell.py) — same fire-once action, "
                  "stockApp.cpp:222-231; already CORE-demoted for an unrelated "
                  "reason (TASK-626, its own `cls_reason`)."),
    "T-CDWN-04": ("DISMISSED",
                  "`set fetchErrCount` unconditionally resets the counter to 0 "
                  "(stockApp.cpp:234-235) regardless of the value written — "
                  "converges to the one state every later reader expects."),
    "T091": ("DISMISSED",
             "`set backoff 3` is the seed for the exact mechanism under test — "
             "`reconnect` resetting `consecutiveFailures` — so the passing path "
             "restores it BY DEFINITION. Already declared FLAKY/demoted "
             "(TASK-591) for an unrelated reason."),
    "T078": ("ORDER-SENSITIVE",
             "`if rg.get(\"state\") != \"D_IDLE\": skip(...)` (shell.py) is the "
             "FIRST statement in the body — a genuine precondition on whatever "
             "a predecessor left `dragState` at, not a check of its own action."),
    "T147": ("ORDER-SENSITIVE",
             "`if r.get(\"name\") != \"Spotify\": skip(\"precondition: need "
             "Spotify active\")` (shell.py:1089-1091) is the first statement — "
             "depends on session history, exactly B-3/B-4's shape."),
    "T148": ("DISMISSED",
             "Reads `appId` AFTER its own taskbar tap to Clock (shell.py) — "
             "confirms its own action, not a predecessor's state."),
    "T_BI_02": ("ORDER-SENSITIVE",
                "`# Ensure Spotify active` guard is the first statement "
                "(shell.py:1228-1231), before this body has done anything of "
                "its own — a real precondition on prior state."),
    "T_BI_04": ("ORDER-SENSITIVE",
                "Same first-statement `appId` precondition as T_BI_02 "
                "(shell.py:1339-1341)."),
    "T-SET-08": ("DISMISSED",
                 "The `appId`/`Crypto` guard checks the RESULT of this body's "
                 "own `switchApp` two lines earlier (shell.py:3721-3729) — self, "
                 "not a predecessor."),
    "T192": ("DISMISSED",
             "`stockSubView`/`stockChartRange` are read right after this body's "
             "own tab-tap/`triggerHeatmap` (stock.py) to confirm ITS transition "
             "landed; `triggerHeatmap` is the fire-once action documented above."),
    "T201": ("DISMISSED", "Same self-check shape as T192 — reads `stockSubView` "
                          "immediately after its own `set triggerHeatmap 1` "
                          "(stock.py:1214-1221)."),
    "T202": ("DISMISSED", "Same self-check shape as T192 (stock.py)."),
    "T203": ("DISMISSED", "Same self-check shape as T192 (stock.py)."),
    "T272": ("DISMISSED",
             "`triggerTeletextFetch` is the same fire-once action shape "
             "(teletextApp.cpp:229); the `lastPlaylistDraw` guard "
             "(`if not r0.get(\"ok\")`) tests whether the READ succeeded, not "
             "the field's value — not a readiness precondition at all."),
    "T276": ("DISMISSED",
             "The `finally:` block (webradio.py) issues `set wrStop 1`, which "
             "stops playback the `set wrPlay 0` earlier in the body started — "
             "functionally negated on every exit path even though it is a "
             "different field name, which the paired-write heuristic does not "
             "recognise as a match."),
    "T_CLK_03": ("DISMISSED",
                 "Ends with `_restore_spotify_from_clock(dut)`, which issues "
                 "`set clockStyle 0` (clock.py:19) — restored on the pass path. "
                 "The scanner's own-body-only view can't see across that call "
                 "boundary; T_CLK_12 below is the sibling that skips it."),
    "T_CLK_04": ("DISMISSED", "Same `_restore_spotify_from_clock` restore as "
                              "T_CLK_03 (clock.py:19)."),
    "T_CLK_05": ("DISMISSED", "Same `_restore_spotify_from_clock` restore as "
                              "T_CLK_03 (clock.py:19)."),
    "T_CLK_06": ("DISMISSED", "Same `_restore_spotify_from_clock` restore as "
                              "T_CLK_03 (clock.py:19)."),
    "T_CLK_08": ("DISMISSED", "Same `_restore_spotify_from_clock` restore as "
                              "T_CLK_03 (clock.py:19)."),
    "T_CLK_10": ("DISMISSED", "Same `_restore_spotify_from_clock` restore as "
                              "T_CLK_03 (clock.py:19)."),
    "T_CLK_12": ("ORDER-SENSITIVE",
                 "The taxonomy review's own named exception (§5.2 C4): "
                 "`t_clk_12` sets styles 0..3 in a loop (clock.py:200-201) and "
                 "`pass_()`es with NO restore call at all — leaves clockStyle=3 "
                 "for whatever runs next."),
    "T_CX_04": ("ORDER-SENSITIVE",
                "THE OTHER flagship case named in B-3/B-4 alongside T_WX_04. "
                "FIXED (TASK-594): the `if r_pre.get(\"ready\") is True: ...` "
                "branch now calls `unmet(...)` naming its own predecessors "
                "(T_CX_01/T_CX_03), not `skip(...)` — a full-suite run "
                "honestly reports UNMET instead of a false-green SKIP. "
                "cryptoReady is still LATCHED and this id still cannot "
                "PASS twice in one boot's full-suite order; that is now "
                "visible instead of hidden. No firmware reset exists for "
                "this latch (it is a deliberate never-re-armed design per "
                "cryptoApp.h), so `set cryptoReady 0` was rejected as an "
                "injector-shaped fake reversal rather than added as a "
                "NOT_INJECTORS boot-value reset — see "
                "gate/check_armed_injectors.py. No longer matched by "
                "`_readiness_hits` (which greps for `skip(` only) since the "
                "false-green shape B-4(a) targets no longer applies once the "
                "verdict is UNMET; kept here as the historical record."),
    "T_PLR_06": ("DISMISSED",
                 "`set fbCancel` is a fire-once cancel action "
                 "(cmdSet.cpp:376-378, no persisted field) and the body ends "
                 "with `_restore_spotify(dut)`."),
    "T_PLR_14": ("DISMISSED",
                 "`get shellBusy` (player.py:794) reads back whether THIS "
                 "body's own eject tap is still mid-walk — a timing check on "
                 "its own just-taken action, not inherited state."),
    "T_PLR_24": ("ORDER-SENSITIVE",
                 "NEW: `set plPlay <idx>` (cmdSet.cpp:237-246) really calls "
                 "`dbgPlayRow()`. The body taps STOP afterward on the pass "
                 "path, which likely mitigates it in practice, but "
                 "`_leave_player` still does not restore cursor/play state, so "
                 "a FAIL exit before the STOP tap leaves it changed."),
    "T_PR_03": ("DISMISSED",
                "Sets `prRange 5` itself as the starting fixture (planeradar.py) "
                "and the 4-tap cycle it asserts (5->10->15->25->5) returns "
                "prRange to that same 5 on the pass path — self-restoring by "
                "the shape of its own oracle."),
    "T_PR_05": ("DISMISSED",
                "`set triggerPlaneRadarFetch 1` is the same fire-once action "
                "shape (planeRadarApp.cpp:229-241)."),
    # H-15 / H-6 (M-TESTQUAL-H-audit-data-apps-review.md): not scanner-detected
    # (`_TASK635_INJECTOR_FIELDS`-shaped exclusions and the boot-scoped latch
    # below are both outside edge_shape()'s regex/AST patterns), added by hand
    # as one of the "three real dependencies this corpus has" the scanner
    # cannot see. Registry indices 0-25 (the 26 data-app ids) otherwise carry
    # no _order.py entries at all.
    "T_PR_02": ("VACUITY",
                "`isConnecting()` is `!_everHadResult` (planeRadarApp.h:244,278), "
                "set true by the first successful poll OR any injection, reset "
                "only by `init()`/`_setActiveLoc()`. T_PR_01 at index 17 is "
                "PlaneRadar's first entry, so `init()` runs there; by T_PR_02 at "
                "18, resume()'s enqueue plus a drained result can pre-satisfy "
                "`connecting == false` within one tick — on any third-or-later "
                "entry the term is pre-satisfied outright. What the id proves is "
                "'a fetch has resolved since boot', not 'within one poll of app "
                "entry'; the render half of exit criterion 1 has no oracle at "
                "all (`prAircraftCount` only interpolated into the pass "
                "string). The same latch is the baseline gate in T_PR_05:180 "
                "and T_PRM_02:349."),
    "T_WR_EJECT_02": ("DISMISSED",
                       "`get appId` (webradio.py) confirms THIS body's own "
                       "`_webradio_enter_with_stations` call landed — self, not "
                       "a predecessor's state."),
    "T_WR_HEAP_03": ("ORDER-SENSITIVE",
                      "EXPLICITLY documented cross-test dependency: the fallback "
                      "branch's own skip messages read \"not in WebRadio — run "
                      "T_WR_COEX_01 first\" / \"no stations loaded — run "
                      "T_WR_COEX_01 first\" (webradio.py:672-679). `set wrPlay 0` "
                      "a few lines later is also left unrestored."),
    "T_WR_HEAP_04": ("ORDER-SENSITIVE", "Same explicit T_WR_COEX_01 dependency "
                                        "and unrestored `wrPlay` as T_WR_HEAP_03 "
                                        "(webradio.py)."),
    "T_WX_04": ("ORDER-SENSITIVE",
                "THE flagship case B-3/B-4 are written about. FIXED "
                "(TASK-594): the `if r_pre.get(\"ready\") is True: ...` "
                "branch now calls `unmet(...)` naming its own predecessors "
                "(T_WX_01/T_WX_03), not `skip(...)` — a full-suite run "
                "honestly reports UNMET instead of a false-green SKIP. "
                "weatherReady is still LATCHED and this id still cannot "
                "PASS twice in one boot's full-suite order; that is now "
                "visible instead of hidden. No firmware reset exists for "
                "this latch (it is a deliberate never-re-armed design per "
                "weatherApp.h), so `set weatherReady 0` was rejected as an "
                "injector-shaped fake reversal rather than added as a "
                "NOT_INJECTORS boot-value reset — see "
                "gate/check_armed_injectors.py. No longer matched by "
                "`_readiness_hits` (which greps for `skip(` only) since the "
                "false-green shape B-4(a) targets no longer applies once the "
                "verdict is UNMET; kept here as the historical record."),
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
        fired = [k for k in EDGE_SHAPES if cand[tid][k]]
        A(f"           shapes: {', '.join(fired)}")
        for kind in EDGE_SHAPES:
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
