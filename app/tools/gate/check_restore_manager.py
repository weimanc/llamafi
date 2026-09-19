#!/usr/bin/env python3
"""check_restore_manager.py — a test that mutates device state restores it through
the manager. TASK-602 / M-HARNESS2 R17.

THE DEFECT. A test writes device state and does not put it back, or puts it back
only on the path where it passed. Measured: `F-9` (4 of 30 WebRadio bodies restore
anything), `E-15` (17 of 31 player rows leak), `C-15` (a restore on the pass path
only, so every FAILURE leaves an arbitrary app), `C-12`/`D-15`/`E-4` (seven restores
default to a literal, `r.get('val', 0)` for `playerMode` four times, silently
REWRITING persisted state). The cost is not theoretical: three armed injectors
nothing clears wedged a family each for a whole run, and one of them spent a year
filed as network churn.

WHY THIS GATE DOES NOT LOOK FOR `finally:`. R17 asks for a mechanism, and the
check has to assert the mechanism is USED. A `try/finally` matches a pattern and
still leaks, in every one of the four ways above:

  * `finally:` restoring a DIFFERENT variable than the body set — passes any
    static match for "a restore exists near a set";
  * `finally: dut.cmd(f"set playerMode {r.get('val', 0)}")` — a restore whose
    snapshot defaulted, i.e. a write of a literal dressed as a restore;
  * `finally: dut.cmd("set bgPoll 1")` — a restore to a guessed constant, correct
    only for callers that happened to find it at 1;
  * `dut.cmd(...)` for the restore at all — unacknowledged, so a REFUSED restore
    is indistinguishable from a successful one.

All four are in the negative suite as fixtures that this gate FLAGS. What it
credits is exactly one thing: the mutation is lexically inside a `with` block on
`Dut.saved(...)` / `Dut.injected(...)` naming that variable. Those close all four
by construction — the snapshot raises rather than defaults, the exit runs on every
path, and the write is `set_val`, which raises unless the device acks.

R17 IS A RATCHET (§14 of the requirements: `ratchet` row). So the gate is blocking
against a DATED, PER-MODULE, SHRINK-ONLY ledger —
`docs/verification/unrestored_mutations_ratchet.md` — in both directions: a cap
above the real count is headroom to reintroduce the defect and is itself a failure.

  M1  no module exceeds its ledgered count of unrestored mutations.
  M2  no ledger row is stale — a row above the real count must be lowered.
  M3  no ledger row names a module that does not exist.
  M4  every row carries an owning TASK id and an ISO date; no wildcards.
  M5  `lib/` holds ZERO, unledgered and unexemptable — the managers live there.
  M6  every DELEGATING_MANAGERS entry still delegates to `saved`/`injected`.
      A registry entry is a credit for every call site of that helper; when the
      helper stops using the manager the credit becomes a lie, silently.

No DUT, no build, no network. Sub-second.

    python3 app/tools/gate/check_restore_manager.py [--verbose] [--print-counts]
                                                    [--list <module>]

── THE RUNTIME ARM (TASK-673, M-HARNESS2-runtime-gates.md §4) ────────────────

The static scan above is a NECESSARY-condition check written as if it were
sufficient, and it says so honestly: it cannot see a restore that only runs on
the FAIL path (§4's own words: "cannot see a restore on the fail path (`C-15`),
cannot see a `with` whose restore was refused, cannot see a restore of the
wrong variable at runtime"). Those are runtime facts about a specific EXECUTION,
and the static AST walk has no execution to look at.

`lib/canfail.sweep()` already drives one: it poisons a healthy transcript at
every position with four poisons and runs the real body through the real `Dut`,
searching for a reply sequence that reddens it. TASK-671/674 read outcomes off
that search; this arm reads a THIRD thing off the exact same replays, at ZERO
extra replay cost (`Sweep.restore_leaks`, populated inline in the search loop
— see `lib/canfail.py`'s docstring for the instrumentation).

WHAT COUNTS AS A FINDING, STATED ONCE, PRECISELY (read this before touching
the arm — it is the one place this task can go wrong and produce a confident,
plausible, WRONG result):

  A `set VAR ...` command that the body issued and got ACKED at some position
  BEFORE a FAIL/UNMET verdict was recorded is a MUTATION on that poisoned run.
  (It can only appear there acked: a MISS before the verdict aborts the body
  before any verdict is written, which voids the whole replay row before this
  arm ever sees it — `lib/replay.py`'s ordinary miss-handling, unmodified.)

  For each such mutated var, look at every OTHER `set VAR ...` command ANYWHERE
  in the whole run — NOT only from the verdict onward; see the correction
  below for why:

    * a LATER `set VAR ...` anywhere at all, regardless of whether IT hit the
      transcript -> a set-back was ATTEMPTED on this path. Not a finding, full
      stop — true whether the attempt reached the transcript or not.
    * NO later `set VAR ...` anywhere -> `NO_RESTORE_ATTEMPTED`. This is
      R17's C-15 shape, observed rather than inferred, and the only kind this
      arm reports as a finding.

  CORRECTION, KEPT HERE BECAUSE IT IS THE WHOLE REASON THE RULE READS THIS WAY.
  The first draft only looked "from the verdict onward" — it reads more
  literally as "the FAIL branch's own cleanup", which is the shape the design
  doc describes. It produces a real false positive: `T-CDWN-02`'s `shellBusy`
  mutation is properly `with dut.injected("shellBusy", 1, clear_to="0")`
  -managed (`suite/serialdbg/shell.py`), but the `with` block closes — and the
  manager's restore fires — BEFORE the later `fail()` that inspects the tap
  reply's `skipped` field, not after it (the checks live outside the `with`).
  A verdict-relative split saw the restore land before the verdict and called
  it a leak. What R17 actually asks is whether a set-back was EVER attempted
  once the var was mutated, not whether it landed on a particular side of the
  verdict a body's own control flow happens to write it on.

THE TRAP THIS AVOIDS. A recorded transcript is a HEALTHY run; the command tail
after a poison-induced FAIL/UNMET verdict is very often NOT the tail the
healthy recording took, so a set-back attempted on this path frequently MISSES
the transcript (`lib/replay.py`'s "a miss AFTER the verdict does not void the
row" rule exists for exactly this). Treating a missed set-back as "no restore"
would flag nearly every mutating body and would be measuring the RECORDING,
not the SUITE — the confident-wrong result this docstring is warning about.
So a later `set VAR` that missed is its own kind,
`RESTORE_ATTEMPTED_UNRECORDED` — printed, counted, **never** a finding, and
never merged into "clean" either (it says nothing either way; see census
counts in `--verbose`).

A SECOND TRAP, CAUGHT AT REVIEW AND CLOSED. "ACKED" above is NOT "the write
hit the transcript" — those are different questions and a REFUSE poison is
exactly where they split. `poison_reply`'s REFUSE branch rewrites a reply to
`{"ok": false, "err": "poisoned", ...}`; `StubTransport.write` still finds
that exchange (no `TranscriptMiss`), but the device DECLINED. `set_val` (and
every body that checks `r.get("ok")` itself) raises/aborts on it, so nothing
was mutated at all — a REFUSE-poisoned `set` that is properly managed or
properly checked never runs its `with` body, and there is nothing to restore.
The first draft of `_RestoreWitness` logged "did the write raise
`TranscriptMiss`" as `ok`, which is true for a REFUSE (the exchange exists) and
produced two real false positives, measured on the live ledger: `T-BUSY-01b`'s
`bgPoll` (`_bgpoll_suspended`, properly `dut.saved(...)`-managed) and `T085`'s
`songDuration` (a raw `dut.cmd` explicitly checked with
`if not r_force.get("ok"): fail(...); return` — the body's OWN guard against
exactly this). `lib/canfail._replied_ok()` fixes it: `acked` now means the
recorded reply for that exchange is a JSON object with `ok: true`, read back
from the (possibly poisoned) transcript at the moment the command is logged,
not inferred from whether the lookup itself raised. See `_replied_ok`'s and
`_RestoreWitness`'s docstrings in `lib/canfail.py` for the full account,
including why PERTURB and DROP are BOTH safe here (`ok` is a `FRAMING` field,
preserved verbatim by both) and why SILENCE is too (`_replied_ok([])` is
`False`, independent of whether `write()` itself raised).

A KNOWN LOWER BOUND. "Any later `set VAR`, anywhere" credits a second,
unrelated mutation of the same var as a restore — a body mutating `wrStop`
(or `wrMaxVol`, `wrPlay`, `spotifyWedge`, … — all measured with repeated
same-var `set`s in one id in the live corpus) three times and never actually
restoring it clears this arm on the second write alone. `T_WR_VOL_CLAMP` was
checked by hand and genuinely restores; the arm did not verify that, and a
real repeat-mutation leak of the same shape would clear identically. This is
not closed here — it needs a value-aware comparison against the pre-mutation
state — and every count this arm reports is a LOWER BOUND for exactly this
reason (see `lib/canfail.py`'s `_restore_leaks()` docstring).

`SELF_REARMING_VARS` (`suite/serialdbg/_restore_scan.py`, currently `cooldown`
— the firmware overwrites `shell::state().cooldownMs` on every consumed tap,
so there is nothing a restore could put back) is excluded here exactly as the
static gate excludes it, for the same reason: it would otherwise be the single
largest source of findings and every one of them would be a false positive
against a documented, cited structural exemption.

An id with NO transcript contributes nothing — a census line, never a finding
(TASK-643 owns growing the recorded set; a host gate cannot demand a board
session).

THE LEDGER. `unrestored_mutations_ratchet.md`'s existing table is a per-MODULE
cap and cannot express "this VAR leaks on an observed runtime path" — a var
usually leaks through one unmanaged mutation site shared by many ids in the
module, so keying by id would multiply one defect into dozens of rows for no
information gain. The runtime section below keys by **var**: one row per
variable this arm has observed leaking on at least one real FAIL/UNMET replay,
with one example id/path as evidence. Same discipline as every other ledger in
this family — dated, owned (`TASK-673`), shrink-only, and a stale row (the var
no longer leaks) is itself a blocking failure.

    python3 app/tools/gate/check_restore_manager.py --verbose
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

sys.path.insert(0, TOOLS)

# TASK-592: the pure AST analysis moved to suite/serialdbg/_restore_scan.py so
# `_order.py`'s edge enumeration could reuse it without `gate/` (a LEAF —
# nothing may import from it) being imported by `suite/`. Every name below is
# unchanged in behaviour; see that module's docstring for why it moved.
from suite.serialdbg._restore_scan import (      # noqa: E402
    MANAGER_METHODS, DELEGATING_MANAGERS, WIRE_METHODS, MECHANISM_FUNCS,
    MECHANISM_MODULE, SELF_REARMING_VARS, unrestored_mutations,
)

# TASK-673: the runtime arm. `lib/canfail` never imports a suite (its own
# dependency rule), so `SELF_REARMING_VARS` above — a suite-side exemption —
# is applied HERE, in the gate, not pushed down into `lib/`.
from lib import canfail as CF                    # noqa: E402
from lib import replay as RP                     # noqa: E402

LEDGER_REL = "docs/verification/unrestored_mutations_ratchet.md"
TRANSCRIPTS_REL = "app/tools/suite/serialdbg/transcripts"

SCAN_ROOTS = ("suite", "lib")

_TASK_RE = re.compile(r"^TASK-\d+$")
_SEP_RE = re.compile(r":?-{2,}:?")


def scan(root: str = None) -> tuple:
    """-> ({module: count}, {module: [(line, var)]}) over SCAN_ROOTS."""
    root = root or TOOLS
    counts: dict = {}
    detail: dict = {}
    for sub in SCAN_ROOTS:
        base = os.path.join(root, sub)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fn in sorted(filenames):
                if not fn.endswith(".py"):
                    continue
                path = os.path.join(dirpath, fn)
                rel = os.path.relpath(path, root).replace(os.sep, "/")
                with open(path, encoding="utf-8", errors="replace") as fh:
                    src = fh.read()
                try:
                    sites = unrestored_mutations(
                        src,
                        MECHANISM_FUNCS if rel == MECHANISM_MODULE else frozenset())
                except SyntaxError as e:
                    counts[rel] = -1
                    print(f"  (unparseable: {rel}: {e})", file=sys.stderr)
                    continue
                counts[rel] = len(sites)
                detail[rel] = sites
    return counts, detail


def check_delegates(root: str = None) -> list:
    """M6 — every registry entry still delegates to a real manager."""
    root = root or TOOLS
    out: list = []
    sources: dict = {}
    for sub in SCAN_ROOTS:
        for dirpath, dirnames, filenames in os.walk(os.path.join(root, sub)):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fn in sorted(filenames):
                if fn.endswith(".py"):
                    p = os.path.join(dirpath, fn)
                    with open(p, encoding="utf-8", errors="replace") as fh:
                        sources[os.path.relpath(p, root).replace(os.sep, "/")] = fh.read()
    for name in sorted(DELEGATING_MANAGERS):
        found = False
        delegates = False
        for rel, src in sources.items():
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            for n in ast.walk(tree):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
                    found = True
                    for m in ast.walk(n):
                        if isinstance(m, ast.Call) and isinstance(m.func, ast.Attribute) \
                                and m.func.attr in MANAGER_METHODS:
                            delegates = True
        if not found:
            out.append(f"M6 DELEGATING_MANAGERS[{name!r}]: no such helper in the "
                       f"suite — delete the entry, it credits every call site of a "
                       f"function that does not exist")
        elif not delegates:
            out.append(f"M6 DELEGATING_MANAGERS[{name!r}]: the helper no longer "
                       f"calls Dut.saved/injected, so the credit it grants its call "
                       f"sites is stale. Restore the delegation or delete the entry")
    return out


def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_ledger(path: str = None) -> tuple:
    """-> ({module: (cap, 'rel:line')}, [errors]). Same rules as the other three
    ledgers in this repo. AN ABSENT FILE FAILS CLOSED (zero rows -> every nonzero
    module is over cap)."""
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
        if s == RUNTIME_LEDGER_HEADER:
            # TASK-673's per-var table starts here — a DIFFERENT ledger sharing
            # this file. `parse_runtime_ledger()` owns everything from here on.
            break
        if not s.startswith("|"):
            header = None
            continue
        cells = _cells(s)
        if all(_SEP_RE.fullmatch(x) for x in cells if x):
            continue
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if len(cells) < 4:
            continue
        mod = cells[0].strip("`* ")
        cap_s, owner, since = cells[1].strip("`* "), cells[2].strip("`* "), cells[3].strip("`* ")
        if "*" in mod or "?" in mod:
            errors.append(f"M4 {rel}:{i}: module {mod!r} is a wildcard — a ratchet "
                          f"row names one file")
            continue
        try:
            cap = int(cap_s)
        except ValueError:
            errors.append(f"M4 {rel}:{i}: cap {cap_s!r} is not an integer")
            continue
        if not _TASK_RE.match(owner):
            errors.append(f"M4 {rel}:{i}: owner {owner!r} must be a TASK-NNN id")
            continue
        try:
            datetime.date.fromisoformat(since)
        except ValueError:
            errors.append(f"M4 {rel}:{i}: since {since!r} is not an ISO YYYY-MM-DD date")
            continue
        rows[mod] = (cap, f"{rel}:{i}")
    return rows, errors


def evaluate(counts: dict, ledger: dict) -> list:
    out: list = []
    for mod in sorted(counts):
        n = counts[mod]
        if n < 0:
            out.append(f"M1 {mod}: unparseable — the ratchet cannot be measured")
            continue
        cap, where = ledger.get(mod, (0, None))
        if mod.startswith("lib/") and mod in ledger:
            out.append(
                f"M5 {mod}: `lib/` may not hold a ratchet row at all ({where}). The "
                f"restore managers live here; an unrestored write in the shared "
                f"layer reaches every caller at once. Delete the row and the write")
            cap = 0
        if n > cap:
            out.append(
                f"M1 {mod}: {n} unrestored device writes, cap {cap}"
                + (f" ({where})" if where else " (no ledger row)")
                + f". Wrap the mutation in `with dut.saved(<var>, set_to=…)` — or, "
                  f"for a write-only injector, `with dut.injected(<var>, v, "
                  f"clear_to=…)`. A try/finally is not a restore mechanism (R17)")
        elif n < cap:
            out.append(
                f"M2 {where}: {mod} is ledgered at {cap} but holds {n} — lower the "
                f"row to {n}. The ledger is shrink-only, and a cap above the real "
                f"count is headroom to reintroduce the defect")
    for mod, (cap, where) in sorted(ledger.items()):
        if mod not in counts:
            out.append(f"M3 {where}: {mod} is ledgered but no such module exists — "
                       f"delete the row")
    return out


# ── the runtime arm (TASK-673) ──────────────────────────────────────────────

RUNTIME_LEDGER_HEADER = "## Runtime findings (TASK-673)"


def load_transcripts(directory: str = None) -> tuple:
    """-> ({id: Transcript}, [errors]) for every `<id>.json` under `directory`.

    Same loader shape as `check_can_go_red.load_transcripts` /
    `check_gating_offline.load_transcripts` — a transcript is the same object
    to all three gates.
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


