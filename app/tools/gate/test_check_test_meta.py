#!/usr/bin/env python3
"""Negative tests for check_test_meta.py and the seeder behind it — BP-068.

A gate that has never been seen to fail is not a gate. Every case below mutates
a record the way the checker is meant to catch and asserts the finding appears;
two positive controls guard the other direction (the live registry is clean, and
a legitimate override with a reason is NOT a finding — that is the whole point of
M-TESTARCH §13.3's seed/declaration split and the thing an equality gate would
get wrong).

The seeder itself is tested directly too: a checker that agrees with a broken
seeder proves nothing.

No DUT, no build, no network. Run: python3 app/tools/gate/test_check_test_meta.py
"""

from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import _case_runner  # noqa: E402

import check_test_meta as C                            # noqa: E402
from suite.serialdbg import _meta                      # noqa: E402
import suite.serialdbg as _suite                       # noqa: E402


def rec(**over) -> dict:
    """One well-formed record; each case breaks exactly one field."""
    r = {"id": "T_X_01", "cls": "FEATURE", "scope": "Clock", "effect": "mutating",
         "module": "clock", "scope_seed": "Clock", "scope_seeded_by": "module",
         "scope_declared": False, "scope_reason": None, "cls_declared": False,
         "cls_seed": "FEATURE", "cls_reason": None,
         "effect_seed": "mutating", "effect_declared": False, "effect_reason": None}
    r.update(over)
    return {r["id"]: r}


#: A cls_reason long enough to clear MIN_CLS_REASON — the shape a real one has.
GOOD_REASON = ("Every id in the corpus taps through this gate, so a failure here "
               "means no later tap verdict describes the machine the test arranged.")


def one(findings, needle):
    hits = [f for f in findings if needle in f]
    assert hits, f"expected a finding containing {needle!r}, got {findings}"
    return hits


# ── negative cases ────────────────────────────────────────────────────────────

def case_unresolved_scope():
    f = C.evaluate(rec(scope=_meta.UNKNOWN_SCOPE))
    one(f, "no scope")


def case_scope_outside_enum():
    f = C.evaluate(rec(scope="Winamp"))          # the DISPLAY name, not APP_ORDER
    one(f, "is not in the enum")


def case_override_without_reason():
    f = C.evaluate(rec(scope="WebRadio", scope_declared=True, scope_reason=None))
    one(f, "no scope_reason")


def case_handtyped_scope_equals_seed():
    """EC-D2: zero hand-typed scope values where the seeder derives one."""
    f = C.evaluate(rec(scope="Clock", scope_declared=True, scope_reason="clock"))
    one(f, "hand-typing a seeded value")


def case_bad_effect():
    f = C.evaluate(rec(effect="readonly"))       # missing the hyphen
    one(f, "effect 'readonly' is not in")


def case_bad_cls():
    f = C.evaluate(rec(cls="APPLICATION"))
    one(f, "cls 'APPLICATION' is not in")


def case_effect_override_without_reason():
    f = C.evaluate(rec(effect="read-only", effect_declared=True))
    one(f, "no effect_reason")


def case_catch_all_outside_shell():
    """A family module renamed so it no longer matches an app must be loud."""
    f = C.evaluate(rec(module="clocks", scope="shell", scope_seed="shell",
                       scope_seeded_by="catch-all"))
    one(f, "seeds nothing")


def case_case_only_enum_collision():
    """§13.3's renamed defect: `Spotify` and `spotify` may not both exist."""
    f = C.evaluate(rec(), scopes=tuple(_meta.SCOPES) + ("spotify",))
    one(f, "case-only collision")


# ── R35: the gating-class declaration gate (TASK-591) ────────────────────────
#
# BP-068. Each case drives `evaluate_gating_classes` with a record set that is
# exactly one mutation away from clean, and asserts the finding appears. The
# ledger arm gets the same treatment in both directions: a row must suppress the
# finding it names, and must FAIL once the finding stops occurring.

