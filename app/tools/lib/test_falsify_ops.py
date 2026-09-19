#!/usr/bin/env python3
"""test_falsify_ops.py — negative suite for `lib/falsify_ops.py` (TASK-714).

WHY THIS LIVES IN `lib/`, NOT `gate/`. `falsify_ops.py` is a `lib/` module —
it depends only on `lib.replay` and is meant to be imported by a future
TASK-643 driver, not by a gate. Its own negative suite belongs next to it the
same way `lib/test_replay.py` sits next to `lib/replay.py` and
`lib/test_armed.py` sits next to the armed-state code it tests: a `gate/`
test pairs with a `check_*.py` gate script that CONSUMES a lib module's
output (`gate/test_check_can_go_red.py` tests the SWEEP's grading and ledger
logic, not `perturb_value` itself). This file tests the operators in
isolation, the way `lib/test_replay.py` tests `Transcript`/`replay_test` in
isolation before `check_can_go_red.py` ever runs a sweep over them.

WHAT IS PINNED HERE, per the task:

  * `perturb_threshold`/`scramble_string` are deterministic (same input, same
    output) and type-checked (raise, don't silently no-op, on the wrong type).
  * `perturb_threshold` actually moves a numeric reading past an arbitrary
    declared bound, in both directions of magnitude and across int/float.
  * `scramble_string` actually breaks `startswith`, `in`, and `==` together,
    on the literal needles named in the TASK-714 background (`T_PLR_08`'s
    `"(120)"`, `T_PLR_10`'s `"./"`/`"/mp3/"`) — `canfail.perturb_value` does
    NOT break any of the three, verified alongside so the contrast is run,
    not asserted from memory.
  * `lib.canfail.perturb_value` — THE SHARED R34 POISON — IS UNCHANGED. A
    fixed input/output pin on it is arm T1 below; if someone "improves" it to
    reach these two claim shapes, this suite catches it before
    `check_can_go_red.py`'s 129/196 or `check_restore_manager.py`'s 14 ledger
    rows move as a side effect.
  * both new operators actually flip a real test body's verdict when run
    through the REAL replay engine (`lib.replay.replay_test`), the same
    grading path `lib.canfail`'s R34 sweep uses (`_FailWitness`/`_grade`) —
    not merely "the Python function returns something different". `T_CLK_11`
    and `T_PLR_12` are BASELINE-NOT-PASS on their REAL recordings
    (`check_can_go_red.py`'s own report — confirmed before writing this file):
    there is no recorded PASS to arm a control+arm pair against. `T_CLK_11`
    uses a fully hand-built SYNTHETIC transcript, to the id's real command
    sequence; `T_PLR_12` instead HEALS the real 46-exchange recording (every
    line kept except the 5 `freeHeap` numbers, rewritten to a healthy delta) —
    both are allowed by this task's brief, and the difference is called out at
    each site below. The SUBSTRING demonstration uses a synthetic body+
    transcript (not `T_PLR_08`/10/11 verbatim — those ids are NOT declared by
    this task) built from the literal checks named in the background.

    python3 app/tools/lib/test_falsify_ops.py [-v]
"""

from __future__ import annotations

import os
import sys

_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_TOOLS, os.path.join(_TOOLS, "suite")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import canfail as CF                                    # noqa: E402
from lib import falsify_ops as FO                                 # noqa: E402
from lib import replay as RP                                      # noqa: E402
from lib import results as R                                      # noqa: E402
from lib.results import fail, pass_                                # noqa: E402