def runtime_evidence(tid: str, fn, t) -> list:
    """-> [(var, kind, RestoreLeak)] for one id — the SELF_REARMING_VARS-
    filtered read of `lib.canfail.sweep(...)`'s byproduct. See the module
    docstring for exactly what `kind` means and why `SELF_REARMING_VARS` is
    excluded here rather than in `lib/canfail.py`.
    """
    s = CF.sweep(tid, fn, t)
    out = []
    for leak in s.restore_leaks:
        if leak.var in SELF_REARMING_VARS:
            continue
        out.append((leak.var, leak.kind, leak))
    return out


def runtime_findings(tests: dict, transcripts: dict) -> tuple:
    """-> ({var: [(tid, RestoreLeak)]}, {var: [(tid, RestoreLeak)]}).

    First dict: `NO_RESTORE_ATTEMPTED` evidence, keyed by var — THE finding.
    Second: `RESTORE_ATTEMPTED_UNRECORDED` evidence, keyed by var — printed
    and counted, never a finding (see the module docstring's trap warning).

    An id with no transcript, or whose registry entry is not a function,
    contributes nothing (UNRECORDED is a census line elsewhere, not this).
    """
    leaks: dict = {}
    unrecorded: dict = {}
    for tid, fn in sorted(tests.items()):
        t = transcripts.get(tid)
        if t is None or fn is None:
            continue
        for var, kind, leak in runtime_evidence(tid, fn, t):
            bucket = leaks if kind == "NO_RESTORE_ATTEMPTED" else unrecorded
            bucket.setdefault(var, []).append((tid, leak))
    return leaks, unrecorded


