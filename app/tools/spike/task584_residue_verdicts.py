#!/usr/bin/env python3
"""TASK-584 proof harness — the six `_check_residue` callers can now FAIL.

WHAT THIS IS. `D-2` found six ids that spend the residue regression on a
`skip()`: the helper returns `False` on exactly the condition the ids exist to
catch, and every caller turned that into a green, non-blocking SKIP. TASK-584
converts those exits to `fail()`. This file is the evidence that the conversion
took — that each of the six now reaches a `fail()` on ITS OWN SUBJECT, and that
the branches which are genuinely not the subject land on `UNMET` (which blocks,
ADR-066 D4) rather than on a skip or an invented regression.

WHY A SPIKE AND NOT A GATE. It proves a property of six bodies at one moment,
not an invariant of the corpus; the corpus invariant is R34's no-reachable-
`fail()` gate, which is TASK-603's to specify and land. `run/check-docs`' SPIKE
check retires this file when TASK-584 is archived, which is correct: once R34's
gate is blocking, it subsumes the reachability half of this proof.

METHOD — no DUT, no serial port, host-only.
  * The six bodies are obtained through `build_all_tests()`, the sanctioned
    entry point; nothing else is imported from the suite.
  * The REAL `lib.dut.Dut` is used, not a stand-in. Only the transport is fake:
    a scripted byte-level `ser` object with `write`/`flush`/`readline`. So
    `cmd`, `read_reply`, `get_int`, `get_str`, the reply correlation and the
    NoAnswer/BadField split all execute their production code paths. A fake
    `Dut` would have proved that the fake agrees with itself.
  * A virtual clock replaces `time.sleep`/`time.monotonic` so the 3 s residue
    windows and the 0.4 s settles cost nothing and are deterministic.

Run: `python3 app/tools/spike/task584_residue_verdicts.py`   (exit 0 = proved)
"""

import json
import os
import sys
import threading
import time as _time_mod

_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_TOOLS, os.path.join(_TOOLS, "suite")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ── virtual clock ────────────────────────────────────────────────────────────
# Patched onto the stdlib `time` module so every `import time` in the suite and
# in lib/dut.py sees it. Nothing in the tested paths uses wall-clock time for
# anything but bounding a loop, so a monotonic counter is a faithful model.

class _Clock:
    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t

    def sleep(self, d):
        self.t += max(0.0, float(d))


_CLOCK = _Clock()
_REAL_SLEEP, _REAL_MONO = _time_mod.sleep, _time_mod.monotonic
_time_mod.sleep = _CLOCK.sleep
_time_mod.monotonic = _CLOCK.monotonic

import coords as _c                                             # noqa: E402
from app_ids_gen import APP_SLOT                                # noqa: E402
from lib import results as R                                    # noqa: E402
from lib.dut import Dut, NoAnswer                               # noqa: E402
from serialdbg import build_all_tests                           # noqa: E402

_SLOT_TO_APP = {v: k for k, v in APP_SLOT.items()}
_TB_N = APP_SLOT["WebRadio"]          # taskbar cycle length (TASK-242)
#: slot y-centre -> slot index, derived from the generated layout, not typed.
_Y_TO_SLOT = {_c.tap_taskbar_slot(i)[1]: i for i in range(_TB_N + 1)}


# ── the scripted device ──────────────────────────────────────────────────────

class FakeSerial:
    """A byte-level stand-in for `Dut.ser` driving a small model of the shell."""

    def __init__(self, dev):
        self.dev = dev
        self.out = []

    def write(self, b):
        line = b.decode().strip()
        for reply in self.dev.handle(line):
            self.out.append(json.dumps(reply) + "\n")

    def flush(self):
        pass

    def readline(self):
        if self.out:
            return self.out.pop(0).encode()
        # Nothing queued: the line is quiet. Advance the virtual clock so the
        # caller's deadline is reachable instead of spinning forever.
        _CLOCK.t += 0.01
        return b""