def case_seeded_core_is_a_finding():
    """The live defect R35 exists for: 43 CORE ids applied by seed_cls()."""
    f = C.evaluate_gating_classes(rec(id="T-BUSY-01", cls="CORE", scope="shell",
                                      cls_seed="CORE"))
    one(f, "G1 T-BUSY-01")
    one(f, "SEEDED from scope 'shell'")


def case_declared_gating_class_without_a_reason():
    """A declaration with no argument is not a declaration — it is a value.
    None, empty and whitespace-only must all read as absent."""
    for empty in (None, "", "   \n  "):
        f = C.evaluate_gating_classes(rec(cls="CORE", scope="shell",
                                          cls_declared=True, cls_reason=empty))
        one(f, "declared with no reason")


def case_reason_too_short_to_be_an_argument():
    """`cls_reason="core"` restates the class name. G3, and NOT exemptable."""
    f = C.evaluate_gating_classes(rec(cls="CORE", scope="shell",
                                      cls_declared=True, cls_reason="core"))
    hits = one(f, "G3 T_X_01")
    assert "too short to be an argument" in hits[0], hits


def case_short_reason_is_not_exemptable():
    """A ledger row must not launder a G3 — only G1 is exemptable."""
    led = {("undeclared-gating-class", "T_X_01"): "docs/x.md:1"}
    f = C.evaluate_gating_classes(
        rec(cls="CORE", scope="shell", cls_declared=True, cls_reason="core"), led)
    one(f, "G3 T_X_01")


def case_health_and_rig_are_covered_too():
    """R35 says RIG, HEALTH *and* CORE — not CORE alone."""
    for cls in ("RIG", "HEALTH"):
        f = C.evaluate_gating_classes(rec(cls=cls, scope="rig", cls_declared=True))
        one(f, f"class {cls} is declared with no reason")


def case_ledger_row_suppresses_its_finding():
    led = {("undeclared-gating-class", "T_X_01"): "docs/v/gating.md:44"}
    f = C.evaluate_gating_classes(rec(cls="CORE", scope="shell"), led)
    assert not f, f"a ledger row did not suppress its finding: {f}"


def case_ledger_row_suppresses_exactly_one_id():
    """Rule 1: a row is keyed on `(kind, id)`. It must not cover a sibling — no
    file, family or wildcard exemption exists. Two undeclared CORE ids, one row:
    exactly one finding survives, and it names the OTHER id."""
    two = dict(rec(id="T_A", cls="CORE", scope="shell"))
    two.update(rec(id="T_B", cls="CORE", scope="shell"))
    led = {("undeclared-gating-class", "T_A"): "docs/v/gating.md:44"}
    f = C.evaluate_gating_classes(two, led)
    assert len(f) == 1, f"expected exactly one surviving finding, got {f}"
    one(f, "G1 T_B")


def case_stale_ledger_row_is_blocking():
    """The rule that makes it a gate and not an amnesty: the list can only shrink."""
    led = {("undeclared-gating-class", "T_X_01"): "docs/v/gating.md:44"}
    f = C.evaluate_gating_classes(
        rec(cls="CORE", scope="shell", cls_declared=True, cls_reason=GOOD_REASON), led)
    one(f, "G2 docs/v/gating.md:44")
    one(f, "can only shrink")


def case_ledger_row_for_an_unknown_id_is_stale():
    """A row naming an id no registry contains is stale by the same rule."""
    led = {("undeclared-gating-class", "T_GONE"): "docs/v/gating.md:99"}
    f = C.evaluate_gating_classes(rec(cls="FEATURE"), led)
    one(f, "G2 docs/v/gating.md:99")


def case_malformed_ledger_rows(tmp=None):
    """Owner must be a TASK id, `since` an ISO date, kind exemptable."""
    import tempfile
    body = ("| id | kind | why | owner | since |\n"
            "|---|---|---|---|---|\n"
            "| `T_A` | undeclared-gating-class | x | nobody | 2026-09-04 |\n"
            "| `T_B` | undeclared-gating-class | x | TASK-591 | soon |\n"
            "| `T_C` | gating-flake | x | TASK-591 | 2026-09-04 |\n"
            "| `T_D` | undeclared-gating-class | x | TASK-591 | 2026-09-04 |\n")
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
        fh.write(body)
        path = fh.name
    try:
        rows, errors = C.parse_ledger(path)
    finally:
        os.unlink(path)
    one(errors, "owner 'nobody'")
    one(errors, "since 'soon'")
    one(errors, "kind 'gating-flake' is not exemptable")
    assert list(rows) == [("undeclared-gating-class", "T_D")], rows


