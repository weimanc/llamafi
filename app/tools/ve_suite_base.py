#!/usr/bin/env python3
"""
Shared boilerplate for satellite VE test suites (TASK-140).

A new satellite suite needs:
    from ve_suite_base import (
        RESULTS, pass_, fail, skip, flake,
        make_arg_parser, run_suite, print_results,
    )
    from run_serialdbg_tests import Dut
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from run_serialdbg_tests import Dut

# ── result tracking ───────────────────────────────────────────────────────────

RESULTS: dict[str, str] = {}


def pass_(tid: str, detail: str = ""):
    RESULTS[tid] = "PASS"
    print(f"  [PASS] {tid}" + (f"  {detail}" if detail else ""))


def fail(tid: str, reason: str):
    RESULTS[tid] = f"FAIL: {reason}"
    print(f"  [FAIL] {tid}  {reason}")


def skip(tid: str, reason: str):
    RESULTS[tid] = f"SKIP: {reason}"
    print(f"  [SKIP] {tid}  {reason}")


def flake(tid: str, reason: str):
    RESULTS[tid] = f"FLAKE: {reason}"
    print(f"  [FLAKE] {tid}  {reason}")


# ── CLI factory ───────────────────────────────────────────────────────────────

def make_arg_parser(
    all_tests: list[str],
    description: str | None = None,
) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--port", default="/dev/ttyUSB0")
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
        try:
            test_fns[tid](dut)
        except TimeoutError as e:
            fail(tid, f"TimeoutError: {e}")
        except Exception as e:
            fail(tid, f"Exception: {e}")
            traceback.print_exc()
        time.sleep(inter_test_sleep)


# ── results summary ───────────────────────────────────────────────────────────

def print_results(all_tests: list[str]) -> None:
    print("\n── Results ──────────────────────────────────")
    passed  = sum(1 for v in RESULTS.values() if v == "PASS")
    failed  = sum(1 for v in RESULTS.values() if v.startswith("FAIL"))
    skipped = sum(1 for v in RESULTS.values() if v.startswith("SKIP"))
    flaked  = sum(1 for v in RESULTS.values() if v.startswith("FLAKE"))
    for tid in all_tests:
        if tid in RESULTS:
            print(f"  {tid}: {RESULTS[tid]}")
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped, {flaked} flaked")
    sys.exit(0 if failed == 0 else 1)