class Device:
    """Enough of the shell to run the six bodies, with per-scenario knobs."""

    def __init__(self, app="Spotify", tb_offset=0, sub_view="list",
                 pl_ticking=True, silent=(), taps_miss=(), drag_dead=False,
                 switch_app_dead=False):
        self.app = app
        self.tb_offset = tb_offset
        self.sub_view = sub_view
        self.pl_ticking = pl_ticking      # False => lastPlaylistDraw frozen
        self.silent = set(silent)         # vars the device will not answer
        self.taps_miss = set(taps_miss)   # taps that resolve to these apps miss
        self.drag_dead = drag_dead        # taskbar drags do not move the offset
        self.switch_app_dead = switch_app_dead
        self.pl_ms = 500_000

    # -- helpers ------------------------------------------------------------
    def _var(self, _var_name, **kw):
        if _var_name in self.silent:
            return []
        return [dict(ok=True, var=_var_name, **kw)]

    def _arrive(self, app):
        if app in self.taps_miss:
            self.app = "Clock"            # a plausible miss: the neighbour slot
            return
        self.app = app

    # -- the wire -----------------------------------------------------------
    def handle(self, line):
        w = line.split()
        if w[:1] == ["set"]:
            return [{"ok": True, "cmd": "set"}]
        if w[:1] == ["switchApp"]:
            if not self.switch_app_dead:
                self._arrive(_SLOT_TO_APP.get(int(w[1]), "Clock"))
            return [{"ok": True, "cmd": "switchApp"}]
        if w[:1] == ["tap"]:
            x, y = int(w[1]), int(w[2])
            if y in _Y_TO_SLOT and x >= 275:          # taskbar column
                slot = _Y_TO_SLOT[y]
                self._arrive(_SLOT_TO_APP.get((slot + self.tb_offset) % _TB_N,
                                              "Clock"))
            elif self.app == "Stock" and y < 60:      # the chart-drill tap
                self.sub_view = "chart" if not self.drag_dead else self.sub_view
            return [{"ok": True, "cmd": "tap", "hit": "TASKBAR"}]
        if w[:1] == ["drag"]:
            if not self.drag_dead:
                # One taskbar slot per TASKBAR_SLOT_H of travel, signed: this is
                # the model `_tb_set_offset` was written against (50 px = +1).
                y1, y2 = int(w[2]), int(w[4])
                steps = (y1 - y2) // _c.TASKBAR_SLOT_H
                self.tb_offset = (self.tb_offset + steps) % _TB_N
            return [{"ok": True, "cmd": "drag"}]
        if w[:2] == ["get", "shellCooldown"]:
            return [{"ok": True, "var": "shellCooldown", "remainingMs": 0}]
        if w[:2] == ["get", "appId"]:
            return self._var("appId", val=APP_SLOT.get(self.app, 1),
                             name=self.app)
        if w[:2] == ["get", "tbScrollOffset"]:
            return self._var("tbScrollOffset", val=self.tb_offset)
        if w[:2] == ["get", "stockSubView"]:
            return self._var("stockSubView", val=self.sub_view)
        if w[:2] == ["get", "lastPlaylistDraw"]:
            # SpotifyApp::tick() -> drawPlaylist() -> PleditView::draw() stamps
            # _lastDrawMs whenever the shell is on Spotify and ticking.
            if self.app == "Spotify" and self.pl_ticking:
                self.pl_ms += 17
            return self._var("lastPlaylistDraw", ms=self.pl_ms)
        return [{"ok": True, "cmd": w[0] if w else "?"}]


def make_dut(dev):
    """A REAL `Dut` with a fake transport — see the module docstring."""
    d = object.__new__(Dut)
    d.ser = FakeSerial(dev)
    d._owner_thread = threading.current_thread()
    d.port = "fake"
    return d


# ── the scenario table ───────────────────────────────────────────────────────
# Each row: (id, label, Device kwargs, expected Verdict | "raises NoAnswer").
# "SUBJECT" in a label marks a row that is the regression the id exists to
# catch — the rows D-2 says used to be green.

V = R.Verdict
SHELL = [("T_MA_03", "Matrix"), ("T_GOL_03", "Life"),
         ("T_WX_03", "Weather"), ("T_CX_03", "Crypto")]

SCENARIOS = []
for tid, app in SHELL:
    SCENARIOS += [
        (tid, f"cannot reach {app} (precondition)", dict(taps_miss=[app]), V.UNMET),
        (tid, "tap back missed Spotify",
         dict(taps_miss=["Spotify"]), V.FAIL),
        (tid, "SUBJECT: clock frozen after switch-back",
         dict(pl_ticking=False), V.FAIL),
        (tid, "device silent on lastPlaylistDraw",
         dict(silent=["lastPlaylistDraw"]), "NoAnswer"),
        (tid, "healthy round trip", dict(), V.PASS),
    ]

