#!/usr/bin/env python3
"""test_check_private_results.py — the A-6 gate's negative suite. TASK-646.

BP-068: a gate that cannot be shown to fail is not a gate. Every arm below
builds a tree the checker MUST reject, or one it MUST accept, and runs the real
`findings()` over it — plus the arms that assert the actual migration landed,
by IDENTITY against `lib.results` rather than by reading the source.

No DUT, no build, no network. Sub-second.

    python3 app/tools/gate/test_check_private_results.py
"""

from __future__ import annotations

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from gate import check_private_results as G                    # noqa: E402
import lib.results as R                                        # noqa: E402
import run_sync_tests as S                                     # noqa: E402

FAILS: list = []
N = [0]


def check(name, got, want):
    N[0] += 1
    if got != want:
        FAILS.append(f"{name}: got {got!r}, want {want!r}")


def scan(source: str, name: str = "probe.py") -> list:
    """Run the real checker over a one-file tree. -> [(rule, lineno)]."""
    d = tempfile.mkdtemp(prefix="privres-")
    os.makedirs(os.path.join(d, "app", "tools"), exist_ok=True)
    with open(os.path.join(d, "app", "tools", name), "w", encoding="utf-8") as fh:
        fh.write(source)
    return sorted((r, ln) for _rel, ln, r, _d in G.findings(root=d))


def main() -> int:
    # ── R1: the recorder names ───────────────────────────────────────────────────

    for _n in G.RECORDER_NAMES:
        check(f"R1 def {_n}",
              [r for r, _ in scan(f"def {_n}(tid, reason=None):\n    pass\n")],
              ["R1"])

    check("R1 an unrelated name is not a finding",
          scan("def record(tid, reason):\n    pass\n"), [])

    check("R1 a NESTED recorder is not a module-level definition and is not "
          "flagged — the gate is about the module's public shape",
          scan("def outer():\n    def pass_(tid):\n        pass\n"), [])

    # ── R2: the fail() arity discriminator ───────────────────────────────────────

    check("R2 fail(tid, reason) is a verdict recorder",
          [r for r, _ in scan("def fail(tid, reason):\n    pass\n")], ["R2"])
    check("R2 fail(msg) is an abort helper and is NOT flagged",
          scan("def fail(msg):\n    raise SystemExit(1)\n"), [])
    check("R2 fail() with no args is not flagged",
          scan("def fail():\n    pass\n"), [])
    check("R2 kwonly args do not count — `fail(msg, *, hint=None)` is still the "
          "one-argument abort helper, not a recorder",
          scan("def fail(msg, *, hint=None):\n    pass\n"), [])
    check("R2 a POSITIONAL-ONLY id still counts",
          scan("def fail(tid, /, reason):\n    pass\n"), [("R2", 1)])

    # ── R3: the store ────────────────────────────────────────────────────────────

    check("R3 a bare RESULTS assignment",
          [r for r, _ in scan("RESULTS = {}\n")], ["R3"])
    check("R3 an annotated RESULTS assignment",
          [r for r, _ in scan("RESULTS: dict = {}\n")], ["R3"])
    check("R3 IMPORTING RESULTS is the fix, and is not a finding",
          scan("from lib.results import RESULTS\n"), [])
    check("R3 a differently-named local store is not a finding",
          scan("_MY_ROWS = {}\n"), [])

    # ── the owner is exempt, and only the owner ──────────────────────────────────

    def _owner_scan(source):
        d = tempfile.mkdtemp(prefix="privres-owner-")
        os.makedirs(os.path.join(d, "app", "tools", "lib"), exist_ok=True)
        with open(os.path.join(d, "app", "tools", "lib", "results.py"), "w") as fh:
            fh.write(source)
        return G.findings(root=d)


    check("the owner may define the layer", _owner_scan("RESULTS = {}\n"
                                                        "def pass_(tid):\n    pass\n"),
          [])

    # ── the ledger refuses an undated or unowned row ─────────────────────────────

    def _ledger(text):
        d = tempfile.mkdtemp(prefix="privres-led-")
        p = os.path.join(d, "led.md")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        return G.parse_ledger(p)


    _HDR = "| file | rule | owner | since | why |\n|---|---|---|---|---|\n"
    rows, errs = _ledger(_HDR + "| `a.py` | R3 | TASK-646 | 2026-09-06 | ok |\n")
    check("ledger: a well-formed row parses", (len(rows), len(errs)), (1, 0))
    rows, errs = _ledger(_HDR + "| `a.py` | R3 | someone | 2026-09-06 | ok |\n")
    check("ledger: an owner that is not a TASK id is refused", (len(rows), len(errs)),
          (0, 1))
    rows, errs = _ledger(_HDR + "| `a.py` | R3 | TASK-646 | soon | ok |\n")
    check("ledger: an undated row is refused", (len(rows), len(errs)), (0, 1))

    # ── the live tree ────────────────────────────────────────────────────────────

    check("the repository itself is at zero unexcepted findings", G.main(), 0)

    # ── TASK-646's own migration, asserted by IDENTITY ───────────────────────────
    #
    # Reading `run_sync_tests.py`'s source for an import line would prove only that
    # a line exists. These arms prove the names the twenty test bodies actually call
    # ARE the shared layer's objects — the one fact that makes their verdicts land
    # in the shared store, obey the flaky policy and reach the artifact.

    for _n in ("RESULTS", "pass_", "fail", "skip", "flake", "unmet", "not_run",
               "print_results", "run_with_flake_retry"):
        check(f"run_sync_tests.{_n} IS lib.results.{_n}",
              getattr(S, _n) is getattr(R, _n), True)

    check("run_sync_tests still registers its twenty ids", len(S.ALL_TESTS), 20)

    print("=== test_check_private_results.py — TASK-646 A-6 gate negative suite ===")
    for f in FAILS:
        print(f"  FAIL: {f}")
    print(f"\n=== {N[0] - len(FAILS)}/{N[0]} checks passed ===")
    return 1 if FAILS else 0


# TASK-609/R48: nothing runs at import. This file used to execute its whole
# body on import, which `check_import_safety.py` reports as a SystemExit out of
# an import — the exact shape that row closed for six other modules.
if __name__ == "__main__":
    sys.exit(main())
