#!/usr/bin/env python3
"""check_gating_offline.py — a gating class may not need the outside world.
TASK-626 / M-HARNESS2 R36.

R36: **a RIG, HEALTH or CORE test's precondition MUST be satisfiable offline on a
healthy board.** The cost of breaking it is not a lost test, it is a lost RUN: a
CORE id that FAILs on a 45 s live HTTPS timeout runs at index 14 under TASK-566's
class order and NOT-RUNs the 167 FEATURE ids below it. A network outage must not
be able to declare the firmware untestable — nor may a missing host directory
(`B-2`: a CORE id that was a host-side source grep, demoted as `T133` in
TASK-591 and the reason the host-file-layout half of this check reads zero).

WHAT IT ASSERTS. For every id whose class can block, the gate walks the id's body
and every same-package helper it reaches, and fails the id if that closure touches
one of four things, each of which is a fact about the outside world rather than
about the board:

  N1  a device debug key whose value is produced by (or arms) a live external
      HTTP fetch — `NETWORK_KEYS`, every entry carrying its firmware evidence;
  N2  a suite helper that BLOCKS on such a fetch — `NETWORK_HELPERS`;
  N3  an app whose activation issues an external fetch — `NETWORK_APPS`. This is
      the shape a key-level check cannot see: `T-BUSY-03` names no fetch key at
      all, it just switches to Weather and Crypto, and their activation fetch is
      what its `shellBusy` reading depends on;
  N4  the host FILE LAYOUT — `open`, `glob`, `os.path.exists`, `subprocess` — in
      a gating body. `B-2`'s shape. Reads zero and is blocking there.

WHY A CLOSURE WALK AND NOT A GREP OVER THE BODY. Every one of the seven ids in
scope reaches its network dependence through a helper: `_wait_chart_complete`,
`_poll_chart_len_positive`, `_stock_ok_count`, `_wait_for_queue`. A grep over the
80 lines of the body sees none of them, which is exactly how seven CORE ids came
to be network-dependent without anyone writing it down.

LANDING. Blocking, against a dated shrink-only ledger,
`docs/verification/gating_offline_exceptions.md`. The ledger is NOT an amnesty:
every row is keyed on one `(kind, id)` pair, carries an owning task and a date,
and a row whose finding no longer occurs is itself a blocking failure. It exists
because the only two resolutions — demote the id out of the gating class, or
inject its precondition so it no longer needs the network — **change what the
suite blocks on**, and that is the human's call. TASK-591's twenty demotions were
put to the human for the same reason and approved as a set.

**This gate reading zero is an exit criterion of TASK-617** (the held class-order
switch). It does not read zero today: seven ids are ledgered. Anyone checking
that criterion should read the count this gate prints, not this paragraph.

No DUT, no build, no network. Sub-second.

    python3 app/tools/gate/check_gating_offline.py [--verbose] [--print-rows]
                                                   [--explain <id>]
"""

from __future__ import annotations

import argparse
import ast
import datetime
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))
PKG = os.path.join(TOOLS, "suite", "serialdbg")

LEDGER_REL = "docs/verification/gating_offline_exceptions.md"

#: The classes whose failure stops the run. FEATURE is the safe default and is
#: not policed here — a FEATURE id may depend on whatever it likes.
GATING = ("RIG", "HEALTH", "CORE")

KINDS = ("network-key", "network-helper", "network-app", "host-file-layout")

#: N1 — device debug keys whose value is PRODUCED BY, or which ARM, a live
#: external HTTP fetch. Each is a fact about firmware, cited:
#:   chartLen, fetchOkCount, fetchErrCount, lastChartFetch, stockChartProgress,
#:   quoteOkCount, lastQuoteFetch, stockQuoteProgress, fetchFailed, triggerFetch
#:       — StockApp's Yahoo Finance chart/quote fetches (`app/src/apps/stockApp.cpp`);
#:         `set triggerFetch 1` enqueues one on the dataTask.
#:   cryptoReady, cryptoLastFetch, cryptoHttpCode, cryptoFetchPhase
#:       — CryptoApp's price fetch.
#:   weatherReady, weatherFetchPhase, geocode
#:       — WeatherApp's forecast + geocode fetches.
#:   teletextReady, teletextHttpCode, triggerTeletextFetch
#:       — NOS Teletekst fetch.
#:   prAircraftCount, prLastHttp, triggerPlaneRadarFetch
#:       — adsb.fi fetch.
#:   wrLastHttp, wrIcy, wrCount
#:       — radio-browser.info station list and the ICY stream itself.
#: Deliberately NOT here: `activeError`, `lastHttp`, `backoff`, `dataq`, `heap` —
#: they are readable and meaningful with no network at all, and including them
#: would make the check accuse the whole shell.
NETWORK_KEYS = frozenset("""
chartLen fetchOkCount fetchErrCount lastChartFetch stockChartProgress
quoteOkCount lastQuoteFetch stockQuoteProgress fetchFailed triggerFetch
cryptoReady cryptoLastFetch cryptoHttpCode cryptoFetchPhase
weatherReady weatherFetchPhase geocode
teletextReady teletextHttpCode triggerTeletextFetch
prAircraftCount prLastHttp triggerPlaneRadarFetch
wrLastHttp wrIcy wrCount
""".split())

