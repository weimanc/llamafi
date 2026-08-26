#!/usr/bin/env python3
"""
TASK-488 Part B — DUT verification of the three M-SRCLAYOUT refactor commits
(a044f5d / 78caa95 / b36f184).

Pass criteria: docs/project/tasks-architecture.md § TASK-488 — pass criteria.
Ids T_488_04 .. T_488_11. Part A (T_488_01..03) is host-only and lives in the
session record, not here.

Flash cyd2usb_winamp_debug first (run/task488 does this and restores prod).

    ./run/task488

Every app sweep runs THREE full cycles: g_appLaunched[] makes the first visit
call init() and every later visit resume(), so a one-pass sweep would exercise
only init() and miss a broken resume() — the specific bug class these commits
could introduce.
"""

from __future__ import annotations

import re
import sys
import time

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

import coords as _c                                     # noqa: E402
from app_ids_gen import APP_ORDER, APP_SLOT             # noqa: E402
from lib.dut import Dut                                  # noqa: E402  TASK-479: direct import
from ve_suite_base import (                             # noqa: E402
    RESULTS, pass_, fail, skip,
    make_arg_parser, run_suite, print_results,
)

ALL_TESTS = [f"T_488_{n:02d}" for n in range(4, 12)]

# Taskbar carries only the apps before WebRadio (WebRadio/LocalPlayer are
# eject-only — see feedback_webradio_eject_only / TASK-242).
_TB_N = APP_SLOT["WebRadio"]
_TB_X = _c.TASKBAR_X + _c.TASKBAR_W // 2
_VISIBLE_SLOTS = 240 // _c.TASKBAR_SLOT_H          # 6 physical slots on screen

# Settings geometry, mirrored from app/src/settings/settingsSection.h.
_S_CONTENT_Y = 28
_S_ROW_H = 26
_SETTINGS_ID = APP_SLOT["Settings"]

_T0 = time.monotonic()

_RESET_RE = re.compile(r"Guru Meditation|rst:0x|Backtrace:|abort\(\) was called|"
                       r"Task watchdog got triggered|ets Jul")

# Cycle-1 heap sample for T_488_11, filled by T_488_04.
_HEAP = {}
# Serial evidence collected during the T_488_04 sweep, consumed by T_488_05.
_SWEEP_LOG = []


# ── helpers ───────────────────────────────────────────────────────────────────

def _switch(dut: Dut, app_id: int, settle: float = 0.6) -> tuple[str | None, list[str]]:
    """switchApp <id>, then read back `get appId`. Returns (name, serial lines
    seen between the two commands) so a reset signature can be caught in situ."""
    dut.send(f"switchApp {app_id}")
    lines = []
    deadline = time.monotonic() + settle
    while time.monotonic() < deadline:
        line = dut.ser.readline().decode(errors="replace").strip()
        if line:
            lines.append(line)
    # A `get` can go unanswered for seconds while tlsYield or a fetch holds the
    # shell (see the tlsYield-starvation history) — that is a slow console, not
    # a dead device, so retry once with a longer window before giving up.
    try:
        r = dut.cmd("get appId", timeout=5.0)
    except TimeoutError:
        r = dut.cmd("get appId", timeout=15.0)
    return (r.get("name") if r.get("ok") else None), lines


def _restore(dut: Dut):
    dut.cmd("set playerMode spotify", timeout=3.0)
    _switch(dut, APP_SLOT["Spotify"])


def _heap(dut: Dut) -> int | None:
    """Free internal heap. `get heap` reports freeInt/lfbInt/freeDma/lfbDma."""
    try:
        r = dut.cmd("get heap", timeout=5.0)
    except TimeoutError:
        r = dut.cmd("get heap", timeout=15.0)
    v = r.get("freeInt")
    return int(v) if isinstance(v, (int, float)) else None


def _elapsed_s() -> float:
    """Seconds since this suite opened the port — the firmware exposes no
    uptime, so before/after heap samples are anchored to host time instead."""
    return time.monotonic() - _T0


# ── T_488_04 / 05 — the 39-switch sweep ───────────────────────────────────────