def case_gating_set_is_derived_not_typed():
    """Adding a class above FEATURE must WIDEN the check automatically. A typed
    tuple is how a gate silently stops covering a new class."""
    assert set(C.GATING) == {"RIG", "HEALTH", "CORE"}, C.GATING
    assert set(C.GATING) | set(C._order.CORE_BLOCKS) == set(C._meta.CLASSES)


def case_feature_needs_no_reason():
    """The safe default stays free — R35 constrains gating classes only."""
    f = C.evaluate_gating_classes(rec(cls="FEATURE"))
    assert not f, f"a FEATURE id was asked for a reason: {f}"


def case_live_registry_gating_classes_are_clean_or_ledgered():
    """The live corpus, through the real ledger file. This is the gate at
    BLOCKING: it passes only because every undeclared gating id has a dated,
    task-owned row — and fails the moment one is added without one."""
    ledger, errors = C.parse_ledger()
    assert not errors, f"the R35 ledger is malformed: {errors}"
    f = C.evaluate_gating_classes(_suite.build_all_meta(), ledger)
    assert not f, f"live gating-class findings: {f}"


def case_the_declared_gating_ids_carry_real_sentences():
    """Positive control on the corpus itself: every DECLARED gating reason is a
    sentence, not a tag, and no two ids share one (a copy-pasted reason is a
    restatement of the class name by another route)."""
    recs = _suite.build_all_meta()
    gating = {t for t, r in recs.items() if r["cls"] in C.GATING}
    declared = {t: (r.get("cls_reason") or "").strip()
                for t, r in recs.items()
                if r["cls"] in C.GATING and r.get("cls_declared") and r.get("cls_reason")}
    # DERIVED, not a typed floor. This used to read `>= 25` — TASK-591's census
    # frozen as a literal — and it went red the moment TASK-626 demoted five ids
    # out of CORE, i.e. on a change that made the corpus BETTER by this check's
    # own standard. The invariant is not "there are at least N of them", it is
    # "every id whose class can block declares that class with a reason", which
    # is what G1 enforces and what this positive control should assert.
    assert gating, "no gating ids at all — the census cannot be right"
    assert set(declared) == gating, \
        f"gating ids with no declared reason: {sorted(gating - set(declared))}"
    short = {t: len(v) for t, v in declared.items() if len(v) < C.MIN_CLS_REASON}
    assert not short, f"reasons too short to be arguments: {short}"
    dupes = [t for t, v in declared.items()
             if list(declared.values()).count(v) > 1]
    assert not dupes, f"duplicated cls_reason text on: {sorted(dupes)}"


# ── TASK-641: the falsifier record (oracle/premise/falsifier) ────────────────
#
# `read_keys` and `today` are passed explicitly throughout so these cases
# exercise `evaluate_falsifiers` against small fixtures, never the real
# `app/gen/read_keys.py` or the system clock (the live corpus gets its own
# positive control below, the same split R35's cases use for its ledger).

_TODAY = datetime.date(2026, 9, 19)
_RK_CLOCKSTYLE = {"T_X_01": {"status": "transcript",
                             "keys": [["set", "clockStyle"]], "unresolved": []}}


def case_oracle_shape_outside_enum():
    f = C.evaluate_falsifiers(rec(oracle={"clockStyle": "BOGUS"}),
                              read_keys=_RK_CLOCKSTYLE, today=_TODAY)
    one(f, "not in")


def case_oracle_key_not_in_generated_set():
    """§2: 'a declared key that is not in the generated set is a gate
    failure' — a heap oracle declared against a read set that only ever
    saw `clockStyle`."""
    f = C.evaluate_falsifiers(rec(oracle={"heap": "SNAPSHOT"}),
                              read_keys=_RK_CLOCKSTYLE, today=_TODAY)
    one(f, "is not in the generated read set")


