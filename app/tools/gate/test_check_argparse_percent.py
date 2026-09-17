#!/usr/bin/env python3
"""test_check_argparse_percent.py — the negative suite for TASK-696's
`check_argparse_percent.py`. BP-068: a gate without a negative test is not a
gate.

Every arm constructs a fixture and asserts the finding KIND ("UNSAFE" /
"MANUAL" / none), not merely a non-empty list — a checker that flagged one
wrong thing about everything would still pass a bare `findings != []` test.

Fixtures are run through BOTH `find_unsafe_percent()` (the pure, string-in
function) and, for the ones claiming to be genuinely safe, the REAL
`argparse` module in this interpreter — so "PASS" here also means "this
interpreter's argparse does not actually raise on it", not just "our checker
agrees with itself". That closes the loop the whole gate exists for: the
checker's verdict and the interpreter's behaviour must agree.

No DUT, no serial port, no network, no build.

    python3 app/tools/gate/test_check_argparse_percent.py
"""

from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import check_argparse_percent as C                                  # noqa: E402

FAILURES: list = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILURES.append(name)


def kinds(findings):
    return sorted({f.kind for f in findings})


# ── fixtures ──────────────────────────────────────────────────────────────

CLEAN_HELP = '''
import argparse
p = argparse.ArgumentParser()
p.add_argument("--x", help="a clean help string with no percent at all")
'''

BARE_PERCENT_HELP = '''
import argparse
p = argparse.ArgumentParser()
p.add_argument("--x", help="30%% is fine but 30% chance is not")
'''

DOUBLED_PERCENT_HELP = '''
import argparse
p = argparse.ArgumentParser()
p.add_argument("--x", help="a literal 100%% here, escaped correctly")
'''

RECOGNIZED_PLACEHOLDER_HELP = '''
import argparse
p = argparse.ArgumentParser()
p.add_argument("--x", type=int, default=5,
               help="uses %(default)s and %(prog)s and %(type)s safely")
'''

UNRECOGNIZED_PLACEHOLDER_HELP = '''
import argparse
p = argparse.ArgumentParser()
p.add_argument("--x", help="uses %(bogus)s which is not an action field")
'''

# The exact shape already in this codebase (sdwrite_repro.py): a %-format
# expression evaluated BEFORE the result is ever passed to help=. The `%s`
# never survives into the AST string literal that becomes the actual help=
# argument, so this must NOT be flagged.
PREFORMATTED_HELP = '''
import argparse
CHUNK_COUNTS = [1, 2, 3]
p = argparse.ArgumentParser()
p.add_argument("--chunks", default="",
               help="comma-separated chunk counts (default: %s)"
                    % ",".join(str(c) for c in CHUNK_COUNTS))
'''

# description/epilog: a bare '%' with NO '%(prog)' trigger anywhere in the
# text is safe, no matter how many bare '%' it has — this is the real shape
# of test_stream_buffer.py's docstring-as-description.
DESCRIPTION_BARE_PERCENT_NO_TRIGGER = '''
"""Buffer stays SAFE if it never drops below 30% in the window."""
import argparse
p = argparse.ArgumentParser(description=__doc__)
'''

# description WITH the '%(prog)' trigger AND an unrelated bare '%' — this
# DOES crash (at --help time), because once triggered the whole text runs
# through `text % dict(prog=...)`.
DESCRIPTION_TRIGGERED_UNSAFE = '''
import argparse
p = argparse.ArgumentParser(description="%(prog)s handles 30% of cases")
'''

# description with the trigger, formatted correctly — safe.
DESCRIPTION_TRIGGERED_SAFE = '''
import argparse
p = argparse.ArgumentParser(description="%(prog)s handles cases correctly")
'''

# __doc__.splitlines()[0] / __doc__.split("\\n")[0] resolve against the real
# module docstring; a bare '%' further down (not on line 0) must not flag.
DOC_FIRST_LINE_SAFE = '''
"""Clean first line.

But 30% mentioned later in the docstring body, off the first line.
"""
import argparse
p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
'''

DOC_FIRST_LINE_UNSAFE = '''
"""30% right on the first line, with the trigger present too: %(prog)s."""
import argparse
p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
'''

# prog= is data, never a template — must never be flagged regardless of %.
PROG_NEVER_FLAGGED = '''
import argparse
p = argparse.ArgumentParser(prog="50% done", description="clean")
'''

# A runtime variable — cannot be statically resolved; must be MANUAL, not
# silently passed and not UNSAFE (we cannot prove either way).
RUNTIME_VARIABLE_MANUAL = '''
import argparse
def make(description):
    return argparse.ArgumentParser(description=description)
'''

# add_parser (subparsers) must be scanned the same as add_argument.
ADD_PARSER_UNSAFE = '''
import argparse
p = argparse.ArgumentParser()
sub = p.add_subparsers()
sub.add_parser("daemon", help="30% chance of this crashing")
'''


def _real_argparse_raises(src: str) -> bool:
    """Execute `src` in a fresh namespace and report whether constructing
    the parser (not rendering --help) raises. This is the ground truth the
    checker's UNSAFE verdicts for `help=` are checked against — `help=` is
    checked at add_argument()/add_parser() time in this interpreter."""
    ns: dict = {}
    try:
        exec(compile(src, "<fixture>", "exec"), ns)
    except Exception:
        return True
    return False


