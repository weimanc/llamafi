#!/usr/bin/env python3
"""
audit_origin.py — origin-relative render + hit-test audit (TASK-082).

Usage:
    python3 tools/audit_origin.py             # T141–T146 (full run)
    python3 tools/audit_origin.py --grep-only # T141 only (static grep)
    python3 tools/audit_origin.py --visual    # T141–T146 + gen/origin_audit.png

Exit 0 = all requested checks pass.
"""

import sys
import re
import argparse
from pathlib import Path

TOOLS_DIR = Path(__file__).parent          # app/tools/
APP_DIR   = TOOLS_DIR.parent              # app/
WINAMP_H  = APP_DIR / "src" / "winamp" / "winampDisplay.h"

# ── T141 — Static grep ────────────────────────────────────────────────────────
#
# Scan winampDisplay.h for tft draw/fill/pushImage calls.
# Extract the X-coordinate argument and verify it is origin-relative
# (a variable, not a bare integer literal), except the explicit gutter-fill
# pattern fillRect(0, ...) which is an accepted origin-independent clear.

# tft methods where the first positional argument is X
FIRST_ARG_IS_X = re.compile(
    r'\btft\.(fillRect|pushImage|drawPixel|drawLine|drawRect|fillRoundRect|drawRoundRect'
    r'|drawBitmap|pushSprite)\s*\('
)

# tft methods where the second positional argument is X (e.g. drawString)
SECOND_ARG_IS_X = re.compile(
    r'\btft\.(drawString|drawFloat|drawNumber|drawChar|drawCentreString|drawRightString)\s*\('
)

# tft methods that have no X (fillScreen, setTextColor, etc.) — skip
SKIP_METHODS = re.compile(
    r'\btft\.(fillScreen|setTextColor|setTextFont|setTextSize|setSwapBytes'
    r'|getSwapBytes|setCursor|setRotation|begin|init|setTouch)\s*\('
)

# Accepted non-integer X expressions:
# - Any identifier (variable name) — always accepted
# - Simple arithmetic: identifier + constant, identifier - constant, etc.
BARE_INT = re.compile(r'^\s*(-?\d+)\s*$')

# The explicit gutter-fill 0 is accepted: fillRect(0, ...)
ACCEPTED_ZERO_CONTEXT = {'fillRect'}

PASS = 0
FAIL = 1


def t141_grep(verbose=False):
    """T141: static X-arg audit of winampDisplay.h. Returns list of failure strings."""
    if not WINAMP_H.exists():
        return [f"ERROR: {WINAMP_H} not found"]

    failures = []
    src = WINAMP_H.read_text(encoding="utf-8")
    lines = src.splitlines()

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()

        # Skip comments
        if stripped.startswith("//") or stripped.startswith("*"):
            continue

        # Identify call type
        m1 = FIRST_ARG_IS_X.search(line)
        m2 = SECOND_ARG_IS_X.search(line)
        skip = SKIP_METHODS.search(line)

        if skip and not m1 and not m2:
            continue

        if not m1 and not m2:
            continue

        # Extract argument list (up to first unmatched closing paren)
        paren_start = line.find('(', (m1 or m2).end() - 1)
        if paren_start < 0:
            continue

        # Collect args from this line (may be multi-line, but most are single-line)
        args_str = line[paren_start + 1:]
        # For multi-line calls, join next lines until parens balance
        depth = 1
        for next_line in lines[lineno:]:  # lineno is 1-based, so lines[lineno] is the next
            if depth <= 0:
                break
            for ch in next_line:
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
            if depth > 0:
                args_str += " " + next_line.strip()
            else:
                break

        # Tokenise args by comma (naive — doesn't handle nested parens in args,
        # but tft calls don't have them).
        args = _split_args(args_str)
        if not args:
            continue

        method = (m1 or m2).group(1)

        if m1:
            x_arg = args[0]
        else:  # second arg is X
            if len(args) < 2:
                continue
            x_arg = args[1]

        x_arg = x_arg.strip()

        # Accept: any expression containing a non-digit identifier character
        # (i.e. a variable is present).
        if re.search(r'[A-Za-z_]', x_arg):
            if verbose:
                print(f"  ok  {WINAMP_H.name}:{lineno}: {method}(x={x_arg!r} ...)")
            continue

        # It's a numeric expression. Accept 0 in fillRect context.
        m_int = BARE_INT.match(x_arg)
        if m_int:
            val = int(m_int.group(1))
            if val == 0 and method in ACCEPTED_ZERO_CONTEXT:
                if verbose:
                    print(f"  ok  {WINAMP_H.name}:{lineno}: {method}(x=0 [gutter-fill]) ...")
                continue
            failures.append(
                f"{WINAMP_H.name}:{lineno}: bare X literal {val!r} in tft.{method}() — "
                f"must be origin-relative (use originX + offset)"
            )
        else:
            # Non-trivial numeric expression without identifiers — unlikely, flag it
            failures.append(
                f"{WINAMP_H.name}:{lineno}: suspicious X arg {x_arg!r} in tft.{method}()"
            )

    return failures


def _split_args(s):
    """Split a comma-separated argument string, respecting paren depth."""
    args = []
    depth = 0
    current = []
    for ch in s:
        if ch == '(' :
            depth += 1
            current.append(ch)
        elif ch == ')':
            if depth == 0:
                break
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            args.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        args.append(''.join(current).strip())
    return args


# ── T142–T146 stubs ───────────────────────────────────────────────────────────
# Full implementation in TASK-082. These stubs print a notice and exit non-zero
# so the check_build.sh gate knows T142–T146 are pending.

def t142_t146_stub():
    print("T142–T146: zone boundary + full regression tests (TASK-082 pending)")
    print("  Run --grep-only to execute only T141.")
    return ["T142–T146 not yet implemented (TASK-082)"]


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Origin-relative render audit")
    parser.add_argument("--grep-only", action="store_true",
                        help="T141 only: static grep for bare X literals")
    parser.add_argument("--visual", action="store_true",
                        help="Generate gen/origin_audit.png (requires T142–T146)")
    parser.add_argument("--verbose", action="store_true",
                        help="Print accepted lines too")
    args = parser.parse_args()

    all_failures = []

    print("=== audit_origin.py ===")
    print()

    print("[T141] Static grep — bare X literals in winampDisplay.h")
    failures_141 = t141_grep(verbose=args.verbose)
    if failures_141:
        for f in failures_141:
            print(f"  FAIL  {f}")
        all_failures.extend(failures_141)
    else:
        print("  PASS  no bare X integer literals")
    print()

    if not args.grep_only:
        failures_rest = t142_t146_stub()
        all_failures.extend(failures_rest)

    if args.visual and not args.grep_only:
        print("--visual requires T142–T146 (TASK-082 pending)")
        all_failures.append("--visual not yet implemented")

    passed = len(all_failures) == 0
    print(f"=== Results: {'PASS' if passed else 'FAIL'} ({len(all_failures)} failures) ===")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
