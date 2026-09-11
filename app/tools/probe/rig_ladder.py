#!/usr/bin/env python3
"""probe/rig_ladder.py — PROP-011 X-P2 load ladder on the F-4 bare rig.

For each rung (1 bare, 2 +WiFi, 3 +WiFi+TFT, 4 +WiFi+TFT+SD, 6 display-only
+TFT no WiFi — PROP-011 X-P2b-1) and each brownout
level in descending order: build and flash rig/bare_bod with that rung's
-DBARE_* flags and -DBARE_BOD_THRES=<level>, then capture REPS boots. A boot =
stamp `reset who=xp2` in rigwatch, open the port, pulse EN via RTS, read up to
BOOT_TIMEOUT_S, and record whether `[bod] TRIP tag=wifi-end` appeared. A rung
stops descending at its first level with 0/REPS trips; B_boot for the rung is
the lowest level that tripped at least once.

THIS DRIVER FLASHES AND RESETS THE BOARD and opens the serial port directly —
the experiment needs it. It refuses without --i-know-this-resets-the-board, and
refuses if F-4 (rig/bare_bod/src/debug/bodWatch.h) is absent. Nothing at import.

    python3 probe/rig_ladder.py --i-know-this-resets-the-board --out /tmp/claude-1000/xp2/ladder.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
BARE_RIG_DIR = os.environ.get("BARE_RIG_DIR", os.path.join(REPO, "rig", "bare_bod"))
PORT_DEFAULT = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
PIO = os.path.expanduser("~/.platformio/penv/bin/pio")

LEVELS = (7, 5, 3, 2, 1, 0)
RUNGS = (1, 2, 3, 4)
REPS = 3
BOOT_TIMEOUT_S = 30.0
RUNG_FLAGS = {1: "", 2: "-DBARE_WIFI", 3: "-DBARE_WIFI -DBARE_TFT",
              4: "-DBARE_WIFI -DBARE_TFT -DBARE_SD",
              6: "-DBARE_TFT"}


def marker(bare_rig_dir: str) -> str:
    return os.path.join(bare_rig_dir, "src", "debug", "bodWatch.h")


def f4_landed(marker_path: str) -> bool:
    return os.path.exists(marker_path)


def build_flags(rung: int, level: int, extra: str = "") -> str:
    return f"{RUNG_FLAGS[rung]} -DBARE_BOD_THRES={level} {extra}".strip()


_TRIP_RE = re.compile(r"\[bod\] TRIP tag=wifi-end\b")
_REASON_RE = re.compile(r"\[bootreason\] (\d+) (\w+)")
_THRES_RE = re.compile(r"\[bod\] armed thres=(\d+)")


def parse_boot(text: str) -> dict:
    """Pure: one boot's serial text -> what the ladder needs."""
    reason = _REASON_RE.search(text)
    thres = _THRES_RE.search(text)
    return {"tripped": bool(_TRIP_RE.search(text)),
            "ready": "[bootphase] 6 ready" in text,
            "bootreason": int(reason.group(1)) if reason else None,
            "armed_thres": int(thres.group(1)) if thres else None,
            "wifi_ip": "[wifi] IP " in text,
            "usb_drop": "[rig] usb-drop" in text}


def b_boot(level_results: dict) -> int | None:
    """Pure: {level: trips} for one rung -> lowest level with >=1 trip, or None."""
    tripped = [lvl for lvl, trips in level_results.items() if trips > 0]
    return min(tripped) if tripped else None


def keep_descending(trips: int) -> bool:
    return trips > 0


def stop_rung(trips: int, drops: int, no_stop: bool) -> bool:
    """Pure: stop descending this rung after this level? A USB-dropped boot is
    NO DATA, not a quiet boot, so a level whose only non-trips are drops never
    ends the descent (2026-09-11: level 1 dropped USB on 3/3 first boots)."""
    if no_stop:
        return False
    return not keep_descending(trips) and drops == 0


