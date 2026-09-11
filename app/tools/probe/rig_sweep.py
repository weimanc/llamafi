#!/usr/bin/env python3
"""probe/rig_sweep.py — PROP-011 X-P2 B_boot sweep driver (TASK-677 H-1).

For each level in --levels (stop at the first level that produces no trip,
unless --all), --reps times: `bod N` (sets the boot threshold), `reboot`
(a real reset), wait for `[bootphase] 6` (timeout 60s), record whether
`[bod] TRIP tag=wifi-end` appeared in that boot's slice of the log and its
`min=`/`dur=` fields. Reports B_boot and the per-level trip table.

THIS DRIVER RESETS THE BOARD — every `reboot` ends whatever TASK-557
observation window is running (PROP-011-runbook.md §0.1 rule 2). It refuses
to run at all unless invoked with --i-know-this-resets-the-board, and even
then it first writes `./run/rig-timeline --since 48h` to a file (so the
window's length is captured before it ends) and stamps
`note phase=X-P2-sweep level=N` before each reboot.

This session only implements and --dry-run's it (PROP-011-runbook.md §3
X-P2: Sonnet drives it, but the reflash-window cost means it is scheduled,
not executed, by whoever is running H-1's own commit). Still talks to the
board ONLY through the tmux monitor (lib.monitor_tmux) plus `reboot` sent
the same way — never opens the serial port itself.

    python3 probe/rig_sweep.py --dry-run --levels 7,5,3,2,1,0 --reps 3
    python3 probe/rig_sweep.py --i-know-this-resets-the-board \\
        --levels 7,5,3,2,1,0 --reps 3 --timeline-out /tmp/p2_pre_timeline.txt
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from lib import monitor_tmux as mt  # noqa: E402
from lib import rigwatch  # noqa: E402

_BOOTPHASE0_RE = re.compile(r"\[bootphase\]\s+0\b")
_BOOTPHASE6_RE = re.compile(r"\[bootphase\]\s+6\b")
_WIFI_END_TRIP_RE = re.compile(
    r"\[bod\] TRIP tag=wifi-end[^\n]*\bmin=(\d+)[^\n]*\bdur=(\d+)")
#: F-1's ordering is `... dur=<n> ... min=<n>` — accept either field order so
#: this driver does not silently miss a trip if that ordering ever changes.
_WIFI_END_TRIP_RE_ALT = re.compile(
    r"\[bod\] TRIP tag=wifi-end[^\n]*\bdur=(\d+)[^\n]*\bmin=(\d+)")
#: PROP-011 X-P2b-2: `[bodmit] inwindow mask=<m> t=<ms> duty=<d> txdbm=<n>` is the
#: applied-state proof that bit0 (backlight forced off across WiFi init) actually
#: took effect this boot — duty must read 0 when bit0 is set.
_BODMIT_INWINDOW_RE = re.compile(r"\[bodmit\] inwindow mask=(\d+)[^\n]*\bduty=(\d+)")
#: The console's `bod` QUERY reply (bare `bod`, no argument) — used as a
#: liveness check that the console is actually reading Serial before we type
#: anything else at it. The SET reply (`bod N`) has `"bootThres"` but not
#: `"thresNow"`, so this pattern (requiring thresNow) never matches a set-ack.
_BOD_QUERY_ACK_RE = re.compile(
    r'\{"ok":true,"cmd":"bod","thresNow":(\d+),"bootThres":(\d+)')
#: `bod N`'s SET reply carries `"note"` right after bootThres and no thresNow.
_BOD_SET_ACK_RE = re.compile(r'\{"ok":true,"cmd":"bod","bootThres":(\d+),"note"')
#: `bodmit N`'s reply (set or query — both carry bootMit; set additionally
#: carries "note", which we don't need to key on since the query form is never
#: sent by this driver's write path).
_BODMIT_ACK_RE = re.compile(r'\{"ok":true,"cmd":"bodmit","bootMit":(\d+)')
_BOD_ARMED_RE = re.compile(r"\[bod\] armed thres=(\d+)")

DEFAULT_LEVELS = [7, 5, 3, 2, 1, 0]
BOOT_TIMEOUT_S = 60.0
ACK_TIMEOUT_S = 5.0


def parse_boot_slice(text: str) -> dict:
    """Pure: whether the boot's `wifi-end` trip appeared, and its fields, out
    of one boot's log slice. No device/tmux involved — exercised directly by
    the fixture tests below."""
    m = _WIFI_END_TRIP_RE.search(text)
    if m:
        return {"tripped": True, "min": int(m.group(1)), "dur": int(m.group(2))}
    m = _WIFI_END_TRIP_RE_ALT.search(text)
    if m:
        return {"tripped": True, "min": int(m.group(2)), "dur": int(m.group(1))}
    return {"tripped": False, "min": None, "dur": None}


def reached_bootphase6(text: str) -> bool:
    return bool(_BOOTPHASE6_RE.search(text))


def slice_since_bootphase0(text: str) -> str | None:
    """Pure: the reviewer's fault #2 fix. `text` is everything read since the
    offset taken BEFORE the `reboot` was sent (which may still contain the
    tail of the PREVIOUS boot, if that previous boot's own reader hadn't
    caught up yet). Returns only what comes from the first `[bootphase] 0`
    onward — the new boot — or None if that boot hasn't reached phase 0 yet
    (caller should keep polling)."""
    m = _BOOTPHASE0_RE.search(text)
    return text[m.start():] if m else None


def bod_query_ack_seen(text: str) -> bool:
    """Pure: did a bare `bod` query reply appear (console liveness check)?"""
    return bool(_BOD_QUERY_ACK_RE.search(text))


def bod_set_ack_level(text: str) -> int | None:
    """Pure: the bootThres value from the most recent `bod N` SET reply, or
    None if no set-ack appears."""
    matches = list(_BOD_SET_ACK_RE.finditer(text))
    return int(matches[-1].group(1)) if matches else None


def bodmit_ack_mask(text: str) -> int | None:
    """Pure: the bootMit value from the most recent `bodmit N` reply, or None
    if no ack appears."""
    matches = list(_BODMIT_ACK_RE.finditer(text))
    return int(matches[-1].group(1)) if matches else None


def armed_level_from(text: str) -> int | None:
    """Pure: the threshold this boot actually armed with, from its own
    `[bod] armed thres=` line (first occurrence in the slice)."""
    m = _BOD_ARMED_RE.search(text)
    return int(m.group(1)) if m else None


def parse_bodmit_proof(text: str, requested: int = 0) -> dict:
    """Pure: did `[bodmit] inwindow ...` appear in this boot's log slice, and
    does it prove the REQUESTED mask (default 0 = unmitigated, matching the
    board's rest state) was the one actually applied? Reviewer fix #4: proof
    now compares requested vs applied mask, not just internal duty/mask
    self-consistency — a boot that silently kept the old mask must not read
    as proved just because that old mask's own duty reading was consistent."""
    m = _BODMIT_INWINDOW_RE.search(text)
    if not m:
        return {"seen": False, "mask": None, "duty": None, "proved": False}
    mask, duty = int(m.group(1)), int(m.group(2))
    proved = (mask == requested) and ((duty == 0) if (requested & 1) else True)
    return {"seen": True, "mask": mask, "duty": duty, "proved": proved}


def _dry_run(levels: list[int], reps: int, bodmit: int | None = None) -> None:
    print("[dry-run] would write ./run/rig-timeline --since 48h to a file first")
    for level in levels:
        for rep in range(reps):
            print(f"[dry-run] stamp phase=X-P2-sweep level={level} rep={rep} bodmit={bodmit}")
            print(f"[dry-run] send: bod (liveness check, wait <={ACK_TIMEOUT_S:.0f}s for ack)")
            if bodmit is not None:
                print(f"[dry-run] send: bodmit {bodmit} (wait for ack, else INVALID)")
            print(f"[dry-run] send: bod {level} (wait for ack, else INVALID)")
            print("[dry-run] send: reboot   <-- RESETS THE BOARD")
            print(f"[dry-run] wait up to {BOOT_TIMEOUT_S:.0f}s for the NEW boot's own "
                 f"[bootphase] 0 then [bootphase] 6, slice from bootphase 0 onward, "
                 f"parse [bod] TRIP tag=wifi-end within that slice only")
        print(f"[dry-run] (stop descending here if level={level} produced 0/{reps} trips, "
             f"unless --all)")


def _wait_for(off: int, predicate, timeout_s: float, poll: float = 0.5) -> tuple[bool, str]:
    """Poll `mt.read_from(off)` until `predicate(text)` is truthy or timeout.
    Returns (found, last-text-read). Not pure (reads the device log) — the
    thing under test in the fixtures below is `predicate`, not this loop."""
    deadline = time.monotonic() + timeout_s
    text = mt.read_from(off)
    while not predicate(text):
        if time.monotonic() >= deadline:
            return False, text
        time.sleep(poll)
        text = mt.read_from(off)
    return True, text


def _invalid(level: int, rep: int, bodmit: int | None, reason: str) -> dict:
    print(f"INVALID boot level={level} rep={rep} bodmit={bodmit}: {reason}")
    return {"level": level, "rep": rep, "bodmit": bodmit, "invalid": reason,
            "tripped": False, "booted": False}


def run_one_boot(level: int, rep: int, bodmit: int | None = None) -> dict:
    rigwatch.stamp("note", phase="X-P2-sweep", level=str(level), rep=str(rep),
                    bodmit=str(bodmit) if bodmit is not None else "-")
    requested_mask = bodmit if bodmit is not None else 0

    # Reviewer fault #1/#2: never type into a board that might still be
    # booting from the PREVIOUS reboot. Confirm the console is live first.
    off = mt.size()
    mt.send("bod")
    ok, text = _wait_for(off, bod_query_ack_seen, ACK_TIMEOUT_S)
    if not ok:
        return _invalid(level, rep, bodmit, "console did not ack a bare `bod` "
                         f"query within {ACK_TIMEOUT_S}s — board likely still booting")

    if bodmit is not None:
        off = mt.size()
        mt.send(f"bodmit {bodmit}")
        ok, text = _wait_for(off, lambda t: bodmit_ack_mask(t) is not None, ACK_TIMEOUT_S)
        got = bodmit_ack_mask(text) if ok else None
        if not ok or got != bodmit:
            return _invalid(level, rep, bodmit,
                             f"bodmit {bodmit} not acked (got {got!r})")

    off = mt.size()
    mt.send(f"bod {level}")
    ok, text = _wait_for(off, lambda t: bod_set_ack_level(t) is not None, ACK_TIMEOUT_S)
    got = bod_set_ack_level(text) if ok else None
    if not ok or got != level:
        return _invalid(level, rep, bodmit, f"bod {level} not acked (got {got!r})")

    # Only now — both acks confirmed — do we reboot.
    pre_reboot_off = mt.size()
    mt.send("reboot")

    # Reviewer fault #3: analyse only the NEW boot. Wait for its own
    # [bootphase] 0 before trusting anything in the read text as this boot's.
    deadline = time.monotonic() + BOOT_TIMEOUT_S
    boot_text = None
    booted = False
    while time.monotonic() < deadline:
        raw = mt.read_from(pre_reboot_off)
        boot_text = slice_since_bootphase0(raw)
        if boot_text is not None and reached_bootphase6(boot_text):
            booted = True
            break
        time.sleep(1.0)
    if boot_text is None:
        # Never reached [bootphase] 0 at all within the timeout.
        return _invalid(level, rep, bodmit,
                         "no [bootphase] 0 seen after reboot within "
                         f"{BOOT_TIMEOUT_S}s")

    result = parse_boot_slice(boot_text)
    result["level"] = level
    result["rep"] = rep
    result["booted"] = booted
    result["bodmit"] = bodmit
    result["armed_level"] = armed_level_from(boot_text)
    result.update({f"bodmit_{k}": v
                    for k, v in parse_bodmit_proof(boot_text, requested_mask).items()})
    return result


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--levels", default="7,5,3,2")
    ap.add_argument("--allow-low-levels", action="store_true",
                    help="permit levels 1 and 0 — on 2026-09-11 every WiFi boot armed at "
                         "<=1 dropped the CH340 off USB (EXP-035); the board then stays armed "
                         "there and the console is unreachable")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--bodmit", type=int, default=None, choices=[0, 1, 2, 3],
                    help="PROP-011 X-P2b-2: send `bodmit N` before each `bod <level>` "
                         "this run (bit0 = backlight forced off across the WiFi-init "
                         "window only). Omit to leave bodmit untouched.")
    ap.add_argument("--all", action="store_true",
                    help="do not stop descending at the first no-trip level")
    ap.add_argument("--timeline-out", default="/tmp/rig_sweep_pre_timeline.txt")
    ap.add_argument("--i-know-this-resets-the-board", action="store_true",
                    dest="confirmed")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    levels = [int(x) for x in a.levels.split(",") if x.strip()]

    if a.dry_run:
        _dry_run(levels, a.reps, a.bodmit)
        return 0

    if min(levels, default=7) < 2 and not a.allow_low_levels:
        print("REFUSED: levels below 2 drop the CH340 off USB on every WiFi boot on this "
              "board (EXP-035), leaving it armed low with the console unreachable. Pass "
              "--allow-low-levels only with a recovery plan (EXP-035 §aftermath).",
              file=sys.stderr)
        return 3

    if not a.confirmed:
        print("REFUSED: rig_sweep.py resets the board on every rep (each "
             "`reboot` ends any live TASK-557 observation window). Re-run "
             "with --i-know-this-resets-the-board, after reading "
             "PROP-011-runbook.md §0.1 rule 2 and §3 X-P2.", file=sys.stderr)
        return 3

    try:
        timeline = subprocess.run(
            [sys.executable, "-m", "lib.rigwatch", "timeline", "--since", "48h"],
            cwd=TOOLS, capture_output=True, text=True, timeout=30, check=False)
        with open(a.timeline_out, "w", encoding="utf-8") as fh:
            fh.write(timeline.stdout)
        print(f"pre-reflash timeline captured -> {a.timeline_out}")
    except (OSError, subprocess.SubprocessError) as e:
        print(f"WARN: could not capture the pre-reflash timeline: {e}", file=sys.stderr)

    results = []
    try:
        for level in levels:
            level_results = []
            for rep in range(a.reps):
                r = run_one_boot(level, rep, bodmit=a.bodmit)
                level_results.append(r)
                print(r)
            results.extend(level_results)
            trips = sum(1 for r in level_results if r["tripped"])
            print(f"level={level}: {trips}/{a.reps} tripped")
            if not a.all and trips == 0:
                print(f"stopping descent at level={level} (0/{a.reps} tripped)")
                break
    finally:
        # `bod N` and `bodmit N` both persist across reboots (RTC_NOINIT): never leave
        # the board armed at a sweep level or with the backlight mitigation still set.
        # bodmit must go back to 0 BEFORE bod 7, not after. monitor_tmux.send() stamps
        # the reboot as a harness reset.
        mt.send("bodmit 0")
        time.sleep(0.5)
        mt.send("bod 7")
        time.sleep(1.0)
        restore_off = mt.size()
        mt.send("reboot")
        # Reviewer fault #1: THIS process's own exit must not race the next
        # invocation's first command into a board that hasn't booted yet —
        # wait for the restore boot to actually reach ready before returning.
        ready, _ = _wait_for(restore_off, reached_bootphase6, BOOT_TIMEOUT_S)
        print(f"restored: bodmit 0 + bod 7 + reboot sent, "
              f"{'ready' if ready else f'NOT ready within {BOOT_TIMEOUT_S:.0f}s'}")

    print("\nlevel  trips/reps")
    for level in levels:
        rs = [r for r in results if r["level"] == level]
        if not rs:
            continue
        trips = sum(1 for r in rs if r["tripped"])
        print(f"{level:>5}  {trips}/{len(rs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
