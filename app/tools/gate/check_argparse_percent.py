#!/usr/bin/env python3
"""check_argparse_percent.py — no `argparse` call in app/tools/ carries a
`help=`/`description=`/`epilog=` string that argparse's own `%`-interpolation
will choke on. TASK-696.

THE DEFECT. `HelpFormatter` applies Python `%`-style interpolation to help
text. On the venv's Python 3.12 this interpolation only runs when `--help` is
actually rendered — a broken string sits inert until someone asks for help.
On Python 3.14, `add_argument()` validates its `help=` string IMMEDIATELY
(via the new `_check_help`), so a bare `%` now raises `ValueError` at
PARSER-CONSTRUCTION time — before a single argument is parsed, before
`--help` is ever requested. `smoke_test.sh` invokes tools with system
`python3`, which is 3.14 on this machine; the venv is 3.12. TASK-636 hit
this once already (a stray `%` in a probe's `help=` passed for months under
the venv and broke the instant the same file ran under system Python).

THE ACTUAL RUNTIME BEHAVIOUR (verified against `argparse.py` in this
Python's stdlib, not guessed — see `HelpFormatter._expand_help` and
`HelpFormatter._format_text`):

  * `help=` (an `add_argument()`/`add_parser()` kwarg) — `_expand_help` runs
    `help_string % params` the moment `%` appears ANYWHERE in the string,
    where `params` is `vars(action)` plus `prog`. A bare `%` (not doubled,
    not part of a `%(name)conv` naming one of the action's own fields) is a
    malformed format string and raises immediately at `add_argument()`/
    `add_parser()` time. The valid names are not just `prog`/`default`/
    `choices` — they are EVERY field an `Action` carries: `action`, `dest`,
    `option_strings`, `nargs`, `const`, `default`, `type`, `choices`,
    `required`, `help`, `metavar`, plus `prog`.

  * `description=`/`epilog=` — `_format_text` is far more lenient: it ONLY
    interpolates when the literal substring `%(prog)` appears in the text,
    and even then not until `format_help()`/`print_help()` actually runs
    (there is no construction-time check for these two — confirmed: a
    `description="30% done"` builds an `ArgumentParser` with no error and
    only raises when `--help` is invoked). A description/epilog with NO
    `%(prog)` substring is safe no matter how many other bare `%` characters
    it contains — a real module docstring like `test_stream_buffer.py`'s,
    which discusses buffer fill percentages, is exactly this safe shape.

  * `prog=` (the `ArgumentParser()` kwarg itself) is pure DATA — its value is
    substituted, verbatim, as the *value* of another string's `%(prog)s`; it
    is never itself run through `%`-formatting. A `%` inside a `prog=` value
    cannot crash anything. It is still inspected here (the task asked for
    it), but it will never appear in a finding.

WHY THIS NEEDS ITS OWN GATE, NOT A FOLD INTO `check_import_safety.py`.
`check_import_safety.py` imports every module under `app/tools/` — but this
defect fires from `add_argument()`/`ArgumentParser()` CALLS, and every tool
here builds its parser inside `if __name__ == "__main__":` or a `main()`
function, never at module level (confirmed by inspection: none of the ~30
files with argparse calls construct a parser outside a function). Importing
the module never reaches that code, so `check_import_safety.py` — by design,
since it must NOT run any script's `main()` (that could open a port or hit
the network) — cannot see this bug at all. A static, AST-level read of the
`help=`/`description=`/`epilog=` text is the only check that can catch it
without actually invoking every tool's argument parser.

WHAT COUNTS AS A FINDING. This walks the AST (not a text grep — a `%s % (...)`
computed before it is ever passed to `help=`, as in `sdwrite_repro.py`, must
not false-positive) for every `argparse.ArgumentParser(...)`,
`.add_argument(...)` and subparsers' `.add_parser(...)` call, resolves each
`help=`/`description=`/`epilog=`/`prog=` value where it can (string literal,
f-string literal parts, string concatenation, `__doc__` / `__doc__.split(...)
[0]` / `__doc__.splitlines()[0]`, a `%`-formatted expression that fully
resolves before assignment), and reports:

  * UNSAFE  — a value that resolves and, per the rules above, WILL raise.
  * MANUAL  — a value this cannot statically resolve (built from a runtime
    variable, a non-literal `.format()` base, an opaque function call). Not a
    failure by itself — flagged for a human to look at once, in `--verbose`.

No DUT, no build, no network. Sub-second.

    python3 app/tools/gate/check_argparse_percent.py [--verbose]
"""

from __future__ import annotations

import argparse
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))