def case_oracle_key_missing_on_approx_id_carries_a_hint():
    """APPROX ids get the same finding, plus a hint that the static walk
    may simply be behind — the finding is not weakened, only explained."""
    f = C.evaluate_falsifiers(
        rec(oracle={"heap": "SNAPSHOT"}),
        read_keys={"T_X_01": {"status": "APPROX", "keys": [], "unresolved": []}},
        today=_TODAY)
    hits = one(f, "is not in the generated read set")
    assert "APPROX" in hits[0], hits


def case_oracle_key_field_form_checks_the_base_key():
    """`clockStyle.name` -> the base key `clockStyle` is what must be read;
    the `.field` half is not itself required to appear anywhere."""
    f = C.evaluate_falsifiers(rec(oracle={"clockStyle.name": "SNAPSHOT"}),
                              read_keys=_RK_CLOCKSTYLE, today=_TODAY)
    assert not f, f


def case_falsifier_bad_format_is_a_finding():
    f = C.evaluate_falsifiers(rec(falsifier="somehow, replay-ish"),
                              read_keys=_RK_CLOCKSTYLE, today=_TODAY)
    one(f, "neither 'replay' nor")


def case_falsifier_physical_expired_is_a_finding():
    f = C.evaluate_falsifiers(
        rec(falsifier="physical: SD eject; expires 2020-01-01"),
        read_keys=_RK_CLOCKSTYLE, today=_TODAY)
    one(f, "expired 2020-01-01")


def case_falsifier_physical_unexpired_is_not_a_finding():
    f = C.evaluate_falsifiers(
        rec(falsifier="physical: SD eject; expires 2030-01-01"),
        read_keys=_RK_CLOCKSTYLE, today=_TODAY)
    assert not f, f


def case_falsifier_replay_with_a_real_oracle_is_not_a_finding():
    """TASK-642: nothing is typed — a SNAPSHOT-only oracle derives 'replay'
    on its own, and the derived value is clean."""
    f = C.evaluate_falsifiers(
        rec(oracle={"clockStyle": "SNAPSHOT"},
            falsifier="replay", falsifier_typed=None, falsifier_derived=True),
        read_keys=_RK_CLOCKSTYLE, today=_TODAY)
    assert not f, f


# TASK-642 (M-HARNESS2 §3/§8, amended 2026-09-19): "replay" is DERIVED from
# the declared oracle shapes, never typed — a hand-typed one can only
# disagree with the derivation or restate it, so it is a finding either way.
# `physical: ...` is untouched: still typed, still expiry-checked, never
# reported as this kind of redundancy.

def case_handtyped_replay_is_a_finding():
    f = C.evaluate_falsifiers(
        rec(oracle={"clockStyle": "SNAPSHOT"}, falsifier="replay",
            falsifier_typed="replay", falsifier_derived=False),
        read_keys=_RK_CLOCKSTYLE, today=_TODAY)
    one(f, "is hand-typed")


def case_handtyped_replay_disagreeing_with_shapes_is_still_a_finding():
    """The other direction: the shapes do NOT support replay (a PHYSICAL
    oracle key) but someone typed "replay" anyway. Still a finding, and for
    the SAME reason text — hand-typing this value is never allowed, whether
    or not it happens to match what the shapes would have said."""
    f = C.evaluate_falsifiers(
        rec(oracle={"heap": "PHYSICAL"}, falsifier="replay",
            falsifier_typed="replay", falsifier_derived=False),
        read_keys={}, today=_TODAY)
    one(f, "is hand-typed")


def case_physical_falsifier_is_not_reported_as_redundant():
    """A typed `physical: ...` is not "replay" and must never trip the
    redundancy finding — only its own format/expiry checks apply."""
    rk = {"T_X_01": {"status": "transcript",
                      "keys": [["set", "eject"]], "unresolved": []}}
    f = C.evaluate_falsifiers(
        rec(oracle={"eject": "PHYSICAL"},
            falsifier="physical: SD eject; expires 2030-01-01",
            falsifier_typed="physical: SD eject; expires 2030-01-01",
            falsifier_derived=False),
        read_keys=rk, today=_TODAY)
    assert not f, f