SCENARIOS += [
    ("T172", "cannot start on Spotify (precondition)",
     dict(app="Clock", taps_miss=["Spotify"]), V.UNMET),
    ("T172", "cannot reach Stock", dict(taps_miss=["Stock"]), V.FAIL),
    ("T172", "SUBJECT: clock frozen after Stock->Spotify",
     dict(pl_ticking=False), V.FAIL),
    ("T172", "device silent on lastPlaylistDraw",
     dict(silent=["lastPlaylistDraw"]), "NoAnswer"),
    ("T172", "healthy round trip", dict(), V.PASS),

    ("T182", "cannot start on Spotify (precondition)",
     dict(app="Clock", taps_miss=["Spotify"]), V.UNMET),
    ("T182", "cannot enter chart view (precondition)",
     dict(drag_dead=True), V.UNMET),
    ("T182", "SUBJECT: taskbar drag did not scroll",
     dict(), V.FAIL),                       # patched below: drag dies mid-body
    ("T182", "SUBJECT: taskbar slot tap landed elsewhere",
     dict(taps_miss=["Stock"]), V.FAIL),
    ("T182", "SUBJECT: clock frozen after taskbar-driven return",
     dict(pl_ticking=False), V.FAIL),
    ("T182", "device goes silent at the taskbar-arrival read",
     dict(), "NoAnswer"),
    ("T182", "healthy round trip", dict(), V.PASS),
]


class _SilentAtArrival(Device):
    """T182's typed `get appId` after the slot tap goes unanswered — the case
    TASK-596's accessor exists to separate from a wrong answer. It must raise
    NoAnswer (-> UNMET at the runner), never report the taskbar as broken."""

    def handle(self, line):
        if line.startswith("tap ") and self.tb_offset == 2:
            self.silent.add("appId")
        return super().handle(line)


class _DragDiesAfterChart(Device):
    """T182's taskbar scroll fails, but only after the chart drill succeeded —
    the one arrangement that reaches the scroll assertion at all."""

    def handle(self, line):
        if line.startswith("drag ") and self.sub_view == "chart":
            self.drag_dead = True
        return super().handle(line)


# ── driver ───────────────────────────────────────────────────────────────────

def run() -> int:
    tests = build_all_tests()
    bad, n = [], 0
    print(f"TASK-584 — {len(SCENARIOS)} scenarios over 6 ids\n")
    for tid, label, kw, expect in SCENARIOS:
        n += 1
        cls = (_DragDiesAfterChart if "drag did not scroll" in label
               else _SilentAtArrival if "silent at the taskbar-arrival" in label
               else Device)
        dev = cls(**kw)
        dut = make_dut(dev)
        R.RESULTS.clear()
        R.VERDICTS.clear()
        raised = None
        try:
            tests[tid](dut)
        except NoAnswer as e:
            raised = e
        except Exception as e:                                  # pragma: no cover
            raised = e

        if expect == "NoAnswer":
            got = "NoAnswer" if isinstance(raised, NoAnswer) else (
                f"{type(raised).__name__}" if raised else
                f"no raise; verdict={R.VERDICTS.get(tid)}")
            ok = got == "NoAnswer"
        else:
            got = R.VERDICTS.get(tid)
            ok = (raised is None and got is expect)
            got = f"{got.value if got else None}" + (
                f" (+{type(raised).__name__})" if raised else "")
            expect_s = expect.value
        expect_s = expect if expect == "NoAnswer" else expect.value
        mark = "ok  " if ok else "BAD "
        print(f"  {mark}{tid:9s} {label:48s} expect={expect_s:8s} got={got}")
        if not ok:
            bad.append(f"{tid}: {label} — expected {expect_s}, got {got}")

    print()
    if bad:
        print(f"FAIL — {len(bad)} of {n} scenarios did not produce the "
              f"designed verdict:")
        for b in bad:
            print(f"  · {b}")
        return 1
    print(f"PASS — all {n} scenarios produced the designed verdict.")
    print("Each of the six ids reaches a fail() on its own subject; every "
          "unestablished precondition lands on UNMET (blocking), and a silent "
          "device raises NoAnswer -> UNMET at the runner rather than being "
          "reported as the regression.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    finally:
        _time_mod.sleep, _time_mod.monotonic = _REAL_SLEEP, _REAL_MONO