def wait_for_node(port: str, timeout_s: float = 20.0) -> bool:
    """After a USB drop the by-id node is gone until re-enumeration finishes."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if os.path.exists(port):
            time.sleep(1.5)   # let the ch341 driver finish binding
            return True
        time.sleep(0.25)
    return False


def _stamp(kind: str, **kw) -> None:
    from lib import rigwatch as rw
    rw.stamp(kind, **kw)


def _flash(bare_rig_dir: str, port: str, flags: str) -> bool:
    import subprocess
    env = dict(os.environ, PLATFORMIO_BUILD_FLAGS=flags)
    for attempt in range(4):
        _stamp("flash-begin", who="xp2", flags=flags)
        p = subprocess.run([PIO, "run", "-e", "bare", "-t", "upload", "--upload-port", port],
                           cwd=bare_rig_dir, env=env, capture_output=True, text=True, timeout=600)
        _stamp("flash-end", who="xp2", rc=str(p.returncode))
        if p.returncode == 0:
            return True
        time.sleep(2)
    sys.stderr.write((p.stdout or "")[-1500:] + (p.stderr or "")[-1500:])
    return False


def _capture_boot(port: str) -> str:
    import serial
    if not wait_for_node(port):
        return "\n[rig] usb-drop: port node absent for 20 s before the boot\n"
    _stamp("reset", who="xp2")
    s = serial.Serial()
    s.port, s.baudrate, s.timeout = port, 115200, 0.5
    s.dtr = False
    s.rts = False
    s.open()
    s.rts = True            # EN low
    time.sleep(0.1)
    s.rts = False           # EN released -> boot
    buf, t0, ready_at = [], time.time(), None
    while time.time() - t0 < BOOT_TIMEOUT_S:
        try:
            d = s.read(4096)
        except serial.SerialException as e:
            # The CH340 fell off USB mid-boot (2026-09-11, rung 2 level 1). That
            # is the TASK-557 signature and the thing being measured: record it
            # as data. Never reopen inside this boot — an open is another reset.
            buf.append(f"\n[rig] usb-drop at +{time.time() - t0:.2f}s: {e}\n")
            break
        if d:
            buf.append(d.decode("utf-8", "replace"))
            if ready_at is None and "[bootphase] 6 ready" in "".join(buf):
                ready_at = time.time()
        if ready_at and time.time() - ready_at > 2.0:
            break
    try:
        s.close()
    except (serial.SerialException, OSError):
        pass
    return "".join(buf)


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rungs", default=",".join(str(r) for r in RUNGS))
    ap.add_argument("--levels", default=",".join(str(l) for l in LEVELS))
    ap.add_argument("--reps", type=int, default=REPS)
    ap.add_argument("--bare-rig-dir", default=BARE_RIG_DIR)
    ap.add_argument("--port", default=PORT_DEFAULT)
    ap.add_argument("--out", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--extra-flags", default="",
                    help="appended to every build, e.g. '-DBOD_NO_ISR' for an A/B")
    ap.add_argument("--no-stop", action="store_true",
                    help="run every listed level in the given order (targeted repeats)")
    ap.add_argument("--i-know-this-resets-the-board", action="store_true")
    return ap


def main(argv: list) -> int:
    a = build_arg_parser().parse_args(argv)
    rungs = [int(x) for x in a.rungs.split(",") if x.strip()]
    levels = [int(x) for x in a.levels.split(",") if x.strip()]
    if a.dry_run:
        print(f"[dry-run] bare rig: {a.bare_rig_dir}")
        for rung in rungs:
            for level in levels:
                print(f"[dry-run] rung={rung} level={level}: PLATFORMIO_BUILD_FLAGS="
                      f"'{build_flags(rung, level, a.extra_flags)}' pio run -e bare -t upload; "
                      f"{a.reps} boots; stop the rung at the first 0/{a.reps} level")
        return 0
    if not f4_landed(marker(a.bare_rig_dir)):
        print(f"REFUSED: F-4 not landed — no {marker(a.bare_rig_dir)}. "
              "See PROP-011-runbook.md §1 F-4.", file=sys.stderr)
        return 3
    if not a.i_know_this_resets_the_board:
        print("rig_ladder: refusing — flashes and resets the board and opens the port. "
              "Re-run with --i-know-this-resets-the-board.", file=sys.stderr)
        return 3
    summary = {}
    for rung in rungs:
        per_level = {}
        for level in levels:
            flags = build_flags(rung, level, a.extra_flags)
            if not _flash(a.bare_rig_dir, a.port, flags):
                print(json.dumps({"rung": rung, "level": level, "error": "flash failed"}), flush=True)
                return 1
            trips = drops = 0
            for rep in range(1, a.reps + 1):
                text = _capture_boot(a.port)
                row = {"rung": rung, "level": level, "rep": rep, "t": round(time.time(), 3),
                       **parse_boot(text)}
                trips += int(row["tripped"])
                drops += int(row["usb_drop"])
                print(json.dumps(row), flush=True)
                if a.out:
                    with open(a.out, "a") as fh:
                        fh.write(json.dumps(row) + "\n")
                    with open(a.out + ".raw", "a") as fh:
                        fh.write(f"\n===== rung={rung} level={level} rep={rep} t={row['t']} =====\n{text}")
            per_level[f"{level}@{len(per_level)}" if level in per_level else level] = trips
            if stop_rung(trips, drops, a.no_stop):
                break
        summary[rung] = {"trips_by_level": per_level, "b_boot": b_boot(per_level)}
        print(json.dumps({"rung": rung, **summary[rung]}), flush=True)
    print(json.dumps({"summary": summary}), flush=True)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.exit(main(sys.argv[1:]))
