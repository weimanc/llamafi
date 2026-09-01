#!/usr/bin/env python3
"""test_boot_gate.py — the boot gates in lib/dut.py (TASK-560, TASK-564).

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

TASK-564 extends the same stub-the-serial pattern (BP-068) to the boot-PHASE
gate: `_wait_for_ready()` now waits for `[bootphase] 6 ready` with a per-phase
deadline, every SetupFailure from the readiness path is stamped with
`last-phase=`/`gen=`, and `_TeeSerial` counts observed `[bootphase] 0` lines. A
board that stalls at phase 3 is even less producible on demand than a bannerless
one — it needs a WiFi cascade that never returns — so these are stubbed too.
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




# ── TASK-564: the boot-phase gate, the generation counter, the stamp ──────────

class _PhaseSer:
    """Emits a scripted line sequence, then goes quiet.

    Quiet means readline() returns b"" immediately rather than blocking, so the
    deadline loops spin — which is why every phase test below shrinks
    _BOOT_PHASE_DEADLINE_S first. The mechanism is what is under test; the
    numbers get their own check (`phase-4 budget clears the firmware bound`)."""

    def __init__(self, lines):
        self.timeout = 0.5
        self._queued = [l.encode() + b"\n" for l in lines]

    def readline(self):
        return self._queued.pop(0) if self._queued else b""

    def write(self, payload):
        pass

    def flush(self):
        pass

    def reset_input_buffer(self):
        self._queued.clear()


def _phase_dut(lines, run_id="9"):
    """A Dut whose serial is a _TeeSerial (so the gen counter is live) over a
    scripted phase stream."""
    dut = object.__new__(d.Dut)
    dut.ser = d._TeeSerial(_PhaseSer(lines), run_id=run_id)
    dut._last_phase = None
    return dut


def _fast_phases(fn):
    """Run fn with tiny per-phase deadlines. Restores them afterwards."""
    orig = dict(d._BOOT_PHASE_DEADLINE_S)
    orig_grace = d._BOOT_PHASE_GRACE_S
    d._BOOT_PHASE_DEADLINE_S.update({k: 0.3 for k in orig})
    d._BOOT_PHASE_GRACE_S = 0.3
    try:
        return fn()
    finally:
        d._BOOT_PHASE_DEADLINE_S.clear()
        d._BOOT_PHASE_DEADLINE_S.update(orig)
        d._BOOT_PHASE_GRACE_S = orig_grace


_FULL_BOOT = [f"[bootphase] {n} {name}" for n, name in d._BOOT_PHASE_NAMES.items()]


def phase_tests():
    # The bounds are derived, not decorative. Phase 3's cascade is bounded by
    # firmware constants at 10 000 (NVS) + 300 (settle) + 5 x 10 000 (candidate
    # probes) + 15 000 (re-assoc settle) = 75.3 s, so phase 4's budget must
    # clear it or a merely-slow WiFi boot becomes a false setup failure. This is
    # the one check that fails if someone "tidies" the constant.
    check("phase-4 budget clears the firmware cascade bound (75.3 s)",
          d._BOOT_PHASE_DEADLINE_S[4] >= 75.3, True)
    check("phase names match the firmware call sites",
          [d._BOOT_PHASE_NAMES[n] for n in range(7)],
          ["reset", "fs", "display", "wifi", "time", "services", "ready"])

    # A clean boot: the gate reaches 6 and the generation is minted from the
    # single observed `[bootphase] 0`.
    dut = _phase_dut(_FULL_BOOT)
    ip = _fast_phases(lambda: dut._wait_for_bootphase_6())
    check("clean boot -> reaches phase 6", dut.last_phase(), "6 ready")
    check("clean boot -> no IP line seen", ip, False)
    check("clean boot -> gen is <run-id>.1", dut.gen_tag(), "9.1")

    # setup()'s own IP line lands inside the phase window. If the gate ate it
    # silently the caller would sit out the full 25+75 s WiFi wait on a board
    # that had already said the link was up.
    dut = _phase_dut(_FULL_BOOT[:4] + ["IP address: 192.168.1.5"] + _FULL_BOOT[4:])
    ip = _fast_phases(lambda: dut._wait_for_bootphase_6())
    check("IP line inside the phase window is reported", ip, True)

    # Stalled mid-boot. The whole point of the per-phase deadline: say WHICH
    # stage, not "the DUT was not ready".
    dut = _phase_dut(_FULL_BOOT[:4])
    try:
        _fast_phases(lambda: dut._wait_for_bootphase_6())
        check("stall at phase 3 -> aborts", "ok", "fail")
    except d.SetupFailure as e:
        check("stall at phase 3 -> boot-phase-timeout", e.reason, "boot-phase-timeout")
        check("stall at phase 3 -> names the stage", "[bootphase] 3 wifi" in str(e), True)
        check("stall at phase 3 -> names the phase not reached",
              "no phase 4 (time)" in str(e), True)
        check("stall -> offers the escape hatch", "DUT_BOOT_GATE=warn" in str(e), True)
    check("stall -> last_phase is the last one SEEN", dut.last_phase(), "3 wifi")

    # Same escape hatch as the boot-observation gate, for the same reason: this
    # lands while TASK-557 is open.
    orig = d._DUT_BOOT_GATE
    d._DUT_BOOT_GATE = "warn"
    try:
        dut = _phase_dut(_FULL_BOOT[:4])
        _fast_phases(lambda: dut._wait_for_bootphase_6())
        check("gate=warn -> phase stall returns instead of aborting", True, True)
    except d.SetupFailure:
        check("gate=warn -> phase stall returns instead of aborting", False, True)
    finally:
        d._DUT_BOOT_GATE = orig

    # A board that resets while we watch it boot. Today that is an invisible
    # confound; the counter has to make it an event.
    dut = _phase_dut(_FULL_BOOT[:3] + _FULL_BOOT)
    _fast_phases(lambda: dut._wait_for_bootphase_6())
    check("mid-boot reset -> generation increments", dut.gen_tag(), "9.2")
    check("mid-boot reset -> still reaches phase 6", dut.last_phase(), "6 ready")

    # Pre-TASK-561 firmware says nothing. That must degrade to the legacy gates,
    # not to an unreadable phase timeout — _verify_debug_firmware()'s verdict is
    # the legible one for a wrong binary.
    dut = _phase_dut(["[boot] git=n/a elf=deadbeef", "Initialisation done."])
    _fast_phases(lambda: dut._wait_for_bootphase_6())
    check("no phase stream -> falls back instead of failing", dut.last_phase(), None)

    # gen=? is a real answer, not a placeholder: under DUT_BOOT_GATE=warn there
    # may genuinely have been no observed boot, and a `?` compares to nothing.
    dut = _phase_dut([])
    check("no boot observed -> gen=?", dut.gen_tag(), "?")

    # Every SetupFailure out of the readiness path says which phase it died in.
    dut = _phase_dut(_FULL_BOOT[:2])
    try:
        _fast_phases(lambda: dut._wait_for_bootphase_6())
        check("stamp -> raised", False, True)
    except d.SetupFailure as e:
        check("unstamped failure does not invent a last-phase",
              "last-phase=" in str(e), False)
        e.stamp(dut.last_phase(), dut.gen_tag())
        check("stamped failure carries last-phase", "last-phase=1 fs" in str(e), True)
        check("stamped failure carries the generation", "gen=9.1" in str(e), True)

    # The run id has to differ between sessions on the same port, or the
    # cross-session comparison in design 16.1 prints gen=1 on both sides.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        f = pathlib.Path(td) / "runid"
        orig_f = d._run_id_file
        d._run_id_file = lambda port: f
        try:
            a = d._next_run_id("/dev/null")
            b = d._next_run_id("/dev/null")
        finally:
            d._run_id_file = orig_f
    check("run id is monotonic across sessions", (a, b), ("1", "2"))


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
    print("TASK-564 — boot-phase gate, generation counter, last-phase stamp")
    phase_tests()

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