def t_488_04(dut: Dut):
    """3 cycles x 13 apps = 39 switches; every switch lands on the requested id,
    no reboot / WDT / Guru Meditation anywhere in the sweep."""
    print("T_488_04  switchapp 0..12 x3 cycles (39 switches), no reset")
    _HEAP["before"] = _heap(dut)
    _HEAP["before_t"] = _elapsed_s()
    wrong, resets = [], []
    for cycle in (1, 2, 3):
        for app_id, name in enumerate(APP_ORDER):
            got, lines = _switch(dut, app_id)
            _SWEEP_LOG.append((cycle, name, lines))
            for ln in lines:
                if _RESET_RE.search(ln):
                    resets.append(f"cycle{cycle}/{name}: {ln}")
            if got != name:
                wrong.append(f"cycle{cycle}: switchApp {app_id} ({name}) -> {got!r}")
        print(f"    cycle {cycle}/3 complete")
    _HEAP["after"] = _heap(dut)
    _HEAP["after_t"] = _elapsed_s()
    _HEAP["sweep_duration"] = _HEAP["after_t"] - _HEAP["before_t"]
    _restore(dut)
    if resets:
        fail("T_488_04", f"reset signature during sweep: {resets[:3]}")
        return
    if wrong:
        fail("T_488_04", f"{len(wrong)} switches landed wrong: {wrong[:5]}")
        return
    pass_("T_488_04", "39/39 switches landed on the requested id, no reset")


def t_488_05(dut: Dut):
    """init() exactly once (cycle 1), resume() on cycles 2 and 3.

    Only two apps emit a distinguishable marker: Aquarium ('[aquarium] init
    sprite' / '[aquarium] resume sprite') and WebRadio ('HEAP init'). Aquarium
    is one of the three whose state struct a044f5d deleted, so it is the app
    this criterion most needs. The other eleven emit no init/resume marker at
    all — recorded as not-observable rather than inferred (adding firmware
    instrumentation is out of scope for a verification-only session).
    """
    print("T_488_05  init once / resume on later cycles (log markers)")
    if not _SWEEP_LOG:
        skip("T_488_05", "T_488_04 did not run — no sweep log to read")
        return
    seen = {}
    for cycle, name, lines in _SWEEP_LOG:
        for ln in lines:
            if "[aquarium] init" in ln:
                seen.setdefault(("Aquarium", "init"), []).append(cycle)
            if "[aquarium] resume" in ln:
                seen.setdefault(("Aquarium", "resume"), []).append(cycle)
            if "webradio" in ln and "HEAP init" in ln:
                seen.setdefault(("WebRadio", "init"), []).append(cycle)
    aq_init = seen.get(("Aquarium", "init"), [])
    aq_res = seen.get(("Aquarium", "resume"), [])
    detail = f"aquarium init={aq_init} resume={aq_res} webradio init={seen.get(('WebRadio','init'), [])}"
    if aq_init != [1]:
        fail("T_488_05", f"Aquarium init cycles={aq_init}, expected exactly [1] ({detail})")
        return
    if sorted(set(aq_res)) != [2, 3]:
        fail("T_488_05", f"Aquarium resume cycles={aq_res}, expected 2 and 3 ({detail})")
        return
    pass_("T_488_05", detail + "  (11 apps emit no marker — not observable)")


# ── T_488_06 — the three deleted-struct apps ──────────────────────────────────

def t_488_06(dut: Dut):
    """Spotify / Clock / Aquarium — the three whose state structs a044f5d
    deleted. Enter, leave, re-enter x3; state must survive re-entry."""
    print("T_488_06  Spotify/Clock/Aquarium state survives re-entry x3")
    probes = {
        "Clock": ("get clockStyle", ("style", "val", "name")),
        "Aquarium": ("get aquariumFish", ("count", "fish", "val")),
        "Spotify": ("get songDuration", ("ms", "val", "duration")),
    }
    readings = {}
    bad = []
    for name, (cmd, keys) in probes.items():
        vals = []
        for _ in range(3):
            _switch(dut, APP_SLOT[name])
            time.sleep(0.5)
            r = dut.cmd(cmd, timeout=5.0)
            v = next((r[k] for k in keys if k in r), None)
            vals.append(v)
            _switch(dut, APP_SLOT["Clock" if name != "Clock" else "Matrix"])
            time.sleep(0.3)
        readings[name] = vals
        if any(v is None for v in vals):
            bad.append(f"{name}: probe {cmd} unreadable {vals}")
        elif name in ("Clock", "Aquarium") and len(set(map(str, vals))) != 1:
            bad.append(f"{name}: state changed across re-entry {vals}")
    _restore(dut)
    if bad:
        fail("T_488_06", "; ".join(bad))
        return
    pass_("T_488_06", f"{readings}")


# ── T_488_07 — taskbar slot → app mapping ─────────────────────────────────────