#: N2 — suite helpers that BLOCK on something outside the board. The Spotify ones
#: are the second half of the class: `T_BI_03`'s precondition is a live Spotify
#: queue of >= 2, which under TASK-243's permanent 403 it does not get.
NETWORK_HELPERS = frozenset({
    "_wait_chart_complete", "_wait_quote_complete", "_poll_chart_len_positive",
    "_stock_ok_count", "_stock_quote_count",
    "_wait_for_queue", "wait_for_queue", "_wait_queue_len",
})

#: N3 — apps whose ACTIVATION issues an external fetch, so switching to them makes
#: the id's reading depend on the network even when it names no fetch key.
#: (`app/src/apps/{weatherApp,cryptoApp,stockApp,teletextApp,planeRadarApp,
#: webRadioApp}.cpp` — each issues its fetch from `init()`/`resume()`.)
NETWORK_APPS = frozenset({"Weather", "Crypto", "Stock", "Teletext",
                          "PlaneRadar", "WebRadio"})

#: N4 — the host file layout. `B-2`'s shape: a CORE id that greps the checkout.
HOST_FS_NAMES = frozenset({"open", "glob", "iglob", "listdir", "walk", "exists",
                           "isfile", "isdir", "run", "check_output", "Popen"})

_SET_GET_RE = re.compile(r"^\s*(?:get|set)\s+([A-Za-z_][A-Za-z0-9_]*)\b")
_SEP_RE = re.compile(r":?-{2,}:?")
_TASK_RE = re.compile(r"^TASK-\d+$")
TEST_ID_RE = re.compile(r"T\d{3}[a-z]?|T_[A-Z0-9]+(?:_[A-Z0-9]+)*_\d+[a-z]?|"
                        r"T-[A-Z0-9]+-\d+[a-z]?")


# ── the package, parsed once ─────────────────────────────────────────────────

def load_package(pkg: str = None) -> tuple:
    """-> (functions {name: [node]}, registry {id: fnname})."""
    pkg = pkg or PKG
    fns: dict = {}
    reg: dict = {}
    for path in sorted(glob.glob(os.path.join(pkg, "*.py"))):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                tree = ast.parse(fh.read())
        except (OSError, SyntaxError):
            continue
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fns.setdefault(n.name, []).append((rel, n))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if not any(x == "ALL" or "TEST" in x.upper() for x in names):
                continue
            if isinstance(node.value, ast.Dict):
                for k, v in zip(node.value.keys, node.value.values):
                    if isinstance(k, ast.Constant) and isinstance(k.value, str) \
                            and isinstance(v, ast.Name):
                        reg.setdefault(k.value, v.id)
    return fns, reg


def closure(fnname: str, fns: dict) -> set:
    """Every same-package function reachable from `fnname`, including itself."""
    seen: set = set()
    stack = [fnname]
    while stack:
        cur = stack.pop()
        if cur in seen or cur not in fns:
            continue
        seen.add(cur)
        for _rel, node in fns[cur]:
            for n in ast.walk(node):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                        and n.func.id in fns:
                    stack.append(n.func.id)
    return seen


def _literals(node: ast.AST) -> set:
    """Short string constants in a function — command strings and app names.

    LONG strings are excluded because the corpus's docstrings quote firmware key
    names extensively (one shared diagnostic helper's docstring names
    `fetchOkCount`, `chartLen` and `stockChartProgress` in prose), and a checker
    that reads prose accuses every caller of a helper that merely EXPLAINS a
    fetch. 80 characters is comfortably above every command string and every app
    name in the corpus and far below every docstring.
    """
    out: set = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) \
                and len(n.value) <= 80:
            out.add(n.value)
        elif isinstance(n, ast.JoinedStr):
            txt = "".join(v.value for v in n.values if isinstance(v, ast.Constant))
            if txt and len(txt) <= 80:
                out.add(txt)
    return out


