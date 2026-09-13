"""suite/serialdbg/_restore_scan.py — the pure AST analysis behind "does this
mutation get restored through the manager?" TASK-602 / TASK-592.

MOVED HERE FROM `gate/check_restore_manager.py` (TASK-592). The gate's own
docstring explains WHY the analysis looks only for `with dut.saved(...)` /
`with dut.injected(...)` / a registered delegate, and not for `finally:` — that
reasoning is unchanged and still lives there. What moved is only the pure,
string-in/AST-out function `unrestored_mutations` and the small pieces it is
built from.

WHY IT MOVED. `_order.py`'s 0->1-edge enumeration (§6 R3 / TASK-566) needed the
same analysis for its new unrestored-set shape (finding B-4(b),
docs/verification/reviews/M-TESTQUAL-B-taxonomy-review.md). The project rule is
"extend, don't fork" (feedback_extend_dont_fork_tools.md) and the dependency
rule is downward-only: `gate/` is a LEAF and nothing may import from it, while
`suite/` may import `lib/` and `_order.py` already lives in `suite/serialdbg/`.
So the analysis could not stay in `gate/check_restore_manager.py` and be
reused by `_order.py` — it had to move to a module `gate/` imports FROM, not
the reverse. `check_restore_manager.py` now imports every name below unchanged;
its own file keeps the ledger, the scan-the-tree walk, and the CLI.
"""

from __future__ import annotations

import ast
import re

#: The managers. Nothing else is credited — see check_restore_manager.py's
#: module docstring for the four leak shapes a bare `finally:` match would miss.
MANAGER_METHODS = frozenset({"saved", "injected"})

#: Suite-level context managers that DELEGATE to a manager above, mapped to the
#: variables they cover. Each entry is verified by check_restore_manager.py's
#: M6 against the helper's own source, so it cannot outlive the delegation it
#: claims.
DELEGATING_MANAGERS = {
    "_bgpoll_suspended": frozenset({"bgPoll"}),
}

#: Methods that put a command on the wire.
WIRE_METHODS = frozenset({"cmd", "send", "read_reply"})

#: The manager's OWN implementation, in `lib/dut.py`. These functions write
#: device state because writing it back is what they are; counting them would
#: make the mechanism its own violation. Named exactly, not by prefix, and
#: applied only to `lib/dut.py` by the caller.
MECHANISM_FUNCS = frozenset({"saved", "injected", "_restore", "set_val"})
MECHANISM_MODULE = "lib/dut.py"

#: Variables the FIRMWARE re-arms on its own, so there is no state for a test
#: to leak and nothing a restore could put back. See check_restore_manager.py
#: for the cited evidence — this constant is the checkable claim, not a taste
#: judgement.
SELF_REARMING_VARS = frozenset({"cooldown"})

#: `set <var>` — the var is the second whitespace token of the command string.
_SET_RE = re.compile(r"^\s*set\s+([A-Za-z_][A-Za-z0-9_]*)\b")

#: `set` keys that CLEAR state and set none (TASK-635's `set injclear`, the
#: boundary check's own disarm). Wrapping a clear in a restore manager would
#: re-arm what it just cleared, so a clear is not a mutation to account for.
CLEARING_KEYS = frozenset({"injclear"})


def _leading_text(node: ast.AST):
    """The literal prefix of a string-ish node, or None.

    An f-string is its own case and it matters: `f"set {v} 1"` names no
    variable statically, while `f"set prRange {n}"` names one perfectly well.
    Reading only the LEADING literal gets the second right and leaves the
    first unnamed (`None`), which is the honest answer — a dynamic var cannot
    be matched against a manager's declared cover set.
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
            if m.group(1) in CLEARING_KEYS:
                return (False, None)
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

    Pure and string-in, so both callers' negative suites can drive it with
    fixtures without a Dut or a port.
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
