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


def _fast_readiness(fn):
    """Run fn with a tiny phase-0 deadline and tiny shell probes.

    Same idiom, same reason as _fast_phases() below: _FakeSer.readline() returns
    b"" immediately, so every deadline in the boot-not-observed branch is spun
    through at full speed and the only thing the wall clock measures is the
    constants. Before TASK-629 this file spent 2.0 + 3 x 3.0 s per mute _run()
    — 26 s of run/check's 63 s host budget — sleeping through waits it fully
    controlled. The PRODUCTION values are asserted separately in
    production_constant_tests(); shrinking them here must never be able to
    shrink them there.
    """
    orig_phase0 = d._BOOT_PHASE_DEADLINE_S[0]
    orig_probe = d._SHELL_PROBE_DEADLINE_S
    d._BOOT_PHASE_DEADLINE_S[0] = 0.05
    d._SHELL_PROBE_DEADLINE_S = 0.02
    try:
        return fn()
    finally:
        d._BOOT_PHASE_DEADLINE_S[0] = orig_phase0
        d._SHELL_PROBE_DEADLINE_S = orig_probe


def _run(answers_probe, gate):
    """Returns ('ok', None) if it returned, or ('fail', (reason, message))."""
    orig = d._DUT_BOOT_GATE
    d._DUT_BOOT_GATE = gate
    try:
        dut = object.__new__(d.Dut)
        dut.ser = _FakeSer(answers_probe)
        try:
            _fast_readiness(dut._wait_for_ready)
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


# ── TASK-575: the tee forwards attribute ASSIGNMENT, not just reads ──────────

def tee_setattr_tests():
    """_TeeSerial had __getattr__ but no __setattr__, so `dut.ser.timeout = 0.5`
    set a shadow attribute on the wrapper — which then also shadowed the read,
    so the value read back looked correct while pyserial went on using the
    constructor's timeout. The check that matters is on the UNDERLYING object,
    never on the wrapper."""
    raw = _PhaseSer([])
    raw.write_timeout = None
    tee = d._TeeSerial(raw, run_id="7")

    tee.timeout = 0.5
    check("timeout set through the tee reaches pyserial", raw.timeout, 0.5)
    check("timeout read back through the tee is pyserial's", tee.timeout, 0.5)
    check("no shadow copy on the wrapper", "timeout" in tee.__dict__, False)

    # The save/restore idiom the harness uses everywhere (`orig = ser.timeout`
    # … `ser.timeout = orig`) has to round-trip, including nested.
    orig = tee.timeout
    tee.timeout = 1.0
    tee.timeout = orig
    check("save/restore round-trips on pyserial", raw.timeout, 0.5)

    # test_fetch_stress.py arms this one and only this one; before the fix it
    # was never armed at all, so a stalled CH340 write blocked forever.
    tee.write_timeout = 3.0
    check("write_timeout reaches pyserial too", raw.write_timeout, 3.0)

    # An attribute pyserial has never seen still forwards — the wrapper is a
    # proxy, not a filter.
    tee.baudrate = 115200
    check("unknown attribute forwards rather than shadowing", raw.baudrate, 115200)

    # …and the wrapper's OWN state must not be forwarded, or construction
    # itself would write the log handle and the generation counter onto the
    # serial object.
    check("_ser stays on the wrapper", tee.__dict__["_ser"] is raw, True)
    check("ring buffer stays on the wrapper", "_ring" in tee.__dict__, True)
    check("run_id stays on the wrapper", tee.__dict__.get("run_id"), "7")
    check("boot_count stays on the wrapper", "boot_count" in tee.__dict__, True)
    check("run_id was not written to pyserial", hasattr(raw, "run_id"), False)
    check("boot_count was not written to pyserial",
          hasattr(raw, "boot_count"), False)

    # The counter still counts after the assignment path changed.
    tee = d._TeeSerial(_PhaseSer(["[bootphase] 0 reset"]), run_id="7")
    tee.timeout = 0.2
    tee.readline()
    check("generation counter survives the setattr change", tee.gen_tag(), "7.1")


# ── TASK-698: expecting_reboot suppresses the false UNEXPECTED alarm ────────

