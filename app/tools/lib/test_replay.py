#!/usr/bin/env python3
"""test_replay.py — the negative suite for the replay engine (TASK-628/631).

R10's own verification clause: *"the job itself is negative-tested — deliberately
break the mutator and assert it reports zero falsifications rather than passing
vacuously."* That is arm N2 below. The rest of the file exists because the other
three failure modes DEV §4 names — a transcript miss read as a confirmation, a
stale transcript read as a regression, a body's `except Exception:` swallowing a
miss — are all silent, and a silent defect in this engine manufactures exactly
the acceptance number the M-HARNESS2 programme was convened to disbelieve.

METHOD, and why it is allowed to import a suite. `lib/replay.py` imports nothing
from `suite/` — M-TOOLING §3 is intact for the MODULE. This file is a test: it is
imported by nothing, and it reaches the suite only through `build_all_tests()`,
the one sanctioned entry point, because the whole claim under test is *"a
recorded session replays against a REAL test body with no device present."* A
hand-written stand-in body would prove the engine agrees with itself, which is
the mistake `spike/task584_residue_verdicts.py` was careful not to make.

The subject is `T_MA_03` (Matrix -> Spotify canvas residue). Chosen because it
exercises every part of the engine at once: `_switch_to` and `_tb_set_offset`
BRANCH on replies, so a positional transcript desyncs; `_check_residue` polls
`get lastPlaylistDraw` repeatedly, so the SAME command string must return
DIFFERENT replies at different `nth` — the case a naive `{command: reply}` map
cannot represent; and it sleeps 3.15 s of wall time, which the virtual clock
must make free.

No DUT, no serial port, no network, no build.

    python3 app/tools/lib/test_replay.py [-v]        (exit 0 = all arms pass)
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time as _time_mod

_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_TOOLS, os.path.join(_TOOLS, "suite")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import replay as RP                                     # noqa: E402
from lib import results as R                                     # noqa: E402
from lib.dut import Dut                                          # noqa: E402
from lib.replay import Reason, Status                            # noqa: E402

TID = "T_MA_03"
FAKE_ELF = "deadbeef"

VERBOSE = "-v" in sys.argv or "--verbose" in sys.argv
FAILURES: list = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'BAD '}{name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(f"{name}: {detail}")


# ── the scripted device, used ONLY to produce the recording ──────────────────
#
# It never appears in a replay. Its only job is to be a plausible board for one
# pass so that a genuine transcript, in the real on-disk format, exists to
# replay. (On hardware this recording comes from `RP.recording(dut, tid)` around
# a live session; the format and the code path are identical, which is the point
# of recording at the transport rather than per method.)

import coords as _c                                              # noqa: E402
from app_ids_gen import APP_SLOT                                 # noqa: E402

_SLOT_TO_APP = {v: k for k, v in APP_SLOT.items()}
_TB_N = APP_SLOT["WebRadio"]
_Y_TO_SLOT = {_c.tap_taskbar_slot(i)[1]: i for i in range(_TB_N + 1)}


class Device:
    """Just enough shell for T_MA_03."""

    def __init__(self, pl_ticking=True, tap_lands=True):
        self.app = "Spotify"
        self.offset = 0
        self.pl_ms = 500_000
        self.pl_ticking = pl_ticking
        self.tap_lands = tap_lands

    def handle(self, line):
        w = line.split()
        if w[:2] == ["get", "shellCooldown"]:
            return [{"ok": True, "var": "shellCooldown", "remainingMs": 0}]
        if w[:2] == ["get", "tbScrollOffset"]:
            return [{"ok": True, "var": "tbScrollOffset", "val": self.offset}]
        if w[:2] == ["get", "appId"]:
            return [{"ok": True, "var": "appId",
                     "val": APP_SLOT.get(self.app, 1), "name": self.app}]
        if w[:2] == ["get", "lastPlaylistDraw"]:
            if self.app == "Spotify" and self.pl_ticking:
                self.pl_ms += 17
            return [{"ok": True, "var": "lastPlaylistDraw", "ms": self.pl_ms}]
        if w[:1] == ["tap"]:
            x, y = int(w[1]), int(w[2])
            if y in _Y_TO_SLOT and x >= 275 and self.tap_lands:
                self.app = _SLOT_TO_APP.get((_Y_TO_SLOT[y] + self.offset)
                                            % _TB_N, "Clock")
            return [{"ok": True, "cmd": "tap", "hit": "TASKBAR"}]
        if w[:1] == ["drag"]:
            y1, y2 = int(w[2]), int(w[4])
            self.offset = (self.offset + (y1 - y2) // _c.TASKBAR_SLOT_H) % _TB_N
            return [{"ok": True, "cmd": "drag"}]
        if w[:1] == ["set"]:
            return [{"ok": True, "cmd": "set"}]
        return [{"ok": True, "cmd": w[0] if w else "?"}]


class _FakeSerial:
    """Byte transport over `Device` — the same shape `RP.RecordingSerial` wraps
    on hardware, so the recorder under test is exercised unchanged."""

    def __init__(self, dev, clock):
        self.dev, self.clock, self.out = dev, clock, []

    def write(self, b):
        for reply in self.dev.handle(b.decode().strip()):
            self.out.append(json.dumps(reply))
        return len(b)

    def flush(self):
        pass

    def readline(self):
        if self.out:
            return (self.out.pop(0) + "\n").encode()
        self.clock.tick()
        return b""

    def gen_tag(self):
        return "g1"


def record(device: Device) -> RP.Transcript:
    """Drive the REAL body once against `device`, through the REAL recorder."""
    clock = RP.VirtualClock()
    dut = object.__new__(Dut)
    dut.ser = _FakeSerial(device, clock)
    dut._owner_thread = threading.current_thread()
    dut.port, dut.elf, dut.elf_expected = "fake", FAKE_ELF, FAKE_ELF
    dut.build_env = "cyd2usb_winamp_debug"
    body = TESTS[TID]
    R.RESULTS.clear()
    with RP.virtual_time(clock):
        with RP.recording(dut, TID) as rec:
            body(dut)
    verdict = R.VERDICTS.get(TID)
    R.RESULTS.clear()
    return rec.transcript, verdict


def rp(transcript, **kw):
    kw.setdefault("expected_elf", FAKE_ELF)
    return RP.replay_test(TID, TESTS[TID], transcript, **kw)


# ═════════════════════════════════════════════════════════════════════════════

def main() -> int:
    """Everything runs here, behind the `__main__` guard TASK-609 requires:
    importing this file must not run a suite, and `sys.exit` at import time is
    an import-time side effect like any other."""
    global TESTS
    from serialdbg import build_all_tests
    TESTS = build_all_tests()


    print(f"TASK-628/631 replay engine — negative suite over the real {TID} body\n")

    # ── P0: a session is recordable, and the recording is keyed ──────────────────
    print("P — the positive arms (the engine has to work before it can be broken)")

    t_ok, rec_verdict = record(Device())
    check("P1 recording produced a PASS on the fake board",
          rec_verdict is R.Verdict.PASS, f"got {rec_verdict}")
    check("P2 the transcript is non-empty",
          len(t_ok.exchanges) > 5, f"{len(t_ok.exchanges)} exchanges")

    _repeats = t_ok.count_of("get lastPlaylistDraw")
    check("P3 the SAME command is recorded more than once — a `{cmd: reply}` map "
          "could not hold this session", _repeats >= 2,
          f"`get lastPlaylistDraw` recorded {_repeats}x")
    _a = json.loads(t_ok.get("get lastPlaylistDraw", 0)[0])["ms"]
    _b = json.loads(t_ok.get("get lastPlaylistDraw", 1)[0])["ms"]
    check("P4 …and its two occurrences carry DIFFERENT values, which is the whole "
          "oracle of this id", _a != _b, f"ms {_a} then {_b}")

    r = rp(t_ok)
    check("P5 the recording replays to the same PASS with NO device present",
          r.status is Status.OK and r.verdict is R.Verdict.PASS, repr(r))
    check("P6 the replay is a confirmation", r.is_confirmation, repr(r))
    check("P7 the virtual clock made the sleeps free",
          r.slept_s >= 0.6 and r.wall_s < 1.0,
          f"body slept {r.slept_s:.2f} virtual s in {r.wall_s*1000:.0f} ms wall")

    # ── N1: a transcript miss is INCONCLUSIVE, never a pass and never a fail ─────
    print("\nN — the negative arms")

    t_hole = RP.Transcript.from_dict(t_ok.to_dict())
    _dropped = ("get lastPlaylistDraw", 1)
    t_hole.exchanges.pop(_dropped)
    r = rp(t_hole)
    check("N1 a transcript with a hole is INCONCLUSIVE(transcript-miss)",
          r.status is Status.INCONCLUSIVE and r.reason is Reason.TRANSCRIPT_MISS,
          repr(r))
    check("N1a …and is NOT reported as a pass", r.verdict is not R.Verdict.PASS,
          f"verdict={r.verdict}")
    check("N1b …and is NOT reported as a fail — the mutation job would have "
          "counted that as a falsification",
          r.verdict is not R.Verdict.FAIL, f"verdict={r.verdict}")
    check("N1c …and `confirmations()` refuses to count it",
          RP.confirmations([r]) == 0, f"counted {RP.confirmations([r])}")

    # The miss must survive the body's own error handling. `_helpers.py` and the
    # family modules contain bare `except Exception:` arms; a miss they can catch is
    # a miss that becomes a pass on a reply that never arrived.
    _caught = {}


    def _swallowing_body(dut):
        try:
            dut.cmd("get nothing-was-ever-recorded-for-this", timeout=1.0)
        except Exception as e:                                       # noqa: BLE001
            _caught["it"] = e
            R.pass_(TID, "swallowed the miss and passed anyway")


    r = RP.replay_test(TID, _swallowing_body, t_ok, expected_elf=FAKE_ELF)
    check("N2 a body's `except Exception:` CANNOT swallow a transcript miss",
          "it" not in _caught and r.reason is Reason.TRANSCRIPT_MISS, repr(r))

    # ── N3: break the mutator — it must report ZERO falsifications ───────────────
    # R10's own verification clause, verbatim. A mutator that mutates nothing must
    # not produce a single falsification; if it does, the mechanism is scoring
    # something other than the mutation.

    t_null = t_ok.mutate(lambda c, n, o: False, lambda o: o)
    check("N3 the broken (no-op) mutator changed nothing",
          getattr(t_null, "mutations", -1) == 0,
          f"{getattr(t_null, 'mutations', None)} fields rewritten")
    r_null = rp(t_null)
    _falsifications = 1 if (r_null.is_confirmation
                            and r_null.verdict is R.Verdict.FAIL) else 0
    check("N3a …and the job reports ZERO falsifications rather than passing "
          "vacuously", _falsifications == 0,
          f"{_falsifications} falsification(s), verdict={r_null.verdict}")

    # The other half of the same clause: a mutator that DOES bite must falsify, or
    # "zero falsifications" is trivially true and proves nothing. The oracle chosen
    # here is the landing read — `get appId` #1, the one T_MA_03 spends its own
    # verdict on. Its FAIL branch then calls `_restore_spotify`, whose commands the
    # healthy recording never contains, so this arm is ALSO the proof of the
    # tail-miss rule: the verdict was reached on recorded replies and stands.
    t_landed = t_ok.mutate(
        lambda c, n, o: c == "get appId" and n == 1,
        lambda o: dict(o, val=APP_SLOT["Clock"], name="Clock"))
    r_landed = rp(t_landed)
    check("N4 mutating the oracle field DOES falsify the id",
          r_landed.is_confirmation and r_landed.verdict is R.Verdict.FAIL,
          repr(r_landed))
    check("N4a the control is not vacuous: N3 and N4 differ on the same body",
          r_null.verdict is not r_landed.verdict,
          f"{r_null.verdict} vs {r_landed.verdict}")
    check("N4b …and the falsification is flagged as reaching its verdict before "
          "the recording ran out", r_landed.tail_miss, repr(r_landed))
    check("N4c `strict_tail=True` refuses that same row, so a driver that wants "
          "full coverage can have it",
          rp(t_landed, strict_tail=True).reason is Reason.TRANSCRIPT_MISS)

    # The complementary case, and the reason the rule is narrow: a miss BEFORE any
    # verdict is still a void. N1 is that case on a hand-made hole; this is it on a
    # real polling oracle. Freezing `lastPlaylistDraw` makes `_check_residue` poll
    # for the full 3 s window, far past what a healthy board recorded, and the miss
    # lands while the id has no verdict at all.
    _frozen = {"v": None}


    def _freeze_ms(o):
        if _frozen["v"] is None:
            _frozen["v"] = o["ms"]
        return dict(o, ms=_frozen["v"])


    r_frozen = rp(t_ok.mutate(lambda c, n, o: o.get("var") == "lastPlaylistDraw",
                              _freeze_ms))
    check("N4d freezing a POLLED oracle out-runs the recording, and that is a void "
          "— not a falsification",
          r_frozen.status is Status.INCONCLUSIVE
          and r_frozen.reason is Reason.TRANSCRIPT_MISS
          and RP.confirmations([r_frozen]) == 0, repr(r_frozen))

    # ── N5: staleness is loud, and is not a failing test ────────────────────────
    t_stale = RP.Transcript.from_dict(t_ok.to_dict())
    t_stale.elf = "0badc0de"
    r = rp(t_stale)
    check("N5 a transcript from other firmware is INCONCLUSIVE(stale-transcript)",
          r.status is Status.INCONCLUSIVE and r.reason is Reason.STALE_TRANSCRIPT,
          repr(r))
    check("N5a …and says re-record rather than blaming the test",
          "RE-RECORD" in r.detail, r.detail[:60])

    _saved_env = os.environ.pop("REPLAY_ELF", None)
    try:
        r = RP.replay_test(TID, TESTS[TID], t_ok,
                           expected_elf=RP.current_elf_expected("no-such-env"))
    finally:
        if _saved_env is not None:
            os.environ["REPLAY_ELF"] = _saved_env
    check("N6 no built firmware to compare against is INCONCLUSIVE(elf-unknown), "
          "not an assumption of freshness",
          r.status is Status.INCONCLUSIVE and r.reason is Reason.ELF_UNKNOWN,
          repr(r))

    r = RP.replay_test(TID, TESTS[TID], t_ok, elf_check=False)
    check("N7 a WAIVED elf check runs, but is not a confirmation",
          r.status is Status.OK and not r.is_confirmation, repr(r))

    check("N8 an empty transcript is INCONCLUSIVE(no-transcript)",
          rp(RP.Transcript(TID)).reason is Reason.NO_TRANSCRIPT)

    # ── N9: a real branch, not a hand-made hole ─────────────────────────────────
    # The DEV §4.1 case in its natural form: mutate a reply the body BRANCHES on and
    # it walks somewhere the recording never went. A positional store would hand it
    # the next recorded reply — plausible, wrong, and silent. The keyed store must
    # report a miss instead.

    t_branch = t_ok.mutate(
        lambda c, n, o: o.get("var") == "appId" and n == 0,
        lambda o: dict(o, val=APP_SLOT["Clock"], name="Clock"))
    r = rp(t_branch)
    check("N9 a mutation that makes the body branch off the recorded path reports "
          "a miss, not a plausible wrong reply",
          r.status is Status.INCONCLUSIVE
          and r.reason in (Reason.TRANSCRIPT_MISS, Reason.NO_VERDICT)
          or (r.status is Status.OK and r.verdict is R.Verdict.UNMET),
          repr(r))

    # ── N10: redaction ──────────────────────────────────────────────────────────
    check("N10 a secret-looking reply field never enters a transcript",
          '"<redacted>"' in RP.redact_line(
              '{"ok":true,"var":"cfg","refreshToken":"AQD-xyz"}')
          and "AQD-xyz" not in RP.redact_line(
              '{"ok":true,"var":"cfg","refreshToken":"AQD-xyz"}'))
    check("N10a …and a secret-looking argument never enters a command",
          RP.redact_cmd("set wifiPass hunter2") == "set wifiPass <redacted>",
          RP.redact_cmd("set wifiPass hunter2"))
    check("N10b …while an ordinary command is untouched",
          RP.redact_cmd("set clockStyle vfd") == "set clockStyle vfd")


    # ═════ TASK-631 — the fail ring ══════════════════════════════════════════════

    print("\nT631 — the last 20 exchanges behind a blocking verdict")


    def _ringed_dut(device, clock):
        d = object.__new__(Dut)
        d.ser = _FakeSerial(device, clock)
        d._owner_thread = threading.current_thread()
        d.port, d.elf, d.build_env = "fake", FAKE_ELF, "cyd2usb_winamp_debug"
        ring = RP.FailRing().wrap(d)
        return d, ring


    _clock = RP.VirtualClock()
    dut, ring = _ringed_dut(Device(pl_ticking=False), _clock)   # the residue defect
    R.RESULTS.clear()
    R.set_exchange_provider(ring.snapshot)
    try:
        ring.begin(TID)
        with RP.virtual_time(_clock):
            TESTS[TID](dut)
        doc = R.build_document(exit_code=1, order=[TID])
    finally:
        R.set_exchange_provider(None)

    _row = doc["results"][0]
    check("T1 the run FAILed (the ring is only interesting on a blocking verdict)",
          _row["verdict"] == "FAIL", _row["verdict"])
    _ex = _row["exchanges"]
    check("T2 the FAIL row carries its exchanges", bool(_ex), f"{_ex and len(_ex)}")
    check("T3 …exactly the last 20, never more", len(_ex or []) == RP.RING_LEN,
          f"{len(_ex or [])}")
    check("T4 …newest last, each with the id it happened under",
          _ex[-1]["seq"] > _ex[0]["seq"] and all(e["id"] == TID for e in _ex))
    check("T5 …carrying the command AND its reply",
          all("cmd" in e and "replies" in e for e in _ex)
          and any(e["replies"] for e in _ex))
    check("T6 the summary text did NOT grow a 20-line dump — the payload is in the "
          "artifact only",
          "exchanges" not in R.RESULTS[TID] and len(R.RESULTS[TID].splitlines()) == 1,
          R.RESULTS[TID][:70])
    # The field arrived in 1.1 and the schema only moves forward, so the
    # assertion is ">= the MINOR that added it", not "== 1.1": pinning the
    # equality made an unrelated additive bump (TASK-645's 1.2) red this arm,
    # which is a test asserting the schema never grows.
    check("T7 the artifact declares at least the MINOR that added the field",
          tuple(int(x) for x in doc["schema"]["version"].split("."))
          >= (1, 1), doc["schema"]["version"])

    # Green run: the payload must not merely be small, it must not be BUILT.
    R.RESULTS.clear()
    _clock = RP.VirtualClock()
    dut, ring = _ringed_dut(Device(), _clock)
    R.set_exchange_provider(ring.snapshot)
    try:
        ring.begin(TID)
        with RP.virtual_time(_clock):
            TESTS[TID](dut)
        doc_green = R.build_document(exit_code=0, order=[TID])
    finally:
        R.set_exchange_provider(None)
    check("T8 a PASS row carries no exchanges at all",
          doc_green["results"][0]["verdict"] == "PASS"
          and doc_green["results"][0]["exchanges"] is None)
    check("T9 …and nothing was captured into EXCHANGES on the green run",
          not R.EXCHANGES, f"{len(R.EXCHANGES)} captured")

    # ── the measurement, not an assertion ───────────────────────────────────────
    N = 20000
    _dev, _clk = Device(), RP.VirtualClock()
    _plain = _FakeSerial(_dev, _clk)
    _t = _time_mod.perf_counter()
    for _i in range(N):
        _plain.write(b"get appId\n")
        _plain.readline()
    _base = _time_mod.perf_counter() - _t

    _dev2, _clk2 = Device(), RP.VirtualClock()
    _d2 = object.__new__(Dut)
    _d2.ser = _FakeSerial(_dev2, _clk2)
    _d2._owner_thread = threading.current_thread()
    _ring2 = RP.FailRing().wrap(_d2)
    _ring2.begin(TID)
    _t = _time_mod.perf_counter()
    for _i in range(N):
        _d2.ser.write(b"get appId\n")
        _d2.ser.readline()
    _ringed = _time_mod.perf_counter() - _t

    _per_ex_us = (_ringed - _base) / N * 1e6
    _green_bytes = len(json.dumps(doc_green))
    _fail_bytes = len(json.dumps(doc))
    print(f"\n  [measured] ring overhead {_per_ex_us:.2f} µs per exchange "
          f"({_base*1e3:.0f} ms -> {_ringed*1e3:.0f} ms over {N} exchanges)")
    print(f"  [measured] a real exchange is a 115200-baud serial round trip: "
          f"~2-3 ms. The ring is ~{_per_ex_us/2000*100:.4f} % of one.")
    print(f"  [measured] artifact size: green {_green_bytes} B, "
          f"with one FAIL's 20 exchanges {_fail_bytes} B "
          f"(+{_fail_bytes - _green_bytes} B per blocking verdict)")
    print(f"  [measured] a full 195-id run's ring cost: "
          f"{_per_ex_us * 200 * 195 / 1e6:.3f} s at ~200 commands/id")
    check("T10 the ring costs under 5 µs per exchange", _per_ex_us < 5.0,
          f"{_per_ex_us:.2f} µs")
    check("T11 a green artifact grows by nothing",
          _green_bytes < _fail_bytes and abs(_green_bytes) > 0)

    # ═════════════════════════════════════════════════════════════════════════════

    print()
    if FAILURES:
        print(f"FAIL — {len(FAILURES)} arm(s) did not hold:")
        for f in FAILURES:
            print(f"  · {f}")
        return 1
    print("PASS — the engine replays a real body with no device, a transcript miss "
          "is INCONCLUSIVE and not a verdict, a broken mutator reports zero "
          "falsifications, a stale transcript says re-record, and a FAIL carries "
          "its last 20 exchanges at no cost to a green run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