#: Family switch helpers whose target app is in their NAME rather than in an
#: argument. Keeping this a table rather than a name prefix means a new
#: `_switch_to_<app>` helper is invisible to N3 until someone adds it here —
#: which is the safe direction to be wrong in only because `_switch_to(dut, "X")`
#: is the form the corpus actually uses; this table has one entry.
SWITCH_HELPERS = {"_switch_to_stock": "Stock"}

#: `APP_SLOT['Weather']` inside an f-string — `switchApp {APP_SLOT['Weather']}`.
_APP_SLOT_RE = re.compile(r"APP_SLOT\[['\"]([A-Za-z]+)['\"]\]")


def _switched_apps(node: ast.AST) -> set:
    """App names this function ACTIVATES.

    Narrow on purpose. An app name that merely appears as a string is not a
    switch: `_restore_spotify` COMPARES `get appId`'s name against "WebRadio" and
    "LocalPlayer" to decide whether it must step off a player app first, and a
    checker that reads that as "drives WebRadio" accuses the eight ids that
    restore Spotify of needing radio-browser.info. Only two forms count — the
    first argument of `_switch_to(dut, "X")`, and `APP_SLOT['X']` used to build a
    `switchApp` or `tap` command.
    """
    out: set = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                and n.func.id == "_switch_to" and len(n.args) >= 2 \
                and isinstance(n.args[1], ast.Constant) \
                and isinstance(n.args[1].value, str):
            out.add(n.args[1].value)
        elif isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) \
                and n.value.id == "APP_SLOT" \
                and isinstance(n.slice, ast.Constant) \
                and isinstance(n.slice.value, str):
            out.add(n.slice.value)
        elif isinstance(n, ast.JoinedStr):
            txt = ast.unparse(n) if hasattr(ast, "unparse") else ""
            out |= set(_APP_SLOT_RE.findall(txt))
    # `APP_SLOT[name] for name in ["Clock", "Weather", "Crypto", …]` — the slot is
    # a VARIABLE, so the two forms above see nothing, and `T-BUSY-03` (whose whole
    # subject is what a canvas tap does in six named apps, two of which fetch on
    # activation) reads clean. When a function indexes APP_SLOT dynamically, the
    # app names it drives are the app names it MENTIONS. Scoped to such functions
    # only, so a body that merely compares against an app name is untouched.
    if any(isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name)
           and n.value.id == "APP_SLOT" and not isinstance(n.slice, ast.Constant)
           for n in ast.walk(node)):
        for n in ast.walk(node):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) \
                    and n.value in NETWORK_APPS:
                out.add(n.value)
    return out


def evidence(fnname: str, fns: dict) -> list:
    """-> [(kind, detail)] for one id's whole call closure."""
    hits: list = []
    reach = closure(fnname, fns)
    for name in sorted(reach):
        if name in NETWORK_HELPERS:
            hits.append(("network-helper", f"reaches `{name}()`"))
        if name in SWITCH_HELPERS and SWITCH_HELPERS[name] in NETWORK_APPS:
            hits.append(("network-app",
                         f"reaches `{name}()`, which activates "
                         f"{SWITCH_HELPERS[name]}"))
        for rel, node in fns.get(name, []):
            for lit in sorted(_literals(node)):
                m = _SET_GET_RE.match(lit)
                if m and m.group(1) in NETWORK_KEYS:
                    hits.append(("network-key",
                                 f"`{lit.strip()}` in {name}() ({rel})"))
            for app in sorted(_switched_apps(node)):
                if app in NETWORK_APPS:
                    hits.append(("network-app",
                                 f"switches to {app} in {name}() ({rel})"))
            for n in ast.walk(node):
                fn = n.func if isinstance(n, ast.Call) else None
                nm = None
                if isinstance(fn, ast.Name):
                    nm = fn.id
                elif isinstance(fn, ast.Attribute):
                    nm = fn.attr
                if nm is not None and nm in NETWORK_HELPERS:
                    hits.append(("network-helper",
                                 f"calls `{nm}()` in {name}() ({rel})"))
                if nm is not None and nm in HOST_FS_NAMES:
                    hits.append(("host-file-layout",
                                 f"`{nm}(...)` in {name}() ({rel})"))
    # One finding per kind per id: the id is either offline-satisfiable or not,
    # and eleven lines of the same accusation is a worse report, not a stronger
    # one. The first piece of evidence for each kind is kept.
    out: list = []
    for kind in KINDS:
        first = next((d for k, d in hits if k == kind), None)
        if first:
            n = sum(1 for k, _d in hits if k == kind)
            out.append((kind, first + (f" (+{n - 1} more)" if n > 1 else "")))
    return out


