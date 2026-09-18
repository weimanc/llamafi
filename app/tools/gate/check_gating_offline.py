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

── THE RUNTIME ARM (TASK-674, M-HARNESS2-runtime-gates.md §4) ────────────────

The closure walk above is a NECESSARY-condition check written as if it were
sufficient (same critique as R34/R18/R17's static siblings): the lists are
hand-kept, so a new key or app is invisible until someone adds it, and the
closure OVER-approximates — a helper reachable in the call graph is not
necessarily a helper actually called on the recorded path.

Where a healthy transcript exists (`app/tools/suite/serialdbg/transcripts/
<id>.json`, TASK-628/671), that recording's command set is not a guess about
what the id's precondition touches — it is the exact list of commands the body
issued and got answered on a real run. So the runtime arm asks the same two
questions (N1, N3) of that command set directly, with **no closure, no
reachability, no hand-kept `NETWORK_APPS` table for app identity**:

  * **N1 (runtime)** — for every recorded `get X` / `set X ...` exchange, is
    `X` in `NETWORK_KEYS`? If the body's own recorded run asked that question
    and got an answer, the dependence is not hypothetical.
  * **N3 (runtime)** — for every recorded `switchApp <n>` exchange, does `<n>`
    resolve (via the codegen'd `app_ids_gen.APP_SLOT`, not a hand-kept name
    list) to an app in `NETWORK_APPS`? This reads the transcript's own
    `switchApp` commands, exactly as the design's §4 table names ("read app
    switches off the ... commands") — `switchApp` rather than `tap`, because
    a `tap` on a taskbar slot is one more level of pixel-coordinate inference
    away from "which app did this activate" than the command that already
    says so directly.

    `<n>` IS THE `AppId` ENUM VALUE, not a taskbar position: `switchApp` casts
    its argument straight to `AppId` (app/src/debug/serialConsole/cmdMisc.cpp:34).
    `APP_SLOT` is usable for the lookup because `app_ids_gen.APP_ORDER` is
    generated from the same `APP_X` rows as the enum (app/src/appRegistry.h:26),
    so its index IS the enum value — which is NOT true of taskbar geometry
    (`WebRadio` has an `AppId` and no taskbar slot at all). If those two ever
    diverge, this lookup is the thing that breaks.

  THE RESIDUAL, STATED RATHER THAN HIDDEN. N3-runtime sees only `switchApp`.
  An app entered by a taskbar `tap` is invisible to it, and gating transcripts
  do contain taps. What makes that survivable today is a cheap cross-check, run
  2026-09-19 and reproducible: the `get appId` replies recorded across all 17
  gating transcripts name only Spotify, Clock, Life, Settings and Aquarium —
  no `NETWORK_APPS` app is ever active in any of them, by any route. That is a
  measurement of the current corpus, not a property of the arm; a future id
  that taps its way into Weather would need this arm to read `appId` replies
  as well as `switchApp` commands.

N2 (a suite helper that BLOCKS on a fetch) and N4 (host file layout) have no
runtime analogue here: a transcript is a serial trace, not a call graph or a
filesystem listing, so it cannot show that a Python helper blocked or that a
host path was open()'d. Those two stay static-only.

WHAT A RUNTIME FINDING MEANS, AND WHAT IT DOES NOT. A transcript is evidence
about the RUN THAT WAS RECORDED — a healthy board, at the ELF stamped into the
file, on the date it was taken — never about the firmware in the tree today
(`lib/canfail.py`'s docstring draws this line for R34; the same line applies
here unchanged). A runtime finding says "this dependence is not hypothetical:
it happened," not "it still happens on the current build." An id with NO
transcript contributes nothing here — it is a census line (`UNRECORDED`),
never a finding, because the recorded set is a ratchet a host gate cannot
demand (TASK-643 owns growing it).

Findings from both arms share ONE ledger (`gating_offline_exceptions.md`), one
`(kind, id)` key space, and one exit-code convention — per M-HARNESS2's rule
that a runtime arm is added to its static sibling's gate, not forked into a
parallel one.
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

sys.path.insert(0, TOOLS)
from lib import replay as RP                                    # noqa: E402
from app_ids_gen import APP_SLOT                                # noqa: E402

#: `switchApp <AppId>` -> app name, off the SAME codegen the firmware and the
#: suite build against (`app/tools/app_ids_gen.py`, regenerated by
#: `gen_app_registry.py`) — not a hand-kept table like `NETWORK_APPS`/N3.
#: `APP_SLOT`'s index is the `AppId` enum value (both come from `APP_X` order);
#: it is NOT a taskbar position. See the docstring's N3-runtime paragraph.
APP_NAME_BY_SLOT = {i: name for name, i in APP_SLOT.items()}

LEDGER_REL = "docs/verification/gating_offline_exceptions.md"
TRANSCRIPTS_REL = "app/tools/suite/serialdbg/transcripts"

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
_SWITCH_APP_RE = re.compile(r"^\s*switchApp\s+(\d+)\s*$")
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


# ── the runtime arm (TASK-674) ──────────────────────────────────────────────

def load_transcripts(directory: str = None) -> tuple:
    """-> ({id: Transcript}, [errors]) for every `<id>.json` under `directory`.

    Mirrors `check_can_go_red.load_transcripts` deliberately — same loader
    shape, same id-matches-filename check — because a transcript is the same
    kind of object to both gates; this one just reads its command set instead
    of replaying it.
    """
    directory = directory or os.path.join(ROOT, TRANSCRIPTS_REL)
    out: dict = {}
    errors: list = []
    if not os.path.isdir(directory):
        return out, errors
    for path in sorted(glob.glob(os.path.join(directory, "*.json"))):
        stem = os.path.splitext(os.path.basename(path))[0]
        try:
            t = RP.Transcript.load(path)
        except (OSError, ValueError) as e:
            errors.append(f"{path}: unreadable transcript "
                          f"({type(e).__name__}: {e}); re-record it or delete it")
            continue
        tid = t.tid or stem
        if tid != stem:
            errors.append(f"{path}: file is named {stem!r} but records id {tid!r}")
            continue
        out[tid] = t
    return out, errors


def runtime_evidence(t) -> list:
    """-> [(kind, detail)] read off ONE recorded transcript's command set.

    No closure, no reachability: `t.exchanges` is keyed `(cmd, nth)` in record
    order, and `cmd` is the literal command string the body sent and got an
    answer for on a real run. N1 and N3 only — see the module docstring for
    why N2/N4 have no runtime analogue.
    """
    hits: list = []
    for cmd, nth in t.exchanges:
        m = _SET_GET_RE.match(cmd)
        if m and m.group(1) in NETWORK_KEYS:
            hits.append(("network-key",
                         f"recorded exchange `{cmd}` (occurrence #{nth})"))
            continue
        sm = _SWITCH_APP_RE.match(cmd)
        if sm:
            name = APP_NAME_BY_SLOT.get(int(sm.group(1)))
            if name in NETWORK_APPS:
                hits.append(("network-app",
                             f"recorded exchange `{cmd}` switches to {name}"))
    out: list = []
    for kind in KINDS:
        matches = [d for k, d in hits if k == kind]
        if matches:
            n = len(matches)
            out.append((kind, matches[0] + (f" (+{n - 1} more)" if n > 1 else "")))
    return out


def runtime_findings(meta: dict, transcripts: dict) -> list:
    """-> [(kind, id, message)], the runtime-arm counterpart of `findings()`.

    An id with no transcript contributes nothing here — see UNRECORDED
    handling in `main()`. This never claims anything about the firmware in
    the tree today; see the module docstring's "WHAT A RUNTIME FINDING MEANS"
    section.
    """
    out: list = []
    for tid in sorted(meta):
        rec = meta[tid]
        cls = rec.get("cls") if isinstance(rec, dict) else None
        if cls not in GATING:
            continue
        t = transcripts.get(tid)
        if t is None:
            continue
        for kind, detail in runtime_evidence(t):
            out.append((kind, tid,
                        f"{tid} ({cls}) -> {kind} [RUNTIME, TASK-674]: {detail}. "
                        f"This was OBSERVED on the id's recorded healthy run, not "
                        f"inferred from a call-graph closure — R36 still requires "
                        f"the precondition be satisfiable OFFLINE"))
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

    found_static = findings(meta, fns, reg)
    transcripts, t_errors = load_transcripts()
    found_runtime = runtime_findings(meta, transcripts)
    found = found_static + found_runtime

    ledger, lerrs = parse_ledger()
    fails, n_exc = evaluate(found, ledger)
    fails = t_errors + lerrs + fails

    gating_ids = {tid for tid, r in meta.items()
                  if isinstance(r, dict) and r.get("cls") in GATING}
    recorded = sorted(tid for tid in gating_ids if tid in transcripts)
    unrecorded = sorted(gating_ids - set(transcripts))
    static_keys = {(k, t) for k, t, _m in found_static}
    runtime_only = sorted({(k, t) for k, t, _m in found_runtime} - static_keys)

    if args.print_rows:
        for kind, tid, _m in found:
            print(f"| `{tid}` | {kind} | … | TASK-617 | "
                  f"{datetime.date.today().isoformat()} |")
    if args.verbose:
        n_gate = len(gating_ids)
        ids = sorted({t for _k, t, _m in found})
        print(f"gating ids: {n_gate}; network/host-dependent: {len(ids)} "
              f"({', '.join(ids) or 'none'}); {len(found)} finding(s), "
              f"{len(ledger)} ledger rows, {n_exc} used")
        print(f"runtime arm (TASK-674): {len(recorded)} recorded / "
              f"{n_gate} gating ids ({len(unrecorded)} UNRECORDED: "
              f"{', '.join(unrecorded) or 'none'})")
        if runtime_only:
            print(f"  [note] runtime-only findings (the static closure walk "
                  f"missed these; the recording is ground truth): "
                  f"{', '.join(f'{t}/{k}' for k, t in runtime_only)}")

    if fails:
        print(f"FAIL: check_gating_offline.py — {len(fails)} finding(s) "
              f"(TASK-626 / R36, incl. TASK-674 runtime arm):")
        for f in fails:
            print(f"  {f}")
        return 1
    n_ids = len({t for _k, t, _m in found})
    print(f"OK: check_gating_offline.py — {n_ids} gating id(s) depend on the "
          f"outside world (static + TASK-674 runtime arm), all on the dated "
          f"shrink-only ledger ({len(ledger)} rows). {len(recorded)}/"
          f"{len(gating_ids)} gating ids have a recorded transcript "
          f"({len(unrecorded)} UNRECORDED). R36/TASK-617 is met when this "
          f"reads 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