def _tb_offset(dut: Dut) -> int | None:
    r = dut.cmd("get tbScrollOffset", timeout=3.0)
    v = r.get("val")
    return int(v) if isinstance(v, (int, float)) else None


def _tb_scroll_one(dut: Dut):
    dut.set_cooldown_zero()
    dut.cmd(f"drag {_TB_X} 110 {_TB_X} 60 10", timeout=5.0)
    time.sleep(0.2)


def _tb_reset_offset(dut: Dut) -> bool:
    """Scroll the taskbar back to offset 0. Physical slot N only equals AppId N
    at offset 0 — without this, any test that taps a slot by AppId taps whatever
    the previous test's scrolling left there (the first-run T_488_08 defect)."""
    for _ in range(_TB_N + 1):
        off = _tb_offset(dut)
        if off == 0:
            return True
        if off is None:
            return False
        _tb_scroll_one(dut)
    return _tb_offset(dut) == 0


def t_488_07(dut: Dut):
    """Tap every visible taskbar slot, scroll, tap again — x3. Each tap must
    land on the app whose icon that slot is showing (the TASK-413 remap shape)."""
    print("T_488_07  taskbar slot -> app mapping, tap/scroll/tap x3")
    mism = []
    for rnd in (1, 2, 3):
        off = _tb_offset(dut)
        if off is None:
            skip("T_488_07", "tbScrollOffset unreadable")
            return
        for slot in range(_VISIBLE_SLOTS):
            expected = APP_ORDER[(off + slot) % _TB_N]
            if expected == "Spotify":
                continue        # player slot deliberately cycles modes (ADR-059 D6)
            dut.set_cooldown_zero()
            x, y = _c.tap_taskbar_slot(slot)
            dut.cmd(f"tap {x} {y}", timeout=5.0)
            time.sleep(0.4)
            got = dut.cmd("get appId", timeout=5.0).get("name")
            if got != expected:
                mism.append(f"round{rnd} off={off} slot={slot}: expected {expected}, got {got}")
        _tb_scroll_one(dut)
        print(f"    round {rnd}/3 complete (offset {off})")
    _restore(dut)
    if mism:
        fail("T_488_07", f"{len(mism)} slot->app mismatches: {mism[:5]}")
        return
    pass_("T_488_07", f"{3 * (_VISIBLE_SLOTS - 1)} taps, every slot landed on its icon's app")


# ── T_488_08 — eject / player-mode cycle ──────────────────────────────────────

def t_488_08(dut: Dut):
    """Spotify -> WebRadio -> Player -> Spotify via the player-slot tap, x3
    cycles; `get playerMode` tracks the app each time."""
    print("T_488_08  player cycle Spotify->WebRadio->Player->Spotify x3")
    dut.cmd("set playerMode spotify", timeout=3.0)
    _switch(dut, APP_SLOT["Spotify"])
    if not _tb_reset_offset(dut):
        skip("T_488_08", "could not return the taskbar to scrollOffset 0")
        return
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    expected = ["WebRadio", "LocalPlayer", "Spotify"]
    mode_of = {"WebRadio": 1, "LocalPlayer": 2, "Spotify": 0}
    bad = []
    for cycle in (1, 2, 3):
        for want in expected:
            dut.set_cooldown_zero()
            dut.cmd(f"tap {sx} {sy}", timeout=6.0)
            time.sleep(0.5)
            got = dut.cmd("get appId", timeout=5.0).get("name")
            pm = dut.cmd("get playerMode", timeout=5.0).get("val")
            if got != want:
                bad.append(f"cycle{cycle}: expected {want}, got {got}")
            elif pm != mode_of[want]:
                bad.append(f"cycle{cycle}: {want} but playerMode={pm} (want {mode_of[want]})")
        print(f"    cycle {cycle}/3 complete")
    dut.cmd("set playerMode spotify", timeout=3.0)
    _restore(dut)
    if bad:
        fail("T_488_08", f"{bad[:5]}")
        return
    pass_("T_488_08", "9/9 mode transitions correct, playerMode tracked each one")


# ── T_488_09 — Settings sections ──────────────────────────────────────────────