FAILURES: list = []
VERBOSE = "-v" in sys.argv


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'BAD '}{name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(f"{name}: {detail}")


# ── run a body against a transcript through the REAL grading path ───────────
#
# The same three lines `canfail.sweep()` uses for its baseline check, reused
# here rather than reinvented — `_wrapped`/`_FailWitness`/`_grade` are private
# but this is exactly the "own negative suite reaching into the module's
# internals" pattern `gate/test_check_can_go_red.py` already uses (`CF._grade`,
# `CF.poison_transcript`, `CF._dispatch`).

def _run(tid, body, transcript):
    arm_box = [None]
    run = CF._wrapped(tid, body, arm_box)
    with CF._FailWitness() as w:
        res = RP.replay_test(tid, run, transcript, elf_check=False, probe_time=True)
    grade = CF._grade(arm_box[0], w, tid) if res.status is RP.Status.OK else None
    return res, grade


def main() -> int:
    print("=== test_falsify_ops.py — TASK-714 operator negative suite ===")

    # ═════════════════════ T1 — the shared poison is unchanged ═════════════
    print("\n-- T1: canfail.perturb_value is untouched --")
    check("T1a int +1", CF.perturb_value(5) == 6)
    check("T1b float +1.0", CF.perturb_value(5.0) == 6.0)
    check("T1c bool flips", CF.perturb_value(True) is False)
    check("T1d string appends '~'", CF.perturb_value("x") == "x~")
    check("T1e perturb_value preserves a prefix (the exact gap THRESHOLD/"
          "SUBSTRING exist because of)",
          "./music/track.mp3~".startswith("./")
          and CF.perturb_value("./music/track.mp3") == "./music/track.mp3~")
    check("T1f perturb_value preserves containment",
          "(120)" in CF.perturb_value("Title (120)"))
    check("T1g perturb_value(+1) cannot cross a 4096 bound",
          abs(CF.perturb_value(106168) - 106168) < 4096)

    # ═════════════════════ T2 — perturb_threshold, pure ═════════════════════
    print("\n-- T2: perturb_threshold (THRESHOLD shape) --")
    check("T2a moves an int past its bound",
          abs(FO.perturb_threshold(106168, 4096) - 106168) > 4096)
    check("T2b moves a float past its bound",
          abs(FO.perturb_threshold(106168.5, 4096) - 106168.5) > 4096)
    check("T2c deterministic — same input, same output",
          FO.perturb_threshold(60136, 4096) == FO.perturb_threshold(60136, 4096))
    check("T2d moves DOWN — the direction every measured budget check needs "
          "(earlier - later > bound; decreasing 'later' widens the delta)",
          FO.perturb_threshold(100, 10) < 100)
    check("T2e crosses regardless of starting magnitude (a near-zero reading,"
          " the T_PLR_12 'd_free' shape)",
          abs(FO.perturb_threshold(3, 256) - 3) > 256)
    try:
        FO.perturb_threshold(True, 10)
        check("T2f rejects bool (not a real numeric reading)", False)
    except TypeError:
        check("T2f rejects bool (not a real numeric reading)", True)
    try:
        FO.perturb_threshold("5", 10)
        check("T2g rejects a string value", False)
    except TypeError:
        check("T2g rejects a string value", True)
    try:
        FO.perturb_threshold(5, 0)
        check("T2h rejects a non-positive bound", False)
    except ValueError:
        check("T2h rejects a non-positive bound", True)
    try:
        FO.perturb_threshold(5, -1)
        check("T2i rejects a negative bound", False)
    except ValueError:
        check("T2i rejects a negative bound", True)

    # ═════════════════════ T3 — scramble_string, pure ═══════════════════════
    print("\n-- T3: scramble_string (SUBSTRING shape) --")
    s1 = "./music/track.mp3"
    m1 = FO.scramble_string(s1)
    check("T3a type-preserving", isinstance(m1, str))
    check("T3b breaks startswith (perturb_value does not)",
          not m1.startswith("./") and s1.startswith("./"))
    s2 = "Title (120)"
    m2 = FO.scramble_string(s2)
    check("T3c breaks containment (perturb_value does not)",
          "(120)" not in m2 and "(120)" in s2)
    check("T3d breaks equality", m2 != s2)
    check("T3e deterministic", FO.scramble_string(s2) == FO.scramble_string(s2))
    check("T3f length-preserving (a pure substitution cipher, not append/drop)",
          len(m2) == len(s2))
    s3 = "/mp3/01 - Tomorrow Comes Today.mp3"
    m3 = FO.scramble_string(s3)
    check("T3g breaks a longer real-corpus path's prefix",
          not m3.startswith("/mp3/") and s3.startswith("/mp3/"))
    # non-ASCII: the UTF-8 fold corpus (T_PLR_11) exercises codepoints outside
    # printable ASCII once folded to '?', but the operator must still behave on
    # real non-ASCII input (pre-fold), not just on the folded placeholder.
    s4 = "Bj富rk"
    m4 = FO.scramble_string(s4)
    check("T3h non-ASCII codepoint still shifts (no no-op character)",
          all(a != b for a, b in zip(s4, m4)))
    try:
        FO.scramble_string(12345)
        check("T3i rejects a non-string value", False)
    except TypeError:
        check("T3i rejects a non-string value", True)

    # ═════════════ T4 — perturb_threshold bites through the REAL engine ═════
    # T_CLK_11's shape: two `info` reads of `heap`; fail iff h0 - h1 >= 4096.
    # SYNTHETIC transcript — T_CLK_11's real recording is BASELINE-NOT-PASS
    # (confirmed via `check_can_go_red.py` before writing this: the recorded
    # board session already leaked 46032 B, so there is no recorded PASS to
    # arm against). Built to the id's real command sequence
    # (suite/serialdbg/clock.py: `_switch_to_clock` + the double style-cycle +
    # the extra reset + `_restore_spotify_from_clock`).
    print("\n-- T4: perturb_threshold flips T_CLK_11 through replay_test "
          "(SYNTHETIC transcript — the real recording is BASELINE-NOT-PASS) --")
    from suite.serialdbg.clock import t_clk_11

    def _info(heap):
        return ('{"ok":true,"cmd":"info","git":"a","elf":"x","build":"x",'
                f'"heap":{heap},"isPlaying":false,"progressMs":0,'
                '"durationMs":0,"volumePct":-1,"shuffle":false,"repeat":2,'
                '"consecutiveFailures":0}')

    def _set_style(i):
        names = ["digital", "flip", "nixie", "vfd"]
        return ('{"ok":true,"cmd":"set","var":"clockStyle","val":%d,'
                '"name":"%s","saved":true}') % (i, names[i])

    def _build_clk11_transcript(h0, h1):
        t = RP.Transcript("T_CLK_11", elf="synthetic", build_env=None)
        t.add("switchApp 1", ['{"ok":true,"cmd":"switchApp","id":1}'])
        t.add("info", [_info(h0)])
        for i in (0, 1, 2, 3):
            t.add(f"set clockStyle {i}", [_set_style(i)])
        for i in (0, 1, 2, 3):
            t.add(f"set clockStyle {i}", [_set_style(i)])
        t.add("set clockStyle 0", [_set_style(0)])          # the extra reset
        t.add("info", [_info(h1)])
        t.add("set clockStyle 0", [_set_style(0)])          # restore (only
        t.add("switchApp 0", ['{"ok":true,"cmd":"switchApp","id":0}'])  # reached on PASS)
        return t

    healthy = _build_clk11_transcript(100000, 99950)        # leak=50 < 4096
    res0, grade0 = _run("T_CLK_11", t_clk_11, healthy)
    check("T4a synthetic baseline replays to PASS with no miss",
          res0.status is RP.Status.OK and res0.verdict is R.Verdict.PASS,
          f"status={res0.status} verdict={getattr(res0, 'verdict', None)} "
          f"detail={res0.detail}")

    mutated = FO.mutate_field(healthy, FO.by_cmd("info", nth=1), "heap",
                              FO.perturb_threshold, 4096)
    res1, grade1 = _run("T_CLK_11", t_clk_11, mutated)
    check("T4b THRESHOLD-mutated arm goes red — ASSERTION",
          res1.status is RP.Status.OK and res1.verdict is R.Verdict.FAIL
          and grade1 is CF.Grade.ASSERTION,
          f"status={res1.status} verdict={getattr(res1, 'verdict', None)} "
          f"grade={grade1} record={getattr(res1, 'record', '')[:100]}")

    # ═════════════ T5 — perturb_threshold bites T_PLR_12 (d_load, d_free) ═══
    # T_PLR_12's shape: 5 `get plMem` reads; two derived-delta checks against
    # `base.freeHeap`. HEALED-REAL transcript, not hand-built from scratch:
    # T_PLR_12's actual recording (suite/serialdbg/transcripts/T_PLR_12.json)
    # is a real, full 46-exchange session — `_enter_player`'s taskbar-tap
    # retries, `_switch_to`'s scroll-offset dance, the real `set plLoad`/
    # `get plCount` exchange, all of it — and it is BASELINE-NOT-PASS for an
    # ORDINARY reason: `check_can_go_red.py` reports it FAILs, and reading the
    # 5 `freeHeap` values off it (55764 -> 97320 -> 48976 -> 97716 -> 101396)
    # shows why — real Spotify backoff/TLS churn during the recording moved
    # free heap by tens of KB in EITHER direction between reads, so
    # `d_free = base - freed` is -45632 on this recording, `abs(...) > 256`
    # trips even though nothing leaked. Rewriting ONLY the 5 `freeHeap`
    # numbers (every other line, including the non-JSON diagnostic noise,
    # untouched) turns it into a healthy PASS without inventing a command
    # sequence by hand — the real body's real branches are what get replayed.
    print("\n-- T5: perturb_threshold flips T_PLR_12's d_load/d_free through "
          "replay_test (a HEALED COPY of the real recording — see comment) --")
    from suite.serialdbg.player import t_plr_12

    _PLR12_PATH = os.path.join(_TOOLS, "suite", "serialdbg", "transcripts",
                               "T_PLR_12.json")

    def _healed_plr12(free_heaps: dict) -> RP.Transcript:
        """A copy of the REAL T_PLR_12 recording with `freeHeap` on the
        `nth`-th `get plMem` exchange replaced per `free_heaps` (nth -> value);
        every other field, and every non-JSON line, is untouched."""
        base = RP.Transcript.load(_PLR12_PATH)

        # `Transcript.mutate`'s `fn` does not see `nth`, so this healing step
        # (fixing up a fixture, NOT the falsifier operator) rewrites the copy
        # directly instead. The operator itself (`perturb_threshold`, via
        # `mutate_field`/`by_var` below) is applied separately, afterward.
        out = RP.Transcript(base.tid, base.elf, base.build_env,
                            base.recorded_at, base.gen)
        out.preamble = list(base.preamble)
        import json as _json
        for (cmd, nth), lines in base.exchanges.items():
            if cmd == "get plMem" and nth in free_heaps:
                new_lines = []
                for ln in lines:
                    s = (ln or "").strip()
                    if s.startswith("{"):
                        obj = _json.loads(s)
                        if obj.get("var") == "plMem":
                            obj["freeHeap"] = free_heaps[nth]
                            new_lines.append(_json.dumps(obj))
                            continue
                    new_lines.append(ln)
                out.exchanges[(cmd, nth)] = new_lines
            else:
                out.exchanges[(cmd, nth)] = list(lines)
        return out

    # real occurrences: 0=base, 1=entered, 2=peak, 3=after, 4=freed
    healthy2 = _healed_plr12({0: 100000, 1: 99400, 2: 95200, 3: 95050, 4: 99900})
    res2, grade2 = _run("T_PLR_12", t_plr_12, healthy2)
    check("T5a synthetic baseline replays to PASS with no miss",
          res2.status is RP.Status.OK and res2.verdict is R.Verdict.PASS,
          f"status={res2.status} verdict={getattr(res2, 'verdict', None)} "
          f"detail={res2.detail}")

    # The 4th `get plMem` occurrence (nth=3) is `after`. Push it down by more
    # than the 5324 B `d_load` bound.
    mutated_load = FO.mutate_field(healthy2, FO.by_var("plMem", nth=3),
                                   "freeHeap", FO.perturb_threshold, 5324)
    res3, grade3 = _run("T_PLR_12", t_plr_12, mutated_load)
    check("T5b THRESHOLD-mutated d_load arm goes red — ASSERTION",
          res3.status is RP.Status.OK and res3.verdict is R.Verdict.FAIL
          and grade3 is CF.Grade.ASSERTION,
          f"status={res3.status} verdict={getattr(res3, 'verdict', None)} "
          f"grade={grade3} record={getattr(res3, 'record', '')[:120]}")

    # The 5th `get plMem` occurrence (nth=4) is `freed`. Push it down by more
    # than the 256 B `d_free` bound.
    mutated_free = FO.mutate_field(healthy2, FO.by_var("plMem", nth=4),
                                   "freeHeap", FO.perturb_threshold, 256)
    res4, grade4 = _run("T_PLR_12", t_plr_12, mutated_free)
    check("T5c THRESHOLD-mutated d_free arm goes red — ASSERTION",
          res4.status is RP.Status.OK and res4.verdict is R.Verdict.FAIL
          and grade4 is CF.Grade.ASSERTION,
          f"status={res4.status} verdict={getattr(res4, 'verdict', None)} "
          f"grade={grade4} record={getattr(res4, 'record', '')[:120]}")

    # ═════════════ T6 — scramble_string bites through the REAL engine ═══════
    # A minimal, hand-written demo body — NOT a registered suite id, and NOT
    # T_PLR_08/10/11 (this task declares neither). It exercises exactly the
    # two checks named in the TASK-714 background: a prefix check and a
    # containment check against one string reply, so the SUBSTRING operator's
    # bite is shown through the same replay/grading path as T4/T5, not merely
    # as a bare function call.
    print("\n-- T6: scramble_string flips a SUBSTRING-shaped demo body "
          "through replay_test (hand-written demo body, not a suite id) --")

    def _substring_demo_body(dut):
        tid = "T_FALSIFY_DEMO"
        r = dut.cmd("get plRow 0")
        # One-arg `.get()` (not `.get("text", "")`) — R18/`check_defaulted_reads.py`
        # forbids defaulting a device-reply field to a same-typed literal, since a
        # dropped field then reads as a real empty string instead of a failure.
        text = r.get("text")
        if not text or not text.startswith("/mp3/"):
            fail(tid, f"path {text!r} did not resolve under /mp3/")
            return
        if "(120)" not in text:
            fail(tid, f"row text {text!r} missing the expected '(120)' tag")
            return
        pass_(tid, f"row text {text!r} OK")

    def _row_reply(text):
        return '{"ok":true,"cmd":"get","var":"plRow","idx":0,"text":"%s","durSec":192}' % text

    demo_t = RP.Transcript("T_FALSIFY_DEMO", elf="synthetic", build_env=None)
    demo_t.add("get plRow 0", [_row_reply("/mp3/01 - Track (120).mp3")])
    res5, grade5 = _run("T_FALSIFY_DEMO", _substring_demo_body, demo_t)
    check("T6a demo baseline replays to PASS",
          res5.status is RP.Status.OK and res5.verdict is R.Verdict.PASS,
          f"status={res5.status} verdict={getattr(res5, 'verdict', None)}")

    # First show perturb_value does NOT falsify it (the documented gap).
    perturbed = FO.mutate_field(demo_t, FO.by_var("plRow"), "text",
                                CF.perturb_value)
    res6, grade6 = _run("T_FALSIFY_DEMO", _substring_demo_body, perturbed)
    check("T6b perturb_value ('~'-appended) leaves the demo body PASS "
          "(the exact gap SUBSTRING exists to close)",
          res6.status is RP.Status.OK and res6.verdict is R.Verdict.PASS,
          f"status={res6.status} verdict={getattr(res6, 'verdict', None)}")

    scrambled = FO.mutate_field(demo_t, FO.by_var("plRow"), "text",
                               FO.scramble_string)
    res7, grade7 = _run("T_FALSIFY_DEMO", _substring_demo_body, scrambled)
    check("T6c SUBSTRING-mutated arm goes red — ASSERTION",
          res7.status is RP.Status.OK and res7.verdict is R.Verdict.FAIL
          and grade7 is CF.Grade.ASSERTION,
          f"status={res7.status} verdict={getattr(res7, 'verdict', None)} "
          f"grade={grade7} record={getattr(res7, 'record', '')[:120]}")

    print()
    if FAILURES:
        print(f"FAIL — {len(FAILURES)} check(s) did not hold:")
        for f in FAILURES:
            print(f"  · {f}")
        return 1
    print("PASS — perturb_value is unchanged; perturb_threshold crosses an "
          "arbitrary declared bound and flips T_CLK_11/T_PLR_12's real bodies "
          "to ASSERTION FAIL through the real replay engine; scramble_string "
          "breaks startswith/in/== where perturb_value does not, and flips a "
          "SUBSTRING-shaped demo body the same way.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