def case_oracle_with_only_replay_shapes_derives_replay():
    """An id with declared shapes and no typed falsifier at all derives
    'replay' — exercised through the real seeder/resolver, not a hand-built
    fixture, so this pins `_meta.derive_falsifier` itself."""
    assert _meta.derive_falsifier({"clockStyle": "SNAPSHOT"}) == "replay"
    assert _meta.derive_falsifier(
        {"a": "SNAPSHOT", "b": "POLL", "c": "TRANSITION"}) == "replay"
    assert _meta.derive_falsifier({}) is None


def case_physical_or_none_shape_does_not_derive_replay():
    """The two shapes with no host operator (§3) block the derivation —
    even mixed with an otherwise-replayable shape, because ONE key nothing
    can falsify makes the id as a whole not confirmable by replay alone."""
    assert _meta.derive_falsifier({"eject": "PHYSICAL"}) is None
    assert _meta.derive_falsifier({"unobservable": "NONE"}) is None
    assert _meta.derive_falsifier(
        {"clockStyle": "SNAPSHOT", "eject": "PHYSICAL"}) is None


def case_undeclared_id_is_not_a_finding():
    """No oracle, no falsifier at all is never itself a finding — most of
    the corpus predates this axis (§7's own opt-in framing)."""
    f = C.evaluate_falsifiers(rec(), read_keys={}, today=_TODAY)
    assert not f, f


# TASK-714 — the THRESHOLD shape's `bounds` requirement (M-HARNESS2 §3
# amendment). `perturb_threshold` (`lib/falsify_ops.py`) has to be TOLD how
# far past the reading counts as "crossed the bound" — unlike `SNAPSHOT`'s
# fixed `+1`, there is no step size that works for every possible bound — so
# every `THRESHOLD` oracle key needs a matching `bounds[key]`, and a `bounds`
# entry with no `THRESHOLD` key behind it is dead data nobody would notice
# going stale.

def case_threshold_with_no_bound_is_a_finding():
    f = C.evaluate_falsifiers(rec(oracle={"clockStyle": "THRESHOLD"}),
                              read_keys=_RK_CLOCKSTYLE, today=_TODAY)
    one(f, "no bounds['clockStyle']")


def case_threshold_non_positive_bound_is_a_finding():
    f = C.evaluate_falsifiers(
        rec(oracle={"clockStyle": "THRESHOLD"}, bounds={"clockStyle": 0}),
        read_keys=_RK_CLOCKSTYLE, today=_TODAY)
    one(f, "is not a positive")


def case_threshold_negative_bound_is_a_finding():
    f = C.evaluate_falsifiers(
        rec(oracle={"clockStyle": "THRESHOLD"}, bounds={"clockStyle": -5}),
        read_keys=_RK_CLOCKSTYLE, today=_TODAY)
    one(f, "is not a positive")


def case_threshold_bool_bound_is_a_finding():
    """A `bool` is an `int` in Python — `isinstance(True, int)` is `True` —
    so this has to be checked explicitly, the same way `perturb_threshold`
    itself refuses a `bool` value."""
    f = C.evaluate_falsifiers(
        rec(oracle={"clockStyle": "THRESHOLD"}, bounds={"clockStyle": True}),
        read_keys=_RK_CLOCKSTYLE, today=_TODAY)
    one(f, "is not a positive")


def case_threshold_string_bound_is_a_finding():
    f = C.evaluate_falsifiers(
        rec(oracle={"clockStyle": "THRESHOLD"}, bounds={"clockStyle": "4096"}),
        read_keys=_RK_CLOCKSTYLE, today=_TODAY)
    one(f, "is not a positive")


def case_threshold_with_a_good_bound_is_not_a_finding():
    f = C.evaluate_falsifiers(
        rec(oracle={"clockStyle": "THRESHOLD"}, bounds={"clockStyle": 4096}),
        read_keys=_RK_CLOCKSTYLE, today=_TODAY)
    assert not f, f


