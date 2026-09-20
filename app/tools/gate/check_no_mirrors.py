#!/usr/bin/env python3
"""check_no_mirrors.py — the mirror-equality gate. TASK-606 / M-HARNESS2 R42/R43.

WHY THIS EXISTS. WP-Z's review (docs/verification/reviews/M-TESTQUAL-Z-findings-
review.md §10) found the suite re-declaring firmware constants, enum values, app
slots, layout coordinates and key names in at least nine registered places, in
every case where a generator, a parser or a generated Python module already
existed that it could have imported instead. Every one of those values is
CORRECT TODAY (`A-8` is confirmed latent, not live) — the cost is entirely
future and entirely silent, and worse than "the suite fails": the firmware
CLAMPS the coordinates the Stock suite mirrors, so a drifted value never
*misses* — it selects a different row or tab, which only the ids that read
their selection back can see, while the rest run on believing they tested the
thing they used to test.

R42 (MUST): no firmware fact is mirrored in the suite; parse it from the
firmware or from `app/gen/`. This gate holds the `(suite symbol, firmware
symbol)` pairs the review's nine-mirror register named and asserts them equal
at gate time — the register's own action item, `A-18`. A drifted pair fails
loud, converting a silent selection-swap into a build failure.

R43 (SHOULD): a formula that exists in the firmware should not be
re-implemented in the harness. Covered by the same equality pairs: `A-9`'s
tab-centre formula and `D-6`'s row-height formula are asserted by recomputing
the firmware's formula from firmware-parsed constants and comparing the RESULT
against the suite's literal/table — not by asserting the two pieces of code
are textually identical (they can't be: one is C++, one is Python). Where a
firmware formula involves something this gate cannot evaluate without a C++
compiler (a cast expression, e.g. `(int)AppId::Settings + 1`), the pair
instead compares against a value derived from the SAME already-generated
source the firmware's own formula is provably equal to (by the firmware's own
`static_assert`, read structurally below) — see `_check_c13` for why this is
sound rather than a second, independent guess at the number.

DESIGN DECISIONS

* Firmware side. Prefer an existing generated Python mirror over a new parser
  wherever one exists: `app_ids_gen.py` (generated from `appRegistry.h` by
  `gen/gen_app_registry.py`) is the source for every app-slot/app-count fact
  (`A-8`, `C-13`, `H-19`). Where no generated Python mirror exists, this file
  reads the C++/header source directly with small regex extractors modelled on
  the two parsers `app/tools/coords.py` already uses in production
  (`_parse` for `#define NAME value`, `_parse_cpp_constexpr_int` for
  `constexpr int NAME = value;`) — generalised here to more constexpr types
  (`uint8_t`/`int16_t`/`uint32_t`/plain `int`) since the firmware facts in the
  register aren't all typed `int`. This is deliberately NOT a rewrite of
  `gen_app_registry.py`'s own regex (TASK-600/R7's scar: a second glob over
  the same ground saw a different, smaller, subset of the same data) — it
  reuses that module's OUTPUT instead of re-deriving it.

* Suite side, without a suite->gate layering violation. `gate/check_test_meta.py`
  already established that a gate MAY import `suite.serialdbg` directly to
  read its data (the layering rule — "a suite may use lib/; lib/ never imports
  a suite" — restricts what suite/preview/bake may import, not what a leaf
  gate may read). `gate/check_import_safety.py` guarantees every suite module
  is safe to import (no port access at import time), so importing the family
  modules here to read their live values (`stock.py`'s `_TAB_XY`, `health.py`'s
  `_PLAYER_MODES`, `_helpers.py`'s `_TB_N`, `shell.py`'s settings-geometry
  names) is both safe and exact — no regex on the suite side at all for those.
  One mirror (`F-16`'s literal 19/21/12 occurrences in `webradio.py`) has no
  named module-level constant to import — for that this file uses
  `inspect.getsource()` on the already-imported module and a small regex,
  which is line-number-proof (it re-reads the CURRENT source text at gate
  time, never a cached line offset) but still suite-side text, unlike the
  firmware regexes above which read files by path. (`A-8`'s `switchApp N`
  literals in `clock.py` and `H-12`'s tap-coordinate literals in
  `teletext.py` used to be handled the same way; TASK-715 deleted both
  literals — `clock.py` now imports `app_ids_gen.APP_SLOT` and `teletext.py`
  now imports `coords.py`'s parsed `TTXT_*` constants — so those two pairs
  were removed from the register below rather than converted, since a pair
  with no remaining suite-side literal has nothing left to compare against
  the firmware value that wouldn't just be comparing the same parsed value
  to itself.)

* What a pair looks like when the suite side is a table/formula, not a
  scalar (R43). `A-9`'s `_TAB_XY` and `D-6`'s `_APP_LIST_ROW_H` are both
  DETERMINISTIC integer formulas over firmware-parsed constants, so this gate
  recomputes the firmware formula in Python from the parsed constants and
  compares the numeric RESULT against the suite's table/scalar — equality is
  well-defined and exact for both. `C-13`'s pair is flagged explicitly as
  COINCIDENTAL in its finding text (`_TB_N` and `TASKBAR_APP_COUNT` are
  numerically equal today but computed from semantically different
  quantities — `APP_SLOT["WebRadio"]` vs `AppId::Settings + 1`) — this gate
  still asserts the VALUES equal (that's what would actually break first) and
  the finding/verdict text says so, so a future reader is not misled by a
  green checkmark into thinking the two expressions were ever the same
  expression.

RULING (TASK-619 / mem_layout.py). `app/gen/mem_layout.py` mirrors
`app/mem_manifest.yaml`'s static overlay budget (region offsets/sizes/budget
per doc type: crypto/planeradar/heatmap/weather). None of the nine register
entries are memory-manifest facts, and a repo-wide grep found zero importers
of `mem_layout.py` outside its own generator (`gen/gen_mem_layout.py`) — no
suite test reads MEM_OFFSETS/MEM_REGION_SIZES/MEM_BUDGET_USED at all, so there
is no live mirror for this gate to consume. TASK-619's ruling ("survives only
if TASK-606 consumes it within one milestone, else it and its `run/check` step
are deleted") therefore resolves NEGATIVE: this gate does not use
`mem_layout.py`, because nothing in the register needs it. Consume-or-delete
decides DELETE — left to a follow-up row per the task's instruction not to
edit tasks-harness2.md here.

RULING (H-19 / console.cpp). Verifying the citation found the help string
was in fact still stale (`<appId 0..8>` against `APP_COUNT = 13`) — a live,
pre-existing defect, not a citation error. Rather than land this MUST gate
non-zero on day one for a one-line, zero-behavior-risk help string with no
test consumer (confirmed: no suite file references it), the string was
corrected in the same change (`console.cpp`, the `switchApp` row) so the gate
seeds at zero "by construction," per this task's own ruling 1 — not by
adjusting this file's expected value, which stayed `APP_COUNT - 1` throughout.

No DUT, no build, no network. Run directly, or via app/tools/smoke_test.sh
(run/check gate 8).

    python3 app/tools/gate/check_no_mirrors.py --verbose
"""