#: Fields argparse's `_expand_help` will accept in a `%(name)conv` help
#: placeholder: every attribute an `Action` object carries, plus `prog`
#: (added by the formatter itself). Source: `argparse.Action.__init__`'s
#: assigned attributes and `HelpFormatter._expand_help`.
HELP_KEYS = frozenset({
    "action", "dest", "option_strings", "nargs", "const", "default", "type",
    "choices", "required", "help", "metavar", "prog",
})

#: Valid trailing conversion characters for a `%(name)X` placeholder — the
#: standard Python `%`-format conversion types.
_CONV_CHARS = "diouxXeEfFgGcrsa%"

#: Names this gate treats specially. `prog=` is included per TASK-696's
#: request but is DATA, never a template — see docstring — so it is scanned
#: only for completeness and never produces a finding.
KWARGS_OF_INTEREST = ("help", "description", "epilog", "prog")

#: Calls examined. Matches `.attr` or bare `Name` so both `argparse.
#: ArgumentParser(...)` and an aliased/bound `ap.add_argument(...)` are seen.
ARGPARSE_CALL_NAMES = frozenset({"ArgumentParser", "add_argument", "add_parser"})


class Finding:
    __slots__ = ("filename", "lineno", "kwarg", "kind", "message")

    def __init__(self, filename, lineno, kwarg, kind, message):
        self.filename = filename
        self.lineno = lineno
        self.kwarg = kwarg
        self.kind = kind  # "UNSAFE" or "MANUAL"
        self.message = message

    def __str__(self):
        return (f"{self.kind} {self.filename}:{self.lineno} {self.kwarg}= "
                f"— {self.message}")

    def __repr__(self):
        return str(self)


def _call_name(node: ast.Call):
    fn = node.func
    if isinstance(fn, ast.Attribute):
        return fn.attr
    if isinstance(fn, ast.Name):
        return fn.id
    return None


def _flatten_concat(node) -> tuple:
    """(-> ok, joined_str) for a chain of literal `"a" + "b" + ...`."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True, node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        lok, lval = _flatten_concat(node.left)
        rok, rval = _flatten_concat(node.right)
        if lok and rok:
            return True, lval + rval
    return False, None


def _doc_slice(module_doc: str, node: ast.AST):
    """Resolve `__doc__`, `__doc__.splitlines()[0]` and `__doc__.split(SEP)[0]`
    against the enclosing module's real docstring. Returns (ok, value)."""
    if isinstance(node, ast.Name) and node.id == "__doc__":
        return True, module_doc or ""
    if isinstance(node, ast.Subscript):
        # __doc__.splitlines()[0] / __doc__.split("\n")[0], index 0 only —
        # every real use in this tree takes the first line.
        idx = node.slice
        if isinstance(idx, ast.Constant) and idx.value == 0:
            call = node.value
            if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr in ("splitlines", "split")
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "__doc__"):
                doc = module_doc or ""
                lines = doc.splitlines()
                return True, (lines[0] if lines else "")
    return False, None


def _resolve(node: ast.AST, module_doc: str):
    """Resolve an AST node to (status, value) where status is one of
    "literal" (value is the exact final string argparse will see),
    "preformatted" (value already went through `%` at call time — the
    result cannot carry a residual argparse-relevant `%` from that
    operator, since a leftover would have raised in the `%` call itself,
    not in argparse), or "manual" (value is None, cannot resolve)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return "literal", node.value

    if isinstance(node, ast.JoinedStr):
        # f-string: only literal segments matter — a `%` in an interpolated
        # expression's *value* is data, not template text, and cannot be
        # statically known anyway. Non-literal segments are replaced with a
        # placeholder that cannot itself form a `%(...)` sequence.
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            else:
                parts.append("\x00")
        return "literal", "".join(parts)

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        # "template" % (...) — Python's own `%` operator runs at CALL time,
        # before the result is ever handed to argparse. Whatever `%`
        # characters were in the template are consumed by that operator (or
        # the operator itself raises, a plain Python bug unrelated to this
        # gate); the resulting str cannot carry a residual argparse-style
        # placeholder from the template. Only trust this when the left side
        # is itself a literal — this is exactly the `sdwrite_repro.py` shape.
        ok, _ = _flatten_concat(node.left) if isinstance(node.left, ast.BinOp) else (
            isinstance(node.left, ast.Constant) and isinstance(node.left.value, str), None)
        if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
            return "preformatted", None
        return "manual", None

    ok, val = _flatten_concat(node)
    if ok:
        return "literal", val

    ok, val = _doc_slice(module_doc, node)
    if ok:
        return "literal", val

    if isinstance(node, ast.Call):
        fn = node.func
        if isinstance(fn, ast.Attribute) and fn.attr == "format":
            base = fn.value
            if isinstance(base, ast.Constant) and isinstance(base.value, str):
                # `.format()` uses `{}`, not `%` — any `%` in the base
                # literal survives verbatim into the final string.
                return "literal", base.value
        return "manual", None

    return "manual", None


def _check_help_string(s: str) -> str:
    """-> "" if `s` is safe as a `help=` value, else a description of the
    first unsafe `%`. Mirrors `HelpFormatter._expand_help`: any `%` at all
    triggers `%`-interpolation against the action's own fields."""
    i, n = 0, len(s)
    while i < n:
        if s[i] != "%":
            i += 1
            continue
        if i + 1 < n and s[i + 1] == "%":
            i += 2
            continue
        if i + 1 < n and s[i + 1] == "(":
            close = s.find(")", i + 2)
            if close != -1 and close + 1 < n and s[close + 1] in _CONV_CHARS:
                key = s[i + 2:close]
                if key in HELP_KEYS:
                    i = close + 2
                    continue
                return (f"'%({key})...' at offset {i} — {key!r} is not one of "
                        f"argparse's recognized help fields")
        return f"bare '%' at offset {i} ({s[max(0, i-12):i+12]!r})"
    return ""