def case_bounds_entry_with_no_threshold_key_is_a_finding():
    """`bounds` naming a key that is not declared `THRESHOLD` at all (or not
    declared as an oracle key at all) is dead data — nothing would ever
    read it, and nothing would notice it going stale."""
    f = C.evaluate_falsifiers(
        rec(oracle={"clockStyle": "SNAPSHOT"}, bounds={"clockStyle": 4096}),
        read_keys=_RK_CLOCKSTYLE, today=_TODAY)
    one(f, "dead bound data")


def case_bounds_entry_for_an_undeclared_key_is_a_finding():
    f = C.evaluate_falsifiers(
        rec(oracle={"clockStyle": "SNAPSHOT"}, bounds={"heap": 4096}),
        read_keys=_RK_CLOCKSTYLE, today=_TODAY)
    one(f, "dead bound data")


def case_substring_needs_no_bound():
    """`SUBSTRING` is the other TASK-714 shape and takes no `bounds` entry —
    `scramble_string` needs no magnitude, only the string itself."""
    f = C.evaluate_falsifiers(
        rec(oracle={"clockStyle": "SUBSTRING"}),
        read_keys=_RK_CLOCKSTYLE, today=_TODAY)
    assert not f, f


def case_live_clock_falsifiers_are_clean():
    """The live corpus, through the real generated `app/gen/read_keys.py`
    and today's date. This is the gate at BLOCKING for the Clock cohort
    declared so far: it passes only because every declared oracle key is a
    real read and every falsifier is well-formed and unexpired."""
    recs = _suite.build_all_meta()
    f = C.evaluate_falsifiers(recs)
    assert not f, f"live falsifier findings: {f}"


# ── positive controls ─────────────────────────────────────────────────────────

def case_live_registry_is_clean():
    f = C.evaluate(_suite.build_all_meta())
    assert not f, f"the live registry produced findings: {f}"


def case_legitimate_override_is_not_a_finding():
    """The T_PMT_* shape: a declaration that DIFFERS from its seed and carries a
    reason is data, not a violation. An equality gate would fail exactly here."""
    f = C.evaluate(rec(id="T_PMT_02", scope="WebRadio", module="player",
                       scope_seed="LocalPlayer", scope_declared=True,
                       scope_reason="cross-mode"))
    assert not f, f"a reasoned override was reported: {f}"


def case_annotation_without_override_is_not_a_finding():
    f = C.evaluate(rec(scope_reason="cross-mode"))
    assert not f, f"a scope_reason annotation was reported: {f}"


# ── the seeder itself ─────────────────────────────────────────────────────────

def case_seed_by_module_and_prefix_and_catch_all():
    assert _meta.seed_scope("T169", "stock") == ("Stock", "module")
    # player.py maps via the app's DISPLAY name ('Player' -> 'LocalPlayer').
    assert _meta.seed_scope("T_PLR_01", "player") == ("LocalPlayer", "module")
    assert _meta.seed_scope("T_WX_01", "shell") == ("Weather", "prefix")
    assert _meta.seed_scope("T_BI_01", "shell") == ("boot", "prefix")
    assert _meta.seed_scope("T-BUSY-01", "shell") == ("shell", "catch-all")


def case_seed_cls_defaults():
    assert _meta.seed_cls("shell") == "CORE"
    assert _meta.seed_cls("boot") == "CORE"
    assert _meta.seed_cls("taskbar") == "CORE"
    assert _meta.seed_cls("rig") == "RIG"
    assert _meta.seed_cls("Clock") == "FEATURE"


def case_seed_effect_reads_the_commands():
    def ro(dut):
        dut.cmd("get appId")
        dut.cmd("info")

    def mut(dut):
        dut.cmd("get appId")
        dut.cmd(f"tap {1} {2}")

    def reset(dut):
        dut.send("reboot")

    assert _meta.seed_effect(ro) == "read-only"
    assert _meta.seed_effect(mut) == "mutating"
    assert _meta.seed_effect(reset) == "resetting"
    # Conservative default: no commands at all is NOT read-only (EC-S1).
    assert _meta.seed_effect(lambda dut: None) == "mutating"
    assert _meta.seed_effect(None) == "mutating"