from __future__ import annotations

import argparse
import inspect
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))
sys.path.insert(0, TOOLS)

from app_ids_gen import APP_ORDER, APP_SLOT, APP_COUNT   # noqa: E402


def _root(path: str) -> str:
    return os.path.join(ROOT, path)


def _read(path: str) -> str:
    with open(_root(path), encoding="utf-8") as fh:
        return fh.read()


# ── generic firmware-source parsers (pattern: app/tools/coords.py's own) ────

_DEFINE_RE = re.compile(r'^\s*#define\s+(\w+)\s+([^\r\n]*)', re.M)
_CONSTEXPR_RE = re.compile(
    r'(?:static\s+)?constexpr\s+(?:u?int(?:8|16|32|64)_t|int|unsigned)\s+'
    r'(\w+)\s*=\s*([^;]+);'
)


def _strip_comment(raw: str) -> str:
    return raw.split("//")[0].strip()


def find_define_int(text: str, name: str):
    """#define NAME <int-literal> -> int, or None if not found / not numeric."""
    for m in _DEFINE_RE.finditer(text):
        if m.group(1) == name:
            val = _strip_comment(m.group(2))
            try:
                return int(val, 0)
            except ValueError:
                return None
    return None


def find_constexpr_int(text: str, name: str):
    """constexpr <int type> NAME = <expr>; -> int if the expr is a bare
    integer literal, else the raw (stripped) expression text for a caller
    that wants to sanity-check the FORMULA rather than evaluate it (this file
    does not embed a C++ evaluator)."""
    for m in _CONSTEXPR_RE.finditer(text):
        if m.group(1) == name:
            expr = m.group(2).strip()
            try:
                return int(expr, 0)
            except ValueError:
                return expr
    return None


