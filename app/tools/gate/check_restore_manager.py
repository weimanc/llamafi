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
"""

from __future__ import annotations

import argparse
import ast
import datetime
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))

LEDGER_REL = "docs/verification/unrestored_mutations_ratchet.md"

#: The managers. Nothing else is credited, by design — see the module docstring.
MANAGER_METHODS = frozenset({"saved", "injected"})

#: Suite-level context managers that DELEGATE to a manager above, mapped to the
#: variables they cover. Each entry is verified by M6 against the helper's own
#: source, so it cannot outlive the delegation it claims.
DELEGATING_MANAGERS = {
    "_bgpoll_suspended": frozenset({"bgPoll"}),
}

#: Methods that put a command on the wire.
WIRE_METHODS = frozenset({"cmd", "send", "read_reply"})

#: The manager's OWN implementation, in `lib/dut.py`. These functions write device
#: state because writing it back is what they are; counting them would make the
#: mechanism its own violation. Named exactly, not by prefix, and applied only to
#: `lib/dut.py` — a helper elsewhere called `_restore` gets no credit from this.
MECHANISM_FUNCS = frozenset({"saved", "injected", "_restore", "set_val"})
MECHANISM_MODULE = "lib/dut.py"

#: Variables the FIRMWARE re-arms on its own, so there is no state for a test to
#: leak and nothing a restore could put back. One entry, with its evidence:
#:   `cooldown` — `shell::state().cooldownMs` is an absolute millis() deadline the
#:   shell rewrites on every consumed tap (`app/src/appShell.cpp:272,296,305`).
#:   `set cooldown 0` clears a deadline that the next tap unconditionally re-arms.
#: This is a claim about firmware, so it is checkable and dated, not a taste
#: judgement. Adding an entry requires the same: a line of firmware that rewrites
#: the variable unconditionally, cited.
SELF_REARMING_VARS = frozenset({"cooldown"})

SCAN_ROOTS = ("suite", "lib")

_TASK_RE = re.compile(r"^TASK-\d+$")
_SEP_RE = re.compile(r":?-{2,}:?")
#: `set <var>` — the var is the second whitespace token of the command string.
_SET_RE = re.compile(r"^\s*set\s+([A-Za-z_][A-Za-z0-9_]*)\b")


def _leading_text(node: ast.AST):
    """The literal prefix of a string-ish node, or None.

    An f-string is its own case and it matters: `f"set {v} 1"` names no variable
    statically, while `f"set prRange {n}"` names one perfectly well. Reading only
    the LEADING literal gets the second right and leaves the first unnamed
    (`None`), which is the honest answer — a dynamic var cannot be matched
    against a manager's declared cover set.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        if node.values and isinstance(node.values[0], ast.Constant) \
                and isinstance(node.values[0].value, str):
            return node.values[0].value
    return None


def _mutation_var(node: ast.AST):
    """-> (True, var|None) if this Call writes device state, else (False, None)."""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return (False, None)
    attr = node.func.attr
    if attr == "set_val":
        if node.args:
            v = _leading_text(node.args[0])
            return (True, v if v and v.isidentifier() else None)
        return (True, None)
    if attr in WIRE_METHODS and node.args:
        text = _leading_text(node.args[0])
        if text is None:
            return (False, None)
        m = _SET_RE.match(text)
        if m:
            return (True, m.group(1))
        if text.strip().startswith("set ") or text.strip() == "set":
            return (True, None)          # `set` with a dynamic var name
    return (False, None)


def _covered_vars(with_node: ast.With) -> tuple:
    """-> (named_vars, saw_any_manager) for one `with` statement."""
    named: set = set()
    any_mgr = False
    for item in with_node.items:
        call = item.context_expr
        if not isinstance(call, ast.Call):
            continue
        fn = call.func
        if isinstance(fn, ast.Attribute) and fn.attr in MANAGER_METHODS:
            any_mgr = True
            for a in call.args:
                t = _leading_text(a)
                if t:
                    named.add(t)
        elif isinstance(fn, ast.Name) and fn.id in DELEGATING_MANAGERS:
            any_mgr = True
            named |= set(DELEGATING_MANAGERS[fn.id])
    return (named, any_mgr)


def unrestored_mutations(src: str, mechanism_funcs=frozenset()) -> list:
    """-> [(lineno, var_or_None)] for every device write outside a manager.

    Pure and string-in, so the negative suite drives it with fixtures.
    """
    tree = ast.parse(src)
    hits: dict = {}

    def collect(node, stack):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.With):
                covered, any_mgr = _covered_vars(child)
                # Only the BODY is inside the manager: the `with` items
                # themselves are evaluated before it is armed.
                for item in child.items:
                    collect(item, stack)
                for stmt in child.body:
                    collect(stmt, stack + [(covered, any_mgr)])
                continue
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and child.name in mechanism_funcs:
                continue
            is_mut, var = _mutation_var(child)
            if is_mut and var in SELF_REARMING_VARS:
                is_mut = False
            if is_mut:
                if var is None:
                    ok = any(any_mgr for _c, any_mgr in stack)
                else:
                    ok = any(var in c for c, _a in stack)
                if not ok:
                    hits[(child.lineno, child.col_offset)] = var
            collect(child, stack)

    collect(tree, [])
    return [(ln, var) for (ln, _c), var in sorted(hits.items())]


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--print-counts", action="store_true",
                    help="print the per-module rows (how you refresh the ledger)")
    ap.add_argument("--list", metavar="MODULE",
                    help="print every unrestored write site in one module")
    args = ap.parse_args()

    counts, detail = scan()
    ledger, lerrs = parse_ledger()
    findings = lerrs + check_delegates() + evaluate(counts, ledger)

    if args.print_counts:
        for mod in sorted(counts, key=lambda m: -counts[m]):
            if counts[mod]:
                print(f"| `{mod}` | {counts[mod]} | TASK-602 | "
                      f"{datetime.date.today().isoformat()} |")
    if args.list:
        for ln, var in detail.get(args.list, []):
            print(f"{args.list}:{ln}: set {var or '<dynamic>'}")
    if args.verbose:
        total = sum(v for v in counts.values() if v > 0)
        print(f"unrestored device writes: {total} across "
              f"{sum(1 for v in counts.values() if v > 0)} modules; "
              f"{len(ledger)} ledger rows")

    if findings:
        print(f"FAIL: check_restore_manager.py — {len(findings)} finding(s) "
              f"(TASK-602 / R17):")
        for f in findings:
            print(f"  {f}")
        return 1
    print(f"OK: check_restore_manager.py — "
          f"{sum(v for v in counts.values() if v > 0)} unrestored device writes, "
          f"all within the shrink-only ratchet ({len(ledger)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