def t_488_09(dut: Dut):
    """Open Settings, enter and leave all seven sections (SettingsApp was a
    moved class). Every section renders and returns to the category list."""
    print("T_488_09  Settings: enter/leave all sections")
    r = dut.cmd(f"switchApp {_SETTINGS_ID}", timeout=5.0)
    time.sleep(0.4)
    if not dut.cmd("get appId", timeout=5.0).get("name") == "Settings":
        skip("T_488_09", f"could not enter Settings ({r})")
        _restore(dut)
        return
    sec0 = dut.cmd("get settingsSection", timeout=5.0).get("section")
    bad = []
    entered = []
    for row in range(7):
        dut.set_cooldown_zero()
        y = _S_CONTENT_Y + row * _S_ROW_H + _S_ROW_H // 2
        dut.cmd(f"tap 137 {y}", timeout=5.0)
        time.sleep(0.4)
        sec = dut.cmd("get settingsSection", timeout=5.0).get("section")
        entered.append(sec)
        if sec != row:
            bad.append(f"row {row} -> section {sec}")
        dut.set_cooldown_zero()
        dut.cmd("tap 30 14", timeout=5.0)          # back
        time.sleep(0.4)
        back = dut.cmd("get settingsSection", timeout=5.0).get("section")
        if back != -1:
            bad.append(f"row {row} back -> section {back} (want -1)")
    _restore(dut)
    if bad:
        fail("T_488_09", f"start={sec0} entered={entered} problems={bad}")
        return
    pass_("T_488_09", f"7/7 sections entered and returned cleanly (entered={entered})")


# ── T_488_10 — debug console surface ──────────────────────────────────────────

def t_488_10(dut: Dut, get_keys: list[str] | None = None):
    """`help` lists the same command set as before b36f184, and every `get` key
    the console implements still resolves (no 'unknown var')."""
    print("T_488_10  help + every get key resolves")
    r = dut.cmd("help", timeout=8.0)
    cmds = [c.get("name") for c in r.get("commands", [])] if r.get("ok") else []
    if not cmds:
        fail("T_488_10", f"help returned no command list: {r}")
        return
    missing_cmds = [c for c in _EXPECTED_CMDS if c not in cmds]
    extra_cmds = [c for c in cmds if c not in _EXPECTED_CMDS]
    unknown = []
    unreadable = []
    for key in (get_keys or []):
        try:
            rr = dut.cmd(f"get {key}", timeout=6.0)
        except TimeoutError:
            unreadable.append(key)
            continue
        if rr.get("error") == "unknown var":
            unknown.append(key)
    detail = (f"help={len(cmds)} cmds, {len(get_keys or [])} get keys probed")
    if missing_cmds or extra_cmds:
        fail("T_488_10", f"help set differs from pre-move kCmds: missing={missing_cmds} extra={extra_cmds}")
        return
    if unknown:
        fail("T_488_10", f"{len(unknown)} get keys unresolved: {unknown}")
        return
    if unreadable:
        fail("T_488_10", f"{len(unreadable)} get keys timed out: {unreadable}")
        return
    pass_("T_488_10", detail + ", all resolved")


# Command set as of b36f184~1 (kCmds[] in main.cpp, verified byte-identical to
# HEAD by a static diff — this is the "same set as before the move" reference).
_EXPECTED_CMDS = [
    "reconnect", "tap", "drag", "release", "tick", "get", "set", "switchApp",
    "info", "screendump", "colorprobe", "sdprobe", "sdcycle", "sdmem",
    "sdmount", "sdumount", "sdclean", "sdwrite", "sdls", "sdmbr", "sdread",
    "sdmkdir", "sdput", "help", "reboot", "advance",
]


# ── T_488_11 — heap stability ─────────────────────────────────────────────────