def find_enum_values(text: str, enum_name: str) -> dict:
    """enum [class] NAME [: type] { A, B = 5, C, ... }; -> {name: value},
    honoring explicit `= N` and defaulting to prev+1 (starting at 0), the same
    rule C++ itself uses. Returns {} if the enum isn't found (a finding, not
    a silent skip, at the call site)."""
    m = re.search(
        r'enum\s+(?:class\s+)?' + re.escape(enum_name) +
        r'\s*(?::\s*\w+\s*)?\{([^}]*)\}', text, re.S)
    if not m:
        return {}
    out = {}
    nxt = 0
    for entry in m.group(1).split(","):
        entry = _strip_comment(entry).strip()
        if not entry:
            continue
        if "=" in entry:
            nm, val = entry.split("=", 1)
            nm = nm.strip()
            try:
                nxt = int(val.strip(), 0)
            except ValueError:
                continue
        else:
            nm = entry.strip()
        out[nm] = nxt
        nxt += 1
    return out


def find_all_string_arrays(text: str, var_name: str) -> list:
    """All `NAME[] = { "a", "b", ... };` occurrences (there can be more than
    one copy of the same array — that duplication is itself part of what this
    gate is checking for `A-10`) -> list of tuple-of-strings, one per
    occurrence, in file order."""
    out = []
    for m in re.finditer(re.escape(var_name) + r'\s*\[\s*\]\s*=\s*\{([^}]*)\}', text):
        out.append(tuple(re.findall(r'"([^"]*)"', m.group(1))))
    return out


class Finding:
    """One register entry's verdict. `ok=False` covers BOTH a real value
    disagreement and a symbol this file could not locate — R42's whole point
    is that neither may be a silent skip."""

    def __init__(self, id_, desc, suite_cite, fw_cite, suite_val, fw_val, ok, note=""):
        self.id = id_
        self.desc = desc
        self.suite_cite = suite_cite
        self.fw_cite = fw_cite
        self.suite_val = suite_val
        self.fw_val = fw_val
        self.ok = ok
        self.note = note

    def line(self) -> str:
        status = "OK  " if self.ok else "FAIL"
        return (f"[{status}] {self.id}: suite={self.suite_val!r} "
                f"firmware={self.fw_val!r}  ({self.desc})")


# ── A-8: REMOVED (TASK-715) — clock.py no longer hardcodes app-slot literals.
#
# clock.py now imports `APP_SLOT` from app_ids_gen directly (`_CLOCK =
# APP_SLOT["Clock"]`, `_SPOTIFY = APP_SLOT["Spotify"]`) instead of writing
# `switchApp 1`/`switchApp 0`. There is no longer a suite-side literal for
# this pair to compare against a firmware value — a pair with nothing on one
# side would either compare a value to itself (the "gate agreeing with
# itself" failure this task explicitly rules out) or degenerate into
# asserting `import app_ids_gen` exists, which `check_import_safety.py`
# already covers structurally for every suite module. Deleting the pair
# outright is the correct direction: the mirror is gone, so the register
# that exists to catch mirrors should shrink, not grow a vacuous check.