def case_seed_effect_follows_helper_calls():
    """§16.3's reference case: a step that looks read-only but calls a helper
    that switches app is mutating, and nothing else would notice."""
    import suite.serialdbg.shell as sh
    assert _meta.seed_effect(sh.TESTS["T-BUSY-01"]) == "mutating"
    # And the live suite must not classify a rebooting test as anything else.
    import suite.serialdbg.planeradar as pr
    assert _meta.seed_effect(pr.TESTS["T_PR_04"]) == "resetting"


def case_selector_resolves_names_and_paths():
    assert _meta.resolve_selector("LocalPlayer") == "LocalPlayer"
    assert _meta.resolve_selector("spotify-chrome") == "spotify-chrome"
    assert _meta.resolve_selector("app/src/apps/localPlayerApp.cpp") == "LocalPlayer"
    # The stray that an app/src/apps/ glob would miss (design §13.4).
    assert _meta.resolve_selector("app/src/stock/stockApp.cpp") == "Stock"
    assert _meta.resolve_selector("app/src/shell/appShell.cpp") == "shell"
    try:
        _meta.resolve_selector("app/src/util/ringbuf.h")
    except ValueError:
        pass
    else:
        raise AssertionError("an unresolvable path must raise, not guess")


def case_selector_is_case_sensitive():
    """`--scope spotify` must NOT silently resolve to `Spotify`."""
    try:
        _meta.resolve_selector("spotify")
    except ValueError:
        pass
    else:
        raise AssertionError("a case-mismatched scope name resolved anyway")


def case_scope_selection_is_non_empty_for_every_app():
    meta = _suite.build_all_meta()
    empty = [a for a in ("Clock", "Stock", "WebRadio", "LocalPlayer", "PlaneRadar",
                         "Teletext", "Weather", "Crypto", "Matrix", "Life",
                         "Settings", "Spotify")
             if not _suite.ids_for_scope(a, meta)]
    assert not empty, f"apps with no ids at all: {empty}"


def case_app_source_map_matches_app_order():
    root = str(HERE.parent.parent.parent)
    m = _meta.app_source_map(root)
    assert set(m) == set(_meta.APP_ORDER), sorted(set(m) ^ set(_meta.APP_ORDER))
    assert os.path.basename(m["Stock"]) == "stockApp.cpp"