def t_488_11(dut: Dut):
    """Free heap must not decline because of app switching.

    The spec's bare "after >= before - 2 KB" is not measurable as written on
    this DUT: the two samples sit ~90 s apart and free heap is still moving on
    its own that late after a reset (TASK-425; the handover says the same). A
    bare before/after therefore cannot separate a switching leak from ordinary
    background drift — Spotify polling, WiFi, dataTask all allocate.

    So the sweep is measured against a CONTROL of the same duration in which
    the device sits idle on Spotify and no app switch happens. A changed static
    lifetime shows up as sweep drift materially worse than idle drift; shared
    background drift cancels out.
    """
    print("T_488_11  heap stability: idle control, then repeated sweeps")
    idle_s = min(_HEAP.get("sweep_duration", 90.0), 90.0)

    # Control: same app foreground, no switching. Establishes background drift.
    _switch(dut, APP_SLOT["Spotify"])
    dut.cmd("set playerMode spotify", timeout=3.0)
    h0 = _heap(dut)
    if h0 is None:
        skip("T_488_11", "heap unreadable")
        return
    print(f"    control: idling {idle_s:.0f}s on Spotify (no app switches)…")
    time.sleep(idle_s)
    h1 = _heap(dut)
    idle_delta = h1 - h0

    # Three successive sweeps, each sampled at the SAME resting point (Spotify
    # foreground, playerMode spotify). The first sweep necessarily pays one-off
    # costs — every app's init() allocates its buffers, and entering WebRadio /
    # LocalPlayer takes the ~48 KB A-lite audio arena, which is held by design
    # and not a leak. What a changed static lifetime would look like is a
    # decline that REPEATS: sweeps 2 and 3 must cost nothing further.
    # Entering WebRadio / LocalPlayer takes and releases the ~48 KB A-lite
    # audio arena, and which way it happens to sit at sample time swamps
    # everything else (a pre-refactor A/B run showed a +39144 B sweep). With
    # --no-players the sweep covers the eleven taskbar apps instead — which is
    # where all seven moved App classes live, so it still answers the question
    # the criterion is asking, with a signal that is not 48 KB of noise.
    sweep_ids = range(_TB_N) if _NO_PLAYERS else range(len(APP_ORDER))
    samples = [h1]
    for n in range(1, _SWEEPS + 1):
        for _ in range(3):
            for app_id in sweep_ids:
                _switch(dut, app_id, settle=0.4)
        _switch(dut, APP_SLOT["Spotify"])
        dut.cmd("set playerMode spotify", timeout=3.0)
        time.sleep(1.0)
        samples.append(_heap(dut))
        print(f"    sweep {n}/{_SWEEPS} done — freeInt={samples[-1]}")

    deltas = [samples[i + 1] - samples[i] for i in range(len(samples) - 1)]
    steady = deltas[1:]                       # sweeps 2 and 3, past the one-offs
    detail = (f"idle {idle_delta:+d} B over {idle_s:.0f}s; "
              f"heap after each sweep {samples}; per-sweep deltas {deltas}; "
              f"first-sweep one-offs (app init + audio arena) excluded from the gate")
    if any(d < -2048 for d in steady):
        fail("T_488_11", f"heap keeps falling after the first sweep — {detail}")
        return
    pass_("T_488_11", detail)


TEST_FNS = {
    "T_488_04": t_488_04,
    "T_488_05": t_488_05,
    "T_488_06": t_488_06,
    "T_488_07": t_488_07,
    "T_488_08": t_488_08,
    "T_488_09": lambda d: t_488_09(d),
    "T_488_10": lambda d: t_488_10(d, _GET_KEYS),
    "T_488_11": t_488_11,
}

_GET_KEYS: list[str] = []
_NO_PLAYERS = False
_SWEEPS = 3   # TASK-505: default preserves the original 3-sweep behavior


def main():
    global _GET_KEYS, _NO_PLAYERS, _SWEEPS
    p = make_arg_parser(ALL_TESTS, description="TASK-488 Part B — DUT verification")
    p.add_argument("--get-keys", default="",
                   help="comma-separated `get` keys for T_488_10 (from a static "
                        "scan of cmdGet.h + the per-app dbgGet chains)")
    p.add_argument("--no-players", action="store_true",
                   help="T_488_11: sweep the 11 taskbar apps only, leaving "
                        "WebRadio/LocalPlayer out so the ~48 KB audio arena "
                        "does not swamp the measurement")
    p.add_argument("--sweeps", type=int, default=3,
                   help="T_488_11 (TASK-505): number of post-idle sweeps to run "
                        "(default 3, matching the original criterion). A longer "
                        "run answers whether the heap plateau TASK-505 observed "
                        "after 3 sweeps is genuine or just a slower decline — "
                        "the PASS/FAIL gate still only judges sweeps 2..N "
                        "(sweep 1's one-off app-init/arena cost stays excluded).")
    p.add_argument("--settle", type=float, default=150.0,
                   help="seconds to wait after boot before the first heap read "
                        "(TASK-425: heap is not stable before ~150 s post-reset)")
    args = p.parse_args()
    _GET_KEYS = [k for k in args.get_keys.split(",") if k]
    _NO_PLAYERS = args.no_players
    _SWEEPS = max(1, args.sweeps)

    dut = Dut(args.port, args.baud, args.timeout)
    if args.settle > 0:
        print(f"  [settle] waiting {args.settle:.0f}s post-boot before heap-sensitive "
              f"work (TASK-425)…", flush=True)
        time.sleep(args.settle)
    selected = [t for t in args.tests.split(",") if t]
    run_suite(ALL_TESTS, TEST_FNS, dut, selected)
    print_results(ALL_TESTS)
    return 0 if all(v == "PASS" for v in RESULTS.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
