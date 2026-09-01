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

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import check_test_meta as C                            # noqa: E402
from suite.serialdbg import _meta                      # noqa: E402
import suite.serialdbg as _suite                       # noqa: E402


def rec(**over) -> dict:
    """One well-formed record; each case breaks exactly one field."""
    r = {"id": "T_X_01", "cls": "FEATURE", "scope": "Clock", "effect": "mutating",
         "module": "clock", "scope_seed": "Clock", "scope_seeded_by": "module",
         "scope_declared": False, "scope_reason": None, "cls_declared": False,
         "effect_seed": "mutating", "effect_declared": False, "effect_reason": None}
    r.update(over)
    return {r["id"]: r}


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
    print(f"test_check_test_meta: {len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