def _real_argparse_help_raises(src: str) -> bool:
    """Like above, but also renders --help — for description/epilog, whose
    interpolation only happens at render time, not construction time."""
    ns: dict = {}
    try:
        exec(compile(src, "<fixture>", "exec"), ns)
        ns["p"].parse_args(["--help"])
    except SystemExit:
        return False  # --help succeeded and exited normally
    except Exception:
        return True
    return False


def test_help_kwarg():
    print("help= fixtures")
    check("clean help string passes",
          kinds(C.find_unsafe_percent(CLEAN_HELP)) == [])
    check("clean help string really does not raise at add_argument time",
          not _real_argparse_raises(CLEAN_HELP))

    f = C.find_unsafe_percent(BARE_PERCENT_HELP)
    check("bare unescaped % is UNSAFE", kinds(f) == ["UNSAFE"], f)
    check("bare unescaped % really does raise at add_argument time",
          _real_argparse_raises(BARE_PERCENT_HELP))

    check("doubled %% (escaped literal) passes",
          kinds(C.find_unsafe_percent(DOUBLED_PERCENT_HELP)) == [])
    check("doubled %% really does not raise",
          not _real_argparse_raises(DOUBLED_PERCENT_HELP))

    check("recognized placeholders (%(default)s, %(prog)s, %(type)s) pass",
          kinds(C.find_unsafe_percent(RECOGNIZED_PLACEHOLDER_HELP)) == [])
    check("recognized placeholders really do not raise",
          not _real_argparse_raises(RECOGNIZED_PLACEHOLDER_HELP))

    f = C.find_unsafe_percent(UNRECOGNIZED_PLACEHOLDER_HELP)
    check("unrecognized %(bogus)s placeholder is UNSAFE", kinds(f) == ["UNSAFE"], f)
    check("unrecognized placeholder really does raise",
          _real_argparse_raises(UNRECOGNIZED_PLACEHOLDER_HELP))

    check("add_parser() help is scanned the same as add_argument()",
          kinds(C.find_unsafe_percent(ADD_PARSER_UNSAFE)) == ["UNSAFE"])
    check("add_parser()'s bad help really does raise",
          _real_argparse_raises(ADD_PARSER_UNSAFE))


def test_preformatted_shape():
    print("the exact sdwrite_repro.py shape")
    f = C.find_unsafe_percent(PREFORMATTED_HELP)
    check("a %-format expression evaluated before help= is NOT flagged",
          kinds(f) == [], f)
    check("...and really does not raise (ground truth)",
          not _real_argparse_raises(PREFORMATTED_HELP))


def test_description_epilog():
    print("description=/epilog= fixtures")
    check("bare % with no %(prog) trigger anywhere is safe",
          kinds(C.find_unsafe_percent(DESCRIPTION_BARE_PERCENT_NO_TRIGGER)) == [])
    check("...and really does not raise, even at --help render time",
          not _real_argparse_help_raises(DESCRIPTION_BARE_PERCENT_NO_TRIGGER))

    f = C.find_unsafe_percent(DESCRIPTION_TRIGGERED_UNSAFE)
    check("%(prog) trigger + unrelated bare % is UNSAFE", kinds(f) == ["UNSAFE"], f)
    check("...and really does raise, but only at --help render time",
          _real_argparse_help_raises(DESCRIPTION_TRIGGERED_UNSAFE))
    check("...construction itself does NOT raise (render-time only)",
          not _real_argparse_raises(DESCRIPTION_TRIGGERED_UNSAFE))

    check("%(prog) trigger used correctly is safe",
          kinds(C.find_unsafe_percent(DESCRIPTION_TRIGGERED_SAFE)) == [])
    check("...and really does not raise",
          not _real_argparse_help_raises(DESCRIPTION_TRIGGERED_SAFE))


def test_doc_slicing():
    print("__doc__ / __doc__.splitlines()[0] resolution")
    check("a bare % off the first line of the docstring is not flagged",
          kinds(C.find_unsafe_percent(DOC_FIRST_LINE_SAFE)) == [])
    check("...and really does not raise",
          not _real_argparse_raises(DOC_FIRST_LINE_SAFE))

    f = C.find_unsafe_percent(DOC_FIRST_LINE_UNSAFE)
    check("a %(prog) trigger + bare % ON the first line is UNSAFE",
          kinds(f) == ["UNSAFE"], f)


def test_prog_kwarg():
    print("prog= fixtures")
    check("prog= is never flagged regardless of %",
          kinds(C.find_unsafe_percent(PROG_NEVER_FLAGGED)) == [])
    check("...and really does not raise",
          not _real_argparse_help_raises(PROG_NEVER_FLAGGED))


def test_manual_review():
    print("unresolvable (MANUAL) fixtures")
    f = C.find_unsafe_percent(RUNTIME_VARIABLE_MANUAL)
    check("a runtime variable is MANUAL, not silently passed and not UNSAFE",
          kinds(f) == ["MANUAL"], f)


def test_live_tree_is_clean():
    print("the real app/tools/ tree")
    findings = C.scan()
    unsafe = [x for x in findings if x.kind == "UNSAFE"]
    check("the live tree has zero UNSAFE findings", unsafe == [], unsafe)


def main():
    print("test_check_argparse_percent.py — TASK-696 negative suite\n")
    test_help_kwarg()
    test_preformatted_shape()
    test_description_epilog()
    test_doc_slicing()
    test_prog_kwarg()
    test_manual_review()
    test_live_tree_is_clean()
    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} arm(s) failed: {', '.join(FAILURES)}")
        return 1
    print("OK: test_check_argparse_percent.py — all arms passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