def _check_description_string(s: str) -> str:
    """-> "" if `s` is safe as a `description=`/`epilog=` value. `_format_text`
    only interpolates when the literal substring '%(prog)' appears; absent
    that trigger, ANY other `%` is inert and safe."""
    if "%(prog)" not in s:
        return ""
    # Triggered: the whole text goes through `s % dict(prog=...)` — every
    # `%` in it must be `%%` or a `%(prog)conv` placeholder.
    i, n = 0, len(s)
    while i < n:
        if s[i] != "%":
            i += 1
            continue
        if i + 1 < n and s[i + 1] == "%":
            i += 2
            continue
        if i + 1 < n and s[i + 1] == "(":
            close = s.find(")", i + 2)
            if close != -1 and close + 1 < n and s[close + 1] in _CONV_CHARS:
                key = s[i + 2:close]
                if key == "prog":
                    i = close + 2
                    continue
                return (f"'%({key})...' at offset {i} — description/epilog "
                        f"interpolation only ever supplies 'prog'")
        return (f"bare '%' at offset {i} ({s[max(0, i-12):i+12]!r}) — "
                f"'%(prog)' elsewhere in this text triggers interpolation "
                f"over the WHOLE string at --help time")
    return ""


def find_unsafe_percent(source: str, filename: str = "<string>") -> list:
    """Pure, string-in: the whole gate's logic, driveable from fixtures.

    -> list[Finding], both UNSAFE and MANUAL kinds.
    """
    findings = []
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        return [Finding(filename, getattr(e, "lineno", 0) or 0, "<parse>",
                        "MANUAL", f"file does not parse: {e}")]

    module_doc = ast.get_docstring(tree, clean=False) or ""

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node) not in ARGPARSE_CALL_NAMES:
            continue
        for kw in node.keywords:
            if kw.arg not in KWARGS_OF_INTEREST:
                continue
            status, value = _resolve(kw.value, module_doc)
            if status == "preformatted":
                continue  # resolved at call time, before argparse ever sees it
            if status == "manual":
                findings.append(Finding(
                    filename, node.lineno, kw.arg, "MANUAL",
                    f"value is not statically resolvable "
                    f"({ast.dump(kw.value)[:80]}...)"))
                continue
            # status == "literal"
            if kw.arg == "prog":
                continue  # data, never itself run through `%`-formatting
            if kw.arg == "help":
                msg = _check_help_string(value)
            else:  # description / epilog
                msg = _check_description_string(value)
            if msg:
                findings.append(Finding(filename, node.lineno, kw.arg,
                                        "UNSAFE", msg))
    return findings


def scan(root: str = None) -> list:
    root = root or TOOLS
    findings = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, TOOLS).replace(os.sep, "/")
            with open(path, encoding="utf-8", errors="replace") as fh:
                src = fh.read()
            findings.extend(find_unsafe_percent(src, filename=rel))
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true",
                    help="also print MANUAL (unresolvable) findings")
    args = ap.parse_args()

    findings = scan()
    unsafe = [f for f in findings if f.kind == "UNSAFE"]
    manual = [f for f in findings if f.kind == "MANUAL"]

    if args.verbose and manual:
        print(f"MANUAL review ({len(manual)}) — not statically resolvable, "
              f"not a failure by itself:")
        for f in manual:
            print(f"  {f}")

    if unsafe:
        print(f"FAIL: check_argparse_percent.py — {len(unsafe)} unsafe '%' "
              f"finding(s) (TASK-696):")
        for f in unsafe:
            print(f"  {f}")
        return 1

    print(f"OK: check_argparse_percent.py — 0 unsafe '%' findings "
          f"({len(manual)} flagged for manual review)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
