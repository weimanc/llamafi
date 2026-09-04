#!/usr/bin/env python3
"""
Shared boilerplate for satellite VE test suites (TASK-140).

A new satellite suite needs:
    from ve_suite_base import (
        RESULTS, pass_, fail, skip, flake, unmet,
        make_arg_parser, run_suite, print_results,
    )
    from lib.dut import Dut
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from lib.dut import Dut  # TASK-479: direct import (was run_serialdbg_tests re-export)

# ── result tracking — moved to lib/results.py (TASK-520) ──────────────────────
# These were byte-identical copies of run_serialdbg_tests.py's. Re-exported here
# so every satellite suite keeps its existing import line, exactly like the
# lib/dut.py shim. flake() now consults docs/verification/flaky.yaml.
from lib.dut import resolve_port                              # noqa: E402,F401
# TASK-624: `unmet`, `Verdict` and `verdict_of` are re-exported alongside them.
# A satellite suite whose precondition did not hold must be able to say so —
# `unmet()` — rather than reach for `skip()`, which is green (R28).
from lib.results import (RESULTS, pass_, fail, skip, flake,   # noqa: E402,F401
                         run_with_flake_retry, print_results,
                         unmet, Verdict, verdict_of)


# ── CLI factory ───────────────────────────────────────────────────────────────

def make_arg_parser(
    all_tests: list[str],
    description: str | None = None,
) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--port", default=resolve_port())
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--timeout", type=float, default=3.0,
                   help="default serial read timeout in seconds")
    p.add_argument("--tests", default=",".join(all_tests),
                   help="comma-separated test IDs (default: all)")
    return p


# ── test dispatcher ───────────────────────────────────────────────────────────

def run_suite(
    all_tests: list[str],
    test_fns: dict[str, Callable],
    dut: "Dut",
    selected: list[str],
    inter_test_sleep: float = 0.5,
) -> None:
    for tid in selected:
        def _once(tid=tid):
            try:
                test_fns[tid](dut)
            except TimeoutError as e:
                fail(tid, f"TimeoutError: {e}")
            except Exception as e:
                fail(tid, f"Exception: {e}")
                traceback.print_exc()
        # TASK-520: a declared flake gets exactly one mandated retry here; an
        # undeclared one never reaches this path (flake() already made it a FAIL).
        run_with_flake_retry(tid, _once)
        time.sleep(inter_test_sleep)


# ── results summary — lib/results.print_results (imported above) ──────────────
