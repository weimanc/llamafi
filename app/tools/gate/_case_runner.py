"""_case_runner.py — shared CASES-list runner for gate/test_check_*.py suites.

TASK-614/A-16: six of these suites (test_check_app_conformance,
_armed_injectors, _board_currency, _flake_class, _production_symbols,
_test_meta) carried byte-identical `main()` bodies, differing only in the
printed module name. One implementation, N call sites.

Each suite still owns its own CASES list and case functions — this only
runs them and prints the same PASS/FAIL/ERROR/summary lines every one of
them already printed. Not a new pattern: the leading underscore marks it
private to gate/, following the same "leaf helper nothing outside its
directory imports" shape as lib/'s internal modules.
"""
from __future__ import annotations

from typing import Callable, Sequence, Tuple

Case = Tuple[str, Callable[[], None]]


def run_cases(module_name: str, cases: Sequence[Case]) -> int:
    failed = 0
    for name, fn in cases:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
    print(f"{module_name}: {len(cases) - failed}/{len(cases)} passed")
    return 1 if failed else 0