def findings(meta: dict, fns: dict = None, reg: dict = None) -> list:
    """-> [(kind, id, message)]. `meta` is build_all_meta()'s record dict."""
    if fns is None or reg is None:
        fns, reg = load_package()
    out: list = []
    for tid in sorted(meta):
        rec = meta[tid]
        cls = rec.get("cls") if isinstance(rec, dict) else None
        if cls not in GATING:
            continue
        fn = reg.get(tid)
        if not fn:
            continue
        for kind, detail in evidence(fn, fns):
            out.append((kind, tid,
                        f"{tid} ({cls}) -> {kind}: {detail}. R36: a gating "
                        f"class's precondition must be satisfiable OFFLINE on a "
                        f"healthy board — a network outage may not NOT-RUN the "
                        f"classes below it"))
    return out


# ── the ledger ───────────────────────────────────────────────────────────────

def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_ledger(path: str = None) -> tuple:
    path = path or os.path.join(ROOT, LEDGER_REL)
    rows: dict = {}
    errors: list = []
    if not os.path.exists(path):
        return rows, errors
    rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
    header = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().split("\n")
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if not s.startswith("|"):
            header = None
            continue
        cells = _cells(s)
        if all(_SEP_RE.fullmatch(x) for x in cells if x):
            continue
        if header is None:
            header = cells
            continue
        if len(cells) < 5:
            continue
        tid, kind = cells[0].strip("`* "), cells[1].strip("`* ").lower()
        owner, since = cells[3].strip("`* "), cells[4].strip("`* ")
        where = f"{rel}:{i}"
        if not TEST_ID_RE.fullmatch(tid):
            errors.append(f"L {where}: {tid!r} is not a test id")
            continue
        if kind not in KINDS:
            errors.append(f"L {where}: kind {kind!r} is not one of {list(KINDS)}")
            continue
        if kind == "host-file-layout":
            errors.append(f"L {where}: `host-file-layout` is NOT exemptable. It "
                          f"reads zero and is blocking there — `B-2`'s shape is "
                          f"the one R36 names as unarguable")
            continue
        if not _TASK_RE.match(owner):
            errors.append(f"L {where}: owner {owner!r} must be a TASK-NNN id")
            continue
        try:
            datetime.date.fromisoformat(since)
        except ValueError:
            errors.append(f"L {where}: since {since!r} is not an ISO date")
            continue
        rows[(kind, tid)] = where
    return rows, errors


def evaluate(found: list, ledger: dict) -> tuple:
    fails: list = []
    used: set = set()
    for kind, tid, msg in found:
        if (kind, tid) in ledger:
            used.add((kind, tid))
            continue
        fails.append(f"{kind.upper()} {msg}")
    for key, where in sorted(ledger.items()):
        if key not in used:
            fails.append(f"STALE {where}: the {key[0]} finding for {key[1]} no "
                         f"longer occurs — delete the row. This ledger only shrinks")
    return fails, len(used)


def _load_meta():
    sys.path.insert(0, TOOLS)
    from suite.serialdbg import build_all_meta          # noqa: PLC0415
    return build_all_meta()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--print-rows", action="store_true")
    ap.add_argument("--explain", metavar="ID")
    args = ap.parse_args()

    meta = _load_meta()
    fns, reg = load_package()

    if args.explain:
        fn = reg.get(args.explain)
        print(f"{args.explain} -> {fn}")
        for kind, detail in evidence(fn, fns) if fn else []:
            print(f"  {kind}: {detail}")
        return 0

    found = findings(meta, fns, reg)
    ledger, lerrs = parse_ledger()
    fails, n_exc = evaluate(found, ledger)
    fails = lerrs + fails

    if args.print_rows:
        for kind, tid, _m in found:
            print(f"| `{tid}` | {kind} | … | TASK-617 | "
                  f"{datetime.date.today().isoformat()} |")
    if args.verbose:
        n_gate = sum(1 for r in meta.values()
                     if isinstance(r, dict) and r.get("cls") in GATING)
        ids = sorted({t for _k, t, _m in found})
        print(f"gating ids: {n_gate}; network/host-dependent: {len(ids)} "
              f"({', '.join(ids) or 'none'}); {len(found)} finding(s), "
              f"{len(ledger)} ledger rows, {n_exc} used")

    if fails:
        print(f"FAIL: check_gating_offline.py — {len(fails)} finding(s) "
              f"(TASK-626 / R36):")
        for f in fails:
            print(f"  {f}")
        return 1
    n_ids = len({t for _k, t, _m in found})
    print(f"OK: check_gating_offline.py — {n_ids} gating id(s) depend on the "
          f"outside world, all on the dated shrink-only ledger "
          f"({len(ledger)} rows). R36/TASK-617 is met when this reads 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