def _captured(fn):
    """Run fn(), returning what it printed to stdout. No pytest here — this
    file runs as a plain script, so capture is hand-rolled like the rest of
    it (BP-068's stub-the-serial idiom, one level up)."""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn()
    return buf.getvalue()


def expecting_reboot_tests():
    """`_TeeSerial` used to print "UNEXPECTED: the board reset mid-session"
    for EVERY boot after the first, with no awareness that some test ids
    (effect="resetting", e.g. T_PR_04) deliberately reboot the board as part
    of what they assert. The dispatch loop now arms `expecting_reboot` before
    such an id and clears it right after; readline() must honour that flag
    without touching the boot_count INCREMENT, which stays unconditional."""

    # (a) A second boot marked expected must NOT print the alarm.
    tee = d._TeeSerial(_PhaseSer(["[bootphase] 0 first",
                                  "[bootphase] 0 second"]), run_id="3")
    tee.readline()  # boot_count -> 1, never "UNEXPECTED" regardless
    tee.expecting_reboot = True
    out = _captured(tee.readline)  # boot_count -> 2, expected this time
    check("expected reboot -> boot_count still increments", tee.boot_count, 2)
    check("expected reboot -> no UNEXPECTED alarm", "UNEXPECTED" in out, False)
    check("expected reboot -> still logs the observation",
          "[bootphase] 0 observed" in out, True)

    # (b) Regression guard: a second boot NOT marked expected still alarms,
    # exactly as before this change.
    tee = d._TeeSerial(_PhaseSer(["[bootphase] 0 first",
                                  "[bootphase] 0 second"]), run_id="4")
    tee.readline()
    out = _captured(tee.readline)  # expecting_reboot defaults False -> real alarm
    check("unexpected reboot -> boot_count still increments", tee.boot_count, 2)
    check("unexpected reboot -> UNEXPECTED alarm fires", "UNEXPECTED" in out, True)

    # (c) The flag is per-boot, not sticky: clearing it after one
    # resetting-effect test must not leave a later boot silently suppressed.
    tee = d._TeeSerial(_PhaseSer(["[bootphase] 0 a",
                                  "[bootphase] 0 b",
                                  "[bootphase] 0 c"]), run_id="5")
    tee.readline()                       # gen 1, never alarms
    tee.expecting_reboot = True
    tee.readline()                       # gen 2, expected -> quiet
    tee.expecting_reboot = False         # dispatch loop's `finally` clears it
    out = _captured(tee.readline)        # gen 3, NOT armed -> must alarm
    check("flag is per-boot, not sticky", "UNEXPECTED" in out, True)
    check("flag left cleared reads False", tee.expecting_reboot, False)


def production_constant_tests() -> None:
    """The values _fast_readiness() shrinks, asserted at their real sizes.

    NEGATIVE-CONTROL for the speed-up itself (BP-068): _fast_readiness() makes
    the gate blind to the constants it overrides, so if someone "fixes" the 27 s
    by editing dut.py instead of the test, this is what fails. The numbers are
    derived, not decorative — 3.0 s is wait_shell_cooldown_clear's worst-case
    input drop, and one attempt cannot tell a busy shell from a dead one.
    """
    check("phase-0 deadline is the production 2 s", d._BOOT_PHASE_DEADLINE_S[0], 2.0)
    check("shell probe waits the shell's own 3 s cooldown",
          d._SHELL_PROBE_DEADLINE_S, 3.0)
    check("the probe is retried, not one-shot", d._SHELL_PROBE_ATTEMPTS >= 3, True)
    # …and the shrink is scoped: it must be back to production after every use.
    _fast_readiness(lambda: None)
    check("_fast_readiness restores phase-0", d._BOOT_PHASE_DEADLINE_S[0], 2.0)
    check("_fast_readiness restores the probe deadline",
          d._SHELL_PROBE_DEADLINE_S, 3.0)


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
    print("TASK-629 — the production deadlines this file shrinks for speed")
    production_constant_tests()

    print()
    print("TASK-564 — boot-phase gate, generation counter, last-phase stamp")
    phase_tests()

    print()
    print("TASK-575 — _TeeSerial forwards attribute assignment")
    tee_setattr_tests()

    print()
    print("TASK-698 — expecting_reboot suppresses the false UNEXPECTED alarm")
    expecting_reboot_tests()

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