def _cells_rt(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_runtime_ledger(path: str = None) -> tuple:
    """-> ({var: (example_id, where)}, [errors]) from the `RUNTIME_LEDGER_HEADER`
    table in the same ratchet file. A row not under that header is not read —
    it belongs to the per-module ratchet `parse_ledger()` already owns."""
    path = path or os.path.join(ROOT, LEDGER_REL)
    rows: dict = {}
    errors: list = []
    if not os.path.exists(path):
        return rows, errors
    rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().split("\n")
    in_section = False
    header = None
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if s.startswith("## "):
            in_section = (s == RUNTIME_LEDGER_HEADER)
            header = None
            continue
        if not in_section:
            continue
        if not s.startswith("|"):
            header = None
            continue
        cells = _cells_rt(s)
        if all(_SEP_RE.fullmatch(x) for x in cells if x):
            continue
        if header is None:
            header = cells
            continue
        if len(cells) < 4:
            continue
        var = cells[0].strip("`* ")
        example, owner, since = (cells[1].strip("`* "), cells[2].strip("`* "),
                                 cells[3].strip("`* "))
        where = f"{rel}:{i}"
        if "*" in var or "?" in var:
            errors.append(f"{where}: var {var!r} is a wildcard — a runtime "
                          f"finding names one variable")
            continue
        if not _TASK_RE.match(owner):
            errors.append(f"{where}: owner {owner!r} must be a TASK-NNN id")
            continue
        try:
            datetime.date.fromisoformat(since)
        except ValueError:
            errors.append(f"{where}: since {since!r} is not an ISO YYYY-MM-DD date")
            continue
        rows[var] = (example, where)
    return rows, errors


def evaluate_runtime(leaks: dict, ledger: dict) -> tuple:
    """-> ([failures], {var used}) — same shrink-only discipline as `evaluate()`,
    keyed by `var` instead of by module."""
    fails: list = []
    used: set = set()
    for var in sorted(leaks):
        if var in ledger:
            used.add(var)
            continue
        tid, leak = leaks[var][0]
        fails.append(
            f"R17-RT {var}: NO_RESTORE_ATTEMPTED, observed on {tid} "
            f"({leak}) [{len(leaks[var])} occurrence(s) across "
            f"{len({t for t, _l in leaks[var]})} id(s)]. Wrap the mutation in "
            f"`with dut.saved(<var>, set_to=…)`/`dut.injected(...)`, or carry a "
            f"dated ledger row under {RUNTIME_LEDGER_HEADER!r} saying why not")
    for var, (_example, where) in sorted(ledger.items()):
        if var not in used:
            fails.append(f"{where}: {var} -> stale runtime ledger row, the arm no "
                        f"longer finds NO_RESTORE_ATTEMPTED for it — delete the "
                        f"row. The list can only shrink")
    return fails, used


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--print-counts", action="store_true",
                    help="print the per-module rows (how you refresh the ledger)")
    ap.add_argument("--list", metavar="MODULE",
                    help="print every unrestored write site in one module")
    ap.add_argument("--print-runtime-rows", action="store_true",
                    help="print the runtime-arm ledger rows (TASK-673)")
    args = ap.parse_args()

    counts, detail = scan()
    ledger, lerrs = parse_ledger()
    findings = lerrs + check_delegates() + evaluate(counts, ledger)

    # TASK-673: the runtime arm.
    sys.path.insert(0, TOOLS)
    from suite.serialdbg import build_all_tests           # noqa: PLC0415
    tests = build_all_tests()
    transcripts, t_errors = load_transcripts()
    leaks, unrecorded_restore = runtime_findings(tests, transcripts)
    rt_ledger, rt_lerrs = parse_runtime_ledger()
    rt_fails, rt_used = evaluate_runtime(leaks, rt_ledger)
    findings = t_errors + rt_lerrs + rt_fails + findings

    ids_with_transcript = sum(1 for tid in tests if tid in transcripts)

    if args.print_counts:
        for mod in sorted(counts, key=lambda m: -counts[m]):
            if counts[mod]:
                print(f"| `{mod}` | {counts[mod]} | TASK-602 | "
                      f"{datetime.date.today().isoformat()} |")
    if args.list:
        for ln, var in detail.get(args.list, []):
            print(f"{args.list}:{ln}: set {var or '<dynamic>'}")
    if args.print_runtime_rows:
        for var in sorted(leaks):
            tid, leak = leaks[var][0]
            print(f"| `{var}` | `{tid}` ({leak}) | TASK-673 | "
                  f"{datetime.date.today().isoformat()} |")
    if args.verbose:
        total = sum(v for v in counts.values() if v > 0)
        print(f"unrestored device writes: {total} across "
              f"{sum(1 for v in counts.values() if v > 0)} modules; "
              f"{len(ledger)} ledger rows")
        print(f"runtime arm (TASK-673): {ids_with_transcript}/{len(tests)} ids "
              f"recorded; {len(leaks)} var(s) with a NO_RESTORE_ATTEMPTED "
              f"finding ({sum(len(v) for v in leaks.values())} occurrence(s)); "
              f"{len(unrecorded_restore)} var(s) RESTORE_ATTEMPTED_UNRECORDED "
              f"(not a finding); {len(rt_ledger)} runtime ledger rows")
        if unrecorded_restore:
            for var in sorted(unrecorded_restore):
                tid, leak = unrecorded_restore[var][0]
                print(f"  [note] {var}: RESTORE_ATTEMPTED_UNRECORDED, e.g. "
                      f"{tid} ({leak}) — a set-back was attempted but the "
                      f"healthy recording cannot answer for it; not a leak")

    if findings:
        print(f"FAIL: check_restore_manager.py — {len(findings)} finding(s) "
              f"(TASK-602 / R17, incl. TASK-673 runtime arm):")
        for f in findings:
            print(f"  {f}")
        return 1
    print(f"OK: check_restore_manager.py — "
          f"{sum(v for v in counts.values() if v > 0)} unrestored device writes, "
          f"all within the shrink-only ratchet ({len(ledger)} rows). Runtime arm: "
          f"{len(leaks)} var(s) with a finding, all ledgered "
          f"({len(rt_ledger)} rows); {ids_with_transcript}/{len(tests)} ids "
          f"have a recorded transcript.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