CASES = [
    ("N1  unresolved scope",                 case_unresolved_scope),
    ("N2  scope outside the enum",           case_scope_outside_enum),
    ("N3  override with no reason",          case_override_without_reason),
    ("N4  hand-typed scope == seed",         case_handtyped_scope_equals_seed),
    ("N5  effect outside the enum",          case_bad_effect),
    ("N6  cls outside the enum",             case_bad_cls),
    ("N7  effect override with no reason",   case_effect_override_without_reason),
    ("N8  catch-all outside shell.py",       case_catch_all_outside_shell),
    ("N9  case-only enum collision",         case_case_only_enum_collision),
    ("P1  live registry is clean",           case_live_registry_is_clean),
    ("P2  reasoned override is data",        case_legitimate_override_is_not_a_finding),
    ("P3  reason-only annotation is data",   case_annotation_without_override_is_not_a_finding),
    ("S1  seed by module/prefix/catch-all",  case_seed_by_module_and_prefix_and_catch_all),
    ("S2  cls defaults",                     case_seed_cls_defaults),
    ("S3  effect from the commands",         case_seed_effect_reads_the_commands),
    ("S4  effect follows helper calls",      case_seed_effect_follows_helper_calls),
    ("S5  selector: names and paths",        case_selector_resolves_names_and_paths),
    ("S6  selector is case-sensitive",       case_selector_is_case_sensitive),
    ("S7  every app selects >= 1 id",        case_scope_selection_is_non_empty_for_every_app),
    ("S8  app/src glob == APP_ORDER",        case_app_source_map_matches_app_order),
    # R35 — the gating-class declaration gate (TASK-591)
    ("G1  seeded CORE is a finding",         case_seeded_core_is_a_finding),
    ("G2  declared class, no reason",        case_declared_gating_class_without_a_reason),
    ("G3  reason too short to be one",       case_reason_too_short_to_be_an_argument),
    ("G4  a short reason is not exemptable", case_short_reason_is_not_exemptable),
    ("G5  RIG and HEALTH covered too",       case_health_and_rig_are_covered_too),
    ("G6  a row suppresses its finding",     case_ledger_row_suppresses_its_finding),
    ("G7  a row covers ONE (kind,id)",       case_ledger_row_suppresses_exactly_one_id),
    ("G8  a stale row is blocking",          case_stale_ledger_row_is_blocking),
    ("G9  a row for an unknown id is stale", case_ledger_row_for_an_unknown_id_is_stale),
    ("G10 malformed ledger rows",            case_malformed_ledger_rows),
    ("G11 the gating set is derived",        case_gating_set_is_derived_not_typed),
    ("G12 FEATURE needs no reason",          case_feature_needs_no_reason),
    ("G13 live gating set is clean",         case_live_registry_gating_classes_are_clean_or_ledgered),
    ("G14 declared reasons are sentences",   case_the_declared_gating_ids_carry_real_sentences),
    # TASK-641 — the falsifier record (oracle/premise/falsifier)
    ("F1  oracle shape outside the enum",    case_oracle_shape_outside_enum),
    ("F2  oracle key not in read set",       case_oracle_key_not_in_generated_set),
    ("F3  APPROX miss carries a hint",       case_oracle_key_missing_on_approx_id_carries_a_hint),
    ("F4  key.field checks the base key",    case_oracle_key_field_form_checks_the_base_key),
    ("F5  malformed falsifier string",       case_falsifier_bad_format_is_a_finding),
    ("F6  expired physical falsifier",       case_falsifier_physical_expired_is_a_finding),
    ("F7  unexpired physical is not a finding", case_falsifier_physical_unexpired_is_not_a_finding),
    ("F8  replay + real oracle is clean",    case_falsifier_replay_with_a_real_oracle_is_not_a_finding),
    ("F9  no declaration is not a finding",  case_undeclared_id_is_not_a_finding),
    ("F10 live Clock falsifiers are clean",  case_live_clock_falsifiers_are_clean),
    # TASK-714 — THRESHOLD's bounds requirement, SUBSTRING's lack of one
    ("F11 THRESHOLD with no bound",          case_threshold_with_no_bound_is_a_finding),
    ("F12 THRESHOLD bound <= 0",             case_threshold_non_positive_bound_is_a_finding),
    ("F13 THRESHOLD bound negative",         case_threshold_negative_bound_is_a_finding),
    ("F14 THRESHOLD bound is a bool",        case_threshold_bool_bound_is_a_finding),
    ("F15 THRESHOLD bound is a string",      case_threshold_string_bound_is_a_finding),
    ("F16 THRESHOLD + a good bound is clean", case_threshold_with_a_good_bound_is_not_a_finding),
    ("F17 bounds naming a non-THRESHOLD key", case_bounds_entry_with_no_threshold_key_is_a_finding),
    ("F18 bounds naming an undeclared key",  case_bounds_entry_for_an_undeclared_key_is_a_finding),
    ("F19 SUBSTRING needs no bound",         case_substring_needs_no_bound),
    # TASK-642 — 'replay' derived from shapes, never hand-typed
    ("F20 hand-typed replay is a finding",   case_handtyped_replay_is_a_finding),
    ("F21 hand-typed replay vs PHYSICAL",    case_handtyped_replay_disagreeing_with_shapes_is_still_a_finding),
    ("F22 physical is not redundant",        case_physical_falsifier_is_not_reported_as_redundant),
    ("F23 replay-only shapes derive replay", case_oracle_with_only_replay_shapes_derives_replay),
    ("F24 PHYSICAL/NONE block derivation",   case_physical_or_none_shape_does_not_derive_replay),
]


def main() -> int:
    return _case_runner.run_cases("test_check_test_meta", CASES)


if __name__ == "__main__":
    sys.exit(main())