# ── A-9: stock.py's _TAB_XY four-pair table mirrors a two-constant formula ──

def check_a9() -> Finding:
    import suite.serialdbg.stock as stock_mod
    fw_text = _read("app/src/stock/stockShared.h")
    tabs_x = find_define_int(fw_text, "ST_CHART_TABS_X")
    tab_w = find_define_int(fw_text, "ST_CHART_TAB_W")
    header_h = find_define_int(fw_text, "ST_CHART_HEADER_H")
    if None in (tabs_x, tab_w, header_h):
        return Finding("A-9", "Stock chart tab centres", "stock.py _TAB_XY",
                        "stockShared.h ST_CHART_TABS_X/TAB_W/HEADER_H",
                        getattr(stock_mod, "_TAB_XY", None), None, False,
                        "firmware constant(s) not found by name")
    expected = [(tabs_x + i * tab_w + tab_w // 2, header_h // 2) for i in range(4)]
    suite_val = list(getattr(stock_mod, "_TAB_XY", []))
    ok = suite_val == expected
    return Finding(
        "A-9", "stock.py's 4-pair _TAB_XY table vs the tab-centre formula",
        "app/tools/suite/serialdbg/stock.py:_TAB_XY",
        "app/src/stock/stockShared.h ST_CHART_TABS_X/ST_CHART_TAB_W/ST_CHART_HEADER_H",
        suite_val, expected, ok,
    )


# ── A-10: PR_FETCH_TYPE + _PLAYER_MODES mirror firmware enums ──────────────

def check_a10_fetchtype() -> Finding:
    import suite.serialdbg.planeradar as pr_mod
    fw_text = _read("app/src/dataTask.h")
    enum_vals = find_enum_values(fw_text, "FetchType")
    fw_val = enum_vals.get("DATA_FETCH_PLANERADAR")
    suite_val = getattr(pr_mod, "PR_FETCH_TYPE", None)
    ok = fw_val is not None and suite_val == fw_val
    return Finding(
        "A-10a", "planeradar.py's PR_FETCH_TYPE vs dataTask.h's FetchType enum",
        "app/tools/suite/serialdbg/planeradar.py:PR_FETCH_TYPE",
        "app/src/dataTask.h enum FetchType { DATA_FETCH_PLANERADAR }",
        suite_val, fw_val, ok,
    )


def check_a10_playermodes() -> Finding:
    import suite.serialdbg.health as health_mod
    suite_val = tuple(getattr(health_mod, "_PLAYER_MODES", ()))
    # kPmNames is textually duplicated three times in the firmware (cmdGet.cpp
    # x2, cmdSet.cpp x1) — the review's own citation named cmdSet.cpp as the
    # sole source, which is WRONG: `get playerMode`, the command health.py
    # actually calls, reads the copy in cmdGet.cpp (both of them; cmdSet.cpp's
    # copy backs `set playerMode` instead). All three are checked against the
    # suite value so a drift in ANY copy is caught, not just the one the old
    # citation happened to name.
    occurrences = []
    for relpath in (
        "app/src/debug/serialConsole/cmdGet.cpp",
        "app/src/debug/serialConsole/cmdSet.cpp",
    ):
        text = _read(relpath)
        for i, arr in enumerate(find_all_string_arrays(text, "kPmNames")):
            occurrences.append((f"{relpath}#{i}", arr))
    if not occurrences:
        return Finding("A-10b", "health.py's _PLAYER_MODES vs cmdGet.cpp's kPmNames",
                        "app/tools/suite/serialdbg/health.py:_PLAYER_MODES",
                        "app/src/debug/serialConsole/{cmdGet,cmdSet}.cpp kPmNames[]",
                        suite_val, None, False, "no kPmNames[] array found in either file")
    fw_vals = {arr for _, arr in occurrences}
    ok = fw_vals == {suite_val}
    note = ""
    if len(fw_vals) > 1:
        note = ("firmware itself disagrees across kPmNames copies: " +
                "; ".join(f"{loc}={arr}" for loc, arr in occurrences))
    elif not ok:
        note = f"suite {suite_val} != firmware {next(iter(fw_vals))}"
    return Finding(
        "A-10b", "health.py's _PLAYER_MODES vs every kPmNames[] copy in the firmware",
        "app/tools/suite/serialdbg/health.py:_PLAYER_MODES",
        "app/src/debug/serialConsole/cmdGet.cpp kPmNames[] (used by `get playerMode`); "
        "also duplicated in cmdSet.cpp (used by `set playerMode`)",
        suite_val, sorted(fw_vals), ok, note,
    )


# ── C-13: _TB_N == TASKBAR_APP_COUNT by coincidence, not by shared formula ──

def check_c13() -> Finding:
    import suite.serialdbg._helpers as helpers_mod
    suite_val = getattr(helpers_mod, "_TB_N", None)
    # Firmware: TASKBAR_APP_COUNT = (int)AppId::Settings + 1, guarded by the
    # header's own static_assert. This file has no C++ evaluator, so rather
    # than re-derive "+1" as a second independent guess, it reads the VALUE
    # from app_ids_gen.py (generated from the same appRegistry.h AppId enum
    # order the firmware casts) and confirms the firmware source still
    # states the expected FORMULA (a structural, not numeric, check) so a
    # rewrite of taskbar.h's definition to something else is still caught.
    fw_text = _read("app/src/shell/taskbar.h")
    formula_present = bool(re.search(
        r'TASKBAR_APP_COUNT\s*=\s*\(int\)\s*AppId::Settings\s*\+\s*1', fw_text))
    fw_val = APP_SLOT["Settings"] + 1
    ok = formula_present and suite_val == fw_val
    note = ("COINCIDENTAL match (C-13): _TB_N is APP_SLOT['WebRadio'], "
            "TASKBAR_APP_COUNT is AppId::Settings+1 — same value today, "
            "different quantities; a future app reorder can break this "
            "silently even with this pair green")
    if not formula_present:
        note = "taskbar.h no longer states '(int)AppId::Settings + 1' — re-derive this check"
    return Finding(
        "C-13", "_helpers.py's _TB_N vs taskbar.h's TASKBAR_APP_COUNT (coincidental equality)",
        "app/tools/suite/serialdbg/_helpers.py:_TB_N (= APP_SLOT['WebRadio'])",
        "app/src/shell/taskbar.h:TASKBAR_APP_COUNT (= (int)AppId::Settings + 1)",
        suite_val, fw_val, ok, note,
    )


# ── D-6: Settings tap geometry + the _appListRowH() formula ────────────────

def check_d6() -> Finding:
    import suite.serialdbg.shell as shell_mod
    fw_settings = _read("app/src/settings/settingsSection.h")
    fw_configurable = _read("app/gen/configurable_apps.h")
    s_content_y = find_constexpr_int(fw_settings, "S_CONTENT_Y")
    s_row_h = find_constexpr_int(fw_settings, "S_ROW_H")
    s_content_h = find_constexpr_int(fw_settings, "S_CONTENT_H")
    configurable_count = find_define_int(fw_configurable, "CONFIGURABLE_APP_COUNT")
    fw_vals = {
        "S_CONTENT_Y": s_content_y, "S_ROW_H": s_row_h,
        "S_CONTENT_H": s_content_h, "CONFIGURABLE_APP_COUNT": configurable_count,
    }
    if any(v is None or isinstance(v, str) for v in fw_vals.values()):
        return Finding("D-6", "Settings tap geometry + _appListRowH() formula",
                        "app/tools/suite/serialdbg/shell.py:_S_*/_APP_LIST_ROW_H",
                        "settingsSection.h/configurable_apps.h", None, fw_vals, False,
                        "one or more firmware constants not found by name")
    # appsSection.h _appListRowH(): min(S_ROW_H, S_CONTENT_H // CONFIGURABLE_APP_COUNT)
    expected_row_h = min(s_row_h, s_content_h // configurable_count)
    suite_vals = {
        "_S_CONTENT_Y": getattr(shell_mod, "_S_CONTENT_Y", None),
        "_S_ROW_H": getattr(shell_mod, "_S_ROW_H", None),
        "_S_CONTENT_H": getattr(shell_mod, "_S_CONTENT_H", None),
        "_CONFIGURABLE_APP_COUNT": getattr(shell_mod, "_CONFIGURABLE_APP_COUNT", None),
        "_APP_LIST_ROW_H": getattr(shell_mod, "_APP_LIST_ROW_H", None),
    }
    ok = (suite_vals["_S_CONTENT_Y"] == s_content_y and
          suite_vals["_S_ROW_H"] == s_row_h and
          suite_vals["_S_CONTENT_H"] == s_content_h and
          suite_vals["_CONFIGURABLE_APP_COUNT"] == configurable_count and
          suite_vals["_APP_LIST_ROW_H"] == expected_row_h)
    return Finding(
        "D-6", "shell.py's Settings geometry + hand-reimplemented _appListRowH() formula",
        "app/tools/suite/serialdbg/shell.py:_S_CONTENT_Y/_S_ROW_H/_S_CONTENT_H/"
        "_CONFIGURABLE_APP_COUNT/_APP_LIST_ROW_H",
        "app/src/settings/settingsSection.h S_CONTENT_Y/S_ROW_H/S_CONTENT_H; "
        "app/gen/configurable_apps.h CONFIGURABLE_APP_COUNT; "
        "app/src/settings/appsSection.h _appListRowH() formula",
        suite_vals, {**fw_vals, "_appListRowH()": expected_row_h}, ok,
    )


# ── F-16: SPEC_BARS + two WebRadio volume-cap constants ────────────────────

def check_f16() -> list:
    import suite.serialdbg.webradio as wr_mod
    src = inspect.getsource(wr_mod)
    findings = []

    vu_text = _read("app/src/winamp/vuMeter.h")
    spec_bars = find_constexpr_int(vu_text, "SPEC_BARS")
    bars_literals = {int(n) for n in re.findall(r'len\(bars\d\)\s*!=\s*(\d+)', src)}
    ok = bool(bars_literals) and bars_literals == {spec_bars}
    findings.append(Finding(
        "F-16a", "webradio.py's hardcoded spectrum-bar count vs vuMeter.h SPEC_BARS",
        "app/tools/suite/serialdbg/webradio.py (len(bars) != 19)",
        "app/src/winamp/vuMeter.h:SPEC_BARS",
        sorted(bars_literals), spec_bars, ok,
    ))

    ae_text = _read("app/src/audio/audioEngine.h")
    wr_max = find_constexpr_int(ae_text, "WR_VOLUME_MAX")
    wr_soft_cap = find_constexpr_int(ae_text, "WR_VOLUME_SOFT_CAP_STOCK")

    full_range = re.search(r'\(1,\s*(\d+),\s*\1,', src)
    full_range_val = int(full_range.group(1)) if full_range else None
    ok = full_range_val is not None and full_range_val == wr_max
    findings.append(Finding(
        "F-16b", "webradio.py's HW-mod full-range literal vs audioEngine.h WR_VOLUME_MAX",
        "app/tools/suite/serialdbg/webradio.py (cases: (1, 21, 21, ...))",
        "app/src/audio/audioEngine.h:WR_VOLUME_MAX",
        full_range_val, wr_max, ok,
    ))

    soft_cap = re.search(r'\(0,\s*21,\s*(\d+),', src)
    soft_cap_val = int(soft_cap.group(1)) if soft_cap else None
    ok = soft_cap_val is not None and soft_cap_val == wr_soft_cap
    findings.append(Finding(
        "F-16c", "webradio.py's stock soft-cap literal vs audioEngine.h WR_VOLUME_SOFT_CAP_STOCK",
        "app/tools/suite/serialdbg/webradio.py (cases: (0, 21, 12, ...))",
        "app/src/audio/audioEngine.h:WR_VOLUME_SOFT_CAP_STOCK",
        soft_cap_val, wr_soft_cap, ok,
    ))
    return findings


# ── H-12: REMOVED (TASK-715) — teletext.py no longer hand-mirrors y-values.
#
# teletext.py now imports `coords as _c` and reads `_c.TTXT_STRIP_BACK_Y0`,
# `_c.TTXT_STRIP_BACK_Y1`, `_c.TTXT_STRIP_PREV_Y0`, `_c.TTXT_STRIP_PAGE_Y1`
# and `_c.ttxt_subdn_centre()` — all parsed at coords.py import time from the
# GENERATED app/gen/teletext_layout.h via the module's existing `_parse()`
# (coords.py itself gained the `TTXT_*` constants for this). There is no
# longer a suite-side literal for this pair to compare: as with A-8, keeping
# a pair here would mean comparing coords.py's parsed value against itself
# (coords.py IS the firmware-fact source now) — a gate agreeing with itself,
# not a check. Deleted rather than converted, for the same reason as A-8.


# ── H-19: console.cpp's switchApp help string vs APP_COUNT ─────────────────

def check_h19() -> Finding:
    fw_text = _read("app/src/debug/serialConsole/console.cpp")
    m = re.search(r'"switchApp".*?"<appId 0\.\.(\d+)>"', fw_text)
    suite_val = int(m.group(1)) if m else None
    fw_val = APP_COUNT - 1
    ok = suite_val is not None and suite_val == fw_val
    return Finding(
        "H-19", "console.cpp's switchApp help string upper bound vs APP_COUNT-1 "
        "(the same drift class as the rest of this register, on the firmware side)",
        "app/src/debug/serialConsole/console.cpp (\"<appId 0..N>\" literal)",
        "app/tools/app_ids_gen.py:APP_COUNT (generated from app/src/appRegistry.h)",
        suite_val, fw_val, ok,
        "" if ok else "help string is stale against the current app roster "
                       "(fixed alongside this gate's introduction, TASK-606)",
    )


ALL_CHECKS = (
    check_a9, check_a10_fetchtype, check_a10_playermodes,
    check_c13, check_d6, check_f16, check_h19,
)


def run_all() -> list:
    findings = []
    for fn in ALL_CHECKS:
        result = fn()
        if isinstance(result, list):
            findings.extend(result)
        else:
            findings.append(result)
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verbose", action="store_true",
                     help="print every pair's citation and note, not just the verdict line")
    args = ap.parse_args()

    findings = run_all()
    bad = [f for f in findings if not f.ok]

    for f in findings:
        print(f.line())
        if args.verbose:
            print(f"        suite:    {f.suite_cite}")
            print(f"        firmware: {f.fw_cite}")
            if f.note:
                print(f"        note:     {f.note}")

    print(f"\n{len(findings) - len(bad)}/{len(findings)} pairs agree")
    if bad:
        print(f"FAIL: {len(bad)} mirror pair(s) disagree or could not be resolved "
              f"(R42): {', '.join(f.id for f in bad)}", file=sys.stderr)
        return 1
    print("OK: check_no_mirrors.py — every registered (suite, firmware) pair agrees")
    return 0


if __name__ == "__main__":
    sys.exit(main())
