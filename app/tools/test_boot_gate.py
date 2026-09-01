#!/usr/bin/env python3
"""test_boot_gate.py — TASK-560's boot-observation gate in lib/dut.py.

Host-only, no DUT, sub-second. Wired into smoke_test.sh.

Why this exists: `_wait_for_ready()` used to `return` silently when it did not
see a boot banner within 2 s of opening the port. Every readiness gate — the
WiFi wait, TASK-434's bounded extension, the `get ip` fallback, the variant
probe, the first-successful-poll wait — lives after that point, so a missed
banner meant the harness declared itself ready and started issuing commands
with no record that anything had been skipped. Tests then failed on
preconditions that were never established, which is how TASK-553 burned a day.

Serial is stubbed. The bannerless case cannot be produced on real hardware on
demand (opening the port resets the board, and a healthy board then prints the
banner), so a stub is the only way to exercise the branch that matters.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lib.dut as d  # noqa: E402

_failures = []


def check(label, got, want):
    if got != want:
        _failures.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")
    else:
        print(f"  ok   {label}: {got}")


class _FakeSer:
    """Never emits a boot banner. Optionally answers the `get heap` probe."""

    def __init__(self, answers_probe):
        self.timeout = 0.5
        self._answers = answers_probe
        self._queued = []

    def readline(self):
        return self._queued.pop(0) if self._queued else b""

    def write(self, payload):
        if self._answers and payload.strip() == b"get heap":
            self._queued.append(b'{"var":"heap","val":1}\n')

    def flush(self):
        pass

    def reset_input_buffer(self):
        self._queued.clear()


def _run(answers_probe, gate):
    """Returns ('ok', None) if it returned, or ('fail', (reason, message))."""
    orig = d._DUT_BOOT_GATE
    d._DUT_BOOT_GATE = gate
    try:
        dut = object.__new__(d.Dut)
        dut.ser = _FakeSer(answers_probe)
        try:
            dut._wait_for_ready()
            return ("ok", None)
        except d.SetupFailure as e:
            return ("fail", (e.reason, str(e)))
    finally:
        d._DUT_BOOT_GATE = orig


def main() -> int:
    print("test_boot_gate.py — TASK-560 boot-observation gate")

    # A board that never answers: no banner, no probe response.
    outcome, info = _run(False, "fail")
    check("mute board -> aborts", outcome, "fail")
    if outcome == "fail":
        check("mute board -> boot-not-observed", info[0], "boot-not-observed")
        check("mute board -> says shell is mute too", "mute too" in info[1], True)

    # The genuinely silent case this task exists for: the board ANSWERS, so it
    # is running, but this open observed no boot -- it was already in loop() and
    # every readiness gate has been skipped. Must still abort.
    outcome, info = _run(True, "fail")
    check("responsive-but-not-ready -> aborts", outcome, "fail")
    if outcome == "fail":
        check("responsive -> boot-not-observed", info[0], "boot-not-observed")
        check("responsive -> names the skipped gates",
              "SKIPPED" in info[1], True)
        check("responsive -> does NOT claim the board is mute",
              "mute too" in info[1], False)
        check("message offers the escape hatch",
              "DUT_BOOT_GATE=warn" in info[1], True)

    # The escape hatch. Exists so this gate gets turned down rather than
    # reverted wholesale while TASK-557 is unresolved.
    outcome, _ = _run(True, "warn")
    check("gate=warn -> returns instead of aborting", outcome, "ok")
    outcome, _ = _run(False, "warn")
    check("gate=warn -> returns even for a mute board", outcome, "ok")

    print()
    if _failures:
        print(f"FAILED: {len(_failures)} case(s)")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print("PASS: all boot-gate cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
